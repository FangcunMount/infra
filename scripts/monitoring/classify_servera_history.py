"""Classify historical sampling gaps against the preserved pre-cutover receipt."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from servera_history_seam import (
    MAX_AGE,
    METRICS,
    OWNERS,
    bind_history,
    compare,
    endpoint_time,
    joined_inputs,
    matrix,
    named_rows,
    utc_stamp,
    verify_http_bodies,
)


def gaps(samples, start_ms, end_ms):
    # Include unsettled edges. The caller must provide a fixed historical interval.
    ordered = sorted({start_ms, end_ms, *samples})
    return [
        (left, right)
        for left, right in zip(ordered, ordered[1:])
        if right - left > MAX_AGE * 1000
    ]


def classify(source, history, candidate, merged, boundary_ms):
    start, end, targets = joined_inputs((source, history, candidate, merged))
    if source["route"] != "macmini" or source["binding_before"]["remote_read"]:
        raise ValueError("the old collector local TSDB receipt is required")
    verified = compare(history, candidate, merged, boundary_ms)
    rows = []
    for metric, healthy in METRICS.items():
        expected = targets if metric == "up" else OWNERS
        old, restored, local, combined = [
            named_rows(
                matrix(item["responses"][metric], metric, start, end), metric, expected
            )
            for item in (source, history, candidate, merged)
        ]
        for identity in sorted(expected):
            labels, original = old[identity]
            restored_labels, archived = restored[identity]
            _, candidate_points = local[identity]
            _, merged_points = combined[identity]
            if labels != restored_labels:
                raise ValueError(
                    f"{metric}: old collector labels differ for {identity}"
                )
            # The fixed archive still has to preserve every old sample on the
            # reviewed interval, including timestamps where local wins the merge.
            if original != archived:
                raise ValueError(
                    f"{metric}: restored archive differs from source for {identity}"
                )
            first_local = min(candidate_points)
            prior_gaps = gaps(original, start * 1000, end * 1000)
            inherited = []
            changed = []
            for left, right in gaps(merged_points, start * 1000, end * 1000):
                pair = dict(
                    after=utc_stamp(left),
                    before=utc_stamp(right),
                    seconds=(right - left) / 1000,
                )
                if right <= first_local and any(
                    old_left <= left and right <= old_right
                    for old_left, old_right in prior_gaps
                ):
                    inherited.append(pair)
                else:
                    changed.append(pair)
            local_gaps = [
                dict(
                    after=utc_stamp(left),
                    before=utc_stamp(right),
                    seconds=(right - left) / 1000,
                )
                for left, right in gaps(candidate_points, boundary_ms, end * 1000)
            ]
            original_bad = [
                dict(
                    at=utc_stamp(at),
                    value=value,
                    visible_in_merged=merged_points.get(at) == value,
                )
                for at, value in original.items()
                if float(value) != healthy
            ]
            candidate_bad = [
                dict(at=utc_stamp(at), value=value)
                for at, value in candidate_points.items()
                if float(value) != healthy
            ]
            rows.append(
                dict(
                    metric=metric,
                    labels=dict(labels),
                    inherited_source_gaps=inherited,
                    unresolved_gaps=changed,
                    candidate_local_gaps=local_gaps,
                    preserved_source_nonhealthy=original_bad,
                    candidate_nonhealthy=candidate_bad,
                )
            )
    return dict(
        schema="monitoring-h06-gap-classification/v1",
        boundary=verified["boundary"],
        series=rows,
        inherited_source_gap_count=sum(
            len(row["inherited_source_gaps"]) for row in rows
        ),
        unresolved_gap_count=sum(len(row["unresolved_gaps"]) for row in rows),
        candidate_local_gap_count=sum(len(row["candidate_local_gaps"]) for row in rows),
        current_nonhealthy_count=sum(len(row["candidate_nonhealthy"]) for row in rows),
        pause_for_review=any(
            row["unresolved_gaps"]
            or row["candidate_local_gaps"]
            or row["candidate_nonhealthy"]
            for row in rows
        ),
        isolated_or_production_authorization=False,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "receipts", nargs=4, type=Path, metavar="SOURCE_HISTORY_LOCAL_MERGED"
    )
    parser.add_argument("--local-boundary", required=True)
    parser.add_argument("--b05", type=Path, required=True)
    parser.add_argument("--history-volume-proof", type=Path, required=True)
    parser.add_argument("--import-approval", type=Path, required=True)
    args = parser.parse_args()
    raw = [path.read_bytes() for path in args.receipts]
    source, history, local, merged = map(json.loads, raw)
    for receipt in (source, history, local, merged):
        verify_http_bodies(receipt)
    b05, volume, approval = (
        path.read_bytes()
        for path in (args.b05, args.history_volume_proof, args.import_approval)
    )
    binding = bind_history(b05, volume, approval, history)
    result = classify(
        source, history, local, merged, endpoint_time(args.local_boundary)
    )
    result["input_sha256"] = [
        sha256(value).hexdigest() for value in (*raw, b05, volume, approval)
    ]
    result["history_binding"] = binding
    print(json.dumps(result, indent=2))
    return int(result["pause_for_review"])


if __name__ == "__main__":
    raise SystemExit(main())
