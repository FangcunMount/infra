"""Hosted-runner HTTPS ingress + native Broker recreate/recovery acceptance."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sys
import time

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'scripts/rocketmq'))
from final_image_candidate import ci_guard
import image_start_fixture as fixtures
from provision_v2 import Admin
from config import render
from acceptance import accepted,client,request,verify
from native_broker import add_native_port,critical,healthy,inspect,override,ports,run

INGRESS='nginx@sha256:6784fb0834aa7dbbe12e3d7471e69c290df3e6ba810dc38b34ae33d3c1c05f7d'
HOST='100.118.164.39'


def wait_http(base,ca):
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        try:
            if request(client(ca),base,'/login/check.query')[0]==200:return
        except (OSError,ValueError):pass
        time.sleep(2)
    raise RuntimeError('https_dashboard_not_ready')


def main():
    ci_guard(os.environ)
    assert os.geteuid()==0,'owned_fixture_requires_sudo_E'
    report=dict(production=False,passed=0,failed=1,skipped=0,cases={},events=[])
    fixture=fixtures.OwnedImageFixture(REPO,report);fixture.image='rocketmq-m3-image-start:5.5.1'
    compose=None;front=None;bad=None;firewall=False;address=False
    try:
        report['stage']='owned_dependencies'
        assert HOST not in fixture.run(['ip','-j','address','show']).stdout,'owned_address_conflict'
        fixture.run(['ip','address','add',HOST+'/32','dev','lo']);address=True
        original=fixtures.render
        fixtures.render=lambda accounts,output,advertised,templates:original(accounts,output,HOST,templates)
        writer=fixtures.write_private
        def write_fixture(path,value):
            if path.name=='compose.json':
                for network in value['networks'].values():network['internal']=False
            return writer(path,value)
        fixtures.write_private=write_fixture
        fixture.dependencies()
        broker=fixture.project+'-broker-1';nameserver=fixture.project+'-nameserver-1'
        ns_before=inspect(nameserver)
        ui=dict(username='dashboard-admin',password=secrets.token_hex(32))
        account=dict(username='dashboard-management',password=secrets.token_hex(32))
        admin=Admin(broker)
        admin('createUser','-u',account['username'],'-p',account['password'],'-t','Super',mutation=True)
        admin('updateTopic','-t','owned-dashboard-inventory','-r','1','-w','1','-a','+message.type=NORMAL',mutation=True)
        admin('updateSubGroup','-g','owned-dashboard-inventory',mutation=True)
        users=admin.users()
        metadata=admin.metadata('/tmp/owned-dashboard-before')
        before=inspect(broker)
        fixture.run(['python3',str(REPO/'scripts/dashboard/firewall.py'),'--bind-ip',HOST,'--network',fixture.network])
        firewall=True
        report['stage']='native_broker_recreation'
        overlay=fixture.directory/'native-rpc.json';override(overlay,before,HOST)
        def checkpoint(phase,**fields):report['events'].append(dict(phase=phase,**fields))
        candidate,backup=add_native_port(before,fixture.compose,overlay,fixture.directory,HOST,checkpoint)
        cases=report['cases']
        cases['cold_backup_after_stop']=backup['files']>0 and backup['bytes']>0 and not backup['store_restored']
        cases['broker_same_image_resources_config_mounts']=critical(candidate)==critical(before)
        cases['broker_native_private_port']=ports(candidate)=={**ports(before),'10911/tcp':[(HOST,'10911')]}
        cases['broker_users_and_inventory_preserved']=admin.users()==users and admin.metadata('/tmp/owned-dashboard-after')==metadata
        report['stage']='current_store_recovery_drill'
        recovery=fixture.directory/'recovery.json'
        recovery.write_text(json.dumps(dict(services=dict(broker=dict(hostname=before['Config']['Hostname'])))))
        fixture.run([*fixture.compose,'-f',str(recovery),'up','-d','--no-deps','--pull','never','broker'],timeout=150)
        recovered=healthy(broker)
        cases['original_mapping_recovery_uses_current_store']=ports(recovered)==ports(before) and admin.users()==users
        fixture.run([*fixture.compose,'-f',str(overlay),'up','-d','--no-deps','--pull','never','broker'],timeout=150)
        candidate=healthy(broker)
        cases['native_mapping_reapplied_without_store_restore']=critical(candidate)==critical(before) and admin.users()==users
        report['stage']='dashboard_and_https_ingress'
        cfg=fixture.directory/'dashboard';render(cfg,ui,account,(fixture.private/'mq-ca.crt').read_bytes())
        fixture.run(['chown','-R','10001:10001',str(cfg)])
        env=dict(os.environ,DASHBOARD_CONFIG_ROOT=str(cfg),DASHBOARD_BIND_IP=HOST,DASHBOARD_BROKER_NETWORK=fixture.network)
        doc=json.loads(fixture.run(['docker','compose','-f',str(REPO/'components/rocketmq-dashboard/docker-compose.yml'),'config','--format','json'],env=env).stdout)
        doc.pop('name',None);doc['services']['dashboard']['restart']='no'
        file=fixture.directory/'dashboard-compose.json';file.write_text(json.dumps(doc));file.chmod(0o600)
        compose=['docker','compose','-p',fixture.project+'-dashboard','-f',str(file)]
        fixture.run(compose+['pull'],timeout=300);fixture.run(compose+['up','-d'],timeout=90)
        bad_ca=fixture.directory/'untrusted.crt'
        fixture.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=unrelated-ca',
            '-keyout',str(fixture.directory/'untrusted.key'),'-out',str(bad_ca)])
        bad_cfg=fixture.directory/'bad-dashboard';render(bad_cfg,ui,account,bad_ca.read_bytes())
        fixture.run(['chown','-R','10001:10001',str(bad_cfg)])
        bad=fixture.project+'-untrusted';bad_backend=fixture.port();bad_front=fixture.port()
        service=doc['services']['dashboard']
        fixture.run(['docker','run','-d','--name',bad,'--label',fixture.label,'--network',fixture.network,
            '--user','10001:10001','--read-only','--memory','512m','--cap-drop','ALL',
            '--tmpfs','/tmp:rw,nosuid,size=67108864,uid=10001,gid=10001',
            '-v',str(bad_cfg)+':/run/dashboard:ro','-p','127.0.0.1:'+str(bad_backend)+':8082',
            '--entrypoint','java',service['image'],*service['command']])
        tls=fixture.directory/'front-tls';(tls/'certs').mkdir(parents=True);(tls/'private').mkdir()
        crt=tls/'certs/fangcunmount.cn.crt';key=tls/'private/fangcunmount.cn.key'
        fixture.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost',
            '-addext','subjectAltName=DNS:localhost,IP:127.0.0.1','-keyout',str(key),'-out',str(crt)])
        key.chmod(0o600)
        front_cfg=fixture.directory/'front';front_cfg.mkdir(mode=0o755)
        template=(REPO/'components/rocketmq-dashboard/server-a.conf').read_text()
        good=template.replace('mq.fangcunmount.cn','localhost').replace('listen 80;','listen 127.0.0.1:80;').replace('listen 443 ssl;','listen 127.0.0.1:443 ssl;')
        (front_cfg/'good.conf').write_text(good)
        parts=template.split('server {',2)
        rejected=(parts[0]+'server {'+parts[2]).replace('mq.fangcunmount.cn','localhost').replace('mq_dashboard_login','mq_dashboard_bad_login')
        rejected=rejected.replace('listen 443 ssl;',f'listen 127.0.0.1:{bad_front} ssl;').replace(HOST+':18082','127.0.0.1:'+str(bad_backend))
        (front_cfg/'bad.conf').write_text(rejected)
        (front_cfg/'nginx.conf').write_text('worker_processes 1; pid /tmp/nginx.pid; error_log /dev/stderr warn; events { worker_connections 128; } http { include /etc/nginx/mime.types; access_log off; client_body_temp_path /tmp/client; proxy_temp_path /tmp/proxy; fastcgi_temp_path /tmp/fastcgi; uwsgi_temp_path /tmp/uwsgi; scgi_temp_path /tmp/scgi; include /front/good.conf; include /front/bad.conf; }')
        fixture.run(['docker','pull',INGRESS],timeout=300)
        front=fixture.project+'-ingress'
        common=['docker','run','--rm','--label',fixture.label,'--network','host','--read-only','--memory','128m',
            '--tmpfs','/tmp:rw,nosuid,size=16777216',
            '-v',str(front_cfg)+':/front:ro','-v',str(tls)+':/data/ssl:ro','--entrypoint','nginx',INGRESS]
        fixture.run(common+['-t','-c','/front/nginx.conf'])
        fixture.run(['docker','run','-d','--name',front,*common[3:-1],INGRESS,'-c','/front/nginx.conf','-g','daemon off;'])
        base='https://localhost';bad_base='https://localhost:'+str(bad_front)
        wait_http(base,crt);wait_http(bad_base,crt)
        report['stage']='https_authenticated_acceptance'
        cases.update(verify(base,ui,crt))
        redirect=request(client(crt),'http://localhost','/')[0]
        cases['http_redirects_https']=redirect==301
        session=client(crt)
        assert accepted(request(session,bad_base,'/login/login.do',ui)),'wrong_ca_control_login_failed'
        assert not accepted(request(session,bad_base,'/topic/list.query')),'untrusted_ca_accepted'
        control=client(crt)
        assert accepted(request(control,base,'/login/login.do',ui)) and accepted(request(control,base,'/topic/list.query')),'trusted_control_failed'
        cases['wrong_ca_denied_with_valid_https_session']=True
        for port in (10911,18082):
            denied=fixture.run(['docker','run','--rm','--network','bridge','--entrypoint','bash',fixture.image,
                '-c',f'timeout 3 bash -c "exec 3<>/dev/tcp/{HOST}/{port}"'],required=False)
            cases['foreign_bridge_'+str(port)+'_denied']=denied.returncode!=0
        ids=fixture.run(compose+['ps','-q']).stdout.split();assert len(ids)==1,'serverd_must_have_only_dashboard'
        app=inspect(ids[0]);ns_after=inspect(nameserver)
        cases['no_serverd_nginx_service']=set(doc['services'])=={'dashboard'}
        cases['dashboard_nonroot_readonly_bounded']=app['Config']['User']=='10001:10001' and app['HostConfig']['ReadonlyRootfs'] and app['HostConfig']['Memory']==512*1024**2 and not app['State']['OOMKilled'] and app['RestartCount']==0
        cases['nameserver_not_restarted']=ns_before['Id']==ns_after['Id'] and ns_before['State']['StartedAt']==ns_after['State']['StartedAt']
        jar=fixture.run(['docker','exec',app['Id'],'sha256sum','/rocketmq-dashboard.jar']).stdout.split()[0]
        cases['exact_official_jar']=jar=='98125ee1496edbab776e1374f3566f81a2dfb5e0fba0a12c468acbc21b468a73'
        assert all(cases.values()),'native_https_acceptance_incomplete'
        report.update(passed=len(cases),failed=0,stage='complete',dashboard_image_tag='2.1.0',
            dashboard_application_version='2.1.1-SNAPSHOT',dashboard_jar_sha256=jar,
            source_sha=os.environ.get('GITHUB_SHA'),production_credentials_used=False,
            ingress_image=INGRESS,backup=backup,store_restored=False)
    except Exception as error:
        report['error_type']=type(error).__name__
        if isinstance(error,AssertionError):report['error_code']=str(error)
        if hasattr(error,'diagnostics'):report['acceptance_diagnostics']=error.diagnostics
        if front:
            logs=fixture.run(['docker','logs','--tail','30',front],required=False)
            report['ingress_diagnostic']=(logs.stdout+logs.stderr)[-3000:]
        if compose:
            ids=fixture.run(compose+['ps','-aq'],required=False).stdout.split()
            report['dashboard_states']=[{k:inspect(name)['State'].get(k) for k in ['Running','OOMKilled','ExitCode']} for name in ids]
        raise RuntimeError('owned_native_https_validation_failed') from None
    finally:
        for name in (front,bad):
            if name:fixture.run(['docker','rm','-f',name],required=False)
        if compose:fixture.run(compose+['down','-v','--remove-orphans'],required=False,timeout=120)
        if firewall:
            for port in ('18082','10911'):
                fixture.run(['iptables','-D','DOCKER-USER','-p','tcp','-m','conntrack','--ctorigdst',HOST,'--ctorigdstport',port,'-j','INFRA-MQ-DASH'])
                fixture.run(['iptables','-D','INPUT','-p','tcp','-d',HOST,'--dport',port,'-j','INFRA-MQ-DASH'])
            fixture.run(['iptables','-F','INFRA-MQ-DASH']);fixture.run(['iptables','-X','INFRA-MQ-DASH'])
        if address:fixture.run(['ip','address','del',HOST+'/32','dev','lo'])
        fixture.cleanup()
        Path('dashboard-probe.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
