#!/usr/bin/env python3
"""Download immutable GitHub stable release assets and install outside SDK sources.

No publication, tag mutation, production connection or editable/replace install.
The following Docker acceptance consumes the verified Go binary and interpreter.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import tomllib

REPO = 'FangcunMount/reliable-messaging'
MODULE = 'github.com/' + REPO
GO_TAG = 'v0.5.0'
PY_TAG = 'python/v0.4.0'
VERSION = '0.4.0'


def run(arguments, *, cwd=None):
    result = subprocess.run(arguments,cwd=cwd,capture_output=True,text=True,timeout=300,
                            env=dict(os.environ,GOWORK="off",GOTOOLCHAIN="local",PYTHONPATH=""))
    if result.returncode:
        raise RuntimeError('published installation command failed: '+Path(arguments[0]).name)
    return result.stdout


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tag_sha(tag):
    obj=json.loads(run(['gh','api',f'repos/{REPO}/git/ref/tags/{tag}']))['object']
    for _ in range(4):
        if obj['type']=='commit':
            return obj['sha']
        if obj['type']!='tag':
            break
        obj=json.loads(run(['gh','api',f'repos/{REPO}/git/tags/'+obj['sha']]))['object']
    raise RuntimeError('tag did not resolve to an exact commit')


def verify_package(python, candidate, files):
    code="import json,reliable_messaging as p,importlib.metadata as m; print(json.dumps({'path':p.__file__,'version':m.version('fangcun-reliable-messaging'),'client':m.version('rocketmq-python-client')}))"
    metadata=json.loads(run([str(python),'-I','-c',code]))
    package=Path(metadata['path']).parent.resolve()
    if package.is_relative_to(candidate) or metadata['version']!=VERSION or metadata['client']!='5.1.2':
        raise RuntimeError('installed package provenance/version differs')
    prefix='python/src/reliable_messaging/'
    count=0
    for name, expected in files.items():
        if name.startswith(prefix):
            if digest(package/name.removeprefix(prefix))!=expected:
                raise RuntimeError('installed package bytes differ from fixed candidate')
            count+=1
    if count < 10:
        raise RuntimeError('installed source proof unexpectedly empty')
    return {**metadata,'verified_files':count}


def source_manifest(candidate):
    tracked=run(['git','ls-files','-z'],cwd=candidate).split('\0')
    names=[name for name in tracked if name and (
        Path(name).suffix in ('.go','.sql','.json','.patch')
        or name in ('go.mod','go.sum','python/pyproject.toml','python/uv.lock')
        or name.startswith('python/src/reliable_messaging/')
    )]
    return {name:digest(candidate/name) for name in sorted(names)}


def install_python_assets(candidate, downloads, output, source_files):
    """Install fixed wheel/sdist and lock outside source; verify bytes and dependencies."""
    # Derive constraints from the fixed asset dependency lock without installing
    # the project directory. Runtime dependencies must not silently float.
    locked_project=output/'locked-project'; locked_project.mkdir(mode=0o700)
    shutil.copyfile(candidate/'python/pyproject.toml',locked_project/'pyproject.toml')
    shutil.copyfile(downloads/'uv.lock',locked_project/'uv.lock')
    constraints=output/'runtime-constraints.txt'
    run(['uv','export','--project',str(locked_project),'--frozen','--all-extras',
         '--all-groups','--no-emit-project','--no-hashes','--format','requirements.txt',
         '--output-file',str(constraints)])
    locked=tomllib.loads((downloads/'uv.lock').read_text())
    allowed={}
    for package in locked['package']:
        allowed.setdefault(package['name'].lower().replace('_','-'),set()).add(package['version'])
    packages={}
    for kind,suffix in (('wheel','*.whl'),('sdist','*.tar.gz')):
        matches=list(downloads.glob(suffix))
        if len(matches)!=1:
            raise RuntimeError('expected one fixed '+kind)
        environment=output/kind
        run(['uv','venv',str(environment)])
        python=environment/'bin/python'
        run(['uv','pip','install','--python',str(python),'--constraint',str(constraints),
             str(matches[0])+'[nsq,rocketmq]','asyncmy'])
        packages[kind]=verify_package(python,candidate,source_files)
        versions=json.loads(run([str(python),'-I','-c',
            "import json,importlib.metadata as m; print(json.dumps({d.metadata['Name'].lower().replace('_','-'):d.version for d in m.distributions()}))"]))
        if any(version not in allowed.get(name,set()) for name,version in versions.items()):
            raise RuntimeError('installed dependency differs from downloaded fixed lock')
        packages[kind]['dependency_versions']=versions
    return packages


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    candidate=args.candidate.resolve()
    output=args.output.resolve(); output.mkdir(mode=0o700,parents=True,exist_ok=False)
    sha=run(['git','rev-parse','HEAD'],cwd=candidate).strip()
    if tag_sha(GO_TAG)!=sha or tag_sha(PY_TAG)!=sha:
        raise RuntimeError('both published tags must equal the checked-out candidate SHA')
    metadata={}
    for tag in (GO_TAG,PY_TAG):
        release=json.loads(run(['gh','release','view',tag,'-R',REPO,'--json','tagName,isPrerelease,isDraft,assets']))
        if release['isPrerelease'] or release.get('isDraft', False) or release['tagName']!=tag:
            raise RuntimeError('fixed stable release metadata absent')
        metadata[tag]=release
    downloads=output/'assets'; downloads.mkdir(mode=0o700)
    run(['gh','release','download',PY_TAG,'-R',REPO,'--dir',str(downloads),'--pattern','*'])
    receipt=json.loads((downloads/'transaction-release-receipt.json').read_text())
    if receipt['source_sha']!=sha or receipt['go_tag']!=GO_TAG or receipt['python_tag']!=PY_TAG:
        raise RuntimeError('downloaded release receipt differs from tag/source')
    for name, expected in receipt['assets'].items():
        if Path(name).name!=name or digest(downloads/name)!=expected:
            raise RuntimeError('downloaded asset checksum mismatch')
    checksums={}
    for line in (downloads/'SHA256SUMS').read_text().splitlines():
        expected,name=line.split(None,1); name=name.lstrip('* ')
        if Path(name).name!=name or digest(downloads/name)!=expected:
            raise RuntimeError('downloaded SHA256SUMS mismatch')
        checksums[name]=expected
    if 'transaction-release-receipt.json' not in checksums or not set(receipt['assets'])<=checksums.keys():
        raise RuntimeError('release checksums omit required fixed assets')
    source_files=receipt['source_files_sha256']
    if source_files != source_manifest(candidate):
        raise RuntimeError('release source manifest is incomplete or differs from candidate')
    if digest(downloads/'uv.lock') != source_files.get('python/uv.lock'):
        raise RuntimeError('downloaded dependency lock differs from fixed SDK candidate')
    for name, expected in source_files.items():
        if name.startswith('/') or '..' in Path(name).parts or digest(candidate/name)!=expected:
            raise RuntimeError('candidate source bytes differ from published receipt')
    module=json.loads(run(['go','mod','download','-json',MODULE+'@'+GO_TAG],cwd=output))
    if module.get('Error') or module.get('Version')!=GO_TAG or not module.get('Sum') or not module.get('GoModSum'):
        raise RuntimeError('published Go module checksum resolution failed')
    if module.get('Origin',{}).get('Hash',sha)!=sha:
        raise RuntimeError('published Go module origin differs from fixed tag')
    module_dir=Path(module['Dir'])
    checked=0
    for name, expected in source_files.items():
        if digest(module_dir/name)!=expected:
            raise RuntimeError('published Go module source differs from candidate')
        checked+=1
    if checked < 50 or 'replace ' in (module_dir/'go.mod').read_text():
        raise RuntimeError('published Go source proof empty or uses replace')
    binary=output/'sdk-go-probe'
    run(['go','build','-mod=readonly','-o',str(binary),'./transport/rocketmq/internal/sdkprobe'],cwd=module_dir)
    packages=install_python_assets(candidate,downloads,output,source_files)
    report={'source_sha':sha,'go_tag':GO_TAG,'python_tag':PY_TAG,'asset_sha256':checksums,
            'go_module':{k:module[k] for k in ('Path','Version','Sum','GoModSum')},
            'go_verified_files':checked,'go_binary':str(binary),'go_binary_sha256':digest(binary),
            'python_interpreter':str(output/'wheel/bin/python'),'packages':packages,
            'local_replace':False,'editable_install':False,'isolated_python':True}
    (output/'published-installation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'source_sha':sha,'go_verified_files':checked,'installed':['wheel','sdist']}))


if __name__=='__main__':
    main()
