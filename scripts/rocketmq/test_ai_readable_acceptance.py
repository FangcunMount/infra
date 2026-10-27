import copy
import os
import unittest
from unittest.mock import patch

from ai_admission_acceptance import acceptance_profile, validate_host_sdk_lock
from ai_readable_acceptance import URL, SHA256, complete_manifest
from routes import validate


class AIReadableTest(unittest.TestCase):
    def test_profiles_freeze_same_actual_test_ids_and_strict_sdk(self):
        for kind in ('admission', 'state', 'finalization', 'paired', 'paired_faults'):
            with self.subTest(kind=kind):
                with patch.dict(os.environ, QS_AI_READABLE_ROUTES='0'):
                    original = acceptance_profile(kind)
                frozen = copy.deepcopy(original['manifest']())
                with patch.dict(os.environ, QS_AI_READABLE_ROUTES='1'):
                    current = acceptance_profile(kind)
                if kind != 'paired_faults':
                    self.assertEqual(current['tests'], original['tests'])
                self.assertEqual(current['file'], original['file'])
                self.assertEqual(current['sdk_version'], '0.5.0rc1')
                self.assertEqual(current['sdk_url'], URL)
                self.assertEqual(current['sdk_sha256'], SHA256)
                manifest = current['manifest']()
                validate(manifest)
                self.assertEqual(manifest['version'], 3)
                self.assertEqual({r['topic'] for r in manifest['routes']},
                                 {'qs.ai.commands.v1', 'qs.ai.events.v1', 'qs.ai.acks.v1'})
                self.assertTrue(all(r['naming_scheme'] == 'readable-v1' for r in manifest['routes']))
                self.assertEqual(original['manifest'](), frozen)
                self.assertEqual(manifest, complete_manifest(original['manifest']))
                if kind != 'paired_faults':
                    self.assertIsNone(current['partial'](''))
                    with self.assertRaises(RuntimeError):
                        current['parse']('', '<testsuite/>')

    def test_paired_profiles_keep_exact_owners_and_cannot_claim_empty_native_results(self):
        from paired_acceptance import FULL_CASES
        from test_paired_acceptance import receipt,xml
        from paired_acceptance import MARKER,FULL_TESTS
        import json
        with patch.dict(os.environ, QS_AI_READABLE_ROUTES='1',QS_M3_PAIRED_PROFILE='full'):
            current=acceptance_profile('paired')
        manifest=current['manifest']()
        self.assertEqual(set(manifest['accounts']),{'ai','qs'})
        self.assertEqual(len(manifest['routes']),3)
        value=receipt(True);value.update(sdk_go='v0.6.0-rc.1',sdk_python='0.5.0rc1')
        self.assertEqual(set(current['parse'](MARKER+json.dumps(value),xml(FULL_TESTS))['cases']),FULL_CASES)
        value['sdk_go']='v0.5.0'
        with self.assertRaises(RuntimeError):current['parse'](MARKER+json.dumps(value),xml(FULL_TESTS))

    def test_fixed_released_wheel_is_mandatory(self):
        with patch.dict(os.environ, QS_AI_READABLE_ROUTES='1'):
            profile = acceptance_profile('state')
        package = dict(name='fangcun-reliable-messaging', version='0.5.0rc1',
                       source={'url': URL}, wheels=[{'url': URL, 'hash': 'sha256:' + SHA256}])
        self.assertEqual(validate_host_sdk_lock({'package': [package]}, profile), SHA256)
        for bad in (dict(package, version='0.4.0'), dict(package, source={'path': '../sdk'}),
                    dict(package, wheels=[{'url': URL, 'hash': 'sha256:' + '0' * 64}])):
            with self.assertRaises(RuntimeError):
                validate_host_sdk_lock({'package': [bad]}, profile)

    def test_unknown_or_mixed_modes_refuse(self):
        with patch.dict(os.environ, QS_AI_READABLE_ROUTES='yes'):
            with self.assertRaises(RuntimeError):
                acceptance_profile('admission')
        with patch.dict(os.environ, QS_AI_READABLE_ROUTES='1'):
            for kind in ('protection', 'native_limit', 'db_faults'):
                with self.assertRaises(RuntimeError):
                    acceptance_profile(kind)
