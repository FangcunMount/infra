"""One surviving producer against an actually killed, owned Broker; source SDK gate."""
import json
from sdk_acceptance import wait_reference_checks

CASE='public_python_surviving_producer_broker_sigkill_real_checks'
SETUP_CASES=frozenset(('v2_go_python_infra_exact_route_vectors',
    'v2_existing_type_conflict_refuses_all_resource_mutations',
    'v2_idempotent_typed_resources_and_minimum_owner_acls',
    'v2_existing_configuration_conflict_refused'))


def run_live_recovery(start,sql,control,proof,passed):
    identity='packet-sdk-python-live-restart'
    sender=start('sdk-python','fault-live-broker',identity,branches=3)
    sender.wait('ready');sender.wait('half',identity,'all_prepared')
    if (sql(f"SELECT COUNT(*) FROM sdk_business WHERE id='{identity}';") != '0'
            or sql("SELECT COUNT(*) FROM rm_tx_witness w JOIN rm_tx_execution e USING(execution_key) "
                f"WHERE e.operation_id='op-{identity}' AND w.state='prepared' AND w.half_outcome='prepared';") != '3'):
        raise RuntimeError('all actual half ACKs without business commit required before Broker crash')
    proof.update(same_producer_pid=sender.process.pid,half_prepared_before_kill=3,business_before_kill=0)
    proof['broker_kill']=control.kill()
    sender.send('commit')
    sender.wait('fault_observed',identity,'fault-live-broker',timeout=45)
    sender.wait('live_waiting',identity,'admission_stopped_original_checks_drained',timeout=20)
    result=json.loads(sender.wait('result',identity)['decision'])
    if (result.get('local') != 'committed' or result.get('local_calls') != 1
            or len(result.get('branches',[])) != 3
            or any(b.get('half') != 'prepared' or b.get('final') != 'unknown' for b in result['branches'])
            or sql(f"SELECT COUNT(*) FROM sdk_business WHERE id='{identity}';") != '1'):
        raise RuntimeError('one committed original root and three actual final Unknown results required')
    proof.update(local_calls=1,business_after_commit=1,final_unknown=3)
    proof['broker_restart']=control.start()
    wait_reference_checks(sender,[f'{identity}-b{i}' for i in range(3)],'commit')
    observer=start('sdk-go','consume')
    observer.wait('ready')
    for i in range(3):observer.wait('received',f'{identity}-b{i}')
    observer.send('stop');observer.wait('closed');observer.finish()
    sender.send('stop');sender.wait('closed');sender.finish()
    stats=json.loads(sender.wait('metrics')['decision'])
    if (not stats.get('stopped') or stats.get('completed_results') != 1
            or stats.get('local_committed_results') != 1 or stats.get('half_prepared_results') != 3
            or stats.get('final_unknown_results') != 3 or not 3 <= stats.get('check_commit',0) <= 1024
            or any(stats.get(k) != 0 for k in ('active_sends','pending_calls','pending_checks','running_checks'))):
        raise RuntimeError('same producer replayed business or failed to drain actual checks/RPCs')
    proof.update(check_commit=stats['check_commit'],consumed_original_messages=3,
        producer_unchanged=True,stats=stats,source_candidate_only=True)
    passed(CASE)
