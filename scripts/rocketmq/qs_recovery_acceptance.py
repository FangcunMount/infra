"""Required host-retirement recovery proof, separate from earlier M3/M4 counts."""
import json
import re

RECOVERY_MODULE = dict(Path='github.com/FangcunMount/reliable-messaging', Version='v0.6.0',
    Sum='h1:ncfphXuTE6JtSH9wJTxakZxkLxic4uws15L5dRvYrg0=',
    GoModSum='h1:GPiWG8ZsX4pvIZ6QyvLnBVO5iCqNhvsnKwFcg0ftC7I=')


def validate_recovery_module(module):
    if not isinstance(module, dict) or 'Replace' in module or any(module.get(k) != v for k, v in RECOVERY_MODULE.items()):
        raise RuntimeError('current retirement recovery requires exact published SDK0.6.0 and original module sums')

CASES = frozenset((
    'original_transaction_roots_without_relay',
    'real_redis_current_day_cli_rebuild_and_repeat',
    'answersheet_operator_original_request_response_loss',
    'known_reminder_original_receipt_no_repeat',
    'unknown_provider_response_never_resends',
    'frozen_reminder_recipients_survive_recovery',
    'worker_sigkill_after_effect_before_ack',
    'same_owned_broker_sigkill_restart',
    'actual_original_wire_redelivery_after_restart',
    'one_assessment_run_outcome_and_report',
    'late_original_delivery_preserves_rank_and_notification_counts',
    'conflicting_source_refuses_whole_rebuild',
    'closed_or_changed_task_refuses_new_send',
    'receipts_readable_with_writes_disabled',
))


def recovery_diagnostics(output):
    """Export only bounded, fixed-schema technical states of owned fixtures."""
    result = []
    label = lambda v: isinstance(v, str) and bool(re.fullmatch(r'[a-z0-9_.]{0,80}', v))
    number = lambda v: type(v) is int and 0 <= v <= 2147483647
    def rows(value, schema):
        return value is None or (isinstance(value, list) and len(value) <= 10 and all(
            isinstance(row, dict) and set(row) == set(schema) and all(check(row[k]) for k, check in schema.items()) for row in value))
    for line in output.splitlines():
        if not line.startswith('M3C_COMPLETION_DIAGNOSTIC '):
            continue
        try:
            v = json.loads(line.removeprefix('M3C_COMPLETION_DIAGNOSTIC '))
        except ValueError:
            raise RuntimeError('invalid fixed recovery diagnostic') from None
        flags = {'assessment_read_ok', 'run_read_ok', 'dead_letter_read_ok', 'hold_read_ok', 'redis_read_ok'}
        fields = flags | {'stage', 'ensure_calls', 'reminder_visits', 'provider_calls', 'assessments', 'runs', 'dead_letters', 'held_deliveries', 'worker_lock_pttl_ms', 'mongo'}
        if (not isinstance(v, dict) or set(v) != fields or v['stage'] not in {'before_report', 'failure'}
                or any(type(v[k]) is not bool for k in flags)
                or not number(v['ensure_calls']) or not number(v['provider_calls'])
                or not isinstance(v['reminder_visits'], list) or len(v['reminder_visits']) != 4 or any(type(x) is not bool for x in v['reminder_visits'])
                or type(v['worker_lock_pttl_ms']) is not int or not -2 <= v['worker_lock_pttl_ms'] <= 300000
                or not rows(v['assessments'], {'status':label,'count':number})
                or not rows(v['runs'], {'status':label,'attempt':number,'disposition':label,'lease_expired':lambda x:type(x) is bool})
                or not rows(v['dead_letters'], {'event_type':label,'attempt':number,'disposition':label})
                or not rows(v['held_deliveries'], {'status':label,'attempt':number,'disposition':label})
                or not isinstance(v['mongo'], dict) or set(v['mongo']) != {'report_generations','interpretation_runs','interpret_report_artifacts'}):
            raise RuntimeError('unsafe or incomplete fixed recovery diagnostic')
        for m in v['mongo'].values():
            if (not isinstance(m, dict) or set(m) != {'count','statuses','expired_leases','read_ok'}
                    or type(m['read_ok']) is not bool or not number(m['count']) or not number(m['expired_leases'])
                    or not isinstance(m['statuses'], list) or len(m['statuses']) > 10 or not all(label(x) for x in m['statuses'])):
                raise RuntimeError('unsafe fixed recovery collection diagnostic')
        if len(result) >= 2 or any(r['stage'] == v['stage'] for r in result):
            raise RuntimeError('duplicate fixed recovery diagnostic')
        result.append(v)
    return result


def parse_recovery_receipt(output, source):
    rows = [json.loads(line.removeprefix('M3C_QS_RECOVERY_RECEIPT '))
            for line in output.splitlines() if line.startswith('M3C_QS_RECOVERY_RECEIPT ')]
    if len(rows) != 1:
        raise RuntimeError('one actual host retirement receipt required')
    value = rows[0]
    flags = ('api_lease_recovery_started', 'api_lease_recovery_drained', 'report_claim_observed', 'proxy_routes_ready', 'processing_lease_observed', 'real_redis', 'broker_sigkill', 'worker_sigkill', 'controlled_provider',
             'owned_databases_dropped', 'no_existing_storage', 'no_production')
    if (value.get('source_sha') != source or value.get('passed') != len(CASES)
            or value.get('failed') != 0 or value.get('skipped') != 0
            or set(value.get('cases', {})) != CASES
            or any(v is not True for v in value['cases'].values())
            or any(value.get(k) is not True for k in flags)
            or value.get('worker_pids_distinct') is not True
            or type(value.get('processing_lease_ttl_ms')) is not int
            or not 0 < value['processing_lease_ttl_ms'] <= 300000
            or type(value.get('report_lease_ttl_ms')) is not int
            or not 0 < value['report_lease_ttl_ms'] <= 300000
            or type(value.get('proxy_routes_checked')) is not int
            or not 1 <= value['proxy_routes_checked'] <= 128
            or not re.search(r'--- PASS: TestM3HostRetirementRecovery \(', output)
            or re.search(r'--- (?:SKIP|FAIL):|WARNING: DATA RACE', output)):
        raise RuntimeError('current recovery proof incomplete, wrong source, failed or skipped')
    return value


def recovery_gate_diagnostics(output):
    """Fixed message classes only; never return child text, IDs or lock keys."""
    classes={'contention_retry','wait_started','wait_completed','wait_cancelled',
             'wait_exhausted','ensure_failed','processed'}
    rows=[]
    for line in output.splitlines():
        if not line.startswith('M3C_WORKER_GATE_DIAGNOSTIC '):continue
        raw=line.removeprefix('M3C_WORKER_GATE_DIAGNOSTIC ')
        if len(raw)>2048:raise RuntimeError('gate diagnostic exceeds bound')
        try:value=json.loads(raw)
        except ValueError:raise RuntimeError('invalid gate diagnostic') from None
        if (not isinstance(value,dict) or set(value)!={'worker','counts','truncated'}
                or value['worker'] not in {'first','replacement'}
                or type(value['truncated']) is not bool
                or not isinstance(value['counts'],dict) or set(value['counts'])!=classes
                or any(type(x) is not int or not 0<=x<=10000 for x in value['counts'].values())
                or len(rows)>=2 or any(x['worker']==value['worker'] for x in rows)):
            raise RuntimeError('unsafe or incomplete gate diagnostic')
        rows.append(value)
    return rows


def process_startup_diagnostics(output):
    """Bounded public technical labels; never retain a child's private text."""
    result = []
    for line in output.splitlines():
        if not line.startswith('M5_PROCESS_STARTUP_DIAGNOSTIC '):
            continue
        raw = line.removeprefix('M5_PROCESS_STARTUP_DIAGNOSTIC ')
        if len(raw) > 512:
            raise RuntimeError('startup diagnostic exceeds bound')
        try:
            value = json.loads(raw)
        except ValueError:
            raise RuntimeError('invalid startup diagnostic') from None
        if (not isinstance(value, dict) or set(value) != {'role', 'phase', 'stage', 'reason', 'exit_code'}
                or value['role'] not in {'api', 'collection', 'worker'}
                or value['phase'] not in {'startup_exit', 'health_deadline'}
                or value['stage'] not in {'unknown', 'resources', 'container', 'integrations', 'transports', 'runtime', 'shutdown'}
                or value['reason'] not in {'process_exit', 'owned_namespace', 'compiled_source', 'schema_pair', 'iam', 'database'}
                or type(value['exit_code']) is not int or not -1 <= value['exit_code'] <= 255
                or len(result) >= 3 or any(x['role'] == value['role'] for x in result)):
            raise RuntimeError('unsafe or duplicate startup diagnostic')
        result.append(value)
    return result
