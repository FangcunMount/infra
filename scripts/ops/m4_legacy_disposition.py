"""Named M4 legacy assets only. Preview is the default; no prune or DROP."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

OP = 'm4-legacy-disposition-20261027'
OLD_ROOT = '/var/lib/fangcun-m3/windows/20261025081841-2/'
ARCHIVES = {
    'serverA': {'three-full-databases.sql', 'three-full-databases.sql.gz', 'three-full-restoration.sql', 'same-window-protection.tar.gz'},
    'serverC': {'qs-full.archive.gz', 'same-window-protection.tar.gz'},
    'serverD': {'nsqd-cold-data.tar.gz', 'same-window-protection.tar.gz'},
}
NSQ_IMAGE = 'sha256:1a369c146af71bc95c25d54b375a2b98452478c1eaf4e85f8fcb01da20f2c78a'
NSQ_NAMES = {'nsqd', 'nsqlookupd', 'nsqadmin'}
SQL_QUEUES = {('iam', 'domain_event_outbox'): ('status', 'published'), ('iam', 'rm_outbox'): ('state', 'published'), ('qs', 'rm_outbox'): ('state', 'published'), ('qs', 'ai_messaging_outbox'): ('stage', 'confirmed'), ('ai', 'messaging_outbox'): ('stage', 'confirmed')}
D = ['/usr/bin/docker', '--host', 'unix:///var/run/docker.sock']

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()

def regular(path):
    p = Path(path)
    if p.resolve() != p or not stat.S_ISREG(p.lstat().st_mode):
        raise ValueError('Exact regular file required')
    return p

def validate_plan(plan):
    if plan.get('operation') != OP or plan.get('authorization') != 'user-20261027-dispose-now':
        raise ValueError('Named authorization required')
    if plan.get('kind') == 'archives':
        host = plan['host']
        for row in plan['files']:
            p = Path(row['path'])
            if host == 'mac-mini-old':
                expected = Path.home() / 'backups/infra/rocketmq/m3-production-window-20261025081841-2'
                allowed = p.parent == expected and p.name in {'serverA-protection.tar.gz', 'serverC-protection.tar.gz', 'serverD-protection.tar.gz'}
            else:
                allowed = host in ARCHIVES and p.parent == Path(OLD_ROOT) and p.name in ARCHIVES[host]
            if not allowed:
                raise ValueError('Archive path outside named scope')
    elif plan.get('kind') == 'nsq':
        if plan['host'] != 'serverD' or {x['name'] for x in plan['containers']} != NSQ_NAMES or any(x['image'] != NSQ_IMAGE or x['running'] or x['restart'] != 'no' for x in plan['containers']):
            raise ValueError('Retired NSQ identity required')
        if plan['data_tree_sha256'] != '6f72f5614855547ef4bf8d7661846a20c23692065dbe75e66bdc493d5a2171d9':
            raise ValueError('Original NSQ manifest required')
        for row in plan['configs']:
            if row['path'] not in {'/data/infra/nsq/' + name + '.conf' for name in NSQ_NAMES}:
                raise ValueError('Config outside named scope')
        if len(plan['configs']) != 3 or len(plan['containers']) != 3:
            raise ValueError('Complete retired scope required')
    else:
        raise ValueError('Unsupported disposition kind')
    paths = [r['path'] for r in plan.get('files', plan.get('configs', []))]
    if len(set(paths)) != len(paths):
        raise ValueError('Duplicate path')
    return plan

def check_files(rows):
    for row in rows:
        p = regular(row['path']); s = p.stat()
        if s.st_size != row['bytes'] or digest(p) != row['sha256'] or ('inode' in row and s.st_ino != row['inode']):
            raise ValueError('File changed; preserve evidence')

def runtime(rows):
    return {x['Id']: (x['Name'], x['Image'], x['State']['Running'], x['State']['StartedAt'], x['RestartCount']) for x in rows}

def docker(*args):
    return subprocess.check_output(D + list(args), timeout=40)

def all_containers():
    ids = docker('ps', '-aq').decode().split()
    return json.loads(docker('inspect', *ids)) if ids else []

@contextlib.contextmanager
def deployment_lock():
    p = regular('/var/lib/fangcun-image-retention/deploy.lock'); before = p.stat()
    with p.open('r+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            if not os.path.samestat(before, p.stat()):
                raise ValueError('Deployment lock replaced')
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)

def apply(plan):
    validate_plan(plan)
    if plan['kind'] == 'archives':
        check_files(plan['files'])
        deleted = []
        for row in plan['files']:
            p = regular(row['path']); p.unlink(); deleted.append(dict(path=row['path'], bytes=row['bytes'], sha256=row['sha256']))
        return dict(kind='archives', host=plan['host'], deleted=deleted, database_or_runtime_changed=False)
    with deployment_lock():
        rows = all_containers(); before = runtime(rows); selected = {x['id']: x for x in plan['containers']}
        expected = [x for x in rows if x['Id'] in selected]
        if len(expected) != 3 or {x['Id'] for x in rows if x['Image'] == NSQ_IMAGE} != set(selected):
            raise ValueError('Image references changed')
        for x in expected:
            p = selected[x['Id']]
            if x['Name'].lstrip('/') != p['name'] or x['State']['Running'] or x['HostConfig']['RestartPolicy']['Name'] != 'no' or x['Mounts'] != p['mounts']:
                raise ValueError('Retired container changed')
        check_files(plan['configs'])
        base = Path('/data/infra/nsq/data'); entries = []
        for p in sorted(base.rglob('*')):
            if p.is_symlink():
                raise ValueError('Symlink in retired data')
            if p.is_file():
                entries.append(dict(path=str(p.relative_to(base)), bytes=p.stat().st_size, sha256=digest(p)))
        if len(entries) != 1519 or hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest() != plan['data_tree_sha256']:
            raise ValueError('Retired data changed')
        docker('rm', *sorted(selected))
        if any(x['Image'] == NSQ_IMAGE for x in all_containers()):
            raise ValueError('Image still referenced')
        docker('image', 'rm', '--no-prune', NSQ_IMAGE)
        for row in entries:
            regular(str(base / row['path'])).unlink()
        for p in sorted(base.rglob('*'), key=lambda p: len(p.parts), reverse=True):
            if p.is_dir():p.rmdir()
        base.rmdir()
        for row in plan['configs']:regular(row['path']).unlink()
        # Keep the empty source root and audit metadata; no recursive deletion outside the frozen data.
        after = runtime(all_containers()); protected = {k:v for k,v in before.items() if k not in selected}
        if after != protected:
            raise ValueError('Other runtime changed during disposition')
        return dict(kind='nsq', removed_containers=3, removed_image=NSQ_IMAGE, data_files=len(entries), data_bytes=sum(x['bytes'] for x in entries), removed_configs=3, named_volumes_deleted=0, other_runtime_unchanged=True)

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--plan', required=True); parser.add_argument('--sha256', required=True); parser.add_argument('--execute', action='store_true'); args = parser.parse_args()
    p = regular(args.plan)
    if digest(p) != args.sha256:raise ValueError('Plan digest changed')
    plan = validate_plan(json.loads(p.read_bytes()))
    print(json.dumps(apply(plan) if args.execute else dict(preview=True, kind=plan['kind'], operation=OP)))

if __name__ == '__main__':main()
