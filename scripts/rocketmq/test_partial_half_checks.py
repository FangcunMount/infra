"""Exact stage selection; real ACK loss and Broker recovery still require CI."""
import copy
import unittest

from sdk_faults import partial_half_rollback_checks


class PartialHalfChecksTest(unittest.TestCase):
    def setUp(self):
        self.result = {'local': 'not_started', 'local_calls': 0, 'branches': [
            {'message_id': 'case-b0', 'half': 'prepared', 'final': 'rollback_confirmed'},
            {'message_id': 'case-b1', 'half': 'unknown', 'final': 'not_attempted'},
            {'message_id': 'case-b2', 'half': 'not_attempted', 'final': 'not_attempted'}]}

    def test_confirmed_rollback_does_not_require_a_second_broker_check(self):
        self.assertEqual(partial_half_rollback_checks(self.result, 'case'), ['case-b1'])

    def test_unknown_first_rollback_requires_both_exact_prepared_halves(self):
        self.result['branches'][0]['final'] = 'unknown'
        self.assertEqual(partial_half_rollback_checks(self.result, 'case'), ['case-b0', 'case-b1'])

    def test_changed_identity_stages_or_started_business_cannot_pass(self):
        changes = [('local', 'committed'), ('local_calls', 1)]
        for key, value in changes:
            result = copy.deepcopy(self.result); result[key] = value
            with self.assertRaises(RuntimeError):
                partial_half_rollback_checks(result, 'case')
        for index, key, value in ((0, 'final', 'commit_confirmed'),
                                  (1, 'message_id', 'old-b1'),
                                  (1, 'half', 'rejected'),
                                  (2, 'half', 'prepared')):
            result = copy.deepcopy(self.result); result['branches'][index][key] = value
            with self.assertRaises(RuntimeError):
                partial_half_rollback_checks(result, 'case')
