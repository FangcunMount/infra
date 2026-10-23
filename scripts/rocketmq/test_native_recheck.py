"""Pure request/primary-read guards; never construct real clients."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('native_recheck', Path(__file__).with_name('ci-native-recheck.py'))
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


class NativeRecheckGuards(unittest.TestCase):
    def test_only_github_hosted_with_local_context_environment(self):
        good = dict(GITHUB_ACTIONS='true', RUNNER_OS='Linux', RUNNER_ENVIRONMENT='github-hosted')
        subject.ci_guard(good)
        for bad in ({}, dict(good, RUNNER_ENVIRONMENT='self-hosted'), dict(good, RUNNER_OS='macOS'),
                    dict(good, DOCKER_HOST='tcp://remote:2375'), dict(good, DOCKER_CONTEXT='remote')):
            with self.assertRaises(RuntimeError): subject.ci_guard(bad)

    def test_exact_single_frame_no_raw_output_required(self):
        self.assertEqual(subject.frame('private\nSAFE {"passed":1}\n', 'SAFE '), {'passed':1})
        for raw in ('', 'SAFE []', 'SAFE {}\nSAFE {}'):
            with self.assertRaises(RuntimeError): subject.frame(raw, 'SAFE ')

    def test_exact_primary_read_requires_all_three_hashes_and_states(self):
        good = '\t'.join(['1'*64,'2'*64,'3'*64,'committed','committed','not_attempted'])
        self.assertEqual(subject.authoritative_snapshot(good)['execution_state'], 'committed')
        for raw in ('', good+'\n'+good, good.replace('1'*64,'wrong'), good.replace('committed','unknown'),
                    good.replace('not_attempted','false_success')):
            with self.assertRaises(RuntimeError): subject.authoritative_snapshot(raw)


if __name__ == '__main__': unittest.main()
