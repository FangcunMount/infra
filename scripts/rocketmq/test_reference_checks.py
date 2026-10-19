"""Recovery evidence must identify the current message, never a global counter."""
import unittest

from sdk_acceptance import wait_reference_checks


class Recorder:
    def __init__(self):
        self.calls = []

    def wait(self, *args, **kwargs):
        self.calls.append((args, kwargs))


class ReferenceCheckTest(unittest.TestCase):
    def test_old_reference_aggregate_counter_or_wrong_decision_cannot_satisfy_current_case(self):
        probe = Recorder()
        prior = [{'event':'checked','id':'current-b0','decision':'rollback'},
                 {'event':'checked_reference','id':'old-b0','decision':'rollback'},
                 {'event':'checked_reference','id':'current-b0','decision':'commit'}]
        wait_reference_checks(probe, ['current-b0','current-b1'], 'rollback', observed=prior)
        self.assertEqual([call[0] for call in probe.calls],
                         [('checked_reference','current-b0','rollback'),
                          ('checked_reference','current-b1','rollback')])

    def test_exact_current_reference_from_drained_startup_attempt_is_reused(self):
        probe = Recorder()
        prior = [{'event':'checked_reference','id':'current-b0','decision':'commit'}]
        wait_reference_checks(probe, ['current-b0','current-b1'], 'commit', observed=prior)
        self.assertEqual([call[0] for call in probe.calls], [('checked_reference','current-b1','commit')])
