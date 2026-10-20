"""QS report transaction host proof, only inside the owned infra fixture."""
import hashlib
import json
import os
import re
import secrets

from provision_v2 import provision
from routes import consumer_group_v2, physical_topic_v2, validate_v2
from iam_acceptance import host_failure_summary, retain_private_host_output


CASES = frozenset((
    'constructor_no_ddl', 'half_invisible', 'original_success_witness_wire',
    'duplicate_first_artifact', 'original_failure_witness', 'future_retry_preserved',
    'root_abort_atomic', 'stale_claim_cannot_commit', 'committed_reply_discard_recovery',
    'native_callback_reentry', 'no_new_publish_outbox', 'new_instance_exact_recovery',
    'closed_admission_no_business', 'v2_authority_audit'))


def report_manifest():
    topic, subscription = 'qs.evaluation.lifecycle', 'qs-m3-report-observer'
    route = {'id': 'qs-report-native', 'topic': topic, 'subscription': subscription,
             'message_type': 'TRANSACTION', 'owner': 'qs.mongo', 'route_revision': 'm3-1',
             'physical_topic': physical_topic_v2(topic, 'TRANSACTION', 'qs.mongo', 'm3-1'),
             'consumer_group': consumer_group_v2(topic, subscription)}
    manifest = {'version': 2, 'routes': [route],
                'topic_options': {'read_queue_nums': 1, 'write_queue_nums': 1, 'perm': 6},
                'group_options': {'retry_queue_nums': 8},
                'accounts': {'qs-report-producer': {'owner': 'qs.mongo', 'publish': [route['id']], 'subscriptions': []},
                             'qs-report-observer': {'publish': [], 'subscriptions': [route['id']]}}}
    validate_v2(manifest)
    return manifest


def parse_report_receipt(output):
    receipts = [json.loads(line.split('M3_QS_REPORT_RECEIPT ', 1)[1])
                for line in output.splitlines() if 'M3_QS_REPORT_RECEIPT {' in line]
    if (len(receipts) != 1 or receipts[0].get('passed') != len(CASES)
            or receipts[0].get('failed') != 0 or receipts[0].get('skipped') != 0
            or set(receipts[0].get('cases', {})) != CASES
            or any(value is not True for value in receipts[0]['cases'].values())
            or receipts[0].get('root_ack_discard_is_client_level') is not True
            or receipts[0].get('mongo_callback_failpoint') is not True
            or receipts[0].get('host_entry') != 'interpretation_original_root_committer'
            or receipts[0].get('system_login_not_claimed') is not True
            or not re.search(r'--- PASS: TestM3ReportTerminalBrokerHost \(', output)
            or re.search(r'--- (?:SKIP|FAIL):|WARNING: DATA RACE', output)):
        raise RuntimeError('QS native report receipt absent, incomplete, failed or skipped')
    return receipts[0]


def run_qs_report_host(source, directory, broker, project, grpc_port, mongo_port, ca, run, proof, private_log=None):
    source = source.resolve()
    if not (source / 'go.mod').is_file() or run(['git', 'status', '--porcelain'], cwd=source).stdout.strip():
        raise RuntimeError('exact clean QS host source required')
    proof['source_sha'] = run(['git', 'rev-parse', 'HEAD'], cwd=source).stdout.strip()
    env = dict(os.environ, GOWORK='off', GOFLAGS='-mod=readonly')
    module = json.loads(run(['go', 'list', '-m', '-json', 'github.com/FangcunMount/reliable-messaging'], cwd=source, env=env).stdout)
    if module.get('Replace') or not module.get('Version') or not module.get('Sum'):
        raise RuntimeError('fixed published SDK without local replace required')
    proof['sdk_module'] = {key: module.get(key) for key in ('Path', 'Version', 'Sum', 'GoModSum')}
    manifest = report_manifest()
    accounts = {role: {'username': 'm3-' + role + '-' + secrets.token_hex(4), 'password': secrets.token_hex(32)}
                for role in manifest['accounts']}
    proof['provision'] = provision(broker, manifest, accounts)
    routes = directory / 'qs-report-routes.json'
    routes.write_text(json.dumps(manifest)); routes.chmod(0o600)
    paths = {}
    for role in accounts:
        credentials = directory / (role + '-credentials.json')
        credentials.write_text(json.dumps(accounts[role])); credentials.chmod(0o600)
        config = {'provider': 'rocketmq', 'enabled': True,
                  'rocketmq': {'endpoint': f'127.0.0.1:{grpc_port}', 'credentials_file': str(credentials),
                               'ca_file': str(ca), 'routes_file': str(routes),
                               'instance_id': 'qs-m3-report-fixture', 'publish_enabled': True}}
        if role == 'qs-report-producer':
            config['rocketmq']['transactions'] = {'qs.mongo': {'store_id': 'qs-native-mongo-primary',
                                                              'writer_epoch': 'm3-1', 'route_revision': 'm3-1'}}
        path = directory / (role + '-options.json')
        path.write_text(json.dumps(config)); path.chmod(0o600); paths[role] = path
    logs = directory / 'qs-report-private-client-logs'; logs.mkdir(mode=0o700)
    env.update({'QS_M3_FIXTURE_PROJECT': project,
                'QS_M3_MONGO_URI': f'mongodb://127.0.0.1:{mongo_port}/?replicaSet=sdk-proof&directConnection=true',
                'QS_M3_PRODUCER_CONFIG': str(paths['qs-report-producer']),
                'QS_M3_OBSERVER_CONFIG': str(paths['qs-report-observer']),
                'rocketmq.client.logRoot': str(logs), 'rocketmq.client.logLevel': 'error'})
    result = run(['go', 'test', '-race', '-tags=integration,m3_report_integration', '-count=1', '-timeout=5m', '-v',
                  './internal/apiserver/container/internal/transaction', '-run', '^TestM3ReportTerminalBrokerHost$'],
                 cwd=source, env=env, timeout=420, required=False)
    raw = result.stdout + result.stderr
    capture = directory / 'qs-report-host-private.log'; capture.write_text(raw); capture.chmod(0o600)
    proof['private_output_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
    proof['exit_code'] = result.returncode
    proof['diagnostics'] = host_failure_summary(raw)
    proof['diagnostics']['assertion_lines'] = sorted(set(int(n) for n in re.findall(r'(?:m3_report_broker|m3_retry_dispatch_recovery)_integration_test\.go:(\d+)', raw)))[:32]
    if private_log is not None:
        retain_private_host_output(private_log, raw)
    if result.returncode:
        raise RuntimeError('actual QS report host acceptance failed (private output withheld)')
    proof['native_receipt'] = parse_report_receipt(result.stdout)
    proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if not proof['source_clean_after']:
        raise RuntimeError('QS source changed during native acceptance')
    proof['scope'] = ('real RocketMQ and original report Mongo terminal committer; fixtures create the original running claim and immutable report; '
                      'client root ACK discard is not packet loss; fresh instance is not SIGKILL; no model invocation, production or system acceptance')
