import io
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from final_image_candidate import GO_SUM, MODULE, check_go_buildinfo, ci_guard, inventory_names, saved_config


class FinalImageProofTest(unittest.TestCase):
    def test_refuses_local_self_hosted_and_external_daemon(self):
        env = dict(GITHUB_ACTIONS='true', RUNNER_OS='Linux', RUNNER_ENVIRONMENT='github-hosted')
        ci_guard(env)
        for changed in ({}, dict(env, RUNNER_ENVIRONMENT='self-hosted'),
                        dict(env, DOCKER_HOST='tcp://outside'), dict(env, DOCKER_CONTEXT='other')):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                ci_guard(changed)

    def test_binary_rejects_other_version_sum_and_replace(self):
        raw = 'runtime\n\tdep\t' + MODULE + '\tv0.5.0\t' + GO_SUM + '\n'
        self.assertEqual(check_go_buildinfo(raw)['version'], 'v0.5.0')
        for changed in (raw.replace('v0.5.0', 'v0.5.0-rocketmq-tx.4'),
                        raw.replace(GO_SUM, 'h1:other'),
                        raw + '\t=>\t../local-sdk\t(devel)\n', '', raw + raw):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                check_go_buildinfo(changed)

    def test_archive_inventory_never_extracts_or_accepts_deferred_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'rootfs.tar'
            for name in ('app/qs-worker', '../outside', '/outside',
                         'app/host-observer', 'app/native_recovery.py',
                         'app/native-resume-helper', 'app/JavaNativeHalfManaged.class'):
                with tarfile.open(archive, 'w') as output:
                    item = tarfile.TarInfo(name)
                    item.size = 1
                    output.addfile(item, io.BytesIO(b'x'))
                if name == 'app/qs-worker':
                    self.assertEqual(inventory_names(archive), [name])
                else:
                    with self.subTest(name=name), self.assertRaises(ValueError):
                        inventory_names(archive)
            self.assertFalse((Path(directory) / 'app').exists())

    def test_config_digest_comes_from_actual_archive_not_engine_manifest_id(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'image.tar'
            config = b'{"os":"linux","architecture":"amd64","config":{"User":"www"}}'
            for tags in (['m3-image:fixed'], ['other:tag']):
                manifest = json.dumps([{'Config': 'config.json', 'RepoTags': tags}]).encode()
                with tarfile.open(archive, 'w') as output:
                    for name, body in (('manifest.json', manifest), ('config.json', config)):
                        item = tarfile.TarInfo(name)
                        item.size = len(body)
                        output.addfile(item, io.BytesIO(body))
                if tags == ['m3-image:fixed']:
                    digest, value = saved_config(archive, 'm3-image:fixed')
                    self.assertEqual(digest, 'sha256:' + hashlib.sha256(config).hexdigest())
                    self.assertEqual(value['config']['User'], 'www')
                else:
                    with self.assertRaises(ValueError):
                        saved_config(archive, 'm3-image:fixed')


if __name__ == '__main__':
    unittest.main()
