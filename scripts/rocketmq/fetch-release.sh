#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$root/components/rocketmq"
base=https://dist.apache.org/repos/dist/release/rocketmq/5.5.1
curl --fail --location --retry 3 "$base/rocketmq-all-5.5.1-bin-release.zip" -o rocketmq.zip
curl --fail --location --retry 3 "$base/rocketmq-all-5.5.1-bin-release.zip.asc" -o rocketmq.zip.asc
curl --fail --location --retry 3 https://downloads.apache.org/rocketmq/KEYS -o KEYS
python3 - <<'CHECK'
import hashlib
from pathlib import Path
expected="21555d9bd79792ac89f246566f19f58e300784c59b96289fd0c74db14787861081fb60ebb95cf541bf20a3e508bf3b70feb9596ea3ba6dc5dc88fa6081f00577"
if hashlib.sha512(Path("rocketmq.zip").read_bytes()).hexdigest()!=expected:
    raise SystemExit("RocketMQ5.5.1 archive checksum mismatch")
print("RocketMQ5.5.1 source archive verified; Docker build additionally requires pinned PGP signer")
CHECK
