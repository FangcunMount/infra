"""Read an already-started candidate by exact container, image and boot identity."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import shlex
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--container", required=True)
parser.add_argument("--image", required=True)
parser.add_argument("--started-at", required=True)
parser.add_argument("--collection-ip", required=True, nargs=2)
parser.add_argument("--qs-source", required=True, help="full source SHA from the running QS inventory")
parser.add_argument("--end", required=True, help="explicit UTC timestamp on a 15 second boundary")
args = parser.parse_args()
if not re.fullmatch(r"[0-9a-f]{64}", args.container) or not re.fullmatch(r"sha256:[0-9a-f]{64}", args.image):
    parser.error("exact container ID and image SHA-256 are required")
if not re.fullmatch(r"[0-9a-f]{40}", args.qs_source):
    parser.error("--qs-source must be a full lowercase SHA")
if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?Z", args.started_at):
    parser.error("StartedAt must be the exact Docker UTC timestamp")
end = datetime.fromisoformat(args.end)
if end.utcoffset() != timezone.utc.utcoffset(None) or end.microsecond or end.second % 15:
    parser.error("--end must be UTC aligned to 15 seconds")
if not 0 <= time.time() - end.timestamp() <= 30:
    parser.error("--end must be a current observation boundary")
if datetime.fromisoformat(args.started_at).timestamp() > end.timestamp() - 7200:
    parser.error("the named candidate process must cover the full two-hour interval")

verifier_path = Path(__file__).with_name("m5_window_central_observe.py")
verifier = verifier_path.read_text().partition('if __name__ == "__main__":')[0]
probe = '''
requests = []
get = api("http://127.0.0.1:9090")

def capture(path, **params):
    response = get(path, **params)
    requests.append(dict(path=path, params=params, data=response))
    return response

report = observe(capture, expected_targets(IPS, QS_SOURCE), END, range_seconds=7200)
print(json.dumps(dict(report=report, requests=requests), separators=(",", ":"), allow_nan=False))
'''
shell = '''
set -eu
id=$1
expected_image=$2
expected_start=$3
identity() {
    docker inspect --type container --format '{{.Id}} {{.Image}} {{.State.StartedAt}} {{index .Config.Labels "com.docker.compose.project"}} {{index .Config.Labels "com.docker.compose.service"}} {{.State.Running}} {{.State.Pid}}' "$id"
}
before=$(identity)
case "$before" in
    "$id $expected_image $expected_start qlume-servera-monitoring servera-collector true "*) ;;
    *) exit 1 ;;
esac
pid=${before##* }
test "$pid" -gt 0
nsenter -t "$pid" -n /usr/bin/python3 -B -
test "$(identity)" = "$before"
'''
source = f"IPS = {args.collection_ip!r}\nEND = {int(end.timestamp())}\nQS_SOURCE = {args.qs_source!r}\n" + verifier + probe
argv = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=7",
        "-o", "StrictHostKeyChecking=yes", "servera",
        shlex.join(["sudo", "-n", "/bin/sh", "-c", shell, "candidate-read",
                    args.container, args.image, args.started_at])]
result = subprocess.run(argv, input=source.encode(), capture_output=True, timeout=42, check=True)
if len(result.stdout) > 4_000_000:
    raise SystemExit("candidate response exceeded bound")
document = json.loads(result.stdout)
report = document["report"]
assert report["read_only"] and not report["execution_authorized"]
assert report["points"] == 481 and len(document["requests"]) == 9
assert len(report["expected_targets"]) == 10 and len(report["expected_owners"]) == 4
document["binding"] = dict(container_id=args.container, image_id=args.image, started_at=args.started_at,
                           qs_runtime_source=args.qs_source,
                           query_path="candidate-network-namespace-loopback", identity_rechecked=True,
                           verifier_sha256=sha256(verifier_path.read_bytes()).hexdigest(),
                           raw_response_sha256=sha256(result.stdout).hexdigest())
print(json.dumps(document, separators=(",", ":"), allow_nan=False))
raise SystemExit(0 if report["passed"] else 1)
