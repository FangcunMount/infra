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
    try:
        # Deliberately advertise host address, exactly as production does. The
        # relay is necessary; direct service DNS alone cannot pass this test.
        host=json.loads(fixture.run(['docker','network','inspect','bridge']).stdout)[0]['IPAM']['Config'][0]['Gateway']
        original=fixtures.render
        fixtures.render=lambda accounts,output,advertised,templates: original(accounts,output,host,templates)
        fixture.dependencies()
        broker=fixture.project+'-broker-1'
        before=json.loads(fixture.run(['docker','inspect',broker]).stdout)[0]
        ui=dict(username='dashboard-admin',password=secrets.token_hex(32))
        account=dict(username='dashboard-management',password=secrets.token_hex(32))
        admin=Admin(broker)
        admin('createUser','-u',account['username'],'-p',account['password'],'-t','Super',mutation=True)
        assert admin.users()[account['username']]==(account['password'],'Super','Enable')
        cfg=fixture.directory/'dashboard'
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
        fixture.run(compose+['pull'],timeout=300)
        fixture.run(compose+['up','-d'],timeout=120)
        base='http://127.0.0.1:'+str(port)
        deadline=time.monotonic()+150
        while True:
            try:
                if request(client(),base,'/login/check.query')[0]==200:break
            except (OSError,ValueError):pass
            if time.monotonic()>deadline:raise RuntimeError('dashboard_start_timeout')
            time.sleep(2)
        cases=verify(base,ui)
        current=json.loads(fixture.run(['docker','inspect',broker]).stdout)[0]
        cases['broker_not_recreated_or_restarted']=(current['Id']==before['Id'] and
            current['State']['StartedAt']==before['State']['StartedAt'])
        ids=fixture.run(compose+['ps','-q']).stdout.split()
        rows=json.loads(fixture.run(['docker','inspect',*ids]).stdout)
        cases['resource_caps_enforced']=sorted(r['HostConfig']['Memory'] for r in rows)==[48*1024**2,512*1024**2]
        cases['nonroot_readonly_no_oom']=all(r['Config']['User']=='10001:10001' and
            r['HostConfig']['ReadonlyRootfs'] and not r['State']['OOMKilled'] and r['RestartCount']==0 for r in rows)
        assert all(cases.values()), 'acceptance_incomplete'
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
        fixture.run(['sudo','chown','-R',str(os.getuid())+':'+str(os.getgid()),str(fixture.directory)],required=False)
        fixture.cleanup()
        Path('dashboard-probe.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
