"""Protect original assets across immutable material preparation and failures."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import m4_material_stage as m


class MaterialStageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.sources = self.directory / 'sources'
        self.sources.mkdir(mode=0o700)
        self.root = self.directory / 'output'
        self.uid, self.gid = os.getuid(), os.getgid()
        self.plan = self.make_plan('iam')

    def make_plan(self, role):
        targets = ['rocketmq/credentials.json', 'rocketmq/ca.crt', 'rocketmq/routes.json']
        if role == 'qs-api':
            targets.append('rocketmq/mongo-credentials.json')
        if role in ('qs-api', 'ai'):
            targets += [name + '.original.json' for name in ('qs.sign', 'qs.encrypt', 'ai.sign', 'ai.encrypt')]
        files = []
        for target in targets:
            source = self.sources / (role + '-' + Path(target).name)
            raw = ('original frozen bytes ' + role + target).encode()
            source.write_bytes(raw)
            source.chmod(0o600)
            info = source.stat()
            files.append(dict(source=str(source), target=target, sha256=m.sha(raw), bytes=len(raw), source_uid=info.st_uid, source_gid=info.st_gid, source_mode=0o600))
        return dict(schema='m4-material-stage/v1', host=m.ROLES[role][0], role=role,
                    revision='m4-c06-test-1', source_receipt_sha256='a' * 64, files=files)

    def stage(self, plan=None, *, apply=True):
        return m.stage(self.plan if plan is None else plan, apply=apply, root=self.root,
                       uid=self.uid, gid=self.gid, source_roots=(self.sources,))

    def destination(self, plan=None):
        plan = self.plan if plan is None else plan
        return self.root / m.ROLES[plan['role']][1] / 'versions' / plan['revision']

    def test_preview_has_no_filesystem_effect(self):
        result = self.stage(apply=False)
        self.assertEqual(result['status'], 'ready')
        self.assertFalse(result['activated'])
        self.assertFalse(self.root.exists())

    def test_four_roles_copy_first_bytes_with_fixed_modes_and_no_pointer(self):
        for role in m.ROLES:
            with self.subTest(role=role):
                plan = self.make_plan(role)
                result = self.stage(plan)
                destination = self.destination(plan)
                self.assertEqual(result['status'], 'staged')
                self.assertFalse(result['activated'])
                self.assertFalse((destination.parent.parent / 'current.json').exists())
                for row in plan['files']:
                    copied = destination / row['target']
                    self.assertEqual(copied.read_bytes(), Path(row['source']).read_bytes())
                    self.assertEqual(copied.stat().st_mode & 0o777, 0o440)
                self.assertEqual(destination.stat().st_mode & 0o777, 0o750)

    def test_existing_pointer_source_bytes_and_permissions_are_unchanged(self):
        base = self.destination().parent.parent
        base.mkdir(parents=True)
        pointer = base / 'current.json'
        pointer.write_bytes(b'old active binding remains')
        originals = [pointer] + [Path(row['source']) for row in self.plan['files']]
        before = {p: (p.read_bytes(), p.stat().st_mode, p.stat().st_ino, p.stat().st_mtime_ns, p.stat().st_ctime_ns) for p in originals}
        self.stage()
        for p, expected in before.items():
            self.assertEqual((p.read_bytes(), p.stat().st_mode, p.stat().st_ino, p.stat().st_mtime_ns, p.stat().st_ctime_ns), expected)

    def test_identical_retry_does_not_rewrite_published_files(self):
        self.stage()
        paths = [p for p in self.destination().rglob('*') if p.is_file()]
        before = {p: (p.stat().st_ino, p.stat().st_mtime_ns) for p in paths}
        self.assertEqual(self.stage()['status'], 'already-staged')
        self.assertEqual(before, {p: (p.stat().st_ino, p.stat().st_mtime_ns) for p in paths})

    def verify(self, plan=None, **changes):
        plan = self.plan if plan is None else plan
        values = dict(role=plan['role'], revision=plan['revision'], root=self.root,
                      uid=self.uid, gid=self.gid)
        values.update(changes)
        return m.verify_staged(plan, **values)

    def test_readonly_verification_survives_removal_of_retained_source_files(self):
        self.stage()
        paths = [p for p in self.destination().rglob('*') if p.is_file()]
        before = {p: (p.stat().st_ino, p.stat().st_mtime_ns, p.stat().st_ctime_ns, p.read_bytes()) for p in paths}
        for row in self.plan['files']:
            Path(row['source']).unlink()
        with patch.object(m, 'deployment_lock') as lock:
            result = self.verify()
        lock.assert_not_called()
        self.assertEqual(result['status'], 'verified')
        self.assertTrue(result['read_only'])
        self.assertFalse(result['activated'])
        self.assertEqual(before, {p: (p.stat().st_ino, p.stat().st_mtime_ns, p.stat().st_ctime_ns, p.read_bytes()) for p in paths})

    def test_readonly_missing_target_or_wrong_identity_never_creates_anything(self):
        with self.assertRaises((m.Refused,OSError)):
            self.verify()
        self.assertFalse(self.root.exists())
        self.stage()
        for changes in (dict(role='worker'),dict(revision='m4-wrong'),dict(role='unknown')):
            with self.subTest(changes=changes),self.assertRaises(m.Refused):
                self.verify(**changes)
        self.assertEqual(sorted(p.name for p in self.destination().parent.iterdir()), [self.plan['revision']])

    def test_readonly_verification_refuses_bad_files_modes_and_symlinks(self):
        self.stage()
        path=self.destination()/'rocketmq/credentials.json'
        raw=path.read_bytes()
        for defect in ('missing','bytes','world-readable','symlink'):
            with self.subTest(defect=defect):
                path.chmod(0o600)
                if defect=='missing':path.unlink()
                elif defect=='bytes':path.write_bytes(raw+b'bad');path.chmod(0o440)
                elif defect=='world-readable':path.chmod(0o444)
                else:path.unlink();path.symlink_to(Path(self.plan['files'][0]['source']))
                with self.assertRaises((m.Refused,OSError)):
                    self.verify()
                if path.exists() or path.is_symlink():path.unlink()
                path.write_bytes(raw);path.chmod(0o440)
        self.assertEqual(self.verify()['status'],'verified')

    def test_readonly_verification_requires_unchanged_receipt_and_safe_ancestors(self):
        self.stage()
        receipt=self.destination()/m.RECEIPT
        raw=receipt.read_bytes();receipt.chmod(0o600)
        changed=json.loads(raw);changed['role']='worker';receipt.write_bytes(m.encoded(changed));receipt.chmod(0o440)
        with self.assertRaises(m.Refused):self.verify()
        receipt.chmod(0o600);receipt.write_bytes(raw);receipt.chmod(0o440)
        self.destination().parent.chmod(0o770)
        with self.assertRaises(m.Refused):self.verify()
        self.destination().parent.chmod(0o750)
        self.assertEqual(self.verify()['status'],'verified')

    def install_plan(self, plan=None):
        plan=self.plan if plan is None else plan
        self.plans=self.directory/'plans';self.plans.mkdir(mode=0o700,exist_ok=True)
        raw=(json.dumps(plan,indent=2)+'\n').encode()
        path=self.plans/(m.sha(raw)+'.json');path.write_bytes(raw);path.chmod(0o600)
        return path

    def discover(self, **changes):
        args=dict(role=self.plan['role'],revision=self.plan['revision'],host=self.plan['host'],
                  root=self.root,plan_root=self.plans,uid=self.uid,gid=self.gid)
        args.update(changes)
        return m.verify_installed(**args)

    def test_installed_verification_resolves_formatted_original_plan_without_sources(self):
        self.stage();plan_path=self.install_plan()
        self.assertNotEqual(plan_path.stem,m.sha(m.encoded(self.plan)))
        for row in self.plan['files']:Path(row['source']).unlink()
        with patch.object(m,'deployment_lock') as lock:
            self.assertEqual(self.discover()['status'],'verified')
        lock.assert_not_called()

    def test_installed_verification_refuses_wrong_identity_and_missing_plan(self):
        self.stage();path=self.install_plan()
        for changes in (dict(host='serverD'),dict(role='worker'),dict(revision='m4-wrong')):
            with self.subTest(changes=changes),self.assertRaises((m.Refused,OSError)):
                self.discover(**changes)
        path.unlink()
        with self.assertRaises(m.Refused):self.discover()

    def test_installed_verification_requires_root_plan_mode_hash_and_non_symlink(self):
        self.stage();path=self.install_plan();original=path.read_bytes()
        for defect in ('mode','bytes','symlink'):
            if defect=='mode':path.chmod(0o640)
            elif defect=='bytes':path.write_bytes(original+b' ')
            else:path.unlink();path.symlink_to(Path(self.plan['files'][0]['source']))
            with self.subTest(defect=defect),self.assertRaises((m.Refused,OSError)):self.discover()
            if path.exists() or path.is_symlink():path.unlink()
            path.write_bytes(original);path.chmod(0o600)
        self.assertEqual(self.discover()['status'],'verified')

    def test_installed_verification_is_bounded_before_reading_plan_bodies(self):
        self.stage();self.install_plan()
        for i in range(128):
            p=self.plans/(f'{i:064x}'+'.json');p.write_bytes(b'x');p.chmod(0o600)
        with self.assertRaisesRegex(m.Refused,'reviewed_plan_count'):self.discover()

    def test_installed_verification_does_not_trust_tampered_target_receipt(self):
        self.stage();self.install_plan()
        p=self.destination()/m.RECEIPT;raw=p.read_bytes();value=json.loads(raw)
        value['plan_sha256']='b'*64;p.chmod(0o600);p.write_bytes(m.encoded(value));p.chmod(0o440)
        with self.assertRaisesRegex(m.Refused,'reviewed_plan_missing'):self.discover()
        p.chmod(0o600);p.write_bytes(raw);p.chmod(0o440)
        self.assertEqual(self.discover()['status'],'verified')

    def test_wrong_role_host_revision_or_incomplete_files_refused_before_creation(self):
        for key, value in [('role', 'unknown'), ('host', 'serverD'), ('revision', '../active'), ('revision', 'old-m3'), ('files', []), ('source_receipt_sha256', 'not-a-hash')]:
            with self.subTest(key=key, value=value):
                plan = copy.deepcopy(self.plan)
                plan[key] = value
                with self.assertRaises(m.Refused):
                    self.stage(plan)
                self.assertFalse(self.root.exists())

    def test_target_escape_duplicate_and_receipt_injection_refused(self):
        for target in ['../current.json', '/etc/passwd', 'rocketmq/../current.json', 'rocketmq\\credentials.json', m.RECEIPT]:
            plan = copy.deepcopy(self.plan)
            plan['files'][0]['target'] = target
            with self.subTest(target=target), self.assertRaises(m.Refused):
                self.stage(plan)
        plan = copy.deepcopy(self.plan)
        plan['files'].append(copy.deepcopy(plan['files'][0]))
        with self.assertRaises(m.Refused):
            self.stage(plan)
        self.assertFalse(self.root.exists())

    def test_source_scope_and_parent_symlink_refused(self):
        outside = self.directory / 'outside.json'
        outside.write_bytes(Path(self.plan['files'][0]['source']).read_bytes())
        outside.chmod(0o600)
        plan = copy.deepcopy(self.plan)
        plan['files'][0]['source'] = str(outside)
        with self.assertRaises(m.Refused):
            self.stage(plan)
        parent_link = self.directory / 'source-alias'
        parent_link.symlink_to(self.sources, target_is_directory=True)
        plan['files'][0]['source'] = str(parent_link / Path(self.plan['files'][0]['source']).name)
        with self.assertRaises(m.Refused):
            self.stage(plan)
        allowed_link = self.sources / 'allowed-alias'
        allowed_link.symlink_to(self.sources, target_is_directory=True)
        plan['files'][0]['source'] = str(allowed_link / Path(self.plan['files'][0]['source']).name)
        with self.assertRaises(m.Refused):
            self.stage(plan)  # A symlink inside the allowed source scope also fails.
        source = Path(self.plan['files'][0]['source'])
        saved = source.with_name('saved-source.json')
        source.rename(saved)
        source.symlink_to(saved)
        with self.assertRaises(m.Refused):
            self.stage()
        source.unlink()
        saved.rename(source)
        self.assertFalse(self.root.exists())

    def test_missing_source_and_byte_or_permission_drift_refused_before_creation(self):
        source = Path(self.plan['files'][0]['source'])
        original = source.read_bytes()
        for effect in ('missing', 'bytes', 'mode'):
            with self.subTest(effect=effect):
                if effect == 'missing':
                    source.unlink()
                elif effect == 'bytes':
                    source.write_bytes(original + b' drift')
                else:
                    source.chmod(0o640)
                with self.assertRaises((m.Refused, OSError)):
                    self.stage()
                self.assertFalse(self.root.exists())
                source.write_bytes(original)
                source.chmod(0o600)

    def test_unsafe_parent_refused_without_changing_it(self):
        self.root.mkdir(mode=0o777)
        self.root.chmod(0o777)
        with self.assertRaises(m.Refused):
            self.stage()
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o777)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_destination_symlink_and_conflicting_existing_revision_never_overwritten(self):
        destination = self.destination()
        destination.parent.mkdir(parents=True)
        destination.symlink_to(self.sources, target_is_directory=True)
        with self.assertRaises(m.Refused):
            self.stage()
        destination.unlink()
        destination.mkdir()
        sentinel = destination / 'old'
        sentinel.write_bytes(b'protected old revision')
        with self.assertRaises((m.Refused, OSError)):
            self.stage()
        self.assertEqual(sentinel.read_bytes(), b'protected old revision')

    def test_tampered_staged_file_receipt_mode_and_extra_directory_refused(self):
        self.stage()
        destination = self.destination()
        target = destination / 'rocketmq/credentials.json'
        original = target.read_bytes()
        target.chmod(0o600)
        target.write_bytes(original + b' changed')
        target.chmod(0o440)
        with self.assertRaises(m.Refused):
            self.stage()
        target.chmod(0o600)
        target.write_bytes(original)
        with self.assertRaises(m.Refused):
            self.stage()
        target.chmod(0o440)
        (destination / 'extra').mkdir()
        with self.assertRaises(m.Refused):
            self.stage()

    def test_disk_failure_removes_only_own_staging_and_retains_sources(self):
        originals = {r['source']: Path(r['source']).read_bytes() for r in self.plan['files']}
        real = m.write_new
        calls = []
        def fail(path, raw, uid, gid):
            calls.append(path)
            if len(calls) == 2:
                raise OSError('synthetic full filesystem')
            real(path, raw, uid, gid)
        with patch.object(m, 'write_new', fail), self.assertRaises(OSError):
            self.stage()
        self.assertFalse(self.root.exists())
        self.assertEqual(originals, {p: Path(p).read_bytes() for p in originals})

    def test_source_change_during_copy_cannot_publish_revision(self):
        source = Path(self.plan['files'][0]['source'])
        real = m.write_new
        def change(path, raw, uid, gid):
            real(path, raw, uid, gid)
            if path.name == m.RECEIPT:
                source.write_bytes(b'changed by an independent actor')
        with patch.object(m, 'write_new', change), self.assertRaises(m.Refused):
            self.stage()
        self.assertFalse(self.destination().exists())
        self.assertFalse(self.root.exists())

    def test_duplicate_manifest_keys_are_not_silently_normalized(self):
        with self.assertRaises(m.Refused):
            json.loads('{"role":"iam","role":"worker"}', object_pairs_hook=m.unique)


if __name__ == '__main__':
    unittest.main()
