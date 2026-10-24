"""Actual IAM original writer for the CI-owned native recovery fixture.

Private control files carry original identities. Public evidence contains only
source/module hashes, exact counters and fixed assertions, never a DSN or wire.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import time
from audit_transaction_limit import write_private


def require(value,stage):
    if not value:raise RuntimeError(stage)


def metadata(value):
    keys={'database','owner','store_id','writer_epoch','operation_id','branch_id','fence','message_id'}
    require(isinstance(value,dict) and set(value)==keys,'exact_original_host_metadata_required')
    require(value['owner']=='iam.mysql' and value['store_id']=='iam-native-primary' and value['writer_epoch']=='m3-1','original_host_binding_required')
    require(isinstance(value['database'],str) and re.fullmatch(r'iam_m3_broker_test_[0-9]{10,30}',value['database']),'owned_original_database_required')
    require(type(value['fence']) is int and 1<=value['fence']<=2**63-1,'exact_original_fence_required')
    for key in ('operation_id','branch_id','message_id'):
        require(isinstance(value[key],str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',value[key]),'bounded_original_identity_required')
    return dict(value,user='root',business_count_sql="SELECT COUNT(*) FROM authz_roles WHERE name='m3:native_recovery_original'",
        writer='actual IAM WithinPlannedTx original GORM role/version/witness root',
        scope='one original IAM host commit with actual Broker network disconnection; not whole API, SIGKILL or system')


class IAMHost:
    def __init__(self,*,source,directory,project,route,grpc_port,mysql_port,password,ca,account,run,common,probes,proof):
        source=source.resolve()
        require((source/'go.mod').is_file() and not run(['git','status','--porcelain'],cwd=source).stdout,'clean_original_host_source_required')
        source_sha=run(['git','rev-parse','HEAD'],cwd=source).stdout.strip()
        require(re.fullmatch('[0-9a-f]{40}',source_sha),'exact_original_host_source_required')
        env=dict(os.environ,GOWORK='off',GOFLAGS='-mod=readonly')
        module=json.loads(run(['go','list','-m','-json','github.com/FangcunMount/reliable-messaging'],cwd=source,env=env).stdout)
        require(not module.get('Replace') and module['Version']=='v0.5.0-rocketmq-tx.4'
            and module['Sum']=='h1:PflI1oWRjU4RFKvpi8WE/8ICI/1IUp8q8EOsbW1DXCI=','fixed_original_host_module_required')
        control=directory/'iam-native-recovery';control.mkdir(mode=0o700)
        self.control,self.source,self.run,self.proof=control,source,run,proof
        def write(name,value):
            path=control/name;write_private(path,value);return path
        credentials=write('credentials.json',dict(username=account['username'],password=account['password']))
        manifest=write('routes.json',dict(version=2,routes=[route]))
        config=write('options.json',dict(provider='rocketmq',endpoint=f'127.0.0.1:{grpc_port}',credentials_file=str(credentials),ca_file=str(ca),
            routes_file=str(manifest),instance_id='iam-native-recovery-fixture',publish_enabled=True,
            transactions={'iam.mysql':dict(store_id='iam-native-primary',writer_epoch='m3-1',route_revision='m3-1')}))
        binary=directory/'iam-native-recovery-test'
        run(['go','test','-race','-tags=integration,m3_iam_runtime','-c','-o',str(binary),'./internal/pkg/migration'],cwd=source,env=env,timeout=300)
        env.update(IAM_M3_FIXTURE_PROJECT=project,IAM_M3_TEST_MYSQL_DSN=f'root:{password}@tcp(127.0.0.1:{mysql_port})/mysql?parseTime=true&multiStatements=true',
            IAM_M3_BROKER_CONFIG=str(config),IAM_M3_NATIVE_RECOVERY_DIRECTORY=str(control))
        self.probe=common.Probe([str(binary),'-test.v','-test.timeout=6m','-test.run=^TestM3ActualOwnerNativeRecovery$'],directory,env,cwd=source)
        probes.append(self.probe)
        proof['iam_original_host']=dict(source_sha=source_sha,sdk_version=module['Version'],sdk_sum=module['Sum'],binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
            whole_api=False,sigkill=False,system_acceptance=False)

    def wait(self,name,timeout=80):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            path=self.control/name
            if path.exists():
                require(not path.is_symlink() and path.is_file() and path.stat().st_mode&0o077==0,'private_original_control_required')
                return json.loads(path.read_text())
            if self.probe.process.poll() is not None:
                self.failure();raise RuntimeError('original_host_exited_before_private_control')
            time.sleep(.1)
        self.failure();raise RuntimeError('original_host_private_control_timeout')

    def signal(self,name):write_private(self.control/name,dict(continue_owned_fixture=True))

    def failure(self):
        raw=Path(self.probe.log.name).read_text(errors='replace')
        self.proof['iam_host_failure']=dict(exit_code=self.probe.process.poll(),output_sha256=hashlib.sha256(raw.encode()).hexdigest(),
            race_reports=raw.count('WARNING: DATA RACE'),assertion_lines=sorted(set(map(int,re.findall(r'transaction_recovery_native_integration_test.go:(\d+)',raw))))[:32])

    def finish(self):
        self.signal('verify')
        try:self.probe.finish(timeout=40)
        except Exception:self.failure();raise
        self.probe.log.flush();raw=Path(self.probe.log.name).read_text()
        rows=[json.loads(line.split('M3_IAM_NATIVE_RECOVERY ',1)[1]) for line in raw.splitlines() if 'M3_IAM_NATIVE_RECOVERY {' in line]
        require(len(rows)==1 and rows[0]==dict(passed=5,failed=0,skipped=0,original_root_once=True,real_broker_disconnect=True,
            published_sdk_rpc_verified_by_caller=True,resolved_primary_and_paused_replacement=True,system_acceptance=False)
            and '--- PASS: TestM3ActualOwnerNativeRecovery ' in raw and '--- SKIP:' not in raw and '--- FAIL:' not in raw
            and 'WARNING: DATA RACE' not in raw,'actual_original_host_final_assertions_required')
        require(not self.run(['git','status','--porcelain'],cwd=self.source).stdout,'original_host_source_changed')
        self.proof['iam_original_host'].update(receipt=rows[0],private_output_sha256=hashlib.sha256(raw.encode()).hexdigest(),source_clean=True)
