import json
import unittest

from ai_admission_acceptance import CASES, TESTS, admission_manifest, parse_admission_receipt


class AIAdmissionAcceptanceTests(unittest.TestCase):
    def receipt(self):
        return {'cases': {name: True for name in CASES}, 'passed': len(CASES), 'failed': 0, 'skipped': 0,
                'root': 'original_mysql_sqlalchemy', 'sdk': '0.4.0a1', 'client': '5.1.2',
                'system_login_not_claimed': True, 'paired_qs_business_not_claimed': True,
                'real_provider_not_claimed': True, 'process_exit_not_claimed': True,
                'database_commit_network_fault_not_claimed': True}

    def output(self, receipt=None):
        return 'M3_AI_ADMISSION_RECEIPT ' + json.dumps(self.receipt() if receipt is None else receipt)

    def junit(self):
        return '<testsuites><testsuite>' + ''.join(f'<testcase name="{name}"/>' for name in sorted(TESTS)) + '</testsuite></testsuites>'

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


if __name__ == '__main__':
    unittest.main()
