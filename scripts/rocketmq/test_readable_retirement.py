import copy
import datetime as dt
import json
from pathlib import Path
import unittest

from readable_retirement import COUNTERS, plan_retirement, resources
from readable_transition import digest

ROOT = Path(__file__).resolve().parents[2]


class ReadableRetirementTest(unittest.TestCase):
    def setUp(self):
        base = ROOT / 'components/rocketmq'
        self.old = json.loads((base / 'serverd-routes-m3-v2.json').read_text())
        self.new = json.loads((base / 'serverd-routes-readable-v3.json').read_text())
        self.subjects = {role: 'existing-' + str(i) for i, role in enumerate(self.old['accounts'])}
        self.selected = sorted(resources(self.old))
        self.now = dt.datetime(2026, 10, 28, tzinfo=dt.timezone.utc)
        self.evidence = dict(schema='readable-retirement-observations/v1',
            previous_manifest_sha256=digest(self.old), active_manifest_sha256=digest(self.new),
            captured_at='2026-10-28T00:00:00Z', broker_version='5.5.1', cluster='RocketMQ',
            broker='127.0.0.1:10911', nameserver='nameserver:9876',
            cluster_masters=['127.0.0.1:10911'], old_runtimes_stopped=True,
            new_business_accepted=True, history_mapping_preserved=True,
            broker_topic_names=sorted({r['physical_topic'] for r in self.old['routes'] + self.new['routes']}),
            resources={name: dict.fromkeys(COUNTERS, 0) | {'export_sha256': 'a' * 64}
                       for name in self.selected})

    def plan(self):
        return plan_retirement(self.old, self.new, self.subjects, self.selected, self.evidence, self.now)

    def test_exact_commands_preserve_retry_dlq_and_active_resources(self):
        before = copy.deepcopy((self.old, self.new, self.subjects, self.selected, self.evidence))
        result = self.plan()
        self.assertFalse(result['execution_authorized'])
        self.assertTrue(result['read_only'])
        self.assertEqual(len(result['selected']), 19)
        self.assertEqual(result['retained'], [])
        groups = [c for c in result['commands'] if c[0] == 'deleteSubGroup']
        topics = [c for c in result['commands'] if c[0] == 'deleteTopic']
        self.assertEqual((len(groups), len(topics)), (9, 10))
        self.assertTrue(all('-b' in c and '-c' not in c and c[-2:] == ['-r', 'true'] for c in groups))
        self.assertTrue(all('-b' not in c and '-n' in c and '-c' in c for c in topics))
        self.assertTrue(all('-r' in c and c[c.index('-r') + 1] in self.selected
                            for c in result['commands'] if c[0] == 'deleteAcl'))
        self.assertFalse(any('%RETRY%' in str(c) or '%DLQ%' in str(c) for c in result['commands']))
        self.assertEqual(before, (self.old, self.new, self.subjects, self.selected, self.evidence))

    def test_nonzero_missing_boolean_negative_and_unknown_counters_reject(self):
        first = self.selected[0]
        for key in COUNTERS:
            for value in (1, -1, False, None, '0'):
                with self.subTest(key=key, value=value):
                    self.setUp()
                    self.evidence['resources'][first][key] = value
                    with self.assertRaises(ValueError):
                        self.plan()
            self.setUp()
            del self.evidence['resources'][first][key]
            with self.assertRaises(ValueError):
                self.plan()
        self.setUp()
        self.evidence['resources'][first]['unknown_counter'] = 0
        with self.assertRaises(ValueError):
            self.plan()

    def test_individually_clear_subset_retains_other_resources(self):
        keep = self.selected[1:]
        self.selected = self.selected[:1]
        self.evidence['resources'] = {r: self.evidence['resources'][r] for r in self.selected}
        result = self.plan()
        self.assertEqual(result['retained'], keep)
        self.assertTrue(all(c[c.index('-r') + 1] == self.selected[0]
                            for c in result['commands'] if c[0] == 'deleteAcl'))

    def test_missing_metadata_and_pop_retry_cascade_are_rejected_even_with_zero_counters(self):
        topic = next(r.removeprefix('Topic:') for r in self.selected if r.startswith('Topic:'))
        original = list(self.evidence['broker_topic_names'])
        for names in (None, [], original + [original[0]],
                      [name for name in original if name != topic],
                      original + ['%RETRY%unselected-group_' + topic],
                      original + ['%RETRY%unselected-group+' + topic]):
            self.evidence['broker_topic_names'] = names
            with self.subTest(names=names), self.assertRaises(ValueError):
                self.plan()
        self.evidence['broker_topic_names'] = original + ['%RETRY%other-group+other-topic']
        self.plan()

    def test_wildcards_active_system_unknown_and_duplicate_selection_reject(self):
        for selected in ([], ['Topic:*'], ['Topic:RMQ_SYS_TRANS_HALF_TOPIC'],
                         [next(iter(resources(self.new)))], ['Topic:unlisted'],
                         [self.selected[0], self.selected[0]]):
            with self.subTest(selected=selected):
                self.selected = selected
                with self.assertRaises(ValueError):
                    self.plan()

    def test_stale_future_changed_cluster_and_missing_exports_reject(self):
        for key, value in (('captured_at', '2026-10-27T23:59:44Z'),
                           ('captured_at', '2026-10-28T00:00:01Z'),
                           ('cluster_masters', ['127.0.0.1:10911', 'other:10911']),
                           ('old_runtimes_stopped', False), ('new_business_accepted', False),
                           ('history_mapping_preserved', False), ('broker_version', '5.5.0'),
                           ('active_manifest_sha256', 'b' * 64)):
            with self.subTest(key=key):
                self.setUp()
                self.evidence[key] = value
                with self.assertRaises(ValueError):
                    self.plan()
        self.setUp()
        self.evidence['resources'][self.selected[0]]['export_sha256'] = ''
        with self.assertRaises(ValueError):
            self.plan()

    def test_exact_roles_and_subjects_never_accept_credentials_or_duplicates(self):
        for damage in ('extra', 'missing', 'credentials', 'duplicate'):
            with self.subTest(damage=damage):
                self.setUp()
                role = next(iter(self.subjects))
                if damage == 'extra':
                    self.subjects['admin'] = 'administrator'
                elif damage == 'missing':
                    del self.subjects[role]
                elif damage == 'credentials':
                    self.subjects[role] = {'username': 'u', 'password': 'secret'}
                else:
                    self.subjects = dict.fromkeys(self.subjects, 'same-user')
                with self.assertRaises(ValueError):
                    self.plan()
