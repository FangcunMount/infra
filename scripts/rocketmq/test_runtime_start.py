import contextlib
import hashlib
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

import runtime_start as target
from start_boundary import BoundaryError, _encoded
from test_cutover_step import private


def target_fixture(root):
    root = Path(root)
    compose = root/'compose.yaml'; env = root/'runtime.env'
    compose_sha = private(compose, b'services: {}\n'); env_sha = private(env, b'')
    value = {'schema': 'm3-runtime-start/v1', 'coordinator_binding_sha256': '1'*64,
             'host': socket.gethostname(), 'project': 'isolated-m3', 'directory': str(root),
             'compose_file': str(compose), 'compose_sha256': compose_sha,
             'environment_file': str(env), 'environment_sha256': env_sha,
             'services': ['fixture'], 'images': {'fixture': 'isolated/image@sha256:'+'2'*64},
             'instances': {'fixture': 1}, 'ai_host': False}
    plan = root/'target.json'; sha = private(plan, _encoded(value))
    return plan, sha, value


def running(plan):
    return ('3'*64+' '+plan['images']['fixture']+' '+plan['project']+' fixture true none\n').encode()


class RuntimeStartTest(unittest.TestCase):
    def test_default_is_offline_and_explicit_attestation_is_not_implicit(self):
        with tempfile.TemporaryDirectory() as root:
            path, sha, _ = target_fixture(root)
            with patch.object(target, 'execute', side_effect=AssertionError('no target execution')):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(target.main(['--plan', str(path), '--reviewed-sha256', sha]), 0)
                self.assertEqual(json.loads(out.getvalue()), {'status': 'offline_target_plan_verified', 'cutover_authorized': False})
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(target.main(['--plan', str(path), '--reviewed-sha256', sha, '--execute']), 1)

    def test_mutable_images_and_changed_inputs_rejected_without_docker(self):
        with tempfile.TemporaryDirectory() as root:
            path, sha, plan = target_fixture(root)
            target.load(path, sha)
            plan['images']['fixture'] = 'isolated/image:latest'
            sha = private(path, _encoded(plan))
            with self.assertRaises(BoundaryError): target.load(path, sha)
            path, sha, plan = target_fixture(root)
            Path(plan['environment_file']).write_bytes(b'changed=1\n')
            with self.assertRaises(BoundaryError): target.load(path, sha)

    def test_exact_service_budget_and_wrong_host_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path, _, plan = target_fixture(root)
            plan['instances']['unknown'] = 1
            with self.assertRaises(BoundaryError): target.load(path, private(path, _encoded(plan)))
            _, _, plan = target_fixture(root)
            with patch.object(target.socket, 'gethostname', return_value='different-target'):
                with patch.object(target, 'deployment_locks', side_effect=AssertionError('no IO')):
                    with self.assertRaises(BoundaryError): target.execute(plan)

    def test_config_cannot_substitute_image_or_build(self):
        with tempfile.TemporaryDirectory() as root:
            _, _, plan = target_fixture(root)
            good = {'services': {'fixture': {'image': plan['images']['fixture']}}}
            target.verify_config(plan, json.dumps(good))
            for value in ([], {}, {'services': {'fixture': {'image': 'other'}}},
                          {'services': {'fixture': {'image': plan['images']['fixture'], 'build': '.'}}}):
                with self.assertRaises(BoundaryError): target.verify_config(plan, json.dumps(value))

    def test_actual_readback_requires_exact_project_image_service_and_count(self):
        with tempfile.TemporaryDirectory() as root:
            _, _, plan = target_fixture(root)
            raw = running(plan); target.verify_running(plan, raw)
            for bad in (b'', raw+raw, raw.replace(b'true', b'false'), raw.replace(b'none', b'unhealthy'),
                        raw.replace(b'isolated-m3', b'another-project'), raw.replace(b'fixture ', b'other ')):
                with self.assertRaises(BoundaryError): target.verify_running(plan, bad)

    def test_start_uses_fixed_socket_no_build_no_pull_no_dependencies_and_no_fallback(self):
        with tempfile.TemporaryDirectory() as root:
            _, _, plan = target_fixture(root)
            config = json.dumps({'services': {'fixture': {'image': plan['images']['fixture']}}}).encode()
            lock = contextlib.nullcontext
            with patch.object(target.platform, 'system', return_value='Linux'), patch.object(target, 'deployment_locks', side_effect=lambda _: lock()):
                with patch.object(target, 'command', side_effect=[config, b'', b'3'*64+b'\n', running(plan)]) as commands:
                    target.execute(plan)
                argv = [call.args[1] for call in commands.call_args_list]
                start = argv[1]
                self.assertEqual(start[:3], [target.DOCKER, '--host', target.SOCKET])
                self.assertEqual(start[start.index('up'):], ['up', '--detach', '--no-deps', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '120', 'fixture'])
                self.assertEqual(len(argv), 4)
                self.assertFalse(any(x in {'stop', 'down', 'build', 'rollback', 'alembic', '--remove-orphans'} for row in argv for x in row))
                with patch.object(target, 'command', side_effect=[config, BoundaryError('controlled start failure')]) as commands:
                    with self.assertRaises(BoundaryError): target.execute(plan)
                self.assertEqual(commands.call_count, 2)  # No old-image restart or DDL.

    def test_rechecks_frozen_files_after_original_host_lock(self):
        with tempfile.TemporaryDirectory() as root:
            _, _, plan = target_fixture(root)
            @contextlib.contextmanager
            def lock(_):
                Path(plan['compose_file']).write_bytes(b'changed-before-lock\n')
                yield
            with patch.object(target.platform, 'system', return_value='Linux'), patch.object(target, 'deployment_locks', side_effect=lock):
                with patch.object(target, 'command', side_effect=AssertionError('no Docker on drift')):
                    with self.assertRaises(BoundaryError): target.execute(plan)


if __name__ == '__main__':
    unittest.main()
