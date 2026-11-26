"""Regression coverage for the production H04 admission and cutoff paths."""
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[2] / "deploy/serverA/monitoring/h04"
spec = importlib.util.spec_from_file_location(
    "servera_h04", SOURCE / "stop-candidate.py"
)
guard = importlib.util.module_from_spec(spec)
with patch.object(sys, "path", [str(SOURCE), *sys.path]):
    spec.loader.exec_module(guard)

START = "2026-11-14T11:00:00Z"
LATEST = "2026-11-14T11:15:00Z"
CUTOFF = "2026-11-14T13:45:00Z"


class H04CutoffTest(unittest.TestCase):
    def setUp(self):
        work = TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.plan = dict(
            operation="h04-cutoff-test",
            window_start_utc=START,
            latest_start_utc=LATEST,
            cutoff_utc=CUTOFF,
            containers={
                "servera-collector": {"id": "a" * 64},
                "query-bridge": {"id": "b" * 64},
            },
        )
        self.digest = "c" * 64

    def test_stop_closes_admission_even_if_stop_fails(self):
        with patch.object(
            guard, "stop", side_effect=RuntimeError("failed stop")
        ) as stop:
            with self.assertRaisesRegex(RuntimeError, "failed stop"):
                guard.lifecycle(self.root, self.plan, self.digest, "stop")
        self.assertTrue((self.root / "closed.json").exists())
        stop.assert_called_once_with(self.root, self.plan)
        with patch.object(guard, "start_container") as invoke:
            with self.assertRaisesRegex(ValueError, "already closed"):
                guard.lifecycle(self.root, self.plan, self.digest, "start")
        invoke.assert_not_called()

    def test_latest_start_is_exclusive_without_cutoff_receipt(self):
        with patch.object(
            guard, "now", return_value=guard.utc_second(LATEST)
        ), patch.object(guard, "read_docker_for_start") as inspect:
            with self.assertRaisesRegex(ValueError, "outside approved"):
                guard.lifecycle(self.root, self.plan, self.digest, "start")
        inspect.assert_not_called()
        self.assertFalse((self.root / "start-issued.json").exists())

    def test_failed_second_start_closes_before_exact_stop(self):
        created = {
            "State": {"Status": "created"},
            "HostConfig": {"RestartPolicy": {"Name": "no"}},
        }
        collector, bridge = (
            self.plan["containers"][service]["id"]
            for service in ("servera-collector", "query-bridge")
        )
        calls = []

        def attempt(cid, timeout):
            self.assertGreater(timeout, 0)
            self.assertTrue((self.root / "start-issued.json").exists())
            calls.append(cid)
            if cid == bridge:
                raise subprocess.TimeoutExpired("docker start", timeout)

        def stop(root, plan):
            self.assertTrue((root / "closed.json").exists())
            self.assertEqual(plan, self.plan)

        with patch.object(
            guard,
            "now",
            return_value=datetime(2026, 11, 14, 11, 5, tzinfo=timezone.utc),
        ), patch.object(
            guard, "inspect_plan", return_value={"containers": [created, created]}
        ), patch.object(
            guard, "require_timer"
        ), patch.object(
            guard, "wait_ready"
        ), patch.object(
            guard, "start_container", side_effect=attempt
        ), patch.object(
            guard, "stop", side_effect=stop
        ) as close:
            with self.assertRaises(subprocess.TimeoutExpired):
                guard.lifecycle(self.root, self.plan, self.digest, "start")
        close.assert_called_once()
        self.assertEqual(calls, [collector, bridge])
        self.assertFalse((self.root / "started.json").exists())

    def test_requires_exact_loaded_waiting_enabled_timer(self):
        unit, service, timer = guard.units(self.plan["operation"], CUTOFF, self.digest)
        timer_path = self.root / (unit + ".timer")
        timer_path.write_text(timer)
        (self.root / (unit + ".service")).write_text(service)

        def show(*args):
            stored = self.root / args[-1]
            is_timer = stored.suffix == ".timer"
            active, sub = ("active", "waiting") if is_timer else ("inactive", "dead")
            return (
                f"LoadState=loaded\nFragmentPath={stored}\nDropInPaths=\nNeedDaemonReload=no\n"
                f"ActiveState={active}\nSubState={sub}\nUnitFileState={enabled}\n"
            ).encode()

        enabled = "enabled"
        guard.require_timer(self.plan, self.digest, show, self.root)
        enabled = "enabled-runtime"
        with self.assertRaisesRegex(ValueError, "persist across reboot"):
            guard.require_timer(self.plan, self.digest, show, self.root)
        timer_path.write_text(timer.replace("Persistent=true", "Persistent=false"))
        with self.assertRaisesRegex(ValueError, "installed cutoff unit differs"):
            guard.require_timer(self.plan, self.digest, Mock(), self.root)
