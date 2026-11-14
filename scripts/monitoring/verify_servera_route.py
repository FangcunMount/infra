"""Compare the active ServerA proxy with the candidate or original collector."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time

from servera_history_seam import (
    OWNERS,
    expected_targets,
    fail_if,
    matrix,
    named_rows,
    requests,
    scrape_time,
    verify_http_bodies,
)

REMOTE = """
from hashlib import sha256
import json
import socket
import subprocess

assert socket.gethostname().split(".")[0].lower()=="servera"

def read_proxy():
    item,=json.loads(subprocess.check_output(
        ["/usr/bin/docker","--host","unix:///var/run/docker.sock","inspect","--type","container","prometheus-route"],timeout=10))
    assert item["Id"]==ID and item["Image"]==IMAGE and item["State"]["Running"]
    assert item["State"]["StartedAt"]==STARTED and item["State"]["Pid"]>0
    raw=subprocess.check_output(["/usr/bin/docker","--host","unix:///var/run/docker.sock","exec",ID,"cat","/etc/nginx/nginx.conf"],timeout=8)
    assert len(raw)<=100000 and sha256(raw).hexdigest()==CONFIG
    query=item["NetworkSettings"]["Networks"].get("qlume-servera-monitoring-query")
    result=dict(container=ID,image=IMAGE,started_at=STARTED,pid=item["State"]["Pid"],config_sha256=CONFIG,
                private_query_ip=query["IPAddress"] if query else None)
    return result

before=read_proxy()
call=["nsenter","--net","--target",str(before["pid"]),"--","/usr/bin/python3","-B","-"]
body=subprocess.check_output(call,input=CODE.encode(),timeout=40)
assert len(body)<10000000
after=read_proxy()
print(json.dumps(dict(proxy_before=before,proxy_after=after,**json.loads(body))))
"""
INNER = """
from base64 import b64encode
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener
import json

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

client=build_opener(ProxyHandler({}),NoRedirect())
responses={}
bodies={}
status={}
errors={}
for metric,params in QUERIES.items():
    url="http://127.0.0.1:9090/api/v1/query?"+urlencode(params)
    try:
        try:
            response=client.open(url,timeout=8)
        except HTTPError as error:
            response=error
        with response:
            status[metric]=response.code
            raw=response.read(1000001)
    except (OSError, URLError) as error:
        errors[metric]=type(error).__name__
        continue
    if len(raw)>1000000:
        errors[metric]="response_too_large"
        continue
    bodies[metric]=b64encode(raw).decode("ascii")
    try:
        responses[metric]=json.loads(raw)
    except ValueError:
        errors[metric]="invalid_json"
print(json.dumps(dict(responses=responses,raw_http=bodies,http_status=status,errors=errors)))
"""


def verify(expected, actual):
    start, end = (expected[k] for k in ("start", "end"))
    fail_if(
        set(actual) != set(expected["responses"])
        or set(actual) != set(expected["requests"]),
        "proxy query coverage differs from reference",
    )
    counts = {}
    for metric, response in actual.items():
        wanted = matrix(expected["responses"][metric], metric, start, end)
        observed = matrix(response, metric, start, end)
        if observed != wanted:
            raise ValueError(
                f"{metric}: proxy raw series differ from the reference collector"
            )
        counts[metric] = dict(
            series=len(observed),
            samples=sum(len(points) for points in observed.values()),
        )
    return counts


def validate_reference(reference, phase):
    route = "merged" if phase == "h06" else "macmini"
    fail_if(
        reference["schema"] != "servera-prometheus-raw-seam/v1"
        or reference["route"] != route
        or reference["read_only"] is not True
        or reference["binding_before"] != reference["binding_after"]
        or reference["binding_before"]["remote_read"] is not (phase == "h06"),
        f"{phase}: wrong reference route or unstable identity",
    )
    start, end = reference["start"], reference["end"]
    fail_if(
        type(start) is not int
        or type(end) is not int
        or end > time.time()
        or reference["requests"] != requests(start, end),
        "fixed historical raw selectors required",
    )
    verify_http_bodies(reference)
    targets = expected_targets(reference["collection_ips"], reference["qs_source"])
    for metric, response in reference["responses"].items():
        named_rows(
            matrix(response, metric, start, end),
            metric,
            targets if metric == "up" else OWNERS,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("h06", "h07"))
    parser.add_argument(
        "reference",
        type=Path,
        help="merged candidate or pre-cutover Mac mini raw capture",
    )
    parser.add_argument(
        "--proxy",
        type=Path,
        required=True,
        help="reviewed proxy identity and config digest",
    )
    parser.add_argument(
        "--capture", type=Path, required=True, help="new path for raw proxy capture"
    )
    args = parser.parse_args()
    binding_raw = args.proxy.read_bytes()
    binding = json.loads(binding_raw)
    reference_raw = args.reference.read_bytes()
    reference = json.loads(reference_raw)
    validate_reference(reference, args.phase)
    fail_if(
        binding.keys() != {"container", "image", "started_at", "config_sha256"},
        "expected exact proxy binding fields",
    )
    for key, value in (
        ("container", r"[a-f0-9]{64}"),
        ("image", r"sha256:[a-f0-9]{64}"),
        ("config_sha256", r"[a-f0-9]{64}"),
    ):
        fail_if(not re.fullmatch(value, binding[key]), f"invalid proxy {key}")
    scrape_time(binding["started_at"])
    queries = reference["requests"]
    code = "\n".join(
        [
            f'ID={binding["container"]!r}',
            f'IMAGE={binding["image"]!r}',
            f'STARTED={binding["started_at"]!r}',
            f'CONFIG={binding["config_sha256"]!r}',
            "CODE=" + repr(f"QUERIES={queries!r}\n" + INNER),
            REMOTE,
        ]
    )
    ssh = [
        "ssh",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=7",
        "-o",
        "StrictHostKeyChecking=yes",
        "servera",
        shlex.join(["sudo", "-n", "/usr/bin/python3", "-B", "-"]),
    ]
    raw = subprocess.check_output(ssh, input=code.encode(), timeout=60)
    actual = json.loads(raw)
    fd = os.open(
        args.capture, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(fd, "wb") as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())
    folder = os.open(args.capture.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(folder)
    finally:
        os.close(folder)
    proxy = actual["proxy_before"]
    fail_if(
        proxy != actual["proxy_after"]
        or any(proxy[key] != binding[key] for key in binding),
        "proxy identity changed or does not match the supplied binding",
    )
    fail_if(
        args.phase == "h06" and proxy["private_query_ip"] != "172.31.251.2",
        "H06 proxy is outside the approved private query network",
    )
    fail_if(
        actual["errors"] or actual["http_status"] != dict.fromkeys(queries, 200),
        "proxy queries did not all return HTTP 200 with usable bodies",
    )
    verify_http_bodies(actual)
    print(
        json.dumps(
            dict(
                schema="monitoring-servera-proxy-readback/v1",
                phase=args.phase,
                counts=verify(reference, actual["responses"]),
                proxy=proxy,
                reference_route=reference["route"],
                reference_receipt_sha256=sha256(reference_raw).hexdigest(),
                proxy_binding_sha256=sha256(binding_raw).hexdigest(),
                proxy_capture_sha256=sha256(raw).hexdigest(),
                read_only=True,
                execution_authorized=False,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
