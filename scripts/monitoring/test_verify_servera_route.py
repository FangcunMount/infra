"""Exercise route identity, raw comparison and failure evidence on the CLI."""
from base64 import b64encode
from contextlib import redirect_stdout
from copy import deepcopy
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import sys
import time
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import test_servera_history_seam
import verify_servera_route as route
from m5_window_central_observe import utc


class RouteTest(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.fixture = test_servera_history_seam.SeamTest()
        self.reference = self.fixture.raw(
            "macmini", [1015, 1030, 1045, 1060, 1075, 1090]
        )
        self.binding = dict(
            container="a" * 64,
            image="sha256:" + "b" * 64,
            started_at="2026-10-19T06:19:50.80310569Z",
            config_sha256="c" * 64,
        )
        self.proxy = dict(self.binding, pid=123, private_query_ip=None)

    @staticmethod
    def wire(responses):
        return {
            key: b64encode(json.dumps(value).encode()).decode()
            for key, value in responses.items()
        }

    def exercise(self, callback=None):
        responses = deepcopy(self.reference["responses"])
        self.reference["raw_http"] = self.wire(responses)
        reference = self.root / "reference.json"
        reference.write_text(json.dumps(self.reference))
        expected = self.root / "binding.json"
        expected.write_text(json.dumps(self.binding))
        capture = self.root / "capture.json"
        body = dict(
            proxy_before=self.proxy,
            proxy_after=deepcopy(self.proxy),
            responses=responses,
            http_status=dict.fromkeys(responses, 200),
            errors={},
        )
        if self.reference["route"] == "merged":
            source = self.reference["binding_before"]
            stamp = time.time()
            body["live_candidate"] = dict(
                before={
                    key: source[key] for key in ("container", "image", "started_at")
                },
                after={
                    key: source[key] for key in ("container", "image", "started_at")
                },
                configuration={
                    key: source[key] for key in ("config_sha256", "loaded_at")
                },
                observed_at=stamp,
                targets={
                    "activeTargets": [
                        dict(
                            labels=dict(job=job, instance=instance),
                            health="up",
                            lastScrape=utc(stamp - 2).replace("+00:00", "Z"),
                        )
                        for job, instance in sorted(
                            route.expected_targets(
                                self.reference["collection_ips"],
                                self.reference["qs_source"],
                            )
                        )
                    ]
                },
            )
        if callback:
            callback(body)
        body["raw_http"] = self.wire(body["responses"])
        raw = json.dumps(body).encode()
        window = "h06" if self.reference["route"] == "merged" else "h07"
        args = [
            "verify_servera_route.py",
            window,
            str(reference),
            "--proxy",
            str(expected),
            "--capture",
            str(capture),
        ]

        def probe(argv, **options):
            self.assertIn("StrictHostKeyChecking=yes", argv)
            self.assertIn("servera", argv)
            self.assertIn(b"api/v1/query?", options["input"])
            return raw

        output = StringIO()
        try:
            with patch.object(sys, "argv", args), patch.object(
                route.subprocess, "check_output", side_effect=probe
            ), redirect_stdout(output):
                route.main()
        finally:
            self.assertEqual(capture.read_bytes(), raw)
            self.assertEqual(capture.stat().st_mode & 0o777, 0o600)
        return json.loads(output.getvalue())

    def test_h07_reads_exact_raw_samples(self):
        result = self.exercise()
        self.assertEqual(result["reference_route"], "macmini")
        self.assertEqual(sum(row["samples"] for row in result["counts"].values()), 132)
        self.assertEqual(
            result["proxy_capture_sha256"],
            sha256((self.root / "capture.json").read_bytes()).hexdigest(),
        )
        self.assertFalse(result["execution_authorized"])

    def merged_reference(self):
        self.reference["route"] = "merged"
        for side in ("binding_before", "binding_after"):
            self.reference[side].update(
                remote_read=True,
                container="e" * 64,
                image="sha256:" + "f" * 64,
                started_at="2026-10-19T06:20:04Z",
                config_sha256="d" * 64,
                loaded_at="2026-10-19T06:20:05Z",
            )

    def test_h06_rejects_proxy_outside_private_query_network(self):
        self.merged_reference()
        with self.assertRaisesRegex(
            ValueError, "outside the approved private query network"
        ):
            self.exercise()

    def test_h06_checks_active_candidate_targets(self):
        self.merged_reference()
        self.proxy["private_query_ip"] = "172.31.251.2"
        self.assertEqual(self.exercise()["live_candidate"]["active_targets"], 10)

    def test_h06_rejects_missing_worker_despite_matching_historical_samples(self):
        self.merged_reference()
        self.proxy["private_query_ip"] = "172.31.251.2"

        def remove_worker(body):
            rows = body["live_candidate"]["targets"]["activeTargets"]
            worker = next(row for row in rows if row["labels"]["job"] == "qs-worker")
            rows.remove(worker)

        with self.assertRaisesRegex(
            ValueError, "active targets failed.*missing.*qs-worker"
        ):
            self.exercise(remove_worker)

    def test_h06_rejects_stale_worker_despite_matching_historical_samples(self):
        self.merged_reference()
        self.proxy["private_query_ip"] = "172.31.251.2"

        def expire_worker(body):
            live = body["live_candidate"]
            rows = live["targets"]["activeTargets"]
            worker = next(row for row in rows if row["labels"]["job"] == "qs-worker")
            worker["lastScrape"] = utc(live["observed_at"] - 36).replace("+00:00", "Z")

        with self.assertRaisesRegex(ValueError, "unhealthy_or_stale.*qs-worker"):
            self.exercise(expire_worker)

    def test_h06_rejects_candidate_configuration_drift(self):
        self.merged_reference()
        self.proxy["private_query_ip"] = "172.31.251.2"

        def change(body):
            body["live_candidate"]["configuration"][
                "loaded_at"
            ] = "2026-10-19T06:20:06Z"

        with self.assertRaisesRegex(ValueError, "live collector configuration changed"):
            self.exercise(change)

    def test_preserves_partial_query_warning_and_rejects(self):
        def warning(body):
            body["responses"]["up"]["warnings"] = ["remote read unavailable"]

        with self.assertRaisesRegex(ValueError, "returned annotations"):
            self.exercise(warning)

    def test_preserves_error_http_status_and_rejects(self):
        def failure(body):
            body["http_status"]["up"] = 502

        with self.assertRaisesRegex(ValueError, "did not all return HTTP 200"):
            self.exercise(failure)

    def test_reference_phase_must_match(self):
        self.reference["raw_http"] = self.wire(self.reference["responses"])
        with self.assertRaisesRegex(ValueError, "wrong reference route"):
            route.validate_reference(self.reference, "h06")

    def test_edited_sample_rejected(self):
        def change(body):
            body["responses"]["up"]["data"]["result"][0]["values"][0][1] = "0"

        with self.assertRaisesRegex(ValueError, "raw series differ"):
            self.exercise(change)

    def test_proxy_identity_drift_rejected(self):
        def change(body):
            body["proxy_after"]["pid"] = 987

        with self.assertRaisesRegex(ValueError, "proxy identity changed"):
            self.exercise(change)
