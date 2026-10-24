"""Isolated compiled-CLI acceptance; caller owns/cleans the disposable stack.

Original producer is the fixed public SDK source probe, not a business host.
The recovery CLI itself uses the published tx.4 module, actual native admin,
actual original MySQL and actual SDK RPC. Synthetic named reviewers are never
reported as production approval or system acceptance.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import struct
import time

from audit_transaction_limit import export, write_private
from routes import physical_topic_v2,consumer_group_v2
from start_boundary import initialize, _encoded
from cutover_step import execute, load_step
from mysql_commit_proxy import MySQLCommitProxy
from recovery_fixture_store import SQLFixtureStore


def require(value,stage):
    if not value:
        raise RuntimeError(stage)


def safe_failure(directory):
    """Retain stage-only evidence before deleting private fixtures; never echo logs."""
    result=[]
    for path in sorted(Path(directory).rglob('*.log')):
        if path.stat().st_size>65536:
            continue
        for line in path.read_text(errors='replace').splitlines():
            if line.startswith('M3_MANAGED_NATIVE '):
                line=line[len('M3_MANAGED_NATIVE '):]
            elif not line.startswith('{'):
                continue
            try:value=json.loads(line)
            except ValueError:continue
            if not isinstance(value,dict) or value.get('schema') not in ('m3-native-recovery-result/v1','m3-managed-native-recheck/v1'):
                continue
            selected={'schema':value['schema']}
            allowed={
                'last_stage':{'review','single_use_claim','original_primary','native_inspection','sdk_start','native_resume','current_rpc_wait','sdk_drain','fresh_sdk_audit','owned_pool_close','receipt_seal','receipt_sealed','recorded_rpc_receipt','fresh_governance_verify','governance_commit'},
                'failure_stage':{'request','admin_start','broker_binding','physical_record','frozen_identity','finite_window','native_recheck','admin_shutdown'},
                'mode':{'inspect','resume'},'outcome':{'NotAttempted','Unknown','RecheckEnqueued'},
                'native_recheck_outcome':{'NotAttempted','Unknown','RecheckEnqueued'},
                'broker_final_outcome':{'not_attempted','unknown','commit_confirmed','rollback_confirmed'},
                'governance_outcome':{'not_attempted','unknown','commit_confirmed','already_resolved'},
                'failure_kind':{'IllegalArgumentException','NumberFormatException','MQBrokerException','MQClientException','RemotingException','RemotingConnectException','RemotingSendRequestException','RemotingTimeoutException','InterruptedException','UnknownHostException'},
            }
            for key,options in allowed.items():
                item=value.get(key)
                if isinstance(item,str) and item in options:
                    selected[key]=item
            if value.get('failure_kind') and 'failure_kind' not in selected:
                selected['failure_kind']='unclassified_runtime_failure'
            if selected:
                result.append(selected)
    return result[:16]


def fixture_manifest(repo,*,iam=False):
    document=json.loads((repo/'components/rocketmq/test-routes-v2.json').read_text())
    document['routes']=document['routes'][:3]
    ids={r['id'] for r in document['routes']}
    for route in document['routes']:
        if iam and route['owner']=='iam.mysql' and route['message_type']=='TRANSACTION':route['topic']='iam.authz.version.v2'
        route['route_revision']='m3-1'
        route['physical_topic']=physical_topic_v2(route['topic'],route['message_type'],route['owner'],'m3-1')
        route['consumer_group']=consumer_group_v2(route['topic'],route['subscription']) if route['subscription'] else ''
    for account in document['accounts'].values():
        for key in ('publish','subscriptions'):
            account[key]=[identity for identity in account[key] if identity in ids]
    return document


def physical_fingerprint(document,row):
    def field(value):return struct.pack('>I',len(value))+value
    raw=b'm3-native-limit-index-v1\x00'
    for value in (document['topic'].encode(),bytes.fromhex(document['key_sha256']),bytes.fromhex(row['broker_message_id'])):
        raw+=field(value)
    for name in ('queue_id','queue_offset','commitlog_offset','index_hour'):
        value=row[name]
        require(type(value) is int and value>=0,'exact_native_integer_required')
        raw+=struct.pack('>Q',value)
    return hashlib.sha256(raw).digest()


def notice_key(index,binding=None):
    raw=b'm3-native-limit-notice-v1\x00'
    binding=binding or dict(owner='iam.mysql',store_id='sdk-disposable',writer_epoch='sdk-epoch-1')
    for value in (binding['owner'].encode(),binding['store_id'].encode(),binding['writer_epoch'].encode(),b'm3-1',index):
        raw+=struct.pack('>I',len(value))+value
    return hashlib.sha256(raw).digest()


def accept(*,repo,binary,broker,project,directory,manifest,route,account,grpc_port,mysql_port,password,ca,
           java,identity,index_path,index,sql,run,consumer,passed,proof,governance_faults=False,original=None):
    proxy=MySQLCommitProxy(mysql_port).start() if governance_faults else None
    try:
        return _accept(repo=repo,binary=binary,broker=broker,project=project,directory=directory,manifest=manifest,route=route,account=account,
            grpc_port=grpc_port,mysql_port=mysql_port,password=password,ca=ca,java=java,identity=identity,index_path=index_path,index=index,
            sql=sql,run=run,consumer=consumer,passed=passed,proof=proof,proxy=proxy,original=original)
    finally:
        if proxy is not None:
            proof['governance_wire_proxy_cleanup']=proxy.close()


def _accept(*,repo,binary,broker,project,directory,manifest,route,account,grpc_port,mysql_port,password,ca,
           java,identity,index_path,index,sql,run,consumer,passed,proof,proxy,original):
    source=original or dict(owner="iam.mysql",store_id="sdk-disposable",writer_epoch="sdk-epoch-1",database="txprobe",user="txprobe",
        operation_id="op-"+identity,branch_id="branch-0",fence=1,business_count_sql="SELECT COUNT(*) FROM sdk_business",
        writer="fixed Go SDK source probe, not IAM business host",scope="one iam.mysql terminal commit, not the complete four-host/fault matrix")
    db=source.get('adapter') or SQLFixtureStore(sql,source['business_count_sql'])
    root=directory/'managed-cli';root.mkdir(mode=0o700)
    def write(name,value):
        path=root/name
        write_private(path,value)
        return path,hashlib.sha256(path.read_bytes()).hexdigest()
    def call(arguments,*,success=True):
        proof['managed_last_cli']=str(arguments[0])
        result=run([str(binary),*map(str,arguments)],required=False,timeout=225)
        require((result.returncode==0)==success,'compiled_managed_cli_outcome')
        if not success:return None
        value=json.loads(result.stdout)
        require(isinstance(value,dict),'single_safe_compiled_result_required')
        return value
    version=call(['version'])
    require(version['source_sha']==run(['git','rev-parse','HEAD'],cwd=repo).stdout.strip()
            and version['sdk_version']=='v0.5.0-rocketmq-tx.4' and version['effectful_commands'] is True,'fixed_published_cli_build_required')
    proof['managed_cli_build']=version
    # Source fixture installs only its owned governance table explicitly. The
    # CLI's constructor/start/preview never performs schema or binding writes.
    resource=repo/'tools/rocketmq-native-recovery/internal/authority/testdata/iam-000045-governance.sql'
    if original is None:
        require(hashlib.sha256(resource.read_bytes()).hexdigest()=='0d0df3ac8dcc10ebbe9e735ee0a8da600f0eefb3cdc6f33da276c975500e0e5a','frozen_host_governance_schema_required')
        sql(resource.read_text())
    owner_manifest=copy.deepcopy(manifest)
    owner_manifest['accounts']={name:dict(owner='',publish=[],subscriptions=[]) for name in
        ('m3-iam','m3-qs-apiserver','m3-qs-worker','m3-qs-mongo','m3-ai')}
    manifest_file,manifest_sha=write('reviewed-fixture-manifest.json',owner_manifest)
    docker=shutil.which('docker');require(docker is not None,'explicit_local_docker_binary_required')
    docker_config=root/'docker-config';docker_config.mkdir(mode=0o700)
    # CI only: broker is an exactly-owned disposable container. Production
    # freezes a direct Java child in a separately bounded helper image/cgroup.
    native_script=root/'owned-native-admin.sh'
    # Remove the legacy isolated-probe environment variables; the new child
    # receives only the private generated request from the reviewed Go wrapper.
    command=[docker,'--host','unix:///var/run/docker.sock','--config',str(docker_config),'exec','-i',broker,*java[java.index('java'):],'NativeHalfManaged']
    native_script.write_text('#!/bin/bash\nset -euo pipefail\nexec '+shlex.join(command)+' < "$1"\n');native_script.chmod(0o600)
    config=dict(schema='m3-native-recovery-config/v1',owner=source['owner'],store_id=source['store_id'],writer_epoch=source['writer_epoch'],
        database_kind=source.get('database_kind','mysql'),database_uri=source['database_uri'] if 'database_uri' in source else f"{source['user']}:{password}@tcp(127.0.0.1:{proxy.port if proxy else mysql_port})/{source['database']}",database_name=source['database'],database_ca_pem='',
        endpoint=f'127.0.0.1:{grpc_port}',access_key=account['username'],secret_key=account['password'],root_ca_pem=ca.read_text(),
        native_admin_script=str(native_script),native_admin_script_sha256=hashlib.sha256(native_script.read_bytes()).hexdigest(),
        native_admin_nameserver='nameserver:9876',native_admin_broker='127.0.0.1:10911')
    config_path,config_sha=write('original-config.json',config)
    source_bundle=hashlib.sha256(_encoded(dict(source=version['source_sha'],binary=version['binary_sha256'],config=config_sha,manifest=manifest_sha))).hexdigest()
    op=root/'operation'
    binding=dict(schema='m3-start-boundary/v1',operation_id='managed-native-recovery',directory=str(op),scope_sha256=hashlib.sha256(b'owned-iam-sdk-fixture').hexdigest(),
        protection_sha256=hashlib.sha256(index_path.read_bytes()).hexdigest(),restore_receipt_sha256=hashlib.sha256(b'fixture-removal-not-production-restore').hexdigest(),
        source_bundle_sha256=source_bundle,data_owner='synthetic-fixture-data-owner',recovery_owner='synthetic-fixture-recovery-owner')
    binding_sha=hashlib.sha256(_encoded(binding)).hexdigest();initialize(op,binding,binding_sha)
    def governed():
        return db.governance()
    def step(arguments,name,kind):
        script=root/(name+'.sh')
        # Actual coordinator-derived env avoids a self-referential script/plan
        # hash. Go revalidates the live binding/state/marker/reviewed plan.
        args=shlex.join([str(binary),*map(str,arguments)])
        script.write_text('#!/bin/bash\nset -euo pipefail\n'+args+' --directory "$M3_COORDINATOR_DIRECTORY" --binding-sha "$M3_COORDINATOR_BINDING_SHA256" --step "$M3_COORDINATOR_STEP" --step-plan-sha "$M3_COORDINATOR_STEP_PLAN_SHA256"\n');script.chmod(0o600)
        plan=dict(schema='m3-cutover-step/v1',directory=str(op),binding_sha256=binding_sha,host=socket.gethostname(),step=name,kind=kind,
            script=str(script),script_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),cwd=str(root),timeout_seconds=240)
        path=root/(name+'-plan.json');path.write_bytes(_encoded(plan));path.chmod(0o600)
        digest=hashlib.sha256(path.read_bytes()).hexdigest();loaded,raw=load_step(path,digest)
        try:execute(loaded,raw,digest)
        except Exception:
            proof['managed_failure_diagnostics']=safe_failure(op)
            raise
    row=index['records'][0];fingerprint=physical_fingerprint(index,row);key=notice_key(fingerprint,source)
    index_sha=hashlib.sha256(index_path.read_bytes()).hexdigest()
    if original is None:
        sql(f"INSERT INTO messaging_native_limit_notices(notice_key,owner,store_id,writer_epoch,route_revision,native_index_sha256,evidence_sha256,status,schema_version,recorded_at) VALUES(UNHEX('{key.hex()}'),'iam.mysql','sdk-disposable','sdk-epoch-1','m3-1',UNHEX('{fingerprint.hex()}'),UNHEX('{index_sha}'),'blocked',1,UTC_TIMESTAMP(6));")
    else:
        require(governed().split("\t")==[key.hex().upper(),index_sha.upper(),"blocked"],"actual_host_must_import_exact_original_index")
    before=governed()
    selection_path,selection_sha=write('selection.json',dict(schema='m3-native-recovery-selection/v1',operation_id=source['operation_id'],branch_id=source['branch_id'],fence=source['fence'],
        native_index_sha256=fingerprint.hex(),source_bundle_sha256=source_bundle,data_owner=binding['data_owner'],recovery_owner=binding['recovery_owner']))
    request_path=root/'request.json'
    preview=call(['preview','--config',config_path,'--config-sha',config_sha,'--manifest',manifest_file,'--manifest-sha',manifest_sha,
        '--export',index_path,'--export-sha',index_sha,'--selection',selection_path,'--selection-sha',selection_sha,'--output',request_path])
    require(preview['sdk_started'] is False and preview['governance_written'] is False and governed()==before,'preview_changed_original_governance')
    request=json.loads(request_path.read_text());request_sha=preview['request_sha256']
    require(request['snapshot']['local_decision']=='commit' and request['snapshot']['before_final']!='commit_confirmed','real_unconfirmed_original_root_required')
    passed('compiled_cli_preview_freezes_exact_original_primary_and_native_notice')
    approval=dict(schema='m3-native-recovery-approval/v1',action='recover',request_sha256=request_sha,receipt_sha256='',coordinator_binding_sha256=binding_sha,
        source_bundle_sha256=source_bundle,data_owner=binding['data_owner'],recovery_owner=binding['recovery_owner'],expires_at=request['expires_at'])
    approval_path,approval_sha=write('synthetic-recovery-approval.json',approval)
    common=['--config',config_path,'--config-sha',config_sha,'--manifest',manifest_file,'--manifest-sha',manifest_sha,'--export',index_path,'--export-sha',index_sha,
        '--request',request_path,'--request-sha',request_sha,'--approval',approval_path,'--approval-sha',approval_sha]
    # Before the first issued runtime boundary the same immutable request must
    # not create an attempt, start SDK or touch the native record.
    call(['recover',*common,'--directory',op,'--binding-sha',binding_sha,'--step','not-issued','--step-plan-sha','1'*64],success=False)
    require(not list(op.glob('native-attempt-*')) and governed()==before,'prestart_gate_created_effects')
    passed('compiled_recovery_refuses_before_real_first_runtime_boundary')
    step(['recover',*common],'recover-original','runtime-start')
    receipts=list(op.glob('native-attempt-*/receipt.json'));require(len(receipts)==1,'single_complete_current_rpc_receipt_required')
    receipt_path=receipts[0];raw=receipt_path.read_bytes();receipt_data=json.loads(raw);receipt_sha=hashlib.sha256(raw).hexdigest()
    stats=json.loads(receipt_data['runtime_stats'])
    require(receipt_data['request_sha256']==request_sha and receipt_data['invocation_nonce']==request['invocation_nonce'] and receipt_data['native_recheck_outcome']=='RecheckEnqueued'
        and stats['RecoveryCommitConfirmed']>=1 and stats['RecoveryAuditRecorded']==stats['RecoveryCommitConfirmed']+stats['RecoveryRollbackConfirmed']
        and stats['Stopped'] and stats['ActiveSends']==stats['RunningChecks']==stats['QueuedChecks']==0
        and stats['HalfPreparedResults']==stats['CompletedResults']==stats['LocalCommittedResults']==stats['Reconciled']==0,'genuine_checkonly_rpc_drain_required')
    require(governed()==before,'broker_confirmation_auto_resolved_governance')
    passed('published_sdk_actual_native_recheck_current_rpc_private_receipt_and_true_drain')
    consumer.wait('received',identity,decision=source['wire_hash'] if original else None,timeout=100)
    require(db.counts()=='1\t1\t1\t1','recovery_repeated_business_or_sent_new_half')
    passed('original_consumer_identity_and_one_original_business_root_preserved')
    first_audit=db.audit()
    require(first_audit.startswith('commit_confirmed\t'),'positive_sdk_primary_audit_required')
    approval['action']='resolve';approval['receipt_sha256']=receipt_sha
    resolve_path,resolve_sha=write('synthetic-resolution-approval.json',approval)
    common_resolve=common[:-4]+['--approval',resolve_path,'--approval-sha',resolve_sha,'--receipt',receipt_path,'--receipt-sha',receipt_sha]
    if proxy is None:
        step(['resolve-notice',*common_resolve],'resolve-original','forward-repair')
    else:
        def dropped(name,mode):
            proxy.arm(mode)
            try:step(['resolve-notice',*common_resolve],name,'forward-repair')
            except Exception:
                diagnosis=proof.get('managed_failure_diagnostics',[])
                require(any(d.get('last_stage')=='governance_commit' and d.get('governance_outcome')=='unknown'
                    and d.get('broker_final_outcome')=='commit_confirmed' for d in diagnosis),'separate_actual_broker_final_and_governance_unknown_required')
            else:raise RuntimeError('real_governance_commit_fault_was_not_reported_unknown')
        dropped('resolve-before-server-commit','before')
        require(proxy.events==[dict(mode='before',commit_forwarded=False,server_ok=False,reply_dropped=True)]
                and governed()==before,'before_commit_not_sent_or_rolled_back_scope_required')
        passed('actual_governance_commit_before_forward_drop_stays_unknown_and_notice_blocked')
        dropped('resolve-after-server-commit','after')
        require(len(proxy.events)==2 and proxy.events[-1]==dict(mode='after',commit_forwarded=True,server_ok=True,reply_dropped=True),
                'real_server_commit_ok_must_precede_dropped_reply')
        passed('actual_governance_server_commit_reply_drop_is_unknown_without_sdk_or_business_reexecution')
        proof['governance_wire_faults']=list(proxy.events)
    resolved=governed();require("resolved" in resolved and receipt_sha.upper() in resolved,'approved_exact_governance_commit_required')
    step(['verify-resolution',*common_resolve],'verify-original','forward-repair')
    require(governed()==resolved and first_audit==db.audit(),'verification_refreshed_first_evidence_or_sdk_audit')
    passed('independently_reviewed_actual_receipt_resolves_only_governance_and_fresh_verifies')
    # Same request is consumed, even in a newly issued forward-repair step.
    try:step(['recover',*common],'reject-reused-request','forward-repair')
    except Exception:pass
    else:raise RuntimeError('consumed_request_reexecuted')
    require(len(list(op.glob('native-attempt-*')))==1 and governed()==resolved,'rejected_reuse_changed_responsibilities')
    passed('new_issued_step_cannot_reexecute_a_consumed_recovery_request')
    after=export(broker,project,identity,root/'native-index-after.json')
    require(after['records']==index['records'] and hashlib.sha256(index_path.read_bytes()).hexdigest()==index_sha,'native_original_index_rewritten')
    passed('actual_managed_recovery_keeps_original_physical_index_and_first_notice_evidence')
    proof['managed_recovery']=dict(request_sha256=request_sha,receipt_sha256=receipt_sha,native_index_sha256=fingerprint.hex(),
        actual_sdk_stats=stats,original_counts=dict(business=1,requests=1,executions=1,witnesses=1),first_primary_audit_preserved=True,
        approved_governance_resolved=True,same_request_reexecution_refused=True,private_observations=len(receipt_data['observations']),
        production=False,system_acceptance=False,reviewers='synthetic fixture',original_writer=source['writer'],scope=source['scope'])
