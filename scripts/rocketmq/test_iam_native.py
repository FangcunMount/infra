import json
import unittest

from iam_native import REQUIRED, test_counts


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


if __name__ == '__main__':
    unittest.main()
