"""Check W00 target and owner identities in a bounded Prometheus read."""
import argparse
from datetime import datetime, timezone
import ipaddress
import json
import re
import time
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


LOOPBACK = "http://127.0.0.1:19090"
TAILNET = "http://100.126.200.55:19090"
STEP = 15
MAX_AGE = 35
RANGE_SECONDS = 30 * 60
DEFAULT_QS_SOURCE = "4620d11e2cffbc4b67b43965812cff3340f0be43"
OWNERS = {
    ("qs-apiserver", "qs-apiserver:8080", "qs.mysql"),
    ("qs-apiserver", "qs-apiserver:8080", "qs.mongo"),
    ("qs-ai", "qs-ai-api:8000", "ai.mysql"),
    ("iam", "iam-apiserver:9080", "iam.mysql"),
}
METRICS = {
    "up": 1,
    "reliable_messaging_transaction_observation_available": 1,
    "reliable_messaging_transaction_observation_fresh": 1,
    "reliable_messaging_transaction_admission_protected": 0,
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def expected_targets(collection_ips, qs_source=DEFAULT_QS_SOURCE):
    if re.fullmatch(r"[0-9a-f]{40}", qs_source) is None:
        raise ValueError("a full lowercase QS source SHA is required")
    qs_release = f"qs-m5-{qs_source[:12]}"
    ips = {ipaddress.IPv4Address(value) for value in collection_ips}
    if len(ips) != 2 or not all(ip in ipaddress.IPv4Network("172.20.0.0/24") for ip in ips):
        raise ValueError("two verified Collection addresses are required")
    return {
        ("iam", "iam-apiserver:9080"),
        ("qs-ai", "qs-ai-api:8000"),
        ("qs-apiserver", "qs-apiserver:8080"),
        ("rocketmq", "100.118.164.39:5557"),
        ("prometheus", "127.0.0.1:9090"),
        *(("qs-collection-server", f"{ip}:8080") for ip in ips),
        *(("qs-worker", f"{qs_release}-worker-{n}") for n in range(1, 4)),
    }


def utc(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def api(base):
    opener = build_opener(ProxyHandler({}), NoRedirect())

    def get(path, **params):
        with opener.open(base + path + "?" + urlencode(params), timeout=7) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Prometheus response exceeded its bound")
        result = json.loads(raw)
        if result["status"] != "success" or result.get("warnings"):
            raise ValueError("Prometheus query unavailable")
        return result["data"]

    return get


def rows_by_time(matrix, points, keys):
    if matrix["resultType"] != "matrix":
        raise ValueError("expected a Prometheus matrix")
    rows = {point: {} for point in points}
    for series in matrix["result"]:
        identity = tuple(series["metric"][key] for key in keys)
        for point, value in series["values"]:
            by_identity = rows[point]
            if identity in by_identity:
                raise ValueError(f"duplicate series for {identity} at {utc(point)}")
            by_identity[identity] = float(value)
    return rows


def check_matrix(values, source_times, points, keys, expected, value):
    samples = rows_by_time(values, points, keys)
    times = rows_by_time(source_times, points, keys)
    failures = []
    for point in points:
        measured, captured = samples[point], times[point]
        missing = sorted(expected - measured.keys())
        unexpected = sorted((measured.keys() | captured.keys()) - expected)
        wrong = sorted(key for key in expected & measured.keys() if measured[key] != value)
        stale = sorted(key for key in expected & measured.keys()
                       if key not in captured or not 0 <= point - captured[key] <= MAX_AGE)
        if missing or unexpected or wrong or stale:
            failures.append(dict(at=utc(point), missing=missing, unexpected=unexpected, wrong=wrong, stale=stale))
    return failures


def scrape_time(value):
    # Prometheus supplies UTC RFC3339 with up to nine fractional digits.
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?Z", value)
    if not match:
        raise ValueError("invalid Prometheus scrape time")
    whole, fraction = match.groups()
    micros = (fraction or "").ljust(6, "0")[:6]
    return datetime.fromisoformat(f"{whole}.{micros}+00:00").timestamp()


def active_targets(data, expected, now):
    rows = {}
    jobs = {job for job, _ in expected}
    for row in data["activeTargets"]:
        labels = row["labels"]
        if labels.get("job") not in jobs:
            continue
        identity = (labels["job"], labels["instance"])
        if identity in rows:
            raise ValueError(f"duplicate active target {identity}")
        stamp = scrape_time(row["lastScrape"])
        rows[identity] = row["health"] == "up" and 0 <= now - stamp <= MAX_AGE
    return dict(missing=sorted(expected - rows.keys()), unexpected=sorted(rows.keys() - expected),
                unhealthy_or_stale=sorted(key for key, healthy in rows.items() if not healthy))


def observe(get, targets, end, clock=time.time, *, range_seconds=RANGE_SECONDS):
    points = list(range(end - range_seconds, end + 1, STEP))
    params = dict(start=points[0], end=end, step=STEP)
    checks = {}
    for metric, value in METRICS.items():
        expected = targets if metric == "up" else OWNERS
        keys = ("job", "instance") if metric == "up" else ("job", "instance", "owner")
        jobs = "|".join(sorted({row[0] for row in expected}))
        selector = metric + '{job=~"' + jobs + '"}'
        checks[metric] = check_matrix(get("/api/v1/query_range", query=selector, **params),
                                      get("/api/v1/query_range", query=f"timestamp({selector})", **params),
                                      points, keys, expected, value)
    current = get("/api/v1/targets", state="active")
    active = active_targets(current, targets, clock())
    return dict(schema="ai246-central-prewindow/v1", start=utc(points[0]), end=utc(end),
                points=len(points), expected_targets=sorted(targets), expected_owners=sorted(OWNERS),
                max_age_seconds=MAX_AGE, checks=checks, active=active, read_only=True,
                passed=not any(checks.values()) and not any(active.values()), execution_authorized=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection-ip", nargs=2, required=True, help="addresses from named running Collection containers")
    parser.add_argument("--qs-source", default=DEFAULT_QS_SOURCE,
                        help="full source SHA from the independently verified QS container inventory")
    parser.add_argument("--window-minutes", type=int, choices=(30, 120), default=RANGE_SECONDS // 60,
                        help="use 120 for the F07 two-hour gate")
    parser.add_argument("--tailnet", action="store_true", help="use the existing private Prometheus query path")
    args = parser.parse_args()
    transport = "tailnet" if args.tailnet else "collector-loopback"
    try:
        report = observe(api(TAILNET if args.tailnet else LOOPBACK),
                         expected_targets(args.collection_ip, args.qs_source), int(time.time()) // STEP * STEP,
                         range_seconds=args.window_minutes * 60)
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
        report = dict(schema="ai246-central-prewindow/v1", error=type(error).__name__,
                      passed=False, read_only=True, execution_authorized=False)
    print(json.dumps({**report, "transport": transport, "qs_runtime_source": args.qs_source,
                      "range_seconds": args.window_minutes * 60}, allow_nan=False, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
