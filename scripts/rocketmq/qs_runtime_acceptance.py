"""Default QS owners, original stores and real owned Broker restart/Checker."""
import hashlib
import json
import os
import re
import secrets

from iam_acceptance import host_failure_summary
from m3_resources import manifest
from provision_v2 import Admin, provision
from routes import validate_v2

CASES = frozenset((
    'explicit_original_schema_no_constructor_ddl', 'default_dual_owner_start_full_idle_topics',
    'frozen_protocol_inputs_before_roots', 'prepared_halves_hidden_before_original_roots',
    'original_mysql_and_mongo_facts_witness_atomic', 'real_inflight_close_retains_original_dependencies',
    'real_broker_sigkill_after_commit_before_final_rpc', 'local_committed_final_unknown_both_owners',
    'fresh_paused_instance_actual_broker_checker_commits', 'idempotent_observer_preserves_first_wire',
    'owner_budget_and_callback_observation', 'wrong_reference_unknown_without_changed_facts',
    'actual_shutdown_and_owned_cleanup'))
SCOPE = 'default QS dual-owner lifecycle, actual Broker restart and next-instance Checker; protocol fixture facts'


def runtime_manifest(repo):
    value = manifest(repo)
    mysql = dict(value['accounts']['m3-qs-apiserver'], subscriptions=[])
    document = dict(value['accounts']['m3-qs-mongo'])
    worker = {'publish': [], 'subscriptions': ['qs-evaluation-mysql', 'qs-evaluation-mongo']}
    wanted = set(mysql['publish']) | set(document['publish']) | set(worker['subscriptions'])
    value['routes'] = [r for r in value['routes'] if r['id'] in wanted]
    value['accounts'] = {'m3-qs-apiserver': mysql, 'm3-qs-mongo': document, 'm3-qs-worker': worker}
    validate_v2(value)
    return value


def parse_runtime_receipt(output, source):
    rows = [json.loads(line.split('M3_QS_DEFAULT_OWNER_RECEIPT ', 1)[1])
            for line in output.splitlines() if line.startswith('M3_QS_DEFAULT_OWNER_RECEIPT ')]
    if len(rows) != 1:
        raise RuntimeError('one exact default owner runtime receipt required')
    value = rows[0]
    observations = value.get('observed_callbacks', {})
    commits = value.get('new_checker_commits', [])
    if (not re.fullmatch('[0-9a-f]{40}', source) or value.get('source_sha') != source
            or value.get('scope') != SCOPE or value.get('passed') != len(CASES)
            or value.get('failed') != 0 or value.get('skipped') != 0
            or set(value.get('cases', {})) != CASES or any(v is not True for v in value['cases'].values())
            or value.get('local_executor_calls') != [1, 1]
            or value.get('new_half_prepared_results') != [0, 0]
            or type(value.get('close_wait_ms')) is not int or not 0 <= value['close_wait_ms'] <= 2000
            or type(value.get('mongo_database_callbacks')) is not int or value['mongo_database_callbacks'] < 1
            or len(commits) != 2 or any(type(n) is not int or n < 1 for n in commits)
            or set(observations) != {'running', 'queued'}
            or type(observations.get('running')) is not int or not 0 <= observations['running'] <= 4
            or type(observations.get('queued')) is not int or not 0 <= observations['queued'] <= 32
            or type(value.get('duplicate_deliveries')) is not int or value['duplicate_deliveries'] < 0
            or any(value.get(k) is not True for k in ('domain_api_provider_system_not_claimed',
                'producer_process_exit_not_claimed', 'owned_databases_dropped',
                'owned_runtimes_drained', 'same_broker_container_restarted'))
            or not re.search(r'--- PASS: TestM3DefaultOwnerRuntime \(', output)
            or re.search(r'--- (?:SKIP|FAIL):|WARNING: DATA RACE', output)):
        raise RuntimeError('default owner runtime proof wrong source, incomplete, failed, skipped or outside scope')
    return value


def run_qs_runtime_host(source, directory, broker, project, grpc_port, mysql_port, mongo_port,
                        password, ca, run, proof, native_runner, repo, read_parameters):
    source = source.resolve()
    if not (source/'go.mod').is_file() or run(['git', 'status', '--porcelain'], cwd=source).stdout.strip():
        raise RuntimeError('exact clean QS default runtime source required')
    proof['source_sha'] = run(['git', 'rev-parse', 'HEAD'], cwd=source).stdout.strip()
    env = dict(os.environ, GOWORK='off', GOFLAGS='-mod=readonly')
    module = json.loads(run(['go', 'list', '-m', '-json', 'github.com/FangcunMount/reliable-messaging'], cwd=source, env=env).stdout)
    if module.get('Replace') or module.get('Version') != 'v0.5.0-rocketmq-tx.2' or not module.get('Sum'):
        raise RuntimeError('fixed published QS SDK tx.2 without replacement required')
    proof['sdk_module'] = {k: module.get(k) for k in ('Path', 'Version', 'Sum', 'GoModSum')}
    document = runtime_manifest(repo)
    accounts = {role: {'username': 'runtime-' + secrets.token_hex(5), 'password': secrets.token_hex(32)}
                for role in document['accounts']}
    proof['provision'] = provision(broker, document, accounts)
    routes = directory/'qs-owner-runtime-routes.json'; routes.write_text(json.dumps(document)); routes.chmod(0o600)
    credentials = {}
    for role, value in accounts.items():
        path = directory/(role+'-runtime-credentials.json'); path.write_text(json.dumps(value)); path.chmod(0o600); credentials[role] = path
    base = {'endpoint': f'127.0.0.1:{grpc_port}', 'credentials_file': str(credentials['m3-qs-apiserver']),
            'ca_file': str(ca), 'routes_file': str(routes), 'instance_id': 'qs-original-runtime', 'publish_enabled': True,
            'transactions': {owner: {'credentials_file': str(credentials[role]), 'store_id': owner+'-original-runtime',
                                    'writer_epoch': 'm3-1', 'route_revision': 'm3-1'}
                             for owner, role in (('qs.mysql', 'm3-qs-apiserver'), ('qs.mongo', 'm3-qs-mongo'))}}
    opts = directory/'qs-owner-runtime-options.json'; opts.write_text(json.dumps({'provider': 'rocketmq', 'enabled': True, 'rocketmq': base})); opts.chmod(0o600)
    observe = dict(base, credentials_file=str(credentials['m3-qs-worker']), publish_enabled=False, transactions={})
    observer = directory/'qs-owner-runtime-observer.json'; observer.write_text(json.dumps({'provider': 'rocketmq', 'enabled': True, 'rocketmq': observe})); observer.chmod(0o600)
    logs = directory/'qs-owner-runtime-client-logs'; logs.mkdir(mode=0o700)
    env.update(QS_M3_FIXTURE_PROJECT=project, QS_M3_HOST_BROKER=broker,
        QS_M3_HOST_DSN=f'root:{password}@tcp(127.0.0.1:{mysql_port})/?parseTime=true',
        QS_M3_HOST_MONGO_URI=f'mongodb://127.0.0.1:{mongo_port}/?replicaSet=sdk-proof&directConnection=true',
        QS_M3_HOST_OPTIONS=str(opts), QS_M3_HOST_OBSERVER_OPTIONS=str(observer))
    env.update({'rocketmq.client.logRoot': str(logs), 'rocketmq.client.logLevel': 'error'})
    if native_runner is None:
        raise RuntimeError('owned native process group runner required')
    admin = Admin(broker)
    proof['parameters_before'] = read_parameters(admin('getBrokerConfig'))
    try:
        # Keep old owners from winning a backcheck before their connections die.
        # Both original commits complete before the real Broker SIGKILL. This
        # fixture-only window is read back, recorded and restored afterward.
        admin('updateBrokerConfig', '-k', 'transactionTimeOut', '-v', '60000')
        proof['parameters_before_native'] = read_parameters(admin('getBrokerConfig'))
        if proof['parameters_before_native']['transactionTimeOut'] != 60000:
            raise RuntimeError('owned first-check window not effective')
        result = native_runner(['go', 'test', '-race', '-p', '1', '-tags=integration,m3_host_runtime', '-count=1',
                    '-timeout=5m', '-v', './internal/apiserver/container', '-run', '^TestM3DefaultOwnerRuntime$'],
                    cwd=source, env=env, timeout=480, required=False)
        output = result.stdout+result.stderr
        private = directory/'qs-owner-runtime-private.log'; private.write_text(output); private.chmod(0o600)
        proof['native_output_sha256'] = hashlib.sha256(output.encode()).hexdigest()
        proof['native_exit_code'] = result.returncode
        proof['diagnostics'] = host_failure_summary(output)
        proof['diagnostics']['assertion_lines'] = sorted(set(map(int, re.findall(r'owner_runtime_native_integration_test\.go:(\d+)', output))))[:32]
        if result.returncode:
            raise RuntimeError('actual default QS owners failed; private output withheld')
        proof['native_receipt'] = parse_runtime_receipt(output, proof['source_sha'])
        proof['parameters_after_restart'] = read_parameters(admin('getBrokerConfig'))
    finally:
        # Failure may leave only this owned Broker stopped. Do not target any
        # other project or mask a failed test with a successful cleanup claim.
        try:
            admin('updateBrokerConfig', '-k', 'transactionTimeOut', '-v', str(proof['parameters_before']['transactionTimeOut']))
            proof['parameters_restored'] = read_parameters(admin('getBrokerConfig'))
        except RuntimeError:
            proof['parameter_restore_unavailable'] = True
    if proof.get('parameter_restore_unavailable') or proof['parameters_restored'] != proof['parameters_before']:
        raise RuntimeError('owned runtime parameters not restored')
    proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if not proof['source_clean_after']:
        raise RuntimeError('QS source changed during native default owner proof')
    proof['scope'] = SCOPE
