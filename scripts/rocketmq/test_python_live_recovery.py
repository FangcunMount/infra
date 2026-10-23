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


if __name__=='__main__':unittest.main()
