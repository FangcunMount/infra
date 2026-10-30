"""Permission-boundary tests; no real accounts or sudoers are modified."""

import importlib.util
import json
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location('servera_access', Path(__file__).with_name('servera-access.py'))
access = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(access)


class AccessTest(unittest.TestCase):
    def test_tracked_policy_has_exact_reviewed_commands(self):
        raw = access.policy_bytes()
        self.assertEqual(raw.count(b'NOPASSWD:'), 3)
        self.assertNotIn(b'*', raw)
        self.assertNotIn(b'ALL=(ALL)', raw)

    def test_policy_tampering_is_refused(self):
        raw = access.policy_bytes()
        for replacement in (raw + b'deploy ALL=(root) NOPASSWD: /usr/bin/python3 *\n',
                            raw.replace(b'--expect-role iam', b'--expect-role worker'),
                            raw.replace(b'NOPASSWD:', b'SETENV: NOPASSWD:')):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'policy'
                path.write_bytes(replacement)
                with patch.object(access, 'POLICY', path), self.assertRaises(RuntimeError):
                    access.policy_bytes()

    def test_secure_path_refuses_symlink_writable_or_nonroot_tool(self):
        safe = SimpleNamespace(st_uid=0, st_gid=0, st_mode=stat.S_IFDIR | 0o755, st_nlink=1)
        path = Path('/opt/tools/reviewed.py')
        for mode, uid, gid, links in ((stat.S_IFLNK | 0o555, 0, 0, 1),
                                      (stat.S_IFREG | 0o575, 0, 0, 1),
                                      (stat.S_IFREG | 0o555, 1002, 0, 1),
                                      (stat.S_IFREG | 0o555, 0, 2001, 1),
                                      (stat.S_IFREG | 0o555, 0, 0, 2)):
            info = SimpleNamespace(st_uid=uid, st_gid=gid, st_mode=mode, st_nlink=links)
            with patch.object(Path, 'lstat', side_effect=[safe] * 3 + [info]):
                with self.assertRaises(RuntimeError):
                    access.secure_path(path, mode=0o555)
        writable = SimpleNamespace(st_uid=0, st_mode=stat.S_IFDIR | 0o777)
        with patch.object(Path, 'lstat', return_value=writable), self.assertRaises(RuntimeError):
            access.secure_path(path, mode=0o555)

    def test_wrong_host_is_refused_before_account_or_command_access(self):
        with patch.object(access.os, 'geteuid', return_value=0), \
                patch.object(access.socket, 'gethostname', return_value='serverD'), \
                patch.object(access, 'accounts') as accounts, \
                patch.object(access, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'wrong_host'):
                access.preflight()
            accounts.assert_not_called()
            run.assert_not_called()

    def test_material_report_must_be_readonly_and_match_identity(self):
        report = dict(status='verified', read_only=True, activated=False, host='serverA',
                      role='iam', revision=access.REVISION,
                      material_root='/var/lib/fangcun-m4-materials', receipt_sha256='a' * 64)
        access.validate_report(json.dumps(report), 'iam')
        for key, value in (('activated', True), ('read_only', False), ('role', 'ai'),
                           ('revision', 'm4-other-v1'), ('receipt_sha256', 'invalid')):
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                access.validate_report(json.dumps(dict(report, **{key: value})), 'iam')

    def test_apply_does_not_overwrite_unknown_existing_policy_or_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / access.NAME
            original = b'# maintained by another operator\n'
            target.write_bytes(original)
            with patch.object(access, 'DESTINATION', target), \
                    patch.object(access, 'secure_path'), patch.object(access, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'managed_policy_drift'):
                    access.install_policy(access.policy_bytes())
                self.assertEqual(target.read_bytes(), original)
                run.assert_not_called()
            target.unlink()
            target.symlink_to(Path(directory) / 'missing')
            with patch.object(access, 'DESTINATION', target), \
                    patch.object(access, 'secure_path', side_effect=RuntimeError('unsafe_file')):
                with self.assertRaises(RuntimeError):
                    access.install_policy(access.policy_bytes())
                self.assertTrue(target.is_symlink())

    def test_success_is_idempotent_and_preserves_other_policies(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / access.NAME
            other = Path(directory) / 'deploy-cicd'
            other.write_bytes(b'preserved')
            with patch.object(access, 'DESTINATION', target), \
                    patch.object(access, 'secure_path'), patch.object(access.os, 'fchown'), \
                    patch.object(access, 'run'), \
                    patch.object(access, 'audit', return_value={'status': 'verified'}):
                self.assertTrue(access.install_policy(access.policy_bytes()))
                self.assertFalse(access.install_policy(access.policy_bytes()))
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o440)
                self.assertEqual(target.read_bytes(), access.policy_bytes())
                self.assertEqual(other.read_bytes(), b'preserved')
                self.assertEqual(len(list(Path(directory).iterdir())), 2)

    def test_failed_syntax_full_validation_or_behavior_rolls_back(self):
        for stage in ('syntax', 'full', 'behavior'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / access.NAME
                other = Path(directory) / 'existing'
                other.write_bytes(b'unchanged')

                def run(args):
                    if stage == 'syntax' and '-cf' in args:
                        raise RuntimeError('syntax_failed')
                    if stage == 'full' and '-c' in args and target.exists():
                        raise RuntimeError('full_validation_failed')

                with patch.object(access, 'DESTINATION', target), \
                        patch.object(access.os, 'fchown'), patch.object(access, 'run', side_effect=run), \
                        patch.object(access, 'audit', return_value={'status': 'missing_policy'}):
                    with self.assertRaises(RuntimeError):
                        access.install_policy(access.policy_bytes())
                self.assertFalse(target.exists())
                self.assertEqual(other.read_bytes(), b'unchanged')
                self.assertEqual(list(Path(directory).iterdir()), [other])

    def test_negative_probes_only_list_permissions_never_execute(self):
        commands = access.negative_commands()
        self.assertGreaterEqual(len(commands), 8)
        for command in commands:
            self.assertNotIn(command, [access.command(role) for role in access.ROLES])
            with patch.object(access, 'run', return_value=SimpleNamespace(returncode=1)) as run:
                self.assertFalse(access.allowed(command))
                self.assertEqual(run.call_args.args[0][:8],
                                 ['/usr/sbin/runuser', '-u', 'deploy', '--', '/usr/bin/sudo',
                                  '-n', '-l', '--'])


if __name__ == '__main__':
    unittest.main()
