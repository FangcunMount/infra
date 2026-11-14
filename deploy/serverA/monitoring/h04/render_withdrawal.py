"""Render a persistent ServerD withdrawal timer for review without installing it."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from render_deadline import render

ROOT = "/var/lib/qlume-monitoring-pilot-authorizations"


def units(operation, cutoff, zone, digest):
    if re.fullmatch(r"h04-[a-z0-9][a-z0-9-]{4,38}", operation) is None:
        raise ValueError("expected the operation-specific H04 ID")
    if re.fullmatch(r"[a-f0-9]{64}", digest) is None:
        raise ValueError("authorization plan SHA-256 required")
    deadline = render(cutoff, zone)
    name = f"qlume-monitoring-auth-withdraw-{operation}"
    state = f"{ROOT}/{operation}"
    service = f"""[Unit]
Description=Withdraw the H04 ServerD discovery authorization

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -B {state}/serverd-auth.py withdraw {digest}
UMask=0077
PrivateTmp=yes
NoNewPrivileges=yes
TimeoutStartSec=30s
"""
    timer = f"""[Unit]
Description=Schedule withdrawal of the H04 ServerD discovery authorization

[Timer]
OnCalendar={deadline["withdrawal_calendar_utc"]}
Persistent=true
AccuracySec=1s
Unit={name}.service

[Install]
WantedBy=timers.target
"""
    return name, service, timer, deadline


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("operation")
    p.add_argument("plan", type=Path)
    p.add_argument("zone")
    p.add_argument("output", type=Path)
    args = p.parse_args()
    raw = args.plan.read_bytes()
    plan = json.loads(raw)
    if plan["operation_id"] != args.operation:
        raise ValueError("operation identity differs")
    name, service, timer, deadline = units(
        args.operation, plan["cutoff_utc"], args.zone, sha256(raw).hexdigest()
    )
    args.output.mkdir(mode=0o700)
    for suffix, content in (("service", service), ("timer", timer)):
        with (args.output / f"{name}.{suffix}").open("x") as f:
            f.write(content)
    print(
        json.dumps(
            dict(
                operation_id=args.operation,
                unit=name,
                deadline=deadline,
                persistent_requested=True,
                units_installed=False,
                execution_authorized=False,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
