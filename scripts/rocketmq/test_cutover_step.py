import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import shlex
import tempfile
import unittest
from unittest.mock import patch

import cutover_step as step
from start_boundary import Boundary, BoundaryError
from test_start_boundary import fixture


def private(path, raw):
    path.write_bytes(raw); path.chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


def planned(root, directory, digest, script=b'exit 0\n', kind='runtime-start'):
    source = Path(root)/'reviewed.sh'
    source_digest = private(source, script)
    value = {'schema': 'm3-cutover-step/v1', 'directory': str(directory),
             'binding_sha256': digest, 'host': socket.gethostname(), 'step': 'isolated-1',
             'kind': kind, 'script': str(source), 'script_sha256': source_digest,
             'cwd': root, 'timeout_seconds': 1}
    path = Path(root)/'step.json'
    sha = private(path, step._encoded(value))
    return path, sha, value


class CutoverStepTest(unittest.TestCase):
    def test_issued_child_receives_actual_plan_context_without_self_hash_cycle(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root)
            script = b'printf "%s\\n%s\\n%s\\n%s\\n" "$M3_COORDINATOR_DIRECTORY" "$M3_COORDINATOR_BINDING_SHA256" "$M3_COORDINATOR_STEP" "$M3_COORDINATOR_STEP_PLAN_SHA256"\n'
            path, sha, _ = planned(root, directory, digest, script)
            plan, raw = step.load_step(path, sha)
            with patch.object(step.platform, 'system', return_value='Linux'):
                step.execute(plan, raw, sha)
            logs = list(directory.glob('command-*.log'))
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0].read_text().splitlines(), [str(directory), digest, plan['step'], sha])
            self.assertNotIn(sha.encode(), script)
            self.assertTrue((directory/'first-runtime-start.json').exists())

    def test_default_only_verifies_without_host_locks_or_command(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root)
            path, sha, _ = planned(root, directory, digest)
            with patch.object(step, 'execute', side_effect=AssertionError('must stay offline')):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(step.main(['--plan', str(path), '--reviewed-sha256', sha]), 0)
                self.assertEqual(json.loads(output.getvalue()),
                                 {'status': 'offline_plan_verified', 'cutover_authorized': False})
            self.assertFalse((directory/'first-runtime-start.json').exists())

    def test_script_and_plan_digests_private_modes_and_duplicates_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root)
            path, sha, plan = planned(root, directory, digest)
            with self.assertRaises(BoundaryError): step.load_step(path, '0'*64)
            Path(plan['script']).write_bytes(b'exit 1\n')
            with self.assertRaises(BoundaryError): step.load_step(path, sha)
            path.chmod(0o644)
            with self.assertRaises(BoundaryError): step.load_step(path, sha)
            raw = b'{"schema":1,"schema":2}'
            sha = private(path, raw)
            with self.assertRaises(BoundaryError): step.load_step(path, sha)

    def test_fixed_host_checked_before_locks_and_first_start(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root)
            _, sha, plan = planned(root, directory, digest)
            with patch.object(step.socket, 'gethostname', return_value='wrong-host'):
                with patch.object(step, 'deployment_locks', side_effect=AssertionError('no lock IO')):
                    with self.assertRaises(BoundaryError): step.execute(plan, b'exit 0', sha)
            self.assertFalse((directory/'first-runtime-start.json').exists())

    def test_reuses_original_lock_inode_and_refuses_missing_or_symlink(self):
        with tempfile.TemporaryDirectory() as root:
            lock = Path(root)/'deploy.lock'; lock.touch()
            inode = lock.stat().st_ino
            with patch.object(step, 'GLOBAL_LOCK', lock):
                with step.deployment_locks(False):
                    with self.assertRaises(BlockingIOError):
                        with step.deployment_locks(False): pass
                self.assertEqual(lock.stat().st_ino, inode)
                lock.unlink()
                with self.assertRaises(FileNotFoundError):
                    with step.deployment_locks(False): pass
                target = Path(root)/'target'; target.touch(); lock.symlink_to(target)
                with self.assertRaises(OSError):
                    with step.deployment_locks(False): pass

    def test_actual_command_snapshot_private_output_and_irreversible_failure(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root)
            path, sha, _ = planned(root, directory, digest, b'printf "private-body-marker"; exit 7\n')
            plan, script = step.load_step(path, sha)
            # The already-reviewed snapshot, not a later path replacement, executes.
            Path(plan['script']).write_bytes(b'exit 0\n')
            lock = Path(root)/'deploy.lock'; lock.touch()
            output = io.StringIO()
            with patch.object(step, 'GLOBAL_LOCK', lock), patch.object(step.platform, 'system', return_value='Linux'):
                with contextlib.redirect_stdout(output):
                    with self.assertRaises(BoundaryError): step.execute(plan, script, sha)
            self.assertEqual(output.getvalue(), '')
            logs = list(directory.glob('command-*.log')); self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0].stat().st_mode & 0o777, 0o600)
            self.assertEqual(logs[0].read_bytes(), b'private-body-marker')
            with Boundary(directory, digest) as operation:
                self.assertEqual(operation.status()['phase'], 'runtime_start_failed')
                with self.assertRaises(BoundaryError): operation.restore_before_start('restore', lambda: None)

    def test_timeout_keeps_boundary_and_drains_actual_command(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root)
            _, _, plan = planned(root, directory, digest)
            # exec makes the owned shell PID the sleeper; no detached fixture process.
            with Boundary(directory, digest) as operation:
                with self.assertRaises(step.subprocess.TimeoutExpired):
                    operation.start('isolated-timeout', lambda: step.run_script(b'exec sleep 30\n', plan, operation))
                self.assertEqual(operation.status()['phase'], 'runtime_start_failed')
                self.assertFalse(operation.status()['old_data_restore_eligible'])

    def test_success_is_command_return_only_and_repair_approval_is_separate(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root)
            path, sha, plan = planned(root, directory, digest)
            lock = Path(root)/'deploy.lock'; lock.touch()
            with patch.object(step, 'GLOBAL_LOCK', lock), patch.object(step.platform, 'system', return_value='Linux'):
                status = step.execute(plan, b'exit 0\n', sha)
                self.assertFalse(status['cutover_authorized'])
                self.assertEqual(status['phase'], 'runtime_start_returned')
                plan['kind'] = 'pre-start-restore'
                restore_sha = hashlib.sha256(step._encoded(plan)).hexdigest()
                with self.assertRaises(BoundaryError): step.execute(plan, b'exit 0\n', restore_sha)
                plan['kind'] = 'forward-repair'
                repair_sha = hashlib.sha256(step._encoded(plan)).hexdigest()
                step.execute(plan, b'exit 0\n', repair_sha)
            self.assertTrue((directory/('repair-approval-'+repair_sha+'.json')).is_file())

    def test_distinct_reviewed_scope_commands_share_original_restore_boundary(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root)
            with patch.object(step.platform, 'system', return_value='Linux'):
                for scope in ('iam', 'qs', 'ai'):
                    done = Path(root)/(scope+'-restored')
                    source = ('/usr/bin/touch '+shlex.quote(str(done))+'\n').encode()
                    _, _, plan = planned(root, directory, digest, source, kind='pre-start-restore')
                    plan['step'] = 'restore-'+scope
                    sha = hashlib.sha256(step._encoded(plan)).hexdigest()
                    status = step.execute(plan, source, sha)
                    self.assertTrue(done.exists())
                    self.assertEqual(status['phase'], 'restore_returned')
                    self.assertFalse(status['cutover_authorized'])
                    with Boundary(directory, digest) as operation:
                        with self.assertRaises(BoundaryError): operation.start('unsafe-runtime', lambda: None)
            self.assertEqual(len(list(directory.glob('reviewed-step-*.json'))), 3)

    def test_unavailable_never_prints_plan_script_or_exception(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'bad.json'; sha = private(path, b'{"secret":"private-body-marker"}')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(step.main(['--plan', str(path), '--reviewed-sha256', sha]), 1)
            self.assertEqual(json.loads(output.getvalue()), {'status': 'unavailable', 'cutover_authorized': False})


if __name__ == '__main__':
    unittest.main()
