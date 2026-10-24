from pathlib import Path
import tempfile
import unittest

from go_failure_diagnostics import diagnostics


class GoTerminationDiagnosticsTest(unittest.TestCase):
    def test_fatal_frames_and_host_errors_never_export_body_or_arguments(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root);p=source/'internal/worker/process.go';p.parent.mkdir(parents=True);p.write_text('package worker\n')
            raw='fatal error: concurrent map read and map write\nprivate-password-and-wire\n'
            raw+='\tgithub.com/FangcunMount/qs-server/internal/worker/process.go:47 +0x123\n'
            raw+='\tgithub.com/FangcunMount/reliable-messaging@v0.5.0/internal/rocketmq5driver/cache.go:8 +0x20\n'
            raw+='\tinternal/runtime/maps/runtime.go:91 +0x30\n'
            raw+='{"level":"error","caller":"internal/worker/process.go:12","msg":"private-password-and-wire"}\n'
            result=diagnostics(raw,source)
            self.assertTrue(result['signal_presence']['runtime_fatal'])
            self.assertTrue(result['signal_presence']['concurrent_map'])
            self.assertEqual([r['origin'] for r in result['go_frames']],['host','sdk','go_runtime'])
            self.assertEqual(result['error_log_sites'][0]['path'],'internal/worker/process.go')
            self.assertNotIn('private-password-and-wire',str(result))
            self.assertFalse(result['raw_messages_exported'])

    def test_unknown_dependency_paths_are_hashed_and_normal_shutdown_is_not_fatal(self):
        result=diagnostics('context canceled\n\t/private/opaque/build/worker.go:19 +0x12\n',Path('/nonexistent'))
        self.assertTrue(result['signal_presence']['context_cancelled'])
        self.assertFalse(result['signal_presence']['runtime_fatal'])
        self.assertNotIn('/private/opaque',str(result))
        self.assertEqual(result['go_frames'][0]['file'],'worker.go')
