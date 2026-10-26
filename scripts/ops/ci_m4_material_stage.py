"""Required Linux root/Unix proof inside one owned RUNNER_TEMP directory."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

import m4_material_stage as m


def run():
    assert os.geteuid() == 0 and os.environ.get('GITHUB_ACTIONS') == 'true'
    parent = Path(os.environ['RUNNER_TEMP']).resolve()
    assert parent.is_dir() and parent != Path('/')
    cases = []
    with tempfile.TemporaryDirectory(prefix='m4-stage-native-', dir=parent) as temporary:
        owned = Path(temporary).resolve()
        sources = owned / 'sources'
        sources.mkdir(mode=0o700)
        lock = owned / 'deploy.lock'
        lock.write_bytes(b'original lock inode and bytes')
        lock.chmod(0o666)
        lock_before = (lock.stat().st_ino, lock.read_bytes(), lock.stat().st_mode, lock.stat().st_mtime_ns)
        for role, (_, _, gid) in m.ROLES.items():
            targets = ['rocketmq/credentials.json', 'rocketmq/ca.crt', 'rocketmq/routes.json']
            if role == 'qs-api':
                targets.append('rocketmq/mongo-credentials.json')
            if role in ('qs-api', 'ai'):
                targets += [name + '.original.json' for name in ('qs.sign', 'qs.encrypt', 'ai.sign', 'ai.encrypt')]
            files = []
            for target in targets:
                path = sources / (role + '-' + Path(target).name)
                raw = b'original\x00$-bytes-\xff-' + target.encode()
                path.write_bytes(raw)
                path.chmod(0o400)
                files.append(dict(source=str(path), target=target, sha256=m.sha(raw), bytes=len(raw), source_uid=0, source_gid=0, source_mode=0o400))
            plan = dict(schema='m4-material-stage/v1', host=m.ROLES[role][0], role=role, revision='m4-native-stage', source_receipt_sha256='a' * 64, files=files)
            with patch.object(m, 'LOCK', lock), m.deployment_lock():
                first = m.stage(plan, apply=True, root=owned / 'output', source_roots=(sources,))
            destination = owned / 'output' / m.ROLES[role][1] / 'versions' / plan['revision']
            assert first['status'] == 'staged' and first['activated'] is False
            assert all((destination / f['target']).read_bytes() == Path(f['source']).read_bytes() for f in files)
            assert all((destination / f['target']).stat().st_uid == 0 and (destination / f['target']).stat().st_gid == gid for f in files)
            cases.append(role + '-root-stages-exact-bytes-with-original-role-gid')

            def identity(uid):
                def drop():
                    os.setgroups([])
                    os.setgid(uid)
                    os.setuid(uid)
                return drop
            result = subprocess.run(['/bin/sh', '-c', 'test -r rocketmq/credentials.json && ! test -w rocketmq/credentials.json && ! test -w .'], cwd=destination, preexec_fn=identity(gid), capture_output=True, timeout=5)
            assert result.returncode == 0
            cases.append(role + '-ordinary-runtime-reads-but-cannot-write')
            rejected = subprocess.run(['/bin/sh', '-c', 'test -r rocketmq/credentials.json'], cwd=destination, preexec_fn=identity(2001), capture_output=True, timeout=5)
            assert rejected.returncode != 0
            cases.append(role + '-foreign-uid-cannot-read')
            before = {str(p): (p.stat().st_ino, p.stat().st_mtime_ns) for p in destination.rglob('*') if p.is_file()}
            with patch.object(m, 'LOCK', lock), m.deployment_lock():
                second = m.stage(plan, apply=True, root=owned / 'output', source_roots=(sources,))
            assert second['status'] == 'already-staged'
            assert before == {str(p): (p.stat().st_ino, p.stat().st_mtime_ns) for p in destination.rglob('*') if p.is_file()}
            cases.append(role + '-exact-repeat-does-not-rewrite')
        assert lock_before == (lock.stat().st_ino, lock.read_bytes(), lock.stat().st_mode, lock.stat().st_mtime_ns)
        cases.append('shared-lock-inode-content-mode-mtime-preserved')
        with patch.object(m, 'LOCK', lock), m.deployment_lock():
            try:
                with m.deployment_lock():
                    raise AssertionError('busy lock accepted')
            except BlockingIOError:
                pass
        cases.append('busy-shared-lock-refused-without-wait-or-replacement')
    assert not owned.exists()
    cases.append('only-owned-temporary-fixture-cleaned')
    report = dict(schema='m4-material-stage-native/v1', source_sha=os.environ['GITHUB_SHA'], passed=len(cases), failed=0, errors=0, skipped=0, case_ids=cases, production=False, network_used=False, fixture_cleaned=True)
    destination = Path('m4-material-stage-native.json')
    destination.write_text(json.dumps(report, indent=2) + '\n')
    destination.chmod(0o600)
    os.chown(destination, int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID']))
    print(json.dumps({k: v for k, v in report.items() if k != 'case_ids'}))


if __name__ == '__main__':
    run()
