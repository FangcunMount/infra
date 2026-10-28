import copy
import datetime as dt
import json
from pathlib import Path
import unittest

import readable_legacy_retirement as target
import readable_retirement
from readable_transition import digest


class LegacyRetirementTest(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[2] / 'components/rocketmq'
        self.old = json.loads((root / 'serverd-routes.json').read_text())
        self.new = json.loads((root / 'serverd-routes-readable-v3.json').read_text())
        self.subjects = {role: 'rmq-' + role for role in self.old['accounts']}
        self.selected = sorted(target.resources(self.old))
        self.now = dt.datetime(2026, 10, 28, tzinfo=dt.timezone.utc)
        self.evidence = dict(schema='readable-retirement-observations/v1',
            previous_manifest_sha256=digest(self.old), active_manifest_sha256=digest(self.new),
            captured_at='2026-10-28T00:00:00Z', broker_version='5.5.1', cluster='FangcunMount',
            broker='127.0.0.1:10911', nameserver='nameserver:9876',
            cluster_masters=['127.0.0.1:10911'], old_runtimes_stopped=True,
            new_business_accepted=True, history_mapping_preserved=True,
            broker_topic_names=sorted({r['physical_topic'] for r in self.old['routes'] + self.new['routes']}),
            resources={name: dict.fromkeys(target.COUNTERS, 0) | {'export_sha256': 'a' * 64}
                       for name in self.selected})

    def plan(self):
        return target.review(self.old, self.new, self.subjects, self.selected, self.evidence, self.now)

    def test_explicit_v1_catalog_has_ten_topics_twelve_groups_and_exact_grants(self):
        before = copy.deepcopy((self.old, self.new, self.subjects, self.selected, self.evidence))
        p = self.plan(); self.assertEqual(len(p['selected']), 22)
        self.assertEqual(len([c for c in p['commands'] if c[0] == 'deleteTopic']), 10)
        self.assertEqual(len([c for c in p['commands'] if c[0] == 'deleteSubGroup']), 12)
        self.assertEqual(len([c for c in p['commands'] if c[0] == 'deleteAcl']), 29)
        self.assertFalse(p['execution_authorized']); self.assertTrue(p['read_only'])
        self.assertEqual(before, (self.old, self.new, self.subjects, self.selected, self.evidence))
        with self.assertRaises(ValueError):
            readable_retirement.plan_retirement(self.old, self.new, self.subjects, self.selected, self.evidence, self.now)

    def test_missing_nonzero_or_boolean_responsibility_never_means_zero(self):
        for key in target.COUNTERS:
            for value in (1, False, None):
                self.setUp(); self.evidence['resources'][self.selected[0]][key] = value
                with self.assertRaises(ValueError): self.plan()
        self.setUp(); del self.evidence['resources'][self.selected[0]]['export_sha256']
        with self.assertRaises(ValueError): self.plan()

    def test_stale_future_wrong_cluster_history_and_subjects_refused(self):
        for key, value in [('captured_at', '2026-10-27T23:59:44Z'),
                           ('captured_at', '2026-10-28T00:00:01Z'),
                           ('cluster_masters', ['other:10911']), ('history_mapping_preserved', False),
                           ('new_business_accepted', False), ('broker_version', '5.5.0')]:
            self.setUp(); self.evidence[key] = value
            with self.assertRaises(ValueError): self.plan()
        self.setUp(); self.subjects.pop(next(iter(self.subjects)))
        with self.assertRaises(ValueError): self.plan()

    def test_active_system_wildcard_unlisted_and_duplicate_objects_refused(self):
        for selected in [['Topic:*'], ['Topic:RMQ_SYS_TRANS_HALF_TOPIC'],
                         [next(iter(target.resources(self.new)))], ['Topic:unlisted'],
                         [self.selected[0], self.selected[0]]]:
            self.setUp(); self.selected = selected
            with self.assertRaises(ValueError): self.plan()

    def test_both_POP_retry_cascades_protected_and_clear_subset_is_individual(self):
        topic = next(r for r in self.selected if r.startswith('Topic:'))
        for separator in ['_', '+']:
            self.setUp(); self.evidence['broker_topic_names'].append('%RETRY%other-group' + separator + topic[6:])
            with self.assertRaises(ValueError): self.plan()
        self.setUp(); self.selected = [topic]; self.evidence['resources'] = {topic: self.evidence['resources'][topic]}
        p = self.plan(); self.assertEqual(len(p['retained']), 21)
        self.assertFalse(any(c[0] == 'deleteSubGroup' for c in p['commands']))


if __name__ == '__main__':
    unittest.main()
