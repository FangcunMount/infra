"""Regression tests for the history import approval and archive boundary."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
import unittest

from restore_history_volume import approved_inputs
from verify_monitoring_archive import verify


class HistoryImportTests(unittest.TestCase):
    def setUp(self):
        archive = "a" * 64
        self.b05 = json.dumps(
            dict(
                schema="monitoring-h03-b05-restore/v1",
                rehearsal=True,
                restored_from_verified_second_copy=True,
                isolated_restore_verified=True,
                production_mutation=False,
                operation_id="h03-tester",
                h06_prometheus_archive_sha256=archive,
                prometheus=dict(
                    archive_sha256=archive, isolated=True, wal_replay_complete=True
                ),
            )
        ).encode()
        now = datetime.now(timezone.utc)
        self.approval = dict(
            schema="monitoring-h06-history-import-approval/v1",
            fixture=True,
            operation_id="m5-h06-fixture-test",
            h03_operation_id="h03-tester",
            b05_sha256=sha256(self.b05).hexdigest(),
            archive_sha256=archive,
            operator="operator",
            reviewer="reviewer",
            decision_reference="isolated-test",
            starts_at=(now - timedelta(minutes=5)).isoformat(),
            expires_at=(now + timedelta(minutes=30)).isoformat(),
            helper="sha256:" + "b" * 64,
            volume="m5-h06-fixture-test",
        )

    def test_parsed_b05_is_bound_to_exact_original_bytes(self):
        approval = json.dumps(self.approval).encode()
        self.assertEqual(
            approved_inputs(self.b05, approval, True)[1], self.approval["operation_id"]
        )
        with self.assertRaisesRegex(ValueError, "approval does not cover B05"):
            approved_inputs(self.b05 + b"\n", approval, True)

    def test_same_actor_with_whitespace_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "independent approval"):
            approved_inputs(
                self.b05,
                json.dumps(dict(self.approval, reviewer=" operator ")).encode(),
                True,
            )

    def test_production_rejects_rehearsal_receipt(self):
        with self.assertRaisesRegex(ValueError, "verified second-copy"):
            approved_inputs(self.b05, json.dumps(self.approval).encode(), False)

    def test_archive_cannot_escape_the_staging_directory(self):
        for name in ("../outside", "/absolute"):
            with self.subTest(name=name), TemporaryDirectory() as temp:
                archive = Path(temp) / "archive.tar.gz"
                with tarfile.open(archive, "w:gz") as stream:
                    info = tarfile.TarInfo(name)
                    info.size = 1
                    stream.addfile(info, BytesIO(b"x"))
                with self.assertRaises(AssertionError):
                    verify(archive, "prometheus", 1024 * 1024)
