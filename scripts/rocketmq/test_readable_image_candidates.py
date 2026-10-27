import copy
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from image_sdk_profile import sdk_profile
from readable_image_candidates import TARGETS, parse, read, validate_inventory, verify_archive

ROOT = Path(__file__).resolve().parents[2]


class ReadableImageCandidatesTest(unittest.TestCase):
    def setUp(self):
        self.profile = sdk_profile('readable-rc1')
        self.value = dict(schema='readable-image-candidates/v1', sdk_profile='readable-rc1',
            sources=dict(iam='a' * 40, qs='b' * 40, ai='c' * 40), builder_sha='d' * 40,
            image_runs=dict.fromkeys(TARGETS, '40123456789'), go_identity=dict(uid=2000, gid=2000),
            images={target: dict(inventory_sha256='e' * 64, archive_sha256='f' * 64,
                                image_config_id='sha256:' + 'a' * 64, archive_bytes=123) for target in TARGETS},
            routes_sha256=hashlib.sha256((ROOT / 'components/rocketmq/serverd-routes-readable-v3.json').read_bytes()).hexdigest(),
            production=False)

    def inventory(self, target):
        role = 'qs' if target.startswith('qs-') else target
        row = self.value['images'][target]
        value = dict(schema='readable-final-image-inventory/v1', target=target, sdk_profile='readable-rc1',
            source_sha=self.value['sources'][role], builder_source_sha=self.value['builder_sha'],
            expected_sdk_source_sha=self.profile['source_sha'], stable_release=False,
            production=False, registry_published=False, application_started=False,
            runtime_ready=False, cutover_rehearsal_complete=False, passed=1, failed=0, skipped=0,
            archive_bytes=row['archive_bytes'], archive_sha256=row['archive_sha256'], image_config_id=row['image_config_id'],
            deferred_tools_absent=True, image_user='app' if target == 'ai' else 'www',
            cleanup=dict(owned_container_absent=True, owned_image_tag_absent=True, existing_containers_unchanged=True))
        if target == 'ai':
            value['runtime_sdk'] = dict(uid=10001, version=self.profile['python'], client='5.1.2', source=self.value['sources']['ai'])
            value['python_source_lock'] = dict(version=self.profile['python'], wheel_sha256=self.profile['wheel_sha256'], editable=False)
        else:
            value['runtime_sdk'] = dict(version=self.profile['go'], sum=self.profile['go_sum'], replace=False)
            value['verified_uid_gid'] = [2000, 2000]
            value['runtime_binary_sha256'] = 'b' * 64
        return value

    def test_five_exact_sources_and_sdk_inventory_are_required(self):
        self.assertEqual(parse(json.dumps(self.value).encode()), self.value)
        for target in TARGETS:
            data = self.inventory(target)
            self.assertEqual(validate_inventory(self.value, target, data), data)
            for field, wrong in (('schema', 'm3-final-image-inventory/v1'), ('source_sha', 'e' * 40),
                                 ('builder_source_sha', 'f' * 40), ('expected_sdk_source_sha', 'a' * 40),
                                 ('stable_release', True), ('production', True), ('passed', True),
                                 ('skipped', 1), ('archive_sha256', 'b' * 64), ('image_user', 'root')):
                changed = copy.deepcopy(data); changed[field] = wrong
                with self.subTest(target=target, field=field), self.assertRaises(ValueError):
                    validate_inventory(self.value, target, changed)
        wrong = self.inventory('qs-worker'); wrong['verified_uid_gid'] = [0, 0]
        with self.assertRaises(ValueError):
            validate_inventory(self.value, 'qs-worker', wrong)
        wrong = self.inventory('ai'); wrong['runtime_sdk']['version'] = '0.4.0'
        with self.assertRaises(ValueError):
            validate_inventory(self.value, 'ai', wrong)

    def test_legacy_floating_uncoordinated_or_incomplete_candidate_is_rejected(self):
        for field, wrong in (('schema', 'm4-final-image-candidates/v1'), ('sdk_profile', 'm3-stable'),
                             ('sdk_profile', 'readable-stable'), ('builder_sha', 'main'),
                             ('go_identity', dict(uid=0, gid=2000)), ('production', True)):
            changed = copy.deepcopy(self.value); changed[field] = wrong
            with self.subTest(field=field), self.assertRaises(ValueError):
                parse(json.dumps(changed).encode())
        for damage in ('missing_image', 'different_run', 'boolean_size', 'duplicate_json'):
            changed = copy.deepcopy(self.value)
            if damage == 'missing_image': del changed['images']['ai']
            elif damage == 'different_run': changed['image_runs']['qs-worker'] = '40123456790'
            elif damage == 'boolean_size': changed['images']['ai']['archive_bytes'] = True
            raw = json.dumps(changed).encode()
            if damage == 'duplicate_json': raw = raw[:-1] + b',"production":false}'
            with self.subTest(damage=damage), self.assertRaises(ValueError): parse(raw)

    def test_routes_are_frozen_by_original_file_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate, routes = Path(directory) / 'candidate.json', Path(directory) / 'routes.json'
            candidate.write_text(json.dumps(self.value))
            routes.write_bytes((ROOT / 'components/rocketmq/serverd-routes-readable-v3.json').read_bytes())
            self.assertEqual(read(candidate, routes)[0], self.value)
            routes.write_bytes(routes.read_bytes() + b'\n')
            with self.assertRaises(ValueError): read(candidate, routes)

    def test_archive_config_and_inventory_are_verified_without_loading_or_extracting(self):
        target = 'qs-worker'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / (target + '-' + self.value['sources']['qs'] + '.tar.gz')
            config = b'{"os":"linux","architecture":"amd64","config":{"User":"www"}}'
            manifest = json.dumps([dict(Config='config.json', RepoTags=['m3-final-qs-worker:123456abcdef'])]).encode()
            with tarfile.open(archive, 'w:gz') as saved:
                for name, raw in (('manifest.json', manifest), ('config.json', config)):
                    info = tarfile.TarInfo(name); info.size = len(raw); saved.addfile(info, io.BytesIO(raw))
            frozen = self.value['images'][target]
            frozen.update(image_config_id='sha256:' + hashlib.sha256(config).hexdigest(),
                          archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), archive_bytes=archive.stat().st_size)
            inventory = root / 'image-inventory.json'; inventory.write_text(json.dumps(self.inventory(target)))
            frozen['inventory_sha256'] = hashlib.sha256(inventory.read_bytes()).hexdigest()
            self.assertEqual(verify_archive(self.value, target, root), archive)
            self.assertFalse((root / 'config.json').exists())
            inventory.write_bytes(inventory.read_bytes() + b'\n')
            with self.assertRaises(ValueError): verify_archive(self.value, target, root)
