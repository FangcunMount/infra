import unittest
from unittest.mock import Mock
from sdk_recovery_audit import require_records,validate_options


class RecoveryAuditTests(unittest.TestCase):
    def test_only_exact_positive_receipts_are_accepted(self):
        probe=Mock()
        require_records(probe,['original-a','original-b'],'commit_confirmed')
        self.assertEqual(probe.wait.call_count,2)
        probe.wait.assert_any_call('recovery_recorded','original-a','commit_confirmed',timeout=100)
        for outcome in ('unknown','commit','prepared'):
            with self.assertRaises(ValueError):require_records(probe,['original'],outcome)
        with self.assertRaises(ValueError):require_records(probe,[],'commit_confirmed')

    def test_standalone_profile_rejects_other_work_before_resources(self):
        options=dict(sdk_api_go=True,sdk_api_python=True,sdk_recovery_audit=True,
                     sdk='fixture',python='uv',qs_deferred_kind='mysql',sdk_faults=False)
        validate_options(options)
        for key in ('sdk_faults','native_dlq_audit','sdk_limits','paired_host','iam_host'):
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_options(dict(options,**{key:True}))
        with self.assertRaises(ValueError):validate_options(dict(options,sdk_api_python=False))


if __name__=='__main__':unittest.main()
