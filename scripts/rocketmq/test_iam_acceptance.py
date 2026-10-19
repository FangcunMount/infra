import json
import unittest

from iam_acceptance import iam_manifest, parse_host_receipt
from routes import permissions_v2


class IAMAcceptanceTest(unittest.TestCase):
    def test_exact_owner_type_revision_and_minimum_permissions(self):
        manifest = iam_manifest()
        route = manifest['routes'][0]
        self.assertEqual((route['owner'], route['message_type'], route['route_revision']),
                         ('iam.mysql', 'TRANSACTION', 'm3-1'))
        pub = permissions_v2(manifest, manifest['accounts']['iam-producer'])
        sub = permissions_v2(manifest, manifest['accounts']['iam-observer'])
        self.assertEqual(pub, {'Topic:' + route['physical_topic']: {'Pub', 'Get'}})
        self.assertEqual(sub, {'Topic:' + route['physical_topic']: {'Sub', 'Get'},
                              'Group:' + route['consumer_group']: {'Sub', 'Get'}})

    def test_receipt_requires_real_named_test_and_every_nonempty_proof(self):
        receipt = {'passed': 4, 'failed': 0, 'skipped': 0, 'half_invisible': True,
                   'commit_wire_and_witness': True, 'application_entry': True, 'rollback_hidden': True}
        output = 'M3_HOST_RECEIPT ' + json.dumps(receipt) + '\n--- PASS: TestM3ActualBrokerHost (1.00s)\n'
        self.assertEqual(parse_host_receipt(output), receipt)
        for altered in (output.replace('--- PASS:', '--- SKIP:'), output.replace('true', 'false', 1),
                        output.replace('TestM3ActualBrokerHost', 'TestUnrelated'), output + output):
            with self.assertRaises(RuntimeError):
                parse_host_receipt(altered)


if __name__ == '__main__':
    unittest.main()
