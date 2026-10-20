import json
import unittest

from qs_evaluation_acceptance import CASES, evaluation_manifest, parse_evaluation_receipt
from routes import permissions_v2


class QSEvaluationAcceptanceTest(unittest.TestCase):
    def test_exact_owner_and_minimum_acl(self):
        manifest = evaluation_manifest()
        route = manifest['routes'][0]
        self.assertEqual((route['topic'], route['message_type'], route['owner'], route['route_revision']),
                         ('qs.evaluation.lifecycle', 'TRANSACTION', 'qs.mysql', 'm3-1'))
        self.assertEqual(permissions_v2(manifest, manifest['accounts']['qs-evaluation-producer']),
                         {'Topic:' + route['physical_topic']: {'Pub', 'Get'}})
        self.assertEqual(permissions_v2(manifest, manifest['accounts']['qs-evaluation-observer']),
                         {'Topic:' + route['physical_topic']: {'Sub', 'Get'}, 'Group:' + route['consumer_group']: {'Sub', 'Get'}})

    def test_required_receipt_rejects_empty_skipped_partial_and_race(self):
        receipt = {'passed': len(CASES), 'failed': 0, 'skipped': 0, 'cases': {name: True for name in CASES},
                   'broker': 'actual_5.5.1', 'root': 'original_mysql_gorm',
                   'source_input': 'deterministic_fixture_not_system_account', 'process_exit_not_claimed': True}
        output = 'M3_QS_EVALUATION_RECEIPT ' + json.dumps(receipt) + '\n--- PASS: TestM3EvaluationBrokerHost (1.00s)\n'
        self.assertEqual(parse_evaluation_receipt(output), receipt)
        for bad in ('', output + output, output.replace('true', 'false', 1), output.replace('--- PASS:', '--- SKIP:'),
                    output + '\nWARNING: DATA RACE', output.replace('TestM3EvaluationBrokerHost', 'TestSDKProbe'),
                    output.replace('"passed": 6', '"passed": 0'), output.replace('"skipped": 0', '"skipped": 1'),
                    output.replace('original_mysql_gorm', 'fake_service')):
            with self.assertRaises(RuntimeError):
                parse_evaluation_receipt(bad)
