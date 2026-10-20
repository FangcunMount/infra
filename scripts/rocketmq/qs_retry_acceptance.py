"""Future authorization storage proof; does not claim due dispatch or Broker effects."""
import hashlib
import json
import os
import re

from iam_acceptance import host_failure_summary, retain_private_host_output

COMMON = frozenset(('constructor_no_ddl', 'schema_missing_rejected', 'original_root_rollback_atomic',
                    'original_root_commit_atomic', 'due_index_not_early', 'future_authorization_no_half_or_outbox'))
CASES = {'mysql': COMMON | {'duplicate_first_wire_deadline'},
         'mongo': COMMON | {'expired_session_rejected'}}


def parse_retry_receipts(output):
    receipts = [json.loads(line.split('M3_QS_RETRY_STORE_RECEIPT ', 1)[1])
                for line in output.splitlines() if 'M3_QS_RETRY_STORE_RECEIPT {' in line]
    if (len(receipts) != 2 or {r.get('backend') for r in receipts} != set(CASES)
            or re.search(r'--- (?:SKIP|FAIL):|WARNING: DATA RACE', output)):
        raise RuntimeError('QS retry store receipts absent, duplicated, failed or skipped')
    for receipt in receipts:
        backend = receipt['backend']
        name = 'TestM3Retry' + ('MySQL' if backend == 'mysql' else 'Mongo') + 'Store'
        if (receipt.get('passed') != len(CASES[backend]) or receipt.get('failed') != 0
                or receipt.get('skipped') != 0 or set(receipt.get('cases', {})) != CASES[backend]
                or any(value is not True for value in receipt['cases'].values())
                or receipt.get('scope') != 'original_run_and_future_plan_storage_only'
                or receipt.get('broker_dispatch_not_claimed') is not True
                or receipt.get('system_login_not_claimed') is not True
                or not re.search(r'--- PASS: ' + name + r' \(', output)):
            raise RuntimeError('QS retry store receipt incomplete or outside verified scope')
    return {r['backend']: r for r in receipts}


def run_qs_retry_store_host(source, directory, project, mysql_port, mongo_port, password, run, proof, private_log=None):
    source = source.resolve()
    if not (source / 'go.mod').is_file() or run(['git', 'status', '--porcelain'], cwd=source).stdout.strip():
        raise RuntimeError('exact clean QS host source required')
    proof['source_sha'] = run(['git', 'rev-parse', 'HEAD'], cwd=source).stdout.strip()
    env = dict(os.environ, GOWORK='off', GOFLAGS='-mod=readonly')
    module = json.loads(run(['go', 'list', '-m', '-json', 'github.com/FangcunMount/reliable-messaging'], cwd=source, env=env).stdout)
    if module.get('Replace') or not module.get('Version') or not module.get('Sum'):
        raise RuntimeError('fixed published SDK without local replace required')
    proof['sdk_module'] = {key: module.get(key) for key in ('Path', 'Version', 'Sum', 'GoModSum')}
    env.update({'QS_M3_FIXTURE_PROJECT': project,
                'QS_M3_RETRY_DSN': f'root:{password}@tcp(127.0.0.1:{mysql_port})/?parseTime=true',
                'QS_M3_MONGO_URI': f'mongodb://127.0.0.1:{mongo_port}/?replicaSet=sdk-proof&directConnection=true'})
    result = run(['go', 'test', '-p', '1', '-race', '-tags=integration,m3_retry_store', '-count=1',
                  '-timeout=4m', '-v', './internal/apiserver/container/internal/transaction',
                  '-run', '^TestM3Retry(MySQL|Mongo)Store$'], cwd=source, env=env, timeout=420, required=False)
    raw = result.stdout + result.stderr
    capture = directory / 'qs-retry-store-host-private.log'; capture.write_text(raw); capture.chmod(0o600)
    proof['private_output_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
    proof['exit_code'] = result.returncode
    proof['diagnostics'] = host_failure_summary(raw)
    proof['diagnostics']['assertion_lines'] = sorted(set(int(n) for n in re.findall(r'm3_retry_store_integration_test\.go:(\d+)', raw)))[:32]
    if private_log is not None:
        retain_private_host_output(private_log, raw)
    if result.returncode:
        raise RuntimeError('actual QS retry storage acceptance failed (private output withheld)')
    proof['native_receipts'] = parse_retry_receipts(result.stdout)
    proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if not proof['source_clean_after']:
        raise RuntimeError('QS source changed during native acceptance')
    proof['scope'] = 'original MySQL/Mongo Run and future schedule atomicity only; no due dispatcher, Broker, system or production claim'
