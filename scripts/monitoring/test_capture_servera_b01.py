from base64 import b64encode
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest

import capture_servera_b01 as runner
import test_servera_history_seam as test_seam


class RunnerTest(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name)
        self.fixture = test_seam.SeamTest()
        self.binding = {}
        self.paths = []
        for side, key in (("macmini", "a"), ("candidate", "b")):
            data = dict(
                container=key * 64,
                image="sha256:" + key * 64,
                started_at="2026-11-13T21:00:00.123456789Z",
            )
            self.binding[side] = data
            path = self.base / f"{side}.json"
            path.write_text(json.dumps(data))
            self.paths.append(path)
        self.capture_barrier = Barrier(2)

    def probe(self, side, path, scope):
        self.capture_barrier.wait(timeout=3)
        self.assertEqual(json.loads(path.read_bytes()), self.binding[side])
        start, end, _, _ = scope
        fixture = test_seam.SeamTest()
        fixture.start, fixture.end = start, end
        stamp = end - (0 if side == "macmini" else 2)
        receipt = fixture.raw(side, [stamp - 45, stamp - 30, stamp - 15, stamp])
        for when in ("binding_before", "binding_after"):
            receipt[when].update(self.binding[side])
        receipt["raw_http"] = {
            name: b64encode(json.dumps(body).encode()).decode()
            for name, body in receipt["responses"].items()
        }
        return 0, json.dumps(receipt).encode(), b""

    def run_stage(self, probe=None, now=(1800000000, 1800000005)):
        clock = iter(now)
        return runner.run(
            self.base,
            "h03-review-01",
            self.fixture.source,
            self.fixture.ips,
            self.paths,
            probe=probe or self.probe,
            now=lambda: next(clock),
        )

    def test_parallel_read_receipt_and_original_digests(self):
        directory, result = self.run_stage()
        self.assertTrue(result["eligible_for_review"])
        self.assertFalse(result["execution_authorized"])
        self.assertEqual(
            json.loads(json.dumps(result)),
            json.loads((directory / "b01-receipt.json").read_bytes()),
        )
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(len(result["originals_sha256"]), 6)
        for name, digest in result["originals_sha256"].items():
            self.assertEqual((directory / name).stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                sha256((directory / name).read_bytes()).hexdigest(), digest
            )
        with self.assertRaises(FileExistsError):
            self.run_stage()

    def test_timeout_retains_both_sides_and_cannot_be_accepted(self):
        def outcome(side, path, scope):
            code, raw, errors = self.probe(side, path, scope)
            return (
                (124, b"", b"timeout") if side == "candidate" else (code, raw, errors)
            )

        directory, result = self.run_stage(probe=outcome)
        self.assertFalse(result["eligible_for_review"])
        self.assertEqual(result["capture_exit"], dict(macmini=0, candidate=124))
        self.assertTrue((directory / "macmini.json").read_bytes())
        self.assertEqual((directory / "candidate.stderr").read_bytes(), b"timeout")

    def test_capture_scope_or_binding_drift(self):
        def outcome(side, path, scope):
            code, raw, errors = self.probe(side, path, scope)
            data = json.loads(raw)
            if side == "candidate":
                data["binding_before"]["image"] = "sha256:" + "c" * 64
            return code, json.dumps(data).encode(), errors

        _, result = self.run_stage(probe=outcome)
        self.assertFalse(result["eligible_for_review"])
        self.assertIn("operation scope or collector binding", result["failure"])

    def test_capture_duration_counts_against_freshness(self):
        _, result = self.run_stage(now=(1800000000, 1800000034))
        self.assertTrue(result["assessment"]["fresh_simultaneous_overlap"])
        self.assertFalse(result["eligible_for_review"])
        self.assertIn("aged beyond", result["failure"])

    def test_refuses_public_parent_and_skip_capture(self):
        self.base.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "private directory"):
            self.run_stage()

    def test_refuses_same_container_and_skip_capture(self):
        self.paths[1].write_bytes(self.paths[0].read_bytes())
        with self.assertRaisesRegex(ValueError, "same collector"):
            self.run_stage()
