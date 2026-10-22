import json
import unittest
from qs_worker_acceptance import CASES, SCOPE, parse_worker_receipt

class WorkerRuntimeReceiptTest(unittest.TestCase):
    def output(self):
        receipt = dict(source_sha='a'*40, passed=len(CASES), failed=0, skipped=0,
                       cases={case: True for case in CASES}, scope=SCOPE,
                       complete_apiserver_not_claimed=True, provider_not_called=True,
                       system_login_not_claimed=True, owned_database_dropped=True, owned_runtime_drained=True)
        return 'M3_QS_WORKER_RUNTIME_RECEIPT '+json.dumps(receipt)+'\n--- PASS: TestM3WorkerRocketMQRuntime (1.00s)'

    def test_exact_worker_source_scope_cases_cleanup(self):
        self.assertEqual(parse_worker_receipt(self.output(), 'a'*40)['passed'], 4)

    def test_refuses_wrong_source_scope_partial_cleanup_skip_race(self):
        output=self.output()
        for bad in ('',output+'\n'+output,output.replace('a'*40,'b'*40),
                    output.replace('"failed": 0','"failed": 1'), output.replace('"skipped": 0','"skipped": 1'),
                    output.replace('true','false',1),output.replace(SCOPE,'production system acceptance'),
                    output.replace('"owned_runtime_drained": true','"owned_runtime_drained": false'),
                    output.replace('TestM3WorkerRocketMQRuntime','TestSDKProbe'),
                    output+'\nWARNING: DATA RACE',output+'\n--- SKIP: optional (0s)'):
            with self.subTest(bad=bad[:80]):
                with self.assertRaises(RuntimeError):
                    parse_worker_receipt(bad, 'a'*40)
