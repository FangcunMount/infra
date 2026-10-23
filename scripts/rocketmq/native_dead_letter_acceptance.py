"""Isolated native DLQ record plus index-only audit; not business acceptance."""
import hashlib
import json
import os
import re
import secrets
import sys
import time

from audit_transaction_limit import write_private
from provision_v2 import Admin
from routes import consumer_group_v2, physical_topic_v2, validate_v2

CASES = frozenset(('canonical_v2_group_and_minimum_acl','fixed_public_sdk_without_replace',
    'isolated_group_retry_limit_read_back','normal_publish_and_unavailable_handoff',
    'real_native_dlq_index','repeat_index_read_preserves_records','private_index_no_body_or_key',
    'owned_sdk_process_drained'))
SDK = dict(Path='github.com/FangcunMount/reliable-messaging',Version='v0.5.0-rocketmq-tx.3',
    Sum='h1:25yHjaHAcZYjp96+iNVJyYbdnDPvR6p16J06KeG0sP4=',
    GoModSum='h1:GPiWG8ZsX4pvIZ6QyvLnBVO5iCqNhvsnKwFcg0ftC7I=')



def validate_options(options):
    allowed={'native_dlq_audit','sdk','image','mysql_image','report','python','qs_deferred_kind'}
    if (options.get('native_dlq_audit') is not True
            or any(value for key,value in options.items() if key not in allowed)
            or options.get('python','uv')!='uv'
            or options.get('qs_deferred_kind','mysql')!='mysql'):
        raise ValueError('native DLQ audit is a standalone fixture profile')


def manifest():
    topic,subscription='infra.native.audit','native-audit-observer'
    route=dict(id='native-audit',topic=topic,subscription=subscription,message_type='NORMAL',
        owner='qs.mysql',route_revision='m3-1',
        physical_topic=physical_topic_v2(topic,'NORMAL','qs.mysql','m3-1'),
        consumer_group=consumer_group_v2(topic,subscription))
    result=dict(version=2,routes=[route],topic_options=dict(read_queue_nums=1,write_queue_nums=1,perm=6),
        group_options=dict(retry_queue_nums=8),accounts={'native-audit':dict(owner='qs.mysql',
            publish=['native-audit'],subscriptions=['native-audit'])})
    validate_v2(result)
    return result


def safe_event(event):
    """Never let arbitrary child JSON enter the shared public probe receipt."""
    invalid=dict(event='invalid_native_audit_event')
    if not isinstance(event,dict):return invalid
    if event == dict(event='exited'):return dict(event)
    if set(event)=={'event','status'} and event.get('event')=='failed' and isinstance(event.get('status'),str) and event.get('status') in {'invalid_fixture','fixture_failed'}:
        return dict(event)
    if event.get('event')=='ready':
        if (set(event)!={'event','ready','published','wire_sha256','max_inflight'}
                or event['ready'] is not True or type(event['published']) is not int or event['published']!=1
                or type(event['max_inflight']) is not int or event['max_inflight']!=1
                or not isinstance(event['wire_sha256'],str)
                or re.fullmatch('[0-9a-f]{64}',event['wire_sha256']) is None):return invalid
        return dict(event)
    if event.get('event')=='closed':
        counters={'published','handler_calls','failed_handoff_calls','wire_mismatches','application_ack_calls'}
        if (set(event)!=counters|{'event','closed'} or event['closed'] is not True
                or any(type(event[k]) is not int or not 0<=event[k]<=1024 for k in counters)
                or event['published']!=1 or min(event['handler_calls'],event['failed_handoff_calls'])<1
                or event['wire_mismatches']!=0 or event['application_ack_calls']!=0):return invalid
        return dict(event)
    return invalid


def require_event(event,kind):
    safe=safe_event(event)
    if safe.get('event')!=kind:raise RuntimeError('native audit process evidence invalid')
    return safe


def run_native(repo,directory,broker,project,grpc_port,ca,run,native_runner,proof):
    if not project.startswith('rocketmq-m2-') or directory.stat().st_mode&0o077 or native_runner is None:
        raise ValueError('owned isolated native audit fixture required')
    proof['cases']={}
    def passed(case):
        if case not in CASES:raise RuntimeError('unknown native audit case')
        proof['cases'][case]=True
    source=repo/'scripts/rocketmq/probes/native-dead-letter'
    env=dict(os.environ,GOWORK='off',GOFLAGS='-mod=readonly',GOTOOLCHAIN='local')
    module=json.loads(run(['go','list','-m','-json',SDK['Path']],cwd=source,env=env).stdout)
    if module.get('Replace') or any(module.get(k)!=v for k,v in SDK.items()):
        raise RuntimeError('fixed public native audit SDK required')
    go=run(['go','version'],cwd=source,env=env).stdout.strip()
    if re.match(r'go version go1\.25\.12 ',go) is None:raise RuntimeError('fixed native audit Go required')
    binary=directory/'native-dlq-probe'
    run(['go','build','-race','-trimpath','-o',str(binary),'.'],cwd=source,env=env,timeout=300)
    binary.chmod(0o700)
    proof.update(sdk_module=SDK,go_version=go,binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
    passed('fixed_public_sdk_without_replace')
    plan=manifest();route=plan['routes'][0]
    credentials={'native-audit':dict(username='audit-'+secrets.token_hex(8),password=secrets.token_urlsafe(36))}
    manifest_file,credentials_file=directory/'native-audit-manifest.json',directory/'native-audit-credentials.json'
    write_private(manifest_file,plan);write_private(credentials_file,credentials)
    provisioned=run([sys.executable,str(repo/'scripts/rocketmq/provision.py'),'--container',broker,
        '--project',project,'--manifest',str(manifest_file),'--credentials',str(credentials_file)],timeout=180)
    summary=json.loads(provisioned.stdout)
    if summary.get('verified') is not True or summary.get('typed_topics')!=1 or summary.get('principals')!=1:
        raise RuntimeError('native audit resources unverified')
    proof['provision']={k:summary[k] for k in ('version','operations','typed_topics','principals','verified')}
    passed('canonical_v2_group_and_minimum_acl')
    admin=Admin(broker)
    admin('updateSubGroup','-g',route['consumer_group'],'-q','8','-r','1',mutation=True)
    metadata='/home/rocketmq/native-audit-'+secrets.token_hex(8)
    admin.docker('mkdir','-m','700',metadata)
    try:
        group=admin.metadata(metadata)['subscriptionGroupTable'][route['consumer_group']]
        if group.get('retryMaxTimes')!=1 or group.get('retryQueueNums')!=8 or group.get('consumeEnable') is not True:
            raise RuntimeError('isolated native group budget readback differs')
        proof['isolated_group_parameters']=dict(retryMaxTimes=1,retryQueueNums=8,consumeEnable=True)
    finally:
        for filename in ('topic.json','subscriptionGroup.json'):
            admin.docker('rm','-f','--',metadata+'/'+filename,required=False)
        admin.docker('rmdir',metadata,required=False)
    passed('isolated_group_retry_limit_read_back')
    account=credentials['native-audit'];key='audit-'+secrets.token_hex(16)
    route_config=directory/'native-audit-route-private.json'
    write_private(route_config,dict(endpoint=f'127.0.0.1:{grpc_port}',ca=str(ca),topic=route['physical_topic'],
        accesskey=account['username'],secretkey=account['password']))
    from route_read_probe import parse_output
    response=run(['uv','run','--no-project','--isolated','--python','3.11','--with','rocketmq-python-client==5.1.2',
        'python',str(repo/'scripts/rocketmq/route_read_probe.py'),'--config',str(route_config),'--mode','route-read'],timeout=180)
    proof['proxy_route']=parse_output(response.stdout,route['physical_topic'])
    config=directory/'native-audit-go-private.json'
    write_private(config,dict(Project=project,Endpoint=f'127.0.0.1:{grpc_port}',CAFile=str(ca),
        AccessKey=account['username'],SecretKey=account['password'],Key=key,
        Route={k:v for k,v in route.items() if k!='id'}))
    owned={}
    def audit_file(ordinal):
        path=directory/('native-audit-index-'+str(ordinal)+'.json')
        result=native_runner([sys.executable,str(repo/'scripts/rocketmq/audit_native_dead_letters.py'),
            '--container',broker,'--project',project,'--manifest',str(manifest_file),
            '--route',route['id'],'--key',key,'--output',str(path)],cwd=repo,env=env,timeout=30,required=False)
        if result.returncode==1:return None
        if result.returncode not in (0,2) or not path.is_file() or path.stat().st_mode&0o777!=0o600:
            raise RuntimeError('native keyed audit failed')
        public=json.loads(result.stdout.strip());private=path.read_bytes();report=json.loads(private)
        expected={'records','read_only','body_exported','truncated_possible','owner_scope_ambiguous','alert','severity'}
        if (set(public)!=expected or key in result.stdout or key.encode() in private
                or b'private-native-dlq-payload' in private or b'private-native-dlq-payload' in result.stdout.encode()
                or report['key_sha256']!=hashlib.sha256(key.encode()).hexdigest()
                or report['manifest_sha256']!=hashlib.sha256(manifest_file.read_bytes()).hexdigest()
                or report['candidate_owners']!=['qs.mysql'] or report['body_exported'] is not False
                or report['read_only'] is not True or public['read_only'] is not True or public['body_exported'] is not False):
            raise RuntimeError('native audit scope or privacy evidence differs')
        if result.returncode==0:return None
        if len(report['records'])!=1 or public['records']!=1 or public['alert']!='native_dead_letter_records' or public['severity']!='critical':
            raise RuntimeError('real native DLQ index record absent')
        return report
    def supervise(native):
        owned['native']=native
        proof['ready']=require_event(native.wait('ready',timeout=45),'ready')
        deadline=time.monotonic()+75;first=None;ordinal=0
        while time.monotonic()<deadline:
            ordinal+=1;first=audit_file(ordinal)
            if first is not None:break
            time.sleep(1)
        if first is None:raise RuntimeError('real native DLQ record not observed within budget')
        second=audit_file(ordinal+1)
        if second is None or second['records']!=first['records']:
            raise RuntimeError('read-only index changed after repeated query')
        proof['native_index']=dict(records=1,read_only=True,body_exported=False,mode='0600',
            key_sha256=first['key_sha256'],manifest_sha256=first['manifest_sha256'],
            records_sha256=hashlib.sha256(json.dumps(first['records'],sort_keys=True).encode()).hexdigest(),
            repeat_records_unchanged=True,candidate_owners=['qs.mysql'],owner_scope_ambiguous=False,
            query_scope=first['query_scope'],cli_exit_code=2)
        for case in ('real_native_dlq_index','repeat_index_read_preserves_records','private_index_no_body_or_key'):
            passed(case)
        native.send('stop')
        proof['closed']=require_event(native.wait('closed',timeout=30),'closed')
        passed('normal_publish_and_unavailable_handoff')
    try:
        result=native_runner([str(binary),str(config)],cwd=source,env=env,timeout=180,required=False,
            prefix='M3_NATIVE_DLQ_PROBE ',supervise=supervise)
        if result.returncode:raise RuntimeError('native audit SDK process did not close successfully')
        passed('owned_sdk_process_drained')
    finally:
        native=owned.get('native')
        if native is not None:
            native.drain()
            native.events[:]=[safe_event(event) for event in native.events]
    if set(proof['cases'])!=CASES:raise RuntimeError('native audit cases incomplete')
