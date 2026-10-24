"""Owned QS image identity, original paired schemas, binding and full restore.

Preparation component only: does not start business runtimes or authorize cutover.
"""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import time

from audit_transaction_limit import write_private
from image_start_fixture import OwnedImageFixture, require

QS_SHA = 'd6fdc2bcda6db5cd84fd3a2f53b782448ac1e0b7'
QS_HEAD = (110, 44)
MONGO = 'mongo@sha256:340c1c56fb10e95cf79ff547f8664b96bc6ead9909bc355238cbf865a9695a6f'
GO_SUM = 'h1:JUayISCwmVwrLbHfLvgiOo3jr3Dxs7JfWeF3/Br45O0='


def canonical_dump(raw):
    # MySQL verified bug110825: a recreated column gains an explicit redundant
    # CHARACTER SET in SHOW CREATE. Keep the original protection bytes; compare
    # this one syntactic difference only alongside exact information_schema
    # column metadata. Never rewrite INSERT, comments, collation or values.
    pattern = re.compile(r'^([ \t]+`[A-Za-z0-9_]+` (?:varchar\([0-9]+\)|char\([0-9]+\)|(?:tiny|medium|long)?text|enum\([^;]*\)|set\([^;]*\))) CHARACTER SET (utf8mb[34]) (COLLATE \2_[a-z0-9_]+.*)$', re.MULTILINE)
    return pattern.sub(lambda m: m[1] + ' ' + m[3], raw)


def dump_difference(before, after):
    """Diagnostic shape and hashes only; never export SQL/data/comment text."""
    def line(value):
        if value.startswith('CREATE TABLE '): kind = 'create_table'
        elif value.startswith('INSERT INTO '): kind = 'insert_rows'
        elif value.lstrip().startswith('`'): kind = 'column_definition'
        elif value.startswith(') '): kind = 'table_options'
        elif value.startswith('/*!'): kind = 'versioned_directive'
        else: kind = 'other'
        return dict(kind=kind, bytes=len(value.encode()), sha256=hashlib.sha256(value.encode()).hexdigest(),
                    encoding_tokens=sorted(set(re.findall(r'\b(?:utf8mb4|utf8mb3|latin1)(?:_[a-z0-9_]+)?\b', value))) if kind != 'insert_rows' else [])
    a, b = before.splitlines(), after.splitlines()
    return [dict(before=[line(v) for v in a[i:j]], after=[line(v) for v in b[k:l]])
            for op,i,j,k,l in difflib.SequenceMatcher(a=a,b=b,autojunk=False).get_opcodes() if op!='equal'][:16]


def initializer_receipt(raw, profile):
    rows = [line.removeprefix('QS_IMAGE_INIT ') for line in raw.splitlines() if line.startswith('QS_IMAGE_INIT ')]
    require(len(rows) == 1, 'one_original_initializer_receipt_required')
    value = json.loads(rows[0])
    heads = (105, 40) if profile == 'pre_m3' else QS_HEAD
    require(value['source_sha'] == QS_SHA and value['profile'] == profile
            and (value['mysql'], value['mongo']) == heads
            and re.fullmatch('[0-9a-f]{64}', value['resources_sha256'])
            and value['original_templates_applied'] is True
            and value['journal_force_used'] is False and value['production'] is False,
            'exact_original_initializer_receipt_required')
    return value


def mongo_snapshot_program(database):
    require(re.fullmatch(r'qs_m3_image_[a-z0-9_]{1,36}', database), 'owned_database_required')
    # Sort object keys as well as collection/index/document order. UUIDs are
    # retained in the evidence; dropping/restoring must preserve original IDs.
    return '''const d=db.getSiblingDB(''' + json.dumps(database) + ''');
function ordered(v){if(Array.isArray(v))return v.map(ordered);if(v&&typeof v==='object'){const r={};for(const k of Object.keys(v).sort())r[k]=ordered(v[k]);return r;}return v;}
const value=d.getCollectionInfos().sort((a,b)=>a.name.localeCompare(b.name)).map(c=>({
 name:c.name,type:c.type,options:c.options,uuid:c.info.uuid,
 indexes:d.getCollection(c.name).getIndexes().sort((a,b)=>a.name.localeCompare(b.name)),
 documents:d.getCollection(c.name).find().sort({_id:1}).toArray()}));
print(JSON.stringify(ordered(JSON.parse(EJSON.stringify(value,{relaxed:false})))));'''


class QSPairFixture(OwnedImageFixture):
    def dump(self, database):
        # A full database can have seed rows inserted in non-key order. Compare
        # deterministic original dump output, not physical table scan order.
        return self.run(self.compose + ['exec', '-T', 'mysql', 'sh', '-c',
            'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --order-by-primary --hex-blob --compact --skip-comments --skip-dump-date --no-tablespaces --set-gtid-purged=OFF --skip-lock-tables --column-statistics=0 "$@"',
            'owned-protection', database]).stdout

    def mongo(self, program):
        return self.run(['docker', 'exec', self.mongo_name, 'mongosh', '--quiet', '--eval', program]).stdout.strip()

    def mongo_dependencies(self):
        self.run(['docker', 'pull', MONGO], timeout=300)
        self.mongo_name = self.project + '-mongo'
        self.run(['docker', 'run', '-d', '--name', self.mongo_name, '--label', self.label,
                  '--network', self.network, '--network-alias', 'mongo', '--memory', '512m', '--cpus', '1',
                  '--tmpfs', '/data/db', '--tmpfs', '/data/configdb', MONGO,
                  'mongod', '--replSet', 'image-proof', '--bind_ip_all', '--wiredTigerCacheSizeGB', '0.25'])
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            result = self.run(['docker', 'exec', self.mongo_name, 'mongosh', '--quiet', '--eval', 'db.adminCommand({ping:1})'], required=False)
            if result.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError('owned_mongo_ping_budget_exceeded')
        self.mongo("rs.initiate({_id:'image-proof',members:[{_id:0,host:'mongo:27017'}]})")
        while time.monotonic() < deadline:
            if self.mongo('print(db.hello().isWritablePrimary)') == 'true':
                break
            time.sleep(1)
        else:
            raise RuntimeError('owned_mongo_primary_budget_exceeded')
        self.report['dependency_image_ids']['mongo'] = self.run(['docker', 'image', 'inspect', MONGO, '--format', '{{.Id}}']).stdout.strip()

    def prepare(self, database, profile):
        self.sql('CREATE DATABASE `' + database + '` CHARACTER SET utf8mb4;')
        environment = {key: os.environ[key] for key in ('GITHUB_ACTIONS', 'RUNNER_ENVIRONMENT', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')}
        environment.update(QS_IMAGE_DATABASE=database, QS_IMAGE_PROFILE=profile,
                           QS_IMAGE_MYSQL_DSN=f'root:{self.password}@tcp(mysql:3306)/{database}?parseTime=true',
                           QS_IMAGE_MONGO_URI='mongodb://mongo:27017/?replicaSet=image-proof')
        result = self.once('/fixture/qs-pair-init', ['-test.run=^TestM3ImagePreparePair$', '-test.v', '-test.timeout=6m'], environment=environment, timeout=375)
        return initializer_receipt(result, profile)

    def snapshot(self, database):
        sql = self.dump(database)
        mongo = self.mongo(mongo_snapshot_program(database))
        return sql, hashlib.sha256(mongo.encode()).hexdigest()

    def restore_roundtrip(self, database):
        # Explicit fixture tables/collections are controlled retained facts, not
        # business acceptance, legacy message drain or transaction witnesses.
        self.sql(f'CREATE TABLE `{database}`.fixture_retained_state (id BIGINT PRIMARY KEY,body LONGBLOB NOT NULL); INSERT INTO `{database}`.fixture_retained_state VALUES(1,0x00ff03);')
        self.mongo('db.getSiblingDB(' + json.dumps(database) + ").fixture_retained_state.insertOne({_id:1,body:BinData(0,'AP8D'),attempt:7})")
        sql, original_mongo = self.snapshot(database)
        def columns():
            return self.sql("SELECT table_name,ordinal_position,column_name,column_type,is_nullable,IF(column_default IS NULL,'NULL',CONCAT('HEX:',HEX(column_default))),extra,character_set_name,collation_name,HEX(column_comment),generation_expression FROM information_schema.columns WHERE table_schema='" + database + "' ORDER BY table_name,ordinal_position;")
        original_columns = columns()
        def mongo_parts():
            value = json.loads(self.mongo(mongo_snapshot_program(database)))
            return {hashlib.sha256(c['name'].encode()).hexdigest(): {
                key: hashlib.sha256(json.dumps(c.get(key), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                for key in ('type', 'options', 'uuid', 'indexes', 'documents')} for c in value}
        before_parts = mongo_parts()
        backup = self.directory / (database + '.sql'); backup.write_text(sql); backup.chmod(0o600)
        archive = '/tmp/' + database + '.archive.gz'
        self.run(['docker', 'exec', self.mongo_name, 'mongodump', '--quiet', '--db', database, '--archive=' + archive, '--gzip'], timeout=120)
        protected = self.directory / (database + '.archive.gz')
        self.run(['docker', 'cp', self.mongo_name + ':' + archive, str(protected)]); protected.chmod(0o600)
        protection = dict(mysql_sha256=hashlib.sha256(sql.encode()).hexdigest(),
                          mongo_archive_sha256=hashlib.sha256(protected.read_bytes()).hexdigest(),
                          mongo_snapshot_sha256=original_mongo)
        # Add objects absent from the original protection: --drop alone is not
        # enough to remove these. Restore the entire owned pair, preserving UUID.
        self.sql(f'CREATE TABLE `{database}`.fixture_after_protection (id INT); UPDATE `{database}`.fixture_retained_state SET body=0x04;')
        self.mongo('const d=db.getSiblingDB(' + json.dumps(database) + ');d.fixture_after_protection.insertOne({_id:1});d.fixture_retained_state.updateOne({_id:1},{$set:{attempt:99}})')
        require(self.snapshot(database) != (sql, original_mongo), 'controlled_pair_mutation_required')
        self.sql('DROP DATABASE `' + database + '`; CREATE DATABASE `' + database + '` CHARACTER SET utf8mb4;')
        self.sql('SET FOREIGN_KEY_CHECKS=0; USE `' + database + '`;\n' + sql + '\nSET FOREIGN_KEY_CHECKS=1;')
        self.mongo('db.getSiblingDB(' + json.dumps(database) + ').dropDatabase()')
        self.run(['docker', 'exec', self.mongo_name, 'mongorestore', '--quiet', '--archive=' + archive, '--gzip', '--drop', '--preserveUUID', '--nsInclude=' + database + '.*'], timeout=120)
        after_sql, after_mongo = self.snapshot(database)
        after_columns = columns()
        after_parts = mongo_parts()
        self.report.setdefault('restore_readbacks', {})[database] = dict(
            mysql_before_sha256=hashlib.sha256(sql.encode()).hexdigest(),
            mysql_after_sha256=hashlib.sha256(after_sql.encode()).hexdigest(),
            mysql_difference=dump_difference(sql,after_sql),
            mysql_original_protection_unmodified=True,
            mysql_canonical_before_sha256=hashlib.sha256(canonical_dump(sql).encode()).hexdigest(),
            mysql_canonical_after_sha256=hashlib.sha256(canonical_dump(after_sql).encode()).hexdigest(),
            mysql_column_metadata_before_sha256=hashlib.sha256(original_columns.encode()).hexdigest(),
            mysql_column_metadata_after_sha256=hashlib.sha256(after_columns.encode()).hexdigest(),
            mongo_before_sha256=original_mongo, mongo_after_sha256=after_mongo,
            mongo_before_parts=before_parts, mongo_after_parts=after_parts)
        require(canonical_dump(after_sql) == canonical_dump(sql) and original_columns == after_columns
                and after_mongo == original_mongo, 'full_pair_restore_must_match_original_schema_data_and_uuid')
        return protection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('source', 'candidate', 'initializer', 'report'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args(); require(not args.report.exists(), 'new_report_required')
    repo = Path(__file__).resolve().parents[2]
    report = dict(schema='m3-qs-image-pair-preparation/v1', qs_sha=QS_SHA, passed=0, failed=0, skipped=0,
                  production=False, system_acceptance=False, application_started=False,
                  combined_cutover_rehearsal_complete=False, cases={})
    fixture = QSPairFixture(repo, report); run = fixture.run; source = args.source.resolve()
    def case(name): report['cases'][name] = True
    try:
        report['infra_sha'] = run(['git', 'rev-parse', 'HEAD'], cwd=repo).stdout.strip()
        require(run(['git', 'rev-parse', 'HEAD'], cwd=source).stdout.strip() == QS_SHA
                and not run(['git', 'status', '--porcelain'], cwd=source).stdout, 'fixed_clean_qs_source_required')
        candidates = {}
        for target in ('qs-collection', 'qs-worker', 'qs-api'):
            value = fixture.load(args.candidate / target, target, QS_SHA)
            require(value['runtime_sdk'] == dict(version='v0.5.0', sum=GO_SUM, replace=False)
                    and value['verified_uid_gid'] == [2000, 2000], 'actual_formal_qs_image_required')
            candidates[target] = report['candidate']
            case('exact_' + target.replace('-', '_') + '_archive_loaded')
        report['candidates'] = candidates; report.pop('candidate')
        tool = args.candidate / 'qs-api/qs-migrate-offline'
        require(hashlib.sha256(tool.read_bytes()).hexdigest() == value['offline_tool_sha256'], 'same_source_offline_companion_required')
        shutil.copyfile(tool, fixture.private / 'qs-migrate-offline'); (fixture.private / 'qs-migrate-offline').chmod(0o755)
        shutil.copyfile(args.initializer, fixture.private / 'qs-pair-init'); (fixture.private / 'qs-pair-init').chmod(0o755)
        report['initializer_sha256'] = hashlib.sha256(args.initializer.read_bytes()).hexdigest()
        report['original_offline_tool_sha256'] = value['offline_tool_sha256']
        fixture.dependencies(); fixture.mongo_dependencies(); fixture.ownership(2000)
        for profile in ('pre_m3', 'current'):
            fixture.stage = 'original_pair_' + profile
            database = 'qs_m3_image_' + profile + '_' + secrets.token_hex(6)
            receipt = fixture.prepare(database, profile)
            report[profile + '_schema'] = receipt
            case('original_migration_pair_' + profile)
            fixture.stage = 'actual_full_pair_restore_' + profile
            report[profile + '_protection'] = fixture.restore_roundtrip(database)
            case('full_mysql_mongo_restore_with_uuid_' + profile)
            if profile == 'current':
                fixture.stage = 'original_dual_owner_binding'
                env = dict(QS_OFFLINE_MYSQL_DSN=f'root:{fixture.password}@tcp(mysql:3306)/{database}?parseTime=true',
                           QS_OFFLINE_MONGO_URI='mongodb://mongo:27017/?replicaSet=image-proof')
                common = ['--mysql-database', database, '--mongo-database', database, '--timeout', '30s']
                snapshot = json.loads(fixture.once('/fixture/qs-migrate-offline', common, environment=env))
                observed = snapshot['snapshot']
                require(snapshot['read_only'] and observed['source_sha'] == QS_SHA
                        and observed['migration_resources_sha256'] == receipt['resources_sha256']
                        and (observed['mysql_version'], observed['mongo_version']) == (110, 43), 'original_pair_readback_required')
                for owner in ('qs.mysql', 'qs.mongo'):
                    plan = '/fixture/' + owner + '-binding.json'
                    fixture.once('/fixture/qs-migrate-offline', common + ['--binding-action', 'preview', '--binding-plan', plan,
                                 '--binding-operation-id', 'owned-qs-image', '--binding-owner', owner,
                                 '--binding-store-id', 'isolated-' + owner.replace('.', '-') + '-primary', '--binding-writer-epoch', 'm3-1'], environment=env)
                    digest = fixture.once('/usr/bin/sha256sum', [plan], network=False).split()[0]
                    require(re.fullmatch('[0-9a-f]{64}', digest), 'exact_binding_plan_digest_required')
                    for action in ('apply', 'verify'):
                        command = common + ['--binding-action', action, '--binding-plan', plan, '--binding-reviewed-sha256', digest]
                        if action == 'apply': command += ['--binding-writers-excluded']
                        result = json.loads(fixture.once('/fixture/qs-migrate-offline', command, environment=env))
                        if action == 'verify': require(result['verified'] is True and result['cutover_authorized'] is False, 'binding_readback_required')
                    case('original_binding_' + owner.replace('.', '_'))
    except Exception as error:
        report.update(failed=1, failure_stage=fixture.stage, failure_kind=type(error).__name__)
        if re.fullmatch(r'[a-z][a-z0-9_]{1,100}', str(error)):
            report['failure_reason'] = str(error)
    finally:
        report['passed'] = len(report['cases'])
        try: fixture.cleanup()
        except Exception: report['failed'] = 1; report.setdefault('failure_stage', 'owned_cleanup')
        report['source_unchanged'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout
        if not report['source_unchanged']: report['failed'] = 1
        write_private(args.report, report)
    return int(report['failed'] != 0)


if __name__ == '__main__': raise SystemExit(main())
