"""Hosted-runner-only real Dashboard + RocketMQ 5.5.1 TLS/ACL acceptance."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'scripts/rocketmq'))
from final_image_candidate import ci_guard
import image_start_fixture as fixtures
from provision_v2 import Admin
from config import render
from acceptance import client, request, verify


def main():
    ci_guard(os.environ)
    report=dict(production=False,passed=0,failed=1,skipped=0,cases={})
    fixture=fixtures.OwnedImageFixture(REPO,report)
    fixture.image='rocketmq-m3-image-start:5.5.1'
    compose=None
    host='100.118.164.39'
    address_added=False
    firewall_added=False
    try:
        report['stage']='owned_address'
        # Deliberately advertise host address, exactly as production does. The
        # relay is necessary; direct service DNS alone cannot pass this test.
        existing=fixture.run(['ip','-j','address','show']).stdout
        assert host not in existing, 'owned_test_address_conflict'
        fixture.run(['sudo','ip','address','add',host+'/32','dev','lo'])
        address_added=True
        original=fixtures.render
        fixtures.render=lambda accounts,output,advertised,templates: original(accounts,output,host,templates)
        report['stage']='broker_dependencies'
        fixture.dependencies()
        broker=fixture.project+'-broker-1'
        before=json.loads(fixture.run(['docker','inspect',broker]).stdout)[0]
        ui=dict(username='dashboard-admin',password=secrets.token_hex(32))
        account=dict(username='dashboard-management',password=secrets.token_hex(32))
        admin=Admin(broker)
        report['stage']='dedicated_broker_identity'
        admin('createUser','-u',account['username'],'-p',account['password'],'-t','Super',mutation=True)
        row=admin.users()[account['username']]
        assert row[0]==account['password'] and tuple(x.lower() for x in row[1:])==('super','enable'), 'dedicated_identity_not_confirmed'
        cfg=fixture.directory/'dashboard'
        report['stage']='private_configuration'
        render(cfg,ui,account,(fixture.private/'mq-ca.crt').read_bytes())
        fixture.run(['sudo','chown','-R','10001:10001',str(cfg)])
        env=dict(os.environ,DASHBOARD_CONFIG_ROOT=str(cfg),DASHBOARD_BIND_IP=host,
            DASHBOARD_BROKER_NETWORK=fixture.network)
        doc=json.loads(fixture.run(['docker','compose','-f',str(REPO/'components/rocketmq-dashboard/docker-compose.yml'),
            'config','--format','json'],env=env).stdout)
        doc.pop('name',None)
        # Only browser ingress differs from production: loopback, random port.
        port=fixture.port()
        doc['services']['gateway']['ports'][0].update(host_ip='127.0.0.1',published=str(port))
        for value in doc['services'].values():value['restart']='no'
        file=fixture.directory/'dashboard-compose.json'
        file.write_text(json.dumps(doc));file.chmod(0o600)
        compose=['docker','compose','-p',fixture.project+'-dashboard','-f',str(file)]
        report['stage']='fixed_image_pull'
        fixture.run(compose+['pull'],timeout=300)
        report['stage']='scoped_firewall'
        firewall=fixture.run(['sudo','python3',str(REPO/'scripts/dashboard/firewall.py'),
            '--bind-ip',host,'--network',fixture.network],required=False)
        if firewall.returncode:
            # This command has only addresses/network names, no credentials.
            report['firewall_diagnostic']=firewall.stderr[-2000:]
            raise RuntimeError('firewall_install_failed')
        firewall_added=True
        report['stage']='dashboard_start'
        fixture.run(compose+['up','-d'],timeout=120)
        base='http://127.0.0.1:'+str(port)
        deadline=time.monotonic()+150
        report['stage']='dashboard_readiness'
        while True:
            try:
                if request(client(),base,'/login/check.query')[0]==200:break
            except (OSError,ValueError):pass
            if time.monotonic()>deadline:raise RuntimeError('dashboard_start_timeout')
            time.sleep(2)
        report['stage']='authenticated_acceptance'
        cases=verify(base,ui)
        cases['scoped_firewall_applied']=True
        # Foreign Docker bridge cannot use the new host management relay.
        rejected=fixture.run(['docker','run','--rm','--network','bridge','--entrypoint','bash',
            fixture.image,'-c','timeout 3 bash -c "exec 3<>/dev/tcp/'+host+'/10911"'],required=False)
        cases['foreign_bridge_rpc_rejected']=rejected.returncode!=0
        current=json.loads(fixture.run(['docker','inspect',broker]).stdout)[0]
        cases['broker_not_recreated_or_restarted']=(current['Id']==before['Id'] and
            current['State']['StartedAt']==before['State']['StartedAt'])
        ids=fixture.run(compose+['ps','-q']).stdout.split()
        rows=json.loads(fixture.run(['docker','inspect',*ids]).stdout)
        cases['resource_caps_enforced']=sorted(r['HostConfig']['Memory'] for r in rows)==[48*1024**2,512*1024**2]
        cases['nonroot_readonly_no_oom']=all(r['Config']['User']=='10001:10001' and
            r['HostConfig']['ReadonlyRootfs'] and not r['State']['OOMKilled'] and r['RestartCount']==0 for r in rows)
        assert all(cases.values()), 'acceptance_incomplete'
        report['stage']='complete'
        report.update(passed=len(cases),failed=0,cases=cases,
            broker_version='5.5.1',dashboard_version='2.1.0',
            images=[dict(id=r['Image'],reference=r['Config']['Image']) for r in rows],
            source_sha=os.environ.get('GITHUB_SHA'),production_credentials_used=False)
    except Exception as error:
        report['error_type']=type(error).__name__
        if isinstance(error,AssertionError):report['error_code']=str(error)
        if compose:
            logs=fixture.run(compose+['logs','--no-color','--tail','100'],required=False).stdout
            # Only fixed diagnostic classes, never configuration or credentials.
            report['diagnostics']={key:key in logs for key in ('OutOfMemoryError','Permission denied',
                'UnsupportedClassVersionError','UnknownHostException','SSLHandshakeException','Connection refused')}
            report['private_log_sha256']=hashlib.sha256(logs.encode()).hexdigest()
        raise RuntimeError('owned_dashboard_validation_failed') from None
    finally:
        if compose:fixture.run(compose+['down','-v','--remove-orphans'],required=False,timeout=120)
        if firewall_added:
            for port in ('18082','10911'):
                fixture.run(['sudo','iptables','-D','DOCKER-USER','-p','tcp','-m','conntrack',
                    '--ctorigdst',host,'--ctorigdstport',port,'-j','INFRA-MQ-DASH'])
            fixture.run(['sudo','iptables','-F','INFRA-MQ-DASH'])
            fixture.run(['sudo','iptables','-X','INFRA-MQ-DASH'])
        if address_added:fixture.run(['sudo','ip','address','del',host+'/32','dev','lo'])
        fixture.run(['sudo','chown','-R',str(os.getuid())+':'+str(os.getgid()),str(fixture.directory)],required=False)
        fixture.cleanup()
        Path('dashboard-probe.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
