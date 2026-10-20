import json
import unittest

from qs_retry_acceptance import CASES, parse_retry_receipts


class QSRetryAcceptanceTest(unittest.TestCase):
    def output(self):
        lines = []
        for backend in CASES:
            receipt = {'backend': backend, 'passed': len(CASES[backend]), 'failed': 0, 'skipped': 0,
                       'cases': {name: True for name in CASES[backend]},
                       'scope': 'original_run_and_future_plan_storage_only',
                       'broker_dispatch_not_claimed': True, 'system_login_not_claimed': True}
            name = 'TestM3Retry' + ('MySQL' if backend == 'mysql' else 'Mongo') + 'Store'
            lines += ['M3_QS_RETRY_STORE_RECEIPT ' + json.dumps(receipt), '--- PASS: ' + name + ' (1.00s)']
        return '\n'.join(lines)

    def test_two_exact_backends_required(self):
        self.assertEqual(set(parse_retry_receipts(self.output())), set(CASES))

    def test_reject_partial_duplicate_skip_race_wrong_scope_and_missing_tests(self):
        output = self.output()
        for bad in ('', output + '\n' + output, output.split('M3_QS_RETRY_STORE_RECEIPT', 2)[0],
                    output.replace('"backend": "mongo"', '"backend": "mysql"'),
                    output.replace('"skipped": 0', '"skipped": 1'),
                    output.replace('"failed": 0', '"failed": 1'),
                    output.replace('true', 'false', 1), output.replace('--- PASS:', '--- SKIP:'),
                    output + '\nWARNING: DATA RACE', output.replace('TestM3RetryMongoStore', 'TestSDKProbe'),
                    output.replace('original_run_and_future_plan_storage_only', 'full_business_acceptance')):
            with self.subTest(bad=bad[:100]):
                with self.assertRaises(RuntimeError):
                    parse_retry_receipts(bad)
