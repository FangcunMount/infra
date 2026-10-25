from pathlib import Path
import subprocess
import tempfile
import unittest

from nsq_retirement import guard_makefile, retire_serverd_compose, GUARD, SERVICES

ROOT = Path(__file__).resolve().parents[2]


class RetiredNSQTests(unittest.TestCase):
    def test_serverd_overrides_only_disable_three_services(self):
        current = (ROOT/'deploy/serverD/docker-compose.yml').read_bytes()
        self.assertEqual(retire_serverd_compose(current), current)
        self.assertEqual(current.count(b'profiles: [legacy-nsq-retired]'), 3)
        self.assertEqual(current.count(b'restart: "no"'), 3)
        for name in SERVICES:
            self.assertIn(('  '+name+':\n    profiles: [legacy-nsq-retired]\n    restart: "no"\n    extends:').encode(), current)
        generic = (ROOT/'components/nsq/docker-compose.yml').read_text()
        self.assertNotIn('legacy-nsq-retired', generic)
        self.assertEqual(generic.count('restart: always'), 3)

    def test_patch_refuses_missing_or_duplicate_services(self):
        for raw in [b'services:\n', b'  nsqd:\n  nsqd:\n']:
            with self.assertRaises(ValueError):
                retire_serverd_compose(raw)

    def test_patch_refuses_existing_restart_deep_in_service(self):
        raw = ''.join('  '+name+':\n    extends:\n      service: '+name+'\n    restart: always\n' for name in SERVICES).encode()
        with self.assertRaises(ValueError):
            retire_serverd_compose(raw)

    def test_make_patch_preserves_other_targets_and_is_idempotent(self):
        raw = b'untouched:\n\t@echo keep\nnsq-start:\n\t@echo old\nnsq-recreate: prerequisite\n\t@echo old\nserverD-up:\n\t@echo old\n'
        patched = guard_makefile(raw)
        self.assertEqual(patched.count(GUARD.encode()), 3)
        self.assertEqual(patched.replace(GUARD.encode(), b''), raw)
        self.assertEqual(guard_makefile(patched), patched)
        self.assertEqual(guard_makefile((ROOT/'Makefile').read_bytes()), (ROOT/'Makefile').read_bytes())

    def test_make_patch_refuses_missing_or_duplicate_target(self):
        for raw in [b'nsq-start:\n', b'nsq-start:\nnsq-start:\nnsq-recreate:\nserverD-up:\n']:
            with self.assertRaises(ValueError):
                guard_makefile(raw)

    def test_real_marker_guard_blocks_only_retired_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory)/'provider'
            for value, expected in [('rocketmq\n', 1), ('nsq\n', 0), (None, 0)]:
                if value is None:
                    marker.unlink(missing_ok=True)
                else:
                    marker.write_text(value)
                import os
                p = subprocess.run(['bash', str(ROOT/'scripts/rocketmq/guard-nsq.sh')], env=dict(os.environ, MESSAGING_PROVIDER_MARKER=str(marker)), capture_output=True)
                self.assertEqual(p.returncode, expected)

    def test_generic_up_and_restart_guard_precedes_all_side_effects(self):
        text = (ROOT/'scripts/02-components/compose-manager.sh').read_text()
        body = text.split('manage_infra() {', 1)[1].split('# 管理基础设施管理界面', 1)[0]
        self.assertIn('"$action" == "up" || "$action" == "restart"', body)
        self.assertIn('"$component" == "nsq" || "$component" == "all"', body)
        self.assertLess(body.index('guard-nsq.sh'), body.index('ensure_infrastructure'))


if __name__ == '__main__':
    unittest.main()
