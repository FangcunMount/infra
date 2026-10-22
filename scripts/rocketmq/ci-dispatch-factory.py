#!/usr/bin/env python3
"""Owned dual-store default-factory proof; never starts a Broker or business host."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time

from iam_acceptance import host_failure_summary

CASES = frozenset(('original_handles_and_inert_factory', 'missing_schema_rejected_before_loops',
    'explicit_dual_store_preflight', 'foreign_original_handles_rejected', 'fresh_authoritative_binding_reads',
    'original_transaction_context_refused', 'empty_factory_dispatch_never_starts_sender_or_business',
    'real_mysql_metadata_lock_respects_fresh_budget', 'factory_cleanup_preserves_host_database_ownership', 'duplicate_owner_runtime_refused'))
SCOPE = 'actual default dispatch factory; original MySQL and MongoDB preflight and empty scans'
MONGO = 'mongo@sha256:340c1c56fb10e95cf79ff547f8664b96bc6ead9909bc355238cbf865a9695a6f'


def parse_receipt(output, source):
    rows = [json.loads(line.split('M3_QS_DISPATCH_FACTORY_RECEIPT ', 1)[1])
            for line in output.splitlines() if line.startswith('M3_QS_DISPATCH_FACTORY_RECEIPT ')]
    if len(rows) != 1:
        raise RuntimeError('one exact factory receipt required')
    value = rows[0]
    if (not re.fullmatch('[0-9a-f]{40}', source) or value.get('source_sha') != source
            or value.get('passed') != len(CASES) or value.get('failed') != 0 or value.get('skipped') != 0
            or set(value.get('cases', {})) != CASES or any(v is not True for v in value['cases'].values())
            or value.get('scope') != SCOPE
            or any(value.get(k) is not True for k in ('broker_or_business_dispatch_not_claimed',
                'complete_host_startup_not_claimed', 'system_login_not_claimed',
                'owned_databases_dropped', 'original_client_closed_by_fixture'))
            or not re.search(r'--- PASS: TestM3DefaultDispatchFactory \(', output)
            or re.search(r'--- (?:SKIP|FAIL):|WARNING: DATA RACE', output)):
        raise RuntimeError('factory receipt incomplete, wrong source, failed, skipped or cleanup unverified')
    return value


def command(argv, *, required=True, timeout=180, **kwargs):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, **kwargs)
    if required and result.returncode:
        raise RuntimeError('owned fixture command failed; private output withheld')
    return result


def unused_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


class EndpointTrap:
    def __init__(self):
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0)); self.listener.listen(8); self.listener.settimeout(.1)
        self.endpoint = '127.0.0.1:' + str(self.listener.getsockname()[1])
        self.connections = 0
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self.serve)
        self.thread.start()

    def serve(self):
        while not self.stopping.is_set():
            try:
                conn, _ = self.listener.accept()
                self.connections += 1
                conn.close()  # Never read credentials or application bytes.
            except socket.timeout:
                continue
            except OSError:
                return

    def close(self):
        self.stopping.set(); self.thread.join(2)
        if self.thread.is_alive():
            self.listener.close(); return False
        self.listener.setblocking(False)
        while True:
            try:
                conn, _ = self.listener.accept(); self.connections += 1; conn.close()
            except BlockingIOError:
                break
        self.listener.close()
        return True


def native_run(argv, *, env, source, proof):
    process = subprocess.Popen(argv, cwd=source, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        output, _ = process.communicate(timeout=300)
        return process.returncode, output
    finally:
        for sig, pause in ((signal.SIGTERM, .2), (signal.SIGKILL, .2)):
            try:
                os.killpg(process.pid, sig)
                time.sleep(pause)
            except ProcessLookupError:
                break
        if process.poll() is None:
            process.wait(timeout=5)
        drained = False
        for _ in range(30):
            try:
                os.killpg(process.pid, 0)
                time.sleep(.1)
            except ProcessLookupError:
                drained = True; break
        proof['owned_process_groups_drained'] = drained
        if not drained:
            raise RuntimeError('owned native process group remained after wait')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--mysql-image', choices=('mysql:8.0.36','mysql:8.0.44','mysql:8.4.11'), default='mysql:8.0.36')
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    if command(['git','status','--porcelain'], cwd=source).stdout.strip():
        raise RuntimeError('clean fixed source required')
    source_sha = command(['git','rev-parse','HEAD'], cwd=source).stdout.strip()
    module = json.loads(command(['go','list','-m','-json','github.com/FangcunMount/reliable-messaging'], cwd=source, env=dict(os.environ,GOWORK='off',GOFLAGS='-mod=readonly')).stdout)
    if module.get('Replace') or module.get('Version') != 'v0.5.0-rocketmq-tx.2' or not module.get('Sum'):
        raise RuntimeError('fixed published SDK required without replacement')
    root = Path(tempfile.mkdtemp(prefix='rocketmq-m2-factory-')); root.chmod(0o700)
    project = 'rocketmq-m2-factory-' + secrets.token_hex(5)
    compose_file = root/'compose.json'
    compose = ['docker','compose','-p',project,'-f',str(compose_file)]
    password = secrets.token_hex(32)
    sql_port, mongo_port = unused_port(), unused_port()
    trap = EndpointTrap()
    proof = {'source_sha':source_sha,'sdk_module':{k:module.get(k) for k in ('Path','Version','Sum','GoModSum')},
             'owned_process_groups_drained': True}
    cleanup, failure, receipt = {}, None, None
    spec = {'services':{
        'mysql':{'image':args.mysql_image,'environment':{'MYSQL_ROOT_PASSWORD':password,'MYSQL_ROOT_HOST':'%'},
            'ports':[f'127.0.0.1:{sql_port}:3306'],'tmpfs':['/var/lib/mysql'],'mem_limit':'512m','cpus':1,
            'healthcheck':{'test':['CMD-SHELL','MYSQL_PWD=$$MYSQL_ROOT_PASSWORD mysql -uroot -e "SELECT 1"'],
                          'interval':'2s','timeout':'3s','retries':60}},
        'mongo':{'image':MONGO,'command':['mongod','--replSet','sdk-proof','--bind_ip_all','--wiredTigerCacheSizeGB','0.25'],
            'ports':[f'127.0.0.1:{mongo_port}:27017'],'tmpfs':['/data/db','/data/configdb'],'mem_limit':'512m','cpus':1,
            'healthcheck':{'test':['CMD','mongosh','--quiet','--eval','db.adminCommand({ping:1})'],
                          'interval':'2s','timeout':'3s','retries':60}}}}
    compose_file.write_text(json.dumps(spec)); compose_file.chmod(0o600)
    try:
        for name, image in (('mysql_image',args.mysql_image),('mongo_image',MONGO)):
            command(['docker','pull',image], timeout=300)
            proof[name] = command(['docker','image','inspect',image,'--format','{{.Id}}']).stdout.strip()
        command(compose+['up','-d','--wait','--wait-timeout','180'],timeout=240)
        mongo = project+'-mongo-1'
        command(['docker','exec',mongo,'mongosh','--quiet','--eval',
            'rs.initiate({_id:"sdk-proof",members:[{_id:0,host:"localhost:27017"}]})'])
        for _ in range(60):
            result=command(['docker','exec',mongo,'mongosh','--quiet','--eval',
                'if(rs.status().myState!==1){quit(1)}'], required=False)
            if result.returncode==0:break
            time.sleep(.5)
        else:raise RuntimeError('owned Mongo primary unavailable')
        proof['mysql_version']=command(['docker','exec',project+'-mysql-1','sh','-c',
            'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B -e "SELECT VERSION()"']).stdout.strip()
        proof['mongo_version']=command(['docker','exec',mongo,'mongosh','--quiet','--eval','db.version()']).stdout.strip()
        command(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=owned-factory-trap',
                 '-keyout',str(root/'key.pem'),'-out',str(root/'ca.pem')])
        (root/'key.pem').chmod(0o600)
        routes=Path(__file__).resolve().parents[2]/'components/rocketmq/serverd-routes-m3-v2.json'
        shutil.copyfile(routes,root/'routes.json'); (root/'routes.json').chmod(0o600)
        credentials={}
        for owner in ('qs.mysql','qs.mongo'):
            path=root/(owner+'.json');path.write_text(json.dumps({'username':owner+'-inert-fixture','password':secrets.token_hex(32)}));path.chmod(0o600);credentials[owner]=path
        config={'provider':'rocketmq','enabled':True,'rocketmq':{'endpoint':trap.endpoint,'credentials_file':str(credentials['qs.mysql']),
            'ca_file':str(root/'ca.pem'),'routes_file':str(root/'routes.json'),'publish_enabled':True,'transactions':{
                owner:{'credentials_file':str(credentials[owner]),'store_id':owner+'-factory-original',
                       'writer_epoch':'m3-1','route_revision':'m3-1'} for owner in credentials}}}
        options=root/'options.json';options.write_text(json.dumps(config));options.chmod(0o600)
        env=dict(os.environ,GOWORK='off',GOFLAGS='-mod=readonly',QS_M3_FIXTURE_PROJECT=project,
            QS_M3_FACTORY_DSN=f'root:{password}@tcp(127.0.0.1:{sql_port})/?parseTime=true',
            QS_M3_FACTORY_MONGO_URI=f'mongodb://127.0.0.1:{mongo_port}/?replicaSet=sdk-proof&directConnection=true',QS_M3_FACTORY_OPTIONS=str(options))
        code,output=native_run(['go','test','-race','-p','1','-tags=integration,m3_dispatch_factory','-run','^TestM3DefaultDispatchFactory$',
            '-count=1','-v','-timeout=3m','./internal/apiserver/container'],env=env,source=source,proof=proof)
        private=root/'native-private.log';private.write_text(output);private.chmod(0o600)
        proof['native_exit_code']=code;proof['native_output_sha256']=hashlib.sha256(output.encode()).hexdigest()
        proof['diagnostics']=host_failure_summary(output)
        proof['diagnostics']['assertion_lines']=sorted(set(map(int,re.findall(r'retry_dispatch_native_integration_test\.go:(\d+)',output))))[:32]
        if code:raise RuntimeError('native default factory failed; private output withheld')
        receipt=parse_receipt(output,source_sha)
        if trap.connections:raise RuntimeError('inert factory attempted to connect to the endpoint trap')
        proof['endpoint_connections']=trap.connections
        proof['source_clean_after']=not command(['git','status','--porcelain'],cwd=source).stdout.strip()
        if not proof['source_clean_after']:raise RuntimeError('source changed during factory proof')
    except Exception as exc:
        failure=type(exc).__name__+': owned factory proof failed; private output withheld'
    finally:
        cleanup['owned_endpoint_trap_joined']=trap.close()
        proof['endpoint_connections']=trap.connections
        if trap.connections:failure=failure or 'inert endpoint observed an unexpected connection'
        cleanup['compose_down_succeeded']=command(compose+['down','--volumes','--remove-orphans','--timeout','20'],required=False,timeout=120).returncode==0
        cleanup['project_containers_remaining']=bool(command(['docker','ps','-aq','--filter','label=com.docker.compose.project='+project]).stdout.strip())
        if not root.name.startswith('rocketmq-m2-factory-') or not project.startswith('rocketmq-m2-factory-'):
            raise RuntimeError('fixture ownership guard failed')
        shutil.rmtree(root)
        cleanup['private_fixture_removed']=not root.exists()
        cleanup['owned_process_groups_drained']=proof['owned_process_groups_drained']
        if cleanup['project_containers_remaining'] or any(not value for key,value in cleanup.items() if key!='project_containers_remaining'):
            failure=failure or 'owned fixture cleanup incomplete'
        report={'version':1,'batch':'M3-QS-default-dispatch-factory-original-dual-store','project':project,
            'passed':0 if receipt is None else len(CASES),'failed':int(failure is not None),'skipped':0,
            'failure':failure,'native_receipt':receipt,'proof':proof,'cleanup':cleanup,
            'limits':['No Broker, business dispatch, full-host startup, provider, production or system claim; endpoint is an inert owned trap']}
        args.report.write_text(json.dumps(report,indent=2)+'\n');args.report.chmod(0o600)
    if failure:raise SystemExit(1)


if __name__=='__main__':main()
