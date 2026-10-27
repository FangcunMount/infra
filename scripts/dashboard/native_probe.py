"""Hosted-runner-only real Dashboard + RocketMQ 5.5.1 TLS/ACL acceptance."""
import hashlib
import json
import os
import re
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
from acceptance import accepted, client, request, verify


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
        original_write=fixtures.write_private
        def write_fixture(path, value):
            if path.name=='compose.json':
                # Production uses a regular bridge. An internal-only bridge
                # suppresses host port publication on current Docker Engine.
                # All browser/dependency ports remain loopback-bound; the RPC
                # address is a runner-local dummy /32, not a production route.
                for network in value['networks'].values():network['internal']=False
            return original_write(path,value)
        fixtures.write_private=write_fixture
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
        next(row for row in doc['services']['gateway']['ports'] if row['target']==8082).update(host_ip='127.0.0.1',published=str(port))
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
        started=fixture.run(compose+['up','-d'],timeout=120,required=False)
        if started.returncode:
            # Compose arguments contain no credentials: private values are
            # mounted files, not environment values or command-line arguments.
            report['compose_diagnostic']=started.stderr[-3000:]
            raise RuntimeError('dashboard_compose_start_failed')
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
        report['cases']=cases
        report['stage']='untrusted_certificate_rejection'
        bad_ca=fixture.directory/'untrusted.crt'
        fixture.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
            '-subj','/CN=not-the-broker','-keyout',str(fixture.directory/'untrusted.key'),'-out',str(bad_ca)])
        bad_cfg=fixture.directory/'untrusted-dashboard'
        render(bad_cfg,ui,account,bad_ca.read_bytes())
        fixture.run(['sudo','chown','-R','10001:10001',str(bad_cfg)])
        bad_name=fixture.project+'-untrusted';bad_port=fixture.port()
        service=doc['services']['dashboard']
        fixture.run(['docker','run','-d','--name',bad_name,'--label',fixture.label,
            '--network',fixture.network,'--user','10001:10001','--read-only','--memory','512m',
            '--tmpfs','/tmp:rw,nosuid,size=67108864,uid=10001,gid=10001',
            '-v',str(bad_cfg)+':/run/dashboard:ro','-p','127.0.0.1:'+str(bad_port)+':8082',
            '--entrypoint','java',service['image'],*service['command']])
        bad_base='http://127.0.0.1:'+str(bad_port);deadline=time.monotonic()+120
        while True:
            try:
                if request(client(),bad_base,'/login/check.query')[0]==200:break
            except (OSError,ValueError):pass
            if time.monotonic()>deadline:raise RuntimeError('untrusted_dashboard_start_timeout')
            time.sleep(2)
        session=client()
        assert accepted(request(session,bad_base,'/login/login.do',ui)), 'untrusted_test_login_failed'
        assert not accepted(request(session,bad_base,'/topic/list.query')), 'untrusted_ca_accepted'
        logs=fixture.run(['docker','logs',bad_name]).stdout+fixture.run(['docker','logs',bad_name]).stderr
        report['untrusted_tls_error_visible_in_stdout']=any(marker in logs for marker in ('SSLHandshakeException','PKIX','certificate_unknown'))
        # Acceptance is the actual denied request, not the logging destination
        # chosen by the shaded RocketMQ client. Recheck the valid-CA control.
        control=client()
        assert accepted(request(control,base,'/login/login.do',ui)), 'trusted_control_login_failed'
        assert accepted(request(control,base,'/topic/list.query')), 'trusted_control_query_failed'
        cases['untrusted_ca_rejected']=True
        cases['trusted_ca_control_remains_healthy']=True
        fixture.run(['docker','rm','-f',bad_name])
        report['stage']='resource_and_network_acceptance'
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
        app=next(r for r in rows if r['Config']['Image'].startswith('apacherocketmq/'))
        jar=fixture.run(['docker','exec',app['Id'],'sha256sum','/rocketmq-dashboard.jar']).stdout.split()[0]
        cases['exact_official_application_jar']=jar=='98125ee1496edbab776e1374f3566f81a2dfb5e0fba0a12c468acbc21b468a73'
        cases['resource_caps_enforced']=sorted(r['HostConfig']['Memory'] for r in rows)==[48*1024**2,512*1024**2]
        cases['nonroot_readonly_no_oom']=all(r['Config']['User']=='10001:10001' and
            r['HostConfig']['ReadonlyRootfs'] and not r['State']['OOMKilled'] and r['RestartCount']==0 for r in rows)
        assert all(cases.values()), 'acceptance_incomplete'
        report['stage']='complete'
        report.update(passed=len(cases),failed=0,cases=cases,
            broker_version='5.5.1',dashboard_image_tag='2.1.0',dashboard_application_version='2.1.1-SNAPSHOT',
            dashboard_jar_sha256=jar,
            images=[dict(id=r['Image'],reference=r['Config']['Image']) for r in rows],
            source_sha=os.environ.get('GITHUB_SHA'),production_credentials_used=False)
    except Exception as error:
        report['error_type']=type(error).__name__
        if hasattr(error,'diagnostics'):report['acceptance_diagnostics']=error.diagnostics
        if isinstance(error,AssertionError):report['error_code']=str(error)
        if compose:
            ids=fixture.run(compose+['ps','-aq'],required=False).stdout.split()
            if ids:
                rows=json.loads(fixture.run(['docker','inspect',*ids]).stdout)
                report['container_diagnostics']=[dict(name=r['Name'],running=r['State']['Running'],
                    exit_code=r['State']['ExitCode'],oom=r['State']['OOMKilled'],
                    ports=r['NetworkSettings']['Ports']) for r in rows]
            # NGINX has no credentials and access logging is disabled.
            report['gateway_diagnostic']=fixture.run(compose+['logs','--no-color','--tail','20','gateway'],required=False).stdout[-3000:]
            logs=fixture.run(compose+['logs','--no-color','--tail','100'],required=False).stdout
            # Only fixed diagnostic classes, never configuration or credentials.
            report['diagnostics']={key:key in logs for key in ('OutOfMemoryError','Permission denied',
                'Read-only file system','UnsupportedClassVersionError','UnknownHostException',
                'SSLHandshakeException','Connection refused','Unable to start web server')}
            report['exception_classes']=sorted(set(re.findall(r'\b[A-Za-z_][\w.]*(?:Exception|Error)\b',logs)))
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
