import json
import unittest

from qs_event_acceptance import CASES, event_manifest, parse_event_receipt


class QSEventAcceptanceTest(unittest.TestCase):
    def output(self):
        receipt = {'passed': len(CASES), 'failed': 0, 'skipped': 0,
                   'cases': {name: True for name in CASES}, 'root': 'original_mysql_sql',
                   'system_login_not_claimed': True, 'paired_ai_producer_not_claimed': True,
                   'process_exit_not_claimed': True, 'database_commit_network_fault_not_claimed': True}
        return 'M3_QS_AI_EVENT_RECEIPT ' + json.dumps(receipt) + '\n--- PASS: TestM3AIEventBrokerHost (1.00s)'

    def test_manifest_is_transaction_owner_scoped(self):
        manifest = event_manifest()
        self.assertEqual(len(manifest['routes']), 2)
        self.assertEqual(manifest['routes'][0]['message_type'], 'TRANSACTION')
        self.assertEqual(manifest['routes'][0]['owner'], 'qs.mysql')

    def test_exact_nonempty_native_receipt_required(self):
        self.assertEqual(parse_event_receipt(self.output())['passed'], len(CASES))

    def test_reject_partial_duplicate_skip_race_or_broader_claims(self):
        output = self.output()
        for bad in ('', output + output, output.replace('"skipped": 0', '"skipped": 1'),
                    output.replace('"failed": 0', '"failed": 1'), output.replace('true', 'false', 1),
                    output.replace('--- PASS:', '--- SKIP:'), output + '\nWARNING: DATA RACE',
                    output.replace('TestM3AIEventBrokerHost', 'TestSDKProbe'),
                    output.replace('original_mysql_sql', 'full_business_acceptance'),
                    output.replace('"paired_ai_producer_not_claimed": true', '"paired_ai_producer_not_claimed": false')):
            with self.subTest(bad=bad[:80]):
                with self.assertRaises(RuntimeError):
                    parse_event_receipt(bad)
