import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from provision_v2 import ProvisionReadbackError, desired_topics, provision
from routes import permissions_v2


class ProvisionReadbackTest(unittest.TestCase):
    def fixture(self, missing):
        root = Path(__file__).resolve().parents[2]
        manifest = json.loads((root / 'components/rocketmq/test-routes-v2.json').read_text())
        accounts = {role: dict(username='private-' + role, password=str(i) * 64)
                    for i, role in enumerate(manifest['accounts'], 1)}
        metadata = dict(topicConfigTable={}, subscriptionGroupTable={})
        for topic, expected in desired_topics(manifest).items():
            metadata['topicConfigTable'][topic] = dict(expected, attributes={'message.type': expected['message_type']})
        for route in manifest['routes']:
            if route.get('consumer_group'):
                metadata['subscriptionGroupTable'][route['consumer_group']] = dict(
                    retryQueueNums=manifest['group_options']['retry_queue_nums'], consumeEnable=True)
        users = {a['username']: (a['password'], 'Normal', 'Enable') for a in accounts.values()}
        acls = {accounts[role]['username']: permissions_v2(manifest, grants)
                for role, grants in manifest['accounts'].items()}

        class Admin:
            operations = 0
            reads = 0
            def docker(self, *args, **kwargs): return SimpleNamespace(returncode=0)
            def __call__(self, *args, mutation=False):
                self.operations += int(mutation)
                return ''
            def metadata(self, directory):
                self.reads += 1
                value = copy.deepcopy(metadata)
                if self.reads == 1 or missing == 'topics':
                    del value['topicConfigTable'][next(iter(value['topicConfigTable']))]
                if self.reads > 1 and missing == 'groups':
                    del value['subscriptionGroupTable'][next(iter(value['subscriptionGroupTable']))]
                return value
            def users(self): return users
            def acl(self, username):
                value = copy.deepcopy(acls[username])
                if (self.reads > 1 and missing == 'grants' or self.reads == 2 and missing == 'delayed_grant') and username == next(iter(acls)):
                    del value[next(iter(value))]
                if self.reads > 1 and missing == 'conflict':
                    value['Topic:*'] = {'Pub', 'Get'}
                return value
        return manifest, accounts, Admin()

    def test_missing_resources_fail_without_repeating_mutations_or_exporting_secrets(self):
        for missing in ('topics', 'groups', 'grants'):
            manifest, accounts, admin = self.fixture(missing)
            with self.subTest(missing=missing), patch('provision_v2.Admin', return_value=admin), patch('provision_v2.time.sleep') as sleep:
                with self.assertRaises(ProvisionReadbackError) as caught:
                    provision('unused', manifest, accounts)
                audit = caught.exception.audit_diagnostic
                self.assertEqual(audit['missing_counts'][missing], 1)
                self.assertEqual(sum(audit['missing_counts'].values()), 1)
                self.assertEqual(admin.operations, 1)
                self.assertEqual(admin.reads, 4)
                self.assertEqual(sleep.call_count, 2)
                self.assertEqual(len(audit['observations']), 3)
                self.assertIs(audit['mutation_retry_attempted'], False)
                encoded = json.dumps(audit)
                for account in accounts.values():
                    self.assertNotIn(account['username'], encoded)
                    self.assertNotIn(account['password'], encoded)

    def test_complete_readback_still_requires_one_mutation_and_positive_verification(self):
        manifest, accounts, admin = self.fixture(None)
        with patch('provision_v2.Admin', return_value=admin):
            result = provision('unused', manifest, accounts)
        self.assertIs(result['verified'], True)
        self.assertEqual(result['operations'], 1)
        self.assertEqual(admin.reads, 2)

    def test_delayed_read_visibility_must_converge_without_a_second_mutation(self):
        manifest, accounts, admin = self.fixture('delayed_grant')
        with patch('provision_v2.Admin', return_value=admin), patch('provision_v2.time.sleep') as sleep:
            result = provision('unused', manifest, accounts)
        self.assertIs(result['verified'], True)
        self.assertEqual(admin.operations, 1)
        self.assertEqual(admin.reads, 3)
        self.assertEqual(sleep.call_count, 1)
        self.assertEqual(result['readback']['attempts'], 2)
        self.assertEqual(result['readback']['observations'][0]['missing_counts']['grants'], 1)
        self.assertEqual(sum(result['readback']['observations'][-1]['missing_counts'].values()), 0)

    def test_conflicting_snapshot_is_refused_without_waiting_for_a_later_snapshot(self):
        manifest, accounts, admin = self.fixture('conflict')
        with patch('provision_v2.Admin', return_value=admin), patch('provision_v2.time.sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError, 'exceeds or conflicts'):
                provision('unused', manifest, accounts)
        self.assertEqual(admin.operations, 1)
        self.assertEqual(admin.reads, 2)
        sleep.assert_not_called()
