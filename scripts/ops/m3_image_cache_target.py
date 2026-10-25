"""Target-host fixed-image cache only. Credential envelope arrives on SSH stdin."""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def private_json(path, value):
    with path.open('x', encoding='utf8') as f:
        os.chmod(path, 0o600)
        json.dump(value, f)


def checked_plan(raw, sha, target):
    require(hashlib.sha256(raw.encode()).hexdigest() == sha, 'reviewed_plan_changed')
    plan = json.loads(raw)
    require(plan['schema'] == 'm3-fixed-image-cache/v1' and target in ('serverA', 'serverD'), 'fixed_target_required')
    require(set(plan['targets']) == {'serverA', 'serverD'}, 'exact_targets_required')
    roles = plan['targets'][target]['roles']
    require(roles == (['iam', 'qs-api', 'qs-collection', 'ai'] if target == 'serverA' else ['qs-worker']), 'exact_roles_required')
    for role in roles:
        require(re.fullmatch(re.escape(plan['registry']) + r'/fangcunmount/[a-z-]+@sha256:[0-9a-f]{64}', plan['images'][role]['reference']), 'fixed_reference_required')
    require(plan['runtime_started'] is False and plan['old_images_removed'] is False, 'cache_only_required')
    return plan


def remove_auth(root):
    auth = root / 'auth'
    if not auth.exists():
        return
    require(not auth.is_symlink() and auth.stat().st_uid == os.getuid(), 'owned_auth_required')
    require({p.name for p in auth.iterdir()} <= {'config.json'}, 'unexpected_auth_contents')
    for p in auth.iterdir():
        require(not p.is_symlink() and p.stat().st_uid == os.getuid(), 'owned_auth_file_required')
        p.unlink()
    auth.rmdir()


def execute(envelope):
    plan = checked_plan(envelope['plan'], envelope['plan_sha256'], envelope['target'])
    target = envelope['target']; selected = plan['targets'][target]
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64' and socket.gethostname() == target, 'actual_target_mismatch')
    operation = envelope['operation']; require(re.fullmatch(r'[0-9]{1,20}-[0-9]{1,6}', operation), 'fixed_operation_required')
    root = Path('/tmp') / ('m3-image-cache-' + operation + '-' + target)
    if envelope.get('cleanup_only'):
        if root.exists():
            require(not root.is_symlink() and root.stat().st_uid == os.getuid(), 'owned_operation_required')
            remove_auth(root)
        return dict(target=target, cleanup_only=True, authentication_removed=True)
    os.umask(0o077); root.mkdir(mode=0o700)
    report = dict(target=target, passed=0, failed=1, skipped=0, cached={}, runtime_started=False, old_images_removed=False, authentication_removed=False)
    fd = os.open('/var/lib/fangcun-image-retention/deploy.lock', os.O_RDWR | os.O_NOFOLLOW)
    require(os.fstat(fd).st_ino == selected['lock_inode'], 'original_lock_changed')
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    prefix = ['/usr/bin/docker']; password = envelope.get('sudo_password', '')
    def call(args, timeout=45):
        p = subprocess.run(prefix + ['--config', str(root / 'auth'), '--host', 'unix:///var/run/docker.sock'] + args,
            input=(password + '\n').encode() if prefix[0] == 'sudo' and '-S' in prefix else None,
            capture_output=True, timeout=timeout)
        require(p.returncode == 0, 'private_docker_operation_failed')
        return p.stdout
    try:
        auth = envelope['docker_auth']
        require(set(auth) == {'auths'} and set(auth['auths']) == {plan['registry']} and set(auth['auths'][plan['registry']]) == {'auth'}, 'exact_registry_auth_required')
        require(b':' in base64.b64decode(auth['auths'][plan['registry']]['auth'], validate=True), 'registry_auth_invalid')
        (root / 'auth').mkdir(mode=0o700); private_json(root / 'auth/config.json', auth)
        # Select privilege on a read-only command; never retry a pull.
        p = subprocess.run(prefix + ['--host', 'unix:///var/run/docker.sock', 'version', '--format', '{{.Server.Version}}'], capture_output=True, timeout=20)
        if p.returncode:
            prefix = ['sudo', '-S', '-p', '', '/usr/bin/docker'] if password else ['sudo', '-n', '/usr/bin/docker']
        call(['version', '--format', '{{.Server.Version}}'])
        disk = shutil.disk_usage('/var/lib/docker')
        require(disk.free >= selected['minimum_free_bytes'], 'insufficient_cache_headroom')
        def inventory():
            ids = call(['ps', '-aq']).decode().split()
            require(bool(ids), 'nonempty_runtime_inventory_required')
            rows = json.loads(call(['inspect', *ids])); result = {}
            for c in rows:
                result[c['Name']] = {'id': c['Id'], 'image': c['Image'], 'state': {k:c['State'][k] for k in ('StartedAt','Status','OOMKilled')}, 'restart_count':c['RestartCount'],
                    'config_sha256':hashlib.sha256(json.dumps(c['Config'],sort_keys=True).encode()).hexdigest(),
                    'host_config_sha256':hashlib.sha256(json.dumps(c['HostConfig'],sort_keys=True).encode()).hexdigest()}
            return result
        before = inventory(); private_json(root / 'inventory-before.json', before)
        for role in selected['roles']:
            ref = plan['images'][role]['reference']
            call(['pull', '--quiet', ref], timeout=600)
            image = json.loads(call(['image', 'inspect', ref]))[0]
            require(ref in image.get('RepoDigests', []), 'exact_digest_readback_required')
            report['cached'][role] = dict(reference=ref, engine_image_id=image['Id'], source_sha=plan['images'][role]['source_sha'])
        after = inventory(); private_json(root / 'inventory-after.json', after)
        require(before == after, 'original_runtime_changed')
        report.update(passed=len(report['cached']),failed=0,original_containers_unchanged=True)
    except BaseException as error:
        report['error_type'] = type(error).__name__
        if type(error) is ValueError:
            report['error_code'] = str(error)
    finally:
        remove_auth(root); report['authentication_removed'] = not (root / 'auth').exists()
        private_json(root / 'receipt.json', report)
        fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)
    return report


def main():
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda *_: (_ for _ in ()).throw(InterruptedError('cache_interrupted')))
    try:
        envelope = json.loads(sys.stdin.buffer.read(1024 * 1024))
        result = execute(envelope)
    except BaseException as error:
        result = dict(failed=1,error_type=type(error).__name__,runtime_started=False)
    print(json.dumps(result))
    return bool(result.get('failed'))


if __name__ == '__main__':
    raise SystemExit(main())
