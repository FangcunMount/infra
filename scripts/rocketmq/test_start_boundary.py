import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from start_boundary import Boundary, BoundaryError, initialize


def fixture(root):
    directory = Path(root) / 'operation'
    binding = {'schema': 'm3-start-boundary/v1', 'operation_id': 'isolated-m3-1',
               'directory': str(directory), 'scope_sha256': '1'*64,
               'protection_sha256': '2'*64, 'restore_receipt_sha256': '3'*64,
               'source_bundle_sha256': '4'*64, 'data_owner': 'isolated-data-owner',
               'recovery_owner': 'isolated-recovery-owner'}
    raw = json.dumps(binding, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    digest = hashlib.sha256(raw).hexdigest()
    initialize(directory, binding, digest)
    return directory, binding, digest


def crash_after_boundary(directory, digest):
    with Boundary(directory, digest) as operation:
        operation.start('runtime-1', lambda: os._exit(23))


def crash_during_maintenance(directory, digest):
    with Boundary(directory, digest) as operation:
        operation.maintain_before_start('offline-1', lambda: os._exit(23))


def hold_started(directory, digest, ready, release):
    with Boundary(directory, digest) as operation:
        def command():
            ready.set()
            if not release.wait(5):
                raise RuntimeError('fixture release timeout')
        operation.start('runtime-1', command)


class StartBoundaryTest(unittest.TestCase):
    def test_successful_prestart_steps_do_not_publish_runtime_barrier(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root); calls = []
            with Boundary(directory, digest) as operation:
                operation.maintain_before_start('offline-1', lambda: calls.append('first'))
                operation.maintain_before_start('offline-2', lambda: calls.append('second'))
                self.assertTrue(operation.status()['old_data_restore_eligible'])
                self.assertFalse((directory/'first-runtime-start.json').exists())
                operation.start('runtime-1', lambda: calls.append('start'))
            self.assertEqual(calls, ['first', 'second', 'start'])

    def test_failed_maintenance_blocks_start_until_independent_repair(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root); calls = []
            with Boundary(directory, digest) as operation:
                def failed(): raise RuntimeError('controlled offline failure')
                with self.assertRaises(RuntimeError): operation.maintain_before_start('offline-1', failed)
                with self.assertRaises(BoundaryError): operation.start('runtime-1', lambda: calls.append('unsafe'))
                with self.assertRaises(BoundaryError): operation.maintain_before_start('offline-1', lambda: calls.append('repeat'))
                operation.maintain_before_start('reviewed-repair', lambda: calls.append('repair'), '6'*64)
                operation.start('runtime-1', lambda: calls.append('start'))
            self.assertEqual(calls, ['repair', 'start'])

    def test_interrupted_maintenance_keeps_start_closed_without_false_runtime_marker(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root)
            proc = multiprocessing.get_context('fork').Process(target=crash_during_maintenance, args=(directory, digest))
            proc.start(); proc.join(10)
            if proc.is_alive(): proc.kill(); proc.join(5)
            self.assertEqual(proc.exitcode, 23)
            with Boundary(directory, digest) as operation:
                self.assertEqual(operation.status()['phase'], 'maintenance_issued')
                self.assertFalse((directory/'first-runtime-start.json').exists())
                with self.assertRaises(BoundaryError): operation.start('runtime-1', lambda: None)
                operation.maintain_before_start('independent-repair', lambda: None, '6'*64)
                operation.start('runtime-1', lambda: None)

    def test_prestart_repair_approval_cannot_repeat_after_failure(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root); calls = []
            with Boundary(directory, digest) as operation:
                def failed(): raise RuntimeError('controlled failure')
                with self.assertRaises(RuntimeError): operation.maintain_before_start('offline-1', failed)
                with self.assertRaises(RuntimeError): operation.maintain_before_start('repair-1', failed, '6'*64)
                with self.assertRaises(BoundaryError): operation.maintain_before_start('repair-1', lambda: calls.append('unsafe'), '6'*64)
                operation.maintain_before_start('repair-2', lambda: calls.append('new-review'), '7'*64)
            self.assertEqual(calls, ['new-review'])

    def test_old_data_restore_can_close_a_failed_prestart_operation(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root)
            with Boundary(directory, digest) as operation:
                def failed(): raise RuntimeError('controlled offline failure')
                with self.assertRaises(RuntimeError): operation.maintain_before_start('offline-1', failed)
                operation.restore_before_start('approved-old-scope', lambda: None)
                with self.assertRaises(BoundaryError): operation.start('runtime-1', lambda: None)
                with self.assertRaises(BoundaryError): operation.maintain_before_start('offline-2', lambda: None)

    def test_prestart_maintenance_never_runs_after_first_runtime_attempt(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root); calls = []
            with Boundary(directory, digest) as operation:
                operation.start('runtime-1', lambda: None)
                with self.assertRaises(BoundaryError): operation.maintain_before_start('offline-1', lambda: calls.append('unsafe'))
                with self.assertRaises(BoundaryError): operation.maintain_before_start('repair-1', lambda: calls.append('unsafe'), '6'*64)
            self.assertEqual(calls, [])

    def test_interrupted_first_marker_after_maintenance_requires_forward_repair(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root)
            with Boundary(directory, digest) as operation:
                operation.maintain_before_start('offline-1', lambda: None)
                with patch('start_boundary.os.fsync', side_effect=OSError('controlled durability failure')):
                    with self.assertRaises(OSError): operation.start('runtime-1', lambda: None)
            with Boundary(directory, digest) as operation:
                self.assertFalse(operation.status()['old_data_restore_eligible'])
                with self.assertRaises(BoundaryError): operation.start('runtime-1', lambda: None)
                with self.assertRaises(BoundaryError): operation.restore_before_start('old', lambda: None)
                operation.forward_repair('compatible-fix', '8'*64, lambda: None)
                self.assertEqual(operation.status()['phase'], 'forward_repair_returned')

    def test_barrier_is_durable_before_command_and_restore_never_runs(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root)
            calls = []
            with Boundary(directory, digest) as operation:
                self.assertTrue(operation.status()['old_data_restore_eligible'])
                def command():
                    self.assertTrue((directory/'first-runtime-start.json').is_file())
                    self.assertEqual(json.loads((directory/'state.json').read_bytes())['phase'],
                                     'runtime_start_issued')
                    calls.append('start')
                operation.start('runtime-1', command)
                self.assertFalse(operation.status()['old_data_restore_eligible'])
                with self.assertRaises(BoundaryError):
                    operation.restore_before_start('old-backup', lambda: calls.append('restore'))
            self.assertEqual(calls, ['start'])

    def test_failed_start_requires_separate_forward_repair(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root)
            calls = []
            with Boundary(directory, digest) as operation:
                def failed():
                    calls.append('start')
                    raise RuntimeError('controlled callback failure')
                with self.assertRaises(RuntimeError): operation.start('runtime-1', failed)
                with self.assertRaises(BoundaryError): operation.start('runtime-1', lambda: None)
                with self.assertRaises(BoundaryError): operation.restore_before_start('old-backup', lambda: calls.append('restore'))
                operation.forward_repair('fixed-image-1', '5'*64, lambda: calls.append('repair'))
                operation.start('runtime-2', lambda: calls.append('next'))
                self.assertFalse(operation.status()['old_data_restore_eligible'])
            self.assertEqual(calls, ['start', 'repair', 'next'])
            self.assertTrue((directory/('repair-approval-'+'5'*64+'.json')).is_file())

    def test_restore_closes_start_even_when_restore_fails(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root)
            with Boundary(directory, digest) as operation:
                def failed(): raise RuntimeError('controlled restore failure')
                with self.assertRaises(RuntimeError): operation.restore_before_start('original-backup', failed)
                with self.assertRaises(BoundaryError): operation.start('runtime-1', lambda: None)
                operation.restore_before_start('original-backup', lambda: None)
                with self.assertRaises(BoundaryError): operation.start('runtime-1', lambda: None)
                self.assertEqual(operation.status()['phase'], 'restore_returned')

    def test_process_exit_after_first_start_marker_remains_irreversible(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root)
            proc = multiprocessing.get_context('fork').Process(target=crash_after_boundary, args=(directory, digest))
            proc.start(); proc.join(10)
            self.assertFalse(proc.is_alive()); self.assertEqual(proc.exitcode, 23)
            with Boundary(directory, digest) as operation:
                self.assertFalse(operation.status()['old_data_restore_eligible'])
                with self.assertRaises(BoundaryError): operation.restore_before_start('old-backup', lambda: None)
                with self.assertRaises(BoundaryError): operation.start('runtime-1', lambda: None)

    def test_concurrent_restore_cannot_enter_a_running_start(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root)
            ctx = multiprocessing.get_context('fork'); ready, release = ctx.Event(), ctx.Event()
            proc = ctx.Process(target=hold_started, args=(directory, digest, ready, release))
            proc.start()
            try:
                self.assertTrue(ready.wait(5))
                with self.assertRaises(BlockingIOError):
                    with Boundary(directory, digest): pass
            finally:
                release.set(); proc.join(10)
                if proc.is_alive(): proc.kill(); proc.join(5)
            self.assertEqual(proc.exitcode, 0)
            with Boundary(directory, digest) as operation:
                with self.assertRaises(BoundaryError): operation.restore_before_start('old-backup', lambda: None)

    def test_fsync_failure_never_invokes_command_or_erases_barrier(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root); calls = []
            with Boundary(directory, digest) as operation:
                with patch('start_boundary.os.fsync', side_effect=OSError('controlled durability failure')):
                    with self.assertRaises(OSError): operation.start('runtime-1', lambda: calls.append('start'))
            self.assertEqual(calls, [])
            with Boundary(directory, digest) as operation:
                self.assertFalse(operation.status()['old_data_restore_eligible'])
                with self.assertRaises(BoundaryError): operation.start('runtime-1', lambda: None)

    def test_no_reset_move_or_unreviewed_scope(self):
        with tempfile.TemporaryDirectory() as root:
            directory, binding, digest = fixture(root)
            with self.assertRaises(FileExistsError): initialize(directory, binding, digest)
            with self.assertRaises(BoundaryError):
                with Boundary(directory, '0'*64): pass
            moved = Path(root)/'moved'; directory.rename(moved)
            with self.assertRaises(BoundaryError):
                with Boundary(moved, digest): pass

    def test_invalid_step_never_publishes_first_start(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root)
            with Boundary(directory, digest) as operation:
                for value in ('', '../runtime', 'x'*65):
                    with self.assertRaises(BoundaryError): operation.start(value, lambda: None)
                self.assertTrue(operation.status()['old_data_restore_eligible'])
                self.assertFalse((directory/'first-runtime-start.json').exists())

    def test_corrupt_or_missing_state_does_not_prove_no_runtime(self):
        with tempfile.TemporaryDirectory() as root:
            directory, _, digest = fixture(root)
            (directory/'state.json').write_bytes(b'{')
            with self.assertRaises(ValueError):
                with Boundary(directory, digest): pass
            (directory/'state.json').write_text(json.dumps({'binding_sha256': digest, 'phase': [], 'step': ''}))
            with self.assertRaises(BoundaryError):
                with Boundary(directory, digest): pass
            (directory/'state.json').unlink()
            with self.assertRaises(FileNotFoundError):
                with Boundary(directory, digest): pass


if __name__ == '__main__':
    unittest.main()
