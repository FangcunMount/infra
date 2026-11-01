"""Actual immutable ACR AI44 image: owned restore and two paused starts.

Hosted Linux fixture only. No production database, Broker, provider or upstream
RPC inputs. The recovery archive shares the verified production candidate code;
it qualifies a44 restart/configuration repair, not a cure for unknown code bugs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import time

from ai_image_start import KEY_PROGRAM, PYTHON, messaging, metrics
from audit_transaction_limit import write_private
from final_image_candidate import saved_config, sha256
from image_sdk_profile import sdk_profile, verify_readable_python_lock
from image_start_fixture import OwnedImageFixture, require

HEAD = '0044_empty_publisher'
CMD = [PYTHON, '-m', 'qs_ai.bootstrap.server']


def verify_registry_identity(inspected, reference, source):
    require(re.fullmatch('[0-9a-f]{40}', source) is not None, 'exact_source_required')
    require(re.fullmatch(r'[A-Za-z0-9.-]+(?::[0-9]+)?/[A-Za-z0-9_./-]+@sha256:[0-9a-f]{64}', reference) is not None,
            'immutable_registry_reference_required')
    config = inspected['Config']
    require(inspected['Os'] == 'linux' and inspected['Architecture'] == 'amd64'
            and reference in inspected.get('RepoDigests', [])
            and config.get('Labels', {}).get('org.opencontainers.image.revision') == source
            and 'QS_AI_RELEASE_SHA='+source in config.get('Env', [])
            and config.get('User') == 'app' and config.get('Cmd') == CMD
            and config.get('Entrypoint') in (None, []), 'exact_ai44_image_identity_required')
    return reference.rsplit('@', 1)[1]


def load_registry(fixture, reference, source, output):
    inspected = json.loads(fixture.run(['docker', 'image', 'inspect', reference]).stdout)[0]
    digest = verify_registry_identity(inspected, reference, source)
    fixture.image = 'ai44-qualified:'+source[:12]+'-'+secrets.token_hex(4)
    fixture.run(['docker', 'tag', reference, fixture.image])
    code = ('import json,os,importlib.metadata as m; d=m.distribution("fangcun-reliable-messaging"); '
            'print(json.dumps(dict(uid=os.getuid(),sdk=d.version,client=m.version("rocketmq-python-client"),'
            'source=os.environ["QS_AI_RELEASE_SHA"],direct_url=json.loads(d.read_text("direct_url.json")))))')
    raw = fixture.once(PYTHON, ['-c', code], network=False, environment={'HOME':'/tmp'})
    runtime = json.loads(raw)
    expected = sdk_profile('readable-stable')
    # uv does not preserve wheel hashes in direct_url.json. Compare every actual
    # package file with the exact public wheel whose archive digest is locked.
    import io, urllib.request, zipfile
    with urllib.request.urlopen(expected['wheel_url'],timeout=30) as response:
        wheel=response.read(4*1024*1024+1)
    require(len(wheel)<=4*1024*1024 and hashlib.sha256(wheel).hexdigest()==expected['wheel_sha256'],'exact_locked_wheel_required')
    with zipfile.ZipFile(io.BytesIO(wheel)) as z:
        inventory={name:hashlib.sha256(z.read(name)).hexdigest() for name in z.namelist() if name.startswith('reliable_messaging/') and not name.endswith('/')}
    require(inventory and len(inventory)<=1000 and all('..' not in Path(n).parts for n in inventory),'bounded_sdk_payload_required')
    write_private(fixture.private/'sdk-payload.json',inventory);fixture.ownership(10001)
    verify_code=('import hashlib,importlib.metadata as m,json; from pathlib import Path; d=m.distribution("fangcun-reliable-messaging"); '
                 'expected=json.loads(Path("/fixture/sdk-payload.json").read_text()); '
                 'ok=all(hashlib.sha256(d.locate_file(n).read_bytes()).hexdigest()==v for n,v in expected.items()); '
                 'print(json.dumps(dict(files=len(expected),matched=ok))); raise SystemExit(0 if ok else 1)')
    payload=json.loads(fixture.once(PYTHON,['-c',verify_code],network=False,environment={'HOME':'/tmp'}))
    require(payload['matched'] is True and payload['files']==len(inventory),'actual_installed_sdk_payload_required')
    require(runtime['uid'] == 10001 and runtime['sdk'] == '0.5.0' and runtime['client'] == '5.1.2'
            and runtime['source'] == source
            and runtime['direct_url']['url'] == expected['wheel_url']
            and payload['matched'] is True,
            'actual_locked_image_sdk_required')
    archive = output/'ai44-forward-image.tar.gz'
    raw_tar = output/'owned-image.tar'
    fixture.run(['docker', 'save', '--output', str(raw_tar), fixture.image], timeout=300)
    config_id, config = saved_config(raw_tar, fixture.image)
    require(config['config']['Cmd'] == CMD and config['config']['User'] == 'app', 'saved_image_configuration_differs')
    import subprocess
    with archive.open('wb') as stream:
        subprocess.run(['gzip', '-1', '-c', str(raw_tar)], stdout=stream, check=True)
    archive.chmod(0o600);raw_tar.unlink()
    proof = dict(source_sha=source, registry_digest=digest, engine_image_id=inspected['Id'],
                 image_config_id=config_id, archive_sha256=sha256(archive), archive_bytes=archive.stat().st_size,
                 archive_tag=fixture.image, sdk=runtime['sdk'], client=runtime['client'], uid=runtime['uid'],
                 wheel_sha256=expected['wheel_sha256'], installed_sdk_files_verified=payload['files'], shared_production_and_recovery_code=True)
    fixture.report['candidate'] = proof
    return proof


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--source-sha',required=True)
    parser.add_argument('--image',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();source=args.source.resolve();output=args.output.resolve()
    require(re.fullmatch('[0-9a-f]{40}',args.source_sha) is not None,'exact_source_required')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    report=dict(schema='ai246-actual-registry-image44-qualification/v1',source_sha=args.source_sha,
                production=False,system_acceptance=False,model_or_upstream_requests_exercised=False,
                passed=0,failed=0,skipped=0,cases={},scope='owned44 full restore and paused full-runtime/Checker starts before and after retained new fixture facts; no43 replay')
    repo=Path(__file__).resolve().parents[2];fixture=OwnedImageFixture(repo,report);run=fixture.run
    apps=[]
    def case(name,condition=True):require(condition,name);report['cases'][name]=True
    def sql(statement):return fixture.sql(statement)
    try:
        require(run(['git','rev-parse','HEAD'],cwd=source).stdout.strip()==args.source_sha
                and not run(['git','status','--porcelain','--untracked-files=no'],cwd=source).stdout,'fixed_clean_ai_source_required')
        report['infra_sha']=run(['git','rev-parse','HEAD'],cwd=repo).stdout.strip()
        verify_readable_python_lock((source/'uv.lock').read_text(),'readable-stable')
        load_registry(fixture,args.image,args.source_sha,output)
        case('exact_registry_digest_source_config_and_installed_sdk')
        fixture.dependencies();database='ai44_image_'+secrets.token_hex(8)
        sql('CREATE DATABASE `'+database+'`;')
        env=dict(QS_AI_ENVIRONMENT='production',QS_AI_DATABASE_TLS_MODE='DISABLED',
                 QS_AI_DATABASE_URL=f'mysql+asyncmy://root:{fixture.password}@mysql:3306/{database}',
                 HOME='/tmp',GRPC_DEFAULT_SSL_ROOTS_FILE_PATH='/fixture/mq-ca.crt')
        fixture.stage='actual_fresh44_install'
        fixture.once(PYTHON,['-m','alembic','upgrade','head'],environment=env)
        def head():return sql(f'SELECT version_num FROM `{database}`.alembic_version;')
        def target():return sql(f"SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='{database}' AND TABLE_NAME='messaging_outbox';")
        fixture.once(PYTHON,['-m','qs_ai.bootstrap.database_check','--require-head'],environment=env)
        case('actual_original_image_installs_full44_without_legacy_table',head()==HEAD and target()=='0')
        fixture.ownership(10001)
        command=['-m','qs_ai.maintenance.transaction_binding'];plan='/fixture/binding.json'
        fixture.once(PYTHON,command+['--action','preview','--plan',plan,'--operation-id','owned-ai44-image','--store-id','isolated-ai-primary','--writer-epoch','m3-1'],environment=env)
        digest=fixture.once('/usr/bin/sha256sum',[plan],network=False).split()[0]
        fixture.once(PYTHON,command+['--action','apply','--plan',plan,'--reviewed-sha256',digest,'--writers-excluded'],environment=env)
        fixture.once(PYTHON,command+['--action','verify','--plan',plan,'--reviewed-sha256',digest],environment=env)
        case('actual44_initial_binding_cli_verified')
        def insert_fact(number):
            sql(f"INSERT INTO `{database}`.messaging_event_receipts VALUES('qs-server','owned-ack-{number}','owned-event-{number}',7,0x00ff,0x00ff03,1,'2026-11-01 00:00:00.000000');")
        def facts():return sql(f"SELECT HEX(producer),HEX(ack_id),HEX(event_id),organization_id,HEX(header),HEX(body),outcome,recorded_at FROM `{database}`.messaging_event_receipts ORDER BY producer,ack_id;")
        insert_fact(1);original=facts();protection=fixture.dump(database)
        backup=fixture.directory/'original44.sql';backup.write_text(protection);backup.chmod(0o600)
        report['original44_full_protection_sha256']=hashlib.sha256(protection.encode()).hexdigest()
        fixture.stage='owned_full44_restore'
        sql('DROP DATABASE `'+database+'`; CREATE DATABASE `'+database+'`;')
        sql('SET FOREIGN_KEY_CHECKS=0; USE `'+database+'`;\n'+protection+'\nSET FOREIGN_KEY_CHECKS=1;')
        fixture.once(PYTHON,['-m','qs_ai.bootstrap.database_check','--require-head'],environment=env)
        case('actual_full44_restore_preserves_binary_fact_binding_and_ledger',fixture.dump(database)==protection and facts()==original and head()==HEAD and target()=='0')
        fixture.ownership(os.getuid());fixture.provision('m3-ai')
        run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=qs-ai.svc/OU=QS',
             '-addext','subjectAltName=DNS:ai,DNS:qs-ai.svc','-keyout',str(fixture.private/'server.key'),'-out',str(fixture.private/'server.crt')])
        script=fixture.private/'make_keys.py';script.write_text(KEY_PROGRAM);script.chmod(0o600)
        fixture.ownership(10001);fixture.once(PYTHON,['/fixture/make_keys.py'],network=False,environment={'HOME':'/tmp'})
        password=secrets.token_hex(32)
        sql(f"CREATE USER 'ai_runtime'@'%' IDENTIFIED BY '{password}'; GRANT SELECT,INSERT,UPDATE,DELETE ON `{database}`.* TO 'ai_runtime'@'%'; SET GLOBAL log_output='TABLE'; SET GLOBAL general_log='ON';")
        runtime_env=dict(env,QS_AI_DATABASE_URL=f'mysql+asyncmy://ai_runtime:{password}@mysql:3306/{database}',
            QS_AI_MESSAGING=json.dumps(messaging()),
            QS_AI_GRPC=json.dumps(dict(bind_address='0.0.0.0:50061',access_address='qs-fixture:9090',ca_file='/fixture/server.crt',cert_file='/fixture/server.crt',key_file='/fixture/server.key')),
            QS_AI_GENERATION__ENABLED='true',QS_AI_EVALUATION__ENABLED='true',
            QS_AI_DEEPSEEK_API_KEY='owned-unused-fixture-key',QS_AI_ZHIPU_API_KEY='owned-unused-fixture-key')
        envfile=fixture.directory/'runtime.env';envfile.write_text(''.join(k+'='+v+'\n' for k,v in runtime_env.items()));envfile.chmod(0o600)
        report['runtime_environment_sha256']=sha256(envfile)
        def start_stop(suffix):
            fixture.stage='actual44_'+suffix+'_paused_start';app=fixture.project+'-ai-'+suffix
            run(['docker','run','-d','--name',app,'--label',fixture.label,'--network',fixture.network,'--memory','768m','--cpus','0.75',
                 '--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--security-opt','no-new-privileges:true','--cap-drop','ALL',
                 '--env-file',str(envfile),'-v',str(fixture.private)+':/fixture:ro',fixture.image]);apps.append(app)
            def get(path):return run(['docker','exec',app,PYTHON,'-c',"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000"+path+"',timeout=2).read().decode())"],required=False)
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                require(run(['docker','inspect',app,'--format','{{.State.Running}}']).stdout.strip()=='true','actual_ai_process_exited')
                if get('/readyz').returncode==0:
                    try:report[suffix+'_paused_metrics']=metrics(get('/metrics').stdout);break
                    except RuntimeError:pass
                time.sleep(1)
            else:raise RuntimeError('actual_ai_ready_budget_exceeded')
            case(suffix+'_actual_readonly44_ready_and_checker_live')
            run(['docker','stop','--time','210',app],timeout=225)
            state=json.loads(run(['docker','inspect',app]).stdout)[0]['State']
            private=run(['docker','logs',app],required=False);raw=private.stdout+private.stderr
            report[suffix+'_private_log_sha256']=hashlib.sha256(raw.encode()).hexdigest()
            require(not any(name in raw for name in ('drain_timeout','transaction_shutdown_incomplete','component_stopped_with_error')),'actual_ai_drain_incomplete')
            case(suffix+'_graceful_zero_exit_no_oom',state['Status']=='exited' and state['ExitCode']==0 and not state['OOMKilled'])
        start_stop('candidate')
        case('original_binary_fact_preserved_after_candidate_start',facts()==original)
        # A new retained fixture fact is deliberately added AFTER the first start.
        # Never replay the old dump after this boundary; recover using the same44 image.
        insert_fact(2);new=facts();case('new_fact_retained_before_forward_start',new!=original)
        start_stop('forward')
        case('forward_start_keeps_all_original_and_new_facts_without_restore',facts()==new and head()==HEAD and target()=='0')
        ddl=sql("SELECT COUNT(*) FROM mysql.general_log WHERE user_host LIKE 'ai_runtime%' AND command_type IN ('Query','Prepare','Execute') AND UPPER(argument) REGEXP '^[[:space:]]*(CREATE|ALTER|DROP|TRUNCATE|RENAME)[[:space:]]';")
        report['runtime_DDL_attempts']=int(ddl)
        case('both_actual_starts_and_shutdowns_attempt_no_DDL',ddl=='0')
        case('no_model_call_dispatched',sql(f'SELECT COUNT(*) FROM `{database}`.execution_model_calls;')=='0')
    except Exception as error:
        report['failed']=1;report['failure_stage']=fixture.stage;report['failure_kind']=type(error).__name__
        if str(error) in {'actual_ai_process_exited','actual_ai_ready_budget_exceeded','actual_ai_drain_incomplete'}:report['failure_reason']=str(error)
        for app in apps:
            private=run(['docker','logs',app],required=False);raw=private.stdout+private.stderr
            report.setdefault('failed_private_logs_sha256',[]).append(hashlib.sha256(raw.encode()).hexdigest())
            report.setdefault('source_frames',[]).extend(dict(path=p,line=int(n)) for p,n in re.findall(r'File "[^"\n]*/(qs_ai/[^"\n]+\.py)", line ([0-9]+)',raw)[-12:])
    finally:
        report['passed']=len(report['cases'])
        tag=fixture.image
        try:
            fixture.cleanup()
            if tag:run(['docker','image','rm',tag]);report['cleanup']['owned_image_alias_absent']=run(['docker','image','inspect',tag],required=False).returncode!=0
        except Exception:report['failed']=1;report.setdefault('failure_stage','owned_cleanup')
        report['source_unchanged']=not run(['git','status','--porcelain','--untracked-files=no'],cwd=source).stdout
        if not report['source_unchanged']:report['failed']=1
        write_private(output/'ai44-image-qualification.json',report)
    return int(report['failed']!=0)


if __name__=='__main__':raise SystemExit(main())
