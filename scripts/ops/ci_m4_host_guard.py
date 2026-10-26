"""Real deploy-user/root guard boundary on an ephemeral GitHub-hosted runner.

No Docker, DB, MQ, SSH, business transaction or model is started. All fixed
namespaces must be absent; cleanup is restricted to this run's marked roots.
"""
import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import tempfile

import m4_material_stage as m

TOOL_ROOT=Path('/opt/fangcun-m4')
PLAN_ROOT=Path('/var/lib/fangcun-m4')
REVISION='m4-host-guard-fixture'


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',type=Path,required=True)
    args=parser.parse_args()
    assert os.geteuid()==0 and os.environ.get('GITHUB_ACTIONS')=='true'
    assert os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted' and sys.platform=='linux'
    assert os.readlink('/proc/self/ns/mnt')!=os.readlink('/proc/1/ns/mnt')
    caller=int(os.environ['SUDO_UID']);assert caller>0
    caller_gid=pwd.getpwuid(caller).pw_gid;caller_name=pwd.getpwuid(caller).pw_name
    root=Path(__file__).resolve().parents[2]
    operator=Path(__file__).with_name('m4_material_stage.py')
    digest=hashlib.sha256(operator.read_bytes()).hexdigest()
    namespaces=(m.BASE,PLAN_ROOT,TOOL_ROOT)
    assert all(not p.exists() and not p.is_symlink() for p in namespaces)
    report=dict(schema='m4-host-material-guard/v1',source_sha=os.environ['GITHUB_SHA'],
                operator_sha256=digest,passed=0,failed=0,errors=0,skipped=0,cases=[],
                production=False,application_started=False,network_clients_started=False,sources={})
    current_case='owned_setup';owned=None;created=[];private_opt=False
    original_opt=Path('/opt').stat()
    try:
        owned=Path(tempfile.mkdtemp(prefix='m4-host-guard-',dir=os.environ['RUNNER_TEMP'])).resolve()
        owned.chmod(0o755)
        # Hosted runners make /opt world-writable. Keep the real production guard
        # intact; bind only an owned immutable ancestor inside our private mount
        # namespace. Never chmod or chown the original /opt.
        immutable_opt=owned/'private-opt';immutable_opt.mkdir(mode=0o755);immutable_opt.chmod(0o755)
        subprocess.run(['/usr/bin/mount','--bind',str(immutable_opt),'/opt'],check=True,capture_output=True)
        private_opt=True
        report['private_mount_namespace']=True
        identity=(str(owned)+'\n').encode()
        tool=TOOL_ROOT/'material-tools'/(digest+'.py')
        for p in namespaces:
            p.mkdir(mode=0o755);p.chmod(0o755);created.append(p)
            marker=p/'.ci-owned';marker.write_bytes(identity);marker.chmod(0o600)
        tool.parent.mkdir(mode=0o755);tool.parent.chmod(0o755)
        tool.write_bytes(operator.read_bytes());tool.chmod(0o555)
        m.PLANS.mkdir(mode=0o700);m.PLANS.chmod(0o700)
        raw_source=owned/'sources';raw_source.mkdir(mode=0o700)
        client=owned/'client';client.mkdir(mode=0o700);os.chown(client,caller,caller_gid)
        original_sources=[];plans={};targets={};pointers={};before_pointers={};blocks={}
        for name in ('iam','qs','ai'):
            source=(args.sources/name).resolve()
            git=['sudo','-n','-u',caller_name,'git']
            sha=subprocess.check_output(git+['rev-parse','HEAD'],cwd=source,text=True).strip()
            assert re.fullmatch('[a-f0-9]{40}',sha)
            assert not subprocess.check_output(git+['status','--porcelain'],cwd=source)
            report['sources'][name]=sha
        iam=args.sources/'iam';qs=args.sources/'qs';ai=args.sources/'ai'
        guard=(iam/'scripts/cd/material-guard.sh').read_bytes()
        assert guard==(qs/'scripts/cd/material-guard.sh').read_bytes()
        assert ('M4_MATERIAL_TOOL_SHA256='+digest).encode() in guard
        assert ('MATERIAL_TOOL_SHA256 = "'+digest+'"').encode() in (ai/'deploy/serverA/deploy.py').read_bytes()
        iam_main=(iam/'scripts/cd/remote-deploy.sh').read_text().split('acquire_image_deploy_lock\n',1)[1]
        start=iam_main.index('ROCKETMQ_BINDING_REVISION=$(sed')
        blocks['iam']=iam_main[start:iam_main.index('\nsync_package\n',start)]
        qs_main=(qs/'scripts/cd/remote-deploy.sh').read_text().split('acquire_image_deploy_lock\n',1)[1]
        start=qs_main.index('if [ "$SERVICE" = worker ]; then')
        blocks['worker']=qs_main[start:qs_main.index('\n# Verify the public CA',start)]
        start=qs_main.index('  mq_material_revision=')
        blocks['qs-api']=qs_main[start:qs_main.index('  while IFS= read -r mq_retained_image',start)]
        assert all(qs_main.index('m4_material_preflight '+r+' ')<qs_main.index('\nsync_configs\n') for r in ('worker','qs-api'))
        for role,(_,stem,gid) in m.ROLES.items():
            files=[]
            wanted=['rocketmq/credentials.json','rocketmq/ca.crt','rocketmq/routes.json']
            if role=='qs-api':wanted.append('rocketmq/mongo-credentials.json')
            if role in ('qs-api','ai'):wanted += [r+'.fixture.json' for r in ('qs.sign','qs.encrypt','ai.sign','ai.encrypt')]
            for target in wanted:
                source=raw_source/(role+'-'+Path(target).name)
                body=('isolated synthetic material '+role+' '+target).encode()
                source.write_bytes(body);source.chmod(0o400);original_sources.append(source)
                files.append(dict(source=str(source),target=target,sha256=m.sha(body),bytes=len(body),source_uid=0,source_gid=0,source_mode=0o400))
            plan=dict(schema='m4-material-stage/v1',host=m.ROLES[role][0],role=role,revision=REVISION,source_receipt_sha256='a'*64,files=files)
            m.stage(plan,apply=True,source_roots=(raw_source,))
            raw=(json.dumps(plan,indent=2)+'\n').encode();plan_path=m.PLANS/(m.sha(raw)+'.json')
            plan_path.write_bytes(raw);plan_path.chmod(0o600);plans[role]=plan_path
            target=m.BASE/stem/'versions'/REVISION;targets[role]=target
            pointer=target.parent.parent/'current.json';pointer.write_bytes(b'original active pointer bytes');pointer.chmod(0o440)
            pointers[role]=pointer;before_pointers[role]=(pointer.stat().st_ino,pointer.read_bytes(),pointer.stat().st_mtime_ns)
            package=client/role;(package/'configs/env').mkdir(parents=True)
            (package/'configs/env/config.prod.env').write_text('ROCKETMQ_BINDING_REVISION='+REVISION+'\nROCKETMQ_WORKER_BINDING_REVISION='+REVISION+'\n')
            (package/'ai-mq-preflight.json').write_text(json.dumps({'binding_revision':REVISION}))
            if role=='ai':
                volumes=[dict(source=str(target/f['target'])) for f in files]
                (package/'runtime.json').write_text(json.dumps({'services':{'qs-ai':{'volumes':volumes}}}))
            for p in [package,*package.rglob('*')]:
                os.chown(p,caller,caller_gid);p.chmod(0o700 if p.is_dir() else 0o600)
        for p in original_sources:p.unlink()  # No retained-source dependency.
        lock=owned/'original-parent.lock';lock.write_bytes(b'original shared lock bytes');lock.chmod(0o666)
        before_lock=(lock.stat().st_ino,lock.read_bytes(),lock.stat().st_mode,lock.stat().st_mtime_ns)
        def attempt(role,accepted,label):
            nonlocal current_case
            current_case=role+'-'+label
            package=client/role;marker=package/'would-sync-or-stop'
            if marker.exists():marker.unlink()
            program=package/'probe'
            if role=='ai':
                program.write_text('''import importlib.util,sys
from pathlib import Path
s=importlib.util.spec_from_file_location('actual_ai_host',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
m.material_preflight(Path(sys.argv[2]));Path(sys.argv[3]).write_text('would-migrate-or-stop')
''')
                command=['/usr/bin/python3','-I',str(program),str((ai/'deploy/serverA/deploy.py').resolve()),str(package),str(marker)]
            else:
                helper=(iam if role=='iam' else qs)/'scripts/cd/material-guard.sh'
                # Execute the actual host hook before a controlled sync/stop marker.
                program.write_text('set -Eeuo pipefail\nSUDO="sudo -n"\nDEPLOY_TMP='+str(package)+'\nSERVICE='+('worker' if role=='worker' else 'apiserver')+'\nsource '+str(helper.resolve())+'\n'+blocks[role]+'\nprintf would-sync > '+str(marker)+'\n')
                command=['bash',str(program)]
            os.chown(program,caller,caller_gid);program.chmod(0o600)
            result=subprocess.run(['sudo','-n','-u',caller_name,*command],capture_output=True,timeout=15)
            if (result.returncode==0)!=accepted or marker.exists()!=accepted:
                report['private_failure_output_sha256']=hashlib.sha256(result.stdout+result.stderr).hexdigest()
                report['unexpected_exit_code']=result.returncode
                # Only fixed error labels, never source bytes or child command output.
                report['tool_metadata']=[dict(path=str(p),uid=p.lstat().st_uid,mode=oct(p.lstat().st_mode&0o777)) for p in (tool,*tool.parents) if p.exists()]
                report['tool_resolves_exactly']=tool.resolve()==tool
                report['tool_digest_matches']=hashlib.sha256(tool.read_bytes()).hexdigest()==digest
                report['failure_signals']=[label for label in (
                    'Reviewed material tool unavailable', 'Installed materials not verified',
                    'M4 material staging refused', 'Invalid frozen messaging file revision',
                    'Invalid material revision', 'Permission denied', 'unbound variable',
                    'a password is required', 'not allowed to execute')
                    if label.encode() in result.stderr]
                try:
                    m.verify_installed(role=role,revision=REVISION,host=m.ROLES[role][0])
                    report['direct_fixture_verification']='verified'
                except m.Refused as error:
                    code=str(error)
                    report['direct_fixture_verification']=code if re.fullmatch('[a-z_]{1,64}',code) else 'refused'
                except Exception as error:
                    report['direct_fixture_verification']=type(error).__name__
                raise AssertionError('host_material_boundary_failed')
            report['cases'].append(current_case)
        @contextlib.contextmanager
        def changed_file(path,kind):
            raw=path.read_bytes();info=path.stat()
            try:
                if kind=='missing':path.unlink()
                elif kind=='symlink':path.unlink();path.symlink_to(tool)
                elif kind=='mode':path.chmod(0o444)
                elif kind=='bytes':path.chmod(0o600);path.write_bytes(raw+b'wrong owner bytes');path.chmod(info.st_mode&0o777)
                elif kind=='role':
                    value=json.loads(raw);value['role']='wrong';path.chmod(0o600);path.write_bytes(m.encoded(value));path.chmod(info.st_mode&0o777)
                elif kind=='revision':
                    value=json.loads(raw);value['revision']='m4-foreign';path.chmod(0o600);path.write_bytes(m.encoded(value));path.chmod(info.st_mode&0o777)
                yield
            finally:
                if path.exists() or path.is_symlink():path.unlink()
                path.write_bytes(raw);os.chown(path,info.st_uid,info.st_gid);path.chmod(info.st_mode&0o777)
        with lock.open('r+b') as held:
            fcntl.flock(held.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            for role,target in targets.items():
                attempt(role,True,'verified-before-sync-with-parent-lock-and-no-old-sources')
                for name,path,kind in [('missing-credential',target/'rocketmq/credentials.json','missing'),
                    ('credential-symlink',target/'rocketmq/credentials.json','symlink'),
                    ('world-readable-credential',target/'rocketmq/credentials.json','mode'),
                    ('wrong-route-owner',target/'rocketmq/routes.json','bytes'),
                    ('wrong-receipt-role',target/m.RECEIPT,'role'),
                    ('wrong-receipt-revision',target/m.RECEIPT,'revision'),
                    ('missing-reviewed-plan',plans[role],'missing')]:
                    with changed_file(path,kind):attempt(role,False,name)
                parent=target.parent;old=parent.stat().st_mode&0o777
                try:
                    parent.chmod(0o770);attempt(role,False,'mutable-material-ancestor')
                finally:parent.chmod(old)
            for role in ('iam','ai'):
                for defect in ('missing','symlink','bytes','mode','foreign-owner','mutable-parent'):
                    raw=tool.read_bytes();info=tool.stat();parent_mode=tool.parent.stat().st_mode&0o777
                    try:
                        if defect=='missing':tool.unlink()
                        elif defect=='symlink':tool.unlink();tool.symlink_to(operator)
                        elif defect=='bytes':tool.chmod(0o600);tool.write_bytes(raw+b'\n# unreviewed');tool.chmod(0o555)
                        elif defect=='mode':tool.chmod(0o755)
                        elif defect=='foreign-owner':os.chown(tool,caller,caller_gid)
                        else:tool.parent.chmod(0o777)
                        attempt(role,False,'tool-'+defect)
                    finally:
                        if tool.exists() or tool.is_symlink():tool.unlink()
                        tool.write_bytes(raw);os.chown(tool,0,0);tool.chmod(0o555);tool.parent.chmod(parent_mode)
        assert before_lock==(lock.stat().st_ino,lock.read_bytes(),lock.stat().st_mode,lock.stat().st_mtime_ns)
        report['cases'].append('original-parent-lock-inode-bytes-mode-preserved')
        assert all(before_pointers[r]==(p.stat().st_ino,p.read_bytes(),p.stat().st_mtime_ns) for r,p in pointers.items())
        report['cases'].append('all-four-active-pointers-unchanged')
    except Exception as error:
        report.update(failed=1,errors=1,failure_kind=type(error).__name__,failure_case=current_case)
    finally:
        clean=True
        for p in reversed(created):
            try:
                assert p.is_dir() and not p.is_symlink() and (p/'.ci-owned').read_bytes()==identity
                shutil.rmtree(p)
            except Exception:clean=False
        if private_opt:
            try:
                subprocess.run(['/usr/bin/umount','/opt'],check=True,capture_output=True)
                info=Path('/opt').stat()
                clean=clean and (info.st_ino,info.st_uid,info.st_mode)==(original_opt.st_ino,original_opt.st_uid,original_opt.st_mode)
            except Exception:clean=False
        if owned is not None and clean:
            shutil.rmtree(owned);clean=clean and not owned.exists()
        report['owned_cleanup_complete']=clean and all(not p.exists() for p in created)
        if not report['owned_cleanup_complete']:report['failed']=report['errors']=1
        report['passed']=len(report['cases'])
        output=Path('m4-host-material-guard.json');output.write_text(json.dumps(report,indent=2)+'\n');output.chmod(0o600)
        os.chown(output,caller,caller_gid)
    print(json.dumps({k:report[k] for k in ('passed','failed','errors','skipped','owned_cleanup_complete')}))
    return int(report['failed']!=0)


if __name__=='__main__':raise SystemExit(main())
