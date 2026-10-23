"""Actual process-tree lifecycle, without Docker, SDK mocks or external data."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('transaction_harness', Path(__file__).with_name('ci-transactions.py'))
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


class ProbeProcessTest(unittest.TestCase):
    def launch(self, directory):
        # A real launcher plus a real child, exactly the process ownership that
        # uv run introduces. The child inherits stdout until it actually exits.
        code = ("import subprocess,sys,json; "
                "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']); "
                "print('TXPROBE '+json.dumps({'event':'ready','child_pid':child.pid}),flush=True); "
                "child.wait()")
        probe = harness.Probe([sys.executable, '-u', '-c', code], Path(directory), dict(os.environ))
        self.addCleanup(probe.close)
        event = probe.wait('ready', timeout=5)
        self.assertEqual(os.getpgid(event['child_pid']), probe.process.pid)
        self.assertNotEqual(event['child_pid'], probe.process.pid)
        return probe

    def test_sigkill_terminates_actual_child_not_just_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            probe = self.launch(directory)
            probe.kill_group()
            probe.finish(expected=-9)
            self.assertFalse(probe.reader.is_alive())
            self.assertTrue(any(e.get('event') == 'exited' for e in probe.events))
            self.assertTrue(probe.close())

    def test_failure_cleanup_terminates_whole_owned_process_group(self):
        with tempfile.TemporaryDirectory() as directory:
            probe = self.launch(directory)
            self.assertTrue(probe.close())
            self.assertIsNotNone(probe.process.poll())
            self.assertFalse(probe.reader.is_alive())
            self.assertTrue(probe.log.closed)


class ProbeCursorTest(unittest.TestCase):
    def test_second_control_reply_cannot_reuse_a_prior_stats_event(self):
        with tempfile.TemporaryDirectory() as directory:
            code = """import sys,json
count=0
for line in sys.stdin:
 if line.strip() == 'stats':
  count+=1
  print('TXPROBE '+json.dumps({'event':'stats','count':count}),flush=True)
 else:
  print('TXPROBE '+json.dumps({'event':'closed'}),flush=True)
  break
"""
            probe = harness.Probe([sys.executable, '-u', '-c', code], Path(directory), dict(os.environ))
            self.addCleanup(probe.close)
            probe.send('stats')
            self.assertEqual(probe.wait('stats', timeout=5)['count'], 1)
            cursor = len(probe.events)
            probe.send('stats')
            self.assertEqual(probe.wait('stats', timeout=5, after=cursor)['count'], 2)
            probe.send('stop')
            probe.wait('closed', timeout=5)
            probe.finish()
            self.assertTrue(probe.close())
