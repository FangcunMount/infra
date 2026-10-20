"""QS task opening transaction host proof, only inside the owned infra fixture."""
import hashlib
import json
import os
import re
import secrets

from provision_v2 import provision
from routes import consumer_group_v2, physical_topic_v2, validate_v2
from iam_acceptance import host_failure_summary, retain_private_host_output


CASES = frozenset(('constructor_no_ddl', 'half_invisible', 'original_task_witness_wire',
                   'first_entry_reused', 'root_abort_atomic', 'fresh_owner_recovery',
                   'closed_admission_no_business', 'no_new_publish_outbox', 'normal_best_effort_fanout',
                   'normal_root_commit_boundary', 'normal_rejects_transaction_event', 'reminder_precision_compatible',
                   'original_write_abort_atomic', 'stale_schedule_cannot_commit'))


def task_manifest():
    topic, subscription = 'qs.plan.task', 'qs-m3-task-observer'
    route = {'id': 'qs-task-native', 'topic': topic, 'subscription': subscription,
             'message_type': 'TRANSACTION', 'owner': 'qs.mysql', 'route_revision': 'm3-1',
             'physical_topic': physical_topic_v2(topic, 'TRANSACTION', 'qs.mysql', 'm3-1'),
             'consumer_group': consumer_group_v2(topic, subscription)}
    manifest = {'version': 2, 'routes': [route],
                'topic_options': {'read_queue_nums': 1, 'write_queue_nums': 1, 'perm': 6},
                'group_options': {'retry_queue_nums': 8},
                'accounts': {'qs-task-producer': {'owner': 'qs.mysql', 'publish': [route['id']], 'subscriptions': []},
                             'qs-task-observer': {'publish': [], 'subscriptions': [route['id']]}}}
    normal_ids = []
    for topic in ('qs.plan.task', 'qs.survey.lifecycle'):
        for subscription in ('qs-m3-normal-a', 'qs-m3-normal-b'):
            identity = topic + '-' + subscription
            normal_ids.append(identity)
            manifest['routes'].append({'id': identity, 'topic': topic, 'subscription': subscription,
                'message_type': 'NORMAL', 'owner': 'qs.notify', 'route_revision': 'm3-1',
                'physical_topic': physical_topic_v2(topic, 'NORMAL', 'qs.notify', 'm3-1'),
                'consumer_group': consumer_group_v2(topic, subscription)})
    manifest['accounts']['qs-normal-producer'] = {'owner': 'qs.notify', 'publish': normal_ids, 'subscriptions': []}
    for suffix in ('a', 'b'):
        manifest['accounts']['qs-normal-' + suffix] = {'publish': [], 'subscriptions': [
            identity for identity in normal_ids if identity.endswith('-' + suffix)]}
    validate_v2(manifest)
    return manifest


def parse_task_receipt(output):
    receipts = [json.loads(line.split('M3_QS_TASK_RECEIPT ', 1)[1])
                for line in output.splitlines() if 'M3_QS_TASK_RECEIPT {' in line]
    if (len(receipts) != 1 or receipts[0].get('passed') != len(CASES)
            or receipts[0].get('failed') != 0 or receipts[0].get('skipped') != 0
            or set(receipts[0].get('cases', {})) != CASES
            or any(value is not True for value in receipts[0]['cases'].values())
            or receipts[0].get('root') != 'original_mysql_gorm'
            or receipts[0].get('system_login_not_claimed') is not True
            or receipts[0].get('process_exit_not_claimed') is not True
            or not re.search(r'--- PASS: TestM3TaskBrokerHost \(', output)
            or re.search(r'--- (?:SKIP|FAIL):|WARNING: DATA RACE', output)):
        raise RuntimeError('QS native task receipt absent, incomplete, failed or skipped')
    return receipts[0]


def run_qs_task_host(source, directory, broker, project, grpc_port, mysql_port, password, ca, run, proof, private_log=None):
    source = source.resolve()
    if not (source / 'go.mod').is_file() or run(['git', 'status', '--porcelain'], cwd=source).stdout.strip():
        raise RuntimeError('exact clean QS host source required')
    proof['source_sha'] = run(['git', 'rev-parse', 'HEAD'], cwd=source).stdout.strip()
    env = dict(os.environ, GOWORK='off', GOFLAGS='-mod=readonly')
    module = json.loads(run(['go', 'list', '-m', '-json', 'github.com/FangcunMount/reliable-messaging'], cwd=source, env=env).stdout)
    if module.get('Replace') or not module.get('Version') or not module.get('Sum'):
        raise RuntimeError('fixed published SDK without local replace required')
    proof['sdk_module'] = {key: module.get(key) for key in ('Path', 'Version', 'Sum', 'GoModSum')}
    manifest = task_manifest()
    accounts = {role: {'username': 'm3-' + role + '-' + secrets.token_hex(4), 'password': secrets.token_hex(32)}
                for role in manifest['accounts']}
    proof['provision'] = provision(broker, manifest, accounts)
    routes = directory / 'qs-task-routes.json'
    routes.write_text(json.dumps(manifest)); routes.chmod(0o600)
    paths = {}
    for role in accounts:
        credentials = directory / (role + '-credentials.json')
        credentials.write_text(json.dumps(accounts[role])); credentials.chmod(0o600)
        config = {'provider': 'rocketmq', 'enabled': True,
                  'rocketmq': {'endpoint': f'127.0.0.1:{grpc_port}', 'credentials_file': str(credentials),
                               'ca_file': str(ca), 'routes_file': str(routes),
                               'instance_id': 'qs-m3-task-fixture', 'publish_enabled': True}}
        if role == 'qs-task-producer':
            config['rocketmq']['transactions'] = {'qs.mysql': {'store_id': 'qs-native-mysql-task-primary',
                                                              'writer_epoch': 'm3-1', 'route_revision': 'm3-1'}}
        path = directory / (role + '-options.json')
        path.write_text(json.dumps(config)); path.chmod(0o600); paths[role] = path
    logs = directory / 'qs-task-private-client-logs'; logs.mkdir(mode=0o700)
    env.update({'QS_M3_FIXTURE_PROJECT': project,
                'QS_M3_TASK_DSN': f'root:{password}@tcp(127.0.0.1:{mysql_port})/?parseTime=true',
                'QS_M3_PRODUCER_CONFIG': str(paths['qs-task-producer']),
                'QS_M3_OBSERVER_CONFIG': str(paths['qs-task-observer']),
                'QS_M3_NORMAL_PRODUCER_CONFIG': str(paths['qs-normal-producer']),
                'QS_M3_NORMAL_A_CONFIG': str(paths['qs-normal-a']),
                'QS_M3_NORMAL_B_CONFIG': str(paths['qs-normal-b']),
                'rocketmq.client.logRoot': str(logs), 'rocketmq.client.logLevel': 'error'})
    result = run(['go', 'test', '-p', '1', '-race', '-tags=integration,m3_task_broker', '-count=1', '-timeout=3m', '-v',
                  './internal/apiserver/container/internal/transaction', '-run', '^TestM3TaskBrokerHost$'],
                 cwd=source, env=env, timeout=420, required=False)
    raw = result.stdout + result.stderr
    capture = directory / 'qs-task-host-private.log'; capture.write_text(raw); capture.chmod(0o600)
    proof['private_output_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
    proof['exit_code'] = result.returncode
    proof['diagnostics'] = host_failure_summary(raw)
    proof['diagnostics']['assertion_lines'] = sorted(set(int(n) for n in re.findall(r'm3_task_broker_integration_test\.go:(\d+)', raw)))[:32]
    if private_log is not None:
        retain_private_host_output(private_log, raw)
    if result.returncode:
        raise RuntimeError('actual QS task host acceptance failed (private output withheld)')
    proof['native_receipt'] = parse_task_receipt(result.stdout)
    proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if not proof['source_clean_after']:
        raise RuntimeError('QS source changed during native acceptance')
    proof['scope'] = ('real RocketMQ and original MySQL task opening committer; deterministic task fixture; '
                      'no production/system, packet loss, SIGKILL or T13 dispatch claim')
