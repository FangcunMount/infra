import json
import unittest

from qs_deferred_acceptance import CASES, SCOPE, parse_deferred_receipt


class DeferredReceiptTest(unittest.TestCase):
    def output(self):
        receipt = dict(source_sha='a' * 40, passed=len(CASES), failed=0, skipped=0,
                       cases={case: True for case in CASES}, scope=SCOPE,
                       broker_not_claimed=True, whole_worker_not_claimed=True,
                       system_login_not_claimed=True, human_authorization_api_not_claimed=True,
                       owned_databases_dropped=True, owned_child_reaped=True)
        return 'M3_QS_DEFERRED_MYSQL_RECEIPT ' + json.dumps(receipt) + '\n--- PASS: TestRocketMQDeferredNative (1.00s)'

    def test_exact_source_cases_scope_and_cleanup(self):
        self.assertEqual(parse_deferred_receipt(self.output(), 'a' * 40)['passed'], 7)

    def test_refuses_empty_partial_wrong_source_skip_race_and_scope_substitution(self):
        output = self.output()
        for bad in ('', output + '\n' + output, output.replace('"failed": 0', '"failed": 1'),
                    output.replace('"skipped": 0', '"skipped": 1'), output.replace('a' * 40, 'b' * 40),
                    output.replace('true', 'false', 1), output.replace(SCOPE, 'whole production worker'),
                    output.replace('"owned_child_reaped": true', '"owned_child_reaped": false'),
                    output.replace('TestRocketMQDeferredNative', 'TestSDKProbe'), output + '\nWARNING: DATA RACE',
                    output + '\n--- SKIP: optional (0.00s)'):
            with self.subTest(bad=bad[:80]):
                with self.assertRaises(RuntimeError):
                    parse_deferred_receipt(bad, 'a' * 40)
