import json
import unittest

from qs_answer_acceptance import CASES, answer_manifest, parse_answer_receipt, answer_failure_signals
from routes import permissions_v2


class QSAnswerAcceptanceTest(unittest.TestCase):
    def test_exact_owner_and_minimum_acl(self):
        manifest = answer_manifest()
        route = manifest['routes'][0]
        self.assertEqual((route['topic'], route['message_type'], route['owner'], route['route_revision']),
                         ('qs.evaluation.lifecycle', 'TRANSACTION', 'qs.mongo', 'm3-1'))
        self.assertEqual(permissions_v2(manifest, manifest['accounts']['qs-answer-producer']),
                         {'Topic:' + route['physical_topic']: {'Pub', 'Get'}})
        self.assertEqual(permissions_v2(manifest, manifest['accounts']['qs-answer-observer']),
                         {'Topic:' + route['physical_topic']: {'Sub', 'Get'}, 'Group:' + route['consumer_group']: {'Sub', 'Get'}})

    def test_required_receipt_rejects_empty_skipped_partial_and_race(self):
        receipt = {'passed': len(CASES), 'failed': 0, 'skipped': 0, 'cases': {name: True for name in CASES},
                   'root_ack_discard_is_client_level': True, 'mongo_callback_failpoint': True,
                   'upstream_rpc': 'actual_protobuf_service_over_bufconn', 'system_login_not_claimed': True}
        output = 'M3_QS_ANSWER_RECEIPT ' + json.dumps(receipt) + '\n--- PASS: TestM3AnswerSubmissionBrokerHost (1.00s)\n'
        self.assertEqual(parse_answer_receipt(output), receipt)
        for bad in ('', output + output, output.replace('true', 'false', 1), output.replace('--- PASS:', '--- SKIP:'),
                    output + '\nWARNING: DATA RACE', output.replace('TestM3AnswerSubmissionBrokerHost', 'TestSDKProbe'),
                    output.replace('"passed": 16', '"passed": 0'), output.replace('"skipped": 0', '"skipped": 1'),
                    output.replace('actual_protobuf_service_over_bufconn', 'fake_service')):
            with self.assertRaises(RuntimeError):
                parse_answer_receipt(bad)

    def test_failure_signals_export_only_fixed_labels(self):
        private = 'secret-body-tenant-token'
        raw = private + '\nsubmission returned before original root\ncontext deadline exceeded: ' + private
        self.assertEqual(answer_failure_signals(raw), ['deadline', 'returned_before_root'])
        self.assertNotIn(private, json.dumps(answer_failure_signals(raw)))
        self.assertEqual(answer_failure_signals(private), [])
