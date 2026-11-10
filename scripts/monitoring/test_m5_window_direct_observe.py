import unittest
from unittest.mock import Mock, patch

from m5_window_direct_observe import BUSINESS_GAUGES, EXPECTED, PREFIX, business_samples, observe, owner_samples


def metric(name, value, owner='qs.mysql'):
    return f'{PREFIX}{name}{{owner="{owner}",protocol="rocketmq"}} {value}'


class OwnerSampleTests(unittest.TestCase):
    def test_missing_owner_remains_missing(self):
        raw = '\n'.join(metric(name, value) for name, value in EXPECTED.items())
        self.assertEqual(owner_samples(raw, {'qs.mysql', 'qs.mongo'}), {'qs.mysql': EXPECTED, 'qs.mongo': {}})

    def test_conflicting_or_wrong_owner_samples_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            owner_samples(metric('observation_fresh', 0) + '\n' + metric('observation_fresh', 1), {'qs.mysql'})
        with self.assertRaisesRegex(ValueError, 'unexpected_owner'):
            owner_samples(metric('observation_fresh', 1, 'ai.mysql'), {'qs.mysql'})


    def test_business_samples_keep_missing_ack_distinct_from_zero(self):
        available, waiting = BUSINESS_GAUGES['qs']
        self.assertEqual({available: 0, waiting: None}, business_samples(f'{available} 0', (available, waiting)))
        self.assertEqual({available: 1, waiting: 0}, business_samples(f'{available} 1\n{waiting} 0', (available, waiting)))

    def test_conflicting_or_malformed_business_samples_refuse(self):
        _, name = BUSINESS_GAUGES['qs']
        for raw in (f'{name} 1\n{name} 0', f'{name}{{replica="other"}} 1', f'{name} NaN', f'{name} 0.5'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                business_samples(raw, (name,))

    def test_observation_includes_six_readiness_endpoints_and_three_metric_sources(self):
        ok = Mock(return_value={'passed': True})
        with patch('m5_window_direct_observe.query', ok), patch('m5_window_direct_observe.time.sleep'):
            result = observe()
        self.assertTrue(result['passed'])
        self.assertFalse(result['writer_exclusion_verified'])
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(18, ok.call_count)
        expected = {'api-ready', 'collection-1-ready', 'collection-2-ready',
                    'worker-1', 'worker-2', 'worker-3', 'qs', 'ai', 'iam'}
        for frame in result['rounds']:
            self.assertEqual(expected, set(frame['results']))
