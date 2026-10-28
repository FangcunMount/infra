import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import readable_runtime_start as target
from start_boundary import BoundaryError


def private(path, raw):
    if path.exists():
        path.chmod(0o600)
    path.write_bytes(raw)
    path.chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


def fixture(root, role='iam', phase='closed'):
    host, project, service, count, memory, cpu, uid = target.ROLES[role]
    directory = root / phase / role
    directory.mkdir(parents=True, exist_ok=True)
    asset = directory / 'asset'; asset_hash = private(asset, b'frozen')
    asset.chmod(0o440)
    plan = dict(schema='readable-frozen-runtime/v1', role=role, phase=phase, host=host,
                project=project, directory=str(directory), compose_file=str(directory / 'compose.json'),
                compose_sha256=private(directory / 'compose.json', b'{}'),
                environment_file=str(directory / 'runtime.env'),
                environment_sha256=private(directory / 'runtime.env', b'\n'),
                services=[service], images={service: 'sha256:' + '1' * 64},
                instances={service: count}, ai_host=host == 'serverA',
                locks={target.GLOBAL_LOCK: dict(inode=1, device=1, uid=0, gid=0, mode='0o666')},
                assets={str(asset): asset_hash}, original_ids=[f'{n + 1:064x}' for n in range(count)],
                original_images=['sha256:' + '3' * 64] * count,
                published_reference='registry.example/fixed@sha256:' + '4' * 64,
                image_config_id='sha256:' + '5' * 64, source_sha='6' * 40,
                resources=dict(memory=memory, nano_cpus=cpu, uid=uid))
    if host == 'serverA':
        plan['locks'][target.AI_LOCK] = dict(inode=2, device=1, uid=1002, gid=2001, mode='0o600')
    if phase == 'original':
        plan.update(source_sha=None, image_config_id=None, published_reference=None)
        plan['images'] = {service: plan['original_images'][0]}
    path = directory / 'start.json'
    return path, private(path, json.dumps(plan, indent=2).encode()), plan


def config(plan):
    _, _, service, count, memory, cpu, uid = target.ROLES[plan['role']]
    return json.dumps(dict(services={service: dict(image=plan['images'][service], scale=count,
                           mem_limit=str(memory), cpus=cpu / 1000000000, user=str(uid), environment={})})).encode()


class ReadableRuntimeTest(unittest.TestCase):
    def test_all_roles_and_phases_load_exact_pretty_bytes_and_readonly_assets(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value).resolve()
            for role in target.ROLES:
                phases = ['closed', 'acceptance', 'open', 'original'] + (['old-drain'] if role == 'qs-api' else [])
                for phase in phases:
                    with self.subTest(role=role, phase=phase):
                        path, digest, plan = fixture(root, role, phase)
                        self.assertEqual(target.load(path, digest, root=root), plan)
                        target.verify_budget(plan, config(plan))

    def test_target_scope_budget_identity_and_lock_drift_refused(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value).resolve()
            for key, bad in [('host', 'serverB'), ('project', 'other'), ('phase', 'old-drain'),
                             ('instances', {'iam-apiserver': True}), ('images', {'iam-apiserver': 'latest'}),
                             ('resources', dict(memory=1, nano_cpus=1, uid=0)), ('source_sha', 'main'),
                             ('locks', {}), ('assets', {}), ('original_ids', [])]:
                with self.subTest(key=key):
                    path, _, plan = fixture(root)
                    plan[key] = bad
                    with self.assertRaises(BoundaryError):
                        target.load(path, private(path, json.dumps(plan).encode()), root=root)

    def test_changed_input_symlink_world_write_or_duplicate_fields_fail(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value).resolve()
            path, digest, plan = fixture(root)
            path.write_bytes(path.read_bytes() + b' ')
            with self.assertRaises(BoundaryError): target.load(path, digest, root=root)
            path, digest, plan = fixture(root)
            asset = Path(next(iter(plan['assets'])))
            asset.chmod(0o666)
            with self.assertRaises(BoundaryError): target.load(path, digest, root=root)
            asset.chmod(0o600); asset.unlink(); asset.symlink_to(path)
            with self.assertRaises(BoundaryError): target.load(path, digest, root=root)
            path, digest, _ = fixture(root, 'ai')
            raw = path.read_bytes().replace(b'"schema":', b'"schema": "duplicate", "schema":', 1)
            with self.assertRaises(BoundaryError): target.load(path, private(path, raw), root=root)

    def test_config_must_have_one_service_exact_budget_and_no_retired_env(self):
        with tempfile.TemporaryDirectory() as value:
            _, _, plan = fixture(Path(value).resolve())
            for key, bad in [('mem_limit', '1'), ('cpus', 4), ('user', '0'), ('scale', 2),
                             ('environment', {'IAM_NSQ_ENABLED': 'true'})]:
                v = json.loads(config(plan)); v['services']['iam-apiserver'][key] = bad
                with self.assertRaises(BoundaryError): target.verify_budget(plan, json.dumps(v))
            v = json.loads(config(plan)); v['services']['other'] = {}
            with self.assertRaises(BoundaryError): target.verify_budget(plan, json.dumps(v))

    def test_only_exact_existing_external_assets_are_borrowed_and_never_modified(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value).resolve() / 'release'; root.mkdir()
            path, _, plan = fixture(root)
            external = root.parent / 'existing-tls.key'
            expected = private(external, b'original-tls-bytes')
            external.chmod(0o440)
            plan['assets'][str(external)] = expected
            digest = private(path, json.dumps(plan).encode())
            with self.assertRaises(BoundaryError): target.load(path, digest, root=root)
            with patch.object(target, 'EXTERNAL_ASSETS', {external}):
                target.load(path, digest, root=root)
                self.assertEqual(external.read_bytes(), b'original-tls-bytes')
                self.assertEqual(external.stat().st_mode & 0o777, 0o440)
                external.chmod(0o666)
                with self.assertRaises(BoundaryError): target.load(path, digest, root=root)

    def test_cli_offline_and_execute_attestation_never_grants_approval(self):
        with patch.object(target, 'load', return_value={}), patch.object(target, 'execute') as start:
            args = ['--plan', '/unused', '--reviewed-sha256', '1' * 64]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(target.main(args), 0)
                self.assertEqual(target.main(args + ['--execute']), 1)
                self.assertEqual(target.main(args + ['--coordinated-start-already-issued']), 1)
            start.assert_not_called()

    def test_drift_under_lock_or_wrong_host_prevents_any_docker_command(self):
        with tempfile.TemporaryDirectory() as value:
            path, digest, plan = fixture(Path(value).resolve())
            with patch.object(target.socket, 'gethostname', return_value='serverD'), patch.object(target, 'command') as run:
                with self.assertRaises(BoundaryError): target.execute(plan, path, digest)
                run.assert_not_called()
            with patch.object(target.platform, 'system', return_value='Linux'), patch.object(target.socket, 'gethostname', return_value='serverA'), patch.object(target, 'deployment_locks', return_value=contextlib.nullcontext()), patch.object(target, 'load', side_effect=BoundaryError('changed input')), patch.object(target, 'command') as run:
                with self.assertRaises(BoundaryError): target.execute(plan, path, digest)
                run.assert_not_called()

    def test_start_never_pulls_builds_scales_up_or_falls_back_and_rejects_actual_oom(self):
        with tempfile.TemporaryDirectory() as value:
            path, digest, plan = fixture(Path(value).resolve())
            record = dict(Id='a' * 64, Image=plan['images']['iam-apiserver'],
                          Config=dict(Image=plan['images']['iam-apiserver'], Labels={
                              'com.docker.compose.project': plan['project'], 'com.docker.compose.service': 'iam-apiserver'}),
                          State=dict(Running=True, OOMKilled=False, Health=dict(Status='healthy')),
                          HostConfig=dict(Memory=plan['resources']['memory'], NanoCpus=plan['resources']['nano_cpus']))
            for mutation in (None, 'oom', 'image', 'cpu'):
                row = copy.deepcopy(record)
                if mutation == 'oom': row['State']['OOMKilled'] = True
                if mutation == 'image': row['Image'] = 'sha256:' + '9' * 64
                if mutation == 'cpu': row['HostConfig']['NanoCpus'] *= 2
                with patch.object(target.platform, 'system', return_value='Linux'), patch.object(target.socket, 'gethostname', return_value='serverA'), patch.object(target, 'deployment_locks', return_value=contextlib.nullcontext()), patch.object(target, 'load', return_value=plan), patch.object(target, 'command', side_effect=[config(plan), b'', b'a' * 64, json.dumps([row]).encode()]) as run:
                    if mutation:
                        with self.assertRaises(BoundaryError): target.execute(plan, path, digest)
                    else: target.execute(plan, path, digest)
                    argv = run.call_args_list[1].args[1]
                    self.assertEqual(argv[argv.index('up'):], ['up', '--detach', '--no-deps', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '90', '--scale', 'iam-apiserver=1', 'iam-apiserver'])
                    self.assertEqual(run.call_count, 4)


if __name__ == '__main__':
    unittest.main()
