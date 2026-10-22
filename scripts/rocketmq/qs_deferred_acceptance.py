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
    env.update({'QS_M3_FIXTURE_PROJECT': project,
                'QS_M3_DEFERRED_DSN': f'root:{password}@tcp(127.0.0.1:{mysql_port})/?parseTime=true'})
    if native_runner is None:
        raise RuntimeError('owned native process-group runner required')
    result = native_runner(['go', 'test', '-p', '1', '-race', '-tags=integration,m3_deferred_consumer',
                  '-count=1', '-timeout=3m', '-v', './internal/worker/integration/messaging',
                  '-run', '^TestRocketMQDeferredNative$'], cwd=source, env=env, timeout=360, required=False)
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
    proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if not proof['source_clean_after']:
        raise RuntimeError('QS source changed during deferred acceptance')
    proof['scope'] = SCOPE
