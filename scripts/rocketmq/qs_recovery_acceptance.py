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


def parse_recovery_receipt(output, source):
    rows = [json.loads(line.removeprefix('M3C_QS_RECOVERY_RECEIPT '))
            for line in output.splitlines() if line.startswith('M3C_QS_RECOVERY_RECEIPT ')]
    if len(rows) != 1:
        raise RuntimeError('one actual host retirement receipt required')
    value = rows[0]
    flags = ('real_redis', 'broker_sigkill', 'worker_sigkill', 'controlled_provider',
             'owned_databases_dropped', 'no_existing_storage', 'no_production')
    if (value.get('source_sha') != source or value.get('passed') != len(CASES)
            or value.get('failed') != 0 or value.get('skipped') != 0
            or set(value.get('cases', {})) != CASES
            or any(v is not True for v in value['cases'].values())
            or any(value.get(k) is not True for k in flags)
            or value.get('worker_pids_distinct') is not True
            or not re.search(r'--- PASS: TestM3HostRetirementRecovery \(', output)
            or re.search(r'--- (?:SKIP|FAIL):|WARNING: DATA RACE', output)):
        raise RuntimeError('current recovery proof incomplete, wrong source, failed or skipped')
    return value
