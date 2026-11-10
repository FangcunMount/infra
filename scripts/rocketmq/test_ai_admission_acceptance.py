import json
from subprocess import CompletedProcess
import unittest
from unittest.mock import Mock

from ai_admission_acceptance import (
    CASES, TESTS, STABLE_NATIVE_AI_SOURCE, STABLE_NATIVE_SDK_SHA256, acceptance_profile,
    admission_manifest, parse_admission_receipt, read_partial_receipt, validate_host_sdk_lock,
)
from ai_native_origin_acceptance import sys_index_context


class AIAdmissionAcceptanceTests(unittest.TestCase):
    def test_native_index_context_keeps_storage_route_and_log_evidence_separate(self):
        key = 'private-fixture-key'
        log = f'Check transaction. real_topic=fixture,uniqKey={key}\n'
        header = '#Broker Name #QID #Min Offset #Max Offset #Last Updated\n'
        run = Mock(side_effect=[
            CompletedProcess([], 0, log, ''),
            CompletedProcess([], 0, '{"topicConfigTable":{"TRANS_CHECK_MAX_TIME_TOPIC":{}}}', ''),
            CompletedProcess([], 0, header + 'fixture 0 0 2\n', ''),
            CompletedProcess([], 0, '', 'No topic route info for this topic'),
        ])
        report = sys_index_context(run, 'owned-broker', key)
        self.assertTrue(report['local_topic_catalog']['discard_present'])
        self.assertEqual(report['transaction_log']['original_key_counts']['checks'], 1)
        self.assertEqual(report['half_topic_status']['queues'], [dict(queue=0, min_offset=0, max_offset=2)])
        self.assertTrue(report['discard_topic_status']['no_route_reported'])
        self.assertNotIn(key, json.dumps(report))

    def receipt(self):
        return {'cases': {name: True for name in CASES}, 'passed': len(CASES), 'failed': 0, 'skipped': 0,
                'root': 'original_mysql_sqlalchemy', 'sdk': '0.4.0a1', 'client': '5.1.2', 'python': '3.13.15',
                'system_login_not_claimed': True, 'paired_qs_business_not_claimed': True,
                'real_provider_not_claimed': True, 'process_exit_not_claimed': True,
                'database_commit_network_fault_not_claimed': True}

    def output(self, receipt=None):
        return 'M3_AI_ADMISSION_RECEIPT ' + json.dumps(self.receipt() if receipt is None else receipt)

    def junit(self):
        return '<testsuites><testsuite>' + ''.join(f'<testcase name="{name}"/>' for name in sorted(TESTS)) + '</testsuite></testsuites>'

    def test_native_stable_wheel_is_bound_to_exact_ai_source(self):
        stable = acceptance_profile('native_limit', STABLE_NATIVE_AI_SOURCE)
        historical = acceptance_profile('native_limit', 'a' * 40)
        self.assertEqual(stable['sdk_version'], '0.5.0')
        self.assertEqual(stable['sdk_sha256'], STABLE_NATIVE_SDK_SHA256)
        self.assertEqual(historical['sdk_version'], '0.4.0a4')
        self.assertEqual(stable['focus_cases'], historical['focus_cases'])
        self.assertEqual(acceptance_profile('protection', STABLE_NATIVE_AI_SOURCE)['sdk_version'], '0.4.0a4')
        wheel = {'url': stable['sdk_url'], 'hash': 'sha256:' + STABLE_NATIVE_SDK_SHA256}
        locked = {'package': [{'name': 'fangcun-reliable-messaging', 'version': '0.5.0',
                               'source': {'url': stable['sdk_url']}, 'wheels': [wheel]}]}
        self.assertEqual(validate_host_sdk_lock(locked, stable), STABLE_NATIVE_SDK_SHA256)
        for profile in (historical, acceptance_profile('protection', STABLE_NATIVE_AI_SOURCE)):
            with self.assertRaises(RuntimeError):
                validate_host_sdk_lock(locked, profile)
        wheel['hash'] = 'sha256:' + '0' * 64
        with self.assertRaises(RuntimeError):
            validate_host_sdk_lock(locked, stable)

    def test_owner_scoped_manifest_preserves_all_three_distinct_roles(self):
        manifest = admission_manifest()
        command, event = manifest['routes']
        self.assertEqual((command['message_type'], command['owner']), ('TRANSACTION', 'qs.mysql'))
        self.assertEqual((event['message_type'], event['owner']), ('TRANSACTION', 'ai.mysql'))
        self.assertEqual(manifest['accounts']['ai']['publish'], [event['id']])
        self.assertEqual(manifest['accounts']['ai']['subscriptions'], [command['id']])
        self.assertEqual(manifest['accounts']['observer']['publish'], [])

    def test_accepts_only_exact_nonempty_real_host_scope_and_test_identity_set(self):
        self.assertEqual(parse_admission_receipt(self.output(), self.junit())['passed'], len(CASES))

    def test_rejects_partial_duplicated_skipped_failed_or_broader_receipts(self):
        for key, value in (('failed', 1), ('skipped', 1), ('passed', 0), ('cases', {}),
                           ('sdk', 'editable'), ('root', 'full_business_acceptance'),
                           ('paired_qs_business_not_claimed', False), ('process_exit_not_claimed', False)):
            with self.subTest(key=key):
                receipt = self.receipt(); receipt[key] = value
                with self.assertRaises(RuntimeError):
                    parse_admission_receipt(self.output(receipt), self.junit())
        for output in ('', self.output() + '\n' + self.output()):
            with self.assertRaises(RuntimeError):
                parse_admission_receipt(output, self.junit())

    def test_actual_native_tests_cannot_be_replaced_with_generic_probes_or_silent_skips(self):
        for junit in ('<testsuites/>', self.junit().replace('testcase name=', 'testcase different='),
                       self.junit().replace('/>', '><skipped/></testcase>', 1),
                       self.junit().replace('/>', '><failure/></testcase>', 1),
                       self.junit().replace('/>', '><error/></testcase>', 1),
                       self.junit().replace('test_actual_start_half_gate_and_duplicate_reuses_original_plan', 'SDKProbe')):
            with self.subTest(junit=junit[:80]):
                with self.assertRaises(RuntimeError):
                    parse_admission_receipt(self.output(), junit)


    def test_partial_failure_retains_only_known_cases_and_never_becomes_success(self):
        receipt = self.receipt()
        receipt['cases'].pop('lost_final_reply')
        receipt['passed'] -= 1
        receipt['failed'] = 1
        self.assertEqual(read_partial_receipt(self.output(receipt)), receipt)
        with self.assertRaises(RuntimeError):
            parse_admission_receipt(self.output(receipt), self.junit())

    def test_arbitrary_diagnostics_secret_values_and_noninteger_counts_never_leave_private_logs(self):
        for changes in ({'private_wire': 'private payload'}, {'python': 'private payload'},
                        {'cases': {'private payload': True}}, {'failed': False}):
            receipt = self.receipt(); receipt.update(changes)
            self.assertIsNone(read_partial_receipt(self.output(receipt)))


if __name__ == '__main__':
    unittest.main()
