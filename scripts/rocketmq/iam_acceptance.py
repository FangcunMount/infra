"""Actual IAM host acceptance, only inside ci-transactions' owned fixture."""
import hashlib
import json
import os
import re
import secrets
from pathlib import Path

from provision_v2 import provision
from routes import consumer_group_v2, physical_topic_v2, validate_v2


def iam_manifest():
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
    validate_v2(result)
    return result


def parse_host_receipt(output):
    receipts = [json.loads(line.split('M3_HOST_RECEIPT ', 1)[1])
                for line in output.splitlines() if 'M3_HOST_RECEIPT {' in line]
    if (len(receipts) != 1 or receipts[0].get('passed') != 4 or receipts[0].get('failed') != 0
            or receipts[0].get('skipped') != 0
            or any(receipts[0].get(name) is not True for name in
                   ('half_invisible', 'commit_wire_and_witness', 'application_entry', 'rollback_hidden'))
            or not re.search(r'--- PASS: TestM3ActualBrokerHost \(', output)
            or re.search(r'--- (?:SKIP|FAIL):', output)):
        raise RuntimeError('IAM native receipt is absent, failed, skipped or incomplete')
    return receipts[0]


def host_failure_summary(raw):
    # Fixed classifications only; never copy a driver error, wire or credential.
    return {'build_failed': '[build failed]' in raw,
            'test_timeout': 'panic: test timed out' in raw,
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


def run_iam_host(source, directory, broker, project, grpc_port, mysql_port, password, ca, run, proof, private_log=None):
    source = source.resolve()
    if not (source / 'go.mod').is_file():
        raise RuntimeError('required exact IAM source checkout missing')
    tracked = run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if tracked:
        raise RuntimeError('IAM source checkout is dirty before acceptance')
    proof['source_sha'] = run(['git', 'rev-parse', 'HEAD'], cwd=source).stdout.strip()
    env = dict(os.environ, GOWORK='off', GOFLAGS='-mod=readonly')
    module = json.loads(run(['go', 'list', '-m', '-json', 'github.com/FangcunMount/reliable-messaging'],
                            cwd=source, env=env).stdout)
    if module.get('Replace') or not module.get('Version') or not module.get('Sum'):
        raise RuntimeError('IAM must use its pinned downloaded SDK without replace')
    proof['sdk_module'] = {key: module.get(key) for key in ('Path', 'Version', 'Sum', 'GoModSum')}
    manifest = iam_manifest()
    accounts = {role: {'username': 'm3-' + role + '-' + secrets.token_hex(4),
                       'password': secrets.token_hex(32)} for role in manifest['accounts']}
    proof['provision'] = provision(broker, manifest, accounts)
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
    result = run(['go', 'test', '-race', '-tags=integration', '-count=1', '-timeout=3m', '-v',
                  './internal/pkg/migration', '-run', '^TestM3ActualBrokerHost$'],
                 cwd=source, env=env, timeout=240, required=False)
    raw = result.stdout + result.stderr
    capture = directory / 'iam-host-private.log'; capture.write_text(raw); capture.chmod(0o600)
    proof['private_output_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
    proof['exit_code'] = result.returncode
    proof['diagnostics'] = host_failure_summary(raw)
    if private_log is not None:
        retain_private_host_output(private_log, raw)
    if result.returncode:
        raise RuntimeError('actual IAM host acceptance failed (private output withheld)')
    proof['native_receipt'] = parse_host_receipt(result.stdout)
    proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if not proof['source_clean_after']:
        raise RuntimeError('IAM tracked source changed during native acceptance')
    proof['scope'] = 'real Broker, released SDK, host original transaction and application entry; not production/system acceptance'
