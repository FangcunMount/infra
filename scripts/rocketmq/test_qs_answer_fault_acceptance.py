import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from qs_answer_fault_acceptance import CASES, SCOPE, parse_receipt, wire_evidence


class AnswerOriginalPacketReceiptTest(unittest.TestCase):
    def receipt(self, boundary):
        return dict(source_sha='a'*40, scope=SCOPE, boundary=boundary, passed=6, failed=0, skipped=0,
            cases={case: True for case in CASES}, local_calls=1, mongo_callbacks=2, half_prepared=1,
            new_half_prepared=0, new_check_commit=0, new_check_rollback=int(boundary == 'before'),
            business_rows=int(boundary == 'after'), new_local_calls=0, wire_unchanged=True,
            full_api_process_provider_system_not_claimed=True)

    def output(self, receipt):
        return ('M3_QS_ANSWER_FAULT_RECEIPT '+json.dumps(receipt)+
                '\n--- PASS: TestM3AnswerOriginalCommitPacketFault (1s)')

    def test_driver_reentry_does_not_authorize_second_executor_or_new_half(self):
        for boundary in ('before', 'after'):
            value = self.receipt(boundary)
            self.assertEqual(parse_receipt(self.output(value), 'a'*40, boundary), value)

    def test_partial_scope_wrong_business_or_missing_real_abort_check_fails(self):
        value = self.receipt('before')
        for changes in (dict(source_sha='b'*40), dict(scope='full API'), dict(cases={}),
                        dict(passed=0), dict(skipped=1), dict(local_calls=2), dict(mongo_callbacks=17),
                        dict(half_prepared=True), dict(new_local_calls=1), dict(new_half_prepared=1),
                        dict(business_rows=1), dict(new_check_rollback=0), dict(new_check_commit=1),
                        dict(wire_unchanged=False), dict(full_api_process_provider_system_not_claimed=False)):
            with self.subTest(changes=changes):
                with self.assertRaises(RuntimeError): parse_receipt(self.output(dict(value, **changes)), 'a'*40, 'before')
        output = self.output(value)
        for bad in ('', output+'\n'+output, output.replace('TestM3AnswerOriginalCommitPacketFault', 'TestSDKProbe'),
                    output+'\nWARNING: DATA RACE', output+'\n--- SKIP: optional (1s)'):
            with self.assertRaises(RuntimeError): parse_receipt(bad, 'a'*40, 'before')

    def test_wire_evidence_counts_all_matching_original_session_commit_retries(self):
        for boundary in ('before', 'after'):
            events = [dict(kind='mongo', boundary=boundary, backend_ack=boundary == 'after')]*3
            stats = dict(event='stats', seen=3, dropped=3, backend_commit_acks=3 if boundary == 'after' else 0)
            self.assertEqual(wire_evidence(events, stats, boundary)['dropped'], 3)
            for changes in (dict(seen=0), dict(dropped=2), dict(backend_commit_acks=1)):
                with self.assertRaises(RuntimeError): wire_evidence(events, dict(stats, **changes), boundary)
            with self.assertRaises(RuntimeError): wire_evidence([], stats, boundary)
            wrong = [dict(events[0], kind='mysql')]
            with self.assertRaises(RuntimeError): wire_evidence(wrong, stats, boundary)

    def test_invalid_mixed_profile_never_starts_a_fixture(self):
        script = Path(__file__).with_name('ci-transactions.py')
        base = [sys.executable, str(script), '--sdk', '.', '--image', 'unused',
                '--report', '/not-created-native-report.json', '--qs-answer-host-faults']
        options = [[], ['--iam-host', '.'], ['--qs-answer-host', '.', '--iam-host', '.'],
                   ['--qs-answer-host', '.', '--qs-runtime-host', '.'],
                   ['--qs-answer-host', '.', '--sdk-faults'], ['--qs-answer-host', '.', '--sdk-api-go']]
        for argv in options:
            with self.subTest(argv=argv):
                result = subprocess.run(base+argv, env=dict(os.environ, PATH=''),
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 2)
                self.assertIn('original AnswerSheet faults require one explicit QS source', result.stderr)


if __name__ == '__main__':
    unittest.main()
