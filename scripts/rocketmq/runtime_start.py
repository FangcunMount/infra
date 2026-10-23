#!/usr/bin/env python3
"""Fixed target-host Compose start only; no migration, pull, stop or fallback.

Invoke only from the approved single coordinator after its persistent first-start
barrier. The explicit flag is an operator attestation, never approval evidence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import socket
import subprocess

from cutover_step import absolute, deployment_locks, private_bytes, reviewed
from start_boundary import BoundaryError, _digest

DOCKER = '/usr/bin/docker'
SOCKET = 'unix:///var/run/docker.sock'
NAME = re.compile('[a-z0-9][a-z0-9_-]{0,62}')
IMAGE = re.compile('[a-z0-9][a-z0-9._:/-]{0,450}@sha256:[0-9a-f]{64}')


def load(path, digest):
    value = reviewed(path, digest)
    fields = {'schema', 'coordinator_binding_sha256', 'host', 'project', 'directory',
              'compose_file', 'compose_sha256', 'environment_file', 'environment_sha256',
              'services', 'images', 'instances', 'ai_host'}
    if set(value) != fields or value['schema'] != 'm3-runtime-start/v1':
        raise BoundaryError('exact target start plan required')
    _digest(value['coordinator_binding_sha256'])
    if (not isinstance(value['host'], str) or not value['host'] or len(value['host']) > 253
            or any(ord(c) < 33 for c in value['host'])
            or not isinstance(value['project'], str) or not NAME.fullmatch(value['project'])
            or type(value['ai_host']) is not bool):
        raise BoundaryError('fixed target identity required')
    directory = absolute(value['directory'])
    for key, digest_key in (('compose_file', 'compose_sha256'), ('environment_file', 'environment_sha256')):
        path = absolute(value[key])
        # A frozen private release, not arbitrary shared file locations.
        if path.parent != directory or hashlib.sha256(private_bytes(path, 1024*1024)).hexdigest() != _digest(value[digest_key]):
            raise BoundaryError('frozen target configuration differs')
    services = value['services']
    if (not isinstance(services, list) or not 1 <= len(services) <= 16
            or any(not isinstance(x, str) or not NAME.fullmatch(x) for x in services)
            or len(set(services)) != len(services)
            or not isinstance(value['images'], dict) or not isinstance(value['instances'], dict)
            or set(value['images']) != set(services) or set(value['instances']) != set(services)):
        raise BoundaryError('exact bounded service set required')
    for name in services:
        if (not isinstance(value['images'][name], str) or not IMAGE.fullmatch(value['images'][name])
                or type(value['instances'][name]) is not int or not 1 <= value['instances'][name] <= 16):
            raise BoundaryError('fixed image digest and instance budget required')
    if sum(value['instances'].values()) > 16:
        raise BoundaryError('target instance budget exceeded')
    return value


def compose(plan, *args):
    return [DOCKER, '--host', SOCKET, 'compose', '--project-name', plan['project'],
            '--project-directory', plan['directory'], '--file', plan['compose_file'],
            '--env-file', plan['environment_file'], *args]


def command(plan, argv, timeout=30):
    result = subprocess.run(argv, cwd=plan['directory'], capture_output=True, timeout=timeout,
                            env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C',
                                 'HOME': plan['directory']}, check=False)
    if result.returncode != 0 or len(result.stdout) > 2*1024*1024:
        raise BoundaryError('target command failed; preserve coordinator evidence')
    return result.stdout


def verify_config(plan, raw):
    # Config stdout can contain environment values; never print or publish it.
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise BoundaryError('target Compose configuration unavailable')
    services = value.get('services')
    if not isinstance(services, dict):
        raise BoundaryError('target Compose configuration unavailable')
    for name in plan['services']:
        entry = services.get(name)
        if (not isinstance(entry, dict) or entry.get('image') != plan['images'][name]
                or 'build' in entry):
            raise BoundaryError('target image is not the frozen runtime')
        deploy = entry.get('deploy', {})
        if not isinstance(deploy, dict):
            raise BoundaryError('target runtime budget unavailable')
        replicas = deploy.get('replicas', 1)
        scale = entry.get('scale', replicas)
        if (type(replicas) is not int or type(scale) is not int
                or scale != plan['instances'][name]
                or ('replicas' in deploy and replicas != scale)):
            raise BoundaryError('target configured instance budget differs')


def verify_running(plan, raw):
    counts = dict.fromkeys(plan['services'], 0)
    seen = set()
    for line in raw.decode().splitlines():
        fields = line.split()
        if len(fields) != 6:
            raise BoundaryError('target container readback unavailable')
        identity, image, project, service, running, health = fields
        if (re.fullmatch('[0-9a-f]{64}', identity) is None or identity in seen
                or project != plan['project'] or service not in counts
                or image != plan['images'][service] or running != 'true'
                or health not in {'none', 'healthy'}):
            raise BoundaryError('target runtime readback differs')
        seen.add(identity); counts[service] += 1
    if counts != plan['instances']:
        raise BoundaryError('target runtime instance budget differs')


def execute(plan):
    if platform.system() != 'Linux' or socket.gethostname() != plan['host']:
        raise BoundaryError('actual target host differs')
    with deployment_locks(plan['ai_host']):
        # Re-read all frozen inputs after acquiring the original host locks.
        for key, digest_key in (('compose_file', 'compose_sha256'), ('environment_file', 'environment_sha256')):
            if hashlib.sha256(private_bytes(plan[key], 1024*1024)).hexdigest() != plan[digest_key]:
                raise BoundaryError('target configuration changed before startup')
        verify_config(plan, command(plan, compose(plan, 'config', '--format', 'json')))
        command(plan, compose(plan, 'up', '--detach', '--no-deps', '--no-build', '--pull', 'never',
                              '--wait', '--wait-timeout', '120', *plan['services']), timeout=150)
        ids = command(plan, compose(plan, 'ps', '--all', '--quiet', *plan['services'])).decode().split()
        if len(ids) != sum(plan['instances'].values()) or any(re.fullmatch('[0-9a-f]{64}', i) is None for i in ids):
            raise BoundaryError('target service instance set differs')
        template = ('{{.Id}} {{.Config.Image}} {{index .Config.Labels "com.docker.compose.project"}} '
                    '{{index .Config.Labels "com.docker.compose.service"}} {{.State.Running}} '
                    '{{if index .State "Health"}}{{index (index .State "Health") "Status"}}{{else}}none{{end}}')
        verify_running(plan, command(plan, [DOCKER, '--host', SOCKET, 'inspect', '--type', 'container',
                                           '--format', template, *ids]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--reviewed-sha256', required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--coordinated-start-already-issued', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.execute != args.coordinated_start_already_issued:
            raise BoundaryError('explicit coordinator attestation required')
        plan = load(args.plan, args.reviewed_sha256)
        if args.execute:
            execute(plan)
        print(json.dumps({'status': 'target_runtime_readback_verified' if args.execute else 'offline_target_plan_verified',
                          'cutover_authorized': False}, sort_keys=True))
        return 0
    except (OSError, ValueError, BoundaryError, subprocess.SubprocessError):
        print('{"status":"unavailable","cutover_authorized":false}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
