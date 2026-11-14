"""Read fixed raw sample selectors from the old or named candidate Prometheus."""
import argparse
import json
import time
from pathlib import Path
import re
import shlex
import subprocess

from servera_history_seam import matrix, requests, verify_http_bodies
from m5_window_central_observe import expected_targets

SSH = [
    "ssh",
    "-T",
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=7",
    "-o",
    "StrictHostKeyChecking=yes",
]
API = """
from base64 import b64encode
from hashlib import sha256
import json, re
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def capture(port, requests):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    def body(path, params=None):
        url=f"http://127.0.0.1:{port}/api/v1/{path}"
        if params:
            url += "?" + urlencode(params)
        with opener.open(url, timeout=7) as response:
            raw = response.read(1_000_001)
        assert len(raw)<=1_000_000
        return raw
    def get(path):
        return json.loads(body(path))
    def storage():
        flags=get("status/flags")
        assert flags["status"]=="success"
        with opener.open(f"http://127.0.0.1:{port}/metrics",timeout=7) as response:
            raw=response.read(4_000_001)
        assert len(raw)<=4_000_000
        metrics={}
        for line in raw.decode().splitlines():
            if line.startswith(("prometheus_tsdb_lowest_timestamp ","prometheus_tsdb_blocks_loaded ")):
                name,value=line.split()
                assert name not in metrics
                metrics[name]=int(float(value))
        assert len(metrics)==2 and metrics["prometheus_tsdb_lowest_timestamp"]>0
        assert metrics["prometheus_tsdb_blocks_loaded"]>=0
        return dict(local_min_ms=metrics["prometheus_tsdb_lowest_timestamp"],
                    persisted_blocks=metrics["prometheus_tsdb_blocks_loaded"],
                    min_block_duration=flags["data"]["storage.tsdb.min-block-duration"])
    def configuration():
        reply=get("status/config")
        assert reply["status"]=="success" and not reply.get("warnings")
        config=reply["data"]["yaml"]
        runtime=get("status/runtimeinfo")
        assert runtime["status"]=="success" and runtime["data"]["reloadConfigSuccess"] is True
        return dict(config_sha256=sha256(config.encode()).hexdigest(), loaded_at=runtime["data"]["lastConfigTime"],
                    remote_read=bool(re.search(r"(?m)^remote_read:", config)))
    before=configuration()
    storage_before=storage()
    bodies={metric:body("query",params) for metric,params in requests.items()}
    assert configuration()==before
    return dict(configuration=before,responses={name:json.loads(raw) for name,raw in bodies.items()},
                raw_http={name:b64encode(raw).decode("ascii") for name,raw in bodies.items()},
                storage_before=storage_before,storage_after=storage())
"""

HOST = r"""
import json
import socket
import subprocess

if ROUTE == "macmini":
    assert socket.gethostname().split(".")[0].lower()=="macmini-001"
    docker="/usr/local/bin/docker"
    project, service, volume = "macmini-monitoring", "prometheus", "infra_prometheus_data"
else:
    assert socket.gethostname().split(".")[0].lower()=="servera"
    docker="docker"
    project="qlume-servera-monitoring"
    service="history-reader" if ROUTE=="history" else "servera-collector"
    volume="qlume-servera-monitoring-history" if ROUTE=="history" else "qlume-servera-monitoring-data"

def identity():
    item,=json.loads(subprocess.check_output([docker,"inspect","--type","container",CONTAINER], timeout=10))
    state=item["State"]
    labels=item["Config"]["Labels"]
    assert state["Running"] and labels["com.docker.compose.project"]==project
    assert labels["com.docker.compose.service"]==service
    mount,=[row for row in item["Mounts"] if row["Destination"]=="/prometheus"]
    assert mount["Type"]=="volume" and mount["Name"]==volume
    volume_info,=json.loads(subprocess.check_output([docker,"volume","inspect",volume],timeout=10))
    assert volume_info["Mountpoint"]==mount["Source"]
    bound=dict(container=item["Id"],image=item["Image"],started_at=state["StartedAt"],pid=state["Pid"],
               volume=dict(name=volume,created_at=volume_info["CreatedAt"],mount_source=mount["Source"]))
    if EXPECTED:
        assert all(bound[key]==value for key,value in EXPECTED.items())
    return bound

before=identity()
if ROUTE=="macmini":
    exec(API)
    data=capture(19090,REQUESTS)
else:
    port=19092 if ROUTE=="history" else 9090
    source=API+"\nprint(json.dumps(capture("+repr(port)+","+repr(REQUESTS)+")))"
    command=["nsenter","--target",str(before["pid"]),"--net","--","/usr/bin/python3","-B","-"]
    data=json.loads(subprocess.check_output(command,input=source.encode(),timeout=36))
after=identity()
assert before==after
print(json.dumps(dict(binding_before=dict(before,**data["configuration"]),
                      binding_after=dict(after,**data["configuration"]),responses=data["responses"],
                      raw_http=data["raw_http"],
                      storage_before=data["storage_before"],storage_after=data["storage_after"])))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("route", choices=["macmini", "candidate", "history", "merged"])
    parser.add_argument(
        "--start", required=True, type=int, help="fixed UTC epoch seconds, exclusive"
    )
    parser.add_argument(
        "--end", required=True, type=int, help="fixed UTC epoch seconds, inclusive"
    )
    parser.add_argument("--qs-source", required=True)
    parser.add_argument("--collection-ip", required=True, nargs=2)
    parser.add_argument(
        "--binding",
        type=Path,
        required=True,
        help="JSON with exact container, image and started_at",
    )
    args = parser.parse_args()
    expected_targets(args.collection_ip, args.qs_source)
    selectors = requests(args.start, args.end)
    if args.end > int(time.time()):
        parser.error("raw samples must use a historical UTC interval")
    binding = json.loads(args.binding.read_bytes())
    if set(binding) != {"container", "image", "started_at"}:
        parser.error("binding must contain container, image and started_at")
    if not re.fullmatch(r"[a-f0-9]{64}", binding["container"]) or not re.fullmatch(
        r"sha256:[a-f0-9]{64}", binding["image"]
    ):
        parser.error("requires full Docker container and image IDs")
    if args.route == "macmini":
        command = [
            *SSH,
            "-J",
            "servera",
            "mac-mini-old",
            "/usr/bin/python3 -B -",
        ]
    else:
        command = [
            *SSH,
            "servera",
            shlex.join(["sudo", "-n", "/usr/bin/python3", "-B", "-"]),
        ]
    source = "\n".join(
        [
            f"ROUTE={args.route!r}",
            f'CONTAINER={binding["container"]!r}',
            f"EXPECTED={binding!r}",
            f"REQUESTS={selectors!r}",
            f"API={API!r}",
            HOST,
        ]
    )
    raw = subprocess.check_output(command, input=source.encode(), timeout=52)
    assert len(raw) < 10_000_000
    data = json.loads(raw)
    assert data["binding_before"]["remote_read"] == (args.route == "merged")
    result = dict(
        schema="servera-prometheus-raw-seam/v1",
        read_only=True,
        route=args.route,
        start=args.start,
        end=args.end,
        requests=selectors,
        qs_source=args.qs_source,
        collection_ips=args.collection_ip,
        **data,
    )
    print(json.dumps(result, indent=2))
    verify_http_bodies(result)
    for metric, response in result["responses"].items():
        matrix(response, metric, args.start, args.end)


if __name__ == "__main__":
    main()
