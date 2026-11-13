"""Verify that the formal observer injects the exact QS release and two-hour range."""
from contextlib import redirect_stdout
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import re
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
            config = {'sha256': 'c'*64, 'loaded_at': '2026-11-13T17:00:00Z'}
            self.response=json.dumps({'report':report,'requests':[{}]*9,'local_configuration':config}).encode()
            return subprocess.CompletedProcess(argv,0,self.response,b'')
        result=io.StringIO()
        with patch.object(sys,'argv',self.args(source)),patch('time.time',return_value=CLOCK),\
             patch('subprocess.run',side_effect=fake_run),redirect_stdout(result),self.assertRaises(SystemExit) as status:
            runpy.run_path(str(SCRIPT),run_name='__main__')
        self.assertEqual(status.exception.code,0 if passing else 1)
        observed=json.loads(result.getvalue())
        self.assertEqual(observed['local_configuration']['sha256'], 'c'*64)
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

    def test_remote_probe_requires_local_configuration_before_and_after_queries(self):
        source = SCRIPT.read_text().split("probe = " + "'"*3, 1)[1].split("'"*3, 1)[0]
        local = "global:\n  scrape_interval: 15s\nscrape_configs: []\n"
        remote = "remote_read:\n  - url: http://127.0.0.1:19092/api/v1/read\n"
        old_stamp = "2026-11-13T17:00:00Z"
        new_stamp = "2026-11-13T17:00:01Z"
        late_stamp = "2026-11-13T18:00:01Z"
        scenarios = (
            (local, local, old_stamp, old_stamp, True, None, 1),
            (remote, remote, old_stamp, old_stamp, True, "remote read disabled", 0),
            ("global: {}\n", local, old_stamp, old_stamp, True, "configuration is unavailable", 0),
            (local, remote, old_stamp, new_stamp, True, "remote read disabled", 1),
            (local, local + "# changed\n", old_stamp, old_stamp, True, "changed during", 1),
            (local, local, old_stamp, new_stamp, True, "changed during", 1),
            (local, local, old_stamp, old_stamp, False, "reload is unverified", 0),
            (local, local, late_stamp, late_stamp, True, "full two-hour interval", 0),
        )
        for first, second, loaded, reloaded, success, error, observations in scenarios:
            with self.subTest(first=first, second=second, reloaded=reloaded, success=success):
                configs = iter((first, second))
                times = iter((loaded, reloaded))
                calls = []

                def get(path, **params):
                    if path == "/api/v1/status/config":
                        return {"yaml": next(configs)}
                    if path == "/api/v1/status/runtimeinfo":
                        return {"reloadConfigSuccess": success, "lastConfigTime": next(times)}
                    return {"fixture": True}

                def observe(capture, targets, end, *, range_seconds):
                    calls.append((targets, end, range_seconds))
                    self.assertEqual(capture("/api/v1/targets", state="active"), {"fixture": True})
                    return {"passed": True}

                namespace = dict(api=lambda _: get, re=re, json=json,
                                 scrape_time=lambda stamp: datetime.fromisoformat(stamp).timestamp(),
                                 observe=observe, expected_targets=lambda ips, sha: (ips, sha),
                                 IPS=("172.20.0.114", "172.20.0.115"), QS_SOURCE=NEW, END=CLOCK)
                output = io.StringIO()
                with redirect_stdout(output):
                    if error:
                        with self.assertRaisesRegex(ValueError, error):
                            exec(source, namespace)
                    else:
                        exec(source, namespace)
                        result = json.loads(output.getvalue())
                        self.assertEqual(result["local_configuration"],
                                         {"sha256": sha256(local.encode()).hexdigest(), "loaded_at": loaded})
                        self.assertNotIn("scrape_configs:", output.getvalue())
                self.assertEqual(len(calls), observations)
