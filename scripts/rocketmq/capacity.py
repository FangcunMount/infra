#!/usr/bin/env python3
"""Finite host-capacity acceptance sampler; never a persistent collection agent."""
import argparse
import json
from pathlib import Path
import subprocess
import time


def snapshot():
    names = ["rocketmq-broker-1", "rocketmq-nameserver-1",
             "qs-worker-runtime-1", "qs-worker-runtime-2", "qs-worker-runtime-3", "nsqd"]
    rows = json.loads(subprocess.check_output(["docker", "inspect", *names], text=True))
    return {r["Name"].lstrip("/"): {"id": r["Id"], "restarts": r["RestartCount"],
            "oom": r["State"]["OOMKilled"], "running": r["State"]["Running"]} for r in rows}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seconds", type=int, default=660)
    p.add_argument("--report", type=Path, required=True)
    a = p.parse_args()
    if not 1 <= a.seconds <= 3600:
        p.error("finite1..3600 second observation required")
    before = snapshot()
    began = time.time()
    deadline = time.monotonic() + a.seconds
    samples = []
    while True:
        memory = int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines() if line.startswith("MemAvailable:")))
        samples.append({"unix": round(time.time(), 3), "available_kib": memory})
        # Write progress atomically so an operator can stop just the test load
        # if headroom falls below its gate; no business process is controlled.
        report = {"started_unix": began, "samples": samples,
                  "min_available_mib": min(s["available_kib"] for s in samples) / 1024,
                  "complete": time.monotonic() >= deadline}
        if report["complete"]:
            after = snapshot()
            report.update(before=before, after=after,
                          passed=before == after and all(x["running"] and not x["oom"] for x in after.values()) and report["min_available_mib"] >= 512)
        temporary = a.report.with_suffix(".next")
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(a.report)
        if report["complete"]:
            break
        time.sleep(min(5, max(0, deadline-time.monotonic())))


if __name__ == "__main__":
    main()
