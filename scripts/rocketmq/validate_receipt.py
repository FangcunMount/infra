#!/usr/bin/env python3
"""Fail closed on untested image/deployment configuration."""
import json
import hashlib
import sys
from pathlib import Path

receipt = json.loads(Path(sys.argv[1]).read_text())
values = dict(line.split("=", 1) for line in Path(sys.argv[2]).read_text().splitlines()
              if line and not line.startswith("#") and "=" in line)
image = values["ROCKETMQ_IMAGE"]
if image != receipt.get("image") or ("@sha256:" not in image and not image.startswith("sha256:")):
    raise SystemExit("fixed image identity must match acceptance receipt")
if values.get("ROCKETMQ_BIND_IP") != "100.118.164.39":
    raise SystemExit("production endpoint must bind serverD tailnet address")
for key in ("signature_verified", "sync_flush_verified", "persistence_verified", "acl_verified", "sdk_interop_verified"):
    if receipt.get(key) is not True:
        raise SystemExit("missing acceptance evidence: " + key)
if receipt.get("failed") != 0 or receipt.get("skipped") != 0 or receipt.get("passed", 0) < 11:
    raise SystemExit("required real Broker acceptance is incomplete")
root = Path(__file__).resolve().parents[2]
for name in ("Dockerfile", "entrypoint.sh", "broker.conf.example", "proxy.json.example", "docker-compose.yml", "serverd-routes.json"):
    relative = "components/rocketmq/" + name
    if receipt.get("component_files_sha256", {}).get(relative) != hashlib.sha256((root / relative).read_bytes()).hexdigest():
        raise SystemExit("component changed since acceptance: " + name)
if Path("/proc/meminfo").exists():
    available = int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines() if line.startswith("MemAvailable:")))
    if available < 512 * 1024:
        raise SystemExit("less than512MiB host memory available")
