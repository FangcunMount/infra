import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import stat
import unittest
from unittest.mock import patch

import m4_runtime_start as target
import runtime_start as original
from start_boundary import BoundaryError, _encoded
from test_cutover_step import private
from test_runtime_start import target_fixture


def fixture(root, role='iam'):
    root = Path(root).resolve(); directory = root / role; directory.mkdir(exist_ok=True)
    host, project, service, count, image, *_ = target.ROLES[role]
    assets = directory / 'asset.json'; asset_hash = private(assets, b'owned-frozen-input')
    plan = dict(schema='m4-c08-runtime-start/v1', coordinator_binding_sha256='1' * 64,
                role=role, host=host, project=project, directory=str(directory),
                compose_file=str(directory / 'compose.json'),
                compose_sha256=private(directory / 'compose.json', b'{"services":{}}'),
                environment_file=str(directory / 'runtime.env'),
                environment_sha256=private(directory / 'runtime.env', b''),
                services=[service], images={service: 'sha256:' + image}, instances={service: count},
                ai_host=host == 'serverA', assets={str(assets): asset_hash},
                locks={target.GLOBAL_LOCK: dict(inode=1, device=1, uid=0, gid=0, mode='0o666')})
    if host == 'serverA':
        plan['locks'][target.AI_LOCK] = dict(inode=2, device=1, uid=1002, gid=2001, mode='0o600')
    path = directory / 'plan.json'; digest = private(path, _encoded(plan))
    return path, digest, plan


def config(plan):
    *_, memory, cpus, uid = target.ROLES[plan['role']]
    name = plan['services'][0]
    return dict(services={name: dict(image=plan['images'][name], scale=plan['instances'][name],
                                   user=str(uid), cpus=cpus, mem_limit=str(memory), environment={})})


class M4RuntimeStartTest(unittest.TestCase):
    def test_five_fixed_roles_load_and_decode_without_host_or_docker(self):
        with tempfile.TemporaryDirectory() as root:
            for role in target.ROLES:
                with self.subTest(role=role):
                    path, digest, plan = fixture(root, role)
                    self.assertEqual(target.load(path, digest, root=Path(root).resolve()), plan)
                    target.verify_budget(plan, json.dumps(config(plan)))

    def test_target_image_project_replica_and_lock_scope_cannot_be_substituted(self):
        with tempfile.TemporaryDirectory() as root:
            for field, bad in [('host', 'serverB'), ('project', 'other'), ('ai_host', False),
                               ('images', {'iam-apiserver': 'sha256:' + '0' * 64}),
                               ('instances', {'iam-apiserver': True}), ('services', ['other'])]:
                with self.subTest(field=field):
                    path, _, plan = fixture(root); plan[field] = bad
                    with self.assertRaises(BoundaryError):
                        target.load(path, private(path, _encoded(plan)), root=Path(root).resolve())

    def test_changed_asset_symlink_and_out_of_scope_material_fail_before_start(self):
        with tempfile.TemporaryDirectory() as root:
            path, digest, plan = fixture(root)
            asset = Path(next(iter(plan['assets']))); asset.write_bytes(b'drift')
            with self.assertRaises(BoundaryError): target.load(path, digest, root=Path(root).resolve())
            path, _, plan = fixture(root)
            link = Path(root) / 'link'; link.symlink_to(asset)
            plan['assets'] = {str(link): hashlib.sha256(asset.read_bytes()).hexdigest()}
            with self.assertRaises(BoundaryError): target.load(path, private(path, _encoded(plan)), root=Path(root).resolve())

    def test_resource_retired_env_user_and_scale_drift_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            _, _, plan = fixture(root); name = plan['services'][0]
            for key, bad in [('mem_limit', '1'), ('cpus', 8), ('user', '0'), ('scale', 2),
                             ('environment', {'IAM_APISERVER_NSQ_ENABLED': 'true'})]:
                with self.subTest(key=key):
                    value = config(plan); value['services'][name][key] = bad
                    with self.assertRaises(BoundaryError): target.verify_budget(plan, json.dumps(value))

    def test_default_cli_does_not_start_and_attestation_does_not_grant_authority(self):
        with tempfile.TemporaryDirectory() as root:
            path, digest, plan = fixture(root)
            args = ['--plan', str(path), '--reviewed-sha256', digest]
            with patch.object(target, 'load', return_value=plan), patch.object(target, 'execute') as start:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(target.main(args), 0)
                    self.assertEqual(target.main(args + ['--execute']), 1)
                    self.assertEqual(target.main(args + ['--coordinated-start-already-issued']), 1)
                start.assert_not_called()

    def test_start_uses_local_engine_no_pull_build_migration_or_fallback(self):
        with tempfile.TemporaryDirectory() as root:
            _, _, plan = fixture(root); name = plan['services'][0]
            running = ('a' * 64 + ' ' + plan['images'][name] + ' ' + plan['project'] + ' ' + name + ' true healthy\n').encode()
            with patch.object(target.platform, 'system', return_value='Linux'), patch.object(target.socket, 'gethostname', return_value='serverA'), patch.object(target, 'deployment_locks', return_value=contextlib.nullcontext()):
                with patch.object(target, 'command', side_effect=[json.dumps(config(plan)).encode(), b'', b'a' * 64, running]) as run:
                    target.execute(plan)
                    argv = [c.args[1] for c in run.call_args_list]; start = argv[1]
                    self.assertEqual(start[start.index('up'):], ['up', '--detach', '--no-deps', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', '60', '--scale', name + '=1', name])
                    self.assertFalse(any(x in {'stop', 'down', 'pull', 'build', 'migrate', 'rollback'} for row in argv for x in row))
                with patch.object(target, 'command', side_effect=[json.dumps(config(plan)).encode(), BoundaryError('controlled failure')]) as run:
                    with self.assertRaises(BoundaryError): target.execute(plan)
                    self.assertEqual(run.call_count, 2)

    def test_wrong_host_and_material_change_under_lock_fail_before_docker(self):
        with tempfile.TemporaryDirectory() as root:
            _, _, plan = fixture(root)
            with patch.object(target.platform, 'system', return_value='Linux'), patch.object(target.socket, 'gethostname', return_value='serverD'), patch.object(target, 'deployment_locks') as lock:
                with self.assertRaises(BoundaryError): target.execute(plan)
                lock.assert_not_called()
            @contextlib.contextmanager
            def lock(_):
                Path(next(iter(plan['assets']))).write_bytes(b'changed-under-lock')
                yield
            with patch.object(target.platform, 'system', return_value='Linux'), patch.object(target.socket, 'gethostname', return_value='serverA'), patch.object(target, 'deployment_locks', side_effect=lock), patch.object(target, 'command') as run:
                with self.assertRaises(BoundaryError): target.execute(plan)
                run.assert_not_called()

    def test_original_m3_registry_digest_guard_still_rejects_engine_only_id(self):
        with tempfile.TemporaryDirectory() as root:
            path, _, plan = target_fixture(root)
            plan['images']['fixture'] = 'sha256:' + '2' * 64
            with self.assertRaises(BoundaryError): original.load(path, private(path, _encoded(plan)))

    def test_original_lock_metadata_is_required_and_wrong_owner_or_set_refused(self):
        with tempfile.TemporaryDirectory() as root:
            for mutation in ('missing', 'owner', 'mode'):
                path, _, plan = fixture(root)
                if mutation == 'missing': del plan['locks'][target.AI_LOCK]
                if mutation == 'owner': plan['locks'][target.AI_LOCK]['uid'] = 0
                if mutation == 'mode': plan['locks'][target.AI_LOCK]['mode'] = '0o666'
                with self.assertRaises(BoundaryError):
                    target.load(path, private(path, _encoded(plan)), root=Path(root).resolve())

    def test_real_flock_conflict_and_inode_drift_preserve_original_lock(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root).resolve() / 'owned.lock'; private(path, b'')
            s = path.stat(); identity = dict(inode=s.st_ino, device=s.st_dev, uid=s.st_uid,
                                            gid=s.st_gid, mode=oct(stat.S_IMODE(s.st_mode)))
            plan = dict(ai_host=False, locks={str(path): identity})
            with patch.object(target, 'GLOBAL_LOCK', str(path)):
                with target.deployment_locks(plan):
                    with self.assertRaises(BlockingIOError):
                        with target.deployment_locks(plan): self.fail('busy lock acquired')
                self.assertEqual(path.stat().st_ino, s.st_ino)
                plan['locks'][str(path)]['inode'] += 1
                with self.assertRaises(BoundaryError):
                    with target.deployment_locks(plan): self.fail('changed lock acquired')


if __name__ == '__main__':
    unittest.main()
