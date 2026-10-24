"""Compose real host maintenance contracts under one reviewed C1 operation.

GitHub-hosted isolated fixtures only. Host tests own their random databases;
this runner never accepts a database name, endpoint or production approval.
"""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from audit_transaction_limit import write_private
from cutover_step import execute,load_step
from start_boundary import initialize,_encoded,BoundaryError

SOURCES={'iam':'36456cdf2f1c980a5edeedce2eee44634097a00d','qs':'83147d8e99e00fd36c57bc2fc4feb193ebe2a844','ai':'05d2db7151d492bec127270d53121396b515f763'}
MONGO='mongo@sha256:340c1c56fb10e95cf79ff547f8664b96bc6ead9909bc355238cbf865a9695a6f'


def require(value,stage):
    if not value:raise RuntimeError(stage)


def ci_guard(env):
    require(env.get('GITHUB_ACTIONS')=='true' and env.get('RUNNER_OS')=='Linux' and env.get('RUNNER_ENVIRONMENT')=='github-hosted', 'github_hosted_only')
    require(not env.get('DOCKER_HOST') and not env.get('DOCKER_CONTEXT'),'external_daemon_refused')


def go_report(path,required):
    events=[json.loads(line) for line in path.read_text().splitlines()]
    ran={e['Test'] for e in events if e.get('Test') and e['Action']=='run'}
    passed={e['Test'] for e in events if e.get('Test') and e['Action']=='pass'}
    require(ran and ran==passed and required<=ran and not any(e['Action'] in ('fail','skip') for e in events),'nonempty_exact_go_gate_required')
    return dict(passed=len(passed),failed=0,skipped=0,test_ids=sorted(ran),raw_sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def python_report(path):
    root=ET.parse(path).getroot();cases=list(root.iter('testcase'))
    require(len(cases)==8 and not any(case.find(name) is not None for case in cases for name in ('skipped','error','failure')),'eight_actual_python_cases_required')
    return dict(passed=len(cases),failed=0,skipped=0,test_ids=sorted(c.attrib['classname']+'.'+c.attrib['name'] for c in cases),raw_sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def compose(*,repo,iam,qs,ai,directory,mysql_port,password,mongo_uri,run,progress):
    """Dependencies must be supplied by this file's owned main fixture, never CLI."""
    ci_guard(os.environ)
    progress['stage']='source_verification'
    sources={'iam':iam.resolve(),'qs':qs.resolve(),'ai':ai.resolve()}
    for name,path in sources.items():
        require(run(['git','rev-parse','HEAD'],cwd=path).stdout.strip()==SOURCES[name] and not run(['git','status','--porcelain','--untracked-files=no'],cwd=path).stdout,'fixed_clean_host_source_required')
    go=shutil.which('go');uv=shutil.which('uv');require(go and uv,'fixed_tools_required')
    go=str(Path(go).resolve());uv=str(Path(uv).resolve())
    run([uv,'sync','--locked'],cwd=ai,timeout=300)
    source_bundle=hashlib.sha256(_encoded(dict(infra=run(['git','rev-parse','HEAD'],cwd=repo).stdout.strip(),hosts=SOURCES))).hexdigest()
    op=directory/'coordinator'
    binding=dict(schema='m3-start-boundary/v1',operation_id='isolated-host-maintenance',directory=str(op),scope_sha256=hashlib.sha256(b'owned-random-host-schema-fixtures').hexdigest(),
        protection_sha256=hashlib.sha256(b'individual-host-protection-fixtures-not-production-backup').hexdigest(),restore_receipt_sha256=hashlib.sha256(b'owned-cleanup-not-production-restore').hexdigest(),
        source_bundle_sha256=source_bundle,data_owner='synthetic-data-owner',recovery_owner='synthetic-recovery-owner')
    binding_sha=hashlib.sha256(_encoded(binding)).hexdigest();initialize(op,binding,binding_sha)
    env=dict(PATH=os.environ['PATH'],GOWORK='off',GOTOOLCHAIN='local',GOPATH=run([go,'env','GOPATH']).stdout.strip(),GOCACHE=run([go,'env','GOCACHE']).stdout.strip(),
        GITHUB_ACTIONS='true',RUNNER_OS='Linux',RUNNER_ENVIRONMENT='github-hosted',
        IAM_M3_TEST_MYSQL_DSN=f'root:{password}@tcp(127.0.0.1:{mysql_port})/mysql?parseTime=true&multiStatements=true',
        QS_M3_TEST_MYSQL_DSN=f'root:{password}@tcp(127.0.0.1:{mysql_port})/mysql?parseTime=true&multiStatements=true',
        QS_M3_REQUIRE_DATABASE='1',QS_SERVER_TEST_MONGO_URI=mongo_uri,
        QS_AI_SCHEMA_TEST_SERVER=f'mysql+pymysql://root:{password}@127.0.0.1:{mysql_port}/mysql',UV_CACHE_DIR=str(directory/'uv-cache'))
    def step(name,kind,script_body,source=repo):
        script=directory/(name+'.sh');script.write_text('#!/bin/bash\nset -euo pipefail\n'+script_body+'\n');script.chmod(0o600)
        plan=dict(schema='m3-cutover-step/v1',directory=str(op),binding_sha256=binding_sha,host=socket.gethostname(),step=name,kind=kind,script=str(script),script_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),cwd=str(source),timeout_seconds=600)
        file=directory/(name+'-plan.json');file.write_bytes(_encoded(plan));file.chmod(0o600)
        progress['stage']=name
        digest=hashlib.sha256(file.read_bytes()).hexdigest();loaded,raw=load_step(file,digest)
        state=execute(loaded,raw,digest)
        progress.setdefault('completed_steps',[]).append(name)
        return state
    def command(argv,out):
        return '\n'.join('export '+k+'='+shlex.quote(v) for k,v in env.items())+'\n'+shlex.join(argv)+' > '+shlex.quote(str(out))+' 2> '+shlex.quote(str(out)+'.private.stderr')
    outputs={name:directory/(name+('-raw.xml' if name=='ai' else '-raw.jsonl')) for name in sources}
    # Each original host contract retains its own distinct protection/schema
    # boundary. Sharing a coordinator does not merge its database transactions.
    step('iam-maintenance','pre-start-maintenance',command([go,'test','-race','-tags=integration','-json','-count=1','-timeout=5m','./cmd/iam-maintenance','-run','^TestM3MessagingOfflineNative$'],outputs['iam']),iam)
    step('qs-maintenance','pre-start-maintenance',command([go,'test','-race','-tags=integration','-json','-count=1','-timeout=6m','./internal/pkg/migration','-run','^Test(M3InitialBindingCLINative|OfflineNative.*)$'],outputs['qs']),qs)
    # JUnit XML stays separate from captured private raw stdout/stderr.
    step('ai-maintenance','pre-start-maintenance',command([uv,'run','--no-sync','python','-m','pytest','-q','tests/integration/test_transaction_schema.py','tests/integration/test_initial_transaction_binding.py','--junitxml='+str(outputs['ai'])],directory/'ai-private.log'),ai)
    reports={}
    for name,required in [('iam',{'TestM3MessagingOfflineNative'}),('qs',{'TestM3InitialBindingCLINative','TestOfflineNativeUpgradeAndFreshNoop','TestOfflineNativeSQLPartialFailureRemainsDirty','TestOfflineNativeMongoPartialFailureRemainsDirty'}),('ai',set())]:
        progress['stage']='report-'+name
        reports[name]=python_report(outputs[name]) if name=='ai' else go_report(outputs[name],required)
        progress.setdefault('reports',{})[name]=reports[name]
    # This is an explicitly labelled process sentinel, not a business runtime.
    marker=directory/'runtime-sentinel'
    step('first-runtime-sentinel','runtime-start','touch '+shlex.quote(str(marker)))
    require(marker.exists(),'first_start_not_recorded')
    refusals=[]
    for name in sources:
        forbidden=directory/('forbidden-'+name)
        try:step(name+'-forbidden-poststart','pre-start-maintenance','touch '+shlex.quote(str(forbidden)))
        except BoundaryError:pass
        else:raise RuntimeError('poststart_maintenance_not_refused')
        require(not forbidden.exists(),'rejected_maintenance_executed')
        refusals.append(name)
    for name,path in sources.items():require(not run(['git','status','--porcelain','--untracked-files=no'],cwd=path).stdout,'tracked_host_source_changed')
    return dict(source_bundle_sha256=source_bundle,host_sources=SOURCES,reports=reports,post_start_refused=refusals,
        production_authorized=False,actual_runtime=False,actual_writer_freeze=False,actual_production_backup_restore=False,
        scope='same C1 operation, actual individual host maintenance/DDL/binding test contracts; synthetic process sentinel; not a shared business DB or production cutover')
