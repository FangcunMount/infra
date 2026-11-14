"""Stage paired, read-only B01 originals in a private operation directory."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from check_b01 import verify
from servera_history_seam import expected_targets, scrape_time, verify_http_bodies

ROOT = Path(__file__).resolve().parent
SIDES = ("macmini", "candidate")
TOOL_FILES = (
    "capture_servera_b01.py",
    "capture_servera_history.py",
    "check_b01.py",
    "servera_history_seam.py",
    "m5_window_central_observe.py",
)
CAPTURE_TIMEOUT = 65


def write_original(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return sha256(data).hexdigest()


def read_binding(path):
    binding = json.loads(path.read_bytes())
    if (
        set(binding) != {"container", "image", "started_at"}
        or not re.fullmatch(r"[a-f0-9]{64}", binding["container"])
        or not re.fullmatch(r"sha256:[a-f0-9]{64}", binding["image"])
    ):
        raise ValueError(
            "binding requires the exact container ID, image digest and StartedAt"
        )
    scrape_time(binding["started_at"])
    return binding


def capture(side, binding, scope):
    start, end, source, ips = scope
    args = [
        sys.executable,
        "-B",
        str(ROOT / "capture_servera_history.py"),
        side,
        "--start",
        str(start),
        "--end",
        str(end),
        "--qs-source",
        source,
        "--collection-ip",
        *ips,
        "--binding",
        str(binding),
    ]
    try:
        result = subprocess.run(
            args, capture_output=True, timeout=CAPTURE_TIMEOUT, check=False
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as error:
        return (
            124,
            error.stdout or b"",
            (error.stderr or b"") + b"\nB01 capture timed out\n",
        )


def run(base, operation_id, source, ips, supplied, *, probe=capture, now=time.time):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{5,63}", operation_id):
        raise ValueError(
            "operation ID must be 6–64 lowercase letters, digits or hyphens"
        )
    expected_targets(ips, source)
    if (
        base.is_symlink()
        or base.stat().st_uid != os.getuid()
        or base.stat().st_mode & 0o077
    ):
        raise ValueError(
            "the evidence parent must be an existing private directory owned by the operator"
        )
    if not base.is_dir():
        raise ValueError("the evidence parent must be a directory")
    bindings = {
        side: read_binding(path) for side, path in zip(SIDES, supplied, strict=True)
    }
    if bindings["macmini"]["container"] == bindings["candidate"]["container"]:
        raise ValueError("both sides identify the same collector")
    directory = base / operation_id
    directory.mkdir(mode=0o700)
    end = int(now())
    start = end - 300
    scope = (start, end, source, ips)
    originals = {}
    paths = {}
    for side, binding in bindings.items():
        path = directory / f"{side}-binding.json"
        originals[path.name] = write_original(
            path, (json.dumps(binding) + "\n").encode()
        )
        paths[side] = path

    with ThreadPoolExecutor(max_workers=2) as pool:
        requests = {
            side: pool.submit(probe, side, path, scope) for side, path in paths.items()
        }
        captures = {side: future.result() for side, future in requests.items()}
    for side, (_, output, errors) in captures.items():
        for filename, data in ((f"{side}.json", output), (f"{side}.stderr", errors)):
            originals[filename] = write_original(directory / filename, data)

    results = {}
    failure = None
    if any(code for code, _, _ in captures.values()):
        failure = "at least one collector capture failed"
    else:
        try:
            receipts = {
                side: json.loads(output) for side, (_, output, _) in captures.items()
            }
            for side, record in receipts.items():
                verify_http_bodies(record)
                if (
                    record["route"] != side
                    or (
                        record["start"],
                        record["end"],
                        record["qs_source"],
                        tuple(record["collection_ips"]),
                    )
                    != (start, end, source, tuple(ips))
                    or any(
                        record["binding_before"].get(k) != v
                        for k, v in bindings[side].items()
                    )
                ):
                    raise ValueError(
                        f"{side} capture changed the operation scope or collector binding"
                    )
            results = verify(*(receipts[side] for side in SIDES))
        except (ValueError, KeyError, TypeError, OverflowError) as error:
            failure = str(error)
    completed = now()
    if failure is None and not results.get("fresh_simultaneous_overlap"):
        failure = "the paired samples do not establish a fresh common healthy interval"
    # Use the existing B01 age limit again at handoff, counting the capture time itself.
    ready = bool(results.get("fresh_simultaneous_overlap"))
    if ready:
        limit = results["max_sample_age_seconds"]
        ready = all(
            0
            <= completed - datetime.fromisoformat(row["latest_sample"]).timestamp()
            <= limit
            for row in results["series_by_source"]
        )
        if not ready:
            failure = "at least one sample aged beyond the B01 limit while collecting the receipt"
    document = dict(
        schema="monitoring-h03-b01-capture/v1",
        operation_id=operation_id,
        scope=dict(start=start, end=end, qs_source=source, collection_ips=ips),
        completed_utc=datetime.fromtimestamp(completed, timezone.utc).isoformat(),
        capture_exit={side: result[0] for side, result in captures.items()},
        eligible_for_review=ready,
        failure=failure,
        assessment=results,
        originals_sha256=originals,
        tools_sha256={
            name: sha256((ROOT / name).read_bytes()).hexdigest() for name in TOOL_FILES
        },
        read_only=True,
        execution_authorized=False,
    )
    write_original(
        directory / "b01-receipt.json", (json.dumps(document, indent=2) + "\n").encode()
    )
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    os.fsync(fd)
    os.close(fd)
    fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    os.fsync(fd)
    os.close(fd)
    return directory, document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-parent", type=Path, required=True)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--qs-source", required=True)
    parser.add_argument("--collection-ip", nargs=2, required=True)
    parser.add_argument("--macmini-binding", type=Path, required=True)
    parser.add_argument("--candidate-binding", type=Path, required=True)
    args = parser.parse_args()
    directory, result = run(
        args.evidence_parent,
        args.operation_id,
        args.qs_source,
        args.collection_ip,
        (args.macmini_binding, args.candidate_binding),
    )
    print(
        json.dumps(
            dict(
                receipt=str(directory / "b01-receipt.json"),
                eligible_for_review=result["eligible_for_review"],
                execution_authorized=False,
            )
        )
    )
    return 0 if result["eligible_for_review"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
