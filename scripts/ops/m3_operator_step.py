#!/usr/bin/env python3
"""Run a reviewed operator SSH script under the existing single POSIX barrier.

This entrypoint is for the exact reviewed macOS operator host. Target scripts
continue through the original Mac mini SSH ingress and Linux target guards.
No SSH key is copied to a production host and no target coordinator is created.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import socket
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'rocketmq'))
from cutover_step import load_step, run_script
from start_boundary import Boundary, BoundaryError, _digest, _encoded, _publish, _read


def execute(plan, script, expected):
    if (hashlib.sha256(_encoded(plan)).hexdigest() != _digest(expected)
            or hashlib.sha256(script).hexdigest() != plan['script_sha256']):
        raise BoundaryError('reviewed execution snapshot differs')
    if platform.system() != 'Darwin' or socket.gethostname() != plan['host']:
        raise BoundaryError('exact reviewed macOS operator required')
    with Boundary(plan['directory'], plan['binding_sha256']) as operation:
        name = 'reviewed-step-' + expected + '.json'
        try:
            _publish(operation.fd, name, plan)
        except FileExistsError:
            if _read(operation.fd, name) != _encoded(plan):
                raise BoundaryError('operator step receipt differs') from None
        callback = lambda: run_script(script, plan, operation)
        if plan['kind'] == 'runtime-start':
            operation.start(plan['step'], callback)
        elif plan['kind'] == 'pre-start-restore':
            operation.restore_before_start(plan['step'], callback)
        elif plan['kind'] == 'pre-start-maintenance':
            operation.maintain_before_start(plan['step'], callback)
        elif plan['kind'] == 'pre-start-repair':
            operation.maintain_before_start(plan['step'], callback, expected)
        elif plan['kind'] == 'forward-repair':
            operation.forward_repair(plan['step'], expected, callback)
        else:
            raise BoundaryError('exact reviewed operator step kind required')
        return operation.status()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--reviewed-sha256', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    try:
        plan, script = load_step(args.plan, args.reviewed_sha256)
        if args.execute:
            execute(plan, script, args.reviewed_sha256)
        print(json.dumps({'status': 'reviewed_command_returned' if args.execute else 'offline_plan_verified',
                          'cutover_authorized': False}))
        return 0
    except (OSError, ValueError, BoundaryError, subprocess.SubprocessError):
        print('{"status":"unavailable","cutover_authorized":false}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
