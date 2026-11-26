"""Render the isolated ServerA close timer without registering it."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import argparse
import json
import os
import re

WINDOWS = Path("/var/lib/qlume-monitoring-shadow-windows")
OPERATION = r"h04-[a-z0-9][a-z0-9-]{4,38}"


def utc_second(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise ValueError("whole UTC second required")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def units(operation, cutoff, digest):
    if not re.fullmatch(OPERATION, operation):
        raise ValueError("invalid H04 operation")
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("stop plan SHA-256 required")
    when = utc_second(cutoff)
    stamp = when.strftime("%Y-%m-%d %H:%M:%S UTC")
    unit = "qlume-monitoring-shadow-stop-" + operation
    state = WINDOWS / operation
    service = f"""[Unit]
Description=Stop the pinned H04 ServerA shadow collector and bridge
Wants=docker.service
After=docker.service

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -B {state}/stop-candidate.py {state} {digest}
UMask=0077
NoNewPrivileges=yes
TimeoutStartSec=180s
"""
    timer = f"""[Unit]
Description=Close the pinned H04 ServerA shadow collector window

[Timer]
OnCalendar={stamp}
Persistent=true
AccuracySec=1s
Unit={unit}.service

[Install]
WantedBy=timers.target
"""
    return unit, service, timer


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation")
    parser.add_argument("stop_plan", type=Path)
    parser.add_argument("output", type=Path)
    values = parser.parse_args()
    raw = values.stop_plan.read_bytes()
    plan = json.loads(raw)
    if plan["operation"] != values.operation:
        raise ValueError("plan operation differs from requested operation")
    cutoff = plan["cutoff_utc"]
    if (
        not utc_second(plan["window_start_utc"])
        < utc_second(plan["latest_start_utc"])
        < utc_second(cutoff)
    ):
        raise ValueError("H04 window timestamps are out of order")
    unit, service, timer = units(values.operation, cutoff, sha256(raw).hexdigest())
    values.output.mkdir(mode=0o700)
    for suffix, text in (("service", service), ("timer", timer)):
        with (values.output / f"{unit}.{suffix}").open("x") as handle:
            handle.write(text)
    print(json.dumps(dict(name=unit, cutoff_utc=cutoff, registered=False)))
