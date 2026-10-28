import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from readable_retirement_native import empty_topic, single_cluster, run_owned_retirement, retry_v2_parameter, generate_owned_pop_v2
import test_readable_transition as fixtures


class ReadableRetirementNativeTest(unittest.TestCase):
    def test_effective_retry_setting_requires_one_exact_boolean(self):
        self.assertFalse(retry_v2_parameter('enableRetryTopicV2 = false\n'))
        self.assertTrue(retry_v2_parameter(' enableRetryTopicV2 = true \n'))
        for raw in ('','enableRetryTopicV2 = unknown','enableRetryTopicV2 = True',
                    'enableRetryTopicV2 = false\nenableRetryTopicV2 = true'):
            with self.subTest(raw=raw),self.assertRaises(RuntimeError):retry_v2_parameter(raw)

    def control(self,before,*,invoke_error=False,restore_error=False):
        state={'enabled':before};actions=[];admin=Mock()
        admin.side_effect=lambda operation:'enableRetryTopicV2 = '+str(state['enabled']).lower()+'\n'
        admin.metadata.return_value={'topicConfigTable':{'%RETRY%owned+topic':{}}}
        def command(client,operation,*args,**options):
            actions.append(args[-1])
            if not (restore_error and args[-1]=='false'):state['enabled']=args[-1]=='true'
        def invoke():
            self.assertTrue(state['enabled'])
            if invoke_error:raise RuntimeError('owned controlled failure')
            return {'retry_topic':'%RETRY%owned+topic'}
        with (patch('final_image_candidate.ci_guard'),patch('readable_retirement_native.subprocess.run',
                return_value=SimpleNamespace(returncode=0,stdout='rocketmq-m2-aabbccddeeff')),
                patch('readable_retirement_native.Admin',return_value=admin),
                patch('readable_retirement_native.command',side_effect=command)):
            try:result=generate_owned_pop_v2('owned','rocketmq-m2-aabbccddeeff',invoke)
            finally:
                self.assertEqual(actions,[] if before else ['true','false'])
                self.assertTrue(any(c.args[:1]==('rmdir',) for c in admin.docker.call_args_list))
        return result,state

    def test_only_owned_control_temporarily_enables_then_restores_actual_original_value(self):
        for before in (False,True):
            (row,proof),state=self.control(before)
            self.assertEqual(state['enabled'],before)
            self.assertEqual(proof,dict(before=before,during=True,after=before,restored=True,production=False))

    def test_native_generation_failure_still_restores_original_setting_before_exit(self):
        with self.assertRaisesRegex(RuntimeError,'controlled failure'):self.control(False,invoke_error=True)

    def test_restore_failure_cannot_report_a_successful_control(self):
        with self.assertRaisesRegex(RuntimeError,'not restored'):self.control(False,restore_error=True)

    def test_foreign_broker_never_changes_settings_or_calls_generator(self):
        invoke=Mock()
        with (patch('final_image_candidate.ci_guard'),patch('readable_retirement_native.subprocess.run',
                return_value=SimpleNamespace(returncode=0,stdout='production')),
                patch('readable_retirement_native.Admin') as admin):
            with self.assertRaises(RuntimeError):generate_owned_pop_v2('foreign','rocketmq-m2-aabbccddeeff',invoke)
        admin.assert_not_called();invoke.assert_not_called()

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
