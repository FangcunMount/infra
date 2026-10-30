"""Offline contract tests; native sudo -l tests are recorded in the server evidence."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / 'deploy/serverA/sudoers/fangcun-qs-mq-preflight-3b8a931'
TOOL = '/opt/qs-server/qs-apiserver/ai-mq-tools/ce8b2112bd2669efa14ae34880a6f6462e38d629a4a17ff9673936b70b359bb3.py'
IMAGE = 'ghcr.io/fangcunmount/qs-apiserver:3b8a931e2451e38602e8b26bc623bf8d37a69878'


def arguments(pid='12345'):
    return f'{TOOL} --image {IMAGE} --base-config /tmp/qs-deploy-apiserver-{pid}/configs/apiserver.prod.yaml --uid 2000 --gid 2000'


def argument_pattern():
    line = next(line for line in POLICY.read_text().splitlines() if line.startswith('Cmnd_Alias '))
    prefix = 'Cmnd_Alias FANGCUN_QS_MQ_3B8A931 = /usr/bin/python3 '
    if not line.startswith(prefix):
        raise ValueError('unexpected interpreter or alias')
    return line[len(prefix):]


class QSMQPolicyTest(unittest.TestCase):
    def test_policy_is_one_fixed_command_with_scoped_environment(self):
        lines = [s for s in POLICY.read_text().splitlines() if s and not s.startswith('#')]
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[-1], 'deploy ALL=(root) CWD=/ NOPASSWD: NOSETENV: FANGCUN_QS_MQ_3B8A931')
        self.assertEqual(lines[1], 'Defaults!FANGCUN_QS_MQ_3B8A931 env_reset, always_set_home, !setenv, env_delete += "PYTHON*", env_keep -= "PYTHONPATH PYTHONHOME PYTHONUSERBASE PYTHONINSPECT"')
        pattern = argument_pattern()
        self.assertTrue(pattern.startswith('^') and pattern.endswith('$'))
        self.assertLessEqual(len(pattern), 1024)
        self.assertNotIn('*', pattern)
        self.assertNotIn('.*', pattern)
        self.assertEqual(re.findall(r'\[[^\]]*\]\{[^}]*\}', pattern), ['[0-9]{1,7}'])

    def test_current_cd_shape_accepts_only_bounded_pid_variation(self):
        for pid in ('1', '12345', '4194304'):
            with self.subTest(pid=pid):
                self.assertIsNotNone(re.fullmatch(argument_pattern(), arguments(pid)))

    def test_pid_path_cannot_escape_or_consume_extra_arguments(self):
        for pid in ('', '12345678', '123/x', '123/../x', 'abc', '-1', '1 --image x', '1\n2'):
            with self.subTest(pid=pid):
                self.assertIsNone(re.fullmatch(argument_pattern(), arguments(pid)))

    def test_other_interpreter_modes_tools_images_identity_or_arguments_fail(self):
        base = arguments()
        variants = ['-I ' + base, '-c pass', base + ' --plan /tmp/plan.json', base + ' --apply',
                    base + ' ', base.replace(TOOL, '/tmp/uploaded.py'),
                    base.replace(IMAGE, 'ghcr.io/fangcunmount/qs-apiserver:latest'),
                    base.replace(IMAGE, IMAGE + '-other'), base.replace('--uid 2000', '--uid 0'),
                    base.replace('--gid 2000', '--gid 0'),
                    base.replace('/tmp/qs-deploy-apiserver-', '/var/tmp/qs-deploy-apiserver-'),
                    base.replace('configs/apiserver.prod.yaml', 'configs/other.yaml'),
                    base.replace('apiserver.prod.yaml', 'apiserverXprodXyaml')]
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertIsNone(re.fullmatch(argument_pattern(), variant))


if __name__ == '__main__':
    unittest.main()
