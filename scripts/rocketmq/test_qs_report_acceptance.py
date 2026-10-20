import json
import unittest

from qs_report_acceptance import CASES, report_manifest, parse_report_receipt
from routes import permissions_v2


class QSReportAcceptanceTest(unittest.TestCase):
    def test_exact_owner_and_minimum_acl(self):
        manifest = report_manifest()
        route = manifest['routes'][0]
        self.assertEqual((route['topic'], route['message_type'], route['owner'], route['route_revision']),
                         ('assessment-lifecycle', 'TRANSACTION', 'qs.mongo', 'm3-1'))
        self.assertEqual(permissions_v2(manifest, manifest['accounts']['qs-report-producer']),
                         {'Topic:' + route['physical_topic']: {'Pub', 'Get'}})
        self.assertEqual(permissions_v2(manifest, manifest['accounts']['qs-report-observer']),
                         {'Topic:' + route['physical_topic']: {'Sub', 'Get'}, 'Group:' + route['consumer_group']: {'Sub', 'Get'}})

    def test_required_receipt_rejects_empty_skipped_partial_and_race(self):
        receipt = {'passed': len(CASES), 'failed': 0, 'skipped': 0, 'cases': {name: True for name in CASES},
                   'root_ack_discard_is_client_level': True, 'mongo_callback_failpoint': True,
                   'host_entry': 'interpretation_original_root_committer', 'system_login_not_claimed': True}
        output = 'M3_QS_REPORT_RECEIPT ' + json.dumps(receipt) + '\n--- PASS: TestM3ReportTerminalBrokerHost (1.00s)\n'
        self.assertEqual(parse_report_receipt(output), receipt)
        for bad in ('', output + output, output.replace('true', 'false', 1), output.replace('--- PASS:', '--- SKIP:'),
                    output + '\nWARNING: DATA RACE', output.replace('TestM3ReportTerminalBrokerHost', 'TestSDKProbe'),
                    output.replace('"passed": 13', '"passed": 0'), output.replace('"skipped": 0', '"skipped": 1'),
                    output.replace('interpretation_original_root_committer', 'fake_service')):
            with self.assertRaises(RuntimeError):
                parse_report_receipt(bad)
