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
                if self.reads > 1 and missing == 'grants' and username == next(iter(acls)):
                    del value[next(iter(value))]
                return value
        return manifest, accounts, Admin()

    def test_missing_resources_fail_without_repeating_mutations_or_exporting_secrets(self):
        for missing in ('topics', 'groups', 'grants'):
            manifest, accounts, admin = self.fixture(missing)
            with self.subTest(missing=missing), patch('provision_v2.Admin', return_value=admin):
                with self.assertRaises(ProvisionReadbackError) as caught:
                    provision('unused', manifest, accounts)
                audit = caught.exception.audit_diagnostic
                self.assertEqual(audit['missing_counts'][missing], 1)
                self.assertEqual(sum(audit['missing_counts'].values()), 1)
                self.assertEqual(admin.operations, 1)
                self.assertEqual(admin.reads, 2)
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
