import json
import unittest

from qs_replan_acceptance import CASES, commit_states, diagnostics, enabled, receipt


class QSReplanAcceptanceTest(unittest.TestCase):
    def test_commit_diagnostics_are_allowlisted_and_bounded_even_for_forged_error_lines(self):
        value=dict(local='unknown',business_calls=0,ready=False,admission_closed=True,
            lease_expired=False, mysql_number=1146,
            protection=dict(available=True,fresh=True,protected=True,reason='metadata_conflict',wire='SECRET'),
            branches=[dict(half='not_attempted',final='not_attempted',code='',reference='SECRET')],
            execution_token='SECRET',error='SECRET')
        raw='READABLE_REPLAN_COMMIT_STATE '+json.dumps(value)
        state=commit_states(raw)[0]
        self.assertTrue(state['admission_closed']);self.assertEqual(state['mysql_number'],1146)
        self.assertEqual(state['protection'],dict(available=True,fresh=True,protected=True,reason='metadata_conflict'))
        self.assertEqual(state['branches'],[dict(half='not_attempted',final='not_attempted',code='')])
        self.assertNotIn('SECRET',json.dumps(state))
        for key in ('local','business_calls','ready','mysql_number'):value[key]='SECRET'
        value['protection']['reason']=['SECRET']
        value['branches']=[dict(half='SECRET',final=[],code='SECRET',error='SECRET')]*32
        bad='READABLE_REPLAN_COMMIT_STATE '+json.dumps(value)
        states=commit_states('\n'.join([bad]*8))
        self.assertEqual(len(states),4);self.assertEqual(len(states[0]['branches']),16)
        self.assertNotIn('SECRET',json.dumps(states))
        self.assertEqual(commit_states('READABLE_REPLAN_COMMIT_STATE []\nREADABLE_REPLAN_COMMIT_STATE broken'),[])

    def test_failure_diagnostics_preserve_exact_lines_and_fixed_stages_without_runtime_contents(self):
        raw = ('/private/source/readable_owned_replan_test.go:146: READABLE_REPLAN_STAGE replan\n'
               'Error Trace: /private/source/readable_owned_replan_test.go:152\n'
               'Expected: "aborted" Actual: "unknown" password=synthetic-secret wire=DO-NOT-EXPORT\n'
               'READABLE_REPLAN_STAGE unreviewed_secret\n--- FAIL: TestReadableCrossRouteReplanBrokerHost (0.1s)')
        result=diagnostics(raw)
        self.assertEqual(result['assertion_lines'],[152])
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
