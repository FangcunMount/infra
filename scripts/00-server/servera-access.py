#!/usr/bin/env python3
"""Audit ServerA access; --apply adds only the fixed readable-material sudo policy."""

import argparse
from contextlib import contextmanager
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import socket
import stat
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
NAME = 'fangcun-m4-readable-material-verify'
POLICY = ROOT / 'deploy/serverA/sudoers' / NAME
DESTINATION = Path('/etc/sudoers.d') / NAME
DIGEST = '36f3046ed453dfbf8beae684269c94d1a6db0abaa23de51e09d41e462c6a3d5c'
TOOL = Path('/opt/fangcun-m4/material-tools') / (DIGEST + '.py')
REVISION = 'm4-readable-20261028-v1'
ROLES = ('iam', 'qs-api', 'ai')


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def command(role):
    return ['/usr/bin/python3', '-I', str(TOOL), '--verify-installed',
            '--host', 'serverA', '--expect-role', role, '--expect-revision', REVISION]


def run(args, *, check=True):
    result = subprocess.run(args, text=True, capture_output=True, timeout=30)
    # Do not forward subprocess output: material contents and login data stay private.
    if check:
        require(result.returncode == 0, 'command_failed:' + args[0])
    return result


def secure_path(path, *, mode=None):
    """No symlinks or non-root/group/world-writable ancestors, including the file."""
    for item in (*reversed(path.parents), path):
        info = item.lstat()
        require(info.st_uid == 0 and info.st_mode & 0o022 == 0,
                'unsafe_owner_or_write_permission:' + str(item))
        if item != path or mode is None:
            require(stat.S_ISDIR(info.st_mode), 'unsafe_directory:' + str(item))
        else:
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == mode
                    and info.st_gid == 0 and info.st_nlink == 1,
                    'unsafe_file:' + str(item))


def policy_bytes():
    raw = POLICY.read_bytes()
    rules = [line for line in raw.decode().splitlines() if line and not line.startswith('#')]
    expected = ['deploy ALL=(root) NOPASSWD: ' + ' '.join(command(role)) for role in ROLES]
    require(rules == expected, 'policy_must_contain_only_three_exact_commands')
    return raw


def accounts():
    result = {}
    for name in ('root', 'ubuntu', 'deploy', 'www'):
        account = pwd.getpwnam(name)
        groups = sorted(grp.getgrgid(gid).gr_name
                        for gid in os.getgrouplist(name, account.pw_gid))
        password_status = run(['/usr/bin/passwd', '-S', name]).stdout.split()[1]
        result[name] = {'uid': account.pw_uid, 'gid': account.pw_gid,
                        'home': account.pw_dir, 'shell': account.pw_shell,
                        'groups': groups, 'password_status': password_status}
    deploy = result['deploy']
    require((deploy['uid'], deploy['gid'], deploy['home'], deploy['shell'])
            == (1002, 2001, '/home/deploy', '/bin/bash'), 'deploy_identity_drift')
    require(not {'sudo', 'wheel', 'docker'}.intersection(deploy['groups']),
            'deploy_privileged_group_drift')
    runtime = result['www']
    require((runtime['uid'], runtime['gid'], runtime['shell'], runtime['password_status'])
            == (2000, 2000, '/usr/sbin/nologin', 'L'), 'runtime_identity_drift')
    return result


def validate_report(raw, role):
    require(0 < len(raw) <= 32768, 'material_report_size')
    report = json.loads(raw)
    require(report['status'] == 'verified' and report['read_only'] is True
            and report['activated'] is False
            and (report['host'], report['role'], report['revision'])
            == ('serverA', role, REVISION)
            and report['material_root'] == '/var/lib/fangcun-m4-materials',
            'material_verification_failed')
    digest = report['receipt_sha256']
    require(isinstance(digest, str) and len(digest) == 64
            and all(c in '0123456789abcdef' for c in digest), 'invalid_receipt_hash')
    return report


def preflight():
    require(os.geteuid() == 0, 'root_required')
    require(socket.gethostname() == 'serverA', 'wrong_host')
    identity = accounts()
    secure_path(TOOL, mode=0o555)
    require(0 < TOOL.stat().st_size <= 65536
            and hashlib.sha256(TOOL.read_bytes()).hexdigest() == DIGEST, 'tool_digest_drift')
    secure_path(DESTINATION.parent)
    run(['/usr/sbin/visudo', '-c'])
    # Material validity is independent of sudo authorization. Fail before writing.
    for role in ROLES:
        validate_report(run(command(role)).stdout, role)
    return identity


def allowed(args):
    # List authorization only. Negative probes never execute the command.
    return run(['/usr/sbin/runuser', '-u', 'deploy', '--', '/usr/bin/sudo',
                '-n', '-l', '--', *args], check=False).returncode == 0


def negative_commands():
    base = command('iam')
    variants = [['/usr/bin/python3', '-c', 'pass'],
                [arg for arg in base if arg != '-I'], base + ['--plan', '/tmp/plan.json']]
    for old, new in (('serverA', 'serverD'), ('iam', 'worker'), (REVISION, 'm4-unapproved-v1'),
                     ('--verify-installed', '--apply'), (str(TOOL), '/tmp/uploaded.py')):
        variants.append([new if arg == old else arg for arg in base])
    return variants


def audit(raw):
    present = DESTINATION.exists() or DESTINATION.is_symlink()
    if present:
        secure_path(DESTINATION, mode=0o440)
        require(DESTINATION.read_bytes() == raw, 'managed_policy_drift')
    authorization = {role: allowed(command(role)) for role in ROLES}
    require(not any(allowed(args) for args in negative_commands()), 'broader_python_grant_detected')
    receipts = {}
    for role in ROLES:
        if authorization[role]:
            result = run(['/usr/sbin/runuser', '-u', 'deploy', '--', '/usr/bin/sudo',
                          '-n', '--', *command(role)])
            receipts[role] = validate_report(result.stdout, role)['receipt_sha256']
    return {'policy_installed': present, 'authorization': authorization,
            'negative_probes_denied': True, 'receipt_sha256': receipts,
            'status': 'verified' if present and all(authorization.values()) else 'missing_policy'}


@contextmanager
def maintenance_lock():
    path = Path('/run/infra-servera-access.lock')
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(fd, 'rb') as stream:
        secure_path(path, mode=0o600)
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def install_policy(raw):
    """Add one file atomically. Unknown existing content is never overwritten."""
    if DESTINATION.exists() or DESTINATION.is_symlink():
        secure_path(DESTINATION, mode=0o440)
        require(DESTINATION.read_bytes() == raw, 'managed_policy_drift')
        return False
    temporary = None
    published = False
    try:
        fd, name = tempfile.mkstemp(prefix='.' + NAME + '.', dir=DESTINATION.parent)
        temporary = Path(name)  # Dot name is ignored by sudoers includedir.
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fchown(stream.fileno(), 0, 0)
            os.fchmod(stream.fileno(), 0o440)
            os.fsync(stream.fileno())
        run(['/usr/sbin/visudo', '-cf', str(temporary)])
        # link() refuses to replace any destination that appeared concurrently.
        os.link(temporary, DESTINATION)
        published = True
        temporary.unlink()
        temporary = None
        run(['/usr/sbin/visudo', '-c'])
        require(audit(raw)['status'] == 'verified', 'post_install_audit_failed')
        return True
    except BaseException:
        if published:
            DESTINATION.unlink()
            run(['/usr/sbin/visudo', '-c'])
        raise
    finally:
        if temporary is not None:
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    raw = policy_bytes()
    identity = preflight()
    if args.apply:
        with maintenance_lock():
            # Detect existing broad Python grants before adding a new rule.
            audit(raw)
            changed = install_policy(raw)
            report = audit(raw)
    else:
        changed = False
        report = audit(raw)
    report.update(host='serverA', accounts=identity, changed=changed,
                  policy_sha256=hashlib.sha256(raw).hexdigest(),
                  policy_path=str(DESTINATION), revision=REVISION)
    print(json.dumps(report, sort_keys=True))
    return 0 if report['status'] == 'verified' else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, KeyError, ValueError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'status': 'refused', 'reason': str(error)}))
        raise SystemExit(2)
