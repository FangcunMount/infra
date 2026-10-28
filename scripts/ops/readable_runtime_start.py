#!/usr/bin/env python3
"""Start one reviewed readable-name phase using cached engine IDs only.

No pull, stop, migration, material-pointer update or data restore is available.
The window coordinator owns admission, deadline and the first-start barrier.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import socket
import stat
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'rocketmq'))
from m4_runtime_start import AI_LOCK, GLOBAL_LOCK, deployment_locks
from runtime_start import DOCKER, SOCKET, command, compose, verify_config, verify_running
from start_boundary import BoundaryError

ROOT = Path('/opt/fangcun-readable-names/releases/readable-20261028-v2')
ROLES = {
    'iam': ('serverA', 'docker', 'iam-apiserver', 1, 1024 << 20, 1000000000, 2000),
    'qs-api': ('serverA', 'servera-migrated', 'qs-apiserver', 1, 1024 << 20, 2000000000, 2000),
    'qs-collection': ('serverA', 'qs-collection', 'server', 2, 320 << 20, 1000000000, 2000),
    'ai': ('serverA', 'qs-ai', 'qs-ai', 1, 768 << 20, 750000000, 10001),
    'qs-worker': ('serverD', 'qs-worker', 'runtime', 3, 768 << 20, 1000000000, 2000),
}
EXTERNAL_ASSETS = {
    Path('/data/infra/ssl/mysql/ca-chain.pem'),
    Path('/data/infra/ssl/redis/ca-chain.pem'),
    Path('/data/infra/ssl/grpc/ca/ca-chain.crt'),
    Path('/data/infra/ssl/grpc/server/iam-apiserver.crt'),
    Path('/data/infra/ssl/grpc/server/iam-apiserver.key'),
    Path('/data/infra/ssl/grpc/server/qs-ai-fullchain.crt'),
    Path('/data/infra/ssl/grpc/server/qs-ai.key'),
    Path('/opt/fangcun-m4/releases/m4-c08-20261027-v1/qs-api/assets/events.yaml'),
}


def read(path, *, private=False, owners=None):
    p = Path(path)
    info = p.lstat()
    if (p.resolve() != p or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid not in (owners if owners is not None else {os.geteuid()})
            or not 0 < info.st_size <= 1048576
            or info.st_mode & 0o022
            or (private and stat.S_IMODE(info.st_mode) != 0o600)):
        raise BoundaryError('reviewed regular input required')
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        if os.fstat(stream.fileno()) != info:
            raise BoundaryError('input changed during open')
        raw = stream.read(1048577)
    if len(raw) != info.st_size:
        raise BoundaryError('input changed during read')
    return raw


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise BoundaryError('duplicate plan field')
        value[key] = item
    return value


def load(path, digest, *, root=ROOT):
    raw = read(path, private=True)
    if not re.fullmatch('[a-f0-9]{64}', digest) or hashlib.sha256(raw).hexdigest() != digest:
        raise BoundaryError('exact reviewed plan bytes required')
    plan = json.loads(raw, object_pairs_hook=unique)
    fields = {'schema', 'role', 'phase', 'host', 'project', 'directory', 'compose_file',
              'compose_sha256', 'environment_file', 'environment_sha256', 'services', 'images',
              'instances', 'ai_host', 'locks', 'assets', 'original_ids', 'original_images',
              'published_reference', 'image_config_id', 'source_sha', 'resources'}
    if set(plan) != fields or plan['schema'] != 'readable-frozen-runtime/v1' or plan['role'] not in ROLES:
        raise BoundaryError('exact readable phase required')
    role = plan['role']
    host, project, service, count, memory, cpu, uid = ROLES[role]
    phases = {'closed', 'acceptance', 'open', 'original'} | ({'old-drain'} if role == 'qs-api' else set())
    if (plan['phase'] not in phases or plan['host'] != host or plan['project'] != project
            or plan['services'] != [service] or plan['instances'] != {service: count}
            or type(plan['instances'][service]) is not int or plan['ai_host'] is not (host == 'serverA')
            or plan['resources'] != dict(memory=memory, nano_cpus=cpu, uid=uid)
            or set(plan['images']) != {service}
            or not re.fullmatch('sha256:[a-f0-9]{64}', plan['images'][service])):
        raise BoundaryError('fixed host, image identity or budget differs')
    if plan['phase'] == 'original':
        # Recovery pins the actual original engine object, not an inferred
        # registry/config identity on engines using the containerd image store.
        if (any(plan[key] is not None for key in ('source_sha', 'image_config_id', 'published_reference'))
                or set(plan['original_images']) != {plan['images'][service]}):
            raise BoundaryError('exact original runtime required')
    elif (not re.fullmatch('[a-f0-9]{40}', plan['source_sha'])
            or not re.fullmatch('sha256:[a-f0-9]{64}', plan['image_config_id'])
            or not re.fullmatch('[a-z0-9][a-z0-9._:/-]{0,450}@sha256:[a-f0-9]{64}', plan['published_reference'])):
        raise BoundaryError('published candidate identity required')
    directory = root / plan['phase'] / role
    if (plan['directory'] != str(directory) or Path(path).parent != directory
            or Path(plan['compose_file']).parent != directory
            or plan['environment_file'] != str(directory / 'runtime.env')):
        raise BoundaryError('fixed private phase directory required')
    expected_locks = {GLOBAL_LOCK, AI_LOCK} if host == 'serverA' else {GLOBAL_LOCK}
    if not isinstance(plan['locks'], dict) or set(plan['locks']) != expected_locks:
        raise BoundaryError('original lock set required')
    for filename, value in plan['locks'].items():
        if (set(value) != {'inode', 'device', 'uid', 'gid', 'mode'}
                or any(type(value[k]) is not int or value[k] < 0 for k in ('inode', 'device', 'uid', 'gid'))
                or value['inode'] == 0 or value['uid'] != (1002 if filename == AI_LOCK else 0)
                or value['mode'] != ('0o600' if filename == AI_LOCK else '0o666')
                or (filename == AI_LOCK and value['gid'] != 2001)):
            raise BoundaryError('original lock identity differs')
    if (not isinstance(plan['assets'], dict) or not 1 <= len(plan['assets']) <= 40
            or len(plan['original_ids']) != count or len(plan['original_images']) != count
            or len(set(plan['original_ids'])) != count
            or any(not re.fullmatch('[a-f0-9]{64}', x) for x in plan['original_ids'])
            or any(not re.fullmatch('sha256:[a-f0-9]{64}', x) for x in plan['original_images'])):
        raise BoundaryError('bounded frozen material and original runtime required')
    for key in ('compose', 'environment'):
        if hashlib.sha256(read(plan[key + '_file'], private=True)).hexdigest() != plan[key + '_sha256']:
            raise BoundaryError('frozen configuration differs')
    for filename, expected in plan['assets'].items():
        p = Path(filename)
        allowed = p in EXTERNAL_ASSETS or any(p.is_relative_to(base) for base in
                (root, Path('/var/lib/fangcun-m4-materials'), Path('/opt/qs-server/qs-apiserver/ai-mq-releases')))
        owners = {os.geteuid(), 2000, 10001} if p in EXTERNAL_ASSETS else None
        if (not p.is_absolute() or not allowed
                or hashlib.sha256(read(p, owners=owners)).hexdigest() != expected):
            raise BoundaryError('frozen material differs')
    return plan


def verify_budget(plan, raw):
    verify_config(plan, raw)
    services = json.loads(raw)['services']
    if set(services) != set(plan['services']):
        raise BoundaryError('one frozen service required')
    entry = services[plan['services'][0]]
    _, _, _, _, memory, cpu, uid = ROLES[plan['role']]
    if (int(entry.get('mem_limit', 0)) != memory or float(entry.get('cpus', 0)) * 1000000000 != cpu
            or entry.get('user') not in {str(uid), f'{uid}:{uid}', 'app' if uid == 10001 else 'www'}
            or any(re.search(r'(^|_)NSQ(D|_|$)', key) for key in entry.get('environment', {}))):
        raise BoundaryError('runtime budget or retired environment differs')


def execute(plan, path, digest):
    if platform.system() != 'Linux' or socket.gethostname() != plan['host']:
        raise BoundaryError('actual target differs')
    with deployment_locks(plan):
        if load(path, digest) != plan:
            raise BoundaryError('plan changed under lock')
        verify_budget(plan, command(plan, compose(plan, 'config', '--format', 'json')))
        service = plan['services'][0]
        command(plan, compose(plan, 'up', '--detach', '--no-deps', '--no-build', '--pull', 'never',
                              '--wait', '--wait-timeout', '90', '--scale',
                              f'{service}={plan["instances"][service]}', service), timeout=120)
        ids = command(plan, compose(plan, 'ps', '--all', '--quiet', service)).decode().split()
        if len(ids) != plan['instances'][service] or any(not re.fullmatch('[a-f0-9]{64}', x) for x in ids):
            raise BoundaryError('runtime count differs')
        rows = json.loads(command(plan, [DOCKER, '--host', SOCKET, 'inspect', *ids]))
        records = []
        for row in rows:
            if (row['Image'] != plan['images'][service] or row['State']['OOMKilled']
                    or row['HostConfig']['Memory'] != plan['resources']['memory']
                    or row['HostConfig']['NanoCpus'] != plan['resources']['nano_cpus']):
                raise BoundaryError('actual engine, OOM or resource differs')
            labels = row['Config']['Labels']
            records.append(' '.join([row['Id'], row['Config']['Image'], labels['com.docker.compose.project'],
                                    labels['com.docker.compose.service'], str(row['State']['Running']).lower(),
                                    row['State'].get('Health', {}).get('Status', 'none')]))
        verify_running(plan, ('\n'.join(records) + '\n').encode())


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--reviewed-sha256', required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--coordinated-start-already-issued', action='store_true')
    a = p.parse_args(argv)
    try:
        if a.execute != a.coordinated_start_already_issued:
            raise BoundaryError('explicit coordinator attestation required')
        plan = load(a.plan, a.reviewed_sha256)
        if a.execute:
            execute(plan, a.plan, a.reviewed_sha256)
        print(json.dumps(dict(status='readable_runtime_verified' if a.execute else 'readable_offline_verified',
                              cutover_authorized=False)))
        return 0
    except (OSError, ValueError, KeyError, TypeError, BoundaryError, subprocess.SubprocessError):
        print('{"status":"unavailable","cutover_authorized":false}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
