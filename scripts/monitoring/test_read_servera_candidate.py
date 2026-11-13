"""Verify that the formal observer injects the exact QS release and two-hour range."""
from contextlib import redirect_stdout
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
import unittest
from unittest.mock import patch

SCRIPT=Path(__file__).with_name('read_servera_candidate.py')
OLD='4620d11e2cffbc4b67b43965812cff3340f0be43'
NEW='7014c24db0c6b57c130112752857b2bec0b9bc7d'
END='2026-11-13T20:00:00+00:00'
CLOCK=datetime.fromisoformat(END).timestamp()+1

class CandidateObserverTest(unittest.TestCase):
    def args(self,source,started='2026-11-13T17:00:00.123456789Z'):
        return [str(SCRIPT),'--container','a'*64,'--image','sha256:'+'b'*64,
                '--started-at',started,'--collection-ip','172.20.0.114','172.20.0.115',
                '--end',END,'--qs-source',source]

    def exercise(self,source,passing):
        def fake_run(argv,**kw):
            self.assertIn('nsenter',argv[-1])
            self.assertIn('qlume-servera-monitoring servera-collector',argv[-1])
            remote=kw['input'].decode()
            body=remote.partition('\nrequests = []')[0]
            ns={'__name__':'fixture'}
            exec(body,ns)
            self.assertEqual(ns['QS_SOURCE'],source)
            check='observe(capture, expected_targets(IPS, QS_SOURCE), END, range_seconds=7200)'
            self.assertIn(check,remote)
            targets=ns['expected_targets'](ns['IPS'],source)
            self.assertIn(('qs-worker',f'qs-m5-{source[:12]}-worker-3'),targets)
            self.assertEqual(len(targets),10)
            report={'points':481,'read_only':True,'execution_authorized':False,
                    'expected_targets':sorted(targets),'expected_owners':sorted(ns['OWNERS']),
                    'passed':passing}
            self.response=json.dumps({'report':report,'requests':[{}]*9}).encode()
            return subprocess.CompletedProcess(argv,0,self.response,b'')
        result=io.StringIO()
        with patch.object(sys,'argv',self.args(source)),patch('time.time',return_value=CLOCK),\
             patch('subprocess.run',side_effect=fake_run),redirect_stdout(result),self.assertRaises(SystemExit) as status:
            runpy.run_path(str(SCRIPT),run_name='__main__')
        self.assertEqual(status.exception.code,0 if passing else 1)
        observed=json.loads(result.getvalue())
        self.assertEqual(observed['binding']['qs_runtime_source'],source)
        self.assertEqual(observed['binding']['raw_response_sha256'],sha256(self.response).hexdigest())

    def test_original_and_candidate_exact_source(self):
        self.exercise(OLD,True)
        self.exercise(NEW,False)

    def test_rejects_invalid_source_and_short_process_window_without_ssh(self):
        for argv in (self.args('7014c24d'),self.args(NEW,'2026-11-13T18:00:00.123456789Z')):
            with self.subTest(argv=argv),patch.object(sys,'argv',argv),patch('time.time',return_value=CLOCK),\
                 patch('subprocess.run') as remote,self.assertRaises(SystemExit) as status:
                runpy.run_path(str(SCRIPT),run_name='__main__')
            self.assertEqual(status.exception.code,2)
            remote.assert_not_called()
