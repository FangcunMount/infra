import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from ai_database_fault_acceptance import CASES, SCOPE, TEST, parse_receipt, profile, proxy_database_url


class AIOriginalDatabaseReceiptTest(unittest.TestCase):
    def receipt(self, boundary):
        return dict(source_sha='a'*40, boundary=boundary, scope=SCOPE, passed=6, failed=0, skipped=0,
            cases={case: True for case in CASES}, local_calls=1, half_prepared=2, new_half_prepared=0,
            new_check_rollback=int(boundary == 'before'), business_rows=int(boundary == 'after'),
            inbox_rows=int(boundary == 'after'), provider_invocations=0, fixed_two_branch_wire=True,
            full_api_process_real_provider_system_not_claimed=True)

    def output(self, receipt):
        return 'M3_AI_DATABASE_FAULT_RECEIPT '+json.dumps(receipt)

    def xml(self):
        return '<testsuite><testcase name="'+TEST+'" classname="tests.integration.rocketmq_database_faults"/></testsuite>'

    def test_original_root_witness_inbox_and_fixed_two_branches(self):
        for boundary in ('before', 'after'):
            value = self.receipt(boundary)
            self.assertEqual(parse_receipt(self.output(value), self.xml(), 'a'*40, boundary), value)
        self.assertEqual(profile()['sdk_version'], '0.4.0a2')
        self.assertEqual(profile()['name'], 'db_faults')

    def test_native_test_skip_missing_source_wrong_fact_or_model_redo_fails(self):
        value = self.receipt('before')
        for changes in (dict(source_sha='b'*40), dict(cases={}), dict(passed=0), dict(skipped=1),
                        dict(business_rows=1), dict(inbox_rows=1), dict(provider_invocations=1),
                        dict(half_prepared=1), dict(new_half_prepared=1), dict(local_calls=True),
                        dict(new_check_rollback=0), dict(fixed_two_branch_wire=False),
                        dict(full_api_process_real_provider_system_not_claimed=False)):
            with self.subTest(changes=changes):
                with self.assertRaises(RuntimeError):
                    parse_receipt(self.output(dict(value, **changes)), self.xml(), 'a'*40, 'before')
        for xml in ('<testsuite/>', self.xml().replace('/>', '><skipped/></testcase>'),
                    self.xml().replace(TEST, 'test_sdk_probe'),
                    self.xml().replace('rocketmq_database_faults', 'rocketmq_paired_host'),
                    self.xml().replace('</testsuite>', '<testcase name="extra"/></testsuite>')):
            with self.assertRaises(RuntimeError): parse_receipt(self.output(value), xml, 'a'*40, 'before')

    def test_proxy_only_changes_owned_loopback_port_and_preserves_original_database(self):
        url = 'mysql+asyncmy://fixture:synthetic%40value@127.0.0.1:32100/owned_db?charset=utf8mb4'
        self.assertEqual(proxy_database_url(url, '127.0.0.1:32101'), url.replace(':32100/', ':32101/'))
        for source, address in ((url, 'example.com:32101'), (url, '127.0.0.1:70000'),
                                (url.replace('127.0.0.1', 'db.example.com'), '127.0.0.1:32101'),
                                (url.replace('mysql+asyncmy', 'postgresql'), '127.0.0.1:32101')):
            with self.assertRaises(RuntimeError): proxy_database_url(source, address)

    def test_explicit_database_fault_profile_rejected_before_fixture_on_misuse(self):
        script = Path(__file__).with_name('ci-transactions.py')
        base = [sys.executable, str(script), '--sdk', '.', '--image', 'unused', '--report', '/not-created-report.json']
        for extra, kind in ((['--ai-host-database-faults'], 'db_faults'),
                            (['--ai-admission-host', '.', '--ai-host-database-faults'], 'admission'),
                            (['--ai-admission-host', '.', '--ai-host-database-faults', '--iam-host', '.'], 'db_faults'),
                            (['--ai-admission-host', '.'], 'db_faults')):
            result = subprocess.run(base+extra, env=dict(os.environ, PATH='', QS_AI_ACCEPTANCE_KIND=kind),
                capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 2)
            self.assertIn('fault', result.stderr)


if __name__ == '__main__':
    unittest.main()
