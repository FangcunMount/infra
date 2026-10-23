"""Future authorization storage proof; does not claim due dispatch or Broker effects."""
import hashlib
import json
import os
import re

from iam_acceptance import host_failure_summary, retain_private_host_output

COMMON = frozenset(('constructor_no_ddl', 'schema_missing_rejected', 'original_root_rollback_atomic',
                    'original_root_commit_atomic', 'due_index_not_early', 'future_authorization_no_half_or_outbox'))
GOVERNED = frozenset(('governed_manual_original_root', 'governed_force_original_root',
                      'governed_root_rollback_atomic', 'governed_commit_reply_discard_recovered',
                      'governed_first_plan_and_authorization_reused', 'governed_changed_input_conflict',
                      'governed_wrong_scope_rejected', 'governed_no_outbox_or_business_attempt'))
HANDOFF = frozenset(('legacy_transfer_root_rollback_atomic', 'legacy_transfer_exact_first_wire_and_due',
                     'legacy_transfer_repeat_keeps_single_owner', 'legacy_transfer_attempted_or_due_refused',
                     'legacy_replay_cannot_reauthorize_transferred', 'legacy_old_relay_cannot_claim_transferred',
                     'legacy_transferred_status_not_pending'))
CASES = {'mysql': COMMON | {'duplicate_first_wire_deadline'} | GOVERNED | HANDOFF,
         'mongo': COMMON | {'expired_session_rejected'} | GOVERNED | HANDOFF}
CLI_CASES = frozenset(('offline_cli_exact_source_original_primary',
                       'offline_cli_default_without_database_binding',
                       'offline_cli_wrong_binding_and_digest_refused',
                       'offline_cli_first_transfer_and_same_plan_idempotence',
                       'offline_cli_private_receipt_preserved',
                       'offline_cli_does_not_authorize_cutover',
                       'offline_cli_no_new_tables_or_collections',
                       'offline_cli_no_sdk_transaction_rows',
                       'offline_inventory_pending_blocks_exit',
                       'offline_inventory_unreviewed_held_blocks_exit',
                       'offline_inventory_exact_pairs_read_only_accounted',
                       'offline_inventory_missing_ledger_not_empty'))


def parse_retry_receipts(output, *, handoff_cli=False):
    if type(handoff_cli) is not bool:
        raise RuntimeError('exact boolean offline CLI profile required')
    receipts = [json.loads(line.split('M3_QS_RETRY_STORE_RECEIPT ', 1)[1])
                for line in output.splitlines() if 'M3_QS_RETRY_STORE_RECEIPT {' in line]
    if (len(receipts) != 2 or {r.get('backend') for r in receipts} != set(CASES)
            or re.search(r'--- (?:SKIP|FAIL):|WARNING: DATA RACE', output)):
        raise RuntimeError('QS retry store receipts absent, duplicated, failed or skipped')
    for receipt in receipts:
        backend = receipt['backend']
        expected = CASES[backend] | (CLI_CASES if handoff_cli else frozenset())
        name = 'TestM3Retry' + ('MySQL' if backend == 'mysql' else 'Mongo') + 'Store'
        if (receipt.get('passed') != len(expected) or receipt.get('failed') != 0
                or receipt.get('skipped') != 0 or set(receipt.get('cases', {})) != expected
                or any(value is not True for value in receipt['cases'].values())
                or (handoff_cli and receipt.get('offline_cli_required') is not True)
                or (not handoff_cli and receipt.get('offline_cli_required') is not None
                    and receipt.get('offline_cli_required') is not False)
                or receipt.get('scope') != 'original_authorization_and_explicit_future_ownership_handoff'
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
    profile = os.environ.get('QS_M3_RETRY_HANDOFF_CLI_REQUIRED', '')
    if profile not in ('', '1'):
        raise RuntimeError('explicit offline CLI acceptance profile required')
    handoff_cli = profile == '1'
    proof['handoff_cli_required'] = handoff_cli
    if handoff_cli:
        if proof['sdk_module'] != {
                'Path': 'github.com/FangcunMount/reliable-messaging',
                'Version': 'v0.5.0-rocketmq-tx.4',
                'Sum': 'h1:PflI1oWRjU4RFKvpi8WE/8ICI/1IUp8q8EOsbW1DXCI=',
                'GoModSum': 'h1:GPiWG8ZsX4pvIZ6QyvLnBVO5iCqNhvsnKwFcg0ftC7I='}:
            raise RuntimeError('offline CLI requires the fixed published SDK4 module')
        binary = directory / 'qs-retry-handoff-cli'
        run(['go', 'build', '-p', '1', '-race', '-ldflags',
             '-X github.com/FangcunMount/qs-server/pkg/version.GitCommit=' + proof['source_sha'],
             '-o', str(binary), './scripts/maintenance/qs-retry-handoff'],
            cwd=source, env=env, timeout=360)
        binary.chmod(0o700)
        proof['handoff_cli_binary_sha256'] = hashlib.sha256(binary.read_bytes()).hexdigest()
        env.update(QS_M3_RETRY_HANDOFF_CLI_REQUIRED='1',
                   QS_M3_RETRY_HANDOFF_CLI_BINARY=str(binary),
                   QS_M3_RETRY_HANDOFF_CLI_SOURCE_SHA=proof['source_sha'])
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
    proof['diagnostics']['assertion_lines'] = sorted(set(int(n) for n in re.findall(r'm3_retry_(?:store|governance|handoff(?:_cli)?)_integration_test\.go:(\d+)', raw)))[:32]
    if private_log is not None:
        retain_private_host_output(private_log, raw)
    if result.returncode:
        raise RuntimeError('actual QS retry storage acceptance failed (private output withheld)')
    proof['native_receipts'] = parse_retry_receipts(result.stdout, handoff_cli=handoff_cli)
    proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if not proof['source_clean_after']:
        raise RuntimeError('QS source changed during native acceptance')
    proof['scope'] = 'actual governed authorization entrypoints, original MySQL/Mongo Run/future schedule atomicity and legacy future ownership handoff; root reply discard is client-level; no due dispatcher, Broker, model consumer, system or production claim'
    if handoff_cli:
        proof['scope'] += '; explicit exact-source offline CLI first transfer/repeat/default verification/private receipt and original ledger readonly accounting with reviewed source-target pairs/missing-ledger refusal; no production snapshot, all-writer exit or cutover authorization claim'
