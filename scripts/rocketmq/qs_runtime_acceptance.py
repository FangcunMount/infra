"""Default QS owners, original stores and real owned Broker restart/Checker."""
import hashlib
import json
import os
import re
import secrets

from host_sdk_contract import stable_module_matches
from iam_acceptance import host_failure_summary, retain_private_host_output
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
NATIVE_LIMIT_CASES = frozenset((
    'live_configured_open_before_private_native_ingest',
    'actual_sys_index_recorded_idempotently_on_both_original_primaries',
    'live_sampler_seals_reserve_execute_plain_open_and_review',
    'new_configured_open_instance_retains_durable_deny_before_registration',
    'real_original_checker_commit_rpc_and_positive_audit_while_native_blocked',
    'first_wire_facts_and_single_executor_preserved_without_new_half',
    'no_automatic_or_unaudited_governance_resolution',
    'actual_sampler_sdk_shutdown_joined_original_pools_owned_cleanup'))
PROTECTION_CASES = frozenset((
    'exact_owned_audit_timestamp_fixture_only',
    'initial_authoritative_observation_latches_before_registration',
    'plain_admission_cannot_bypass_latch',
    'real_broker_recovery_rpc_then_positive_audit_clears_gap',
    'healthy_sampling_does_not_unlatch',
    'generation_bound_named_review_then_explicit_admission',
    'duplicate_plan_no_new_half_or_business_executor',
    'actual_sampler_and_sdk_shutdown_joined'))
PROTECTION_MODULE = ('v0.5.0-rocketmq-tx.4', 'h1:PflI1oWRjU4RFKvpi8WE/8ICI/1IUp8q8EOsbW1DXCI=',
                     'h1:GPiWG8ZsX4pvIZ6QyvLnBVO5iCqNhvsnKwFcg0ftC7I=')


def validate_module(module, protection=False):
    if stable_module_matches(module):
        return
    if 'Replace' in module or module.get('Path') != 'github.com/FangcunMount/reliable-messaging':
        raise RuntimeError('fixed published QS SDK without replacement required')
    if protection:
        if tuple(module.get(k) for k in ('Version', 'Sum', 'GoModSum')) != PROTECTION_MODULE:
            raise RuntimeError('protocol protection requires exact published SDK tx.4 and verified module sums')
    elif module.get('Version') != 'v0.5.0-rocketmq-tx.2' or not module.get('Sum'):
        raise RuntimeError('baseline default owner profile requires fixed SDK tx.2')


def parse_protection_receipt(output, source):
    # The base receipt separately proves real business roots/first wire/call counts.
    parse_runtime_receipt(output, source)
    rows = [json.loads(line.split('M3_QS_PROTOCOL_PROTECTION_RECEIPT ', 1)[1])
            for line in output.splitlines() if line.startswith('M3_QS_PROTOCOL_PROTECTION_RECEIPT ')]
    if len(rows) != 1:
        raise RuntimeError('one exact protocol protection receipt required')
    value = rows[0]
    fields = {'source_sha', 'passed', 'failed', 'skipped', 'cases', 'fixture_timestamp_aging_seconds',
              'real_ten_minute_elapsed_not_claimed', 'owner_count', 'domain_api_provider_system_not_claimed',
              'owned_databases_dropped'}
    if (set(value) != fields or value['source_sha'] != source
            or type(value['passed']) is not int or value['passed'] != len(PROTECTION_CASES)
            or type(value['failed']) is not int or value['failed'] != 0
            or type(value['skipped']) is not int or value['skipped'] != 0
            or set(value['cases']) != PROTECTION_CASES or any(v is not True for v in value['cases'].values())
            or type(value['owner_count']) is not int or value['owner_count'] != 2
            or type(value['fixture_timestamp_aging_seconds']) is not int or value['fixture_timestamp_aging_seconds'] != 600
            or any(value[k] is not True for k in ('real_ten_minute_elapsed_not_claimed',
                'domain_api_provider_system_not_claimed', 'owned_databases_dropped'))):
        raise RuntimeError('protocol protection proof incomplete, wrong source or outside fixed scope')
    return value

def parse_native_limit_receipt(output, source):
    parse_runtime_receipt(output, source)
    rows = [json.loads(line.split('M3_QS_NATIVE_LIMIT_RECEIPT ', 1)[1])
            for line in output.splitlines() if line.startswith('M3_QS_NATIVE_LIMIT_RECEIPT ')]
    if len(rows) != 1:
        raise RuntimeError('one exact native limit host receipt required')
    value = rows[0]
    flags = {'real_sys_index_required', 'timestamp_aging_not_used', 'governance_resolution_not_claimed',
             'domain_api_provider_system_not_claimed', 'owned_databases_dropped'}
    if (set(value) != flags | {'source_sha', 'passed', 'failed', 'skipped', 'cases', 'owner_count'}
            or value['source_sha'] != source
            or any(value[k] is not True for k in flags)
            or any(type(value[k]) is not int for k in ('passed', 'failed', 'skipped', 'owner_count'))
            or (value['passed'], value['failed'], value['skipped'], value['owner_count']) != (8, 0, 0, 2)
            or not isinstance(value['cases'], dict) or set(value['cases']) != NATIVE_LIMIT_CASES
            or any(v is not True for v in value['cases'].values())):
        raise RuntimeError('native-limit host evidence incomplete or wrong scope')
    return value


SCOPE = 'default QS dual-owner lifecycle, actual Broker restart and next-instance Checker; protocol fixture facts'


def runtime_manifest(repo, recovery=False):
    value = manifest(repo)
    mysql = dict(value['accounts']['m3-qs-apiserver'], subscriptions=[])
    document = dict(value['accounts']['m3-qs-mongo'])
    worker = {'publish': [], 'subscriptions': ['qs-evaluation-mysql', 'qs-evaluation-mongo']}
    if recovery:
        from routes import consumer_group_v2
        worker = dict(value['accounts']['m3-qs-worker'])
        hot = dict(next(r for r in value['routes'] if r['id'] == 'qs-evaluation-mongo'))
        hot.update(id='qs-recovery-hotrank', subscription='qs-apiserver-modelcatalog-hot-rank-v1',
                   consumer_group=consumer_group_v2(hot['topic'], 'qs-apiserver-modelcatalog-hot-rank-v1'))
        value['routes'].append(hot)
        worker['subscriptions'] = list(worker['subscriptions']) + [hot['id']]
    wanted = set(mysql['publish']) | set(document['publish']) | set(worker['subscriptions'])
    value['routes'] = [r for r in value['routes'] if r['id'] in wanted]
    value['accounts'] = {'m3-qs-apiserver': mysql, 'm3-qs-mongo': document, 'm3-qs-worker': worker}
    validate_v2(value)
    if recovery:
        from readable_host_acceptance import readable_manifest
        return readable_manifest(value)
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



def runtime_diagnostics(output):
    """Only schema-bound synthetic phases/counters; never retain error text."""
    result = []
    for line in output.splitlines():
        if not line.startswith('M3_QS_OWNER_DIAGNOSTIC '):
            continue
        try:
            value = json.loads(line.removeprefix('M3_QS_OWNER_DIAGNOSTIC '))
        except ValueError:
            raise RuntimeError('invalid fixed owner diagnostic') from None
        fields = {'stage', 'owner_index', 'local', 'error', 'root_phases', 'lease_remaining_ms', 'elapsed_ms'}
        if (not isinstance(value, dict) or set(value) != fields
                or value['stage'] not in {'local_entered', 'local_committed', 'before_observer_close', 'after_observer_close', 'next_owner_start'}
                or type(value['owner_index']) is not int or value['owner_index'] not in (-1, 0, 1)
                or value['local'] not in {'not_started', 'committed', 'aborted', 'unknown'}
                or not isinstance(value['error'], dict) or set(value['error']) != {'kind', 'code'}
                or value['error']['kind'] not in {'none', 'deadline', 'canceled', 'stale_execution', 'binding', 'transaction_required', 'other', 'mysql', 'mongo', 'metrics_registration', 'protocol_protection', 'host_admission'}
                or type(value['error']['code']) is not int or not 0 <= value['error']['code'] <= 1000000000
                or not isinstance(value['root_phases'], list) or len(value['root_phases']) != 2
                or any(type(n) is not int or not 0 <= n <= 5 for n in value['root_phases'])
                or not isinstance(value['lease_remaining_ms'], list) or len(value['lease_remaining_ms']) != 2
                or any(type(n) is not int or not -86400000 <= n <= 86400000 for n in value['lease_remaining_ms'])
                or type(value['elapsed_ms']) is not int or not 0 <= value['elapsed_ms'] <= 600000
                or len(result) >= 16):
            raise RuntimeError('owner diagnostic outside fixed safe schema')
        result.append(value)
    return result


def run_qs_runtime_host(source, directory, broker, project, grpc_port, mysql_port, mongo_port,
                        password, ca, run, proof, native_runner, repo, read_parameters, protection=False, native_limit=False, recovery=False, redis_port=None, recovery_private_log=None):
    source = source.resolve()
    if not (source/'go.mod').is_file() or run(['git', 'status', '--porcelain'], cwd=source).stdout.strip():
        raise RuntimeError('exact clean QS default runtime source required')
    proof['source_sha'] = run(['git', 'rev-parse', 'HEAD'], cwd=source).stdout.strip()
    env = dict(os.environ, GOWORK='off', GOFLAGS='-mod=readonly')
    module = json.loads(run(['go', 'list', '-m', '-json', 'github.com/FangcunMount/reliable-messaging'], cwd=source, env=env).stdout)
    if recovery:
        from qs_recovery_acceptance import validate_recovery_module
        validate_recovery_module(module)
    else:
        validate_module(module, protection or native_limit)
    proof['sdk_module'] = {k: module.get(k) for k in ('Path', 'Version', 'Sum', 'GoModSum')}
    document = runtime_manifest(repo, recovery=recovery)
    accounts = {role: {'username': 'runtime-' + secrets.token_hex(5), 'password': secrets.token_hex(32)}
                for role in document['accounts']}
    proof['provision'] = provision(broker, document, accounts)
    if recovery:
        proof['manifest_version'] = document['version']
        proof['naming_scheme'] = 'readable-v1'
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
    if recovery:
        if not redis_port or protection or native_limit:
            raise RuntimeError('standalone recovery requires owned Redis')
        tools = {}
        for name, package in (('hotrank-day-rebuild', './scripts/oneoff/hotrank_day_rebuild'),
                              ('answersheet-gap-recover', './scripts/oneoff/answersheet_gap_recover')):
            path = directory/name
            run(['go', 'build', '-o', str(path), package], cwd=source, env=env, timeout=240)
            tools[name] = str(path)
        env.update(QS_M3_RECOVERY_REDIS=f'127.0.0.1:{redis_port}',
            QS_M3_RECOVERY_CERT=str(ca), QS_M3_RECOVERY_KEY=str(directory/'fault-server.key'),
            QS_M3_RECOVERY_HOTRANK=tools['hotrank-day-rebuild'],
            QS_M3_RECOVERY_ANSWERSHEET=tools['answersheet-gap-recover'])
    if protection:
        env['QS_M3_VERIFY_PROTOCOL_PROTECTION'] = '1'
    else:
        env.pop('QS_M3_VERIFY_PROTOCOL_PROTECTION', None)
    env.update({'rocketmq.client.logRoot': str(logs), 'rocketmq.client.logLevel': 'error'})
    if native_limit:
        from native_limit_acceptance import create_native_limit
        proof['native_fault'] = {}
        # Generate/export the actual poison BEFORE any host owner registration;
        # its deliberately absent business reference must not be mistaken for a
        # production owner's invalid-check fault.
        route = next(r for r in document['routes'] if r['owner'] == 'qs.mysql' and r['message_type'] == 'TRANSACTION')
        audit, digest = create_native_limit(repo, directory, broker, project, grpc_port, ca,
            accounts['m3-qs-apiserver'], route, run, native_runner, read_parameters, proof['native_fault'], mysql_port, password)
        env.update(QS_M3_VERIFY_NATIVE_LIMIT='1', QS_M3_NATIVE_LIMIT_AUDIT=str(audit), QS_M3_NATIVE_LIMIT_SHA256=digest)
    else:
        for key in ('QS_M3_VERIFY_NATIVE_LIMIT', 'QS_M3_NATIVE_LIMIT_AUDIT', 'QS_M3_NATIVE_LIMIT_SHA256'):
            env.pop(key, None)

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
        package, test, budget = ('./internal/apiserver/integration/runtimeclosure', '^TestM3HostRetirementRecovery$', '10m') if recovery else ('./internal/apiserver/container', '^TestM3DefaultOwnerRuntime$', '5m')
        linker = ['-ldflags', '-X github.com/FangcunMount/qs-server/pkg/version.GitCommit='+proof['source_sha']] if recovery else []
        result = native_runner(['go', 'test', '-race', '-p', '1', '-tags=integration,m3_host_runtime', '-count=1'] + linker + [
                    '-timeout='+budget, '-v', package, '-run', test],
                    cwd=source, env=env, timeout=720 if recovery else 480, required=False)
        output = result.stdout+result.stderr
        private = directory/'qs-owner-runtime-private.log'; private.write_text(output); private.chmod(0o600)
        if recovery_private_log is not None:
            retain_private_host_output(recovery_private_log, output)
        proof['native_output_sha256'] = hashlib.sha256(output.encode()).hexdigest()
        proof['native_exit_code'] = result.returncode
        proof['diagnostics'] = host_failure_summary(output)
        proof['diagnostics']['assertion_lines'] = sorted(set(map(int, re.findall(r'(?:owner_runtime_native|rocketmq_recovery_m3c)_integration_test\.go:(\d+)', output))))[:32]
        proof['diagnostics']['owner_runtime'] = runtime_diagnostics(output)
        if result.returncode:
            raise RuntimeError('actual default QS owners failed; private output withheld')
        if recovery:
            from qs_recovery_acceptance import parse_recovery_receipt
            proof['native_receipt'] = parse_recovery_receipt(output, proof['source_sha'])
        else:
            proof['native_receipt'] = parse_runtime_receipt(output, proof['source_sha'])
        if protection:
            proof['protection_receipt'] = parse_protection_receipt(output, proof['source_sha'])
        if native_limit:
            proof['native_limit_receipt'] = parse_native_limit_receipt(output, proof['source_sha'])
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
    proof['scope'] = ('host retirement recovery; original business services, owned RocketMQ/MySQL/Mongo/Redis and actual Worker process restart; controlled IAM/provider, no production/system login' if recovery else SCOPE)
