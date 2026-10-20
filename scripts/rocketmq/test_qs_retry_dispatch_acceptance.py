import json
import unittest

from qs_retry_dispatch_acceptance import CASES, parse_dispatch_receipt


class QSRetryDispatchAcceptanceTest(unittest.TestCase):
    def output(self, owner):
        receipt = {'owner': owner, 'passed': len(CASES), 'failed': 0, 'skipped': 0,
                   'cases': {name: True for name in CASES},
                   'system_login_not_claimed': True, 'business_consumer_not_claimed': True}
        name = 'TestM3FailureBrokerHost' if owner == 'qs.mysql' else 'TestM3ReportTerminalBrokerHost'
        return 'M3_QS_RETRY_DISPATCH_RECEIPT ' + json.dumps(receipt) + '\n--- PASS: ' + name + ' (30.00s)'

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
