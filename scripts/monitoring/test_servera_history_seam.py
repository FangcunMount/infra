from copy import deepcopy
from base64 import b64encode
import json
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

    def test_import_must_match_restored_archive_and_history_volume(self):
        archive = "a" * 64
        b05 = dict(
            schema="monitoring-h03-b05-restore/v1",
            operation_id="test",
            rehearsal=False,
            restored_from_verified_second_copy=True,
            isolated_restore_verified=True,
            h06_prometheus_archive_sha256=archive,
            prometheus=dict(
                archive_sha256=archive, isolated=True, wal_replay_complete=True
            ),
        )
        proof = dict(
            schema="monitoring-h06-history-import/v1",
            h03_operation_id="test",
            archive_sha256=archive,
            volume=self.history["binding_before"]["volume"],
            restore_verified=True,
        )
        self.assertEqual(
            bind_history(b05, proof, self.history)["archive_sha256"], archive
        )
        proof["archive_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "not bound"):
            bind_history(b05, proof, self.history)

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
