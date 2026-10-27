"""One surviving producer against an actually killed, owned Broker; source SDK gate."""
import json
import re
from sdk_acceptance import wait_reference_checks

CASE='public_python_surviving_producer_broker_sigkill_real_checks'
SETUP_CASES=frozenset(('v2_go_python_infra_exact_route_vectors',
    'v2_existing_type_conflict_refuses_all_resource_mutations',
    'v2_idempotent_typed_resources_and_minimum_owner_acls',
    'v2_existing_configuration_conflict_refused'))


def required_cases(readable=False):
    setup = SETUP_CASES
    if readable:
        setup = (setup - {'v2_go_python_infra_exact_route_vectors'}) | {'v3_go_python_infra_exact_route_vectors'}
    return setup | {CASE}



TELEMETRY_FIELDS=frozenset(('pending_settings','settings_closing','settings_writes',
    'settings_failures','settings_skipped','heartbeat_ok','heartbeat_missing','heartbeat_errors',
    'last_heartbeat_code','client_running','heartbeat_thread_alive','route_endpoints',
    'channels','closed_streams','open_streams'))
SDK_FIELDS=frozenset(('stopped','stopping','ready','active_sends','pending_calls','pending_checks',
    'running_checks','completed_results','local_committed_results','half_prepared_results',
    'final_unknown_results','check_commit','check_unknown','check_rollback','callback_errors',
    'invalid_checks','database_errors'))


def telemetry_receipt(event):
    raw=event.get('decision','')
    if not isinstance(raw,str) or len(raw)>16384:
        raise RuntimeError('bounded telemetry diagnostic required')
    value=json.loads(raw)
    if not isinstance(value,dict) or set(value) != {'sdk','telemetry'}:
        raise RuntimeError('fixed telemetry diagnostic schema required')
    result={}
    for group,fields in (('sdk',SDK_FIELDS),('telemetry',TELEMETRY_FIELDS)):
        row=value[group]
        if (not isinstance(row,dict) or not fields.issubset(row)
                or any(type(row[k]) not in (bool,int) or not 0 <= row[k] <= 1000000 for k in fields)):
            raise RuntimeError('safe telemetry counters required; no raw log export')
        result[group]={k:row[k] for k in sorted(fields)}
    return result


def inspect(probe,identity):
    cursor=len(probe.events)
    probe.send('inspect')
    return telemetry_receipt(probe.wait('live_telemetry',identity,timeout=10,after=cursor))


def run_live_recovery(start,sql,control,proof,passed,observer_topics):
    identity='packet-sdk-python-live-restart'
    sender=start('sdk-python','fault-live-broker',identity,branches=3)
    sender.wait('ready')
    identity_before=json.loads(sender.wait('live_identity',identity)['decision'])
    if (set(identity_before) != {'pid','client_sha256'}
            or type(identity_before['pid']) is not int or not 1 <= identity_before['pid'] <= 2**31-1
            or not re.fullmatch('[0-9a-f]{64}',identity_before['client_sha256'])):
        raise RuntimeError('actual Python process and producer identity required')
    sender.wait('half',identity,'all_prepared')
    if (sql(f"SELECT COUNT(*) FROM sdk_business WHERE id='{identity}';") != '0'
            or sql("SELECT COUNT(*) FROM rm_tx_witness w JOIN rm_tx_execution e USING(execution_key) "
                f"WHERE e.operation_id='op-{identity}' AND w.state='prepared' AND w.half_outcome='prepared';") != '3'):
        raise RuntimeError('all actual half ACKs without business commit required before Broker crash')
    proof.update(launcher_pid=sender.process.pid,producer_pid=identity_before['pid'],
        client_identity_sha256=identity_before['client_sha256'],half_prepared_before_kill=3,business_before_kill=0)
    proof['broker_topics_before_crash']=control.topic_metadata(observer_topics)
    reader=start('sdk-route','route-read')
    proof['observer_proxy_route_before_crash']=json.loads(reader.wait('proxy_route',timeout=65)['decision'])
    reader.finish()
    if proof['observer_proxy_route_before_crash']['code'] != 20000:
        raise RuntimeError('observer Proxy route unavailable before fault; no Broker crash performed')
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
    proof['before_restart_snapshot']=inspect(sender,identity)
    proof['broker_restart']=control.start()
    try:
        wait_reference_checks(sender,[f'{identity}-b{i}' for i in range(3)],'commit')
    except RuntimeError:
        proof['reference_check_failed']=True
        try:
            proof['on_failure_snapshot']=inspect(sender,identity)
        except RuntimeError:
            proof['inspection_failed']=True
        raise
    proof['after_recheck_snapshot']=inspect(sender,identity)
    proof['topic_routes_ready']=control.wait_topic_routes(observer_topics)
    proof['broker_topics_after_restart']=control.topic_metadata(observer_topics)
    reader=start('sdk-route','route-read')
    proof['observer_proxy_route']=json.loads(reader.wait('proxy_route',timeout=65)['decision'])
    reader.finish()
    if proof['observer_proxy_route']['code'] != 20000 or proof['observer_proxy_route']['queues'] < 1:
        raise RuntimeError('actual observer Proxy route not ready after Broker recovery')
    observer=start('sdk-go','consume')
    observer.wait('ready')
    for i in range(3):observer.wait('received',f'{identity}-b{i}')
    observer.send('stop');observer.wait('closed');observer.finish()
    sender.send('stop')
    identity_after=json.loads(sender.wait('live_identity_after',identity)['decision'])
    if identity_before != identity_after:
        raise RuntimeError('producer process or client instance replaced during recovery')
    sender.wait('closed');sender.finish()
    proof['closed_telemetry']=telemetry_receipt(sender.wait('live_telemetry_closed',identity))
    closed=proof['closed_telemetry']['telemetry']
    if closed['pending_settings'] != 0 or not closed['settings_closing'] or closed['client_running']:
        raise RuntimeError('metadata settings RPCs or client still active after close')
    stats=json.loads(sender.wait('metrics')['decision'])
    if (not stats.get('stopped') or stats.get('completed_results') != 1
            or stats.get('local_committed_results') != 1 or stats.get('half_prepared_results') != 3
            or stats.get('final_unknown_results') != 3 or not 3 <= stats.get('check_commit',0) <= 1024
            or any(stats.get(k) != 0 for k in ('active_sends','pending_calls','pending_checks','running_checks'))):
        raise RuntimeError('same producer replayed business or failed to drain actual checks/RPCs')
    proof.update(check_commit=stats['check_commit'],consumed_original_messages=3,
        producer_unchanged=True,stats=stats,source_candidate_only=True)
    passed(CASE)
