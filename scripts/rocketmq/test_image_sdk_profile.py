import json
import unittest

from final_image_candidate import MODULE, check_go_buildinfo
from image_sdk_profile import sdk_profile, verify_readable_python_lock


class ImageSDKProfileTest(unittest.TestCase):
    def test_readable_binary_and_frozen_m3_contracts_cannot_substitute_each_other(self):
        old, new = sdk_profile('m3-stable'), sdk_profile('readable-rc1')
        for name, contract, other in (('m3-stable', old, new), ('readable-rc1', new, old)):
            raw = f"binary\n\tdep\t{MODULE}\t{contract['go']}\t{contract['go_sum']}\n"
            self.assertEqual(check_go_buildinfo(raw, profile=name)['version'], contract['go'])
            for invalid in (raw.replace(contract['go'], other['go']),
                            raw.replace(contract['go_sum'], other['go_sum']),
                            raw + '\t=>\t../workspace-sdk\t(devel)\n', raw + raw):
                with self.subTest(profile=name), self.assertRaises(ValueError):
                    check_go_buildinfo(invalid, profile=name)
        with self.assertRaises(ValueError):
            check_go_buildinfo(f"dep\t{MODULE}\t{new['go']}\t{new['go_sum']}\n")

    def test_unknown_or_unpublished_profile_is_not_a_floating_version(self):
        for name in ('readable-stable', 'main', 'latest', 'v0.6.0', '', None):
            with self.subTest(name=name), self.assertRaises(ValueError):
                sdk_profile(name)
        value = sdk_profile('readable-rc1')
        value['source_sha'] = 'b' * 40
        self.assertEqual(sdk_profile('readable-rc1')['source_sha'],
                         '5c2e3cd155e67c0f766e93bf95238b16fc219b5f')

    def test_python_lock_requires_the_exact_published_archive_and_checksum(self):
        expected = sdk_profile('readable-rc1')
        def lock(version=expected['python'], url=expected['wheel_url'], checksum=expected['wheel_sha256'], source=None):
            source = {'url': url} if source is None else source
            encoded = ', '.join(key + '=' + json.dumps(value) for key, value in source.items())
            return ('[[package]]\nname="fangcun-reliable-messaging"\nversion=' + json.dumps(version)
                    + '\nsource={' + encoded + '}\nwheels=[{url=' + json.dumps(url)
                    + ', hash=' + json.dumps('sha256:' + checksum) + '}]\n')
        valid = lock()
        self.assertEqual(verify_readable_python_lock(valid, 'readable-rc1')['version'], '0.5.0rc1')
        for invalid in ('', valid + valid, lock(version='0.4.0'), lock(checksum='b' * 64),
                        lock(url='https://example.invalid/repacked.whl'),
                        lock(source={'editable': '../sdk'}), lock(source={'path': '../sdk'})):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                verify_readable_python_lock(invalid, 'readable-rc1')
        with self.assertRaises(ValueError):
            verify_readable_python_lock(valid, 'm3-stable')
