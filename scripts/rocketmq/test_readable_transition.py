import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from provision_v2 import desired_topics, preflight, provision
from readable_transition import digest, merged_permissions, validate_transition
from routes import permissions_v2

ROOT = Path(__file__).resolve().parents[2]


class ReadableTransitionTest(unittest.TestCase):
    def setUp(self):
        base = ROOT / 'components/rocketmq'
        self.old = json.loads((base / 'serverd-routes-m3-v2.json').read_text())
        self.new = json.loads((base / 'serverd-routes-readable-v3.json').read_text())
        self.accounts = {role: {'username': role, 'password': str(i) * 64}
                         for i, role in enumerate(self.old['accounts'], 1)}
        self.users = {row['username']: (row['password'], 'Normal', 'Enable')
                      for row in self.accounts.values()}
        self.metadata = dict(topicConfigTable={}, subscriptionGroupTable={})
        self.install_resources(self.old)
        self.acls = {role: permissions_v2(self.old, grants)
                     for role, grants in self.old['accounts'].items()}

    def install_resources(self, manifest):
        for topic, value in desired_topics(manifest).items():
            self.metadata['topicConfigTable'][topic] = dict(value,
                attributes={'message.type': value['message_type']})
        for route in manifest['routes']:
            if route.get('consumer_group'):
                self.metadata['subscriptionGroupTable'][route['consumer_group']] = dict(
                    retryQueueNums=manifest['group_options']['retry_queue_nums'], consumeEnable=True)

    def prepare(self):
        return preflight(self.new, self.accounts, self.metadata, self.users, self.acls, previous=self.old)

    def test_only_reviewed_resource_and_permission_additions_without_new_users(self):
        before = copy.deepcopy((self.old, self.new, self.accounts, self.metadata, self.users, self.acls))
        topics, groups, users, grants = self.prepare()
        self.assertEqual((len(topics), len(groups), len(users)), (10, 9, 0))
        expected = {role: permissions_v2(self.new, value) for role, value in self.new['accounts'].items()}
        self.assertEqual(len(grants), sum(len(value) for value in expected.values()))
        self.assertTrue(all(resource in expected[role] and actions == expected[role][resource]
                            for role, resource, actions in grants))
        self.assertEqual(before, (self.old, self.new, self.accounts, self.metadata, self.users, self.acls))
        with self.assertRaises(RuntimeError):
            preflight(self.new, self.accounts, self.metadata, self.users, self.acls)

    def test_partial_union_is_idempotent_and_final_readback_requires_complete_union(self):
        old = validate_transition(self.old, self.new)
        _, _, _, grants = self.prepare()
        role, resource, actions = grants[0]
        self.acls[role][resource] = actions
        self.assertEqual(len(self.prepare()[3]), len(grants) - 1)
        self.install_resources(self.new)
        for role in self.new['accounts']:
            self.acls[role] = merged_permissions(self.new, role, old)
        self.assertEqual(self.prepare(), ([], [], [], []))
        role = next(iter(self.old['accounts']))
        resource = next(iter(old[role]))
        del self.acls[role][resource]
        with self.assertRaisesRegex(RuntimeError, 'prior application ACL'):
            self.prepare()

    def test_missing_or_changed_old_topics_groups_or_principals_are_never_recreated(self):
        for damage in ('topic_missing', 'topic_type', 'group_missing', 'group_disabled', 'user_missing'):
            with self.subTest(damage=damage):
                self.setUp()
                topic = next(iter(self.metadata['topicConfigTable']))
                group = next(iter(self.metadata['subscriptionGroupTable']))
                if damage == 'topic_missing':
                    del self.metadata['topicConfigTable'][topic]
                elif damage == 'topic_type':
                    self.metadata['topicConfigTable'][topic]['attributes']['message.type'] = 'FIFO'
                elif damage == 'group_missing':
                    del self.metadata['subscriptionGroupTable'][group]
                elif damage == 'group_disabled':
                    self.metadata['subscriptionGroupTable'][group]['consumeEnable'] = False
                else:
                    del self.users[next(iter(self.users))]
                with self.assertRaises(RuntimeError):
                    self.prepare()

    def test_permission_and_credential_drift_is_refused_before_resource_plan(self):
        for damage in ('wildcard', 'extra_action', 'missing_old', 'password', 'new_only'):
            with self.subTest(damage=damage):
                self.setUp()
                role = next(iter(self.accounts))
                resource = next(iter(self.acls[role]))
                if damage == 'wildcard':
                    self.acls[role]['Topic:*'] = {'Pub', 'Get'}
                elif damage == 'extra_action':
                    self.acls[role][resource].add('Update')
                elif damage == 'missing_old':
                    del self.acls[role][resource]
                elif damage == 'password':
                    self.accounts[role]['password'] = 'different' * 8
                else:
                    self.acls[role] = permissions_v2(self.new, self.new['accounts'][role])
                with self.assertRaises(RuntimeError):
                    self.prepare()

    def test_static_mapping_history_and_budget_drift_refuses_even_admin_construction(self):
        for damage in ('history', 'account', 'queues', 'groups', 'logical'):
            with self.subTest(damage=damage):
                self.setUp()
                if damage == 'history':
                    self.new['historical_routes'].pop()
                elif damage == 'account':
                    self.new['accounts'].pop(next(iter(self.new['accounts'])))
                elif damage == 'queues':
                    self.new['topic_options']['read_queue_nums'] = 2
                elif damage == 'groups':
                    self.new['group_options']['retry_queue_nums'] = 9
                else:
                    self.new['routes'][0]['route_revision'] = 'm3-2'
                with patch('provision_v2.Admin', side_effect=AssertionError('must not access Broker')):
                    with self.assertRaises(ValueError):
                        provision('unused', self.new, self.accounts, previous=self.old)

    def test_owned_native_profile_uses_complete_readable_manifest_and_original_roles(self):
        from m3_resources import resource_documents, expected_cases
        current, previous, path = resource_documents(ROOT, 'full', True)
        self.assertEqual(current, self.new)
        self.assertEqual(previous, self.old)
        self.assertEqual(path, 'components/rocketmq/serverd-routes-readable-v3.json')
        self.assertEqual(len(expected_cases(current)), 130)
        with self.assertRaises(ValueError):
            resource_documents(ROOT, 'bootstrap', True)
        legacy, previous, _ = resource_documents(ROOT, 'full', False)
        self.assertEqual(legacy, self.old)
        self.assertIsNone(previous)

    def test_negative_sentinels_keep_exact_selected_naming_codec(self):
        from m3_resources import conflict_route
        from routes import validate
        for document in (self.old, self.new):
            candidate = copy.deepcopy(document)
            row = conflict_route(document, 'never-create', 'infra.m3.never-created', 'NORMAL')
            candidate['routes'].append(row)
            candidate['accounts']['m3-iam']['publish'].append(row['id'])
            validate(candidate)
            self.assertEqual(row.get('naming_scheme', ''),
                             'readable-v1' if document['version'] == 3 else '')

    def test_manifest_digest_is_stable_and_any_reviewed_change_is_detectable(self):
        self.assertEqual(len(digest(self.new)), 64)
        self.assertEqual(digest(self.new), digest(copy.deepcopy(self.new)))
        changed = copy.deepcopy(self.new)
        changed['group_options']['retry_queue_nums'] += 1
        self.assertNotEqual(digest(changed), digest(self.new))
