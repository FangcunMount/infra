import importlib.util
import json
from pathlib import Path
import socket
import time
import unittest

spec=importlib.util.spec_from_file_location('dispatch_factory_harness',Path(__file__).with_name('ci-dispatch-factory.py'))
harness=importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)

class FactoryReceiptTest(unittest.TestCase):
    def output(self):
        value=dict(source_sha='a'*40,passed=len(harness.CASES),failed=0,skipped=0,cases={k:True for k in harness.CASES},
          scope=harness.SCOPE,broker_or_business_dispatch_not_claimed=True,complete_host_startup_not_claimed=True,
          system_login_not_claimed=True,owned_databases_dropped=True,original_client_closed_by_fixture=True)
        return 'M3_QS_DISPATCH_FACTORY_RECEIPT '+json.dumps(value)+'\n--- PASS: TestM3DefaultDispatchFactory (2.00s)'
    def test_exact_scope_source_cases_and_cleanup(self):
        self.assertEqual(harness.parse_receipt(self.output(),'a'*40)['passed'],10)
    def test_refuse_empty_partial_scope_skip_race_wrong_source_cleanup(self):
        output=self.output()
        for bad in ('',output+'\n'+output,output.replace('a'*40,'b'*40),output.replace('true','false',1),
                    output.replace('"failed": 0','"failed": 1'),output.replace('"skipped": 0','"skipped": 1'),
                    output.replace(harness.SCOPE,'whole business service'),
                    output.replace('"owned_databases_dropped": true','"owned_databases_dropped": false'),
                    output.replace('TestM3DefaultDispatchFactory','TestSDKProbe'),
                    output+'\nWARNING: DATA RACE',output+'\n--- SKIP: optional (0s)'):
            with self.subTest(bad=bad[:80]):
                with self.assertRaises(RuntimeError):harness.parse_receipt(bad,'a'*40)
    def test_owned_endpoint_trap_joins_and_counts_only_connections(self):
        trap=harness.EndpointTrap()
        try:
            host,port=trap.endpoint.split(':')
            with socket.create_connection((host,int(port)),timeout=1):pass
            for _ in range(50):
                if trap.connections==1:break
                time.sleep(.01)
            self.assertEqual(trap.connections,1)
        finally:self.assertTrue(trap.close())

class FailureStateTest(unittest.TestCase):
    def test_diagnostics_export_only_fixed_state_fields(self):
        raw=json.dumps({'Status':'exited','OOMKilled':True,'ExitCode':137,'Restarting':False,
            'Error':'sensitive internal path', 'Health':{'Status':'unhealthy','Log':[{'Output':'private body'}]}})
        state=harness.safe_container_state(raw)
        self.assertEqual(state,{'status':'exited','oom_killed':True,'exit_code':137,'restarting':False,'health':'unhealthy'})
        self.assertNotIn('private',json.dumps(state))
        self.assertNotIn('sensitive',json.dumps(state))
