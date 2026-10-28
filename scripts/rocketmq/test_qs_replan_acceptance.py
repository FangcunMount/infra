import json
import unittest

from qs_replan_acceptance import CASES, diagnostics, enabled, receipt


class QSReplanAcceptanceTest(unittest.TestCase):
    def test_failure_diagnostics_preserve_exact_lines_and_fixed_stages_without_runtime_contents(self):
        raw = ('/private/source/readable_owned_replan_test.go:146: READABLE_REPLAN_STAGE replan\n'
               'Error Trace: /private/source/readable_owned_replan_test.go:152\n'
               'Expected: "aborted" Actual: "unknown" password=synthetic-secret wire=DO-NOT-EXPORT\n'
               'READABLE_REPLAN_STAGE unreviewed_secret\n--- FAIL: TestReadableCrossRouteReplanBrokerHost (0.1s)')
        result=diagnostics(raw)
        self.assertEqual(result['assertion_lines'],[146,152])
        self.assertEqual(result['stages'],['replan'])
        self.assertEqual(result['failed_tests'],['TestReadableCrossRouteReplanBrokerHost'])
        serialized=json.dumps(result)
        for value in ('synthetic-secret','DO-NOT-EXPORT','/private/source','unreviewed_secret','Expected:'):
            self.assertNotIn(value,serialized)

    def test_explicit_owned_profile_only_and_legacy_default_unchanged(self):
        self.assertFalse(enabled({},False));self.assertFalse(enabled({},True))
        good=dict(QS_M3_READABLE_REPLAN='1',GITHUB_ACTIONS='true',RUNNER_OS='Linux',RUNNER_ENVIRONMENT='github-hosted')
        self.assertTrue(enabled(good,True))
        for env,readable in ((good,False),({'QS_M3_READABLE_REPLAN':'yes'},True),
            ({'QS_M3_READABLE_REPLAN':'1'},True),(dict(good,DOCKER_HOST='production'),True)):
            with self.subTest(env=env),self.assertRaises(ValueError):enabled(env,readable)

    def test_real_host_pass_and_complete_exact_case_and_source_required(self):
        value=dict(passed=5,failed=0,skipped=0,cases=dict.fromkeys(CASES,True),source_sha='a'*40,
            scope='actual_mysql_host_root_and_readable_broker_no_provider_or_system')
        raw='READABLE_REPLAN_RECEIPT '+json.dumps(value)+'\n--- PASS: TestReadableCrossRouteReplanBrokerHost (1.00s)'
        self.assertEqual(receipt(raw,'a'*40),value)
        for bad in ('',raw+'\n'+raw,raw.replace('--- PASS:','--- SKIP:'),raw+'\nWARNING: DATA RACE',
            raw.replace('"skipped": 0','"skipped": 1'),raw.replace('"passed": 5','"passed": true'),
            raw.replace('"historical_ordinary_retry_refused": true','"historical_ordinary_retry_refused": false')):
            with self.assertRaises(RuntimeError):receipt(bad,'a'*40)
        with self.assertRaises(RuntimeError):receipt(raw,'b'*40)
