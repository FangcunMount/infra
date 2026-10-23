#!/usr/bin/env python3
"""Owned GitHub Actions NSQ fixture; never run against an existing endpoint."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import time
import urllib.request

import nsq_drain_evidence as gate
from audit_transaction_limit import write_private


def command(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)
    if result.returncode:
        raise RuntimeError("owned_fixture_command_failed")
    return result.stdout.strip()


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("isolated_github_actions_required")
    run, attempt = os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_RUN_ATTEMPT"]
    if not all(re.fullmatch(r"[0-9]{1,20}", x) for x in (run, attempt)):
        raise RuntimeError("owned_identity_required")
    name = "m3-nsq-drain-" + run + "-" + attempt
    project = name
    initial = set(command("docker", "ps", "-aq").split())
    image = "nsqio/nsq:v1.3.0"
    report = dict(schema="m3-nsq-drain-native/v1", passed=0, failed=0, skipped=0, cases={})
    container = None
    try:
        command("docker", "pull", image)
        container = command("docker", "run", "--detach", "--name", name, "--label", "com.docker.compose.project="+project,
                            "--memory=128m", "--cpus=1", "--tmpfs", "/data:rw,size=32m", "--publish", "127.0.0.1::4150", "--publish", "127.0.0.1::4151",
                            image, "/nsqd", "--data-path=/data", "--mem-queue-size=0", "--sync-every=1", "--msg-timeout=30s")
        if not re.fullmatch(r"[0-9a-f]{64}", container):
            raise RuntimeError("owned_container_required")
        def inspect():
            state = json.loads(command("docker", "inspect", container))[0]
            if state["Config"]["Labels"].get("com.docker.compose.project") != project:
                raise RuntimeError("owned_identity_changed")
            return state
        state = inspect()
        def port(number):
            binding = state["NetworkSettings"]["Ports"][str(number)+"/tcp"]
            if len(binding) != 1 or binding[0]["HostIp"] != "127.0.0.1":
                raise RuntimeError("loopback_binding_required")
            return int(binding[0]["HostPort"])
        http_port, tcp_port = port(4151), port(4150)
        def http(path, body=None):
            req = urllib.request.Request("http://127.0.0.1:"+str(http_port)+path, data=body,
                                         headers={"Accept":"application/vnd.nsq; version=1.0"})
            with urllib.request.urlopen(req, timeout=3) as response:
                return response.read(4*1024*1024)
        def stats():return json.loads(http(gate.STATS_PATH))
        def eventually(predicate):
            deadline = time.monotonic()+15
            while time.monotonic() < deadline:
                try:
                    if predicate():return
                except (OSError,ValueError):pass
                time.sleep(.1)
            raise RuntimeError("owned_fixture_condition_timeout")
        eventually(lambda:stats().get("health")=="OK")
        http("/channel/create?topic=owned-drain&channel=owned-worker", b"")
        frozen = dict(node_id="owned-nsqd",container_id=container,container_started_at=state["State"]["StartedAt"],version="1.3.0",topics={"owned-drain":["owned-worker"]})
        manifest = dict(schema="m3-nsq-drain-inventory/v1",nodes=[frozen])
        def capture():
            actual = inspect()
            return dict(node_id="owned-nsqd",container_id=container,container_started_at=actual["State"]["StartedAt"],request_path=gate.STATS_PATH,captured_at=stamp(),stats=stats())
        def envelope(a,b):return dict(schema="m3-nsq-drain-captures/v1",nodes=[dict(node_id="owned-nsqd",captures=[a,b])])
        def evaluate(a,b):return gate.evaluate(manifest,envelope(a,b),dt.datetime.now(dt.timezone.utc))
        def blocked(reason):
            try:evaluate(capture(),capture())
            except ValueError as error:
                if str(error)==reason:return
            raise RuntimeError("expected_original_responsibility_not_blocked")
        def passed(label):report["cases"][label]=True;report["passed"]+=1
        first=capture();time.sleep(5.1);result=evaluate(first,capture())
        if result["cutover_authorized"]:raise RuntimeError("cutover_not_authorized")
        passed("empty_original_node_requires_two_real_samples")
        http("/pub?topic=owned-drain",b"owned-drain-fixture")
        eventually(lambda:stats()["topics"][0]["channels"][0]["backend_depth"]==1)
        blocked("channel_responsibility");passed("disk_channel_depth_blocks_with_zero_topic_depth")
        def message(connection):
            def read(length):
                data=b""
                while len(data)<length:
                    part=connection.recv(length-len(data))
                    if not part:raise RuntimeError("owned_socket_closed")
                    data+=part
                return data
            for _ in range(10):
                length=struct.unpack(">I",read(4))[0]
                if not 4<=length<=65536:raise RuntimeError("owned_frame_limit")
                data=read(length);kind=struct.unpack(">I",data[:4])[0]
                if kind==2:
                    if len(data)<30:raise RuntimeError("owned_message_frame")
                    return data[14:30]
                if kind==0 and data[4:]==b"_heartbeat_":connection.sendall(b"NOP\n")
                elif kind==1:raise RuntimeError("owned_protocol_error")
            raise RuntimeError("owned_message_missing")
        with socket.create_connection(("127.0.0.1",tcp_port),timeout=12) as connection:
            connection.sendall(b"  V2SUB owned-drain owned-worker\nRDY 1\n")
            identity=message(connection)
            eventually(lambda:stats()["topics"][0]["channels"][0]["in_flight_count"]==1)
            blocked("channel_responsibility");passed("actual_inflight_blocks")
            connection.sendall(b"REQ "+identity+b" 1000\n")
            eventually(lambda:stats()["topics"][0]["channels"][0]["deferred_count"]==1)
            blocked("channel_responsibility");passed("actual_deferred_blocks")
            identity=message(connection);connection.sendall(b"FIN "+identity+b"\n")
            eventually(lambda:stats()["topics"][0]["channels"][0]["in_flight_count"]==0)
            first=capture();time.sleep(5.1);evaluate(first,capture());passed("original_fin_then_clean_observation")
            first=capture()
            http("/pub?topic=owned-drain",b"owned-drain-fixture")
            identity=message(connection);connection.sendall(b"FIN "+identity+b"\n")
            eventually(lambda:stats()["topics"][0]["channels"][0]["in_flight_count"]==0)
            time.sleep(5.1)
            try:evaluate(first,capture())
            except ValueError as error:
                if str(error)!="activity_between_captures":raise
            else:raise RuntimeError("unseen_new_publisher_activity_not_detected")
            passed("publication_consumed_between_samples_still_blocks")
        inspect();command("docker","restart",container)
        eventually(lambda:stats().get("health")=="OK")
        blocked("process_restarted");passed("same_container_restart_invalidates_frozen_process")
        image_state=json.loads(command("docker","image","inspect",state["Image"]))[0]
        report.update(image_id=state["Image"],repo_digests=image_state["RepoDigests"],actual_version=stats()["version"],source_sha=command("git","rev-parse","HEAD"),source_clean=not bool(command("git","status","--porcelain")),read_only_production_tool=True)
    except Exception:
        report["failed"]+=1
        report["failure"]="owned_native_drain_fixture_failed"
    finally:
        try:
            if container:
                inspect();command("docker","rm","-f",container)
            final=set(command("docker","ps","-aq").split())
            report["cleanup"]=dict(owned_container_removed=container is None or container not in final,existing_containers_unchanged=initial==final)
            if not all(report["cleanup"].values()):report["failed"]+=1
        except Exception:
            report["failed"]+=1;report["cleanup"]={"unavailable":True}
        report["harness_sha256"]={str(p.resolve().relative_to(Path.cwd())):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),Path("scripts/rocketmq/nsq_drain_evidence.py"))}
        write_private(Path("nsq-drain-native.json"),report)
    return 1 if report["failed"] or report["passed"]!=7 else 0


if __name__=="__main__":raise SystemExit(main())
