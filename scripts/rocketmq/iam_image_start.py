"""Actual IAM candidate image, original limited restore and sealed owner startup.

GitHub-hosted owned fixtures only. This is one T29 component, not the combined
five-image/30-minute rehearsal or production/system acceptance.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import time

from final_image_candidate import ci_guard, sha256, saved_config, GO_SUM
from render import render
from provision_v2 import provision
from m3_resources import manifest
from audit_transaction_limit import write_private

IAM_SHA = '954ad9dee2f71a51151b696ec05d5cb90cc65b50'
NSQ = 'nsqio/nsq@sha256:1a369c146af71bc95c25d54b375a2b98452478c1eaf4e85f8fcb01da20f2c78a'


def require(value, stage):
    if not value:
        raise RuntimeError(stage)


def inventory(value):
    require(value.get('target') == 'iam' and value.get('source_sha') == IAM_SHA,
            'repaired_exact_iam_candidate_required')
    require((value.get('passed'), value.get('failed'), value.get('skipped')) == (1, 0, 0)
            and value.get('deferred_tools_absent') is True
            and value.get('verified_uid_gid') == [2000, 2000]
            and value.get('runtime_sdk') == dict(version='v0.5.0', sum=GO_SUM, replace=False),
            'verified_stable_image_inventory_required')
    require(all(value.get('cleanup', {}).get(k) is True for k in
                ('owned_container_absent', 'owned_image_tag_absent', 'existing_containers_unchanged')),
            'candidate_cleanup_required')


def configuration(base, database, password, *, transaction):
    """Keep the original production shape; substitute only owned fixture inputs."""
    c = copy.deepcopy(base)
    c['mysql'].update({'host': 'mysql:3306', 'username': 'root', 'password': password,
                       'database': database, 'tls-mode': 'DISABLED'})
    c['migration'].update(enabled=False, database=database)
    c['redis']['cache'].update(host='redis', port=6379, username='', password='')
    c['seed_mock_auth']['enabled'] = False
    c['idp']['encryption-key'] = secrets.token_hex(16)
    c['sms'] = {'provider': 'log'}
    c['insecure'].update({'bind-address': '0.0.0.0', 'bind-port': 9080})
    c['grpc']['mtls'].update({'cert-file': '/fixture/server.crt', 'key-file': '/fixture/server.key',
                             'ca-file': '/fixture/server.crt'})
    c['events']['catalog_path'] = '/app/configs/events-m3.yaml' if transaction else '/app/configs/events.yaml'
    c['events']['reliable_messaging']['enabled'] = not transaction
    c['nsq'] = {'enabled': not transaction, 'consumer-sdk-enabled': not transaction,
                'nsqd-addr': 'nsqd:4150', 'lookupd-addrs': ['nsqlookupd:4161'],
                'nsqd-http-addrs': ['http://nsqd:4151']}
    c['messaging'] = dict(provider='rocketmq' if transaction else 'nsq', publish_enabled=transaction is False,
                          instance_id='iam-primary-1', endpoint='broker:8081',
                          credentials_file='/fixture/credentials.json', ca_file='/fixture/mq-ca.crt',
                          routes_file='/fixture/routes.json', transactions={})
    if transaction:
        c['messaging']['transactions'] = {'iam.mysql': dict(store_id='isolated-iam-primary', writer_epoch='m3-1', route_revision='m3-1')}
    return c


def protocol_metrics(raw):
    required = {'sdk_ready': 1, 'sampler_running': 1, 'observation_available': 1,
                'admission_open': 0, 'check_workers_limit': 4, 'check_queue_limit': 32}
    for key, value in required.items():
        expected = f'reliable_messaging_transaction_{key}{{owner="iam.mysql"}} {value}'
        require(expected in raw.splitlines(), 'actual_paused_owner_metrics_required:' + key)
    return required


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'candidate', 'report'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    ci_guard(os.environ)
    require(not args.report.exists(), 'new_report_required')
    spec = importlib.util.spec_from_file_location('ci_fixture', Path(__file__).with_name('ci-transactions.py'))
    common = importlib.util.module_from_spec(spec); spec.loader.exec_module(common)
    run = common.run
    repo = Path(__file__).resolve().parents[2]
    source = args.source.resolve()
    require(run(['git', 'rev-parse', 'HEAD'], cwd=source).stdout.strip() == IAM_SHA, 'fixed_host_source_required')
    require(not run(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=source).stdout, 'clean_host_source_required')
    require(json.loads(run(['docker', 'context', 'inspect']).stdout)[0]['Endpoints']['docker']['Host'] == 'unix:///var/run/docker.sock', 'owned_ci_daemon_required')
    import tempfile
    directory = Path(tempfile.mkdtemp(prefix='m3-iam-image-')); directory.chmod(0o700)
    project = 'rocketmq-m2-image-'+secrets.token_hex(6)
    report = dict(schema='m3-iam-actual-image-start/v1', infra_sha=run(['git', 'rev-parse', 'HEAD'], cwd=repo).stdout.strip(),
                  iam_sha=IAM_SHA, passed=0, failed=0, skipped=0, cases={}, cleanup={},
                  production=False, system_acceptance=False, combined_cutover_rehearsal_complete=False)
    before = {key:set(run(argv).stdout.split()) for key,argv in
              (('containers',['docker','ps','-aq']),('networks',['docker','network','ls','-q']))}
    compose = None; prepared = None; started = False; app = project+'-iam'; app_created = False
    image = None; fixture = directory/'fixture'; fixture.mkdir(mode=0o700)
    (fixture/'keys').mkdir(mode=0o700)
    stage = 'candidate_verification'
    def case(name, condition=True):
        require(condition, name); report['cases'][name] = True
    def sql(statement):
        return run(compose+['exec','-T','mysql','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B'], stdin=statement).stdout.strip()
    def runtime_logs():
        result = run(['docker','logs',app], required=False)
        path = directory/'application-private.log'; path.write_text(result.stdout+result.stderr); path.chmod(0o600)
        report['private_application_log_sha256'] = sha256(path)
    try:
        metadata = json.loads((args.candidate/'image-inventory.json').read_text()); inventory(metadata)
        archives = list(args.candidate.glob('*.tar.gz')); require(len(archives)==1, 'one_candidate_archive_required')
        archive = archives[0]; require(sha256(archive)==metadata['archive_sha256'], 'candidate_archive_digest_differs')
        # Read the unique original tag without extracting untrusted tar members.
        import tarfile
        with tarfile.open(archive) as tar:
            entries = json.load(tar.extractfile('manifest.json'))
            require(len(entries)==1 and len(entries[0]['RepoTags'])==1, 'single_image_archive_required')
            image = entries[0]['RepoTags'][0]
        require(saved_config(archive, image)[0]==metadata['image_config_id'], 'archived_config_differs')
        run(['docker','load','-i',str(archive)],timeout=180)
        require(run(['docker','image','inspect',image,'--format','{{.Id}}']).stdout.strip()==metadata['engine_image_id'], 'loaded_image_differs')
        report['candidate'] = {k:metadata[k] for k in ('source_sha','image_config_id','archive_sha256','runtime_binary_sha256')}
        case('exact_repaired_stable_archive_loaded')
        stage='owned_dependencies'
        broker_image='rocketmq-m3-image-start:5.5.1'
        for dep in ('mysql:8.0.44','redis:7-alpine',NSQ): run(['docker','pull',dep],timeout=300)
        config=directory/'broker'; data=directory/'data'; data.mkdir()
        accounts={name:dict(username='fixture-'+name,password=secrets.token_hex(32)) for name in ('admin','inner')}
        render(accounts,config,'broker',repo/'components/rocketmq'); (config/'tls').mkdir()
        run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=broker',
             '-addext','subjectAltName=DNS:broker,DNS:nameserver,IP:127.0.0.1','-keyout',str(config/'tls/server.key'),'-out',str(config/'tls/server.crt')])
        shutil.copyfile(config/'tls/server.crt',fixture/'mq-ca.crt')
        run(['docker','run','--rm','--user','0','--entrypoint','bash','-v',str(config)+':/config','-v',str(data)+':/data',broker_image,'-c',
             'mkdir -p /data/store /data/auth /data/logs /data/nameserver-logs; chown -R 3000:3000 /data /config; chmod 750 /config /config/tls'])
        environment=dict(os.environ,ROCKETMQ_IMAGE=broker_image,ROCKETMQ_BIND_IP='127.0.0.1',ROCKETMQ_GRPC_PORT=str(common.port()),
                         ROCKETMQ_METRICS_PORT=str(common.port()),ROCKETMQ_DATA_ROOT=str(data),ROCKETMQ_CONFIG_ROOT=str(config))
        document=json.loads(run(['docker','compose','-f',str(repo/'components/rocketmq/docker-compose.yml'),'config','--format','json'],env=environment).stdout)
        document.pop('name',None)
        for network in document['networks'].values(): network.pop('name',None); network['internal']=True
        for service in document['services'].values(): service['restart']='no'
        password=secrets.token_hex(32); database='iam_m3_image_'+secrets.token_hex(8); mysql_port=common.port()
        document['services'].update(mysql=dict(image='mysql:8.0.44',environment=dict(MYSQL_ROOT_PASSWORD=password,MYSQL_ROOT_HOST='%'),
            ports=[f'127.0.0.1:{mysql_port}:3306'],tmpfs=['/var/lib/mysql'],mem_limit='512m',networks=['rocketmq'],
            healthcheck=dict(test=['CMD-SHELL','MYSQL_PWD=$$MYSQL_ROOT_PASSWORD mysql -uroot -e "SELECT 1"'],interval='3s',timeout='3s',retries=50)),
            redis=dict(image='redis:7-alpine',networks=['rocketmq']),
            nsqlookupd=dict(image=NSQ,command=['/nsqlookupd'],networks=['rocketmq']),
            nsqd=dict(image=NSQ,command=['/nsqd','--broadcast-address=nsqd','--lookupd-tcp-address=nsqlookupd:4160'],networks=['rocketmq']))
        compose_file=directory/'compose.json';write_private(compose_file,document)
        compose=['docker','compose','-p',project,'-f',str(compose_file)];started=True
        run(compose+['up','-d','--wait','--wait-timeout','180'],timeout=210)
        report['dependency_image_ids']={name:run(['docker','image','inspect',tag,'--format','{{.Id}}']).stdout.strip()
             for name,tag in dict(mysql='mysql:8.0.44',redis='redis:7-alpine',nsq=NSQ,rocketmq=broker_image).items()}
        sql('CREATE DATABASE `'+database+'`;')
        stage='original_schema41_preparation'
        prepared=source/'scripts/testing/m3_image_start_fixture'; prepared.mkdir()
        shutil.copyfile(repo/'scripts/rocketmq/image_fixtures/iam_init.go',prepared/'main.go')
        fixture_binary=directory/'prepare-iam'
        run(['go','build','-o',str(fixture_binary),'./scripts/testing/m3_image_start_fixture'],cwd=source,timeout=300)
        env=dict(os.environ,IAM_IMAGE_FIXTURE_DSN=f'root:{password}@tcp(127.0.0.1:{mysql_port})/{database}?parseTime=true&multiStatements=true')
        run([str(fixture_binary)],cwd=source,env=env,timeout=180)
        case('original_full_schema41_and_bootstrap')
        run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=iam-apiserver','-addext','subjectAltName=DNS:iam-apiserver,IP:127.0.0.1',
             '-keyout',str(fixture/'server.key'),'-out',str(fixture/'server.crt')])
        doc=manifest(repo); principal=dict(username='iam-'+secrets.token_hex(8),password=secrets.token_hex(32))
        # Full fixed manifest but only its exact IAM account; no temporary broad grants.
        owned=copy.deepcopy(doc);owned['accounts']={'m3-iam':owned['accounts']['m3-iam']}
        provision(project+'-broker-1',owned,{'m3-iam':principal})
        write_private(fixture/'credentials.json',principal);write_private(fixture/'routes.json',doc)
        import yaml
        base=yaml.safe_load((source/'configs/apiserver.prod.yaml').read_text())
        for selected in (False,True):
            c=configuration(base,database,password,transaction=selected)
            write_private(fixture/('transaction.json' if selected else 'baseline.json'),c)
        # Restrict fixture files to the image's actual non-root owner.
        for file in fixture.iterdir(): file.chmod(0o700 if file.is_dir() else 0o600)
        def own(uid,gid):
            run(['docker','run','--rm','--user','0','--entrypoint','sh','-v',str(fixture)+':/fixture',image,'-c',f'chown -R {uid}:{gid} /fixture'])
        own(2000,2000)
        network=project+'_rocketmq'
        def start(filename):
            nonlocal app_created
            run(['docker','run','-d','--name',app,'--network',network,'--memory','512m','--cpus','1',
                 '-v',str(fixture)+':/fixture','-v',str(fixture/'keys')+':/app/data/keys',image,'--config=/fixture/'+filename]); app_created=True
        def wait_http(path):
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                require(run(['docker','inspect',app,'--format','{{.State.Running}}']).stdout.strip()=='true','actual_app_exited')
                result=run(['docker','exec',app,'curl','-fsS','--max-time','2','http://127.0.0.1:9080'+path],required=False)
                if result.returncode==0:return result.stdout
                time.sleep(1)
            raise RuntimeError('actual_app_http_budget_exceeded')
        def stop():
            nonlocal app_created
            run(['docker','stop','--time','40',app],timeout=50)
            code=run(['docker','inspect',app,'--format','{{.State.ExitCode}}']).stdout.strip()
            runtime_logs();run(['docker','rm',app]);app_created=False
            require(code=='0','actual_shutdown_not_clean')
        stage='actual_old_chain_fixture_drain'
        start('baseline.json');wait_http('/healthz')
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            pending=sql(f"SELECT (SELECT COUNT(*) FROM {database}.rm_outbox WHERE BINARY state <> 'published')+(SELECT COUNT(*) FROM {database}.domain_event_outbox WHERE BINARY status <> 'published');")
            if pending=='0':break
            time.sleep(1)
        else:raise RuntimeError('original_bootstrap_outbox_not_drained')
        stop();case('actual_old_sdk_nsqueue_bootstrap_drain')
        # Hash all original tables before installing the seven additive objects.
        # No source body or SQL dump leaves this private command capture.
        tables=sql(f"SELECT table_name FROM information_schema.tables WHERE table_schema='{database}' AND table_name <> 'schema_migrations' ORDER BY table_name;").splitlines()
        require(tables and all(t.replace('_','').isalnum() for t in tables),'original_business_tables_required')
        def retained_digest():
            dump=run(compose+['exec','-T','mysql','sh','-c',
                'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --compact --skip-comments --skip-dump-date --no-tablespaces --set-gtid-purged=OFF --skip-lock-tables --column-statistics=0 "$@"',
                'owned-dump',database,*tables]).stdout
            return hashlib.sha256(dump.encode()).hexdigest()
        original_digest=retained_digest()
        stage='original_image_maintenance_restore'
        cli_env=[]
        for key,value in dict(HOST='mysql',PORT='3306',USERNAME='root',PASSWORD=password,DATABASE=database,TLS_MODE='disabled').items(): cli_env+=['-e','IAM_APISERVER_MYSQL_'+key+'='+value]
        def cli(*argv):
            return run(['docker','run','--rm','--network',network,'--entrypoint','/app/iam-maintenance',*cli_env,
                        '-v',str(fixture)+':/fixture',image,*argv],timeout=180).stdout
        def file_sha(name):
            return run(['docker','run','--rm','--network','none','--entrypoint','sha256sum','-v',str(fixture)+':/fixture:ro',image,'/fixture/'+name]).stdout.split()[0]
        cli('m3-messaging-recovery','--store-id','isolated-iam-primary','--writer-epoch','m3-1','--export-protection','/fixture/protection.json')
        protection_sha=file_sha('protection.json')
        def install(prefix):
            cli('m3-messaging','--action','schema','--store-id','isolated-iam-primary','--writer-epoch','m3-1','--export-plan','/fixture/'+prefix+'.json')
            cli('m3-messaging','--apply','--writers-excluded','--plan','/fixture/'+prefix+'.json','--reviewed-sha256',file_sha(prefix+'.json'))
        install('first-schema')
        cli('m3-messaging-recovery','--restore','--writers-excluded','--pre-start-restore-attested','--protection','/fixture/protection.json','--reviewed-sha256',protection_sha)
        case('original_runtime_image_limited_restore',sql(f'SELECT version,dirty FROM {database}.schema_migrations;')=='41\t0')
        case('all_original_business_ddl_and_rows_preserved',retained_digest()==original_digest)
        report['retained_original_tables_sha256']=original_digest
        install('second-schema')
        cli('m3-messaging','--action','select','--store-id','isolated-iam-primary','--writer-epoch','m3-1','--export-plan','/fixture/select.json')
        cli('m3-messaging','--apply','--writers-excluded','--plan','/fixture/select.json','--reviewed-sha256',file_sha('select.json'))
        case('original_schema45_and_binding_selected',sql(f'SELECT version,dirty FROM {database}.schema_migrations;')=='45\t0')
        stage='actual_paused_transaction_image_start'
        start('transaction.json');wait_http('/healthz')
        deadline=time.monotonic()+30
        while True:
            try: report['paused_owner_metrics']=protocol_metrics(wait_http('/metrics'));break
            except RuntimeError:
                if time.monotonic()>=deadline:raise
                time.sleep(1)
        case('actual_standard_config_and_live_paused_owner')
        case('startup_did_not_execute_ddl',sql(f'SELECT version,dirty FROM {database}.schema_migrations;')=='45\t0')
        stop();case('actual_transaction_shutdown_exit_zero')
        report['passed']=len(report['cases'])
    except Exception as error:
        report['failed']=1;report['failure_stage']=stage
        report['failure_kind']=type(error).__name__
        if app_created:runtime_logs()
    finally:
        clean=report['cleanup']
        if app_created:run(['docker','rm','-f',app],required=False)
        clean['application_absent']=not run(['docker','ps','-aq','--filter','name=^/'+app+'$']).stdout.strip()
        clean['compose_down_succeeded']=not started or run(compose+['down','-v','--remove-orphans'],required=False,timeout=150).returncode==0
        if prepared and prepared.exists():shutil.rmtree(prepared)
        # Broker files and non-root runtime-owned private plans require bounded
        # ownership restoration before removing only this temporary directory.
        if image and directory.exists():
            run(['docker','run','--rm','--user','0','--network','none','--entrypoint','sh','-v',str(directory)+':/owned',image,
                 '-c',f'chown -R {os.getuid()}:{os.getgid()} /owned'],required=False)
        shutil.rmtree(directory)
        clean['private_fixture_directory_removed']=not directory.exists()
        for key,argv in (('containers',['docker','ps','-aq']),('networks',['docker','network','ls','-q'])):
            clean['existing_'+key+'_unchanged']=set(run(argv).stdout.split())==before[key]
        clean['host_source_unchanged']=not run(['git','status','--porcelain','--untracked-files=no'],cwd=source).stdout
        if not all(clean.values()):report['failed']=1;report.setdefault('failure_stage','owned_cleanup')
        write_private(args.report,report)
    return int(report['failed']!=0)


if __name__=='__main__':raise SystemExit(main())
