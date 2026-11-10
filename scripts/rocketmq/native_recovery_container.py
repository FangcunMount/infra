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
from start_boundary import Boundary, BoundaryError, _digest, _encoded, _json, _publish, _read, _step


DOCKER = ('/usr/bin/docker', '--host', 'unix:///var/run/docker.sock')
NATIVE = '/opt/native-recovery/native-recovery'
ADMIN_SCRIPT = '/run/native-recovery/native-admin.sh'
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
    if set(plan) - {'prior_terminal'} != fields or plan['schema'] != 'm3-native-recovery-container/v1':
        raise BoundaryError('exact reviewed container plan required')
    prior = plan.get('prior_terminal')
    if 'prior_terminal' in plan:
        if not isinstance(prior, dict) or set(prior) != {'step_plan_sha256', 'observation_sha256'}:
            raise BoundaryError('exact prior terminal review required')
        _digest(prior['step_plan_sha256'])
        _digest(prior['observation_sha256'])
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
            {p.name for p in java.iterdir()} != {'tls', 'tools.yml', 'native-admin.sh'} or
            {p.name for p in tls.iterdir()} != {'server.crt'}):
        raise BoundaryError('unexpected mounted materials')
    if not isinstance(plan['java'], dict) or set(plan['java']) != {'tools', 'ca', 'admin_script'}:
        raise BoundaryError('reviewed Java inputs required')
    input_digest(java / 'tools.yml', plan['java']['tools'])
    input_digest(tls / 'server.crt', plan['java']['ca'])
    input_digest(java / 'native-admin.sh', plan['java']['admin_script'])
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
    config = _json(private_bytes(material / 'config.json', PRIVATE_FILE_LIMIT))
    if not isinstance(config, dict) or (config.get('native_admin_script'), config.get('native_admin_script_sha256')) != (
            ADMIN_SCRIPT, plan['java']['admin_script']):
        raise BoundaryError('reviewed configuration must select the mounted native admin script')
    return directory, material, java, step_sha, cli


def bind_mounts(directory, material, java, protected):
    return [(str(directory), str(directory), True), (str(material), str(material), False),
            (str(java), '/run/native-recovery', False), *((str(path), str(path), False) for path in protected)]


def create_args(plan, name, cli, mounts):
    return ['create', '--name', name, '--pull', 'never', '--platform', 'linux/amd64',
            '--label', 'native.recovery.step=' + name.removeprefix('native-container-'),
            '--hostname', plan['host'], '--network', plan['network_id'],
            '--read-only', '--user', '3000:3000', '--restart', 'no',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--pids-limit', '64', '--memory', '384m', '--cpus', '1',
            *[arg for source, destination, writable in mounts for arg in (
                '--mount', f'type=bind,src={source},dst={destination}' + ('' if writable else ',readonly'))],
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
            ('prior_terminal' in plan and step['kind'] != 'forward-repair') or
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


def inspect_exit(target, name, image, network):
    container, = json.loads(docker(['container', 'inspect', target]))
    state = container['State']
    cid = _digest(container['Id'])
    if (target not in {name, cid} or
            (container['Name'], container['Image'], state['Status'], state['Running'], container['RestartCount']) != (
                '/' + name, image, 'exited', False, 0) or
            (container['Config']['Labels'] or {}).get('native.recovery.step') != name.removeprefix('native-container-') or
            [v['NetworkID'] for v in container['NetworkSettings']['Networks'].values()] != [network]):
        raise BoundaryError('exact recovery container terminal state unknown')
    return {'container_id': cid, 'exit_code': state['ExitCode'], 'oom_killed': state['OOMKilled'],
            'started_at': state['StartedAt'], 'finished_at': state['FinishedAt']}


def require_created(cid, name, plan, mounts):
    container, = json.loads(docker(['container', 'inspect', cid]))
    config, host, state = (container[field] for field in ('Config', 'HostConfig', 'State'))
    networks = container['NetworkSettings']['Networks']
    network = networks.get(plan['network_name'], {})
    if (container['Id'], container['Name'], container['Image'], state['Status'], state['Running'],
            config['User'], (config['Labels'] or {}).get('native.recovery.step')) != (
            cid, '/' + name, plan['image_id'], 'created', False, '3000:3000', name.removeprefix('native-container-')):
        raise BoundaryError('created recovery container identity differs')
    # Docker can leave the endpoint ID blank until start. NetworkMode is bound at create.
    if (set(networks) != {plan['network_name']} or host['NetworkMode'] != plan['network_id'] or
            network['NetworkID'] not in {'', plan['network_id']}):
        raise BoundaryError('created recovery container network differs')
    if (not host['ReadonlyRootfs'] or host['Privileged'] or host['CapAdd'] or host['CapDrop'] != ['ALL'] or
            host['SecurityOpt'] != ['no-new-privileges'] or host['RestartPolicy']['Name'] != 'no' or
            (host['Memory'], host['NanoCpus'], host['PidsLimit']) != (384 * 1024**2, 10**9, 64) or
            any(host.get(field) for field in ('Devices', 'DeviceRequests', 'PortBindings', 'PublishAllPorts',
                                              'VolumesFrom', 'Binds'))):
        raise BoundaryError('created recovery container sandbox differs')
    actual = [(mount['Source'], mount['Destination'], mount['RW']) for mount in container['Mounts']]
    if any(mount['Type'] != 'bind' for mount in container['Mounts']) or sorted(actual) != sorted(mounts):
        raise BoundaryError('created recovery container mounts differ')


def terminal_observation(fd, previous_name):
    issued = _json(_read(fd, previous_name + '-issued.json'))
    prior_step = _digest(issued['step_plan_sha256'])
    if previous_name != 'native-container-' + prior_step or issued['name'] != previous_name:
        raise BoundaryError('prior issue record differs')
    try:
        created = _json(_read(fd, previous_name + '-created.json'))
    except FileNotFoundError:
        target = previous_name
    else:
        target = _digest(created['container_id'])
    return {'schema': 'm3-native-recovery-terminal-observation/v1',
            'step_plan_sha256': prior_step, 'execution_authorized': False,
            'terminal': inspect_exit(target, previous_name, issued['image_id'], issued['network_id'])}


def observe_prior(plan, step_sha):
    if platform.system() != 'Linux' or (os.geteuid(), os.getegid()) != (3000, 3000) or plan['host'] != socket.gethostname():
        raise BoundaryError('exact Linux recovery executor required')
    directory = private_directory(absolute(plan['directory']))
    with Boundary(directory, plan['binding_sha256']) as operation:
        return terminal_observation(operation.fd, 'native-container-' + _digest(step_sha))


def run_container(fd, plan, directory, material, java, step_sha, cli, protected, deadline):
    name = 'native-container-' + step_sha
    prior = plan.get('prior_terminal')
    reconciled = None
    for previous in os.listdir(fd):
        if re.fullmatch(r'native-container-[0-9a-f]{64}-issued\.json', previous):
            previous_name = previous.removesuffix('-issued.json')
            if previous_name == name:
                raise FileExistsError('exact recovery step was already issued')
            issued = _json(_read(fd, previous))
            if plan['command'] == 'recover' and plan['inputs']['request'] == issued['request_sha256']:
                raise BoundaryError('recovery requires a new request after an issued attempt')
            try:
                terminal = _json(_read(fd, previous_name + '-exit.json'))
            except FileNotFoundError:
                try:
                    terminal = _json(_read(fd, previous_name + '-reconciled.json'))['terminal']
                except FileNotFoundError:
                    if not prior or previous_name != 'native-container-' + prior['step_plan_sha256']:
                        raise BoundaryError('previous recovery container exit is unknown') from None
                    observation = terminal_observation(fd, previous_name)
                    if hashlib.sha256(_encoded(observation)).hexdigest() != prior['observation_sha256']:
                        raise BoundaryError('reviewed prior terminal observation differs')
                    reconciled = (previous_name, observation)
                    continue
            if terminal_observation(fd, previous_name)['terminal'] != terminal:
                raise BoundaryError('previous recovery container exit differs')
    if prior is not None and reconciled is None:
        raise BoundaryError('reviewed prior terminal does not identify an unresolved launch')
    if deadline - time.monotonic() < 219:
        raise BoundaryError('insufficient budget for an additional recovery container')
    if reconciled:
        previous_name, observation = reconciled
        _publish(fd, previous_name + '-reconciled.json',
                 {'terminal': observation['terminal'], 'reviewed_by_step_plan_sha256': step_sha,
                  'observation_sha256': prior['observation_sha256']})
    _publish(fd, name + '-issued.json', {'name': name, 'image_id': plan['image_id'],
                                       'network_id': plan['network_id'], 'step_plan_sha256': step_sha,
                                       'request_sha256': plan['inputs']['request']})
    mounts = bind_mounts(directory, material, java, protected)
    cid = _digest(docker(create_args(plan, name, cli, mounts)))
    _publish(fd, name + '-created.json', {'container_id': cid})
    require_created(cid, name, plan, mounts)
    if deadline - time.monotonic() < 214:
        raise BoundaryError('insufficient budget to start the exact recovery container')
    docker(['start', cid])
    wait_budget = deadline - time.monotonic() - 6
    if wait_budget <= 0:
        raise BoundaryError('container deadline exhausted')
    code = docker(['wait', cid], timeout=wait_budget)
    terminal = inspect_exit(cid, name, plan['image_id'], plan['network_id'])
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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--execute', action='store_true')
    mode.add_argument('--observe-prior', metavar='STEP_PLAN_SHA256')
    args = parser.parse_args()
    try:
        plan = reviewed(args.plan, args.reviewed_sha256)
        if args.observe_prior:
            print(_encoded(observe_prior(plan, args.observe_prior)).decode(), end='')
            return 0
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
