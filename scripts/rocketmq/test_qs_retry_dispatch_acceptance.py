import json
import unittest

from qs_retry_dispatch_acceptance import CASES, parse_dispatch_receipt, readable_future_mode


class QSRetryDispatchAcceptanceTest(unittest.TestCase):
    def output(self, owner):
        receipt = {'owner': owner, 'passed': len(CASES), 'failed': 0, 'skipped': 0,
                   'cases': {name: True for name in CASES},
                   'system_login_not_claimed': True, 'business_consumer_not_claimed': True}
        name = 'TestM3FailureBrokerHost' if owner == 'qs.mysql' else 'TestM3ReportTerminalBrokerHost'
        return 'M3_QS_RETRY_DISPATCH_RECEIPT ' + json.dumps(receipt) + '\n--- PASS: ' + name + ' (30.00s)'

    def test_readable_future_is_an_explicit_owned_profile_and_defaults_stay_legacy(self):
        self.assertFalse(readable_future_mode({}))
        self.assertFalse(readable_future_mode({'QS_M3_READABLE_FUTURE':'0'}))
        trusted=dict(QS_M3_READABLE_FUTURE='1',GITHUB_ACTIONS='true',RUNNER_OS='Linux',RUNNER_ENVIRONMENT='github-hosted')
        self.assertTrue(readable_future_mode(trusted))
        for row in ({'QS_M3_READABLE_FUTURE':'yes'}, {'QS_M3_READABLE_FUTURE':'1'},
                    dict(trusted,DOCKER_CONTEXT='production'),dict(trusted,RUNNER_ENVIRONMENT='self-hosted')):
            with self.assertRaises(ValueError):readable_future_mode(row)

    def test_each_exact_owner_and_real_host_required(self):
        for owner in ('qs.mysql', 'qs.mongo'):
            self.assertEqual(parse_dispatch_receipt(self.output(owner), owner)['owner'], owner)
            with self.assertRaises(RuntimeError):
                parse_dispatch_receipt(self.output(owner), 'iam.mysql')

    def test_reject_partial_duplicate_skip_race_and_wrong_host(self):
        good = self.output('qs.mysql')
        for bad in ('', good + '\n' + good, good.replace('true', 'false', 1),
                    good.replace('--- PASS:', '--- SKIP:'), good + '\nWARNING: DATA RACE',
                    good.replace('TestM3FailureBrokerHost', 'TestSDKProbe'),
                    good.replace('"skipped": 0', '"skipped": 1'),
                    good.replace('qs.mysql', 'qs.mongo')):
            with self.assertRaises(RuntimeError):
                parse_dispatch_receipt(bad, 'qs.mysql')
