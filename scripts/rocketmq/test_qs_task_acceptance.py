import json
import unittest

from qs_task_acceptance import CASES, task_manifest, parse_task_receipt
from routes import permissions_v2


class QSTaskAcceptanceTest(unittest.TestCase):
    def test_exact_owner_and_minimum_acl(self):
        manifest = task_manifest()
        route = manifest['routes'][0]
        self.assertEqual((route['topic'], route['message_type'], route['owner'], route['route_revision']),
                         ('qs.plan.task', 'TRANSACTION', 'qs.mysql', 'm3-1'))
        self.assertEqual(permissions_v2(manifest, manifest['accounts']['qs-task-producer']),
                         {'Topic:' + route['physical_topic']: {'Pub', 'Get'}})
        self.assertEqual(permissions_v2(manifest, manifest['accounts']['qs-task-observer']),
                         {'Topic:' + route['physical_topic']: {'Sub', 'Get'}, 'Group:' + route['consumer_group']: {'Sub', 'Get'}})

    def test_required_receipt_rejects_empty_skipped_partial_and_race(self):
        receipt = {'passed': len(CASES), 'failed': 0, 'skipped': 0, 'cases': {name: True for name in CASES},
                   'root': 'original_mysql_gorm',
                   'system_login_not_claimed': True, 'process_exit_not_claimed': True}
        output = 'M3_QS_TASK_RECEIPT ' + json.dumps(receipt) + '\n--- PASS: TestM3TaskBrokerHost (1.00s)\n'
        self.assertEqual(parse_task_receipt(output), receipt)
        for bad in ('', output + output, output.replace('true', 'false', 1), output.replace('--- PASS:', '--- SKIP:'),
                    output + '\nWARNING: DATA RACE', output.replace('TestM3TaskBrokerHost', 'TestSDKProbe'),
                    output.replace('"passed": 11', '"passed": 0'), output.replace('"skipped": 0', '"skipped": 1'),
                    output.replace('original_mysql_gorm', 'fake_service')):
            with self.assertRaises(RuntimeError):
                parse_task_receipt(bad)


    def test_normal_topics_have_independent_groups_and_cannot_publish_transaction_topic(self):
        manifest = task_manifest()
        routes = {route['id']: route for route in manifest['routes']}
        producer = manifest['accounts']['qs-normal-producer']
        permissions = permissions_v2(manifest, producer)
        self.assertNotIn('Topic:' + routes['qs-task-native']['physical_topic'], permissions)
        self.assertEqual(len(permissions), 2)
        first = permissions_v2(manifest, manifest['accounts']['qs-normal-a'])
        second = permissions_v2(manifest, manifest['accounts']['qs-normal-b'])
        self.assertEqual(len([key for key in first if key.startswith('Group:')]), 2)
        self.assertEqual(len([key for key in second if key.startswith('Group:')]), 2)
        self.assertFalse({key for key in first if key.startswith('Group:')} &
                         {key for key in second if key.startswith('Group:')})
