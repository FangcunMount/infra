"""Actual current worker runtime with owned Broker/MySQL and business RPC fixture."""
import hashlib
import json
import math
import os
import re
import secrets
from datetime import datetime

from host_sdk_contract import stable_module_matches
from iam_acceptance import host_failure_summary, retain_private_host_output
from m3_resources import manifest
from provision_v2 import provision, Admin
from routes import validate_v2

CASES = frozenset((
    'explicit_schema_before_subscription',
    'actual_broker_paused_delivery_preserves_first_wire',
    'original_dispatcher_and_shared_execution_budget',
    'real_broker_handler_drain_retains_grpc_until_return',
))
SCOPE = 'actual worker container/runtime/Broker/MySQL with loopback business RPC fixture'


def parse_worker_receipt(output, expected_source):
    receipts = [json.loads(line.split('M3_QS_WORKER_RUNTIME_RECEIPT ', 1)[1])
                for line in output.splitlines() if 'M3_QS_WORKER_RUNTIME_RECEIPT {' in line]
    if len(receipts) != 1:
        raise RuntimeError('one worker runtime receipt required')
    receipt = receipts[0]
    if (not re.fullmatch(r'[0-9a-f]{40}', expected_source)
            or receipt.get('source_sha') != expected_source
            or receipt.get('passed') != len(CASES) or receipt.get('failed') != 0
            or receipt.get('skipped') != 0 or set(receipt.get('cases', {})) != CASES
            or any(value is not True for value in receipt['cases'].values())
            or receipt.get('scope') != SCOPE
            or type(receipt.get('paused_observation_ms')) is not int or not 0 <= receipt['paused_observation_ms'] <= 65000
            or receipt.get('fixture_shared_limit') != 1 or receipt.get('fixture_observation_budget_ms') != 60000
            or any(receipt.get(key) is not True for key in (
                'complete_apiserver_not_claimed', 'provider_not_called', 'system_login_not_claimed',
                'owned_database_dropped', 'owned_runtime_drained'))
            or not re.search(r'--- PASS: TestM3WorkerRocketMQRuntime \(', output)
            or re.search(r'--- (?:FAIL|SKIP):|WARNING: DATA RACE', output)):
        raise RuntimeError('worker runtime receipt wrong source, partial, failed, skipped or cleanup incomplete')
    return receipt


def worker_failure_diagnostics(output):
    rows = [line.split('M3_WORKER_DIAGNOSTIC ', 1)[1] for line in output.splitlines()
            if line.startswith('M3_WORKER_DIAGNOSTIC ')]
    if not rows:
        return None
    if len(rows) != 1 or len(rows[0]) > 4096:
        return {'invalid': True}
    try:
        value = json.loads(rows[0])
        if (not isinstance(value, dict) or set(value) != {'phase', 'active', 'waiting', 'holds', 'evidence', 'query_failed', 'consume_outcomes', 'transport_errors', 'sdk_stack_sites', 'sdk_stack_truncated'}
                or value['phase'] not in {'paused_delivery', 'active_delivery'}
                or type(value.get('sdk_stack_truncated')) is not bool
                or not isinstance(value.get('sdk_stack_sites'), dict) or len(value['sdk_stack_sites'])>32
                or any(not re.fullmatch(r'(?:subscriber|simple_consumer):[0-9]{1,4}',k) or type(v) is not int or not 1<=v<=32 for k,v in value['sdk_stack_sites'].items()) or type(value['query_failed']) is not bool
                or any(type(value[k]) is not int or not 0 <= value[k] <= 1000000 for k in ('active', 'waiting', 'holds', 'evidence'))
                or not isinstance(value.get('transport_errors'),dict)
                or set(value['transport_errors']) - {'auth_or_acl','deadline','tls','connection','other'}
                or any(type(v) is not int or not 0<=v<=8 for v in value['transport_errors'].values())
                or not isinstance(value['consume_outcomes'], dict)
                or set(value['consume_outcomes']) - {'held', 'hold_failed', 'dispatch_failed', 'decode_failed', 'acked', 'unknown_acked', 'unknown_persist_failed'}
                or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1000000 for v in value['consume_outcomes'].values())):
            return {'invalid': True}
        return value
    except (ValueError, TypeError):
        return {'invalid': True}


def worker_manifest(repo):
    value = manifest(repo)
    worker = value['accounts']['m3-qs-worker']
    wanted = set(worker['subscriptions'])
    value['routes'] = [route for route in value['routes'] if route['id'] in wanted]
    value['accounts'] = {'m3-qs-worker': worker,
        'm3-qs-apiserver': {'owner': 'qs.mysql', 'publish': ['qs-evaluation-mysql'], 'subscriptions': []}}
    validate_v2(value)
    return value


def physical_receive_diagnostics(directory, document):
    """Bounded timing/aliases only; raw SDK payloads and identities stay private."""
    allowed = {'qs-survey-worker', 'qs-evaluation-mysql', 'qs-evaluation-mongo',
               'qs-task-normal', 'qs-task-transaction'}
    aliases = {r['physical_topic']: r['id'] for r in document['routes'] if r['id'] in allowed}
    paths = sorted(directory.glob('probe-*-client/rocketmq_client_go.log*'))
    events = []
    truncated = len(paths) > 4
    for path in paths[:4]:
        if path.is_symlink():
            truncated = True
            continue
        with path.open('rb') as stream:
            raw = stream.read(4 * 1024 * 1024 + 1)
        truncated |= len(raw) > 4 * 1024 * 1024
        active = None
        for line in raw[:4 * 1024 * 1024].decode(errors='replace').splitlines():
            parts = line.split('\t', 3)
            if len(parts) != 4 or parts[1] != 'DEBUG':
                continue
            try:
                at = datetime.fromisoformat(parts[0]).timestamp()
            except (ValueError, OverflowError):
                continue
            if not math.isfinite(at):
                continue
            message = parts[3]
            row = None
            if message.startswith('receiveMessage request:'):
                active = None
                found = [alias for physical, alias in aliases.items() if physical in message]
                if len(found) == 1:
                    active = found[0]
                    row = dict(at=at, kind='receive_start', input=active)
            elif message.startswith('receiveMessage response: status:') and active:
                code = re.search(r'\bcode:\s*(OK|MESSAGE_NOT_FOUND)\b', message)
                row = dict(at=at, kind='receive_status', input=active,
                           status={'OK': 'ok', 'MESSAGE_NOT_FOUND': 'empty'}.get(code[1] if code else '', 'other'))
            elif message.startswith('endTransaction request:'):
                # RPC observation, not a replacement for the original commit proof.
                row = dict(at=at, kind='transaction_end_rpc')
            if row is not None:
                if len(events) >= 256:
                    truncated = True
                    break
                events.append(row)
    events.sort(key=lambda row: row['at'])
    origin = events[0]['at'] if events else 0
    result = []
    for row in events:
        elapsed = round((row['at'] - origin) * 1000)
        if not 0 <= elapsed <= 86400000:
            truncated = True
            continue
        result.append(dict(ms=elapsed, **{key: value for key, value in row.items() if key != 'at'}))
    return dict(available=bool(result), truncated=bool(truncated), events=result,
                scope='private SDK RPC timing; no business success or per-input readiness claim')


def run_qs_worker_host(source, directory, broker, project, grpc_port, mysql_port, password, ca,
                       run, proof, native_runner, repo, private_log=None, *, rotation_candidate=False):
    source = source.resolve()
    if not (source / 'go.mod').is_file() or run(['git', 'status', '--porcelain'], cwd=source).stdout.strip():
        raise RuntimeError('exact clean QS worker source required')
    proof['source_sha'] = run(['git', 'rev-parse', 'HEAD'], cwd=source).stdout.strip()
    env = dict(os.environ, GOWORK='off', GOFLAGS='-mod=readonly')
    module = json.loads(run(['go', 'list', '-m', '-json', 'github.com/FangcunMount/reliable-messaging'], cwd=source, env=env).stdout)
    if rotation_candidate:
        from host_sdk_contract import validate_rotation_module
        validate_rotation_module(module)
        proof['sdk_adoption_scope'] = 'published Go v0.6.1; host adoption candidate'
    elif not stable_module_matches(module) and (module.get('Replace') or module.get('Version') != 'v0.5.0-rocketmq-tx.2' or not module.get('Sum')):
        raise RuntimeError('fixed published worker SDK without replace required')
    proof['sdk_module'] = {key: module.get(key) for key in ('Path', 'Version', 'Sum', 'GoModSum')}
    # Retain ALL canonical worker subscriptions; fixture producer only supplies
    # evaluation TX input. Full production-resource ACL proof is T21.
    document = worker_manifest(repo)
    accounts = {role: {'username': 'worker-native-' + secrets.token_hex(4), 'password': secrets.token_hex(32)}
                for role in document['accounts']}
    proof['provision'] = provision(broker, document, accounts)
    routes = directory / 'worker-runtime-routes.json'
    routes.write_text(json.dumps(document)); routes.chmod(0o600)
    paths = {}
    for role in accounts:
        credentials = directory / (role + '-worker-credentials.json')
        credentials.write_text(json.dumps(accounts[role])); credentials.chmod(0o600)
        config = {'endpoint': f'127.0.0.1:{grpc_port}', 'credentials_file': str(credentials),
                  'ca_file': str(ca), 'routes_file': str(routes), 'instance_id': 'worker-native',
                  'publish_enabled': role != 'm3-qs-worker'}
        if role == 'm3-qs-apiserver':
            config['transactions'] = {'qs.mysql': {'store_id': 'worker-native-mysql',
                                                  'writer_epoch': 'm3-1', 'route_revision': 'm3-1'}}
        path = directory / (role + '-worker-options.json')
        path.write_text(json.dumps(config)); path.chmod(0o600); paths[role] = path
    logs = directory / 'worker-native-client-logs'; logs.mkdir(mode=0o700)
    env.update({'QS_M3_FIXTURE_PROJECT': project,
                'QS_WORKER_RECEIVE_DIAGNOSTICS': '1',
                'QS_M3_WORKER_DSN': f'root:{password}@tcp(127.0.0.1:{mysql_port})/?parseTime=true',
                'QS_M3_WORKER_CONFIG': str(paths['m3-qs-worker']),
                'QS_M3_WORKER_PRODUCER_CONFIG': str(paths['m3-qs-apiserver']),
                'rocketmq.client.logRoot': str(logs), 'rocketmq.client.logLevel': 'error'})
    if native_runner is None:
        raise RuntimeError('owned native process-group runner required')
    result = native_runner(['go', 'test', '-p', '1', '-race', '-tags=integration,m3_worker_runtime',
                  '-count=1', '-timeout=5m', '-v', './internal/worker/process',
                  '-run', '^TestM3WorkerRocketMQRuntime$'], cwd=source, env=env, timeout=420, required=False)
    raw = result.stdout + result.stderr
    capture = directory / 'qs-worker-runtime-private.log'; capture.write_text(raw); capture.chmod(0o600)
    proof['private_output_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
    proof['exit_code'] = result.returncode
    proof['diagnostics'] = host_failure_summary(raw)
    proof['diagnostics']['worker_state'] = worker_failure_diagnostics(raw)
    try:
        proof['diagnostics']['physical_receive'] = physical_receive_diagnostics(directory, document)
    except OSError:
        proof['diagnostics']['physical_receive'] = {'available': False, 'read_failed': True}
    proof['diagnostics']['assertion_lines'] = sorted(set(int(n) for n in re.findall(r'rocketmq_native_integration_test\.go:(\d+)', raw)))[:32]
    if private_log is not None:
        retain_private_host_output(private_log, raw)
    if result.returncode:
        seed = next(r for r in document['routes'] if r['id'] == 'qs-evaluation-mysql')
        try:
            admin = Admin(broker)
            topic_output = admin.docker('java', '-Xms32m', '-Xmx128m', '-cp',
                '/opt/rocketmq/conf:/opt/rocketmq/lib/*', 'org.apache.rocketmq.tools.command.MQAdminStartup',
                'topicStatus', '-n', 'nameserver:9876', '-t', seed['physical_topic']).stdout
            if 'Exception' in topic_output or 'command failed' in topic_output:
                raise RuntimeError('owned topic offset query unavailable')
            queues = []
            for line in topic_output.splitlines():
                fields = line.split()
                if len(fields)>=4 and all(re.fullmatch(r'[0-9]{1,12}',v) for v in fields[1:4]):
                    queues.append({'queue':int(fields[1]),'min_offset':int(fields[2]),'max_offset':int(fields[3])})
            proof['diagnostics']['seed_topic_offsets'] = queues[:8]
            progress_output = admin.docker('java', '-Xms32m', '-Xmx128m', '-cp',
                '/opt/rocketmq/conf:/opt/rocketmq/lib/*', 'org.apache.rocketmq.tools.command.MQAdminStartup',
                'consumerProgress', '-n', 'nameserver:9876', '-g', seed['consumer_group'], '-t', seed['physical_topic']).stdout
            progress = []
            for line in progress_output.splitlines():
                fields = line.split()
                if len(fields)>=7 and fields[0] == seed['physical_topic'] and all(re.fullmatch(r'-?[0-9]{1,12}',v) for v in fields[2:7]):
                    progress.append(dict(zip(('queue','broker_offset','consumer_offset','diff','inflight'),map(int,fields[2:7]))))
            proof['diagnostics']['seed_consumer_progress'] = progress[:8]
        except RuntimeError:
            proof['diagnostics']['seed_topic_offsets_unavailable'] = True
        raise RuntimeError('actual worker runtime native acceptance failed; private output withheld')
    proof['native_receipt'] = parse_worker_receipt(result.stdout, proof['source_sha'])
    proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if not proof['source_clean_after']:
        raise RuntimeError('worker source changed during acceptance')
    proof['scope'] = SCOPE
