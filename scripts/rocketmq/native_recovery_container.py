#!/usr/bin/env python3
"""Launch one reviewed native-recovery container under the Linux coordinator."""
import argparse
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
import time

from cutover_step import absolute, private_bytes, reviewed
from start_boundary import BoundaryError, _digest, _json, _publish, _read, _step


DOCKER = ('/usr/bin/docker', '--host', 'unix:///var/run/docker.sock')
NATIVE = '/opt/native-recovery/native-recovery'
COMMANDS = {'recover', 'resolve-notice', 'verify-resolution'}
INPUTS = ('config', 'manifest', 'export', 'request', 'approval')
PRIVATE_FILE_LIMIT = 65536


def private_directory(path):
    if path.resolve(strict=True) != path or ',' in str(path):
        raise BoundaryError('noncanonical private path')
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.geteuid():
        raise BoundaryError('private executor-owned directory required')
    return path


def input_digest(path, expected):
    if path.resolve(strict=True) != path:
        raise BoundaryError('noncanonical reviewed input')
    if hashlib.sha256(private_bytes(path, PRIVATE_FILE_LIMIT)).hexdigest() != _digest(expected):
        raise BoundaryError('reviewed native input differs')


def arguments(plan, env):
    fields = {'schema', 'command', 'directory', 'host', 'image_id', 'source_sha',
              'network_id', 'network_name', 'binding_sha256', 'step', 'inputs', 'java'}
    if set(plan) != fields or plan['schema'] != 'm3-native-recovery-container/v1':
        raise BoundaryError('exact reviewed container plan required')
    action = plan['command']
    if not isinstance(action, str) or action not in COMMANDS:
        raise BoundaryError('exact native command required')
    if (plan['host'] != socket.gethostname() or
            not isinstance(plan['source_sha'], str) or not re.fullmatch('[0-9a-f]{40}', plan['source_sha']) or
            not isinstance(plan['network_name'], str) or
            not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}', plan['network_name']) or
            plan['network_name'] in {'bridge', 'host', 'none'} or
            not isinstance(plan['image_id'], str) or not plan['image_id'].startswith('sha256:')):
        raise BoundaryError('reviewed host, source, image and dedicated network required')
    _digest(plan['image_id'][7:])
    _digest(plan['network_id'])
    directory = private_directory(absolute(plan['directory']))
    binding = _digest(plan['binding_sha256'])
    step = _step(plan['step'])
    step_sha = _digest(env.get('M3_COORDINATOR_STEP_PLAN_SHA256'))
    if (env.get('M3_COORDINATOR_DIRECTORY'), env.get('M3_COORDINATOR_BINDING_SHA256'),
            env.get('M3_COORDINATOR_STEP')) != (str(directory), binding, step):
        raise BoundaryError('exact current coordinator context required')
    material = private_directory(directory.parent / 'inputs')
    java = private_directory(material / 'java')
    tls = private_directory(java / 'tls')
    if ({p.name for p in material.iterdir()} != {name + '.json' for name in INPUTS} | {'java'} or
            {p.name for p in java.iterdir()} != {'tls', 'tools.yml'} or
            {p.name for p in tls.iterdir()} != {'server.crt'}):
        raise BoundaryError('unexpected mounted materials')
    if not isinstance(plan['java'], dict) or set(plan['java']) != {'tools', 'ca'}:
        raise BoundaryError('reviewed Java inputs required')
    input_digest(java / 'tools.yml', plan['java']['tools'])
    input_digest(tls / 'server.crt', plan['java']['ca'])
    expected = set(INPUTS) if action == 'recover' else set(INPUTS) | {'receipt'}
    if not isinstance(plan['inputs'], dict) or set(plan['inputs']) != expected:
        raise BoundaryError('exact reviewed native inputs required')
    cli = [action, '--directory', str(directory), '--binding-sha', binding,
           '--step', step, '--step-plan-sha', step_sha]
    for name in sorted(expected):
        item = plan['inputs'][name]
        if name == 'receipt':
            if not isinstance(item, dict) or set(item) != {'attempt', 'sha256'} or (
                    not isinstance(item['attempt'], str) or not re.fullmatch(r'native-attempt-[0-9]+', item['attempt'])):
                raise BoundaryError('receipt must belong to the exact operation')
            path = private_directory(directory / item['attempt']) / 'receipt.json'
            digest = item['sha256']
        else:
            path = material / (name + '.json')
            digest = item
        input_digest(path, digest)
        cli += ['--' + name, str(path), '--' + name + '-sha', digest]
    return directory, material, java, step_sha, cli


def create_args(plan, directory, material, java, name, cli, protected):
    return ['create', '--name', name, '--pull', 'never', '--platform', 'linux/amd64',
            '--hostname', plan['host'], '--network', plan['network_id'],
            '--read-only', '--user', '3000:3000', '--restart', 'no',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--pids-limit', '64', '--memory', '384m', '--cpus', '1',
            '--mount', f'type=bind,src={directory},dst={directory}',
            '--mount', f'type=bind,src={material},dst={material},readonly',
            '--mount', f'type=bind,src={java},dst=/run/native-recovery,readonly',
            *[arg for path in protected for arg in ('--mount', f'type=bind,src={path},dst={path},readonly')],
            '--entrypoint', '/usr/bin/timeout', plan['image_id'],
            '--signal=TERM', '--kill-after=12s', '195s', NATIVE, *cli]


def docker(args, *, timeout=5):
    result = subprocess.run([*DOCKER, *args], check=True, capture_output=True, text=True, timeout=timeout,
                            env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'HOME': '/nonexistent'})
    return result.stdout.strip()


def require_issued(fd, plan, directory, step_sha):
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        pass
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        raise BoundaryError('coordinator lock is not held')
    step_bytes = _read(fd, 'reviewed-step-' + step_sha + '.json')
    step = _json(step_bytes)
    state = _json(_read(fd, 'state.json'))
    binding = plan['binding_sha256']
    if (hashlib.sha256(step_bytes).hexdigest() != step_sha or
            (step['directory'], step['binding_sha256'], step['host'], step['step']) != (
                str(directory), binding, plan['host'], plan['step']) or
            step['timeout_seconds'] < 240 or
            (step['kind'], state['phase']) not in {
                ('runtime-start', 'runtime_start_issued'), ('forward-repair', 'forward_repair_issued')} or
            (state['binding_sha256'], state['step']) != (binding, plan['step'])):
        raise BoundaryError('live issued coordinator step differs')
    names = ['binding.json', 'state.json', 'first-runtime-start.json', 'reviewed-step-' + step_sha + '.json']
    if step['kind'] == 'forward-repair':
        names.append('repair-approval-' + step_sha + '.json')
    for name in names:
        _read(fd, name)
    return tuple(directory / name for name in names)


def inspect_exit(cid, name, image):
    container, = json.loads(docker(['container', 'inspect', cid]))
    state = container['State']
    if (container['Id'], container['Name'], container['Image'], state['Status'],
            state['Running'], container['RestartCount']) != (cid, '/' + name, image, 'exited', False, 0):
        raise BoundaryError('exact recovery container terminal state unknown')
    return {'container_id': cid, 'exit_code': state['ExitCode'], 'oom_killed': state['OOMKilled']}


def run_container(fd, plan, directory, material, java, step_sha, cli, protected, deadline):
    name = 'native-container-' + step_sha
    for previous in os.listdir(fd):
        if re.fullmatch(r'native-container-[0-9a-f]{64}-issued\.json', previous):
            previous_name = previous.removesuffix('-issued.json')
            if previous_name == name:
                raise FileExistsError('exact recovery step was already issued')
            try:
                terminal = _json(_read(fd, previous_name + '-exit.json'))
            except FileNotFoundError:
                raise BoundaryError('previous recovery container exit is unknown') from None
            issued = _json(_read(fd, previous))
            created = _json(_read(fd, previous_name + '-created.json'))
            if inspect_exit(_digest(created['container_id']), previous_name, issued['image_id']) != terminal:
                raise BoundaryError('previous recovery container exit differs')
    if deadline - time.monotonic() < 219:
        raise BoundaryError('insufficient budget for an additional recovery container')
    _publish(fd, name + '-issued.json', {'name': name, 'image_id': plan['image_id'],
                                       'network_id': plan['network_id'], 'step_plan_sha256': step_sha})
    cid = _digest(docker(create_args(plan, directory, material, java, name, cli, protected)))
    _publish(fd, name + '-created.json', {'container_id': cid})
    if deadline - time.monotonic() < 214:
        raise BoundaryError('insufficient budget to start the exact recovery container')
    docker(['start', cid])
    wait_budget = deadline - time.monotonic() - 6
    if wait_budget <= 0:
        raise BoundaryError('container deadline exhausted')
    code = docker(['wait', cid], timeout=wait_budget)
    terminal = inspect_exit(cid, name, plan['image_id'])
    if str(terminal['exit_code']) != code:
        raise BoundaryError('exact recovery container terminal state unknown')
    _publish(fd, name + '-exit.json', terminal)
    if code != '0' or terminal['oom_killed']:
        raise BoundaryError('recovery container exited unsuccessfully')


def launch(plan, env):
    if platform.system() != 'Linux' or (os.geteuid(), os.getegid()) != (3000, 3000):
        raise BoundaryError('exact Linux recovery executor required')
    deadline = time.monotonic() + 228
    directory, material, java, step_sha, cli = arguments(plan, env)
    image, = json.loads(docker(['image', 'inspect', plan['image_id']]))
    network, = json.loads(docker(['network', 'inspect', plan['network_id']]))
    if (image['Id'], image['Os'], image['Architecture'], image['Config']['User'],
            (image['Config']['Labels'] or {}).get('org.opencontainers.image.revision')) != (
            plan['image_id'], 'linux', 'amd64', '3000:3000', plan['source_sha']):
        raise BoundaryError('reviewed local image differs')
    if (network['Id'], network['Name'], network['Driver'], network['Scope']) != (
            plan['network_id'], plan['network_name'], 'bridge', 'local'):
        raise BoundaryError('reviewed local network differs')
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        protected = require_issued(fd, plan, directory, step_sha)
        if plan['command'] != 'recover':
            protected += (directory / plan['inputs']['receipt']['attempt'] / 'receipt.json',)
        run_container(fd, plan, directory, material, java, step_sha, cli, protected, deadline)
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--reviewed-sha256', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    try:
        plan = reviewed(args.plan, args.reviewed_sha256)
        if args.execute:
            launch(plan, os.environ)
        else:
            arguments(plan, os.environ)
        print(json.dumps({'status': 'container_exited' if args.execute else 'plan_verified',
                          'execution_authorized': False}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, BoundaryError, subprocess.SubprocessError):
        print('{"status":"unavailable","execution_authorized":false}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
