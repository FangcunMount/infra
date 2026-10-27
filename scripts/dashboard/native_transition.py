"""Single-use serverD native-port transition. Root journal survives SSH loss.

Does not operate serverA, DNS, business databases, workers or NameServer.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import time

from config import render
from firewall import install
from native_broker import add_native_port,critical,digest,healthy,inspect,override,ports,run

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'scripts/rocketmq'))
from provision_v2 import Admin
from admin_audit import snapshot_existing_acls

ROOT=Path('/data/infra/rocketmq-dashboard')
BIND='100.118.164.39';INGRESS='100.74.123.45';NETWORK='rocketmq_rocketmq'


def private(path,value):
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as stream:
        json.dump(value,stream,indent=2);stream.flush();os.fsync(stream.fileno())


def save(path,value):
    temp=path.with_name('.'+path.name+'.'+str(time.time_ns()))
    private(temp,value);os.replace(temp,path)
    fd=os.open(path.parent,os.O_DIRECTORY|os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def trust_bundle(rows):
    result=[];fingerprints={}
    for row,port in rows:
        current=inspect(row['Name'].lstrip('/'))
        if current['Id']!=row['Id'] or current['Image']!=row['Image']:
            raise RuntimeError('trust_source_container_changed')
        host=current['NetworkSettings']['Networks'][NETWORK]['IPAddress']
        # Peer discovery is over the authenticated host's own Docker network.
        # The immutable image/container identity and fresh fingerprint are saved;
        # Dashboard itself always verifies TLS against this exact bundle.
        with socket.create_connection((host,port),timeout=5) as sock:
            with ssl._create_unverified_context().wrap_socket(sock,server_hostname=host) as tls:
                der=tls.getpeercert(binary_form=True)
        fingerprints[row['Name'].lstrip('/')]=hashlib.sha256(der).hexdigest()
        result.append(ssl.DER_cert_to_PEM_cert(der).encode())
    return b''.join(result),fingerprints


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--operation',type=Path,required=True)
    parser.add_argument('--preflight-only',action='store_true')
    args=parser.parse_args()
    if os.geteuid()!=0:raise RuntimeError('root_required')
    if args.plan.stat().st_mode&0o077:raise RuntimeError('private_plan_required')
    plan=json.loads(args.plan.read_text())
    if plan['version']!='dashboard-native-servera/v1' or plan['source_sha']!=REPO.name:
        raise RuntimeError('frozen_source_required')
    if BIND not in run(['tailscale','ip','-4']).stdout.split():raise RuntimeError('host_identity_changed')
    args.operation.mkdir(mode=0o700,parents=True,exist_ok=False)
    state=dict(version=plan['version'],source_sha=plan['source_sha'],events=[],status='preflight',store_restored=False)
    def checkpoint(phase,**fields):
        state['status']=phase;state['events'].append(dict(phase=phase,at=time.time(),**fields));save(args.operation/'state.json',state)
    with open('/var/lib/fangcun-image-retention/deploy.lock','rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        names=['rocketmq-broker-1','rocketmq-nameserver-1','rocketmq-dashboard-dashboard-1','rocketmq-dashboard-gateway-1']
        before={name:inspect(name) for name in names}
        for name,row in before.items():
            if row['Id']!=plan['containers'][name] or not row['State']['Running']:
                raise RuntimeError('original_container_identity_changed')
        broker=before[names[0]];ns=before[names[1]]
        if broker['Image']!=plan['broker_image']:raise RuntimeError('original_broker_image_changed')
        source=Path(plan['compose_file']);environment=Path(plan['environment_file'])
        if digest(source)!=plan['compose_sha256'] or digest(environment)!=plan['environment_sha256']:
            raise RuntimeError('original_compose_environment_changed')
        firewall_unit=Path('/etc/systemd/system/rocketmq-dashboard-firewall.service')
        if digest(firewall_unit)!=plan['firewall_unit_sha256']:raise RuntimeError('firewall_unit_changed')
        workers={name:inspect(name) for name in ['qs-worker-runtime-1','qs-worker-runtime-2','qs-worker-runtime-3']}
        if any(not row['State']['Running'] for row in workers.values()):raise RuntimeError('worker_not_running')
        private(args.operation/'before.private.json',dict(containers=before,workers=workers))
        original=['docker','compose','--env-file',str(environment),'-p','rocketmq','-f',str(source)]
        preview=json.loads(run(original+['config','--format','json']).stdout)['services']['broker']
        if run(['docker','image','inspect',preview['image'],'--format','{{.Id}}']).stdout.strip()!=broker['Image']:
            raise RuntimeError('declared_image_differs_from_runtime')
        declared=preview.get('environment',{})
        actual=dict(item.split('=',1) for item in broker['Config']['Env'])
        if any(actual.get(key)!=str(value) for key,value in declared.items()):raise RuntimeError('declared_environment_drift')
        config_paths=[Path(m['Source']) for m in broker['Mounts'] if m['Destination']=='/etc/rocketmq']
        if len(config_paths)!=1:raise RuntimeError('exact_broker_config_mount_required')
        config_hashes={p.name:digest(p) for p in config_paths[0].iterdir() if p.is_file()}
        size=sum(p.stat().st_size for target in ['store','auth','config']
            for p in Path('/data/infra/rocketmq',target).rglob('*') if p.is_file())
        if shutil.disk_usage(args.operation).free<size*2+1024**3:raise RuntimeError('cold_backup_capacity_required')
        admin=Admin(names[0]);users=admin.users();metadata=admin.metadata('/tmp/dashboard-native-before-'+str(time.time_ns()))
        acls=snapshot_existing_acls(admin,users)
        private(args.operation/'broker-metadata.private.json',dict(users=users,tables=metadata,acls=acls))
        old_policy=run(['iptables','-S','INFRA-ROCKETMQ']).stdout
        overlay=args.operation/'native-rpc.override.json';override(overlay,broker,BIND)
        recovery=args.operation/'recovery.override.json'
        private(recovery,dict(services=dict(broker=dict(hostname=broker['Config']['Hostname']))))
        private(args.operation/'commands.private.json',dict(active=[*original,'-f',str(overlay)],
            recovery=[*original,'-f',str(recovery)],backup_restore_after_first_start_allowed=False))
        checkpoint('preflight_verified')
        if args.preflight_only:
            print(json.dumps(dict(preflight_passed=True,production_services_changed=False,
                estimated_backup_bytes=size,operation=str(args.operation))))
            return
        new_broker=None
        try:
            checkpoint('management_stop_issued')
            run(['docker','stop','--time','30',names[2]],timeout=45)
            run(['docker','stop','--time','15',names[3]],timeout=30)
            run(['docker','rm',names[3]])
            checkpoint('management_closed')
            policy=install(BIND,NETWORK,INGRESS)
            unit='''[Unit]\nDescription=Private RocketMQ Dashboard native forwarding policy\nAfter=docker.service tailscaled.service\nRequires=docker.service\nPartOf=docker.service\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/usr/bin/python3 %s/scripts/dashboard/firewall.py --bind-ip %s --network %s --web-source %s\n[Install]\nWantedBy=multi-user.target\n'''%(REPO,BIND,NETWORK,INGRESS)
            firewall_unit.write_text(unit);firewall_unit.chmod(0o644)
            run(['systemctl','daemon-reload']);run(['systemctl','restart',firewall_unit.name])
            new_broker,backup=add_native_port(broker,original,overlay,args.operation,BIND,checkpoint)
            # Current store is authoritative after the first native start.
            after_users=admin.users();after_metadata=admin.metadata('/tmp/dashboard-native-after-'+str(time.time_ns()))
            if any(after_users.get(key)!=value for key,value in users.items()):raise RuntimeError('existing_broker_user_changed')
            if snapshot_existing_acls(admin,users)!=acls:raise RuntimeError('existing_broker_acl_changed')
            if any(any(after_metadata[table].get(key)!=value for key,value in rows.items()) for table,rows in metadata.items()):
                raise RuntimeError('existing_broker_inventory_changed')
            ca,fingerprints=trust_bundle([(ns,9876),(new_broker,10911)])
            accounts=json.loads((ROOT/'credentials.json').read_text())
            cfg=args.operation/'dashboard-private';render(cfg,accounts['ui'],accounts['broker'],ca)
            for path in [cfg,*cfg.iterdir()]:os.chown(path,10001,10001)
            env=dict(os.environ,DASHBOARD_CONFIG_ROOT=str(cfg),DASHBOARD_BIND_IP=BIND,DASHBOARD_BROKER_NETWORK=NETWORK)
            compose=['docker','compose','-p','rocketmq-dashboard','-f',str(REPO/'components/rocketmq-dashboard/docker-compose.yml')]
            checkpoint('dashboard_start_issued',certificate_fingerprints=fingerprints)
            result=subprocess.run(compose+['up','-d','--remove-orphans','--pull','never','dashboard'],env=env,capture_output=True,timeout=100)
            if result.returncode:raise RuntimeError('dashboard_native_start_failed')
            # HTTP readiness only: authenticated acceptance is performed through
            # the real serverA HTTPS origin, where Secure cookies can be used.
            from acceptance import client,request
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                try:
                    code,value=request(client(),'http://'+BIND+':18082','/login/check.query')
                    if code==200 and value.get('data',{}).get('loginRequired'):break
                except (OSError,ValueError):pass
                time.sleep(2)
            else:raise RuntimeError('dashboard_native_not_ready')
            app=inspect(names[2]);now_ns=inspect(names[1])
            cases=dict(broker_runtime_preserved=critical(new_broker)==critical(broker),
                broker_native_port_only=ports(new_broker)=={**ports(broker),'10911/tcp':[(BIND,'10911')]},
                users_preserved=True,acls_preserved=True,inventory_preserved=True,current_store_retained=True,
                nameserver_unchanged=now_ns['Id']==ns['Id'] and now_ns['State']['StartedAt']==ns['State']['StartedAt'],
                workers_unchanged=all(inspect(name)['Id']==row['Id'] and inspect(name)['State']['StartedAt']==row['State']['StartedAt'] for name,row in workers.items()),
                original_config_unchanged=all(digest(config_paths[0]/name)==value for name,value in config_hashes.items()),
                original_firewall_unchanged=run(['iptables','-S','INFRA-ROCKETMQ']).stdout==old_policy,
                dashboard_nonroot_readonly=app['Config']['User']=='10001:10001' and app['HostConfig']['ReadonlyRootfs'],
                no_dashboard_oom=not app['State']['OOMKilled'],
                serverd_nginx_removed=run(['docker','ps','-aq','--filter','label=com.docker.compose.project=rocketmq-dashboard','--filter','label=com.docker.compose.service=gateway']).stdout.strip()=='')
            if not all(cases.values()):raise RuntimeError('native_transition_incomplete')
            receipt=dict(passed=len(cases),failed=0,skipped=0,cases=cases,firewall=policy,backup=backup,
                certificate_fingerprints=fingerprints,broker_before=broker['Id'],broker_after=new_broker['Id'],
                broker_image=new_broker['Image'],dashboard=app['Id'],dashboard_config=str(cfg),
                source_sha=plan['source_sha'],store_restored=False,https_acceptance_pending=True)
            private(args.operation/'receipt.json',receipt)
            private(ROOT/'active-native.json',dict(source_sha=plan['source_sha'],operation=str(args.operation),
                dashboard_config=str(cfg),broker_compose=[*original,'-f',str(overlay)],dashboard_compose=compose,
                dashboard_environment={key:env[key] for key in ['DASHBOARD_CONFIG_ROOT','DASHBOARD_BIND_IP','DASHBOARD_BROKER_NETWORK']}))
            checkpoint('backend_ready_awaiting_https')
            print(json.dumps(receipt))
        except Exception:
            checkpoint('transition_failed')
            try:current=inspect(names[0])
            except RuntimeError:current=None
            if current is None or not current['State']['Running'] or current['State'].get('Health',{}).get('Status')!='healthy':
                checkpoint('current_store_recovery_issued')
                run([*original,'-f',str(recovery),'up','-d','--no-deps','--pull','never','broker'],timeout=120)
                healthy(names[0]);checkpoint('current_store_recovery_healthy')
            raise


if __name__=='__main__':main()
