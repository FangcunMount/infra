import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from native_limit_acceptance import safe_event
from qs_runtime_acceptance import NATIVE_LIMIT_CASES, parse_native_limit_receipt
from test_qs_runtime_acceptance import DefaultRuntimeReceiptTest


class NativeLimitHandoffTest(unittest.TestCase):
    def receipt(self):
        return dict(source_sha='a'*40, passed=8, failed=0, skipped=0, owner_count=2,
            cases={k: True for k in NATIVE_LIMIT_CASES}, real_sys_index_required=True,
            timestamp_aging_not_used=True, governance_resolution_not_claimed=True,
            domain_api_provider_system_not_claimed=True, owned_databases_dropped=True)

    def output(self, value):
        return DefaultRuntimeReceiptTest().output()+'\nM3_QS_NATIVE_LIMIT_RECEIPT '+json.dumps(value)

    def test_actual_host_receipt_requires_original_lifecycle_proof(self):
        value = self.receipt()
        self.assertEqual(parse_native_limit_receipt(self.output(value), 'a'*40), value)
        with self.assertRaises(RuntimeError):
            parse_native_limit_receipt('M3_QS_NATIVE_LIMIT_RECEIPT '+json.dumps(value), 'a'*40)

    def test_missing_ambiguous_synthetic_or_skipped_claim_rejected(self):
        value = self.receipt()
        for change in ({'source_sha': 'b'*40}, {'passed': True}, {'skipped': 1},
                       {'real_sys_index_required': False}, {'timestamp_aging_not_used': False},
                       {'governance_resolution_not_claimed': False}, {'body': 'private'},
                       {'cases': {}}, {'cases': dict(value['cases'], extra=True)}):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                parse_native_limit_receipt(self.output(dict(value, **change)), 'a'*40)
        with self.assertRaises(RuntimeError):
            parse_native_limit_receipt(self.output(value)+'\nM3_QS_NATIVE_LIMIT_RECEIPT '+json.dumps(value), 'a'*40)

    def test_fault_generator_counters_are_not_business_sdk_proof(self):
        ready = dict(event='ready', prepared=1)
        closed = dict(event='closed', prepared=1, unknown_checks=2, business_calls=0, final_confirmation_calls=0, local_fault_callbacks=1, owned_database_dropped=True)
        self.assertEqual(safe_event(ready), ready)
        self.assertEqual(safe_event(closed), closed)
        for change in ({'unknown_checks': 0}, {'unknown_checks': True}, {'business_calls': 1},
                       {'final_confirmation_calls': 1}, {'wire': 'private'}, {'unknown_checks': 1024}):
            self.assertEqual(safe_event(dict(closed, **change)), {'event': 'invalid_native_limit_fault_event'})
        self.assertEqual(safe_event(dict(ready, prepared=True)), {'event': 'invalid_native_limit_fault_event'})

    def test_mixed_or_missing_host_fails_before_docker(self):
        script = Path(__file__).with_name('ci-transactions.py')
        for flags in ([], ['--qs-runtime-host', '.', '--qs-protocol-protection']):
            result = subprocess.run([sys.executable, str(script), '--sdk', '.', '--image', 'unused',
                '--report', '/not-created-native-limit-report.json', '--qs-native-limit', *flags],
                capture_output=True, text=True, timeout=5, env=dict(os.environ, PATH=''))
            self.assertEqual(result.returncode, 2)
            self.assertIn('native limit requires its own QS runtime profile', result.stderr)


class IAMNativeLimitHandoffTest(unittest.TestCase):
    def output(self, value):
        from iam_acceptance import RUNTIME_CASES
        base = dict(source_sha='a'*40, scope='actual IAM owner lifecycle and original root; in-process only',
            passed=6, failed=0, skipped=0, cases={k: True for k in RUNTIME_CASES}, business_executions=1,
            full_api_process_fault_or_system_not_claimed=True)
        return ('--- PASS: TestM3ActualOwnerDrain (1s)\nM3_IAM_RUNTIME_RECEIPT '+json.dumps(base)
            +'\nM3_IAM_NATIVE_LIMIT_RECEIPT '+json.dumps(value))

    def test_original_host_and_exact_native_scope_required(self):
        from iam_acceptance import NATIVE_LIMIT_CASES, parse_native_limit_receipt
        value = dict(source_sha='a'*40, passed=7, failed=0, skipped=0,
            cases={k: True for k in NATIVE_LIMIT_CASES}, business_executions=1,
            real_sys_index_required=True, idle_checker_readiness_not_new_broker_callback=True,
            governance_resolution_not_claimed=True, full_api_process_fault_or_system_not_claimed=True)
        self.assertEqual(parse_native_limit_receipt(self.output(value), 'a'*40), value)
        for change in ({'passed': True}, {'business_executions': 2}, {'skipped': 1},
                       {'real_sys_index_required': False}, {'idle_checker_readiness_not_new_broker_callback': False},
                       {'governance_resolution_not_claimed': False}, {'cases': {}}, {'wire': 'private'}):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                parse_native_limit_receipt(self.output(dict(value, **change)), 'a'*40)
