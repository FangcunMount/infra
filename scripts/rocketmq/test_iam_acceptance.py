import json
import unittest
import tempfile
from pathlib import Path

from iam_acceptance import iam_manifest, parse_host_receipt, host_failure_summary, retain_private_host_output, parse_fanout_receipt
from routes import permissions_v2


class IAMAcceptanceTest(unittest.TestCase):
    def test_failure_summary_never_exports_runtime_content(self):
        raw = ('--- FAIL: TestM3ActualBrokerHost (1s)\n'
               ' transaction_broker_host_integration_test.go:143: private token wire\n'
               'panic: test timed out after3m\n[build failed]')
        result = host_failure_summary(raw)
        self.assertEqual(result, {'build_failed': True, 'test_timeout': True,
                                 'failed_tests': ['TestM3ActualBrokerHost'], 'assertion_lines': [143],
                                 'race_reports': 0, 'race_frames': []})
        self.assertNotIn('private', json.dumps(result))

    def test_race_summary_exports_only_stack_file_and_line(self):
        raw = ('WARNING: DATA RACE\nRead at 0x123 private wire\n'
               'secret.Function(private-token)\n'
               '  /private/host/client.go:19 +0x38\n'
               'Previous write at 0x123\n'
               '  /owned/path/subscriber.go:47 +0x29\n'
               '==================\nsecret.go:918: private wire')
        result = host_failure_summary(raw)
        self.assertEqual(result['race_reports'], 1)
        self.assertEqual(result['race_frames'], ['client.go:19', 'subscriber.go:47'])
        exported = json.dumps(result)
        for secret in ('private', 'token', 'secret.go', '0x123', 'Function', '/owned'):
            self.assertNotIn(secret, exported)

    def test_explicit_private_capture_refuses_shared_or_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); root.chmod(0o700)
            path = root / 'owned.log'
            retain_private_host_output(path, 'private test fixture only')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                retain_private_host_output(path, 'replacement')
            self.assertEqual(path.read_text(), 'private test fixture only')
            root.chmod(0o755)
            with self.assertRaises(RuntimeError):
                retain_private_host_output(root / 'shared.log', 'private')
            self.assertFalse((root / 'shared.log').exists())
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

    def test_fanout_uses_three_independent_minimum_subscriber_groups(self):
        manifest = iam_manifest(fanout=True)
        routes = manifest['routes']
        self.assertEqual(len({r['physical_topic'] for r in routes}), 1)
        self.assertEqual(len({r['consumer_group'] for r in routes}), 4)
        for account in ('iam-fanout-a', 'iam-fanout-b', 'qs-fanout'):
            permissions = permissions_v2(manifest, manifest['accounts'][account])
            self.assertEqual(len(permissions), 2)
            self.assertTrue(all(actions == {'Sub', 'Get'} for actions in permissions.values()))

    def test_fanout_profile_cannot_accept_old_or_partial_receipt(self):
        receipt = dict(iam_instances=2, iam_revocation_observed=True,
                       qs_notification_received=True, qs_both_subjects_evicted=True,
                       qs_primary_proof_verified=True, qs_subscriber_drained=True, failed=0, skipped=0)
        output = 'M3_FANOUT_RECEIPT ' + json.dumps(receipt)
        self.assertEqual(parse_fanout_receipt(output), receipt)
        for invalid in ('', output + '\n' + output, output.replace('true', 'false', 1),
                        output.replace('"iam_instances": 2', '"iam_instances": 1')):
            with self.assertRaises(RuntimeError):
                parse_fanout_receipt(invalid)

    def test_receipt_requires_real_named_test_and_every_nonempty_proof(self):
        receipt = {'passed': 4, 'failed': 0, 'skipped': 0, 'half_invisible': True,
                   'commit_wire_and_witness': True, 'application_entry': True, 'rollback_hidden': True}
        output = 'M3_HOST_RECEIPT ' + json.dumps(receipt) + '\n--- PASS: TestM3ActualBrokerHost (1.00s)\n'
        self.assertEqual(parse_host_receipt(output), receipt)
        with self.assertRaises(RuntimeError):
            parse_host_receipt(output, require_business_result=True)
        with_result = output.replace('"rollback_hidden": true', '"rollback_hidden": true, "business_result_atomic": true')
        self.assertTrue(parse_host_receipt(with_result, require_business_result=True)['business_result_atomic'])
        for altered in (output.replace('--- PASS:', '--- SKIP:'), output.replace('true', 'false', 1),
                        output.replace('TestM3ActualBrokerHost', 'TestUnrelated'), output + output):
            with self.assertRaises(RuntimeError):
                parse_host_receipt(altered)


if __name__ == '__main__':
    unittest.main()
