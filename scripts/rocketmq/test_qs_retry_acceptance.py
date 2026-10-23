import json
import unittest

from qs_retry_acceptance import CASES, CLI_CASES, parse_retry_receipts


class QSRetryAcceptanceTest(unittest.TestCase):
    def output(self, *, handoff_cli=False):
        lines = []
        for backend in CASES:
            expected = CASES[backend] | (CLI_CASES if handoff_cli else frozenset())
            receipt = {'backend': backend, 'passed': len(expected), 'failed': 0, 'skipped': 0,
                       'cases': {name: True for name in expected},
                       'scope': 'original_authorization_and_explicit_future_ownership_handoff',
                       'broker_dispatch_not_claimed': True, 'system_login_not_claimed': True}
            if handoff_cli:
                receipt['offline_cli_required'] = True
            name = 'TestM3Retry' + ('MySQL' if backend == 'mysql' else 'Mongo') + 'Store'
            lines += ['M3_QS_RETRY_STORE_RECEIPT ' + json.dumps(receipt), '--- PASS: ' + name + ' (1.00s)']
        return '\n'.join(lines)

    def test_two_exact_backends_required(self):
        self.assertEqual(set(parse_retry_receipts(self.output())), set(CASES))

    def test_offline_cli_requires_both_full_case_sets_and_explicit_profile(self):
        output = self.output(handoff_cli=True)
        receipts = parse_retry_receipts(output, handoff_cli=True)
        self.assertEqual({r['passed'] for r in receipts.values()}, {30})
        for bad in (self.output(),
                    output.replace('"offline_cli_required": true', '"offline_cli_required": false'),
                    output.replace('"offline_cli_required": true', '"offline_cli_required": 1'),
                    output.replace('offline_cli_no_sdk_transaction_rows', 'not_verified'),
                    output.replace('"failed": 0', '"failed": 1'),
                    output.replace('--- PASS:', '--- SKIP:')):
            with self.subTest(bad=bad[:80]), self.assertRaises(RuntimeError):
                parse_retry_receipts(bad, handoff_cli=True)
        with self.assertRaises(RuntimeError):
            parse_retry_receipts(output)
        with self.assertRaises(RuntimeError):
            parse_retry_receipts(output, handoff_cli='1')

    def test_default_cannot_claim_offline_cli_without_running_it(self):
        for marker in ('true', '0', '1', '"false"'):
            bad = self.output().replace('"scope":', '"offline_cli_required": ' + marker + ', "scope":')
            with self.subTest(marker=marker), self.assertRaises(RuntimeError):
                parse_retry_receipts(bad)

    def test_reject_partial_duplicate_skip_race_wrong_scope_and_missing_tests(self):
        output = self.output()
        for bad in ('', output + '\n' + output, output.split('M3_QS_RETRY_STORE_RECEIPT', 2)[0],
                    output.replace('"backend": "mongo"', '"backend": "mysql"'),
                    output.replace('"skipped": 0', '"skipped": 1'),
                    output.replace('"failed": 0', '"failed": 1'),
                    output.replace('true', 'false', 1), output.replace('--- PASS:', '--- SKIP:'),
                    output + '\nWARNING: DATA RACE', output.replace('TestM3RetryMongoStore', 'TestSDKProbe'),
                    output.replace('original_authorization_and_explicit_future_ownership_handoff', 'full_business_acceptance')):
            with self.subTest(bad=bad[:100]):
                with self.assertRaises(RuntimeError):
                    parse_retry_receipts(bad)
