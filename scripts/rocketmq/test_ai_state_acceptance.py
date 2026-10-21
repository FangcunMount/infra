import json
import unittest

from ai_admission_acceptance import acceptance_profile, host_failure_diagnostics, parse_admission_receipt
from ai_state_acceptance import CASES, TESTS, state_manifest


class AIStateAcceptanceTests(unittest.TestCase):
    def receipt(self):
        return {'cases': {name: True for name in CASES}, 'passed': len(CASES), 'failed': 0, 'skipped': 0,
                'root': 'original_mysql_sqlalchemy', 'sdk': '0.4.0a1', 'client': '5.1.2', 'python': '3.13.15',
                'system_login_not_claimed': True, 'paired_qs_business_not_claimed': True,
                'real_provider_not_claimed': True, 'process_exit_not_claimed': True,
                'database_commit_network_fault_not_claimed': True}

    def output(self, receipt=None):
        return 'M3_AI_STATE_RECEIPT ' + json.dumps(self.receipt() if receipt is None else receipt)

    def junit(self):
        return '<testsuites><testsuite>' + ''.join(f'<testcase name="{name}"/>' for name in sorted(TESTS)) + '</testsuite></testsuites>'

    def test_state_has_one_owner_topic_and_only_producer_observer_permissions(self):
        manifest = state_manifest()
        self.assertEqual(len(manifest['routes']), 1)
        route = manifest['routes'][0]
        self.assertEqual((route['owner'], route['message_type']), ('ai.mysql', 'TRANSACTION'))
        self.assertEqual(manifest['accounts']['ai']['subscriptions'], [])
        self.assertEqual(manifest['accounts']['observer']['publish'], [])
        self.assertEqual(manifest['accounts']['ai']['publish'], [route['id']])
        self.assertEqual(manifest['accounts']['observer']['subscriptions'], [route['id']])

    def test_exact_six_worker_governance_tests_and_twenty_proofs_are_required(self):
        profile = acceptance_profile('state')
        self.assertEqual(profile['parse'](self.output(), self.junit())['passed'], 20)
        self.assertEqual(profile['file'], 'rocketmq_state_host.py')
        with self.assertRaises(RuntimeError):
            parse_admission_receipt(self.output(), self.junit())

    def test_old_worker_only_receipt_cannot_claim_governance_or_full_review_acceptance(self):
        profile = acceptance_profile('state')
        receipt = self.receipt()
        old = {name: value for name, value in receipt['cases'].items()
               if not name.startswith(('governance_', 'review_'))}
        receipt.update(cases=old, passed=len(old))
        self.assertEqual(len(old), 13)
        self.assertEqual(len(TESTS), 6)
        with self.assertRaises(RuntimeError):
            profile['parse'](self.output(receipt), self.junit())

    def test_other_profile_receipt_is_not_substituted_for_state_acceptance(self):
        old = 'M3_AI_ADMISSION_RECEIPT ' + json.dumps(dict(self.receipt(), cases={}, passed=0))
        profile = acceptance_profile('state')
        self.assertEqual(profile['parse'](self.output() + '\n' + old, self.junit())['passed'], 20)
        with self.assertRaises(RuntimeError):
            profile['parse'](old, self.junit())

    def test_incomplete_failed_skipped_duplicate_or_broader_state_scope_cannot_pass(self):
        profile = acceptance_profile('state')
        for key, value in (('passed', 0), ('failed', 1), ('skipped', 1), ('cases', {}),
                           ('real_provider_not_claimed', False)):
            receipt = self.receipt(); receipt[key] = value
            with self.assertRaises(RuntimeError):
                profile['parse'](self.output(receipt), self.junit())
        for junit in ('<testsuites/>', self.junit().replace('/>', '><skipped/></testcase>', 1),
                      self.junit().replace('/>', '><error/></testcase>', 1), self.junit().replace('test_actual_worker_preflight_lost_final_reply_preserves_local_commit', 'sdk_probe')):
            with self.assertRaises(RuntimeError):
                profile['parse'](self.output(), junit)

    def test_private_payload_and_unknown_case_fields_do_not_escape_partial_receipt(self):
        profile = acceptance_profile('state')
        for change in ({'wire': 'private-wire'}, {'cases': {'private-wire': True}}, {'failed': False}):
            receipt = self.receipt(); receipt.update(change)
            self.assertIsNone(profile['partial'](self.output(receipt)))

    def test_unknown_profile_cannot_select_an_arbitrary_source_or_resource_manifest(self):
        for kind in ('', '../production', 'wrong'):
            with self.assertRaises(RuntimeError):
                acceptance_profile(kind)
        self.assertEqual(len(acceptance_profile('admission')['manifest']()['routes']), 2)
        self.assertEqual(len(acceptance_profile('state')['manifest']()['routes']), 1)

    def test_failure_diagnostics_only_export_declared_test_names_and_bounded_lines(self):
        name = sorted(TESTS)[0]
        raw = f'ERROR tests/integration/rocketmq_state_host.py::{name}\nFAILED tests/integration/rocketmq_state_host.py::private_wire_secret\nrocketmq_state_host.py:42\n'
        self.assertEqual(host_failure_diagnostics(raw, 'rocketmq_state_host.py', TESTS), {'failed_cases': [name], 'assertion_lines': [42]})


if __name__ == '__main__':
    unittest.main()
