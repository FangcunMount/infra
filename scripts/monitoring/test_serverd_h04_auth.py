"""Check authorization expiry rendering and fixed SSH restrictions."""
from base64 import b64encode
from hashlib import sha256
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2] / "deploy/serverA/monitoring/h04"
spec = importlib.util.spec_from_file_location(
    "serverd_h04_auth", SOURCE / "serverd-auth.py"
)
auth = importlib.util.module_from_spec(spec)
with patch.object(sys, "path", [str(SOURCE), *sys.path]):
    spec.loader.exec_module(auth)


class H04AuthorizationTest(unittest.TestCase):
    def setUp(self):
        blob = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes(32)
        self.plan = dict(
            key_blob=b64encode(blob).decode(),
            public_fingerprint="SHA256:"
            + b64encode(sha256(blob).digest()).decode().rstrip("="),
            original_line_sha256="a" * 64,
            starts_utc="2026-11-14T09:00:00Z",
            latest_start_utc="2026-11-14T09:20:00Z",
            cutoff_utc="2026-11-14T12:00:00Z",
        )

    def test_scope_and_cutoff_are_rendered_into_exact_line(self):
        row, _, _ = auth.auth_line("h04-qualified", self.plan)
        self.assertEqual(
            row.decode(),
            'restrict,from="100.74.123.45",expiry-time="20261114195959",'
            'command="/usr/local/sbin/infra-monitoring-discovery" ssh-ed25519 '
            + self.plan["key_blob"]
            + " h04-qualified\n",
        )

    def test_rejects_wrong_fingerprint_or_key_type(self):
        with self.assertRaisesRegex(ValueError, "fingerprint differs"):
            auth.auth_line(
                "h04-qualified", dict(self.plan, public_fingerprint="SHA256:wrong")
            )
        with self.assertRaisesRegex(ValueError, "ED25519"):
            auth.auth_line(
                "h04-qualified", dict(self.plan, key_blob=b64encode(bytes(51)).decode())
            )

    def test_expiry_after_midnight_and_wrong_zone(self):
        cutoff = "2026-11-14T16:00:00Z"
        rendered = auth.render(cutoff, "Asia/Shanghai")
        self.assertEqual(rendered["sshd_expiry_time"], "20261114235959")
        with self.assertRaisesRegex(ValueError, "timezone drift"):
            auth.render(cutoff, "UTC")

    def test_persistent_timer_binds_exact_plan_sha(self):
        digest = "b" * 64
        name, service, timer, _ = auth.units(
            "h04-qualified", self.plan["cutoff_utc"], "Asia/Shanghai", digest
        )
        self.assertIn(f"serverd-auth.py withdraw {digest}", service)
        self.assertIn("OnCalendar=2026-11-14 12:00:00 UTC\nPersistent=true", timer)
        self.assertIn(f"Unit={name}.service", timer)
        with self.assertRaisesRegex(ValueError, "SHA-256 required"):
            auth.units(
                "h04-qualified", self.plan["cutoff_utc"], "Asia/Shanghai", "other"
            )


    def test_h06_has_independent_operation_units_and_exact_line(self):
        cutoff = self.plan["cutoff_utc"]
        old, *_ = auth.units("h04-qualified", cutoff, "Asia/Shanghai", "b" * 64)
        name, service, timer, _ = auth.units("h06-qualified", cutoff, "Asia/Shanghai", "c" * 64)
        self.assertNotEqual(old, name)
        self.assertIn("/h06-qualified/serverd-auth.py withdraw " + "c" * 64, service)
        self.assertIn(f"Unit={name}.service", timer)
        row, _, _ = auth.auth_line("h06-qualified", self.plan)
        self.assertTrue(row.endswith(b" h06-qualified\n"))
        with self.assertRaisesRegex(ValueError, "H04 or H06"):
            auth.units("h07-qualified", cutoff, "Asia/Shanghai", "c" * 64)
