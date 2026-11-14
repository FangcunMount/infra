"""Capture Prometheus raw samples and verify the handoff at a named TSDB boundary."""
import argparse
from base64 import b64decode
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import math
import re
from pathlib import Path

from m5_window_central_observe import (
    METRICS,
    OWNERS,
    MAX_AGE,
    expected_targets,
    scrape_time,
)


def fail_if(condition, message):
    if condition:
        raise ValueError(message)


def check_span(start, end):
    fail_if(
        not (0 < end - start <= 900), "UTC interval must be between 1 and 900 seconds"
    )


def endpoint_time(value):
    fail_if(not value.endswith("Z"), "timestamp requires an explicit UTC Z suffix")
    return round(scrape_time(value) * 1000)


def utc_stamp(stamp):
    return datetime.fromtimestamp(stamp / 1000, timezone.utc).isoformat()


def requests(start, end):
    check_span(start, end)
    return {
        metric: dict(query=f"{metric}[{end-start}s]", time=end) for metric in METRICS
    }


def matrix(response, metric, start, end):
    fail_if(
        response.get("status") != "success"
        or response.get("warnings")
        or response.get("infos"),
        f"{metric}: Prometheus query failed or returned annotations",
    )
    data = response["data"]
    fail_if(
        data["resultType"] != "matrix", f"{metric}: expected original sample matrix"
    )
    result = {}
    for row in data["result"]:
        labels = row["metric"]
        fail_if(labels.get("__name__") != metric, f"{metric}: unexpected metric name")
        key = tuple(sorted(labels.items()))
        fail_if(key in result, f"{metric}: duplicate complete label set")
        samples = {}
        previous = start * 1000
        for timestamp, value in row["values"]:
            milliseconds = Decimal(str(timestamp)) * 1000
            fail_if(
                milliseconds % 1 != 0 or not previous < milliseconds <= end * 1000,
                f"{metric}: sample outside the interval or out of order",
            )
            fail_if(
                not isinstance(value, str) or not math.isfinite(float(value)),
                f"{metric}: invalid sample value",
            )
            previous = stamp = int(milliseconds)
            samples[stamp] = value
        fail_if(not samples, f"{metric}: empty series")
        result[key] = samples
    return result


def named_rows(values, metric, expected):
    names = ("job", "instance") if metric == "up" else ("job", "instance", "owner")
    by_name = {}
    for labels, samples in values.items():
        if (
            identity := tuple(dict(labels).get(name) for name in names)
        ) not in expected:
            continue
        fail_if(identity in by_name, f"{metric}: duplicate named series for {identity}")
        by_name[identity] = labels, samples
    fail_if(
        by_name.keys() != expected,
        f"{metric}: missing named series {sorted(expected-by_name.keys())}",
    )
    return by_name


def joined_inputs(receipts):
    first, *rest = receipts
    fields = ("start", "end", "qs_source", "collection_ips", "requests")
    for receipt in receipts:
        fail_if(
            receipt["schema"] != "servera-prometheus-raw-seam/v1"
            or not receipt["read_only"],
            "unrecognized raw receipt",
        )
        fail_if(
            receipt["requests"] != requests(receipt["start"], receipt["end"]),
            "capture did not use the expected fixed range selectors",
        )
        fail_if(
            any(receipt[field] != first[field] for field in fields),
            "raw captures have different scope",
        )
        fail_if(
            receipt["binding_before"] != receipt["binding_after"],
            "Prometheus identity changed during capture",
        )
        fail_if(
            set(receipt["responses"]) != METRICS.keys(), "raw metric coverage mismatch"
        )
    return (
        first["start"],
        first["end"],
        expected_targets(first["collection_ips"], first["qs_source"]),
    )


def verify_http_bodies(receipt):
    bodies = receipt.get("raw_http", {})
    fail_if(set(bodies) != METRICS.keys(), "exact HTTP response coverage mismatch")
    for metric, encoded in bodies.items():
        raw = b64decode(encoded, validate=True)
        fail_if(
            len(raw) > 1_000_000 or json.loads(raw) != receipt["responses"][metric],
            f"{metric}: exact HTTP body differs from the sample matrix",
        )


def overlap(source, candidate):
    start, end, targets = joined_inputs((source, candidate))
    fail_if(
        source["route"] != "macmini" or candidate["route"] != "candidate",
        "overlap requires the old source and candidate-local receipts",
    )
    fail_if(
        source["binding_before"]["remote_read"]
        or candidate["binding_before"]["remote_read"],
        "overlap requires raw data captured from each local TSDB",
    )
    output = []
    for metric, healthy in METRICS.items():
        expected = targets if metric == "up" else OWNERS
        old, local = [
            named_rows(
                matrix(rec["responses"][metric], metric, start, end), metric, expected
            )
            for rec in (source, candidate)
        ]
        for identity in sorted(expected):
            old_labels, old_samples = old[identity]
            new_labels, new_samples = local[identity]
            fail_if(
                old_labels != new_labels,
                f"{metric}: complete label set differs for {identity}",
            )
            common_start = max(min(old_samples), min(new_samples))
            common_end = min(max(old_samples), max(new_samples))
            fail_if(
                common_end - common_start < 15000,
                f"{metric}: no confirmed collection overlap for {identity}",
            )
            for data in (old_samples, new_samples):
                stamps = [
                    t
                    for t, value in data.items()
                    if common_start <= t <= common_end and float(value) == healthy
                ]
                fail_if(
                    not stamps,
                    f"{metric}: no healthy sampled value during overlap for {identity}",
                )
            output.append(
                dict(
                    metric=metric,
                    labels=dict(old_labels),
                    observed_start=utc_stamp(common_start),
                    observed_end=utc_stamp(common_end),
                )
            )
    return dict(
        kind="source_candidate_raw_overlap", series=output, execution_authorized=False
    )


def compare(history, candidate, merged, boundary_ms):
    start, end, targets = joined_inputs((history, candidate, merged))
    fail_if(
        (history["route"], candidate["route"], merged["route"])
        != ("history", "candidate", "merged"),
        "splice comparison requires history, candidate-local and merged receipts",
    )
    fail_if(
        history["binding_before"]["remote_read"]
        or candidate["binding_before"]["remote_read"]
        or not merged["binding_before"]["remote_read"],
        "raw receipts use the wrong history config",
    )
    fail_if(
        not start * 1000 < boundary_ms < end * 1000,
        "local TSDB boundary must be inside the query interval",
    )
    storage = merged["storage_before"]
    fail_if(
        storage != merged["storage_after"] or storage["local_min_ms"] != boundary_ms,
        "merged TSDB storage boundary changed or differs from the supplied value",
    )
    fail_if(
        storage["min_block_duration"] != "2h",
        "minimum block duration differs from the reviewed configuration",
    )
    reference = candidate["storage_before"]
    fail_if(
        reference != candidate["storage_after"]
        or reference["local_min_ms"] != boundary_ms,
        "candidate-local TSDB boundary changed or differs from the merged candidate",
    )
    # Prometheus 2.54.1 uses the earliest block plus a four-hour margin.
    # Without blocks it uses the query wall clock plus that margin, beyond this historical interval.
    remote_cutoff_ms = (
        boundary_ms + 4 * 3600_000 if storage["persisted_blocks"] else end * 1000
    )
    fail_if(
        candidate["binding_before"]["volume"] != merged["binding_before"]["volume"]
        or candidate["binding_before"]["image"] != merged["binding_before"]["image"],
        "candidate local TSDB volume or image changed",
    )
    details = []
    for metric in METRICS:
        expected = targets if metric == "up" else OWNERS
        raw = [
            matrix(rec["responses"][metric], metric, start, end)
            for rec in (history, candidate, merged)
        ]
        named = [named_rows(rows, metric, expected) for rows in raw]
        for identity in sorted(expected):
            (old_labels, old), (new_labels, new), (merged_labels, observed) = [
                rows[identity] for rows in named
            ]
            fail_if(
                old_labels != new_labels or new_labels != merged_labels,
                f"{metric}: complete label set differs for {identity}",
            )
            fail_if(
                not min(old) < boundary_ms or max(old) < min(new),
                f"{metric}: history does not reach the first candidate sample for {identity}",
            )
            fail_if(
                min(new) < boundary_ms,
                f"{metric}: candidate sample precedes the declared boundary",
            )
            expected_values = {
                stamp: val for stamp, val in old.items() if stamp <= remote_cutoff_ms
            }
            expected_values.update(new)
            fail_if(
                expected_values != observed,
                f"{metric}: merged raw sample timestamps or values differ for {identity}",
            )
            stamps = sorted(observed)
            gaps = [
                {"after": utc_stamp(a), "before": utc_stamp(b)}
                for a, b in zip(stamps, stamps[1:])
                if b - a > MAX_AGE * 1000
            ]
            suppressed_before_local = [
                utc_stamp(t) for t in old if remote_cutoff_ms < t < min(new)
            ]
            details.append(
                dict(
                    metric=metric,
                    labels=dict(old_labels),
                    samples=len(observed),
                    gaps=gaps,
                    source_samples_after_boundary_before_local=suppressed_before_local,
                )
            )
    return dict(
        kind="history_candidate_raw_comparison",
        boundary=utc_stamp(boundary_ms),
        remote_read_query_upper_bound=utc_stamp(min(remote_cutoff_ms, end * 1000)),
        series=details,
        requires_gap_review=any(
            row["gaps"] or row["source_samples_after_boundary_before_local"]
            for row in details
        ),
        execution_authorized=False,
    )


def bind_history(b05_bytes, import_bytes, approval_bytes, capture):
    b05, volume, approval = map(json.loads, (b05_bytes, import_bytes, approval_bytes))
    b05_digest = sha256(b05_bytes).hexdigest()
    approval_digest = sha256(approval_bytes).hexdigest()
    fail_if(
        b05["schema"] != "monitoring-h03-b05-restore/v1"
        or b05["rehearsal"] is not False
        or b05["restored_from_verified_second_copy"] is not True
        or b05["isolated_restore_verified"] is not True
        or b05["production_mutation"] is not False,
        "actual B05 second-copy restore is required",
    )
    archive = b05["h06_prometheus_archive_sha256"]
    fail_if(not re.fullmatch(r"[a-f0-9]{64}", archive), "B05 archive digest is invalid")
    restored = b05["prometheus"]
    fail_if(
        restored["archive_sha256"] != archive
        or restored["isolated"] is not True
        or restored["wal_replay_complete"] is not True
        or type(restored["archive_members_verified"]) is not int
        or restored["archive_members_verified"] <= 0,
        "B05 restore is not bound to the same archive",
    )
    fail_if(
        volume["schema"] != "monitoring-h06-history-import/v1"
        or volume["fixture"] is not False
        or volume["h03_operation_id"] != b05["operation_id"]
        or volume["archive_sha256"] != archive
        or volume["b05_sha256"] != b05_digest
        or volume["approval_sha256"] != approval_digest
        or volume["volume"] != capture["binding_before"]["volume"]
        or type(volume["archive_members"]) is not int
        or volume["archive_members"] != restored["archive_members_verified"]
        or volume["restore_verified"] is not True
        or volume["fsynced"] is not True,
        "history volume import is not bound to the B05 archive and captured volume",
    )
    fail_if(
        approval["schema"] != "monitoring-h06-history-import-approval/v1"
        or approval["fixture"] is not False
        or approval["archive_sha256"] != archive
        or approval["b05_sha256"] != b05_digest
        or approval["operation_id"] != volume["operation_id"]
        or approval["h03_operation_id"] != b05["operation_id"]
        or approval["volume"] != volume["volume"]["name"]
        or approval["volume"] != "qlume-servera-monitoring-history"
        or not approval["operator"].strip()
        or not approval["reviewer"].strip()
        or approval["operator"].strip() == approval["reviewer"].strip()
        or not approval["decision_reference"].strip(),
        "history import approval does not bind the same recovery and volume",
    )
    start, verified_at, expiry = (
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        for value in (
            approval["starts_at"],
            volume["readback_verified_at"],
            approval["expires_at"],
        )
    )
    fail_if(
        any(value.utcoffset() is None for value in (start, verified_at, expiry))
        or not start <= verified_at < expiry,
        "history import readback is outside the approved window",
    )
    return dict(
        archive_sha256=archive,
        volume_name=volume["volume"]["name"],
        operation_id=volume["operation_id"],
        h03_operation_id=b05["operation_id"],
        b05_receipt_sha256=b05_digest,
        approval_sha256=approval_digest,
        import_receipt_sha256=sha256(import_bytes).hexdigest(),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["overlap", "compare"])
    parser.add_argument("receipts", nargs="+", type=Path)
    parser.add_argument(
        "--local-boundary", help="first timestamp of candidate local TSDB, in UTC"
    )
    parser.add_argument("--b05", type=Path, help="verified second-copy restore receipt")
    parser.add_argument(
        "--import-approval", type=Path, help="approved H06 volume import original"
    )
    parser.add_argument(
        "--history-volume-proof",
        type=Path,
        help="H06 approved history volume import receipt",
    )
    args = parser.parse_args()
    inputs = [path.read_bytes() for path in args.receipts]
    parsed = [json.loads(data) for data in inputs]
    for receipt in parsed:
        verify_http_bodies(receipt)
    if (
        args.mode == "overlap"
        and len(parsed) == 2
        and not (
            args.local_boundary
            or args.b05
            or args.history_volume_proof
            or args.import_approval
        )
    ):
        result = overlap(*parsed)
    elif (
        args.mode == "compare"
        and len(parsed) == 3
        and args.local_boundary
        and args.b05
        and args.history_volume_proof
        and args.import_approval
    ):
        boundary = endpoint_time(args.local_boundary)
        result = compare(*parsed, boundary)
        b05, volume, approval = (
            path.read_bytes()
            for path in (args.b05, args.history_volume_proof, args.import_approval)
        )
        result["history_binding"] = bind_history(b05, volume, approval, parsed[0])
    else:
        parser.error(
            "overlap needs two receipts; compare also needs --local-boundary, --b05, --history-volume-proof and --import-approval"
        )
    result["receipt_sha256"] = [sha256(data).hexdigest() for data in inputs]
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
