"""New profile must reject mixed/missing sources before acquiring dependencies."""
import subprocess
import sys
from pathlib import Path
import unittest

class PythonLiveRecoveryProfileTest(unittest.TestCase):
    def test_missing_public_sdk_profiles_and_mixed_host_are_rejected_pre_fixture(self):
        script=Path(__file__).with_name('ci-transactions.py')
        for extra in ([],['--sdk-api-go'],['--sdk-api-go','--sdk-api-python','--ai-admission-host','/missing'],
                      ['--sdk-api-go','--sdk-api-python','--sdk-faults']):
            result=subprocess.run([sys.executable,str(script),'--sdk','/missing',
                '--image','fixture:owned','--report','/missing/report.json',
                '--sdk-python-live-recovery',*extra],capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertIn('requires source SDK Go/Python fixture',result.stderr)
            self.assertNotIn('Traceback',result.stderr)

class TelemetryDiagnosticSchemaTest(unittest.TestCase):
    def test_diagnostics_export_only_known_scalar_counters(self):
        import json
        from python_live_recovery import SDK_FIELDS, TELEMETRY_FIELDS, telemetry_receipt
        row=dict(sdk={key:0 for key in SDK_FIELDS},telemetry={key:0 for key in TELEMETRY_FIELDS})
        row['sdk']['wire']='private-body'
        row['telemetry']['credentials']='private-token'
        parsed=telemetry_receipt({'decision':json.dumps(row)})
        self.assertNotIn('private',json.dumps(parsed))
        row['telemetry']['pending_settings']='private-value'
        with self.assertRaises(RuntimeError):telemetry_receipt({'decision':json.dumps(row)})


class ProxyRouteDiagnosticTest(unittest.TestCase):
    def test_response_exports_only_bounded_codes_and_topic_hash(self):
        from types import SimpleNamespace
        from route_read_probe import receipt
        row=SimpleNamespace(status=SimpleNamespace(code=20000,message='private-token'),message_queues=[object()])
        value=receipt(row,'private-topic',1)
        self.assertNotIn('private',str(value))
        self.assertEqual(value['queues'],1)
        with self.assertRaises(RuntimeError):receipt(row,'private-topic',11)

class ProxyRouteReceiptTest(unittest.TestCase):
    def test_wrong_topic_private_fields_and_refusals_cannot_be_ready(self):
        import hashlib,json
        from route_read_probe import parse_output
        row=dict(code=20000,queues=1,attempts=1,topic_sha256=hashlib.sha256(b'fixture').hexdigest(),read_only=True)
        def output(value):return 'TXPROBE '+json.dumps(dict(event='proxy_route',id='',decision=json.dumps(value)))
        self.assertEqual(parse_output(output(row),'fixture'),row)
        for change in (dict(code=40402),dict(queues=0),dict(raw_wire='private'),dict(attempts=True)):
            with self.assertRaises(RuntimeError):parse_output(output(dict(row,**change)),'fixture')
        with self.assertRaises(RuntimeError):parse_output(output(row),'wrong-topic')

if __name__=='__main__':unittest.main()
