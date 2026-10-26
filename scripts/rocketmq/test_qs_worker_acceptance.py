import json
import unittest
from pathlib import Path
from qs_worker_acceptance import CASES, SCOPE, parse_worker_receipt, worker_failure_diagnostics, worker_manifest

class WorkerRuntimeReceiptTest(unittest.TestCase):
    def output(self):
        receipt = dict(source_sha='a'*40, passed=len(CASES), failed=0, skipped=0,
                       cases={case: True for case in CASES}, scope=SCOPE,
                       complete_apiserver_not_claimed=True, provider_not_called=True,
                       system_login_not_claimed=True, owned_database_dropped=True, owned_runtime_drained=True, paused_observation_ms=25, fixture_shared_limit=1, fixture_observation_budget_ms=60000)
        return 'M3_QS_WORKER_RUNTIME_RECEIPT '+json.dumps(receipt)+'\n--- PASS: TestM3WorkerRocketMQRuntime (1.00s)'

    def test_exact_worker_source_scope_cases_cleanup(self):
        self.assertEqual(parse_worker_receipt(self.output(), 'a'*40)['passed'], 4)

    def test_refuses_wrong_source_scope_partial_cleanup_skip_race(self):
        output=self.output()
        for bad in ('',output+'\n'+output,output.replace('a'*40,'b'*40),output.replace('60000','20000'),output.replace('"paused_observation_ms": 25','"paused_observation_ms": -1'),
                    output.replace('"failed": 0','"failed": 1'), output.replace('"skipped": 0','"skipped": 1'),
                    output.replace('true','false',1),output.replace(SCOPE,'production system acceptance'),
                    output.replace('"owned_runtime_drained": true','"owned_runtime_drained": false'),
                    output.replace('TestM3WorkerRocketMQRuntime','TestSDKProbe'),
                    output+'\nWARNING: DATA RACE',output+'\n--- SKIP: optional (0s)'):
            with self.subTest(bad=bad[:80]):
                with self.assertRaises(RuntimeError):
                    parse_worker_receipt(bad, 'a'*40)

    def test_bounded_failure_facts_reject_identity_payload_and_non_finite_counts(self):
        value=dict(phase='paused_delivery', active=1, waiting=0, holds=0, evidence=0,
                   query_failed=False, consume_outcomes={'hold_failed': 1}, transport_errors={'deadline': 1}, sdk_stack_sites={'subscriber:170': 1}, sdk_stack_truncated=False)
        self.assertEqual(worker_failure_diagnostics('M3_WORKER_DIAGNOSTIC '+json.dumps(value)), value)
        active=dict(value, phase='active_delivery')
        self.assertEqual(worker_failure_diagnostics('M3_WORKER_DIAGNOSTIC '+json.dumps(active)),active)
        self.assertIsNone(worker_failure_diagnostics(''))
        for bad in (dict(value, wire='forbidden'),dict(value, phase='arbitrary'),dict(value, active=True),
                    dict(value, consume_outcomes={'identity-label': 1}),dict(value, holds=-1),dict(value,sdk_stack_sites={'raw-body':1}),dict(value,sdk_stack_sites={'subscriber:170':100}),dict(value, transport_errors={'raw-error': 1}),dict(value, transport_errors={'other': 9}),
                    dict(value, consume_outcomes={'held': float('nan')})):
            self.assertEqual(worker_failure_diagnostics('M3_WORKER_DIAGNOSTIC '+json.dumps(bad)), {'invalid': True})

    def test_fixture_keeps_every_current_worker_input_and_no_worker_publication(self):
        value=worker_manifest(Path(__file__).resolve().parents[2])
        self.assertEqual({r['id'] for r in value['routes']}, {'qs-survey-worker','qs-evaluation-mysql','qs-evaluation-mongo','qs-task-normal','qs-task-transaction'})
        self.assertEqual(value['accounts']['m3-qs-worker']['publish'], [])
        self.assertEqual(set(value['accounts']['m3-qs-worker']['subscriptions']), {r['id'] for r in value['routes']})
        self.assertEqual(value['accounts']['m3-qs-apiserver']['publish'], ['qs-evaluation-mysql'])
