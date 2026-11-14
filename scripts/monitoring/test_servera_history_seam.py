from copy import deepcopy
from base64 import b64encode
import json
from hashlib import sha256
import unittest

from servera_history_seam import (
    METRICS,
    OWNERS,
    bind_history,
    compare,
    expected_targets,
    overlap,
    requests,
    verify_http_bodies,
)


class SeamTest(unittest.TestCase):
    start, end, boundary = 1000, 1150, 1060
    ips = ["172.20.0.114", "172.20.0.115"]
    source = "4620d11e2cffbc4b67b43965812cff3340f0be43"

    def raw(self, route, stamps):
        binding = dict(
            volume={"name": "data", "created_at": "fixture"},
            image="fixture",
            remote_read=route == "merged",
        )
        receipt = dict(
            schema="servera-prometheus-raw-seam/v1",
            read_only=True,
            start=self.start,
            end=self.end,
            qs_source=self.source,
            collection_ips=self.ips,
            requests=requests(self.start, self.end),
            route=route,
            binding_before=binding,
            binding_after=deepcopy(binding),
            responses={},
        )
        storage = dict(
            local_min_ms=self.boundary * 1000,
            persisted_blocks=1,
            min_block_duration="2h",
        )
        receipt["storage_before"] = storage
        receipt["storage_after"] = deepcopy(storage)
        for metric, value in METRICS.items():
            keys = (
                ("job", "instance") if metric == "up" else ("job", "instance", "owner")
            )
            identities = (
                expected_targets(self.ips, self.source) if metric == "up" else OWNERS
            )
            rows = [
                dict(
                    metric=dict(zip(keys, identity), __name__=metric),
                    values=[[stamp, str(value)] for stamp in stamps],
                )
                for identity in sorted(identities)
            ]
            receipt["responses"][metric] = dict(
                status="success", data=dict(resultType="matrix", result=rows)
            )
        return receipt

    def setUp(self):
        self.history = self.raw("history", [1015, 1030, 1045, 1060, 1075, 1090])
        self.local = self.raw("candidate", [1060, 1075, 1090, 1105])
        self.merged = self.raw("merged", [1015, 1030, 1045, 1060, 1075, 1090, 1105])

    def verify(self):
        return compare(self.history, self.local, self.merged, self.boundary * 1000)

    def test_field_receipt_requires_matching_exact_http_bodies(self):
        with self.assertRaisesRegex(ValueError, "exact HTTP response coverage"):
            verify_http_bodies(self.history)
        self.history["raw_http"] = {
            name: b64encode(json.dumps(response).encode()).decode()
            for name, response in self.history["responses"].items()
        }
        verify_http_bodies(self.history)
        self.history["responses"]["up"]["data"]["result"][0]["values"][0][1] = "0"
        with self.assertRaisesRegex(ValueError, "exact HTTP body differs"):
            verify_http_bodies(self.history)

    def test_overlap_and_complete_handoff(self):
        source = deepcopy(self.history)
        source["route"] = "macmini"
        self.assertEqual(len(overlap(source, self.local)["series"]), 22)
        result = self.verify()
        self.assertEqual(len(result["series"]), 22)
        self.assertFalse(result["requires_gap_review"])
        self.assertFalse(result["execution_authorized"])

    def test_independent_scrape_clocks_keep_old_samples_through_remote_cutoff(self):
        self.local = self.raw("candidate", [1061, 1076, 1091, 1106])
        self.merged = self.raw(
            "merged", [1015, 1030, 1045, 1060, 1061, 1075, 1076, 1090, 1091, 1106]
        )
        result = self.verify()
        self.assertFalse(result["requires_gap_review"])

    def test_early_archive_rejected_even_with_unannotated_response(self):
        self.history = self.raw("history", [1015, 1030])
        self.merged = self.raw("merged", [1015, 1030, 1060, 1075, 1090, 1105])
        with self.assertRaisesRegex(ValueError, "does not reach"):
            self.verify()

    def test_missing_raw_timestamp_rejected(self):
        self.merged["responses"]["up"]["data"]["result"][0]["values"].pop(1)
        with self.assertRaisesRegex(ValueError, "raw sample timestamps"):
            self.verify()

    def test_modified_raw_value_rejected(self):
        self.merged["responses"]["up"]["data"]["result"][0]["values"][1][1] = "0"
        with self.assertRaisesRegex(ValueError, "timestamps or values"):
            self.verify()

    def test_label_drift_rejected(self):
        self.merged["responses"]["up"]["data"]["result"][0]["metric"]["extra"] = "drift"
        with self.assertRaisesRegex(ValueError, "complete label set"):
            self.verify()

    def test_warning_rejected(self):
        self.merged["responses"]["up"]["warnings"] = ["history is unavailable"]
        with self.assertRaisesRegex(ValueError, "returned annotations"):
            self.verify()

    def test_head_only_candidate_reads_the_entire_requested_history(self):
        for capture in (self.local, self.merged):
            for timing in ("storage_before", "storage_after"):
                capture[timing]["persisted_blocks"] = 0
        self.assertFalse(self.verify()["requires_gap_review"])

    def test_tsdb_drift_is_rejected(self):
        self.merged["storage_after"]["local_min_ms"] += 1
        with self.assertRaisesRegex(ValueError, "storage boundary changed"):
            self.verify()

    def test_import_binds_actual_receipt_fields_and_exact_originals(self):
        def encoded(value):
            return json.dumps(value).encode()

        archive = "a" * 64
        b05 = dict(
            schema="monitoring-h03-b05-restore/v1",
            operation_id="h03-window",
            rehearsal=False,
            restored_from_verified_second_copy=True,
            isolated_restore_verified=True,
            h06_prometheus_archive_sha256=archive,
            production_mutation=False,
            prometheus=dict(
                archive_sha256=archive,
                isolated=True,
                wal_replay_complete=True,
                archive_members_verified=63,
            ),
        )
        b05_raw = encoded(b05)
        b05_sha = sha256(b05_raw).hexdigest()
        volume = dict(
            name="qlume-servera-monitoring-history",
            created_at="fixture",
            mount_source="/fixture",
        )
        self.history["binding_before"]["volume"] = self.history["binding_after"][
            "volume"
        ] = volume
        approval = dict(
            schema="monitoring-h06-history-import-approval/v1",
            operation_id="h06-window",
            fixture=False,
            h03_operation_id="h03-window",
            archive_sha256=archive,
            b05_sha256=b05_sha,
            volume=volume["name"],
            operator="operator",
            reviewer="reviewer",
            decision_reference="approval-original",
            starts_at="2026-11-14T10:00:00Z",
            expires_at="2026-11-14T10:30:00Z",
        )

        def proof(values):
            return dict(
                schema="monitoring-h06-history-import/v1",
                h03_operation_id="h03-window",
                archive_sha256=archive,
                volume=volume,
                restore_verified=True,
                fixture=False,
                b05_sha256=b05_sha,
                approval_sha256=sha256(encoded(values)).hexdigest(),
                operation_id="h06-window",
                archive_members=63,
                fsynced=True,
                readback_verified_at="2026-11-14T10:07:00+00:00",
            )

        original = proof(approval)
        args = (b05_raw, encoded(original), encoded(approval), self.history)
        result = bind_history(*args)
        self.assertEqual(result["archive_sha256"], archive)
        self.assertEqual(result["b05_receipt_sha256"], b05_sha)
        with self.assertRaisesRegex(ValueError, "not bound"):
            bind_history(b05_raw + b"\n", *args[1:])
        with self.assertRaisesRegex(ValueError, "not bound"):
            bind_history(*args[:2], encoded(approval) + b"\n", self.history)

        for field, value in (
            ("archive_sha256", "b" * 64),
            ("archive_members", 62),
            ("fsynced", False),
            ("fixture", True),
            ("volume", dict(volume, created_at="replacement")),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError, "not bound"
            ):
                bind_history(
                    b05_raw, encoded(dict(original, **{field: value})), *args[2:]
                )
        with self.assertRaisesRegex(ValueError, "outside the approved window"):
            bind_history(
                b05_raw,
                encoded(dict(original, readback_verified_at=approval["expires_at"])),
                *args[2:]
            )
        same = dict(approval, reviewer=" operator ")
        with self.assertRaisesRegex(ValueError, "approval does not bind"):
            bind_history(b05_raw, encoded(proof(same)), encoded(same), self.history)

    def test_wrong_volume_rejected(self):
        self.merged["binding_before"]["volume"] = {"name": "other"}
        self.merged["binding_after"] = deepcopy(self.merged["binding_before"])
        with self.assertRaisesRegex(ValueError, "volume or image changed"):
            self.verify()

    def test_gap_requires_review_even_when_samples_are_exact(self):
        self.local = self.raw("candidate", [1060, 1075, 1145])
        self.merged = self.raw("merged", [1015, 1030, 1045, 1060, 1075, 1090, 1145])
        self.assertTrue(self.verify()["requires_gap_review"])

    def test_overlap_keeps_history_samples_before_late_candidate_series(self):
        self.local = self.raw("candidate", [1090, 1105])
        self.merged = self.raw("merged", [1015, 1030, 1045, 1060, 1075, 1090, 1105])
        self.assertFalse(self.verify()["requires_gap_review"])


if __name__ == "__main__":
    unittest.main()
