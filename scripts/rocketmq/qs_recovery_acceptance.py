"""Actual default QS dual owners, original roots and compiled recovery, CI only."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time

from audit_transaction_limit import export,write_private
from iam_recovery_acceptance import require
from managed_recovery_acceptance import accept as managed_accept
from qs_runtime_acceptance import runtime_manifest,validate_module
from recovery_fixture_store import MongoFixtureStore

SOURCE='9301bf8044cd826aa9f34088e4b97899a12618d3'


def metadata(value):
    require(isinstance(value,dict) and set(value)=={'database','branches','original_root_calls','original_owners_stopped','broker_sigkill_after_commit'},'exact_qs_original_root_metadata_required')
    require(value['original_root_calls']==2 and type(value['original_root_calls']) is int
        and value['original_owners_stopped'] is True and value['broker_sigkill_after_commit'] is True,'real_dual_root_and_stop_required')
    require(isinstance(value['database'],str) and re.fullmatch(r'qs_m3_host_[0-9]{10,30}',value['database']),'owned_qs_original_database_required')
    require(isinstance(value['branches'],list) and len(value['branches'])==2,'full_dual_owner_metadata_required')
    owners=set()
    for branch in value['branches']:
        require(set(branch)=={'owner','store_id','writer_epoch','operation_id','branch_id','fence','message_id','wire_hash'},'exact_qs_original_reference_metadata_required')
        owner=branch['owner'];require(owner in ('qs.mysql','qs.mongo') and owner not in owners,'distinct_qs_original_owners_required');owners.add(owner)
        require(branch['store_id']==owner+'-original-runtime' and branch['writer_epoch']=='m3-1','original_qs_binding_required')
        require(type(branch['fence']) is int and 1<=branch['fence']<=2**63-1,'exact_qs_fence_required')
        require(isinstance(branch['wire_hash'],str) and re.fullmatch('[0-9a-f]{64}',branch['wire_hash']),'original_qs_wire_digest_required')
        for key in ('operation_id','branch_id','message_id'):require(isinstance(branch[key],str) and re.fullmatch('[A-Za-z0-9_.:-]{1,128}',branch[key]),'bounded_original_qs_identity_required')
    return value


def accept(*,source,repo,binary,observer_binary,broker,project,directory,manifest,grpc_port,mysql_port,mongo_port,password,ca,
           accounts,java,mongo,sql_for,run,common,probes,admin,read_parameters,parameters,passed,proof):
    require(run(['git','rev-parse','HEAD'],cwd=source).stdout.strip()==SOURCE and not run(['git','status','--porcelain'],cwd=source).stdout,'fixed_clean_original_qs_source_required')
    env=dict(os.environ,GOWORK='off',GOTOOLCHAIN='local',GOFLAGS='-mod=readonly')
    module=json.loads(run(['go','list','-m','-json','github.com/FangcunMount/reliable-messaging'],cwd=source,env=env).stdout);validate_module(module,True)
    root=directory/'qs-native-recovery';root.mkdir(mode=0o700)
    def write(name,value):path=root/name;write_private(path,value);return path
    routes=write('routes.json',manifest)
    credentials={name:write(name+'-credentials.json',value) for name,value in accounts.items() if name.startswith('m3-qs-')}
    base=dict(endpoint=f'127.0.0.1:{grpc_port}',credentials_file=str(credentials['m3-qs-apiserver']),ca_file=str(ca),routes_file=str(routes),instance_id='qs-original-recovery',publish_enabled=True,
        transactions={owner:dict(credentials_file=str(credentials[role]),store_id=owner+'-original-runtime',writer_epoch='m3-1',route_revision='m3-1') for owner,role in (('qs.mysql','m3-qs-apiserver'),('qs.mongo','m3-qs-mongo'))})
    options=write('options.json',dict(provider='rocketmq',enabled=True,rocketmq=base))
    observer_options=write('old-observer.json',dict(provider='rocketmq',enabled=True,rocketmq=dict(base,credentials_file=str(credentials['m3-qs-worker']),publish_enabled=False,transactions={})))
    uri=f'mongodb://127.0.0.1:{mongo_port}/?replicaSet=sdk-proof&directConnection=true'
    env.update(QS_M3_FIXTURE_PROJECT=project,QS_M3_HOST_BROKER=broker,QS_M3_HOST_DSN=f'root:{password}@tcp(127.0.0.1:{mysql_port})/?parseTime=true',QS_M3_HOST_MONGO_URI=uri,
        QS_M3_HOST_OPTIONS=str(options),QS_M3_HOST_OBSERVER_OPTIONS=str(observer_options),QS_M3_NATIVE_RECOVERY_DIRECTORY=str(root))
    env.pop('QS_M3_VERIFY_PROTOCOL_PROTECTION',None);env.pop('QS_M3_VERIFY_NATIVE_LIMIT',None)
    host_binary=directory/'qs-native-recovery-test'
    run(['go','test','-race','-tags=integration,m3_host_runtime','-c','-o',str(host_binary),'./internal/apiserver/container'],cwd=source,env=env,timeout=300)
    # Hold the original window through two local commits; the existing actual
    # host fixture kills/restarts only its owned Broker and releases to6000.
    admin('updateBrokerConfig','-k','transactionTimeOut','-v','600000',success=True)
    require(read_parameters()['transactionTimeOut']==600000,'owned_original_check_hold_required')
    actor=common.Probe([str(host_binary),'-test.v','-test.timeout=12m','-test.run=^TestM3DefaultOwnerNativeRecovery$'],directory,env,prefix='M3_QS_NATIVE_RECOVERY ',cwd=source/'internal/apiserver/container');probes.append(actor)
    proof['qs_original_host']=dict(source_sha=SOURCE,sdk_module={k:module[k] for k in ('Version','Sum','GoModSum')},binary_sha256=hashlib.sha256(host_binary.read_bytes()).hexdigest(),whole_api=False,domain_projection=False,system_acceptance=False)
    def diagnostic():
        if actor.process.poll() is not None:actor.reader.join(timeout=2)
        actor.log.flush();raw=Path(actor.log.name).read_text(errors='replace')
        proof['qs_host_diagnostics']=dict(exit_code=actor.process.poll(),private_output_sha256=hashlib.sha256(raw.encode()).hexdigest(),race_reports=raw.count('WARNING: DATA RACE'),
            assertion_lines=sorted(set(map(int,re.findall(r'owner_runtime_native_integration_test.go:(\d+)',raw))))[:40])
    def wait(name,timeout=160):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            path=root/name
            if path.exists():require(not path.is_symlink() and path.is_file() and path.stat().st_mode&0o077==0,'private_original_qs_control_required');return json.loads(path.read_text())
            if actor.process.poll() is not None:diagnostic();raise RuntimeError('actual_qs_owner_exited_before_control')
            time.sleep(.1)
        diagnostic();raise RuntimeError('actual_qs_owner_control_timeout')
    original=metadata(wait('original-roots.json'))
    proof['qs_original_roots_committed_and_stopped']=True
    passed('actual_qs_dual_original_roots_commit_and_stop_with_final_unknown_after_real_broker_sigkill')
    admin('updateBrokerConfig','-k','transactionCheckMax','-v','2',success=True)
    actual=read_parameters();require(actual==dict(parameters,transactionCheckMax=2),'bounded_qs_native_fault_parameters_required')
    indices={}
    for b in original['branches']:
        path=root/('native-'+b['owner']+'.json');end=time.monotonic()+110
        while time.monotonic()<end:
            try:indices[b['owner']]=export(broker,project,b['message_id'],path);break
            except RuntimeError:time.sleep(2)
        require(b['owner'] in indices and len(indices[b['owner']]['records'])==1 and not indices[b['owner']]['truncated_possible'],'one_actual_native_index_per_qs_original_owner_required')
    for key,value in parameters.items():admin('updateBrokerConfig','-k',key,'-v',str(value),success=True)
    require(read_parameters()==parameters,'original_qs_parameters_not_restored')
    passed('both_actual_original_qs_halves_reach_native_limit_without_new_producer')
    write('record-notices',dict(continue_owned_fixture=True));require(wait('notices.json',15)==dict(both_original_stores_recorded=True),'both_original_qs_native_notices_required')
    passed('actual_qs_host_imports_each_exact_native_index_on_original_store')
    inputs=[r for r in manifest['routes'] if r['topic']=='qs.evaluation.lifecycle' and r['subscription']=='qs-worker' and r['message_type']=='TRANSACTION']
    require({r['owner'] for r in inputs}=={'qs.mysql','qs.mongo'} and len(inputs)==2,'one_full_shared_qs_observer_inventory_required')
    account=accounts['m3-qs-worker'];observer_config=write('current-observer.json',dict(endpoint=f'127.0.0.1:{grpc_port}',accesskey=account['username'],secretkey=account['password'],ca=str(ca),subscription='qs-worker',inputs=[{k:v for k,v in r.items() if k!='id'} for r in inputs]))
    observer=common.Probe([str(observer_binary),'--config',str(observer_config),'--config-sha',hashlib.sha256(observer_config.read_bytes()).hexdigest()],directory,dict(os.environ));probes.append(observer);observer.wait('ready')
    proof['qs_owner_recoveries']={}
    for b in original['branches']:
        owner=b['owner'];proof['last_qs_recovery_owner']=owner
        scoped=directory/('recover-'+owner);scoped.mkdir(mode=0o700)
        plan=dict(b,database=original['database'],user='root',writer='actual default QS '+owner+' owner with original host protocol fixture root',scope='actual QS original owner/root component, not domain API, provider or system',business_count_sql='SELECT COUNT(*) FROM m3_owner_runtime_facts')
        if owner=='qs.mongo':plan.update(database_kind='mongo',database_uri=uri,adapter=MongoFixtureStore(mongo,original['database']))
        chosen=next(r for r in inputs if r['owner']==owner)
        owner_proof={}
        managed_accept(repo=repo,binary=binary,broker=broker,project=project,directory=scoped,manifest=manifest,route=chosen,account=accounts['m3-qs-apiserver' if owner=='qs.mysql' else 'm3-qs-mongo'],
            grpc_port=grpc_port,mysql_port=mysql_port,password=password,ca=ca,java=java,identity=b['message_id'],index_path=root/('native-'+owner+'.json'),index=indices[owner],sql=sql_for(original['database']),run=run,
            consumer=observer,passed=lambda name,owner=owner:passed(owner+'_'+name),proof=owner_proof,original=plan)
        proof['qs_owner_recoveries'][owner]=owner_proof
    write('verify',dict(continue_owned_fixture=True))
    try:actor.finish(timeout=45)
    except Exception:diagnostic();raise
    diagnostic()
    values=[e for e in actor.events if e.get('passed')==7]
    expected=dict(passed=7,failed=0,skipped=0,original_roots=2,both_owners_stopped=True,both_stores_resolved=True,paused_replacement_drained=True,owned_databases_removed=True,whole_api=False,system_acceptance=False)
    require(values==[expected] and proof['qs_host_diagnostics']['race_reports']==0,'exact_original_qs_roots_and_paused_replacement_required')
    proof['qs_original_host']['receipt']=expected
    observer.send('stop');observer.wait('closed');observer.finish()
    require(sql_for('mysql')("SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name LIKE 'qs_m3_host_%';")=='0','owned_original_qs_mysql_database_remains')
    require(json.loads(mongo('JSON.stringify(db.adminCommand({listDatabases:1,nameOnly:true}).databases.map(x=>x.name).filter(x=>x.startsWith("qs_m3_host_"))))'))==[],'owned_original_qs_mongo_database_remains')
    require(not run(['git','status','--porcelain'],cwd=source).stdout,'original_qs_source_changed')
    proof['qs_original_host'].update(source_clean=True,owned_databases_removed=True)
    passed('actual_qs_both_original_stores_resolved_paused_replacement_drained_and_owned_databases_removed')
