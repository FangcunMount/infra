"""Actual QS command entrypoints; controlled receipts do not claim AI acceptance."""
import hashlib
import json
import os
import re
import secrets

from iam_acceptance import host_failure_summary
from provision_v2 import provision
from routes import consumer_group_v2, physical_topic_v2, validate_v2


CASES = frozenset(('constructor_no_ddl', 'missing_order_schema_refused',
                   'half_invisible_before_root_commit', 'original_business_archive_witness_atomic',
                   'first_wire_authenticated_and_reused', 'stable_input_conflict_before_reseal',
                   'operation_and_payload_scoped', 'fresh_adapter_exact_witness',
                   'predecessor_pending_before_half', 'held_predecessor_before_half',
                   'workflow_and_evaluation_original_entrypoints', 'no_new_command_outbox',
                   'real_server_rejection_root_rollback', 'aborted_duplicate_never_reexecutes',
                   'nonempty_legacy_operation_compatible'))


def command_manifest():
    topic, subscription = 'qs.ai.commands.v1', 'qs-m3-ai-command-observer'
    route = {'id': 'qs-command-native', 'topic': topic, 'subscription': subscription,
             'message_type': 'TRANSACTION', 'owner': 'qs.mysql', 'route_revision': 'm3-1',
             'physical_topic': physical_topic_v2(topic, 'TRANSACTION', 'qs.mysql', 'm3-1'),
             'consumer_group': consumer_group_v2(topic, subscription)}
    manifest = {'version': 2, 'routes': [route],
                'topic_options': {'read_queue_nums': 1, 'write_queue_nums': 1, 'perm': 6},
                'group_options': {'retry_queue_nums': 8},
                'accounts': {'qs-command-producer': {'owner': 'qs.mysql', 'publish': [route['id']], 'subscriptions': []},
                             'qs-command-observer': {'publish': [], 'subscriptions': [route['id']]}}}
    validate_v2(manifest)
    return manifest


def parse_command_receipt(output, *, current_only=False):
    expected = (CASES - {"nonempty_legacy_operation_compatible"}) | {"nonempty_legacy_operation_rejected"} if current_only else CASES
    receipts = [json.loads(line.split('M3_QS_AI_COMMAND_RECEIPT ', 1)[1])
                for line in output.splitlines() if 'M3_QS_AI_COMMAND_RECEIPT {' in line]
    if (len(receipts) != 1 or receipts[0].get('passed') != len(expected)
            or receipts[0].get('failed') != 0 or receipts[0].get('skipped') != 0
            or set(receipts[0].get('cases', {})) != expected
            or any(value is not True for value in receipts[0]['cases'].values())
            or receipts[0].get('root') != 'original_mysql_sql'
            or any(receipts[0].get(key) is not True for key in (
                'system_login_not_claimed', 'paired_ai_receiver_not_claimed',
                'process_exit_not_claimed', 'database_commit_network_fault_not_claimed'))
            or not re.search(r'--- PASS: TestM3AICommandBrokerHost \(', output)
            or re.search(r'--- (?:SKIP|FAIL):|WARNING: DATA RACE', output)):
        raise RuntimeError('QS native command receipt absent, incomplete, failed or skipped')
    return receipts[0]


def run_qs_command_host(source, directory, broker, project, grpc_port, mysql_port, password, ca, run, proof, *, faults=False, native_runner=None, proxy_start=None):
    source = source.resolve()
    if not (source / 'go.mod').is_file() or run(['git', 'status', '--porcelain'], cwd=source).stdout.strip():
        raise RuntimeError('exact clean QS host source required')
    proof['source_sha'] = run(['git', 'rev-parse', 'HEAD'], cwd=source).stdout.strip()
    env = dict(os.environ, GOWORK='off', GOFLAGS='-mod=readonly')
    module = json.loads(run(['go', 'list', '-m', '-json', 'github.com/FangcunMount/reliable-messaging'], cwd=source, env=env).stdout)
    if module.get('Replace') or not module.get('Version') or not module.get('Sum'):
        raise RuntimeError('fixed published SDK without local replace required')
    proof['sdk_module'] = {key: module.get(key) for key in ('Path', 'Version', 'Sum', 'GoModSum')}
    if faults and module.get('Version') != 'v0.5.0-rocketmq-tx.2':
        raise RuntimeError('original command faults require fixed SDK tx.2')
    manifest = command_manifest()
    accounts = {role: {'username': 'm3-' + role + '-' + secrets.token_hex(4), 'password': secrets.token_hex(32)}
                for role in manifest['accounts']}
    proof['provision'] = provision(broker, manifest, accounts)
    routes = directory / 'qs-command-routes.json'
    routes.write_text(json.dumps(manifest)); routes.chmod(0o600)
    paths = {}
    for role in accounts:
        credentials = directory / (role + '-credentials.json')
        credentials.write_text(json.dumps(accounts[role])); credentials.chmod(0o600)
        config = {'provider': 'rocketmq', 'enabled': True,
                  'rocketmq': {'endpoint': f'127.0.0.1:{grpc_port}', 'credentials_file': str(credentials),
                               'ca_file': str(ca), 'routes_file': str(routes),
                               'instance_id': 'qs-m3-command-fixture', 'publish_enabled': True}}
        if role == 'qs-command-producer':
            config['rocketmq']['transactions'] = {'qs.mysql': {'store_id': 'qs-native-mysql-command-primary',
                                                              'writer_epoch': 'm3-1', 'route_revision': 'm3-1'}}
        path = directory / (role + '-options.json')
        path.write_text(json.dumps(config)); path.chmod(0o600); paths[role] = path
    logs = directory / 'qs-command-private-client-logs'; logs.mkdir(mode=0o700)
    env.update({'QS_M3_FIXTURE_PROJECT': project,
                'QS_M3_COMMAND_DSN': f'root:{password}@tcp(127.0.0.1:{mysql_port})/?parseTime=true',
                'QS_M3_PRODUCER_CONFIG': str(paths['qs-command-producer']),
                'QS_M3_OBSERVER_CONFIG': str(paths['qs-command-observer']),
                'rocketmq.client.logRoot': str(logs), 'rocketmq.client.logLevel': 'error'})
    if faults:
        from qs_command_fault_acceptance import run_profile
        run_profile(source, directory, env, run, proof, native_runner, proxy_start)
        return
    result = run(['go', 'test', '-p', '1', '-race', '-tags=integration,m3_ai_command_broker', '-count=1',
                  '-timeout=4m', '-v', './internal/apiserver/infra/mysql/aibridge',
                  '-run', '^TestM3AICommandBrokerHost$'], cwd=source, env=env, timeout=420, required=False)
    raw = result.stdout + result.stderr
    capture = directory / 'qs-command-host-private.log'; capture.write_text(raw); capture.chmod(0o600)
    proof['private_output_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
    proof['exit_code'] = result.returncode
    proof['diagnostics'] = host_failure_summary(raw)
    proof['diagnostics']['assertion_lines'] = sorted(set(int(n) for n in re.findall(
        r'transaction_command_broker_integration_test\.go:(\d+)', raw)))[:32]
    if result.returncode:
        raise RuntimeError('actual QS command host acceptance failed (private output withheld)')
    proof['native_receipt'] = parse_command_receipt(result.stdout, current_only=os.environ.get("QS_M4_CURRENT_READERS") == "1")
    proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if not proof['source_clean_after']:
        raise RuntimeError('QS source changed during native acceptance')
    proof['scope'] = 'actual command entrypoints, original SQL roots and real Broker; controlled predecessor receipts, observer ACK only'
