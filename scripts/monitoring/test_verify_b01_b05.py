from base64 import b64encode
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from datetime import datetime, timezone

import test_servera_history_seam as test_seam
from verify_b01_b05 import verify


class BindingTest(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.old_dir = self.root / "b01"
        self.old_dir.mkdir()
        scope = ("start", "end", "qs_source", "collection_ips")
        case = test_seam.SeamTest()
        operation = "cold-operation-fixture"
        archive = "b" * 64
        self.old = case.raw("macmini", [1075, 1090, 1105, 1120, 1135, 1150])
        for end in ("binding_before", "binding_after"):
            self.old[end].update(container="a" * 64, started_at="1970-01-01T00:00:00Z")
        self.candidate = case.raw("candidate", [1076, 1091, 1106, 1121, 1136])
        self.history = deepcopy(self.old)
        self.history["route"] = "history"
        self.volume = dict(
            name="qlume-servera-monitoring-history",
            created_at="test",
            mount_source="/fixture",
        )
        self.history["binding_before"]["volume"] = self.history["binding_after"][
            "volume"
        ] = self.volume
        old_sha = self.write(self.old_dir / "macmini.json", self.old)
        new_sha = self.write(self.old_dir / "candidate.json", self.candidate)
        utc = lambda s: datetime.fromtimestamp(s, timezone.utc).isoformat()
        self.receipt = dict(
            schema="monitoring-h03-b01-capture/v1",
            operation_id=operation,
            capture_exit={"macmini": 0, "candidate": 0},
            eligible_for_review=True,
            execution_authorized=False,
            completed_utc=utc(1151),
            scope={k: self.old[k] for k in scope},
            originals_sha256={"macmini.json": old_sha, "candidate.json": new_sha},
        )
        receipt_sha = self.write(self.old_dir / "b01-receipt.json", self.receipt)
        source_sha = self.write(
            self.root / "source.json",
            dict(
                b01_overlap_receipt_sha256=receipt_sha,
                containers={
                    "prometheus": dict(
                        id="a" * 64,
                        image="fixture",
                        started_at="1970-01-01T00:00:00Z",
                        volume="data",
                    )
                },
            ),
        )
        self.approval = dict(
            schema="monitoring-h03-cold-window/v1",
            operation_id=operation,
            start_utc=utc(1100),
            recovery_deadline_utc=utc(1180),
            end_utc=utc(1200),
            source_sha256=source_sha,
        )
        approved_sha = self.write(self.root / "approval.json", self.approval)
        started_sha = self.write(
            self.root / "started.json",
            dict(operation_id=operation, at=utc(1155), approval_sha256=approved_sha),
        )
        self.manifest = dict(
            schema="monitoring-h03-post-cold-handoff/v1",
            operation_id=operation,
            rehearsal=False,
            files={
                key: {"sha256": value}
                for key, value in (
                    ("source.json", source_sha),
                    ("approval.json", approved_sha),
                    ("started.json", started_sha),
                    ("prometheus.tar.gz", archive),
                )
            },
        )
        manifest_sha = self.write(self.root / "post-cold-manifest.json", self.manifest)
        self.b05 = dict(
            schema="monitoring-h03-b05-restore/v1",
            operation_id=operation,
            rehearsal=False,
            manifest_sha256=manifest_sha,
            restored_from_verified_second_copy=True,
            isolated_restore_verified=True,
            h06_prometheus_archive_sha256=archive,
            production_mutation=False,
            prometheus=dict(
                wal_replay_complete=True,
                archive_sha256=archive,
                isolated=True,
                archive_members_verified=63,
            ),
        )
        b05_sha = self.write(self.root / "b05.json", self.b05)
        h06_approval = dict(
            schema="monitoring-h06-history-import-approval/v1",
            fixture=False,
            h03_operation_id=operation,
            operation_id="import-operation-fixture",
            archive_sha256=archive,
            b05_sha256=b05_sha,
            volume=self.volume["name"],
            operator="operator",
            reviewer="reviewer",
            decision_reference="test",
            starts_at=utc(1200),
            expires_at=utc(1400),
        )
        import_approval_sha = self.write(
            self.root / "import-approval.json", h06_approval
        )
        self.ingest = dict(
            schema="monitoring-h06-history-import/v1",
            h03_operation_id=operation,
            operation_id=h06_approval["operation_id"],
            fixture=False,
            archive_members=63,
            fsynced=True,
            readback_verified_at=utc(1300),
            approval_sha256=import_approval_sha,
            archive_sha256=archive,
            b05_sha256=b05_sha,
            restore_verified=True,
            volume=self.volume,
        )
        self.write(self.root / "import.json", self.ingest)
        self.write(self.root / "history.json", self.history)

    def write(self, path, value):
        if value.get("schema") == "servera-prometheus-raw-seam/v1":
            value = dict(
                value,
                raw_http={
                    name: b64encode(json.dumps(body).encode()).decode()
                    for name, body in value["responses"].items()
                },
            )
        raw = (json.dumps(value) + "\n").encode()
        path.write_bytes(raw)
        return sha256(raw).hexdigest()

    def check(self):
        return verify(
            self.old_dir,
            self.root,
            self.root / "b05.json",
            self.root / "import.json",
            self.root / "history.json",
            self.root / "import-approval.json",
        )

    def test_full_chain(self):
        result = self.check()
        self.assertEqual(result["exact_restored_b01_samples"], 132)
        self.assertFalse(result["execution_authorized"])

    def test_mutated_receipt(self):
        self.receipt["completed_utc"] = "1970-01-01T00:19:15Z"
        self.write(self.old_dir / "b01-receipt.json", self.receipt)
        with self.assertRaisesRegex(ValueError, "consumed approval"):
            self.check()

    def test_wrong_restore_operation(self):
        self.b05["operation_id"] = "different-operation"
        self.write(self.root / "b05.json", self.b05)
        with self.assertRaisesRegex(ValueError, "operation ID differs"):
            self.check()

    def test_wrong_archive(self):
        self.ingest["archive_sha256"] = "a" * 64
        self.write(self.root / "import.json", self.ingest)
        with self.assertRaisesRegex(ValueError, "different archive"):
            self.check()

    def test_import_references_different_b05_receipt(self):
        self.ingest["b05_sha256"] = "a" * 64
        self.write(self.root / "import.json", self.ingest)
        with self.assertRaisesRegex(ValueError, "captured volume"):
            self.check()

    def test_archived_original_must_preserve_failed_sample_or_gap(self):
        self.history["responses"]["up"]["data"]["result"][0]["values"].pop(1)
        self.write(self.root / "history.json", self.history)
        with self.assertRaisesRegex(ValueError, "archive changed original"):
            self.check()

    def test_wrong_volume(self):
        for phase in ("binding_before", "binding_after"):
            self.history[phase]["volume"] = {"name": "other"}
        self.write(self.root / "history.json", self.history)
        with self.assertRaisesRegex(ValueError, "captured volume"):
            self.check()

    def test_original_drift(self):
        self.old["responses"]["up"]["data"]["result"][0]["values"].pop(0)
        self.write(self.old_dir / "macmini.json", self.old)
        with self.assertRaisesRegex(ValueError, "collector original"):
            self.check()
