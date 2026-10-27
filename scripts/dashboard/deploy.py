"""Explicit serverD-only Dashboard installation; never restarts the Broker."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

from config import render
from acceptance import client, request, verify
from firewall import install

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'scripts/rocketmq'))
from provision_v2 import Admin

ROOT=Path('/data/infra/rocketmq-dashboard')
BIND='100.118.164.39'
NETWORK='rocketmq_rocketmq'
BROKER='rocketmq-broker-1'
EXPECTED_IMAGE='sha256:6387937671866c6ca6c973b8e5df649ce101463e95f4e300c5455b2975bf3353'


def run(args, *, timeout=60, required=True, env=None):
    value=subprocess.run(args,capture_output=True,text=True,timeout=timeout,env=env)
    if required and value.returncode:
        raise RuntimeError('private_install_command_failed')
    return value


def inspect(names):
    return json.loads(run(['docker','inspect',*names]).stdout)


def private(path, value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(value,stream,indent=2)


def memory():
    return int(next(row.split()[1] for row in Path('/proc/meminfo').read_text().splitlines()
        if row.startswith('MemAvailable:')))//1024


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-broker-id',required=True)
    args=parser.parse_args()
    if os.geteuid()!=0:raise RuntimeError('root_required')
    if BIND not in run(['tailscale','ip','-4']).stdout.split():raise RuntimeError('host_identity_changed')
    # Borrow the existing deploy lock without creating or changing its inode.
    with open('/var/lib/fangcun-image-retention/deploy.lock','rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        before=inspect([BROKER,'rocketmq-nameserver-1'])
        broker=before[0]
        if broker['Id']!=args.expected_broker_id or broker['Image']!=EXPECTED_IMAGE:
            raise RuntimeError('original_broker_identity_changed')
        if not all(row['State']['Running'] for row in before):raise RuntimeError('original_mq_not_running')
        if memory()<1000:raise RuntimeError('insufficient_preinstall_memory')
        env=dict(os.environ,DASHBOARD_CONFIG_ROOT=str(ROOT/'private'),DASHBOARD_BIND_IP=BIND,
            DASHBOARD_BROKER_NETWORK=NETWORK)
        compose=['docker','compose','-p','rocketmq-dashboard','-f',str(REPO/'components/rocketmq-dashboard/docker-compose.yml')]
        if run(compose+['ps','-q'],env=env).stdout.strip():raise RuntimeError('dashboard_already_exists')
        ROOT.mkdir(mode=0o700,exist_ok=True)
        credential_path=ROOT/'credentials.json'
        if credential_path.exists():
            if credential_path.stat().st_mode&0o077:raise RuntimeError('unsafe_credential_permissions')
            accounts=json.loads(credential_path.read_text())
        else:
            accounts={kind:dict(username=name,password=secrets.token_hex(32)) for kind,name in
                [('ui','dashboard-admin'),('broker','dashboard-management')]}
            private(credential_path,accounts)
        admin=Admin(BROKER)
        users=admin.users();account=accounts['broker']
        if account['username'] in users:
            row=users[account['username']]
            if row[0]!=account['password'] or tuple(x.lower() for x in row[1:])!=('super','enable'):
                raise RuntimeError('existing_dashboard_identity_conflict')
        else:
            admin('createUser','-u',account['username'],'-p',account['password'],'-t','Super',mutation=True)
        after_users=admin.users()
        if any(after_users.get(name)!=value for name,value in users.items()):
            raise RuntimeError('existing_principal_changed')
        if after_users[account['username']][0]!=account['password']:
            raise RuntimeError('dedicated_identity_not_confirmed')
        config=ROOT/'private'
        if not config.exists():
            render(config,accounts['ui'],account,Path('/data/infra/rocketmq/config/tls/server.crt').read_bytes())
        if config.stat().st_mode&0o077:raise RuntimeError('unsafe_config_directory')
        for path in [config,*config.iterdir()]:os.chown(path,10001,10001)
        firewall=install(BIND,NETWORK)
        unit=Path('/etc/systemd/system/rocketmq-dashboard-firewall.service')
        content='''[Unit]
Description=Private RocketMQ Dashboard Docker forwarding policy
After=docker.service tailscaled.service
Requires=docker.service
PartOf=docker.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/python3 %s/scripts/dashboard/firewall.py --bind-ip %s --network %s
[Install]
WantedBy=multi-user.target
'''%(REPO,BIND,NETWORK)
        if unit.exists() and unit.read_text()!=content:raise RuntimeError('existing_firewall_unit_conflict')
        unit.write_text(content);unit.chmod(0o644)
        run(['systemctl','daemon-reload'])
        run(['systemctl','enable','--now',unit.name])
        try:
            run(compose+['up','-d','--pull','never'],env=env,timeout=120)
            base='http://'+BIND+':18082';deadline=time.monotonic()+180
            while True:
                try:
                    if request(client(),base,'/login/check.query')[0]==200:break
                except (OSError,ValueError):pass
                if time.monotonic()>deadline:raise RuntimeError('dashboard_start_timeout')
                time.sleep(2)
            cases=verify(base,accounts['ui'])
            rows=inspect(run(compose+['ps','-q'],env=env).stdout.split())
            cases['nonroot_readonly_no_oom']=len(rows)==2 and all(r['Config']['User']=='10001:10001' and
                r['HostConfig']['ReadonlyRootfs'] and not r['State']['OOMKilled'] and r['RestartCount']==0 for r in rows)
            after=inspect([BROKER,'rocketmq-nameserver-1'])
            cases['original_mq_not_restarted']=all(a['Id']==b['Id'] and a['State']['StartedAt']==b['State']['StartedAt'] for a,b in zip(before,after))
            cases['memory_headroom']=memory()>=512
            final_users=admin.users()
            cases['existing_users_unchanged']=all(final_users.get(name)==value for name,value in users.items())
            if not all(cases.values()):raise RuntimeError('production_acceptance_incomplete')
            receipt=dict(passed=len(cases),failed=0,skipped=0,cases=cases,firewall=firewall,
                url=base,memory_available_mib=memory(),credentials_file=str(credential_path),
                containers=[dict(name=r['Name'].lstrip('/'),id=r['Id'],image=r['Image'],
                    memory_limit=r['HostConfig']['Memory'],cpu_limit=r['HostConfig']['NanoCpus']) for r in rows])
            private(ROOT/('receipt-'+str(time.time_ns())+'.json'),receipt)
            print(json.dumps(receipt))
        except Exception:
            # Own project only; leave credentials/evidence for diagnosis.
            run(compose+['down'],env=env,required=False,timeout=90)
            raise


if __name__=='__main__':main()
