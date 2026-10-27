"""Actual IAM host acceptance, only inside ci-transactions' owned fixture."""
import hashlib
import json
import os
import re
import secrets
from pathlib import Path

from provision_v2 import provision
from routes import consumer_group_v2, physical_topic_v2, consumer_group_v3, physical_topic_v3, validate


def iam_manifest(fanout=False, *, readable=False):
    topic, subscription = 'iam.authz.version.v2', 'iam-m3-native-observer'
    route = {'id': 'iam-native', 'topic': topic, 'subscription': subscription,
             'message_type': 'TRANSACTION', 'owner': 'iam.mysql', 'route_revision': 'm3-1',
             'physical_topic': physical_topic_v2(topic, 'TRANSACTION', 'iam.mysql', 'm3-1'),
             'consumer_group': consumer_group_v2(topic, subscription)}
    result = {'version': 2, 'routes': [route],
              'topic_options': {'read_queue_nums': 1, 'write_queue_nums': 1, 'perm': 6},
              'group_options': {'retry_queue_nums': 8},
              'accounts': {'iam-producer': {'owner': 'iam.mysql', 'publish': ['iam-native'], 'subscriptions': []},
                           'iam-observer': {'publish': [], 'subscriptions': ['iam-native']}}}
    if fanout:
        for role, subscription in (('iam-fanout-a', 'iam-m3-native-fanout-a'),
                                   ('iam-fanout-b', 'iam-m3-native-fanout-b'),
                                   ('qs-fanout', 'qs-m3-native-fanout')):
            identifier = role + '-native'
            result['routes'].append(dict(route, id=identifier, subscription=subscription,
                                         consumer_group=consumer_group_v2(topic, subscription)))
            result['accounts'][role] = {'publish': [], 'subscriptions': [identifier]}
    if readable:
        result['version'] = 3
        for row in result['routes']:
            row['naming_scheme'] = 'readable-v1'
            row['physical_topic'] = physical_topic_v3(row['topic'], row['message_type'], row['owner'], row['route_revision'])
            row['consumer_group'] = consumer_group_v3(row['topic'], row['subscription'])
    validate(result)
    return result


def parse_host_receipt(output, require_business_result=False):
    receipts = [json.loads(line.split('M3_HOST_RECEIPT ', 1)[1])
                for line in output.splitlines() if 'M3_HOST_RECEIPT {' in line]
    if (len(receipts) != 1 or receipts[0].get('passed') != 4 or receipts[0].get('failed') != 0
            or receipts[0].get('skipped') != 0
            or any(receipts[0].get(name) is not True for name in
                   ('half_invisible', 'commit_wire_and_witness', 'application_entry', 'rollback_hidden'))
            or not re.search(r'--- PASS: TestM3ActualBrokerHost \(', output)
            or re.search(r'--- (?:SKIP|FAIL):', output)):
        raise RuntimeError('IAM native receipt is absent, failed, skipped or incomplete')
    if require_business_result and receipts[0].get('business_result_atomic') is not True:
        raise RuntimeError('original business operation result proof absent')
    return receipts[0]


RUNTIME_CASES = frozenset(('actual_owner_start', 'inflight_root_shutdown_incomplete_retains_pool',
    'late_commit_once_with_witness', 'new_owner_fresh_exact_checker',
    'paused_owner_keeps_checker_and_seals_writes', 'actual_stop_retains_host_pool'))


def parse_runtime_receipt(output, source):
    receipts = [json.loads(line.split('M3_IAM_RUNTIME_RECEIPT ', 1)[1])
                for line in output.splitlines() if 'M3_IAM_RUNTIME_RECEIPT {' in line]
    if len(receipts) != 1:
        raise RuntimeError('one exact IAM owner runtime receipt required')
    value = receipts[0]
    if (not re.fullmatch('[0-9a-f]{40}', source) or value.get('source_sha') != source
            or value.get('scope') != 'actual IAM owner lifecycle and original root; in-process only'
            or value.get('passed') != len(RUNTIME_CASES) or value.get('failed') != 0 or value.get('skipped') != 0
            or set(value.get('cases', {})) != RUNTIME_CASES
            or any(v is not True for v in value['cases'].values())
            or value.get('business_executions') != 1
            or value.get('full_api_process_fault_or_system_not_claimed') is not True
            or not re.search(r'--- PASS: TestM3ActualOwnerDrain \(', output)
            or re.search(r'--- (?:SKIP|FAIL):|WARNING: DATA RACE', output)):
        raise RuntimeError('IAM runtime receipt wrong source, incomplete, failed, skipped or outside exact scope')
    return value


PROTECTION_CASES = frozenset((
    'actual_primary_binding_conflict_latches_current_observation',
    'protected_writer_never_reaches_original_root', 'idle_checker_owner_stays_live',
    'unhealthy_review_and_plain_open_refused', 'healthy_sampling_does_not_unlatch',
    'exact_generation_named_review_restores_admission', 'committed_replay_keeps_one_business_execution',
    'actual_sampler_shutdown_retains_primary_pool'))


def parse_protection_receipt(output, source):
    parse_runtime_receipt(output, source)
    rows = [json.loads(line.split('M3_IAM_PROTOCOL_PROTECTION_RECEIPT ', 1)[1])
            for line in output.splitlines() if 'M3_IAM_PROTOCOL_PROTECTION_RECEIPT {' in line]
    if len(rows) != 1:
        raise RuntimeError('one exact IAM protection receipt required')
    value = rows[0]
    fields = {'source_sha', 'passed', 'failed', 'skipped', 'cases', 'business_executions',
              'binding_fixture_only', 'full_api_process_fault_or_system_not_claimed'}
    if (set(value) != fields or value['source_sha'] != source
            or type(value['passed']) is not int or value['passed'] != len(PROTECTION_CASES)
            or type(value['failed']) is not int or value['failed'] != 0
            or type(value['skipped']) is not int or value['skipped'] != 0
            or set(value['cases']) != PROTECTION_CASES or any(v is not True for v in value['cases'].values())
            or type(value['business_executions']) is not int or value['business_executions'] != 1
            or value['binding_fixture_only'] is not True
            or value['full_api_process_fault_or_system_not_claimed'] is not True):
        raise RuntimeError('IAM protection receipt wrong source, incomplete or outside fixed scope')
    return value


NATIVE_LIMIT_CASES = frozenset((
    'actual_sys_index_idempotent_original_primary_governance',
    'live_sampler_blocks_actual_writer_plain_open_and_review',
    'idle_sdk_checker_readiness_kept_with_original_pool',
    'new_configured_open_owner_keeps_durable_native_protection',
    'original_committed_witness_and_one_business_execution_preserved',
    'no_native_governance_resolution_or_deletion',
    'actual_sampler_shutdown_retains_primary_pool'))


def parse_native_limit_receipt(output, source):
    parse_runtime_receipt(output, source)
    rows = [json.loads(line.split('M3_IAM_NATIVE_LIMIT_RECEIPT ', 1)[1])
            for line in output.splitlines() if 'M3_IAM_NATIVE_LIMIT_RECEIPT {' in line]
    flags = {'real_sys_index_required', 'idle_checker_readiness_not_new_broker_callback',
             'governance_resolution_not_claimed', 'full_api_process_fault_or_system_not_claimed'}
    fields = flags | {'source_sha', 'passed', 'failed', 'skipped', 'cases', 'business_executions'}
    if len(rows) != 1:
        raise RuntimeError('one exact IAM native limit receipt required')
    value = rows[0]
    if (set(value) != fields or value['source_sha'] != source
            or any(type(value[k]) is not int for k in ('passed', 'failed', 'skipped', 'business_executions'))
            or (value['passed'], value['failed'], value['skipped'], value['business_executions']) != (7, 0, 0, 1)
            or not isinstance(value['cases'], dict) or set(value['cases']) != NATIVE_LIMIT_CASES
            or any(v is not True for v in value['cases'].values())
            or any(value[k] is not True for k in flags)):
        raise RuntimeError('IAM native limit receipt incomplete or wrong scope')
    return value


def validate_protection_profile(module, protection, runtime, faults, fanout):
    if protection and (not runtime or faults or fanout):
        raise RuntimeError('IAM protection requires separate actual runtime without faults/fanout')
    if protection and ('Replace' in module or module.get('Path') != 'github.com/FangcunMount/reliable-messaging'
            or tuple(module.get(k) for k in ('Version', 'Sum', 'GoModSum')) != (
                'v0.5.0', 'h1:JUayISCwmVwrLbHfLvgiOo3jr3Dxs7JfWeF3/Br45O0=',
                'h1:GPiWG8ZsX4pvIZ6QyvLnBVO5iCqNhvsnKwFcg0ftC7I=')):
        raise RuntimeError('IAM protection requires exact published stable v0.5.0 module and sums')

def host_failure_summary(raw):
    # Fixed classifications only; never copy a driver error, wire or credential.
    return {'build_failed': '[build failed]' in raw,
            'test_timeout': 'panic: test timed out' in raw,
            'race_reports': raw.count('WARNING: DATA RACE'),
            # Only file basenames/line numbers from race detector stack frames.
            # Never export function arguments, absolute paths or runtime values.
            'race_frames': sorted(set(re.findall(
                r'^\s+(?:[^\s\n]*/)?([A-Za-z0-9_.-]+\.go:\d+)(?: \+0x[0-9a-f]+)?\s*$',
                '\n'.join(re.findall(r'WARNING: DATA RACE\n(.*?)(?=\n={8,}|\Z)', raw, re.S)), re.M)))[:64],
            'failed_tests': sorted(set(re.findall(r'--- FAIL: (Test[A-Za-z0-9_/]+)', raw)))[:16],
            'assertion_lines': sorted(set(int(n) for n in re.findall(r'transaction_broker_host_integration_test\.go:(\d+)', raw)))[:32]}


def retain_private_host_output(path, raw):
    # Explicit local diagnostic destination, never a CI artifact. Refuse shared
    # directories, symlink/file replacement and existing output before writing.
    path = Path(path)
    parent = path.parent
    info = parent.stat()
    if parent.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise RuntimeError('private host output requires an owned0700 directory')
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        stream.write(raw)


def run_iam_host(source, directory, broker, project, grpc_port, mysql_port, password, ca, run, proof, private_log=None, require_business_result=False, qs_source=None, *, faults=False, native_runner=None, proxy_start=None, read_parameters=None, readable=False):
    source = source.resolve()
    if not (source / 'go.mod').is_file():
        raise RuntimeError('required exact IAM source checkout missing')
    tracked = run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if tracked:
        raise RuntimeError('IAM source checkout is dirty before acceptance')
    proof['source_sha'] = run(['git', 'rev-parse', 'HEAD'], cwd=source).stdout.strip()
    runtime_flag = os.environ.get('ROCKETMQ_IAM_RUNTIME_REQUIRED', '0')
    if runtime_flag not in ('0', '1'):
        raise RuntimeError('explicit IAM runtime profile flag required')
    runtime_required = runtime_flag == '1'
    protection_flag = os.environ.get('ROCKETMQ_IAM_PROTOCOL_PROTECTION', '0')
    if protection_flag not in ('0', '1'):
        raise RuntimeError('explicit IAM protection profile flag required')
    protection = protection_flag == '1'
    native_flag = os.environ.get('ROCKETMQ_IAM_NATIVE_LIMIT', '0')
    if native_flag not in ('0', '1') or (native_flag == '1' and protection):
        raise RuntimeError('explicit separate IAM native limit profile required')
    native_limit = native_flag == '1'

    env = dict(os.environ, GOWORK='off', GOFLAGS='-mod=readonly')
    module = json.loads(run(['go', 'list', '-m', '-json', 'github.com/FangcunMount/reliable-messaging'],
                            cwd=source, env=env).stdout)
    if module.get('Replace') or not module.get('Version') or not module.get('Sum'):
        raise RuntimeError('IAM must use its pinned downloaded SDK without replace')
    proof['sdk_module'] = {key: module.get(key) for key in ('Path', 'Version', 'Sum', 'GoModSum')}
    validate_protection_profile(module, protection or native_limit, runtime_required, faults, qs_source is not None)
    env['IAM_M3_VERIFY_PROTOCOL_PROTECTION'] = '1' if protection else '0'
    if (runtime_required or faults) and not (protection or native_limit) and module.get('Version') != 'v0.5.0':
        raise RuntimeError('current IAM runtime proof requires fixed stable SDK v0.5.0')
    if readable:
        if runtime_required or faults or protection or native_limit or qs_source is None:
            raise RuntimeError('readable IAM profile requires separate original-root/business fanout acceptance')
        if tuple(module.get(k) for k in ('Version','Sum','GoModSum')) != (
                'v0.6.0-rc.1','h1:kGWE8og29Er3UYYaNzPgaXj/T/2ltmQJrb+/iI4+nGo=',
                'h1:GPiWG8ZsX4pvIZ6QyvLnBVO5iCqNhvsnKwFcg0ftC7I='):
            raise RuntimeError('readable IAM profile requires exact published prerelease module and sums')
    manifest = iam_manifest(fanout=qs_source is not None, readable=readable)
    proof['manifest_version'] = manifest['version']
    proof['naming_scheme'] = 'readable-v1' if readable else 'hashed-v2'
    proof['manifest_sha256'] = hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    accounts = {role: {'username': 'm3-' + role + '-' + secrets.token_hex(4),
                       'password': secrets.token_hex(32)} for role in manifest['accounts']}
    proof['provision'] = provision(broker, manifest, accounts)
    env['IAM_M3_VERIFY_NATIVE_LIMIT'] = '1' if native_limit else '0'
    if native_limit:
        if read_parameters is None:
            raise RuntimeError('fixed original Broker parameter parser required')
        from native_limit_acceptance import create_native_limit
        proof['native_fault'] = {}
        route = next(r for r in manifest['routes'] if r['owner'] == 'iam.mysql' and r['message_type'] == 'TRANSACTION')
        audit, digest = create_native_limit(repo=Path(__file__).resolve().parents[2], directory=directory,
            broker=broker, project=project, grpc_port=grpc_port, ca=ca, account=accounts['iam-producer'],
            route=route, run=run, native_runner=native_runner, parameters=read_parameters,
            proof=proof['native_fault'], mysql_port=mysql_port, password=password)
        env.update(IAM_M3_NATIVE_LIMIT_AUDIT=str(audit), IAM_M3_NATIVE_LIMIT_SHA256=digest)

    routes = directory / 'iam-routes.json'
    routes.write_text(json.dumps(manifest)); routes.chmod(0o600)
    paths = {}
    for role in accounts:
        credentials = directory / (role + '-credentials.json')
        credentials.write_text(json.dumps(accounts[role])); credentials.chmod(0o600)
        config = {'provider': 'rocketmq', 'endpoint': f'127.0.0.1:{grpc_port}',
                  'credentials_file': str(credentials), 'ca_file': str(ca),
                  'routes_file': str(routes), 'instance_id': 'iam-native-fixture', 'publish_enabled': True}
        if role == 'iam-producer':
            config['transactions'] = {'iam.mysql': {'store_id': 'iam-native-primary',
                                                   'writer_epoch': 'm3-1', 'route_revision': 'm3-1'}}
        path = directory / (role + '-options.json')
        path.write_text(json.dumps(config)); path.chmod(0o600); paths[role] = path
    logs = directory / 'iam-private-client-logs'; logs.mkdir(mode=0o700)
    env.update({'IAM_M3_FIXTURE_PROJECT': project,
                'IAM_M3_TEST_MYSQL_DSN': f'root:{password}@tcp(127.0.0.1:{mysql_port})/mysql?parseTime=true&multiStatements=true',
                'IAM_M3_BROKER_CONFIG': str(paths['iam-producer']),
                'IAM_M3_OBSERVER_CONFIG': str(paths['iam-observer']),
                'rocketmq.client.logRoot': str(logs), 'rocketmq.client.logLevel': 'error'})
    if faults:
        if runtime_required or qs_source is not None:
            raise RuntimeError('original-root faults are a separate IAM profile')
        from iam_fault_acceptance import run_profile
        run_profile(source, directory, env, run, proof, native_runner, proxy_start)
        return
    if qs_source is not None:
        qs_source = qs_source.resolve()
        if not (qs_source / 'go.mod').is_file() or run(['git', 'status', '--porcelain'], cwd=qs_source).stdout.strip():
            raise RuntimeError('required clean QS fanout source checkout missing')
        qs_module = json.loads(run(['go', 'list', '-m', '-json', 'github.com/FangcunMount/reliable-messaging'],
                                   cwd=qs_source, env=env).stdout)
        if qs_module.get('Replace') or any(qs_module.get(k) != module.get(k) for k in ('Version', 'Sum', 'GoModSum')):
            raise RuntimeError('QS and IAM must use the same fixed published SDK')
        binary = directory / 'qs-fanout-test'
        run(['go', 'test', '-race', '-tags=integration,rocketmq_m3', '-c', '-o', str(binary),
             './internal/pkg/iamauth'], cwd=qs_source, env=env, timeout=240)
        proof['qs_fanout'] = {'source_sha': run(['git', 'rev-parse', 'HEAD'], cwd=qs_source).stdout.strip(),
                              'sdk_module': {key: qs_module.get(key) for key in ('Path', 'Version', 'Sum', 'GoModSum')}}
        env.update({'IAM_M3_FANOUT_REQUIRED': '1', 'IAM_M3_FANOUT_QS_BINARY': str(binary),
                    'IAM_M3_FANOUT_A_CONFIG': str(paths['iam-fanout-a']),
                    'IAM_M3_FANOUT_B_CONFIG': str(paths['iam-fanout-b']),
                    'IAM_M3_FANOUT_QS_CONFIG': str(paths['qs-fanout'])})
    tags = 'integration,m3_iam_runtime' if runtime_required else 'integration'
    selected = '^(TestM3ActualBrokerHost|TestM3ActualOwnerDrain)$' if runtime_required else '^TestM3ActualBrokerHost$'
    result = run(['go', 'test', '-race', '-tags=' + tags, '-count=1', '-timeout=3m', '-v',
                  './internal/pkg/migration', '-run', selected],
                 cwd=source, env=env, timeout=240, required=False)
    raw = result.stdout + result.stderr
    capture = directory / 'iam-host-private.log'; capture.write_text(raw); capture.chmod(0o600)
    proof['private_output_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
    proof['exit_code'] = result.returncode
    proof['diagnostics'] = host_failure_summary(raw)
    if runtime_required:
        proof['runtime_assertion_lines'] = sorted(set(map(int,re.findall(r'transaction_runtime_native_integration_test\.go:(\d+)',raw))))[:32]
    if private_log is not None:
        retain_private_host_output(private_log, raw)
    if result.returncode:
        raise RuntimeError('actual IAM host acceptance failed (private output withheld)')
    proof['native_receipt'] = parse_host_receipt(result.stdout, require_business_result)
    if runtime_required:
        proof['runtime_receipt'] = parse_runtime_receipt(result.stdout, proof['source_sha'])
        if protection:
            proof['protection_receipt'] = parse_protection_receipt(result.stdout, proof['source_sha'])
        if native_limit:
            proof['native_limit_receipt'] = parse_native_limit_receipt(result.stdout, proof['source_sha'])
    if qs_source is not None:
        proof['qs_fanout']['receipt'] = parse_fanout_receipt(result.stdout)
        proof['qs_fanout']['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=qs_source).stdout.strip()
        if not proof['qs_fanout']['source_clean_after']:
            raise RuntimeError('QS source changed during fanout acceptance')
    proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if not proof['source_clean_after']:
        raise RuntimeError('IAM tracked source changed during native acceptance')
    proof['scope'] = 'real Broker, released SDK, host original transaction and application entry; not production/system acceptance'


def parse_fanout_receipt(output):
    receipts = [json.loads(line.split('M3_FANOUT_RECEIPT ', 1)[1])
                for line in output.splitlines() if 'M3_FANOUT_RECEIPT {' in line]
    expected = ('iam_revocation_observed', 'qs_notification_received', 'qs_both_subjects_evicted',
                'qs_primary_proof_verified', 'qs_subscriber_drained')
    if (len(receipts) != 1 or receipts[0].get('iam_instances') != 2
            or receipts[0].get('failed') != 0 or receipts[0].get('skipped') != 0
            or any(receipts[0].get(key) is not True for key in expected)):
        raise RuntimeError('separate IAM/QS actual fanout proof absent or incomplete')
    return receipts[0]
