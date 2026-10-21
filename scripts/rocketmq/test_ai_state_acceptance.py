import json
import unittest

from ai_admission_acceptance import acceptance_profile, host_failure_diagnostics, parse_admission_receipt, validate_host_runtime, validate_host_sdk_lock
from ai_state_acceptance import CASES, TESTS, state_manifest


class AIStateAcceptanceTests(unittest.TestCase):
    def receipt(self):
        return {'cases': {name: True for name in CASES}, 'passed': len(CASES), 'failed': 0, 'skipped': 0,
                'root': 'original_mysql_sqlalchemy', 'sdk': '0.4.0a2', 'client': '5.1.2', 'python': '3.13.15',
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

    def test_exact_thirty_four_original_state_tests_and_eighty_four_proofs_are_required(self):
        profile = acceptance_profile('state')
        self.assertEqual(profile['parse'](self.output(), self.junit())['passed'], 84)
        self.assertEqual(profile['file'], 'rocketmq_state_host.py')
        with self.assertRaises(RuntimeError):
            parse_admission_receipt(self.output(), self.junit())

    def test_old_worker_only_receipt_cannot_claim_governance_or_full_review_acceptance(self):
        profile = acceptance_profile('state')
        receipt = self.receipt()
        old = {name: value for name, value in receipt['cases'].items()
               if not name.startswith(('governance_', 'review_', 'correction_', 'solution_', 'resolution_', 'serial_dispatch_', 'interpretation_finish_', 'claim_', 'scanner_', 'finish_retry_', 'serial_completion_', 'semantic_completion_'))}
        receipt.update(cases=old, passed=len(old))
        self.assertEqual(len(old), 13)
        self.assertEqual(len(TESTS), 34)
        with self.assertRaises(RuntimeError):
            profile['parse'](self.output(receipt), self.junit())

    def test_old_governance_twenty_flags_do_not_claim_correction_acceptance(self):
        profile = acceptance_profile('state')
        receipt = self.receipt()
        old = {name: value for name, value in receipt['cases'].items()
               if not name.startswith(('correction_', 'solution_', 'resolution_', 'serial_dispatch_', 'interpretation_finish_', 'claim_', 'scanner_', 'finish_retry_', 'serial_completion_', 'semantic_completion_'))}
        self.assertEqual(len(old), 20)
        receipt.update(cases=old, passed=len(old))
        with self.assertRaises(RuntimeError):
            profile['parse'](self.output(receipt), self.junit())

    def test_other_profile_receipt_is_not_substituted_for_state_acceptance(self):
        old = 'M3_AI_ADMISSION_RECEIPT ' + json.dumps(dict(self.receipt(), cases={}, passed=0))
        profile = acceptance_profile('state')
        self.assertEqual(profile['parse'](self.output() + '\n' + old, self.junit())['passed'], 84)
        with self.assertRaises(RuntimeError):
            profile['parse'](old, self.junit())

    def test_old_eight_tests_and_twenty_five_flags_cannot_claim_solution_acceptance(self):
        profile = acceptance_profile('state')
        receipt = self.receipt()
        old = {name: value for name, value in receipt['cases'].items()
               if not name.startswith(('solution_', 'resolution_', 'serial_dispatch_', 'interpretation_finish_', 'claim_', 'scanner_', 'finish_retry_', 'serial_completion_', 'semantic_completion_'))}
        self.assertEqual(len(old), 25)
        receipt.update(cases=old, passed=len(old))
        old_tests = [name for name in TESTS if not name.startswith(('test_actual_solution_', 'test_actual_resolution_', 'test_actual_serial_', 'test_actual_interpretation_finish_', 'test_actual_interpretation_claim_', 'test_actual_original_claim_scanner_', 'test_actual_explicit_finalization_retry_', 'test_actual_serial_generation_terminal_', 'test_actual_serial_terminal_', 'test_actual_serial_semantic_terminal_', 'test_actual_serial_semantic_cancel_'))]
        self.assertEqual(len(old_tests), 8)
        old_junit = '<testsuites><testsuite>' + ''.join(
            f'<testcase name="{name}"/>' for name in old_tests) + '</testsuite></testsuites>'
        with self.assertRaises(RuntimeError):
            profile['parse'](self.output(receipt), old_junit)

    def test_old_ten_tests_and_thirty_flags_cannot_claim_original_resolution_acceptance(self):
        profile = acceptance_profile('state')
        receipt = self.receipt()
        old = {name: value for name, value in receipt['cases'].items()
               if not name.startswith(('resolution_', 'serial_dispatch_', 'interpretation_finish_', 'claim_', 'scanner_', 'finish_retry_', 'serial_completion_', 'semantic_completion_'))}
        self.assertEqual(len(old), 30)
        receipt.update(cases=old, passed=len(old))
        old_tests = [name for name in TESTS if not name.startswith(('test_actual_resolution_', 'test_actual_serial_', 'test_actual_interpretation_finish_', 'test_actual_interpretation_claim_', 'test_actual_original_claim_scanner_', 'test_actual_explicit_finalization_retry_', 'test_actual_serial_generation_terminal_', 'test_actual_serial_terminal_', 'test_actual_serial_semantic_terminal_', 'test_actual_serial_semantic_cancel_'))]
        self.assertEqual(len(old_tests), 10)
        old_junit = '<testsuites><testsuite>' + ''.join(
            f'<testcase name="{name}"/>' for name in old_tests) + '</testsuite></testsuites>'
        with self.assertRaises(RuntimeError):
            profile['parse'](self.output(receipt), old_junit)

    def test_old_twelve_tests_and_thirty_five_flags_cannot_claim_serial_dispatch_acceptance(self):
        profile = acceptance_profile('state')
        receipt = self.receipt()
        old = {name: value for name, value in receipt['cases'].items()
               if not name.startswith(('serial_dispatch_', 'interpretation_finish_', 'claim_', 'scanner_', 'finish_retry_', 'serial_completion_', 'semantic_completion_'))}
        self.assertEqual(len(old), 35)
        receipt.update(cases=old, passed=len(old))
        old_tests = [name for name in TESTS if not name.startswith(('test_actual_serial_', 'test_actual_interpretation_finish_', 'test_actual_interpretation_claim_', 'test_actual_original_claim_scanner_', 'test_actual_explicit_finalization_retry_', 'test_actual_serial_generation_terminal_', 'test_actual_serial_terminal_', 'test_actual_serial_semantic_terminal_', 'test_actual_serial_semantic_cancel_'))]
        self.assertEqual(len(old_tests), 12)
        old_junit = '<testsuites><testsuite>' + ''.join(
            f'<testcase name="{name}"/>' for name in old_tests) + '</testsuite></testsuites>'
        with self.assertRaises(RuntimeError):
            profile['parse'](self.output(receipt), old_junit)

    def test_old_fifteen_tests_and_forty_two_flags_cannot_claim_interpretation_finish(self):
        profile = acceptance_profile('state')
        receipt = self.receipt()
        old = {name: value for name, value in receipt['cases'].items()
               if not name.startswith(('interpretation_finish_', 'claim_', 'scanner_', 'finish_retry_', 'serial_completion_', 'semantic_completion_'))}
        old_tests = [name for name in TESTS
                     if not name.startswith(('test_actual_interpretation_finish_', 'test_actual_interpretation_claim_', 'test_actual_original_claim_scanner_', 'test_actual_explicit_finalization_retry_', 'test_actual_serial_generation_terminal_', 'test_actual_serial_terminal_', 'test_actual_serial_semantic_terminal_', 'test_actual_serial_semantic_cancel_'))]
        self.assertEqual((len(old_tests), len(old)), (15, 42))
        receipt.update(cases=old, passed=len(old))
        old_junit = '<testsuites><testsuite>' + ''.join(
            f'<testcase name="{name}"/>' for name in old_tests) + '</testsuite></testsuites>'
        with self.assertRaises(RuntimeError):
            profile['parse'](self.output(receipt), old_junit)

    def test_old_nineteen_tests_and_fifty_one_flags_cannot_claim_original_admission(self):
        profile = acceptance_profile('state')
        receipt = self.receipt()
        old = {name: value for name, value in receipt['cases'].items()
               if not name.startswith(('claim_', 'scanner_', 'finish_retry_', 'serial_completion_', 'semantic_completion_'))}
        old_tests = [name for name in TESTS
                     if not name.startswith(('test_actual_interpretation_claim_', 'test_actual_original_claim_scanner_', 'test_actual_explicit_finalization_retry_', 'test_actual_serial_generation_terminal_', 'test_actual_serial_terminal_', 'test_actual_serial_semantic_terminal_', 'test_actual_serial_semantic_cancel_'))]
        self.assertEqual((len(old_tests), len(old)), (19, 51))
        receipt.update(cases=old, passed=len(old))
        old_junit = '<testsuites><testsuite>' + ''.join(
            f'<testcase name="{name}"/>' for name in old_tests) + '</testsuite></testsuites>'
        with self.assertRaises(RuntimeError):
            profile['parse'](self.output(receipt), old_junit)

    def test_old_claim_proofs_or_old_installed_package_cannot_claim_scanner_acceptance(self):
        profile = acceptance_profile('state')
        receipt = self.receipt()
        receipt['cases'] = {k: v for k, v in receipt['cases'].items() if not k.startswith(('scanner_', 'finish_retry_', 'serial_completion_', 'semantic_completion_'))}
        receipt['passed'] = len(receipt['cases'])
        old_tests = [n for n in TESTS if not n.startswith(('test_actual_original_claim_scanner_', 'test_actual_explicit_finalization_retry_', 'test_actual_serial_generation_terminal_', 'test_actual_serial_terminal_', 'test_actual_serial_semantic_terminal_', 'test_actual_serial_semantic_cancel_'))]
        self.assertEqual((len(old_tests), receipt['passed']), (23, 59))
        old_junit = '<testsuites><testsuite>' + ''.join(f'<testcase name="{n}"/>' for n in old_tests) + '</testsuite></testsuites>'
        with self.assertRaises(RuntimeError):
            profile['parse'](self.output(receipt), old_junit)
        receipt = self.receipt(); receipt['sdk'] = '0.4.0a1'
        with self.assertRaises(RuntimeError):
            profile['parse'](self.output(receipt), self.junit())

    def test_state_runtime_requires_exact_downloaded_wheel_url_hash_client_and_installation(self):
        profile = acceptance_profile('state')
        runtime = dict(sdk=profile['sdk_version'], client='5.1.2', python='3.13.15', installed_in_prefix=True,
            direct_url={'url': profile['sdk_url'], 'archive_info': {'hashes': {'sha256': profile['sdk_sha256']}}})
        validate_host_runtime(runtime, profile, '3.13')
        for field, value in [('sdk', '0.4.0a1'), ('client', '5.1.1'), ('installed_in_prefix', False),
                ('direct_url', {'url': profile['sdk_url'], 'archive_info': {'hashes': {'sha256': 'wrong'}}}), ('direct_url', {'url': 'file:///workspace/sdk'})]:
            with self.assertRaises(RuntimeError):
                validate_host_runtime(dict(runtime, **{field: value}), profile, '3.13')

    def test_uv_empty_archive_metadata_uses_strict_immutable_lock_hash(self):
        profile = acceptance_profile('state')
        lock = {'package': [{'name': 'fangcun-reliable-messaging', 'version': '0.4.0a2',
            'source': {'url': profile['sdk_url']},
            'wheels': [{'url': profile['sdk_url'], 'hash': 'sha256:' + profile['sdk_sha256']}]}]}
        self.assertEqual(validate_host_sdk_lock(lock, profile), profile['sdk_sha256'])
        validate_host_runtime(dict(sdk='0.4.0a2', client='5.1.2', python='3.13.15', installed_in_prefix=True,
            direct_url={'url': profile['sdk_url'], 'archive_info': {}}), profile, '3.13')
        for field, value in [('version', '0.4.0a1'), ('source', {'url': 'file:///workspace/sdk'}),
                ('wheels', []), ('wheels', [{'url': profile['sdk_url'], 'hash': 'sha256:wrong'}])]:
            changed = json.loads(json.dumps(lock)); changed['package'][0][field] = value
            with self.assertRaises(RuntimeError):
                validate_host_sdk_lock(changed, profile)
        with self.assertRaises(RuntimeError):
            validate_host_sdk_lock({'package': lock['package'] * 2}, profile)

    def test_old_scanner_receipt_does_not_prove_explicit_finish_retry(self):
        profile = acceptance_profile('state')
        receipt = self.receipt()
        receipt['cases'] = {k: v for k, v in receipt['cases'].items() if not k.startswith(('finish_retry_', 'serial_completion_', 'semantic_completion_'))}
        receipt['passed'] = len(receipt['cases'])
        old_tests = [n for n in TESTS if not n.startswith(('test_actual_explicit_finalization_retry_', 'test_actual_serial_generation_terminal_', 'test_actual_serial_terminal_', 'test_actual_serial_semantic_terminal_', 'test_actual_serial_semantic_cancel_'))]
        self.assertEqual((len(old_tests), receipt['passed']), (26, 64))
        old_junit = '<testsuites><testsuite>' + ''.join(f'<testcase name="{n}"/>' for n in old_tests) + '</testsuite></testsuites>'
        with self.assertRaises(RuntimeError):
            profile['parse'](self.output(receipt), old_junit)

    def test_old_twenty_eight_finish_proofs_cannot_claim_durable_serial_terminal(self):
        profile = acceptance_profile('state')
        receipt = self.receipt()
        receipt['cases'] = {k: v for k, v in receipt['cases'].items()
                            if not k.startswith(('serial_completion_', 'semantic_completion_'))}
        receipt['passed'] = len(receipt['cases'])
        old_tests = [n for n in TESTS if not n.startswith(
            ('test_actual_serial_generation_terminal_', 'test_actual_serial_terminal_', 'test_actual_serial_semantic_terminal_', 'test_actual_serial_semantic_cancel_'))]
        self.assertEqual((len(old_tests), receipt['passed']), (28, 68))
        old_junit = '<testsuites><testsuite>' + ''.join(
            f'<testcase name="{n}"/>' for n in old_tests) + '</testsuite></testsuites>'
        with self.assertRaises(RuntimeError):
            profile['parse'](self.output(receipt), old_junit)

    def test_old_thirty_one_generation_proofs_cannot_claim_serial_semantic_terminal(self):
        profile = acceptance_profile('state')
        receipt = self.receipt()
        receipt['cases'] = {k: v for k, v in receipt['cases'].items()
                            if not k.startswith('semantic_completion_')}
        receipt['passed'] = len(receipt['cases'])
        old_tests = [n for n in TESTS if not n.startswith(
            ('test_actual_serial_semantic_terminal_', 'test_actual_serial_semantic_cancel_'))]
        self.assertEqual((len(old_tests), receipt['passed']), (31, 76))
        old_junit = '<testsuites><testsuite>' + ''.join(
            f'<testcase name="{n}"/>' for n in old_tests) + '</testsuite></testsuites>'
        with self.assertRaises(RuntimeError):
            profile['parse'](self.output(receipt), old_junit)

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
