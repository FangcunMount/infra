"""Actual fixed AI image, original Alembic/initial binding, restore and lifecycle.

Only controlled fixture state. No system/provider/paired or production claim.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import time

from audit_transaction_limit import write_private
from image_start_fixture import OwnedImageFixture, require

AI_SHA='ddff86cad27d03c95dad28490d6cccbc1ce5b15f'
HEAD='0043_native_transaction_limit'
OLD_HEAD='0040_module_table_names'
PYTHON='/app/.venv/bin/python'


def messaging():
    return dict(enabled=True,provider='rocketmq',publish_enabled=False,max_in_flight=1,
        rocketmq=dict(endpoint='broker:8081',credentials_file='/fixture/credentials.json',ca_file='/fixture/mq-ca.crt',routes_file='/fixture/routes.json'),
        signing_key_file='/fixture/ai-sign-private.json',decrypt_key_files={'ai-decrypt':'/fixture/ai-decrypt-private.json'},
        qs_signer_files={'qs-sign':'/fixture/qs-sign-public.json'},qs_recipient_key_file='/fixture/qs-recipient-public.json',
        transactions={'ai.mysql':dict(store_id='isolated-ai-primary',writer_epoch='m3-1',route_revision='m3-1')})


def metrics(raw):
    wanted=dict(sdk_ready=1,sampler_running=1,observation_available=1,admission_open=0,check_workers_limit=1,check_queue_limit=16)
    for key,value in wanted.items():
        require(f'reliable_messaging_transaction_{key}{{owner="ai.mysql"}} {value}' in raw.splitlines(),'actual_paused_ai_metrics_required:'+key)
    return wanted


KEY_PROGRAM='''from jwcrypto import jwk
from pathlib import Path
for name in ('ai-sign','ai-decrypt','qs-sign','qs-recipient'):
    key=jwk.JWK.generate(kty='EC',crv='P-256',kid=name)
    for private in (False,True):
        p=Path('/fixture')/(name+('-private.json' if private else '-public.json'))
        p.write_text(key.export(private_key=private));p.chmod(0o600)
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','candidate','report'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();require(not args.report.exists(),'new_report_required')
    repo=Path(__file__).resolve().parents[2]
    report=dict(schema='m3-ai-actual-image-start/v1',ai_sha=AI_SHA,passed=0,failed=0,skipped=0,cases={},
        production=False,system_acceptance=False,combined_cutover_rehearsal_complete=False,
        scope='actual read-only AI image/original migrations/restore/initial binding/paused lifecycle; controlled retained fact; no model or upstream RPC exercised')
    fixture=OwnedImageFixture(repo,report);run=fixture.run;source=args.source.resolve()
    app=fixture.project+'-ai';app_created=False
    report['infra_sha']=run(['git','rev-parse','HEAD'],cwd=repo).stdout.strip()
    def case(name,condition=True):require(condition,name);report['cases'][name]=True
    def logs():
        result=run(['docker','logs',app],required=False);raw=result.stdout+result.stderr
        report['private_application_log_sha256']=hashlib.sha256(raw.encode()).hexdigest()
        frames=re.findall(r'File "[^"\n]*/(qs_ai/[^"\n]+\.py)", line ([0-9]+)',raw)
        report['application_source_frames']=[dict(path=path,line=int(line)) for path,line in frames[-24:]]
        state=json.loads(run(['docker','inspect',app]).stdout)[0]['State']
        report['application_process_state']={key:state[key] for key in ('Status','ExitCode','OOMKilled')}
    try:
        require(run(['git','rev-parse','HEAD'],cwd=source).stdout.strip()==AI_SHA and not run(['git','status','--porcelain','--untracked-files=no'],cwd=source).stdout,'fixed_clean_ai_source_required')
        metadata=fixture.load(args.candidate,'ai',AI_SHA)
        case('exact_stable_ai_archive_loaded',metadata['runtime_sdk']==dict(uid=10001,version='0.4.0',client='5.1.2',source=AI_SHA))
        fixture.dependencies();database='ai_m3_image_'+secrets.token_hex(8)
        fixture.sql('CREATE DATABASE `'+database+'`;')
        base_env=dict(QS_AI_ENVIRONMENT='production',QS_AI_DATABASE_TLS_MODE='DISABLED',
            QS_AI_DATABASE_URL=f'mysql+asyncmy://root:{fixture.password}@mysql:3306/{database}',
            HOME='/tmp',GRPC_DEFAULT_SSL_ROOTS_FILE_PATH='/fixture/mq-ca.crt')
        fixture.stage='original_alembic40'
        fixture.once(PYTHON,['-m','alembic','upgrade',OLD_HEAD],environment=base_env)
        fixture.sql(f"CREATE TABLE `{database}`.fixture_retained_state(id INT PRIMARY KEY,value BINARY(32) NOT NULL); INSERT INTO `{database}`.fixture_retained_state VALUES(1,UNHEX(SHA2('owned controlled state',256)));")
        old=fixture.sql(f'SELECT version_num FROM `{database}`.alembic_version;')
        case('original_alembic40_and_nonempty_controlled_fact',old==OLD_HEAD)
        fixture.stage='actual_full_scope_restore'
        protection=fixture.dump(database);backup=fixture.directory/'original-protection.sql';backup.write_text(protection);backup.chmod(0o600)
        report['protection_sha256']=hashlib.sha256(protection.encode()).hexdigest()
        fixture.once(PYTHON,['-m','alembic','upgrade','head'],environment=base_env)
        case('first_explicit_alembic43',fixture.sql(f'SELECT version_num FROM `{database}`.alembic_version;')==HEAD)
        fixture.sql('DROP DATABASE `'+database+'`; CREATE DATABASE `'+database+'`;')
        fixture.sql('SET FOREIGN_KEY_CHECKS=0; USE `'+database+'`;\n'+protection+'\nSET FOREIGN_KEY_CHECKS=1;')
        case('original_full_scope_restored_exactly',fixture.dump(database)==protection and fixture.sql(f'SELECT version_num FROM `{database}`.alembic_version;')==OLD_HEAD)
        fixture.once(PYTHON,['-m','alembic','upgrade','head'],environment=base_env)
        fixture.stage='original_initial_binding'
        fixture.ownership(10001)
        plan='/fixture/binding.json'
        command=['-m','qs_ai.maintenance.transaction_binding']
        fixture.once(PYTHON,command+['--action','preview','--plan',plan,'--operation-id','owned-ai-image','--store-id','isolated-ai-primary','--writer-epoch','m3-1'],environment=base_env)
        digest=fixture.once('/usr/bin/sha256sum',[plan],network=False).split()[0]
        require(re.fullmatch('[0-9a-f]{64}',digest),'original_binding_digest_required')
        fixture.once(PYTHON,command+['--action','apply','--plan',plan,'--reviewed-sha256',digest,'--writers-excluded'],environment=base_env)
        fixture.once(PYTHON,command+['--action','verify','--plan',plan,'--reviewed-sha256',digest],environment=base_env)
        case('original_initial_binding_cli_applied_and_verified')
        fixture.stage='private_keys_and_exact_ai_resources'
        fixture.ownership(os.getuid())
        fixture.provision('m3-ai')
        # A production-shaped read-only root requires the pinned client's home
        # log path to live inside the existing bounded /tmp, before SDK import.
        fixture.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=qs-ai.svc/OU=QS',
            '-addext','subjectAltName=DNS:ai,DNS:qs-ai.svc','-keyout',str(fixture.private/'server.key'),'-out',str(fixture.private/'server.crt')])
        key_script=fixture.private/'make_keys.py';key_script.write_text(KEY_PROGRAM);key_script.chmod(0o600)
        fixture.ownership(10001);fixture.once(PYTHON,['/fixture/make_keys.py'],network=False,environment={'HOME':'/tmp'})
        runtime_password=secrets.token_hex(32)
        fixture.sql(f"CREATE USER 'ai_runtime'@'%' IDENTIFIED BY '{runtime_password}'; GRANT SELECT,INSERT,UPDATE,DELETE ON `{database}`.* TO 'ai_runtime'@'%'; SET GLOBAL log_output='TABLE'; SET GLOBAL general_log='ON';")
        runtime_env=dict(base_env,QS_AI_DATABASE_URL=f'mysql+asyncmy://ai_runtime:{runtime_password}@mysql:3306/{database}',
            QS_AI_MESSAGING=json.dumps(messaging()),
            QS_AI_GRPC=json.dumps(dict(bind_address='0.0.0.0:50061',access_address='qs-fixture:9090',ca_file='/fixture/server.crt',cert_file='/fixture/server.crt',key_file='/fixture/server.key')),
            QS_AI_GENERATION__ENABLED='true',QS_AI_EVALUATION__ENABLED='true',
            QS_AI_DEEPSEEK_API_KEY='owned-unused-fixture-key',QS_AI_ZHIPU_API_KEY='owned-unused-fixture-key')
        env=fixture.directory/'runtime.env';env.write_text(''.join(key+'='+value+'\n' for key,value in runtime_env.items()));env.chmod(0o600)
        report['runtime_environment_sha256']=hashlib.sha256(env.read_bytes()).hexdigest()
        fixture.stage='actual_read_only_paused_start'
        run(['docker','run','-d','--name',app,'--label',fixture.label,'--network',fixture.network,'--memory','768m','--cpus','0.75',
            '--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','--security-opt','no-new-privileges:true','--cap-drop','ALL',
            '--env-file',str(env),'-v',str(fixture.private)+':/fixture:ro',fixture.image]);app_created=True
        def get(path):
            return run(['docker','exec',app,PYTHON,'-c',
                "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000"+path+"',timeout=2).read().decode())"],required=False)
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            require(run(['docker','inspect',app,'--format','{{.State.Running}}']).stdout.strip()=='true','actual_ai_process_exited')
            result=get('/readyz')
            if result.returncode==0:
                try:report['paused_owner_metrics']=metrics(get('/metrics').stdout);break
                except RuntimeError:pass
            time.sleep(1)
        else:raise RuntimeError('actual_ai_ready_budget_exceeded')
        case('actual_readonly_server_ready_and_paused_checker_live')
        run(['docker','stop','--time','210',app],timeout=225);logs()
        case('actual_ai_shutdown_exit_zero',report['application_process_state']==dict(Status='exited',ExitCode=0,OOMKilled=False))
        ddl=fixture.sql("SELECT COUNT(*) FROM mysql.general_log WHERE user_host LIKE 'ai_runtime%' AND command_type='Query' AND UPPER(argument) REGEXP '^[[:space:]]*(CREATE|ALTER|DROP|TRUNCATE|RENAME)[[:space:]]';")
        report['runtime_ddl_attempts']=int(ddl)
        case('actual_ai_start_and_shutdown_without_ddl_attempt',ddl=='0' and fixture.sql(f'SELECT version_num FROM `{database}`.alembic_version;')==HEAD)
    except Exception as error:
        report['failed']=1;report['failure_stage']=fixture.stage;report['failure_kind']=type(error).__name__
        if str(error) in {'actual_ai_process_exited','actual_ai_ready_budget_exceeded'}:report['failure_reason']=str(error)
        if app_created:logs()
    finally:
        report['passed']=len(report['cases'])
        try:fixture.cleanup()
        except Exception:report['failed']=1;report.setdefault('failure_stage','owned_cleanup')
        report['source_unchanged']=not run(['git','status','--porcelain','--untracked-files=no'],cwd=source).stdout
        if not report['source_unchanged']:report['failed']=1
        write_private(args.report,report)
    return int(report['failed']!=0)


if __name__=='__main__':raise SystemExit(main())
