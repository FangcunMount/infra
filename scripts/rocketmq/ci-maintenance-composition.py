#!/usr/bin/env python3
"""Required isolated three-host/C1 maintenance composition. Never production."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import tempfile
import time

from audit_transaction_limit import write_private
from maintenance_composition import ci_guard,compose,MONGO


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('iam','qs','ai','report'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();ci_guard(os.environ)
    if args.report.exists():raise RuntimeError('new_report_required')
    spec=importlib.util.spec_from_file_location('fixture',Path(__file__).with_name('ci-transactions.py'))
    common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common);run=common.run
    context=json.loads(run(['docker','context','inspect']).stdout)
    if len(context)!=1 or context[0]['Endpoints']['docker']['Host']!='unix:///var/run/docker.sock':raise RuntimeError('local_ci_daemon_required')
    repo=Path(__file__).resolve().parents[2]
    directory=Path(tempfile.mkdtemp(prefix='m3-maintenance-'));directory.chmod(0o700)
    project='m3-maintenance-'+secrets.token_hex(8)
    report=dict(schema='m3-host-maintenance-composition/v1',infra_sha=run(['git','rev-parse','HEAD'],cwd=repo).stdout.strip(),passed=0,failed=0,skipped=0,failure=None,proof={},cleanup={},
        limits=['Individual original host contracts under one C1 operation, not one shared business database',
            'Runtime sentinel is synthetic; no actual production writer freeze, backup or system acceptance',
            'Host fixture protection/recovery does not authorize production DDL or data restoration'])
    stage='image_preflight';started=False
    def ids(kind):return set(run(['docker','ps','-aq'] if kind=='containers' else ['docker','network','ls','-q']).stdout.split())
    before={kind:ids(kind) for kind in ('containers','networks')}
    command=None
    try:
        mysql_image='mysql:8.0.44'
        for image in (mysql_image,MONGO):run(['docker','pull',image],timeout=300)
        images={key:run(['docker','image','inspect',image,'--format','{{.Id}}']).stdout.strip() for key,image in (('mysql',mysql_image),('mongo',MONGO))}
        report['proof']['images']=images
        mysql_port=common.port();mongo_port=common.port()
        if mysql_port==mongo_port:raise RuntimeError('distinct_loopback_ports_required')
        password=secrets.token_hex(32)
        document=dict(services=dict(mysql=dict(image=images['mysql'],restart='no',mem_limit='512m',cpus=1,tmpfs=['/var/lib/mysql'],
            environment=dict(MYSQL_ROOT_PASSWORD=password,MYSQL_ROOT_HOST='%'),ports=[f'127.0.0.1:{mysql_port}:3306'],networks=['owned'],
            command=['--innodb-buffer-pool-size=128M','--max-connections=80'],
            healthcheck=dict(test=['CMD-SHELL','MYSQL_PWD=$$MYSQL_ROOT_PASSWORD mysql -uroot -e "SELECT 1"'],interval='3s',timeout='3s',retries=50)),
            mongo=dict(image=images['mongo'],restart='no',mem_limit='512m',cpus=1,tmpfs=['/data/db','/data/configdb'],ports=[f'127.0.0.1:{mongo_port}:{mongo_port}'],networks=['owned'],
            command=['mongod','--port',str(mongo_port),'--replSet','maintenance-proof','--bind_ip_all','--wiredTigerCacheSizeGB','0.25'],
            healthcheck=dict(test=['CMD','mongosh','--port',str(mongo_port),'--quiet','--eval','db.adminCommand({ping:1})'],interval='3s',timeout='3s',retries=50))),networks=dict(owned={}))
        file=directory/'compose.json';write_private(file,document)
        command=['docker','compose','-p',project,'-f',str(file)]
        stage='owned_dependencies_start';started=True
        run(command+['up','-d','--wait','--wait-timeout','180'],timeout=210)
        def mongo(js):return run(command+['exec','-T','mongo','mongosh','--port',str(mongo_port),'--quiet','--eval',js]).stdout.strip()
        mongo('rs.initiate({_id:"maintenance-proof",members:[{_id:0,host:"127.0.0.1:'+str(mongo_port)+'"}]})')
        end=time.monotonic()+60
        while time.monotonic()<end:
            if mongo('JSON.stringify(db.adminCommand({hello:1}).isWritablePrimary)')=='true':break
            time.sleep(1)
        else:raise RuntimeError('owned_replica_not_primary')
        mysql_version=run(command+['exec','-T','mysql','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B -e "SELECT VERSION()"']).stdout.strip()
        if mysql_version!='8.0.44' or mongo('db.version()')!='7.0.37':raise RuntimeError('fixed_storage_versions_required')
        report['proof']['versions']=dict(mysql=mysql_version,mongo='7.0.37')
        stage='three_host_original_maintenance'
        report['proof']['progress']={}
        report['proof']['composition']=compose(repo=repo,iam=args.iam,qs=args.qs,ai=args.ai,directory=directory,mysql_port=mysql_port,password=password,
            mongo_uri=f'mongodb://127.0.0.1:{mongo_port}/?directConnection=true&replicaSet=maintenance-proof',run=run,progress=report['proof']['progress'])
        stage='owned_database_absence'
        sql="SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name REGEXP '^(iam_m3_offline_|qs_offline_test_|qs_m3_test_|ai_m3_tx_test_)';"
        remaining=run(command+['exec','-T','mysql','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B'],stdin=sql).stdout.strip()
        if remaining!='0':raise RuntimeError('owned_mysql_databases_remain')
        dbs=json.loads(mongo('JSON.stringify(db.adminCommand({listDatabases:1,nameOnly:true}).databases.map(x=>x.name).filter(x=>!["admin","config","local"].includes(x)))'))
        if dbs:raise RuntimeError('owned_mongo_databases_remain')
        report['proof']['owned_databases_removed']=True
        report['passed']=sum(v['passed'] for v in report['proof']['composition']['reports'].values())+3
    except Exception as error:
        report['failure_kind']=type(error).__name__ if type(error).__name__ in {'JSONDecodeError','ParseError','RuntimeError','FileNotFoundError','KeyError','CalledProcessError'} else 'unclassified_runtime_failure'
        report['failed']=1;report['failure']=stage
        # No exception text or private host log enters the artifact.
    finally:
        clean=report['cleanup']
        clean['compose_down_succeeded']=not started or run(command+['down','-v','--remove-orphans'],required=False,timeout=120).returncode==0
        clean['project_containers_remaining']=bool(run(['docker','ps','-aq','--filter','label=com.docker.compose.project='+project]).stdout.strip())
        clean['project_networks_remaining']=bool(run(['docker','network','ls','-q','--filter','label=com.docker.compose.project='+project]).stdout.strip())
        for kind,original in before.items():clean['existing_'+kind+'_unchanged']=ids(kind)==original
        shutil.rmtree(directory);clean['private_fixture_directory_removed']=not directory.exists()
        if clean!=dict(compose_down_succeeded=True,project_containers_remaining=False,project_networks_remaining=False,existing_containers_unchanged=True,existing_networks_unchanged=True,private_fixture_directory_removed=True):
            report['failed']=1;report['failure']=report['failure'] or 'owned_cleanup'
        write_private(args.report,report)
    return int(report['failed']!=0)


if __name__=='__main__':raise SystemExit(main())
