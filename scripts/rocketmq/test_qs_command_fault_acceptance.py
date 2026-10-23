import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from qs_command_fault_acceptance import CASES, SCOPE, parse_receipt


class QSCommandOriginalPacketTest(unittest.TestCase):
    def receipt(self, boundary):
        return dict(source_sha='a'*40, scope=SCOPE, boundary=boundary, passed=6, failed=0, skipped=0,
            cases={case: True for case in CASES}, seals=1, sdk_executions=1, half_prepared=1,
            new_half_prepared=0, new_check_rollback=int(boundary == 'before'),
            business_rows=int(boundary == 'after'), full_api_process_paired_provider_system_not_claimed=True)

    def output(self, value):
        return ('M3_QS_COMMAND_FAULT_RECEIPT '+json.dumps(value)+
                '\n--- PASS: TestM3AICommandOriginalCommitPacketFault (1s)')

    def test_each_original_commit_boundary_has_exact_frozen_operation(self):
        for boundary in ('before', 'after'):
            value = self.receipt(boundary)
            self.assertEqual(parse_receipt(self.output(value), 'a'*40, boundary), value)

    def test_reseal_second_sdk_execution_missing_abort_or_invented_scope_rejected(self):
        value = self.receipt('before')
        for changes in (dict(source_sha='b'*40), dict(cases={}), dict(passed=0), dict(skipped=1),
                        dict(seals=2), dict(sdk_executions=2), dict(half_prepared=True),
                        dict(new_half_prepared=1), dict(new_check_rollback=0), dict(business_rows=1),
                        dict(scope='paired system acceptance'),
                        dict(full_api_process_paired_provider_system_not_claimed=False)):
            with self.subTest(changes=changes):
                with self.assertRaises(RuntimeError): parse_receipt(self.output(dict(value, **changes)), 'a'*40, 'before')
        output = self.output(value)
        for bad in ('', output+'\n'+output, output.replace('TestM3AICommandOriginalCommitPacketFault','TestSDKProbe'),
                    output+'\n--- SKIP: optional (1s)', output+'\nWARNING: DATA RACE'):
            with self.assertRaises(RuntimeError): parse_receipt(bad,'a'*40,'before')

    def test_mixed_profile_refused_before_fixture_creation(self):
        base = [sys.executable, str(Path(__file__).with_name('ci-transactions.py')),
                '--sdk', '.', '--image', 'unused', '--report', '/not-created-report.json', '--qs-command-host-faults']
        for extra in ([], ['--qs-command-host', '.', '--sdk-api-go'], ['--qs-command-host', '.', '--iam-host', '.'],
                      ['--qs-command-host', '.', '--qs-runtime-host', '.']):
            result = subprocess.run(base+extra, capture_output=True, text=True, timeout=5,
                                    env=dict(os.environ, PATH=''))
            self.assertEqual(result.returncode, 2)
            self.assertIn('original QS command faults require one explicit QS command source', result.stderr)


if __name__ == '__main__':
    unittest.main()
