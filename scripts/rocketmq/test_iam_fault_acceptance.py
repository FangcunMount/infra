import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from iam_fault_acceptance import CASES, SCOPE, fixed_diagnostics, parse_receipt, wire_evidence


class IAMOriginalCommitReceiptTest(unittest.TestCase):
    def receipt(self, boundary):
        return dict(source_sha='a'*40, boundary=boundary, scope=SCOPE,
            passed=6, failed=0, skipped=0, cases={case: True for case in CASES},
            callback_calls=1, half_prepared=1,
            new_paused_rollback_checks=1 if boundary == 'before' else 0,
            full_api_process_provider_system_not_claimed=True)

    def output(self, receipt):
        return ('M3_IAM_FAULT_RECEIPT '+json.dumps(receipt)+
                '\n--- PASS: TestM3IAMOriginalCommitPacketFault (1s)')

    def test_both_boundaries_require_exact_business_root_and_current_source(self):
        for boundary in ('before', 'after'):
            receipt = self.receipt(boundary)
            self.assertEqual(parse_receipt(self.output(receipt), 'a'*40, boundary), receipt)

    def test_cannot_relabel_other_tests_partial_evidence_or_repeat_business(self):
        receipt = self.receipt('before')
        for changes in (dict(source_sha='b'*40), dict(boundary='after'), dict(scope='SDK only'),
                        dict(passed=0), dict(skipped=1), dict(callback_calls=2),
                        dict(half_prepared=True), dict(new_paused_rollback_checks=0),
                        dict(cases={}), dict(cases=dict(receipt['cases'], extra=True)),
                        dict(cases={case: False for case in CASES}),
                        dict(full_api_process_provider_system_not_claimed=False)):
            with self.subTest(changes=changes):
                with self.assertRaises(RuntimeError):
                    parse_receipt(self.output(dict(receipt, **changes)), 'a'*40, 'before')
        output = self.output(receipt)
        for bad in ('', output+'\n'+output, output.replace('TestM3IAMOriginalCommitPacketFault', 'TestSDKProbe'),
                    output+'\n--- SKIP: optional (1s)', output+'\nWARNING: DATA RACE'):
            with self.assertRaises(RuntimeError): parse_receipt(bad, 'a'*40, 'before')

    def test_after_cannot_claim_new_paused_rollback(self):
        receipt = self.receipt('after')
        receipt['new_paused_rollback_checks'] = 1
        with self.assertRaises(RuntimeError): parse_receipt(self.output(receipt), 'a'*40, 'after')

    def test_distinct_real_tcp_before_and_backend_ack_after(self):
        for boundary in ('before', 'after'):
            injection = dict(event='injected', kind='mysql', boundary=boundary,
                             backend_ack=boundary == 'after', dropped=1)
            stats = dict(event='stats', seen=1, dropped=1, backend_commit_acks=int(boundary == 'after'))
            self.assertEqual(wire_evidence(injection, stats, boundary)['boundary'], boundary)
            for changes in (dict(kind='mongo'), dict(dropped=0), dict(backend_ack=not injection['backend_ack'])):
                with self.assertRaises(RuntimeError): wire_evidence(dict(injection, **changes), stats, boundary)
            for changes in (dict(seen=0), dict(seen=2), dict(dropped=0),
                            dict(backend_commit_acks=1-stats['backend_commit_acks'])):
                with self.assertRaises(RuntimeError): wire_evidence(injection, dict(stats, **changes), boundary)


class IAMOriginalCommitIsolationTest(unittest.TestCase):
    def test_mixed_or_missing_profile_rejected_without_git_or_docker(self):
        script = Path(__file__).with_name('ci-transactions.py')
        base = [sys.executable, str(script), '--sdk', '.', '--image', 'unused',
                '--report', '/not-created-native-report.json', '--iam-host-faults']
        cases = [([], dict()), (['--iam-host', '.'], dict(ROCKETMQ_IAM_RUNTIME_REQUIRED='1'))]
        for option in ('--qs-runtime-host', '--qs-deferred-consumer-host', '--qs-answer-host',
                       '--qs-command-host', '--ai-admission-host', '--iam-fanout-qs', '--go-probe'):
            cases.append((['--iam-host', '.', option, '.'], dict()))
        for option in ('--sdk-api-go', '--sdk-api-python', '--sdk-faults', '--m3-resources'):
            cases.append((['--iam-host', '.', option], dict()))
        for argv, extra in cases:
            with self.subTest(argv=argv):
                result = subprocess.run(base+argv, capture_output=True, text=True, timeout=5,
                    env={**os.environ, 'PATH': '', 'ROCKETMQ_IAM_RUNTIME_REQUIRED': '0', **extra})
                self.assertEqual(result.returncode, 2)
                self.assertIn('original IAM faults require one explicit IAM source', result.stderr)

    def test_diagnostic_retains_only_fixed_counts_enums(self):
        value = dict(boundary='after', api_error=False, business_rows=1, version_delta=1,
                     decision='commit', callback_calls=1)
        marker = 'M3_IAM_FAULT_DIAGNOSTIC '
        self.assertEqual(fixed_diagnostics('private arbitrary text'), [])
        self.assertEqual(fixed_diagnostics(marker+json.dumps(value)), [value])
        for changes in (dict(wire='PRIVATE'), dict(decision='PRIVATE'), dict(callback_calls=True),
                        dict(business_rows=-1), dict(version_delta=17), dict(api_error='PRIVATE')):
            with self.assertRaises(RuntimeError): fixed_diagnostics(marker+json.dumps(dict(value, **changes)))
        with self.assertRaises(RuntimeError): fixed_diagnostics('\n'.join([marker+json.dumps(value)]*5))


if __name__ == '__main__':
    unittest.main()
