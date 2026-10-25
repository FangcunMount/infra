#!/usr/bin/env python3
"""Native TLS/MySQL self-password validation on owned GitHub fixtures only."""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

import m3_mysql_credential as tool

IMAGE='mysql@sha256:65ce0889751900d2dd5fc5aa5a5fb59073d401fc43df2eae6bd6afb18e7626dd'


def main():
    if (os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted'
            or os.environ.get('RUNNER_OS')!='Linux'):
        raise RuntimeError('owned GitHub Linux fixture required; no local or production inputs')
    report={'schema':'m3-mysql-credential-native/v1','passed':0,'failed':0,'skipped':0,'cases':[],
            'image':IMAGE,'production':False,'source_sha':os.environ['GITHUB_SHA'],
            'tool_sha256':tool.digest(Path(tool.__file__).read_bytes()),'cleanup':{}}
    prefix='m3-credential-'+secrets.token_hex(5);container=prefix;network=prefix+'-net'
    def run(args,*,data=None,timeout=60,required=True):
        p=subprocess.run(args,input=data,capture_output=True,timeout=timeout)
        if required and p.returncode:raise RuntimeError('owned fixture command failed; raw output omitted')
        return p
    def case(name):report['cases'].append(name);report['passed']=len(report['cases'])
    failure=None
    try:
        with tempfile.TemporaryDirectory(prefix=prefix) as temp:
            root=Path(temp);root.chmod(0o700);cert=root/'cert';cert.mkdir(mode=0o755)
            run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(cert/'ca.key'),
                 '-out',str(cert/'ca.pem'),'-days','1','-subj','/CN=M3 owned test CA'])
            run(['openssl','req','-newkey','rsa:2048','-nodes','-keyout',str(cert/'server.key'),
                 '-out',str(cert/'server.csr'),'-subj','/CN=127.0.0.1'])
            (cert/'extensions').write_text('subjectAltName=IP:127.0.0.1\nextendedKeyUsage=serverAuth\n')
            run(['openssl','x509','-req','-in',str(cert/'server.csr'),'-CA',str(cert/'ca.pem'),
                 '-CAkey',str(cert/'ca.key'),'-CAcreateserial','-out',str(cert/'server.pem'),'-days','1',
                 '-extfile',str(cert/'extensions')])
            for p in cert.iterdir():p.chmod(0o644)
            password=secrets.token_hex(24);env=root/'mysql.env';env.write_text('MYSQL_ROOT_PASSWORD='+password+'\nMYSQL_ROOT_HOST=%\n');env.chmod(0o600)
            run(['docker','network','create',network])
            run(['docker','pull',IMAGE],timeout=240)
            run(['docker','run','--detach','--name',container,'--network',network,'--env-file',str(env),
                 '--publish','127.0.0.1::3306','--memory','768m','--cpus','1','--pids-limit','256',
                 '--mount','type=bind,src='+str(cert)+',dst=/owned-tls,readonly',IMAGE,
                 '--ssl-ca=/owned-tls/ca.pem','--ssl-cert=/owned-tls/server.pem','--ssl-key=/owned-tls/server.key',
                 '--require-secure-transport=ON'])
            sqlcmd=['docker','exec','-i',container,'sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot -N -B']
            until=time.monotonic()+150
            while True:
                p=run(sqlcmd,data=b'SELECT 1;',required=False)
                if p.returncode==0:break
                if time.monotonic()>until:raise RuntimeError('owned mysql readiness timeout')
                time.sleep(1)
            port=int(run(['docker','port',container,'3306/tcp']).stdout.decode().strip().rsplit(':',1)[1])
            identity=run(sqlcmd,data=b'SELECT @@server_uuid,VERSION();').stdout.decode().strip().split('\t');assert len(identity)==2 and identity[1]=='8.0.36'
            databases=['m3_credential_test_'+s for s in ('iam','qs','ai')]
            sql=''.join('CREATE DATABASE `'+db+'`; CREATE TABLE `'+db+'`.sentinel(id INT PRIMARY KEY, value VARCHAR(30)); INSERT INTO `'+db+'`.sentinel VALUES(1,\'original-fact\');' for db in databases)
            run(sqlcmd,data=sql.encode())
            baseline=run(sqlcmd,data=''.join('SELECT * FROM `'+db+'`.sentinel;' for db in databases).encode()).stdout
            for plugin in ('mysql_native_password','caching_sha2_password'):
                user='owned_'+('native' if plugin=='mysql_native_password' else 'caching');old=secrets.token_hex(24);new=secrets.token_hex(32)
                sql="CREATE USER '"+user+"'@'%' IDENTIFIED WITH "+plugin+" BY '"+old+"';"+''.join("GRANT SELECT,INSERT,UPDATE,DELETE ON `"+db+"`.* TO '"+user+"'@'%';" for db in databases)
                run(sqlcmd,data=sql.encode())
                directory=root/user;directory.mkdir(mode=0o700)
                value=dict(schema='m3-mysql-self-credential/v1',operation_id=prefix+'-'+user,host='127.0.0.1',port=port,
                           username=user,current_account=user+'@%',server_uuid=identity[0],server_version=identity[1],
                           old_password=old,new_password=new,ca_file=str(cert/'ca.pem'),directory=str(directory),
                           expires_at=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat(),coordinator_binding_sha256='a'*64)
                plan=directory/'plan.json';plan.write_text(json.dumps(value));plan.chmod(0o600);sha=tool.digest(plan.read_bytes())
                base=[sys.executable,str(Path(tool.__file__)),'--plan',str(plan),'--reviewed-sha256',sha]
                p=run(base);result=json.loads(p.stdout);assert result['status']=='preview' and result['read_only'] and not (directory/'rotation-issued.json').exists();case(plugin+': TLS preview has no mutation')
                wrong=dict(value);wrong['server_uuid']='00000000-0000-0000-0000-000000000001';bad=directory/'wrong.json';bad.write_text(json.dumps(wrong));bad.chmod(0o600)
                p=run([sys.executable,str(Path(tool.__file__)),'--plan',str(bad),'--reviewed-sha256',tool.digest(bad.read_bytes()),'--action','apply','--writers-excluded','--coordinated-start-already-issued'],required=False)
                assert p.returncode and not (directory/'rotation-issued.json').exists();case(plugin+': wrong primary rejected before issuance')
                p=run(base+['--action','apply','--writers-excluded','--coordinated-start-already-issued']);result=json.loads(p.stdout);assert result['status']=='verified' and result['old_credential_rejected'] and not result['read_only'];case(plugin+': own password changed; fresh new succeeds and old rejects')
                p=run(base+['--action','apply','--writers-excluded','--coordinated-start-already-issued'],required=False);assert p.returncode;case(plugin+': second apply refused')
                result=json.loads(run(base+['--action','verify']).stdout);assert result['read_only'] and result['old_credential_rejected']
                actual=run(sqlcmd,data=("SELECT plugin FROM mysql.user WHERE User='"+user+"' AND Host='%';").encode()).stdout.decode().strip();assert actual==plugin;case(plugin+': plugin and read-only verification preserved')
            after=run(sqlcmd,data=''.join('SELECT * FROM `'+db+'`.sentinel;' for db in databases).encode()).stdout
            assert baseline==after;case('all three original business facts unchanged')
            report['tls_verified']=True;report['actual_version']=identity[1];report['business_facts_sha256']=hashlib.sha256(after).hexdigest()
    except BaseException as error:
        report['failed']=1;report['error_type']=type(error).__name__;failure=error
    finally:
        p=run(['docker','rm','--force','--volumes',container],required=False)
        absent=run(['docker','container','inspect',container],required=False).returncode!=0
        n=run(['docker','network','rm',network],required=False)
        report['cleanup']={'owned_container_absent':absent,'owned_network_removed':n.returncode==0,'private_directory_removed':not Path(temp).exists() if 'temp' in locals() else True}
        Path('m3-mysql-credential-native.json').write_text(json.dumps(report,indent=2)+'\n')
    if failure or not all(report['cleanup'].values()):raise SystemExit('owned credential validation failed; no raw credential output')
    print(json.dumps({'passed':report['passed'],'failed':0,'skipped':0,'cleanup':report['cleanup']}))


if __name__=='__main__':main()
