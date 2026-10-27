"""QS answer transaction host proof, only inside the owned infra fixture."""
import hashlib
import json
import os
import re
import secrets

from provision_v2 import provision
from readable_host_acceptance import readable_manifest, record_readable_fixture
from routes import consumer_group_v2, physical_topic_v2, validate_v2
from iam_acceptance import host_failure_summary, retain_private_host_output


CASES = frozenset((
    'half_does_not_accept_business', 'original_root_fact_and_witness_and_wire',
    'duplicate_does_not_execute', 'conflicting_input_rejected',
    'committed_ack_discard_exact_recovery', 'root_abort_no_accepted_fact_or_witness',
    'native_callback_reentry', 'no_new_publish_outbox', 'closed_admission_no_business',
    'full_reference_required_for_acceptance', 'nested_preparation_rejected',
    'collection_202_exact_root', 'collection_unknown_witness_no202',
    'concurrent_reservation_one_execution', 'new_instance_exact_accepted_result',
    'mixed_protocol_marker_rejected'))


def answer_manifest(*, readable=False):
    topic, subscription = 'qs.evaluation.lifecycle', 'qs-m3-answer-observer'
    route = {'id': 'qs-answer-native', 'topic': topic, 'subscription': subscription,
             'message_type': 'TRANSACTION', 'owner': 'qs.mongo', 'route_revision': 'm3-1',
             'physical_topic': physical_topic_v2(topic, 'TRANSACTION', 'qs.mongo', 'm3-1'),
             'consumer_group': consumer_group_v2(topic, subscription)}
    manifest = {'version': 2, 'routes': [route],
                'topic_options': {'read_queue_nums': 1, 'write_queue_nums': 1, 'perm': 6},
                'group_options': {'retry_queue_nums': 8},
                'accounts': {'qs-answer-producer': {'owner': 'qs.mongo', 'publish': [route['id']], 'subscriptions': []},
                             'qs-answer-observer': {'publish': [], 'subscriptions': [route['id']]}}}
    validate_v2(manifest)
    return readable_manifest(manifest) if readable else manifest


def parse_answer_receipt(output):
    receipts = [json.loads(line.split('M3_QS_ANSWER_RECEIPT ', 1)[1])
                for line in output.splitlines() if 'M3_QS_ANSWER_RECEIPT {' in line]
    if (len(receipts) != 1 or receipts[0].get('passed') != len(CASES)
            or receipts[0].get('failed') != 0 or receipts[0].get('skipped') != 0
            or set(receipts[0].get('cases', {})) != CASES
            or any(value is not True for value in receipts[0]['cases'].values())
            or receipts[0].get('root_ack_discard_is_client_level') is not True
            or receipts[0].get('mongo_callback_failpoint') is not True
            or receipts[0].get('upstream_rpc') != 'actual_protobuf_service_over_bufconn'
            or receipts[0].get('system_login_not_claimed') is not True
            or not re.search(r'--- PASS: TestM3AnswerSubmissionBrokerHost \(', output)
            or re.search(r'--- (?:SKIP|FAIL):|WARNING: DATA RACE', output)):
        raise RuntimeError('QS native answer receipt absent, incomplete, failed or skipped')
    return receipts[0]


def answer_failure_signals(raw):
    # Only authored fixed labels are exportable; never forward captured values.
    markers = {
        'root_wait_timeout': 'half preparation did not reach host',
        'returned_before_root': 'submission returned before original root',
        'admission_closed': 'transaction admission closed',
        'sender_admission_unavailable': 'transaction sender admission unavailable',
        'invalid_plan': 'invalid frozen transaction plan',
        'binding_mismatch': 'transaction binding mismatch',
        'all_halves_not_prepared': 'all half messages must be confirmed before local execution',
        'half_audit_failed': 'half_audit_failed',
        'business_binding_differs': 'frozen submission business binding differs',
        'input_conflict': 'transaction idempotency key has different business input',
        'deadline': 'context deadline exceeded',
        'unavailable': 'code = Unavailable',
        'permission_denied': 'code = PermissionDenied',
        'unauthenticated': 'code = Unauthenticated',
    }
    return sorted(label for label, marker in markers.items() if marker in raw)


def run_qs_answer_host(source, directory, broker, project, grpc_port, mongo_port, ca, run, proof, private_log=None, *, faults=False, native_runner=None, proxy_start=None, readable=False):
    source = source.resolve()
    if not (source / 'go.mod').is_file() or run(['git', 'status', '--porcelain'], cwd=source).stdout.strip():
        raise RuntimeError('exact clean QS host source required')
    proof['source_sha'] = run(['git', 'rev-parse', 'HEAD'], cwd=source).stdout.strip()
    env = dict(os.environ, GOWORK='off', GOFLAGS='-mod=readonly')
    module = json.loads(run(['go', 'list', '-m', '-json', 'github.com/FangcunMount/reliable-messaging'], cwd=source, env=env).stdout)
    if module.get('Replace') or not module.get('Version') or not module.get('Sum'):
        raise RuntimeError('fixed published SDK without local replace required')
    proof['sdk_module'] = {key: module.get(key) for key in ('Path', 'Version', 'Sum', 'GoModSum')}
    if readable and faults:
        raise RuntimeError('readable host uses a separate non-fault fixture')
    if faults and module.get('Version') != 'v0.5.0-rocketmq-tx.2':
        raise RuntimeError('original AnswerSheet faults require fixed SDK tx.2')
    manifest = answer_manifest(readable=readable)
    if readable:
        record_readable_fixture(module, manifest, proof)
    accounts = {role: {'username': 'm3-' + role + '-' + secrets.token_hex(4), 'password': secrets.token_hex(32)}
                for role in manifest['accounts']}
    proof['provision'] = provision(broker, manifest, accounts)
    routes = directory / 'qs-answer-routes.json'
    routes.write_text(json.dumps(manifest)); routes.chmod(0o600)
    paths = {}
    for role in accounts:
        credentials = directory / (role + '-credentials.json')
        credentials.write_text(json.dumps(accounts[role])); credentials.chmod(0o600)
        config = {'provider': 'rocketmq', 'enabled': True,
                  'rocketmq': {'endpoint': f'127.0.0.1:{grpc_port}', 'credentials_file': str(credentials),
                               'ca_file': str(ca), 'routes_file': str(routes),
                               'instance_id': 'qs-m3-answer-fixture', 'publish_enabled': True}}
        if role == 'qs-answer-producer':
            config['rocketmq']['transactions'] = {'qs.mongo': {'store_id': 'qs-native-mongo-primary',
                                                              'writer_epoch': 'm3-1', 'route_revision': 'm3-1'}}
        path = directory / (role + '-options.json')
        path.write_text(json.dumps(config)); path.chmod(0o600); paths[role] = path
    logs = directory / 'qs-answer-private-client-logs'; logs.mkdir(mode=0o700)
    env.update({'QS_M3_FIXTURE_PROJECT': project,
                'QS_M3_MONGO_URI': f'mongodb://127.0.0.1:{mongo_port}/?replicaSet=sdk-proof&directConnection=true',
                'QS_M3_PRODUCER_CONFIG': str(paths['qs-answer-producer']),
                'QS_M3_OBSERVER_CONFIG': str(paths['qs-answer-observer']),
                'rocketmq.client.logRoot': str(logs), 'rocketmq.client.logLevel': 'error'})
    if faults:
        from qs_answer_fault_acceptance import run_profile
        run_profile(source, directory, env, run, proof, native_runner, proxy_start)
        return
    result = run(['go', 'test', '-race', '-tags=integration,m3_answersheet_integration', '-count=1', '-timeout=3m', '-v',
                  './internal/apiserver/container/internal/transaction', '-run', '^TestM3AnswerSubmissionBrokerHost$'],
                 cwd=source, env=env, timeout=240, required=False)
    raw = result.stdout + result.stderr
    capture = directory / 'qs-answer-host-private.log'; capture.write_text(raw); capture.chmod(0o600)
    proof['private_output_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
    proof['exit_code'] = result.returncode
    proof['diagnostics'] = host_failure_summary(raw)
    proof['diagnostics']['signals'] = answer_failure_signals(raw)
    proof['diagnostics']['assertion_lines'] = sorted(set(int(n) for n in re.findall(r'm3_answersheet_broker_integration_test\.go:(\d+)', raw)))[:32]
    if private_log is not None:
        retain_private_host_output(private_log, raw)
    if result.returncode:
        raise RuntimeError('actual QS answer host acceptance failed (private output withheld)')
    proof['native_receipt'] = parse_answer_receipt(result.stdout)
    proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if not proof['source_clean_after']:
        raise RuntimeError('QS source changed during native acceptance')
    proof['scope'] = ('real RocketMQ/original Mongo host, Survey wiring, Collection REST and actual protobuf service over bufconn; '
                      'IAM identity fixture and Collection-to-protobuf mapping are test ports; '
                      'client ACK discard is not packet loss; fresh instance is not a SIGKILL proof; not production/system acceptance')
