"""Root helper for owned CI readable route switching, never a production tool."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from final_image_candidate import ci_guard
from m4_owned_materials import BASE, FILES, ROLES, owned_fixture, owned_marker, validate_plan
from m4_image_rebuild import load
from routes import validate
from readable_transition import validate_transition

COMPONENTS = ('iam','ai','api','collection','collection2','worker1','worker2','worker3')
ROOT = Path(__file__).resolve().parents[2]


def require(ok, reason):
    if not ok:raise RuntimeError(reason)


def revision(project, phase):
    require(isinstance(project,str) and re.fullmatch('rocketmq-m2-image-[0-9a-f]{12}',project)
            and phase in ('compat','active'),'fixed_owned_readable_material_phase_required')
    return 'readable-' + phase + '-' + project.rsplit('-',1)[1]


def documents():
    old=json.loads((ROOT/'components/rocketmq/serverd-routes-m3-v2.json').read_bytes())
    new=json.loads((ROOT/'components/rocketmq/serverd-routes-readable-v3.json').read_bytes())
    validate_transition(old,new)
    return {'compat':old,'active':new}


def stopped_instances(value, project):
    require(isinstance(value,list) and len(value)==8,'eight_owned_stopped_instances_required')
    names={}
    for row in value:
        name=row.get('Name','').removeprefix('/')
        require(name in {project+'-'+k for k in COMPONENTS} and name not in names,
                'exact_owned_instance_set_required')
        require(row.get('Config',{}).get('Labels',{}).get('com.fangcunmount.m3.fixture')==project
                and row.get('State',{}).get('Status')=='exited'
                and row['State'].get('Running') is False and type(row['State'].get('ExitCode')) is int
                and row['State']['ExitCode']==0 and row['State'].get('OOMKilled') is False,
                'clean_stopped_owned_runtime_required')
        names[name]=True
    return names


def rebase_mounts(mounts, original, target):
    require(re.fullmatch('m4-owned-[0-9a-f]{12}',original)
            and target in ('readable-compat-'+original[-12:],'readable-active-'+original[-12:]),
            'same_owned_revision_family_required')
    result=copy.deepcopy(mounts)
    for role, values in result.items():
        if role in ('api','collection'):continue
        require(role in ROLES,'fixed_material_role_required')
        before=str(BASE/ROLES[role][0]/'versions'/original)
        after=str(BASE/ROLES[role][0]/'versions'/target)
        for value in values:
            source=value['source']
            require(value.get('read_only') is True and value.get('bind',{}).get('create_host_path') is False
                    and (source==before or source.startswith(before+'/')),'original_readonly_version_mount_required')
            value['source']=after+source[len(before):]
    return result


def private_write(path, raw, *, mode=0o600):
    require(not path.exists() and not path.is_symlink(),'new_owned_material_file_required')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    path.chmod(mode)


def stage(fixture, plan):
    validate_plan(plan,fixture)
    marker=owned_marker(fixture)
    require(marker['project']==plan['project'],'same_original_owned_material_project_required')
    original=plan['revision'];docs=documents();result={}
    before={}
    for row in plan['files']:
        path=BASE/ROLES[row['role']][0]/'versions'/original/row['relative']
        require(path.is_file() and not path.is_symlink() and path.stat().st_uid==0
                and hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'],
                'original_staged_material_changed')
        before[str(path)]=row['sha256']
    for phase, document in docs.items():
        validate(document);next_revision=revision(plan['project'],phase)
        for role,(stem,gid) in ROLES.items():
            directory=BASE/stem/'versions'/next_revision
            require(not directory.exists() and not directory.is_symlink(),'existing_readable_version_refused')
            directory.mkdir(mode=0o750);os.chown(directory,0,gid)
            (directory/'rocketmq').mkdir(mode=0o750);os.chown(directory/'rocketmq',0,gid)
            for relative in FILES[role]:
                source=BASE/stem/'versions'/original/relative
                raw=(json.dumps(document,indent=2)+'\n').encode() if relative=='rocketmq/routes.json' else source.read_bytes()
                path=directory/relative;private_write(path,raw,mode=0o440);os.chown(path,0,gid)
        result[phase]=dict(revision=next_revision,files=21,manifest_version=document['version'],
            routes_sha256=hashlib.sha256((json.dumps(document,indent=2)+'\n').encode()).hexdigest())
    require(all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest for path,digest in before.items()),
            'original_version_not_preserved')
    return dict(versions=result,original_inputs_unchanged=True,production=False)


def activate(fixture, phase, source, image):
    marker=owned_marker(fixture);project=marker['project'];next_revision=revision(project,phase)
    require(isinstance(source,str) and isinstance(image,str) and re.fullmatch('m3-final-qs-api:[0-9a-f]{12}',image),
            'fixed_owned_api_image_required')
    source=Path(source).resolve()
    require(source==Path(os.environ['GITHUB_WORKSPACE']).resolve()/'.five-sources/qs',
            'actual_reviewed_qs_source_required')
    rows=subprocess.run(['docker','inspect','--type','container',*(project+'-'+k for k in COMPONENTS)],
        capture_output=True,text=True,check=True,timeout=20)
    stopped_instances(json.loads(rows.stdout),project)
    # No application is running while this root-owned selector changes. All
    # immutable old/new material files remain, including the original key bytes.
    for role,(stem,_) in ROLES.items():
        directory=BASE/stem/'versions'/next_revision
        require(directory.is_dir() and not directory.is_symlink() and directory.stat().st_uid==0,
                'pre_staged_owned_readable_version_required')
        for relative in FILES[role]:
            path=directory/relative
            require(path.is_file() and not path.is_symlink() and path.stat().st_uid==0
                    and path.stat().st_mode&0o777==0o440,'immutable_readable_material_required')
    plan=json.loads((fixture/'m4-plan.json').read_bytes())
    binding=copy.deepcopy(plan['api_binding']);binding['binding_revision']=next_revision
    current=BASE/ROLES['api'][0]/'current.json'
    require(current.is_file() and not current.is_symlink() and current.stat().st_uid==0,
            'original_owned_api_selector_required')
    pending=current.with_name('readable-selector-'+phase+'.json')
    private_write(pending,(json.dumps(binding)+'\n').encode(),mode=0o440);os.chown(pending,0,2000)
    os.replace(pending,current)
    tool=load(source/'scripts/cd/ai-messaging-release.py','readable_actual_api_freeze')
    base=fixture/('api-base-'+phase+'.json')
    if not base.exists():private_write(base,(fixture/'api/runtime.json').read_bytes())
    require(base.is_file() and not base.is_symlink() and base.stat().st_uid==0
            and base.stat().st_mode&0o777==0o600,'frozen_owned_api_base_required')
    releases=fixture/('actual-api-readable-'+phase);releases.mkdir(mode=0o755,exist_ok=True)
    first=tool.prepare(image,base,2000,2000,release_root=releases)
    second=tool.prepare(image,base,2000,2000,release_root=releases)
    require(first==second and first['binding_revision']==next_revision,'readable_api_freeze_not_repeatable')
    release=releases/first['source_sha'];runtime=(release/'apiserver.json').read_bytes()
    (fixture/'api/runtime.json').write_bytes(runtime)
    composition=json.loads((release/'compose.json').read_bytes())
    return dict(revision=next_revision,manifest_version=documents()[phase]['version'],
        current_sha256=hashlib.sha256(current.read_bytes()).hexdigest(),
        result=first,volumes=composition['services']['qs-apiserver']['volumes'],
        native_metadata=json.loads((release/'metadata.json').read_bytes()),
        rendered_sha256=hashlib.sha256(runtime).hexdigest(),production=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('stage','activate'))
    parser.add_argument('--fixture',required=True);parser.add_argument('--phase',choices=('compat','active'))
    parser.add_argument('--source');parser.add_argument('--image')
    args=parser.parse_args();ci_guard(os.environ)
    require(os.geteuid()==0,'owned_ci_root_required');fixture=owned_fixture(args.fixture)
    if args.action=='stage':result=stage(fixture,json.loads((fixture/'m4-plan.json').read_bytes()))
    else:result=activate(fixture,args.phase,args.source,args.image)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps(dict(schema='readable-owned-material-failure/v1',error_type=type(error).__name__)))
        raise SystemExit(1) from None
