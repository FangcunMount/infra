import copy
import unittest

from readable_host_acceptance import MODULE, readable_manifest, record_readable_fixture
from qs_answer_acceptance import answer_manifest
from qs_evaluation_acceptance import evaluation_manifest
from qs_report_acceptance import report_manifest
from qs_task_acceptance import task_manifest


class ReadableHostTest(unittest.TestCase):
    def test_all_original_root_fixtures_remain_immutable_and_exact(self):
        for factory in (answer_manifest, evaluation_manifest, report_manifest, task_manifest):
            with self.subTest(factory=factory.__name__):
                original = factory()
                frozen = copy.deepcopy(original)
                result = factory(readable=True)
                self.assertEqual(result, readable_manifest(original))
                self.assertEqual(original, frozen)
                self.assertEqual(original['version'], 2)
                self.assertEqual(result['version'], 3)
                self.assertEqual(result['accounts'], original['accounts'])
                self.assertEqual(result['topic_options'], original['topic_options'])
                self.assertEqual(result['group_options'], original['group_options'])
                for before, after in zip(original['routes'], result['routes']):
                    for key in before.keys() - {'physical_topic', 'consumer_group'}:
                        self.assertEqual(before[key], after[key])
                    self.assertEqual(after['naming_scheme'], 'readable-v1')
                    self.assertLessEqual(len(after['consumer_group'].encode()), 64)
                    self.assertNotEqual(before['physical_topic'], after['physical_topic'])

    def test_candidate_identity_and_manifest_fail_closed(self):
        module = dict(MODULE, Path='github.com/FangcunMount/reliable-messaging')
        proof = {}
        record_readable_fixture(module, answer_manifest(readable=True), proof)
        self.assertEqual(proof['manifest_version'], 3)
        for bad in (dict(module, Replace={}), dict(module, Version='v0.5.0'),
                    dict(module, Sum='wrong'), dict(module, Path='foreign')):
            with self.assertRaises(RuntimeError):
                record_readable_fixture(bad, answer_manifest(readable=True), {})
        with self.assertRaises(RuntimeError):
            record_readable_fixture(module, answer_manifest(), {})
