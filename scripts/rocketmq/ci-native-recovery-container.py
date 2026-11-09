#!/usr/bin/env python3
"""Exercise the reviewed Linux coordinator and real image on an empty owned network."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import stat
import subprocess
import tempfile
import uuid

from cutover_step import execute, load_step
from start_boundary import Boundary, BoundaryError, _digest, _encoded, initialize


def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=60).stdout.strip()


def write(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)
    return hashlib.sha256(raw).hexdigest()


def worker(root, image, source, network, name):
    assert (os.geteuid(), os.getegid()) == (3000, 3000)
    os.umask(0o077)
    op, inputs = root / 'operation', root / 'inputs'
    inputs.mkdir(mode=0o700)
    java = inputs / 'java'
    (java / 'tls').mkdir(mode=0o700, parents=True)
    hashes = {key: write(inputs / (key + '.json'), b'{}\n')
              for key in ('config', 'manifest', 'export', 'request', 'approval')}
    named = hashlib.sha256(b'isolated-linux-launcher-refusal').hexdigest()
    binding = dict(schema='m3-start-boundary/v1', operation_id='linux-launcher-fixture', directory=str(op),
                   scope_sha256=named, protection_sha256=named, restore_receipt_sha256=named,
                   source_bundle_sha256=named, data_owner='fixture-data-owner', recovery_owner='fixture-recovery-owner')
    binding_sha = hashlib.sha256(_encoded(binding)).hexdigest()
    initialize(op, binding, binding_sha)
    plan = dict(schema='m3-native-recovery-container/v1', command='recover', directory=str(op),
                host=socket.gethostname(), image_id=image, source_sha=source, network_id=network,
                network_name=name, binding_sha256=binding_sha, step='fixture-refuses-invalid-review',
                inputs=hashes, java={'tools': write(java / 'tools.yml', b'{}\n'),
                                     'ca': write(java / 'tls' / 'server.crt', b'fixture only\n')})
    plan_path = root / 'container-plan.json'
    plan_sha = write(plan_path, _encoded(plan))
    launcher = Path(__file__).with_name('native_recovery_container.py')
    command = ['/usr/bin/python3', str(launcher), '--plan', str(plan_path),
               '--reviewed-sha256', plan_sha, '--execute']
    script = root / 'coordinator-step.sh'
    script_sha = write(script, ('#!/bin/bash\nset -euo pipefail\n' + shlex.join(command) + '\n').encode())
    step = dict(schema='m3-cutover-step/v1', directory=str(op), binding_sha256=binding_sha,
                host=plan['host'], step=plan['step'], kind='runtime-start', script=str(script),
                script_sha256=script_sha, cwd=str(root), timeout_seconds=240)
    step_path = root / 'coordinator-plan.json'
    step_sha = write(step_path, _encoded(step))
    loaded, raw = load_step(step_path, step_sha)
    try:
        execute(loaded, raw, step_sha)
    except BoundaryError:
        pass
    else:
        raise RuntimeError('malformed original request was accepted')
    prefix = op / ('native-container-' + step_sha)
    issued = json.loads(prefix.with_name(prefix.name + '-issued.json').read_text())
    created = json.loads(prefix.with_name(prefix.name + '-created.json').read_text())
    terminal = json.loads(prefix.with_name(prefix.name + '-exit.json').read_text())
    assert issued['request_sha256'] == hashes['request'] and terminal['container_id'] == created['container_id']
    assert terminal['exit_code'] == 1 and not terminal['oom_killed']
    with Boundary(op, binding_sha) as guard:
        state = guard.status()
    assert state['phase'] == 'runtime_start_failed' and not state['old_data_restore_eligible']
    assert not list(op.glob('native-recovery-claim-*')) and not list(op.glob('native-attempt-*'))
    print(json.dumps(dict(linux_coordinator=True, uid=3000, gid=3000, container_id=terminal['container_id'],
                          step_plan_sha256=step_sha, exit_code=1, native_claim_absent=True,
                          old_data_restore_eligible=False, production=False)))


def fixture(image, source):
    from final_image_candidate import ci_guard

    ci_guard(os.environ)
    assert image.startswith('sha256:') and _digest(image[7:]) and re.fullmatch('[0-9a-f]{40}', source)
    assert os.geteuid() != 0
    daemon = Path('/var/run/docker.sock').stat()
    assert stat.S_ISSOCK(daemon.st_mode) and daemon.st_gid != 0
    name = 'f07-linux-launcher-' + uuid.uuid4().hex[:16]
    docker = ['/usr/bin/docker', '--host', 'unix:///var/run/docker.sock']
    network = _digest(run([*docker, 'network', 'create', '--internal', '--label', 'f07.fixture=' + name, name]))
    try:
        with tempfile.TemporaryDirectory(prefix=name + '-', dir='/tmp') as tmp:
            directory = Path(tmp)
            directory.chmod(0o755)
            material = directory / 'private'
            material.mkdir(mode=0o700)
            code = directory / 'code'
            code.mkdir(mode=0o755)
            code.chmod(0o755)  # The workflow has a private umask; UID 3000 must traverse only this code directory.
            for filename in (Path(__file__).name, 'native_recovery_container.py', 'cutover_step.py', 'start_boundary.py'):
                dest = code / filename
                shutil.copyfile(Path(__file__).with_name(filename), dest)
                dest.chmod(0o444)
            run(['/usr/bin/sudo', '-n', '/usr/bin/chown', '3000:3000', str(material)])
            try:
                args = ['/usr/bin/sudo', '-n', '/usr/bin/setpriv', '--reuid=3000', '--regid=3000',
                        '--groups=' + str(daemon.st_gid), '/usr/bin/python3', str(code / Path(__file__).name),
                        '--worker', str(material), image, source, network, name]
                try:
                    proof = json.loads(run(args))
                except subprocess.CalledProcessError as error:
                    raise RuntimeError('isolated worker failed: ' + error.stderr[-1200:].strip()) from None
                cid = _digest(proof['container_id'])
                container, = json.loads(run([*docker, 'container', 'inspect', cid]))
                assert container['Image'] == image and container['Config']['User'] == '3000:3000'
                assert container['HostConfig']['ReadonlyRootfs'] and container['HostConfig']['CapDrop'] == ['ALL']
                assert [v['NetworkID'] for v in container['NetworkSettings']['Networks'].values()] == [network]
                result = next(json.loads(line) for line in run([*docker, 'logs', cid]).splitlines() if line.startswith('{'))
                assert result['schema'] == 'm3-native-recovery-result/v1' and result['last_stage'] == 'review'
                assert not result.get('receipt_sha256')
                proof.update(image_id=image, source_sha=source, failed_before_native_effect=True, network_internal=True)
            finally:
                # Only this fresh internal network can supply cleanup candidates.
                members = json.loads(run([*docker, 'network', 'inspect', network]))[0]['Containers'] or {}
                # Docker may omit exited containers from the active endpoint list.
                saved = run([*docker, 'ps', '-a', '--no-trunc', '--filter', 'network=' + network, '--format', '{{.ID}}'])
                for cid in set(members) | set(saved.splitlines()):
                    cid = _digest(cid)
                    item, = json.loads(run([*docker, 'container', 'inspect', cid]))
                    step = _digest(item['Config']['Labels']['native.recovery.step'])
                    assert item['Name'] == '/native-container-' + step and item['Image'] == image
                    assert not item['State']['Running']
                    run([*docker, 'container', 'rm', cid])
                run(['/usr/bin/sudo', '-n', '/usr/bin/chown', '-R', f'{os.getuid()}:{os.getgid()}', str(material)])
    finally:
        run([*docker, 'network', 'rm', network])
    proof['owned_fixture_cleaned'] = True
    print(json.dumps(proof, sort_keys=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', nargs=5)
    parser.add_argument('--image')
    parser.add_argument('--source')
    args = parser.parse_args()
    if args.worker:
        path, *other = args.worker
        worker(Path(path), *other)
    else:
        fixture(args.image, args.source)
