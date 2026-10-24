#!/usr/bin/env python3
"""One reviewed local-host maintenance step; default is offline verification.

The named production approval supplies the independent plan digest. A successful
command is not readiness, restoration, a system login or permission to reopen
admission. This entry point never calls an ordinary deployment fallback itself.
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import socket
import stat
import subprocess
import time
import uuid

from start_boundary import Boundary, BoundaryError, _digest, _encoded, _json, _publish, _read, _step, initialize

GLOBAL_LOCK = Path('/var/lib/fangcun-image-retention/deploy.lock')
AI_LOCK = Path('/opt/qs-ai/deploy.lock')


def private_bytes(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1 or info.st_uid != os.geteuid() or info.st_size > limit):
            raise BoundaryError('private bounded reviewed input required')
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise BoundaryError('reviewed input exceeds limit')
    return raw


def reviewed(path, digest):
    raw = private_bytes(path, 16384)
    if hashlib.sha256(raw).hexdigest() != _digest(digest):
        raise BoundaryError('independent reviewed digest differs')
    value = _json(raw)
    if raw != _encoded(value):
        raise BoundaryError('canonical reviewed object required')
    return value


def absolute(value):
    if (not isinstance(value, str) or len(value) > 4096 or not value.startswith('/') or '\x00' in value
            or any(part in {'.', '..'} for part in value.split('/'))
            or str(Path(value)) != value):
        raise BoundaryError('fixed absolute operation path required')
    return Path(value)


def load_step(path, digest):
    value = reviewed(path, digest)
    fields = {'schema', 'directory', 'binding_sha256', 'host', 'step', 'kind',
              'script', 'script_sha256', 'cwd', 'timeout_seconds'}
    if set(value) != fields or value['schema'] != 'm3-cutover-step/v1':
        raise BoundaryError('exact reviewed step required')
    absolute(value['directory']); absolute(value['cwd']); absolute(value['script'])
    _digest(value['binding_sha256']); _digest(value['script_sha256']); _step(value['step'])
    if (not isinstance(value['host'], str) or not value['host'] or len(value['host']) > 253
            or any(ord(c) < 33 for c in value['host'])
            or not isinstance(value['kind'], str)
            or value['kind'] not in {'runtime-start', 'pre-start-restore', 'forward-repair',
                                     'pre-start-maintenance', 'pre-start-repair'}
            or type(value['timeout_seconds']) is not int or not 1 <= value['timeout_seconds'] <= 1200):
        raise BoundaryError('bounded host step required')
    script = private_bytes(value['script'], 1024 * 1024)
    if hashlib.sha256(script).hexdigest() != value['script_sha256']:
        raise BoundaryError('exact reviewed script differs')
    return value, script  # Snapshot executes these bytes, never reopens the script.


@contextlib.contextmanager
def deployment_locks(ai_host):
    # Reuse existing inode/order. Never create, chmod or replace deployment locks.
    with contextlib.ExitStack() as stack:
        for path in ([GLOBAL_LOCK, AI_LOCK] if ai_host else [GLOBAL_LOCK]):
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
            stack.callback(os.close, fd)
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid not in {0, os.geteuid()}):
                raise BoundaryError('original deployment lock unavailable')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def _group_exists(group):
    try:
        os.killpg(group, 0)
        return True
    except ProcessLookupError:
        return False


def run_script(script, plan, operation):
    # Raw output stays in the private operation directory, never stdout/CI logs.
    name = 'command-' + uuid.uuid4().hex + '.log'
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=operation.fd)
    with os.fdopen(fd, 'wb') as output:
        process = subprocess.Popen(['/bin/bash', '--noprofile', '--norc', '-e', '-u', '-o', 'pipefail', '-s', '--'],
                                   stdin=subprocess.PIPE, stdout=output, stderr=output,
                                   cwd=plan['cwd'], start_new_session=True,
                                   env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C',
                                        'HOME': str(operation.directory),
                                        # Derived from this already approved plan. Scripts
                                        # cannot embed their own plan hash without a cycle.
                                        # These values alone never grant authorization.
                                        'M3_COORDINATOR_DIRECTORY': str(operation.directory),
                                        'M3_COORDINATOR_BINDING_SHA256': plan['binding_sha256'],
                                        'M3_COORDINATOR_STEP': plan['step'],
                                        'M3_COORDINATOR_STEP_PLAN_SHA256': hashlib.sha256(_encoded(plan)).hexdigest()})
        try:
            process.communicate(script, timeout=plan['timeout_seconds'])
        finally:
            # Confine cleanup to the process group created for this exact step.
            # Timeout/cancellation is never a successful step or a rollback proof.
            detached = process.poll() is not None and _group_exists(process.pid)
            if _group_exists(process.pid):
                with contextlib.suppress(ProcessLookupError): os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            deadline = time.monotonic() + 2
            while _group_exists(process.pid) and time.monotonic() < deadline:
                time.sleep(.05)
            output.flush(); os.fsync(output.fileno()); os.fsync(operation.fd)
            if _group_exists(process.pid):
                raise BoundaryError('owned command group not drained; forward recovery required')
            if detached:
                raise BoundaryError('reviewed command left background work; forward recovery required')
        if process.returncode != 0:
            raise BoundaryError('reviewed command failed; raw output retained privately')


def execute(plan, script, reviewed_sha256):
    if (hashlib.sha256(_encoded(plan)).hexdigest() != _digest(reviewed_sha256)
            or hashlib.sha256(script).hexdigest() != plan['script_sha256']):
        raise BoundaryError('reviewed execution snapshot differs')
    if platform.system() != 'Linux' or socket.gethostname() != plan['host']:
        raise BoundaryError('reviewed execution host differs')
    # The single coordinator owns this barrier; the actual target entrypoint
    # holds that target's existing deployment locks. Taking the coordinator's
    # unrelated host lock here would neither protect remote hosts nor permit a
    # co-located target entrypoint to acquire its own lock safely.
    with Boundary(plan['directory'], plan['binding_sha256']) as operation:
        receipt = 'reviewed-step-' + _digest(reviewed_sha256) + '.json'
        try:
            _publish(operation.fd, receipt, plan)
        except FileExistsError:
            if _read(operation.fd, receipt) != _encoded(plan):
                raise BoundaryError('reviewed step receipt differs') from None
        callback = lambda: run_script(script, plan, operation)
        if plan['kind'] == 'runtime-start':
            operation.start(plan['step'], callback)
        elif plan['kind'] == 'pre-start-restore':
            operation.restore_before_start(plan['step'], callback)
        elif plan['kind'] == 'pre-start-maintenance':
            operation.maintain_before_start(plan['step'], callback)
        elif plan['kind'] == 'pre-start-repair':
            operation.maintain_before_start(plan['step'], callback, reviewed_sha256)
        elif plan['kind'] == 'forward-repair':
            operation.forward_repair(plan['step'], reviewed_sha256, callback)
        else:
            raise BoundaryError('exact reviewed step kind required')
        return operation.status()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--reviewed-sha256', required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--initialize', action='store_true', help='create a reviewed binding once, no command')
    modes.add_argument('--execute', action='store_true', help='execute one separately approved step on its exact Linux host')
    args = parser.parse_args(argv)
    try:
        if args.initialize:
            binding = reviewed(args.plan, args.reviewed_sha256)
            absolute(binding.get('directory'))
            initialize(binding['directory'], binding, args.reviewed_sha256)
            status = 'operation_initialized'
        else:
            plan, script = load_step(args.plan, args.reviewed_sha256)
            if args.execute:
                execute(plan, script, args.reviewed_sha256)
                status = 'reviewed_command_returned'
            else:
                status = 'offline_plan_verified'
        print(json.dumps({'status': status, 'cutover_authorized': False}, sort_keys=True))
        return 0
    except (OSError, ValueError, BoundaryError, subprocess.SubprocessError):
        # Never print a raw command, script, hostname, path, credential or error.
        print('{"status":"unavailable","cutover_authorized":false}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
