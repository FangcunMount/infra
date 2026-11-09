import unittest

from m5_window_direct_observe import EXPECTED, PREFIX, owner_samples


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
