import copy
import json
from pathlib import Path
import unittest

from routes import consumer_group_v3, physical_topic_v3, validate

ROOT = Path(__file__).resolve().parents[2]


class ReadableRoutes(unittest.TestCase):
    def manifest(self):
        return json.loads((ROOT / 'components/rocketmq/serverd-routes-readable-v3.json').read_text())

    def test_frozen_names_and_current_resource_counts(self):
        m = self.manifest()
        validate(m)
        self.assertEqual(len(m['routes']), 12)
        self.assertEqual(len({r['physical_topic'] for r in m['routes']}), 10)
        self.assertEqual(len({r['consumer_group'] for r in m['routes'] if r['subscription']}), 9)
        self.assertEqual(len(m['historical_routes']), 12)
        for r in m['routes']:
            self.assertEqual(r['physical_topic'], physical_topic_v3(r['topic'], r['message_type'], r['owner'], r['route_revision']))
            if r['subscription']:
                self.assertEqual(r['consumer_group'], consumer_group_v3(r['topic'], r['subscription']))
            self.assertLessEqual(len(r['physical_topic']), 64)

    def test_ambiguous_normalization_is_rejected(self):
        m = self.manifest()
        a = copy.deepcopy(m['routes'][0])
        a.update(id='collision', topic=a['topic'].replace('.', '-'))
        m['routes'].append(a)
        with self.assertRaises(ValueError):
            validate(m)
        m = self.manifest()
        a = copy.deepcopy(m['routes'][0])
        a.update(id='group-collision', subscription=a['subscription'].replace('.', '-'))
        m['routes'].append(a)
        with self.assertRaises(ValueError):
            validate(m)

    def test_invalid_fields_and_overlength_never_fall_back(self):
        for field in ('', 'Upper', 'a--b', 'a..b', 'a.-b', 'a_b', 'a b', '中文', 'a\0b'):
            with self.assertRaises(ValueError):
                physical_topic_v3(field, 'NORMAL', 'qs.mysql', 'm3-1')
        for value in ('FIFO', 'DELAY', 'normal'):
            with self.assertRaises(ValueError):
                physical_topic_v3('topic', value, 'qs.mysql', 'm3-1')
        with self.assertRaises(ValueError):
            consumer_group_v3('a' * 40, 'b' * 24)
        with self.assertRaises(ValueError):
            physical_topic_v3('a' * 48, 'NORMAL', 'qs.mysql', 'm3-1')

    def test_scheme_and_history_are_explicit_and_disjoint(self):
        for mutate in (lambda m: m['routes'][0].update(naming_scheme='unknown'),
                       lambda m: m['historical_routes'][0].update(naming_scheme='readable-v1'),
                       lambda m: m['historical_routes'].append(copy.deepcopy(m['routes'][0]))):
            m = self.manifest()
            mutate(m)
            with self.assertRaises(ValueError):
                validate(m)


if __name__ == '__main__':
    unittest.main()
