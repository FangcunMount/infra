"""Current deferred-consumer MySQL proof; no Broker/whole-worker claim."""
import hashlib
import json
import os
import re

from iam_acceptance import host_failure_summary, retain_private_host_output

CASES = frozenset((
    'explicit_schema_required', 'exact_wire_duplicate_and_legacy_refusal',
    'broken_first_link_rolls_back_new_physical_evidence',
    'real_expiry_new_claim_blocks_old_owner',
    'sql_lock_budget_does_not_grant_execution',
    'durable_eight_attempt_budget_and_one_manual_delivery',
    'real_child_kill_retains_attempt_and_frozen_wire',
))
SCOPE = 'original MySQL deferred consumption, real lease/lock/process boundaries; controlled callback failures'
HISTORY_CASES = frozenset(('active_subscriptions_exclude_history',
    'missing_history_does_not_spend_attempt', 'original_wire_and_transport_identity_retained',
    'completed_history_not_republished', 'historical_input_cannot_create_hold'))


def parse_history_receipt(output):
    rows = [json.loads(line.split('READABLE_DEFERRED_HISTORY_RECEIPT ', 1)[1])
            for line in output.splitlines() if 'READABLE_DEFERRED_HISTORY_RECEIPT {' in line]
    if (len(rows) != 1 or rows[0].get('passed') != len(HISTORY_CASES)
            or rows[0].get('failed') != 0 or rows[0].get('skipped') != 0
            or set(rows[0].get('cases', {})) != HISTORY_CASES
            or any(value is not True for value in rows[0]['cases'].values())
            or rows[0].get('broker_not_claimed') is not True
            or rows[0].get('owned_database_dropped') is not True
            or not re.search(r'--- PASS: TestReadableDeferredHistoryNative \(', output)
            or re.search(r'--- (?:FAIL|SKIP):|WARNING: DATA RACE', output)):
        raise RuntimeError('readable historical delivery receipt incomplete, failed or skipped')
    return rows[0]


def parse_deferred_receipt(output, expected_source):
    receipts = [json.loads(line.split('M3_QS_DEFERRED_MYSQL_RECEIPT ', 1)[1])
                for line in output.splitlines() if 'M3_QS_DEFERRED_MYSQL_RECEIPT {' in line]
    if len(receipts) != 1:
        raise RuntimeError('one exact deferred consumer receipt required')
    receipt = receipts[0]
    if (receipt.get('source_sha') != expected_source or not re.fullmatch(r'[0-9a-f]{40}', expected_source)
            or receipt.get('passed') != len(CASES) or receipt.get('failed') != 0
            or receipt.get('skipped') != 0 or set(receipt.get('cases', {})) != CASES
            or any(value is not True for value in receipt['cases'].values())
            or receipt.get('scope') != SCOPE
            or any(receipt.get(key) is not True for key in (
                'broker_not_claimed', 'whole_worker_not_claimed', 'system_login_not_claimed',
                'human_authorization_api_not_claimed', 'owned_databases_dropped', 'owned_child_reaped'))
            or not re.search(r'--- PASS: TestRocketMQDeferredNative \(', output)
            or re.search(r'--- (?:FAIL|SKIP):|WARNING: DATA RACE', output)):
        raise RuntimeError('deferred receipt wrong source, incomplete, failed, skipped or outside scope')
    return receipt


def run_qs_deferred_host(source, directory, project, mysql_port, password, run, proof, native_runner, private_log=None):
    source = source.resolve()
    if not (source / 'go.mod').is_file() or run(['git', 'status', '--porcelain'], cwd=source).stdout.strip():
        raise RuntimeError('exact clean QS deferred source required')
    proof['source_sha'] = run(['git', 'rev-parse', 'HEAD'], cwd=source).stdout.strip()
    env = dict(os.environ, GOWORK='off', GOFLAGS='-mod=readonly')
    module = json.loads(run(['go', 'list', '-m', '-json', 'github.com/FangcunMount/reliable-messaging'], cwd=source, env=env).stdout)
    if module.get('Replace') or not module.get('Version') or not module.get('Sum'):
        raise RuntimeError('published fixed SDK without replace required')
    proof['sdk_module'] = {key: module.get(key) for key in ('Path', 'Version', 'Sum', 'GoModSum')}
    history = os.environ.get('QS_READABLE_HISTORY_REQUIRED', '0')
    if history not in ('0', '1'):
        raise RuntimeError('explicit readable history profile required')
    if history == '1' and module['Version'] != 'v0.6.0-rc.1':
        raise RuntimeError('readable history requires the fixed published SDK candidate')
    env.update({'QS_M3_FIXTURE_PROJECT': project,
                'QS_M3_DEFERRED_DSN': f'root:{password}@tcp(127.0.0.1:{mysql_port})/?parseTime=true'})
    if native_runner is None:
        raise RuntimeError('owned native process-group runner required')
    pattern = ('^(TestRocketMQDeferredNative|TestReadableDeferredHistoryNative)$'
               if history == '1' else '^TestRocketMQDeferredNative$')
    result = native_runner(['go', 'test', '-p', '1', '-race', '-tags=integration,m3_deferred_consumer',
                  '-count=1', '-timeout=3m', '-v', './internal/worker/integration/messaging',
                  '-run', pattern], cwd=source, env=env, timeout=360, required=False)
    raw = result.stdout + result.stderr
    capture = directory / 'qs-deferred-host-private.log'
    capture.write_text(raw); capture.chmod(0o600)
    proof['private_output_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
    proof['exit_code'] = result.returncode
    proof['diagnostics'] = host_failure_summary(raw)
    proof['diagnostics']['assertion_lines'] = sorted(set(int(n) for n in re.findall(r'deferred_native_integration_test\.go:(\d+)', raw)))[:32]
    if private_log is not None:
        retain_private_host_output(private_log, raw)
    if result.returncode:
        raise RuntimeError('actual deferred MySQL acceptance failed (private output withheld)')
    proof['native_receipt'] = parse_deferred_receipt(result.stdout, proof['source_sha'])
    if history == '1':
        proof['legacy_native_receipt'] = proof['native_receipt']
        proof['readable_history_receipt'] = parse_history_receipt(result.stdout)
        cases = dict(proof['native_receipt']['cases'])
        cases.update({'readable_history_' + key: value
                      for key, value in proof['readable_history_receipt']['cases'].items()})
        proof['native_receipt'] = dict(passed=len(cases), failed=0, skipped=0, cases=cases,
            scope='original MySQL deferred delivery plus explicit passive readable history',
            broker_not_claimed=True, system_login_not_claimed=True)
    proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if not proof['source_clean_after']:
        raise RuntimeError('QS source changed during deferred acceptance')
    proof['scope'] = SCOPE
