#!/usr/bin/env python3
"""Owned hosted-CI proof; no production endpoints or production data accepted."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

from m3_mongo_protection import drop_program, profile_identity_program, restore_selection, snapshot_program

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'rocketmq'))
from final_image_candidate import ci_guard


IMAGE = 'mongo@sha256:43fddee7e532a920f3dfdee9e8f4834398c155c26bcb92d790cc1cd3c630fc40'


def run(args, *, data=None, timeout=90, required=True):
    p = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    if required and p.returncode:
        raise RuntimeError('owned_command_failed:' + args[0])
    return p


def execute(output):
    ci_guard(os.environ)
    os.umask(0o077)
    before_containers = run(['docker', 'ps', '-aq']).stdout.split()
    before_networks = run(['docker', 'network', 'ls', '-q']).stdout.split()
    suffix = uuid.uuid4().hex[:12]
    name = 'm3-profile-' + suffix
    network = name + '-network'
    database = 'qs_m3_profile_test_' + suffix
    label = 'com.fangcunmount.m3.profile-proof'
    report = {'schema': 'm3-mongo-profile-preserved-restore/v1', 'passed': 0, 'failed': 0,
              'skipped': 0, 'production': False, 'system_acceptance': False,
              'production_profile_setting_changed': False, 'cases': {}, 'image': IMAGE}
    report['infra_sha'] = run(['git', 'rev-parse', 'HEAD']).stdout.decode().strip()
    report['source_sha256'] = {Path(__file__).name: hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                              'm3_mongo_protection.py': hashlib.sha256(Path(__file__).with_name('m3_mongo_protection.py').read_bytes()).hexdigest()}
    made_network = False

    def case(key):
        report['cases'][key] = True
        report['passed'] += 1

    def js(program):
        return run(['docker', 'exec', '-i', name, 'mongosh', '--quiet', '--file', '/dev/stdin'],
                   data=program.encode(), timeout=50).stdout.decode().strip()

    def json_js(program):
        return json.loads(js(program))

    def selected(program):
        return 'const d=db.getSiblingDB(' + json.dumps(database) + ');' + program

    def inventories():
        return json_js(selected('print(JSON.stringify(d.getCollectionNames()));'))

    def checksum(raw):
        return hashlib.sha256(raw.encode()).hexdigest()

    with tempfile.TemporaryDirectory(prefix='owned-m3-profile-') as private:
        private = Path(private)
        try:
            run(['docker', 'pull', '--platform', 'linux/amd64', IMAGE], timeout=240)
            run(['docker', 'network', 'create', '--label', label + '=' + suffix, network])
            made_network = True
            run(['docker', 'run', '--detach', '--pull', 'never', '--name', name,
                 '--label', label + '=' + suffix, '--network', network,
                 '--memory', '768m', '--cpus', '1', '--pids-limit', '128',
                 '--tmpfs', '/data/db:rw,size=536870912', '--tmpfs', '/data/configdb:rw,size=67108864',
                 IMAGE, 'mongod', '--replSet', 'm3-profile-proof', '--bind_ip_all',
                 '--oplogSize', '32', '--wiredTigerCacheSizeGB', '0.25'])
            end = time.monotonic() + 75
            while True:
                p = run(['docker', 'exec', name, 'mongosh', '--quiet', '--eval', 'db.adminCommand({ping:1})'],
                        timeout=15, required=False)
                if not p.returncode:
                    break
                if time.monotonic() >= end:
                    raise RuntimeError('owned_mongo_readiness_unavailable')
                time.sleep(1)
            js("rs.initiate({_id:'m3-profile-proof',members:[{_id:0,host:'127.0.0.1:27017'}]});")
            end = time.monotonic() + 45
            while json_js('print(JSON.stringify(db.hello().isWritablePrimary));') is not True:
                if time.monotonic() >= end:
                    raise RuntimeError('owned_replica_primary_unavailable')
                time.sleep(1)
            version = json_js('print(JSON.stringify(db.version()));')
            tools = run(['docker', 'exec', name, 'mongodump', '--version']).stdout.decode().splitlines()[0]
            if version != '7.0.31' or tools != 'mongodump version: 100.16.0':
                raise RuntimeError('actual_fixed_mongo_tools_version_differs')
            report.update(mongo_version=version, tools_version=tools, replica_set='m3-profile-proof')
            case('fixed_actual_version_and_owned_replica_primary')

            js(selected("d.facts.insertMany([{_id:1,body:BinData(0,'AP8D'),state:'committed'},{_id:2,body:'保留业务事实'}]);"
                        "d.facts.createIndex({state:1,_id:-1},{name:'ordered_business_index'});"
                        "d.profile_records.insertOne({_id:1,body:'ordinary business collection'});"
                        "d.schema_migrations.insertOne({_id:1,version:40,dirty:false});"
                        "d.createCollection('system.profile',{capped:true,size:8388608});"
                        "d.setProfilingLevel(2,{slowms:0,sampleRate:1});"
                        "d.facts.find({profile_marker:'before-original-backup'}).toArray();"))
            before = js(snapshot_program(database))
            original_names = inventories()
            original_profile = js(profile_identity_program(database))
            profile_rows_before = json_js(selected("print(JSON.stringify(d.getCollection('system.profile').countDocuments({})));"))
            if profile_rows_before <= 0:
                raise RuntimeError('actual_profile_documents_required')
            case('active_profiler_nonempty_and_all_business_types_frozen')

            archive = '/tmp/m3-profile-whole-database.gz'
            run(['docker', 'exec', name, 'mongodump', '--quiet', '--db', database,
                 '--archive=' + archive, '--gzip'])
            # Profiling continues, while business data stays exactly unchanged.
            for _ in range(8):
                js(selected("d.facts.find({profile_marker:'after-original-backup'}).toArray();"))
            if js(snapshot_program(database)) != before or js(profile_identity_program(database)) != original_profile:
                raise RuntimeError('business_or_diagnostic_identity_drifted_during_dump')
            case('whole_database_archive_with_continuing_diagnostic_writes')

            js(selected("d.unreviewed_after_freeze.insertOne({_id:1});"))
            try:
                restore_selection(original_names, inventories(), ['new_sdk_ledger'])
            except ValueError:
                pass
            else:
                raise RuntimeError('unknown_object_not_rejected')
            js(selected('d.unreviewed_after_freeze.drop();'))
            if js(snapshot_program(database)) != before:
                raise RuntimeError('rejected_plan_changed_original_business')
            case('unknown_object_refused_before_any_business_drop')

            js(selected("d.facts.updateOne({_id:1},{$set:{state:'controlled-offline-change'}});"
                        "d.new_sdk_ledger.insertOne({_id:1,state:'controlled-only'});"))
            if js(snapshot_program(database)) == before:
                raise RuntimeError('real_owned_restore_mutation_required')
            plan = restore_selection(original_names, inventories(), ['new_sdk_ledger'])
            if 'system.profile' in plan:
                raise RuntimeError('diagnostic_namespace_selected_for_drop')
            js(drop_program(database, plan))
            run(['docker', 'exec', name, 'mongorestore', '--quiet', '--archive=' + archive,
                 '--gzip', '--drop', '--preserveUUID', '--nsInclude=' + database + '.*',
                 '--nsExclude=' + database + '.system.profile'])
            after = js(snapshot_program(database))
            if before != after:
                raise RuntimeError('actual_business_documents_indexes_options_or_uuid_differ')
            case('all_business_documents_indexes_options_and_uuid_exact_after_restore')

            after_profile = js(profile_identity_program(database))
            markers = json_js(selected("print(JSON.stringify({before:d.getCollection('system.profile').countDocuments({'command.filter.profile_marker':'before-original-backup'}),after:d.getCollection('system.profile').countDocuments({'command.filter.profile_marker':'after-original-backup'})}));"))
            if after_profile != original_profile or not all(markers[x] > 0 for x in ['before', 'after']):
                raise RuntimeError('original_and_postbackup_diagnostics_not_preserved_in_place')
            if inventories() != original_names and sorted(inventories()) != sorted(original_names):
                raise RuntimeError('new_migration_collection_not_removed')
            case('profiler_settings_uuid_indexes_and_both_generations_preserved')
            report.update(business_snapshot_before_sha256=checksum(before), business_snapshot_after_sha256=checksum(after),
                          profile_identity_before_sha256=checksum(original_profile), profile_identity_after_sha256=checksum(after_profile),
                          profile_documents_before=profile_rows_before, diagnostic_markers_retained=markers,
                          new_migration_object_removed=True, raw_business_or_profile_documents_exported=False,
                          selected_database_dropped=False, live_profile_writes_stopped=False)
        except Exception as error:
            report['failed'] += 1
            report['failure_kind'] = type(error).__name__
            report['failure_reason'] = str(error) if isinstance(error, RuntimeError) else 'owned_fixture_failure'
        finally:
            p = run(['docker', 'inspect', '--format', '{{index .Config.Labels "' + label + '"}}', name], required=False)
            if not p.returncode:
                if p.stdout.decode().strip() != suffix:
                    raise RuntimeError('cleanup_ownership_differs')
                run(['docker', 'rm', '--force', name])
            if made_network:
                run(['docker', 'network', 'rm', network])
            report['cleanup'] = {
                'existing_containers_unchanged': before_containers == run(['docker', 'ps', '-aq']).stdout.split(),
                'existing_networks_unchanged': before_networks == run(['docker', 'network', 'ls', '-q']).stdout.split(),
                'owned_container_and_network_removed': True,
                'raw_profile_and_business_archive_removed': True,
            }
            if not all(report['cleanup'].values()):
                report['failed'] += 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    output.chmod(0o600)
    print(json.dumps({k: report[k] for k in ['schema', 'passed', 'failed', 'skipped', 'production']}))
    return 0 if report['passed'] == 6 and report['failed'] == report['skipped'] == 0 else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(execute(args.output))
