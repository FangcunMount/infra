#!/usr/bin/env python3
"""Start only the five frozen M4 C08 projects from verified local engine IDs.

The M3 registry-digest validator remains unchanged. This adapter cannot pull,
migrate, select another provider, stop a service, or restore business data.
The single operator records maintenance and its first-start barrier separately.
"""
import argparse
import contextlib
import fcntl
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rocketmq"))

from cutover_step import private_bytes, reviewed
from runtime_start import DOCKER, SOCKET, command, compose, verify_config, verify_running
from start_boundary import BoundaryError

ROOT = Path('/opt/fangcun-m4/releases/m4-c08-20261027-v1')
GLOBAL_LOCK = '/var/lib/fangcun-image-retention/deploy.lock'
AI_LOCK = '/opt/qs-ai/deploy.lock'
# host, project, service, replicas, actual frozen engine ID, bytes, CPUs, UID/GID
ROLES = {
    'iam': ('serverA', 'docker', 'iam-apiserver', 1,
            'b121e97fc20bf3bd8e8b550a89df8920ec348afd1e5af0bb632acc7e615ae67f', 1 << 30, 1, 2000),
    'qs-api': ('serverA', 'servera-migrated', 'qs-apiserver', 1,
               '501125199a976747ad6febafada18ffc2fa1025504d93b179daa30301bc44d55', 1 << 30, 2, 2000),
    'qs-collection': ('serverA', 'qs-collection', 'server', 2,
                      '97506c3aca75905423b6ad8bd96c234c19f2e8fd52bd25e8acfc9d6935ed576f', 320 << 20, 1, 2000),
    'ai': ('serverA', 'qs-ai', 'qs-ai', 1,
           '927c6cea9c0551be4d026bf53e27e4521a45d4bd9c4b36e848f097657db0ab14', 768 << 20, .75, 10001),
    'qs-worker': ('serverD', 'qs-worker', 'runtime', 3,
                  '85112ee36afa391ab4ad063213aa1f35a37a4b7197522358776731b5d8025971', 768 << 20, 1, 2000),
}


def load(path, digest, *, root=ROOT):
    value = reviewed(path, digest)
    fields = {'schema', 'coordinator_binding_sha256', 'role', 'host', 'project',
              'directory', 'compose_file', 'compose_sha256', 'environment_file',
              'environment_sha256', 'services', 'images', 'instances', 'ai_host', 'assets', 'locks'}
    if set(value) != fields or value['schema'] != 'm4-c08-runtime-start/v1' or value['role'] not in ROLES:
        raise BoundaryError('exact M4 C08 plan required')
    role = value['role']; host, project, service, count, image, *_ = ROLES[role]
    if (value['host'] != host or value['project'] != project
            or value['services'] != [service] or value['images'] != {service: 'sha256:' + image}
            or value['instances'] != {service: count} or type(value['instances'][service]) is not int
            or value['ai_host'] is not (host == 'serverA')
            or re.fullmatch('[a-f0-9]{64}', value['coordinator_binding_sha256']) is None):
        raise BoundaryError('frozen M4 target or budget differs')
    expected_locks = {GLOBAL_LOCK, AI_LOCK} if host == 'serverA' else {GLOBAL_LOCK}
    if not isinstance(value['locks'], dict) or set(value['locks']) != expected_locks:
        raise BoundaryError('exact original M4 lock set required')
    for filename, identity in value['locks'].items():
        if (not isinstance(identity, dict) or set(identity) != {'inode', 'device', 'uid', 'gid', 'mode'}
                or any(type(identity[k]) is not int or identity[k] < 0 for k in ('inode', 'device', 'uid', 'gid'))
                or identity['inode'] == 0
                or (filename == GLOBAL_LOCK and (identity['uid'] != 0 or identity['mode'] != '0o666'))
                or (filename == AI_LOCK and identity != {**identity, 'uid': 1002, 'gid': 2001, 'mode': '0o600'})):
            raise BoundaryError('original M4 lock metadata differs')
    directory = root / role
    for name, suffix in [('directory', ''), ('compose_file', 'compose.json'), ('environment_file', 'runtime.env')]:
        expected = directory / suffix if suffix else directory
        if value[name] != str(expected):
            raise BoundaryError('fixed private M4 release required')
    for key in ('compose', 'environment'):
        if hashlib.sha256(private_bytes(value[key + '_file'], 1 << 20)).hexdigest() != value[key + '_sha256']:
            raise BoundaryError('frozen M4 input differs')
    if not isinstance(value['assets'], dict) or not 1 <= len(value['assets']) <= 32:
        raise BoundaryError('bounded frozen material closure required')
    for filename, expected in value['assets'].items():
        p = Path(filename)
        allowed = (root, Path('/var/lib/fangcun-m4-materials'),
                   Path('/opt/qs-server/qs-apiserver/ai-mq-releases/1f38f583d43c9faf4601a5df9f3f82b764e6547d'))
        if (not p.is_absolute() or p.resolve() != p or not any(p.is_relative_to(base) for base in allowed)
                or not p.is_file() or p.stat().st_size > 1 << 20 or p.stat().st_mode & 0o022
                or hashlib.sha256(p.read_bytes()).hexdigest() != expected):
            raise BoundaryError('frozen M4 material differs')
    return value


@contextlib.contextmanager
def deployment_locks(plan):
    """Respect the original deploy-owned AI lock without changing its owner/mode."""
    def identity(info):
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise BoundaryError('original M4 lock is not a single regular file')
        return dict(inode=info.st_ino, device=info.st_dev, uid=info.st_uid,
                    gid=info.st_gid, mode=oct(stat.S_IMODE(info.st_mode)))
    paths = [GLOBAL_LOCK, AI_LOCK] if plan['ai_host'] else [GLOBAL_LOCK]
    with contextlib.ExitStack() as stack:
        for path in paths:
            if identity(Path(path).lstat()) != plan['locks'][path]:
                raise BoundaryError('original M4 lock changed before open')
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
            stack.callback(os.close, fd)
            if identity(os.fstat(fd)) != plan['locks'][path]:
                raise BoundaryError('original M4 lock changed during open')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
        if any(identity(Path(path).lstat()) != plan['locks'][path] for path in paths):
            raise BoundaryError('original M4 lock changed during execution')


def verify_budget(plan, raw):
    verify_config(plan, raw)
    service = json.loads(raw)['services'][plan['services'][0]]
    *_, memory, cpus, uid = ROLES[plan['role']]
    if (int(service.get('mem_limit', 0)) != memory or float(service.get('cpus', 0)) != cpus
            or service.get('user') not in {str(uid), f'{uid}:{uid}', 'app' if plan['role'] == 'ai' else 'www'}
            or any(re.search(r'(^|_)NSQ(D|_|$)', key) for key in service.get('environment', {}))):
        raise BoundaryError('M4 runtime resource or retired environment differs')


def execute(plan):
    if platform.system() != 'Linux' or socket.gethostname() != plan['host']:
        raise BoundaryError('actual M4 target differs')
    with deployment_locks(plan):
        # Material/configuration drift after lock acquisition fails before Docker up.
        for key in ('compose', 'environment'):
            if hashlib.sha256(private_bytes(plan[key + '_file'], 1 << 20)).hexdigest() != plan[key + '_sha256']:
                raise BoundaryError('M4 input changed before start')
        for filename, expected in plan['assets'].items():
            if hashlib.sha256(Path(filename).read_bytes()).hexdigest() != expected:
                raise BoundaryError('M4 material changed before start')
        verify_budget(plan, command(plan, compose(plan, 'config', '--format', 'json')))
        # Explicit scale is already frozen and validated by verify_config.
        service = plan['services'][0]
        command(plan, compose(plan, 'up', '--detach', '--no-deps', '--no-build', '--pull', 'never',
                              '--wait', '--wait-timeout', '60', '--scale',
                              f'{service}={plan["instances"][service]}', service), timeout=150)
        ids = command(plan, compose(plan, 'ps', '--all', '--quiet', service)).decode().split()
        if len(ids) != plan['instances'][service] or any(re.fullmatch('[a-f0-9]{64}', v) is None for v in ids):
            raise BoundaryError('M4 runtime count differs')
        template = ('{{.Id}} {{.Config.Image}} {{index .Config.Labels "com.docker.compose.project"}} '
                    '{{index .Config.Labels "com.docker.compose.service"}} {{.State.Running}} '
                    '{{if index .State "Health"}}{{index (index .State "Health") "Status"}}{{else}}none{{end}}')
        verify_running(plan, command(plan, [DOCKER, '--host', SOCKET, 'inspect', '--type', 'container',
                                           '--format', template, *ids]))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--reviewed-sha256', required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--coordinated-start-already-issued', action='store_true')
    a = p.parse_args(argv)
    try:
        if a.execute != a.coordinated_start_already_issued:
            raise BoundaryError('explicit M4 coordinator attestation required')
        plan = load(a.plan, a.reviewed_sha256)
        if a.execute:
            execute(plan)
        print(json.dumps(dict(status='m4_runtime_verified' if a.execute else 'm4_offline_plan_verified',
                              cutover_authorized=False)))
        return 0
    except (OSError, ValueError, TypeError, BoundaryError, subprocess.SubprocessError):
        print('{"status":"unavailable","cutover_authorized":false}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
