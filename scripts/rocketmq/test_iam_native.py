import json
import unittest
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

from iam_native import REQUIRED, test_counts, run_test_group


class NativeReceiptTest(unittest.TestCase):
    def output(self):
        return '\n'.join(json.dumps({'Action': 'pass', 'Test': name}) for name in REQUIRED)

    def test_exact_required_names_and_nonempty_zero_skip_gate(self):
        counts, names = test_counts(self.output())
        self.assertEqual(counts, {'pass': 12, 'fail': 0, 'skip': 0})
        self.assertEqual(set(names), REQUIRED)
        for output in ('', '\n'.join(self.output().splitlines()[1:]),
                       self.output() + '\n' + json.dumps({'Action': 'skip', 'Test': 'TestOther'}),
                       self.output() + '\n' + json.dumps({'Action': 'fail', 'Test': 'TestM3Actual'})):
            with self.assertRaises(RuntimeError):
                test_counts(output)

    def test_shell_text_or_successful_package_without_test_cannot_satisfy_gate(self):
        with self.assertRaises(RuntimeError):
            test_counts('--- PASS: TestM3PlannedPolicyNative\n{"Action":"pass","Package":"package"}')

    def test_timed_out_launcher_drains_its_actual_child_before_return(self):
        with tempfile.TemporaryDirectory() as directory:
            pidfile = Path(directory) / 'child.pid'
            source = ('import subprocess,time,sys; '
                      'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"]); '
                      'open(sys.argv[1],"w").write(str(p.pid)); time.sleep(60)')
            try:
                with (Path(directory) / 'private.log').open('w') as stream:
                    with self.assertRaises(subprocess.TimeoutExpired):
                        run_test_group([sys.executable, '-c', source, str(pidfile)],
                                       cwd=directory, env=os.environ.copy(), stream=stream, timeout=.5)
                child = int(pidfile.read_text())
                state = subprocess.run(['ps', '-o', 'stat=', '-p', str(child)], capture_output=True, text=True)
                self.assertTrue(state.returncode == 1 or state.stdout.strip().startswith('Z'))
            finally:
                if pidfile.exists():
                    try:
                        os.kill(int(pidfile.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass


if __name__ == '__main__':
    unittest.main()
