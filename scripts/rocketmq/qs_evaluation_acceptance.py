"""QS evaluation transaction host proof, only inside the owned infra fixture."""
import hashlib
import json
import os
import re
import secrets

from provision_v2 import provision
from routes import consumer_group_v2, physical_topic_v2, validate_v2
from iam_acceptance import host_failure_summary, retain_private_host_output


EVALUATION_CASES = frozenset(('constructor_no_ddl', 'request_cas_wire_and_witness',
                   'request_duplicate_first_wire', 'half_hidden_until_original_outcome_root',
                   'closed_admission_no_business', 'exact_frozen_result_recovery'))
FAILURE_CASES = frozenset(('failure_original_root_and_witness',
                           'future_retry_retains_due_authorization_and_wire',
                           'failure_redelivery_no_extra_attempt_or_input_call'))
CASES = EVALUATION_CASES | FAILURE_CASES



def evaluation_manifest():
    topic, subscription = 'qs.evaluation.lifecycle', 'qs-m3-evaluation-observer'
    route = {'id': 'qs-evaluation-native', 'topic': topic, 'subscription': subscription,
             'message_type': 'TRANSACTION', 'owner': 'qs.mysql', 'route_revision': 'm3-1',
             'physical_topic': physical_topic_v2(topic, 'TRANSACTION', 'qs.mysql', 'm3-1'),
             'consumer_group': consumer_group_v2(topic, subscription)}
    manifest = {'version': 2, 'routes': [route],
                'topic_options': {'read_queue_nums': 1, 'write_queue_nums': 1, 'perm': 6},
                'group_options': {'retry_queue_nums': 8},
                'accounts': {'qs-evaluation-producer': {'owner': 'qs.mysql', 'publish': [route['id']], 'subscriptions': []},
                             'qs-evaluation-observer': {'publish': [], 'subscriptions': [route['id']]}}}
    failure = dict(route, id='qs-failure-native', subscription='qs-m3-failure-observer',
                   consumer_group=consumer_group_v2(topic, 'qs-m3-failure-observer'))
    manifest['routes'].append(failure)
    manifest['accounts']['qs-failure-producer'] = {'owner': 'qs.mysql', 'publish': [failure['id']], 'subscriptions': []}
    manifest['accounts']['qs-failure-observer'] = {'publish': [], 'subscriptions': [failure['id']]}
    validate_v2(manifest)
    return manifest


def parse_evaluation_receipt(output):
    receipts = [json.loads(line.split('M3_QS_EVALUATION_RECEIPT ', 1)[1])
                for line in output.splitlines() if 'M3_QS_EVALUATION_RECEIPT {' in line]
    if (len(receipts) != 1 or receipts[0].get('passed') != len(EVALUATION_CASES)
            or receipts[0].get('failed') != 0 or receipts[0].get('skipped') != 0
            or set(receipts[0].get('cases', {})) != EVALUATION_CASES
            or any(value is not True for value in receipts[0]['cases'].values())
            or receipts[0].get('broker') != 'actual_5.5.1'
            or receipts[0].get('root') != 'original_mysql_gorm'
            or receipts[0].get('source_input') != 'deterministic_fixture_not_system_account'
            or receipts[0].get('process_exit_not_claimed') is not True
            or not re.search(r'--- PASS: TestM3EvaluationBrokerHost \(', output)
            or re.search(r'--- (?:SKIP|FAIL):|WARNING: DATA RACE', output)):
        raise RuntimeError('QS native evaluation receipt absent, incomplete, failed or skipped')
    return receipts[0]


def parse_failure_receipt(output):
    receipts = [json.loads(line.split('M3_QS_FAILURE_RECEIPT ', 1)[1])
                for line in output.splitlines() if 'M3_QS_FAILURE_RECEIPT {' in line]
    if (len(receipts) != 1 or receipts[0].get('passed') != len(FAILURE_CASES)
            or receipts[0].get('failed') != 0 or receipts[0].get('skipped') != 0
            or set(receipts[0].get('cases', {})) != FAILURE_CASES
            or any(v is not True for v in receipts[0]['cases'].values())
            or receipts[0].get('root') != 'original_mysql_gorm'
            or receipts[0].get('source_input') != 'controlled_input_failure_no_provider'
            or receipts[0].get('process_exit_not_claimed') is not True
            or not re.search(r'--- PASS: TestM3FailureBrokerHost \(', output)
            or re.search(r'--- (?:SKIP|FAIL):|WARNING: DATA RACE', output)):
        raise RuntimeError('QS failure host receipt absent, partial, failed or skipped')
    return receipts[0]


def parse_host_receipt(output):
    evaluation, failure = parse_evaluation_receipt(output), parse_failure_receipt(output)
    return dict(evaluation, passed=len(CASES), cases=dict(evaluation['cases'], **failure['cases']),
                failure_entry=failure)


def run_qs_evaluation_host(source, directory, broker, project, grpc_port, mysql_port, password, ca, run, proof, private_log=None):
    source = source.resolve()
    if not (source / 'go.mod').is_file() or run(['git', 'status', '--porcelain'], cwd=source).stdout.strip():
        raise RuntimeError('exact clean QS host source required')
    proof['source_sha'] = run(['git', 'rev-parse', 'HEAD'], cwd=source).stdout.strip()
    env = dict(os.environ, GOWORK='off', GOFLAGS='-mod=readonly')
    module = json.loads(run(['go', 'list', '-m', '-json', 'github.com/FangcunMount/reliable-messaging'], cwd=source, env=env).stdout)
    if module.get('Replace') or not module.get('Version') or not module.get('Sum'):
        raise RuntimeError('fixed published SDK without local replace required')
    proof['sdk_module'] = {key: module.get(key) for key in ('Path', 'Version', 'Sum', 'GoModSum')}
    manifest = evaluation_manifest()
    accounts = {role: {'username': 'm3-' + role + '-' + secrets.token_hex(4), 'password': secrets.token_hex(32)}
                for role in manifest['accounts']}
    proof['provision'] = provision(broker, manifest, accounts)
    routes = directory / 'qs-evaluation-routes.json'
    routes.write_text(json.dumps(manifest)); routes.chmod(0o600)
    paths = {}
    for role in accounts:
        credentials = directory / (role + '-credentials.json')
        credentials.write_text(json.dumps(accounts[role])); credentials.chmod(0o600)
        config = {'provider': 'rocketmq', 'enabled': True,
                  'rocketmq': {'endpoint': f'127.0.0.1:{grpc_port}', 'credentials_file': str(credentials),
                               'ca_file': str(ca), 'routes_file': str(routes),
                               'instance_id': 'qs-m3-evaluation-fixture', 'publish_enabled': True}}
        if role in ('qs-evaluation-producer', 'qs-failure-producer'):
            config['rocketmq']['transactions'] = {'qs.mysql': {'store_id': ('qs-native-mysql-primary' if role == 'qs-evaluation-producer' else 'qs-native-mysql-failure-primary'),
                                                              'writer_epoch': 'm3-1', 'route_revision': 'm3-1'}}
        path = directory / (role + '-options.json')
        path.write_text(json.dumps(config)); path.chmod(0o600); paths[role] = path
    logs = directory / 'qs-evaluation-private-client-logs'; logs.mkdir(mode=0o700)
    env.update({'QS_M3_FIXTURE_PROJECT': project,
                'QS_M3_EVALUATION_DSN': f'root:{password}@tcp(127.0.0.1:{mysql_port})/?parseTime=true',
                'QS_M3_PRODUCER_CONFIG': str(paths['qs-evaluation-producer']),
                'QS_M3_OBSERVER_CONFIG': str(paths['qs-evaluation-observer']),
                'QS_M3_FAILURE_PRODUCER_CONFIG': str(paths['qs-failure-producer']),
                'QS_M3_FAILURE_OBSERVER_CONFIG': str(paths['qs-failure-observer']),
                'rocketmq.client.logRoot': str(logs), 'rocketmq.client.logLevel': 'error'})
    result = run(['go', 'test', '-p', '1', '-race', '-tags=integration,m3_evaluation_broker', '-count=1', '-timeout=5m', '-v',
                  './internal/apiserver/container/internal/transaction', '-run', '^TestM3(Evaluation|Failure)BrokerHost$'],
                 cwd=source, env=env, timeout=420, required=False)
    raw = result.stdout + result.stderr
    capture = directory / 'qs-evaluation-host-private.log'; capture.write_text(raw); capture.chmod(0o600)
    proof['private_output_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
    proof['exit_code'] = result.returncode
    proof['diagnostics'] = host_failure_summary(raw)
    proof['diagnostics']['assertion_lines'] = sorted(set(int(n) for n in re.findall(r'(?:m3_evaluation(?:_failure)?_broker|m3_retry_dispatch_recovery)_integration_test\.go:(\d+)', raw)))[:32]
    if private_log is not None:
        retain_private_host_output(private_log, raw)
    if result.returncode:
        raise RuntimeError('actual QS evaluation host acceptance failed (private output withheld)')
    proof['native_receipt'] = parse_host_receipt(result.stdout)
    proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if not proof['source_clean_after']:
        raise RuntimeError('QS source changed during native acceptance')
    proof['scope'] = ('real RocketMQ and original MySQL application submission/outcome roots; '
                      'deterministic input fixture, not system/production; '
                      'failure engine keeps original future schedule; no provider, packet loss, SIGKILL or T13 handoff claim')
