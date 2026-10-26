"""Actual authenticated QS event receiver and original ACK transaction; controlled AI input only."""
import hashlib
import json
import os
import re
import secrets

from iam_acceptance import host_failure_summary
from provision_v2 import provision
from routes import consumer_group_v2, physical_topic_v2, validate_v2


CASES = frozenset(('constructor_no_ddl', 'half_invisible_before_root_commit',
                   'inbox_projection_archive_witness_atomic', 'first_ack_wire_authenticated',
                   'committed_duplicate_reuses_first_ack', 'conflicting_wire_isolated',
                   'new_command_receipt_without_outbox', 'legacy_command_receipt_compatible',
                   'technical_hold_without_projection', 'nonempty_legacy_inbox_not_adopted',
                   'server_rejection_rolls_back_root', 'aborted_delivery_explicit_retry',
                   'aborted_disposition_explicit_replan', 'no_new_ack_outbox',
                   'fresh_adapter_exact_witness', 'interpretation_projection_original_root', 'prepared_ack_payload_not_exposed'))


def event_manifest():
    routes = []
    for kind, topic, subscription in (
            ('command', 'qs.ai.commands.v1', 'qs-ai.commands.v1'),
            ('ack', 'qs.ai.acks.v1', 'qs-ai.acks.v1')):
        routes.append({'id': 'qs-event-' + kind, 'topic': topic, 'subscription': subscription,
                       'message_type': 'TRANSACTION', 'owner': 'qs.mysql', 'route_revision': 'm3-1',
                       'physical_topic': physical_topic_v2(topic, 'TRANSACTION', 'qs.mysql', 'm3-1'),
                       'consumer_group': consumer_group_v2(topic, subscription)})
    ids = [r['id'] for r in routes]
    manifest = {'version': 2, 'routes': routes,
                'topic_options': {'read_queue_nums': 1, 'write_queue_nums': 1, 'perm': 6},
                'group_options': {'retry_queue_nums': 8},
                'accounts': {'qs-event-producer': {'owner': 'qs.mysql', 'publish': ids, 'subscriptions': []},
                             'qs-event-observer': {'publish': [], 'subscriptions': ids}}}
    validate_v2(manifest)
    return manifest


def parse_event_receipt(output, *, current_only=False):
    expected = (CASES - {"legacy_command_receipt_compatible"}) | {"legacy_command_receipt_rejected"} if current_only else CASES
    receipts = [json.loads(line.split('M3_QS_AI_EVENT_RECEIPT ', 1)[1])
                for line in output.splitlines() if 'M3_QS_AI_EVENT_RECEIPT {' in line]
    if (len(receipts) != 1 or receipts[0].get('passed') != len(expected)
            or receipts[0].get('failed') != 0 or receipts[0].get('skipped') != 0
            or set(receipts[0].get('cases', {})) != expected
            or any(value is not True for value in receipts[0]['cases'].values())
            or receipts[0].get('root') != 'original_mysql_sql'
            or any(receipts[0].get(key) is not True for key in (
                'system_login_not_claimed', 'paired_ai_producer_not_claimed',
                'process_exit_not_claimed', 'database_commit_network_fault_not_claimed'))
            or not re.search(r'--- PASS: TestM3AIEventBrokerHost \(', output)
            or re.search(r'--- (?:SKIP|FAIL):|WARNING: DATA RACE', output)):
        raise RuntimeError('QS native event receipt absent, incomplete, failed or skipped')
    return receipts[0]


def run_qs_event_host(source, directory, broker, project, grpc_port, mysql_port, password, ca, run, proof):
    source = source.resolve()
    if not (source / 'go.mod').is_file() or run(['git', 'status', '--porcelain'], cwd=source).stdout.strip():
        raise RuntimeError('exact clean QS host source required')
    proof['source_sha'] = run(['git', 'rev-parse', 'HEAD'], cwd=source).stdout.strip()
    env = dict(os.environ, GOWORK='off', GOFLAGS='-mod=readonly')
    module = json.loads(run(['go', 'list', '-m', '-json', 'github.com/FangcunMount/reliable-messaging'], cwd=source, env=env).stdout)
    if module.get('Replace') or not module.get('Version') or not module.get('Sum'):
        raise RuntimeError('fixed published SDK without local replace required')
    proof['sdk_module'] = {key: module.get(key) for key in ('Path', 'Version', 'Sum', 'GoModSum')}
    manifest = event_manifest()
    accounts = {role: {'username': 'm3-' + role + '-' + secrets.token_hex(4), 'password': secrets.token_hex(32)}
                for role in manifest['accounts']}
    proof['provision'] = provision(broker, manifest, accounts)
    routes = directory / 'qs-event-routes.json'
    routes.write_text(json.dumps(manifest)); routes.chmod(0o600)
    paths = {}
    for role in accounts:
        credentials = directory / (role + '-credentials.json')
        credentials.write_text(json.dumps(accounts[role])); credentials.chmod(0o600)
        config = {'provider': 'rocketmq', 'enabled': True,
                  'rocketmq': {'endpoint': f'127.0.0.1:{grpc_port}', 'credentials_file': str(credentials),
                               'ca_file': str(ca), 'routes_file': str(routes),
                               'instance_id': 'qs-m3-event-fixture', 'publish_enabled': True}}
        if role == 'qs-event-producer':
            config['rocketmq']['transactions'] = {'qs.mysql': {'store_id': 'qs-native-mysql-event-primary',
                                                              'writer_epoch': 'm3-1', 'route_revision': 'm3-1'}}
        path = directory / (role + '-options.json')
        path.write_text(json.dumps(config)); path.chmod(0o600); paths[role] = path
    logs = directory / 'qs-event-private-client-logs'; logs.mkdir(mode=0o700)
    env.update({'QS_M3_FIXTURE_PROJECT': project,
                'QS_M3_EVENT_DSN': f'root:{password}@tcp(127.0.0.1:{mysql_port})/?parseTime=true',
                'QS_M3_PRODUCER_CONFIG': str(paths['qs-event-producer']),
                'QS_M3_OBSERVER_CONFIG': str(paths['qs-event-observer']),
                'rocketmq.client.logRoot': str(logs), 'rocketmq.client.logLevel': 'error'})
    result = run(['go', 'test', '-p', '1', '-race', '-tags=integration,m3_ai_event_broker', '-count=1',
                  '-timeout=4m', '-v', './internal/apiserver/infra/mysql/aibridge',
                  '-run', '^TestM3AIEventBrokerHost$'], cwd=source, env=env, timeout=420, required=False)
    raw = result.stdout + result.stderr
    capture = directory / 'qs-event-host-private.log'; capture.write_text(raw); capture.chmod(0o600)
    proof['private_output_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
    proof['exit_code'] = result.returncode
    proof['diagnostics'] = host_failure_summary(raw)
    proof['diagnostics']['assertion_lines'] = sorted(set(int(n) for n in re.findall(
        r'transaction_event_broker_integration_test\.go:(\d+)', raw)))[:32]
    if result.returncode:
        raise RuntimeError('actual QS event host acceptance failed (private output withheld)')
    proof['native_receipt'] = parse_event_receipt(result.stdout, current_only=os.environ.get("QS_M4_CURRENT_READERS") == "1")
    proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if not proof['source_clean_after']:
        raise RuntimeError('QS source changed during native acceptance')
    proof['scope'] = 'actual authenticated event receiver, original SQL roots and real ACK Broker; controlled AI inputs, observer ACK only'
