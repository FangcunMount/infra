"""Full-scope restore training on owned CI facts, before any business runtime.

No production names/credentials accepted. Raw protection remains private and is
cleaned with the fixture; this does not attest production retention or approval.
"""
import hashlib
import json
import math
import os
import re
import time

from audit_transaction_limit import write_private
from final_image_candidate import ci_guard
from image_start_fixture import require
from qs_image_pair import canonical_dump, dump_difference, mongo_snapshot_program
from start_boundary import _encoded


def validate_databases(databases):
    require(isinstance(databases, dict) and set(databases) == {'iam', 'qs', 'ai'}, 'exact_owned_database_set_required')
    for store, name in databases.items():
        require(isinstance(name, str) and re.fullmatch(store + '_m3_image_[a-z0-9_]{1,36}', name), 'owned_database_name_required')
    return dict(databases)


class FullImageProtection:
    def __init__(self, fixture, databases):
        ci_guard(os.environ)
        self.f = fixture; self.databases = validate_databases(databases)
        require(not fixture.applications, 'no_runtime_before_restore_training_required')
        self.sql = {}; self.columns = {}; self.definitions = {}; self.provider = fixture.sql('SELECT @@server_uuid;')
        require(bool(re.fullmatch('[a-z0-9-]{36}', self.provider)), 'actual_owned_mysql_identity_required')

    def dump(self, database):
        return self.f.run(self.f.compose + ['exec', '-T', 'mysql', 'sh', '-c',
            'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction --routines --events --triggers --order-by-primary --hex-blob --compact --skip-comments --skip-dump-date --no-tablespaces --set-gtid-purged=OFF --skip-lock-tables --column-statistics=0 --default-character-set=utf8mb4 --set-charset "$@"',
            'owned-full-protection', database]).stdout

    def restore_mysql(self, store):
        # --compact disables SET NAMES unless explicitly re-enabled above.
        # Pin the restore session too: client defaults must not reinterpret
        # retained Unicode facts or generated-expression string literals.
        database = self.databases[store]
        observed = self.f.sql('SET NAMES utf8mb4; SELECT @@character_set_client,@@character_set_connection,@@character_set_results;\n'
            + 'DROP DATABASE `' + database + '`; ' + self.definitions[store] + ';\n'
            + 'SET FOREIGN_KEY_CHECKS=0; USE `' + database + '`;\n' + self.sql[store] + '\nSET FOREIGN_KEY_CHECKS=1;')
        require(observed == 'utf8mb4\tutf8mb4\tutf8mb4', 'exact_restore_session_charset_required')

    def column_metadata(self, database):
        return self.f.sql("SELECT table_name,ordinal_position,column_name,column_type,is_nullable,IF(column_default IS NULL,'NULL',CONCAT('HEX:',HEX(column_default))),extra,character_set_name,collation_name,HEX(column_comment),generation_expression FROM information_schema.columns WHERE table_schema='" + database + "' ORDER BY table_name,ordinal_position;")

    def mysql_snapshot(self, database):
        return dict(canonical_dump_sha256=hashlib.sha256(canonical_dump(self.dump(database)).encode()).hexdigest(),
            columns_sha256=hashlib.sha256(self.column_metadata(database).encode()).hexdigest(),
            database_definition_sha256=hashlib.sha256(self.f.sql('SHOW CREATE DATABASE `' + database + '`;').encode()).hexdigest())

    def mongo_snapshot(self):
        raw = self.f.mongo(mongo_snapshot_program(self.databases['qs']))
        return dict(snapshot_sha256=hashlib.sha256(raw.encode()).hexdigest(), collections=len(json.loads(raw)))

    def train(self):
        f = self.f; qs = self.databases['qs']; ai = self.databases['ai']; iam = self.databases['iam']
        require(not f.applications and f.sql('SELECT @@server_uuid;') == self.provider, 'original_selected_provider_and_no_runtime_required')
        default_charset = f.sql('SELECT @@character_set_client,@@character_set_connection,@@character_set_results;')
        require(bool(re.fullmatch('[a-z0-9_]+\t[a-z0-9_]+\t[a-z0-9_]+', default_charset)), 'fixed_mysql_charset_readback_required')
        f.report['mysql_client_default_charsets'] = default_charset.split('\t')
        f.sql(f'CREATE TABLE `{qs}`.fixture_retained_state(id BIGINT PRIMARY KEY,body LONGBLOB NOT NULL); INSERT INTO `{qs}`.fixture_retained_state VALUES(1,0x00ff03);')
        f.mongo('db.getSiblingDB(' + json.dumps(qs) + ").fixture_retained_state.insertOne({_id:1,body:BinData(0,'AP8D'),attempt:7})")
        require(int(f.sql(f'SELECT COUNT(*) FROM `{iam}`.fixture_bootstrap_event_archive;')) > 0, 'controlled_iam_seed_fact_required')
        require(f.sql(f"SELECT COUNT(*) FROM `{ai}`.messaging_outbox WHERE message_id='fixture-held' AND stage='held';") == '1', 'controlled_ai_held_fact_required')
        before = {}
        manifest = dict(schema='m3-owned-full-image-protection/v1', mysql={}, production=False,
            scope='three full MySQL databases and the complete selected QS Mongo database, including controlled retained facts')
        for store, database in self.databases.items():
            self.sql[store] = self.dump(database); self.columns[store] = self.column_metadata(database)
            definition = f.sql('SHOW CREATE DATABASE `' + database + '`;').split('\t', 1)
            require(len(definition) == 2 and definition[0] == database and definition[1].startswith('CREATE DATABASE '), 'original_database_definition_required')
            self.definitions[store] = definition[1]
            path = f.directory / (store + '-full-protection.sql'); path.write_text(self.sql[store]); path.chmod(0o600)
            before[store] = self.mysql_snapshot(database)
            manifest['mysql'][store] = dict(database=database, original_dump_sha256=hashlib.sha256(self.sql[store].encode()).hexdigest(),
                selected_identity_sha256=hashlib.sha256(_encoded(dict(identity_scheme='owned-mysql-selected-database-v1',server_uuid=self.provider,database=database))).hexdigest(),
                snapshot=before[store])
        before['mongo'] = self.mongo_snapshot()
        self.mongo_archive = '/tmp/' + qs + '-full-protection.gz'
        f.run(['docker', 'exec', f.mongo_name, 'mongodump', '--quiet', '--db', qs, '--archive=' + self.mongo_archive, '--gzip'], timeout=120)
        archive = f.directory / 'qs-full-mongo.archive.gz'; f.run(['docker', 'cp', f.mongo_name + ':' + self.mongo_archive, str(archive)]); archive.chmod(0o600)
        manifest['mongo'] = dict(database=qs, archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), snapshot=before['mongo'])
        write_private(f.directory / 'full-protection-manifest.json', manifest)
        self.manifest_sha = hashlib.sha256((f.directory / 'full-protection-manifest.json').read_bytes()).hexdigest()
        # Deliberately create objects absent from the protection, then restore
        # entire selected databases, never only the three known marker rows.
        for database in self.databases.values(): f.sql('CREATE TABLE `' + database + '`.fixture_after_protection(id INT PRIMARY KEY);')
        f.mongo('db.getSiblingDB(' + json.dumps(qs) + ').fixture_after_protection.insertOne({_id:1})')
        for store, database in self.databases.items(): require(self.mysql_snapshot(database) != before[store], 'actual_mysql_protection_mutation_required')
        require(self.mongo_snapshot() != before['mongo'], 'actual_mongo_protection_mutation_required')
        started = time.monotonic()
        for store, database in self.databases.items():
            self.restore_mysql(store)
        f.report['mysql_restore_session_charsets'] = ['utf8mb4'] * 3
        f.mongo('db.getSiblingDB(' + json.dumps(qs) + ').dropDatabase()')
        f.run(['docker', 'exec', f.mongo_name, 'mongorestore', '--quiet', '--archive=' + self.mongo_archive,
            '--gzip', '--drop', '--preserveUUID', '--nsInclude=' + qs + '.*'], timeout=120)
        after = {store: self.mysql_snapshot(database) for store, database in self.databases.items()}
        after['mongo'] = self.mongo_snapshot()
        provider_unchanged = f.sql('SELECT @@server_uuid;') == self.provider
        if before != after or not provider_unchanged or f.applications:
            # Retain exact readback hashes on failure as well. Never export
            # SQL, retained facts, column comments or private protection bytes.
            f.report['full_restore_difference'] = dict(before=before, after=after,
                provider_unchanged=provider_unchanged, runtime_started=bool(f.applications), mysql={})
            for store, database in self.databases.items():
                if before[store] != after[store]:
                    current = self.dump(database)
                    f.report['full_restore_difference']['mysql'][store] = dict(
                        raw_dump=dump_difference(self.sql[store], current),
                        canonical_dump=dump_difference(canonical_dump(self.sql[store]), canonical_dump(current)),
                        column_metadata=dump_difference(self.columns[store], self.column_metadata(database)))
        require(before == after and provider_unchanged and not f.applications, 'actual_full_scope_restore_readback_differs')
        self.restore_seconds = max(1, math.ceil(time.monotonic() - started))
        receipt = dict(schema='m3-owned-full-image-restore/v1', protection_manifest_sha256=self.manifest_sha,
            snapshots_before=before, snapshots_after=after, restore_duration_seconds=self.restore_seconds,
            original_protection_bytes_unmodified=True, mongo_uuid_preserved=True, runtime_started=False,
            production=False, production_backup_retention_verified=False,
            scope='pre-window controlled restore training; not a production restore or business acceptance')
        path = f.directory / 'full-restore-receipt.json'; write_private(path, receipt)
        self.receipt_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        f.report['full_scope_restore'] = receipt
        return manifest, receipt
