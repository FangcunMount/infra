import unittest
from unittest.mock import patch

from readable_retirement_native import empty_topic, single_cluster, run_owned_retirement
import test_readable_transition as fixtures


class ReadableRetirementNativeTest(unittest.TestCase):
    def test_empty_offsets_require_actual_queue_and_zero_original_offsets(self):
        raw = '#Broker Name  #QID  #Min Offset  #Max Offset  #Last Updated\nserverd-rocketmq 0 0 0\n\nTopic Put TPS: 0.0\n'
        empty_topic(raw)
        for bad in ('', raw.replace('0 0 0', '0 0 1'), raw.replace('0 0 0', '0 1 1'),
                    raw.replace('serverd-rocketmq 0 0 0', ''),
                    raw.replace('serverd-rocketmq 0 0 0', 'serverd-rocketmq 0 0 0\nserverd-rocketmq 1 0 0')):
            with self.assertRaises(RuntimeError):
                empty_topic(bad)

    def test_cluster_requires_one_exact_master(self):
        raw = '#Cluster Name  #Broker Name  #BID  #Addr  #Version\nFangcunMount serverd-rocketmq 0 127.0.0.1:10911 V5_5_1\n'
        single_cluster(raw)
        for bad in ('', raw + 'Other another 0 other:10911 V5_5_1\n',
                    raw.replace('127.0.0.1', '100.118.164.39'), raw.replace(' 0 ', ' 1 ')):
            with self.assertRaises(RuntimeError):
                single_cluster(bad)

    def test_production_project_or_incomplete_native_receipt_never_constructs_admin(self):
        f = fixtures.ReadableTransitionTest()
        f.setUp()
        for project, receipt in (('rocketmq', dict(passed=130, failed=0, skipped=0)),
                                  ('rocketmq-m2-aabbccddeeff', dict(passed=129, failed=0, skipped=0)),
                                  ('rocketmq-m2-aabbccddeeff', dict(passed=130, failed=0, skipped=1))):
            with patch('readable_retirement_native.Admin', side_effect=AssertionError('no Broker access')):
                with self.assertRaises(RuntimeError):
                    run_owned_retirement('unused', project, f.old, f.new, f.accounts, receipt)
