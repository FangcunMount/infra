"""Bind a reviewed B01 overlap to the cold backup and its restored samples."""
import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

from check_b01 import verify as check_overlap
from servera_history_seam import (
    METRICS,
    OWNERS,
    bind_history,
    joined_inputs,
    matrix,
    named_rows,
    verify_http_bodies,
)


def read(path):
    raw = path.read_bytes()
    return json.loads(raw), sha256(raw).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def utc(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.utcoffset() is not None, "receipt time must include its UTC offset")
    return result


def match_source(source, capture):
    identity = source["containers"]["prometheus"]
    old_identity = capture["binding_before"]
    require(
        all(
            old_identity[raw] == identity[signed]
            for raw, signed in (
                ("container", "id"),
                ("image", "image"),
                ("started_at", "started_at"),
            )
        )
        and old_identity["volume"]["name"] == identity["volume"],
        "original B01 collector identity differs",
    )


def paired_originals(b01_dir, receipt):
    old, old_sha = read(b01_dir / "macmini.json")
    candidate, candidate_sha = read(b01_dir / "candidate.json")
    require(
        receipt["originals_sha256"]["macmini.json"] == old_sha
        and receipt["originals_sha256"]["candidate.json"] == candidate_sha,
        "B01 collector original differs",
    )
    for item in (old, candidate):
        verify_http_bodies(item)
        require(
            all(
                item[key] == receipt["scope"][key]
                for key in ("start", "end", "qs_source", "collection_ips")
            ),
            "B01 originals do not match the paired scope",
        )
    overlap = check_overlap(old, candidate)
    require(
        overlap["fresh_simultaneous_overlap"] is True,
        "stored originals do not establish overlap",
    )
    require(
        all(
            0
            <= utc(receipt["completed_utc"]).timestamp()
            - utc(row["latest_sample"]).timestamp()
            <= overlap["max_sample_age_seconds"]
            for row in overlap["series_by_source"]
        ),
        "originals were stale at B01 receipt time",
    )
    return old


def exact_samples(old, history):
    start, end, targets = joined_inputs((old, history))
    require(
        history["route"] == "history"
        and history["binding_before"]["remote_read"] is False,
        "expected the isolated history reader TSDB",
    )
    total = series = 0
    for metric in METRICS:
        expected = targets if metric == "up" else OWNERS
        source, restored = (
            named_rows(
                matrix(item["responses"][metric], metric, start, end), metric, expected
            )
            for item in (old, history)
        )
        require(source == restored, f"archive changed original {metric} samples")
        total += sum(len(samples) for _, samples in source.values())
        series += len(source)
    return total, series


def verify(b01_dir, second_copy, b05_path, import_path, history_path, import_approval):
    receipt, receipt_sha = read(b01_dir / "b01-receipt.json")
    source, source_sha = read(second_copy / "source.json")
    approval, approval_sha = read(second_copy / "approval.json")
    started, started_sha = read(second_copy / "started.json")
    manifest, manifest_sha = read(second_copy / "post-cold-manifest.json")
    b05, b05_sha = read(b05_path)
    ingest, ingest_sha = read(import_path)
    history, history_sha = read(history_path)

    operation = approval["operation_id"]
    require(
        operation
        == receipt["operation_id"]
        == started["operation_id"]
        == manifest["operation_id"]
        == b05["operation_id"]
        == ingest["h03_operation_id"],
        "H03 operation ID differs",
    )
    require(
        receipt["schema"] == "monitoring-h03-b01-capture/v1"
        and receipt["eligible_for_review"] is True
        and receipt["execution_authorized"] is False
        and receipt["capture_exit"] == {"macmini": 0, "candidate": 0},
        "B01 paired receipt is incomplete",
    )
    require(
        source["b01_overlap_receipt_sha256"] == receipt_sha
        and approval["source_sha256"] == source_sha
        and started["approval_sha256"] == approval_sha,
        "consumed approval does not bind the B01 receipt",
    )
    require(
        all(
            manifest["files"][name]["sha256"] == digest
            for name, digest in (
                ("source.json", source_sha),
                ("approval.json", approval_sha),
                ("started.json", started_sha),
            )
        ),
        "B04 manifest does not bind the consumed approval",
    )
    require(
        manifest["schema"] == "monitoring-h03-post-cold-handoff/v1"
        and manifest["rehearsal"] is False
        and b05["schema"] == "monitoring-h03-b05-restore/v1"
        and b05["rehearsal"] is False
        and b05["manifest_sha256"] == manifest_sha
        and b05["restored_from_verified_second_copy"] is True
        and b05["isolated_restore_verified"] is True
        and b05["prometheus"]["wal_replay_complete"] is True,
        "actual second-copy restore is required",
    )
    archive = b05["h06_prometheus_archive_sha256"]
    require(
        archive
        == manifest["files"]["prometheus.tar.gz"]["sha256"]
        == b05["prometheus"]["archive_sha256"]
        == ingest["archive_sha256"],
        "history import used a different archive",
    )
    verify_http_bodies(history)
    binding = bind_history(
        b05_path.read_bytes(),
        import_path.read_bytes(),
        import_approval.read_bytes(),
        history,
    )
    require(
        binding["b05_receipt_sha256"] == b05_sha
        and binding["import_receipt_sha256"] == ingest_sha,
        "history recovery receipts changed during verification",
    )
    require(
        approval["schema"] == "monitoring-h03-cold-window/v1"
        and utc(started["at"])
        < utc(approval["recovery_deadline_utc"])
        <= utc(approval["end_utc"])
        and utc(approval["start_utc"]).timestamp()
        <= receipt["scope"]["end"]
        <= utc(receipt["completed_utc"]).timestamp()
        <= utc(started["at"]).timestamp(),
        "B01 capture did not occur in the cold window before the stop",
    )

    old = paired_originals(b01_dir, receipt)
    match_source(source, old)
    samples, series = exact_samples(old, history)
    return dict(
        schema="monitoring-h06-b01-b05-binding/v1",
        operation_id=operation,
        archive_sha256=archive,
        manifest_sha256=manifest_sha,
        b01_receipt_sha256=receipt_sha,
        b05_receipt_sha256=b05_sha,
        history_import_sha256=ingest_sha,
        history_capture_sha256=history_sha,
        import_approval_sha256=binding["approval_sha256"],
        exact_restored_b01_samples=samples,
        series=series,
        read_only=True,
        execution_authorized=False,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in (
        "b01",
        "second-copy",
        "b05",
        "import-proof",
        "history",
        "import-approval",
    ):
        parser.add_argument("--" + field, type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            verify(
                args.b01,
                args.second_copy,
                args.b05,
                args.import_proof,
                args.history,
                args.import_approval,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
