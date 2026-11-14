"""Check a simultaneous, fresh overlap before taking a cold backup (H03 B01)."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from servera_history_seam import (
    MAX_AGE,
    METRICS,
    OWNERS,
    fail_if,
    joined_inputs,
    matrix,
    named_rows,
    overlap,
    utc_stamp,
)

OVERLAP_MS = 15_000
MAX_AGE_MS = MAX_AGE * 1000


def tail(samples, healthy_value, endpoint):
    """Return the last healthy run and earlier issues using original sample times."""
    points = list(samples.items())
    unhealthy = [
        utc_stamp(stamp) for stamp, value in points if float(value) != healthy_value
    ]
    gaps = [
        {"after": utc_stamp(before), "before": utc_stamp(after)}
        for (before, _), (after, _) in zip(points, points[1:])
        if after - before > MAX_AGE_MS
    ]
    latest, value = points[-1]
    fresh = endpoint - latest <= MAX_AGE_MS
    start = latest
    if float(value) == healthy_value:
        for stamp, value in reversed(points[:-1]):
            if start - stamp > MAX_AGE_MS or float(value) != healthy_value:
                break
            start = stamp
    return dict(
        start=start,
        latest=latest,
        fresh=fresh,
        latest_healthy=float(points[-1][1]) == healthy_value,
        unhealthy=unhealthy,
        gaps=gaps,
    )


def verify(source, candidate):
    # Reuse the existing checks for scope, complete label identity and real per-series overlap.
    baseline = overlap(source, candidate)
    start, end, targets = joined_inputs((source, candidate))
    endpoint = end * 1000
    observations, details = [], []
    for metric, healthy in METRICS.items():
        expected = targets if metric == "up" else OWNERS
        endpoints = [
            (
                side,
                named_rows(
                    matrix(receipt["responses"][metric], metric, start, end),
                    metric,
                    expected,
                ),
            )
            for side, receipt in (("macmini", source), ("candidate", candidate))
        ]
        for side, rows in endpoints:
            for identity, (_, samples) in sorted(rows.items()):
                status = tail(samples, healthy, endpoint)
                observations.append(status)
                details.append(
                    dict(
                        metric=metric,
                        role=side,
                        identity=identity,
                        continuous_healthy_from=utc_stamp(status["start"]),
                        latest_sample=utc_stamp(status["latest"]),
                        fresh=status["fresh"],
                        latest_healthy=status["latest_healthy"],
                        known_gaps=status["gaps"],
                        observed_unhealthy=status["unhealthy"],
                    )
                )
    overlap_start = max(status["start"] for status in observations)
    overlap_end = min(status["latest"] for status in observations)
    qualified = all(
        status["fresh"] and status["latest_healthy"] for status in observations
    )
    qualified = qualified and overlap_end - overlap_start >= OVERLAP_MS
    return dict(
        schema="monitoring-h03-b01-fresh-overlap/v1",
        compared_series=len(baseline["series"]),
        sample_interval_end=utc_stamp(endpoint),
        max_sample_age_seconds=MAX_AGE,
        also_observed_gaps_or_bad_samples=any(
            detail["known_gaps"] or detail["observed_unhealthy"] for detail in details
        ),
        common_healthy_start=utc_stamp(overlap_start),
        common_healthy_end=utc_stamp(overlap_end),
        common_healthy_milliseconds=max(0, overlap_end - overlap_start),
        fresh_simultaneous_overlap=qualified,
        series_by_source=details,
        read_only=True,
        execution_authorized=False,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("macmini", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    raw = [path.read_bytes() for path in (args.macmini, args.candidate)]
    try:
        result = verify(*(json.loads(data) for data in raw))
    except ValueError as error:
        result = dict(
            schema="monitoring-h03-b01-fresh-overlap/v1",
            fresh_simultaneous_overlap=False,
            rejected=str(error),
            read_only=True,
            execution_authorized=False,
        )
    result["capture_sha256"] = [sha256(data).hexdigest() for data in raw]
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["fresh_simultaneous_overlap"] else 1)


if __name__ == "__main__":
    main()
