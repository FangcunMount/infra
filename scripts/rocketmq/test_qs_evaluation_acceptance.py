import json
import unittest

from qs_evaluation_acceptance import EVALUATION_CASES as CASES, evaluation_manifest, parse_evaluation_receipt
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

class QSFailureReceiptTest(unittest.TestCase):
    def test_combined_gate_requires_actual_failure_entry_and_all_future_responsibility(self):
        from qs_evaluation_acceptance import FAILURE_CASES, parse_host_receipt
        evaluation = {'passed': len(CASES), 'failed': 0, 'skipped': 0,
                      'cases': {name: True for name in CASES}, 'broker': 'actual_5.5.1',
                      'root': 'original_mysql_gorm', 'source_input': 'deterministic_fixture_not_system_account',
                      'process_exit_not_claimed': True}
        failure = {'passed': len(FAILURE_CASES), 'failed': 0, 'skipped': 0,
                   'cases': {name: True for name in FAILURE_CASES}, 'root': 'original_mysql_gorm',
                   'source_input': 'controlled_input_failure_no_provider', 'process_exit_not_claimed': True}
        first = 'M3_QS_EVALUATION_RECEIPT ' + json.dumps(evaluation) + '\n--- PASS: TestM3EvaluationBrokerHost (1s)\n'
        second = 'M3_QS_FAILURE_RECEIPT ' + json.dumps(failure) + '\n--- PASS: TestM3FailureBrokerHost (1s)\n'
        self.assertEqual(parse_host_receipt(first + second)['passed'], len(CASES) + len(FAILURE_CASES))
        for bad in (first, second, first + second + second,
                    (first + second).replace('controlled_input_failure_no_provider', 'fake_writer'),
                    (first + second).replace('"future_retry_retains_due_authorization_and_wire": true',
                                             '"future_retry_retains_due_authorization_and_wire": false'),
                    first + second + '\n--- SKIP: DependencyUnavailable'):
            with self.assertRaises(RuntimeError):
                parse_host_receipt(bad)
