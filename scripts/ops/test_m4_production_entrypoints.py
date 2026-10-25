"""Exercise actual retired entrypoints using only owned command fakes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ProductionEntrypointTests(unittest.TestCase):
    def invoke(self, args, **extra):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory);bin_dir = p/'bin';bin_dir.mkdir();log = p/'effects'
            for command in ['docker', 'sudo', 'rm', 'rsync']:
                script = bin_dir/command
                script.write_text('#!/bin/sh\nprintf "%s\\n" "'+command+' $*" >> "$M4_EFFECTS"\nexit 0\n')
                script.chmod(0o700)
            env = dict(os.environ, PATH=str(bin_dir)+os.pathsep+os.environ['PATH'], M4_EFFECTS=str(log), MESSAGING_PROVIDER_MARKER=str(p/'missing-marker'), **extra)
            run = subprocess.run(args, cwd=ROOT, env=env, input='', capture_output=True, text=True, timeout=15)
            return run, log.read_text() if log.exists() else ''

    def test_retired_make_targets_cannot_execute_legacy_actions(self):
        for target in ['init-serverD', 'serverD-up', 'serverD-down', 'serverD-logs', 'serverD-destroy', 'serverD-rebuild', 'nsq-recreate']:
            with self.subTest(target=target):
                p, effects = self.invoke(['make', '--no-print-directory', target])
                self.assertNotEqual(p.returncode, 0)
                self.assertEqual(effects, '')

    def test_production_make_nsq_start_and_restart_reject_before_side_effects(self):
        for target in ['nsq-start', 'nsq-restart']:
            p, effects = self.invoke(['make', '--no-print-directory', target, 'ENV=prod'])
            self.assertNotEqual(p.returncode, 0)
            self.assertIn('Production NSQ deployment is retired', p.stderr)
            self.assertEqual(effects, '')

    def test_serverd_compose_is_not_an_active_source(self):
        self.assertFalse((ROOT/'deploy/serverD/docker-compose.yml').exists())

    def test_legacy_initializer_rejects_serverd_before_any_side_effect(self):
        for operation in ['create', 'remove', 'reset', 'test']:
            p, effects = self.invoke(['bash', 'scripts/02-components/init-infrastructure.sh', operation], INIT_TARGET='serverD')
            self.assertNotEqual(p.returncode, 0)
            self.assertIn('RocketMQ', p.stderr)
            self.assertEqual(effects, '')

    def test_production_guard_rejects_without_needing_a_host_marker(self):
        p, effects = self.invoke(['bash', 'scripts/rocketmq/guard-nsq.sh', 'prod'])
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(effects, '')

    def test_production_install_rejects_before_directory_or_user_setup(self):
        for component in ['nsq', 'all']:
            p, effects = self.invoke(['bash', 'scripts/02-components/install.sh', component, '--env', 'prod', '--dry-run'])
            self.assertNotEqual(p.returncode, 0)
            self.assertIn('Production NSQ deployment is retired', p.stderr)
            self.assertEqual(effects, '')

    def test_development_guard_and_generic_nsq_are_retained(self):
        p, effects = self.invoke(['bash', 'scripts/rocketmq/guard-nsq.sh', 'dev'])
        self.assertEqual(p.returncode, 0)
        self.assertEqual(effects, '')
        self.assertEqual((ROOT/'components/nsq/docker-compose.yml').read_text().count('restart: always'), 3)
        self.assertTrue((ROOT/'deploy/mac-mini/docker-compose.yml').is_file())


if __name__ == '__main__':
    unittest.main()
