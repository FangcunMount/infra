#!/usr/bin/env python3
"""M2-0 required, disposable upstream transaction proof; never production.

Owns a random Compose project, loopback ports, principals and a fresh MySQL.
No external endpoint, existing database or production credentials are accepted.
Failure is failure, including missing dependencies; no skipped cases.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import time

from render import render


DISCARD_TOPIC = "TRANS_CHECK_MAX_TIME_TOPIC"  # TopicValidator in pinned Broker 5.5.1.

PARAMETERS = {"transactionTimeOut": 6000, "transactionCheckInterval": 5000,
              "transactionCheckMax": 24}


def broker_parameters(output):
    """Only allowlisted runtime values may leave the private admin capture."""
    import re
    result = {}
    for name in (*PARAMETERS, "fileReservedTime"):
        match = re.search(r"(?m)^\s*" + name + r"\s*=\s*(\d+)\s*$", output)
        if not match:
            raise RuntimeError("effective transaction parameter missing: " + name)
        result[name] = int(match[1])
    return result


def run(argv, *, timeout=120, env=None, cwd=None, required=True, stdin=None):
    result = subprocess.run(argv, input=stdin, capture_output=True, text=True,
                            env=env, cwd=cwd, timeout=timeout)
    if required and result.returncode:
        # Admin output and driver logs can contain private credentials/DSNs.
        raise RuntimeError(Path(str(argv[0])).name + " operation failed (private output withheld)")
    return result


def port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


class Probe:
    def __init__(self, argv, directory, env):
        self.events = []
        self.incoming = queue.Queue()
        self.log = open(directory / ("probe-" + secrets.token_hex(5) + ".log"), "x")
        os.chmod(self.log.name, 0o600)
        self.process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.log, text=True, env=env, bufsize=1)

        def collect():
            for line in self.process.stdout:
                if line.startswith("TXPROBE "):
                    try:
                        self.incoming.put(json.loads(line[len("TXPROBE "):]))
                    except ValueError:
                        self.incoming.put({"event": "failed"})
                else:
                    self.log.write(line)
            self.incoming.put({"event": "exited"})

        self.reader = threading.Thread(target=collect, daemon=True)
        self.reader.start()

    def drain(self):
        while True:
            try:
                self.events.append(self.incoming.get_nowait())
            except queue.Empty:
                return

    def wait(self, event, identity=None, decision=None, timeout=90):
        deadline = time.monotonic() + timeout
        while True:
            self.drain()
            for item in self.events:
                if (item.get("event") == event and (identity is None or item.get("id") == identity)
                        and (decision is None or item.get("decision") == decision)):
                    return item
            if any(e.get("event") in ("failed", "exited") for e in self.events):
                raise RuntimeError("probe ended before " + event)
            if time.monotonic() >= deadline:
                raise RuntimeError("probe timed out waiting for " + event + "/" + str(decision))
            time.sleep(0.05)

    def send(self, action):
        self.process.stdin.write(action + "\n")
        self.process.stdin.flush()

    def finish(self, expected=0):
        if self.process.wait(timeout=30) != expected:
            raise RuntimeError("unexpected probe process status")
        self.reader.join(timeout=2)
        self.drain()

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.reader.join(timeout=2)
        self.process.stdin.close()
        self.process.stdout.close()
        self.log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--mysql-image", default="mysql:8.0.36")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--go-probe", type=Path)
    parser.add_argument("--sdk-api-python", action="store_true", help="also require public Python/MySQL and cross-language recovery")
    parser.add_argument("--sdk-api-go", action="store_true", help="required public Go SDK acceptance; separate from raw M2-0")
    parser.add_argument("--python", default="uv")
    args = parser.parse_args()
    if args.sdk_api_python and not args.sdk_api_go:
        parser.error("Python SDK acceptance requires the full public Go SDK matrix")
    repo = Path(__file__).resolve().parents[2]
    sources = repo / "scripts/rocketmq/txprobe"
    sdk = args.sdk.resolve()
    sdk_sources = sdk / "transport/rocketmq/internal"
    if not (sdk_sources / "txprobe/main.go").is_file():
        raise RuntimeError("required SDK transaction probe and reviewed RPC fix missing")
    directory = Path(tempfile.mkdtemp(prefix="rocketmq-m2-"))
    directory.chmod(0o700)
    project = "rocketmq-m2-" + secrets.token_hex(6)
    config, data = directory / "config", directory / "data"
    config.mkdir(); data.mkdir(); (config / "tls").mkdir()
    grpc_port, metrics_port, mysql_port = port(), port(), port()
    while len({grpc_port, metrics_port, mysql_port}) != 3:
        grpc_port, metrics_port, mysql_port = port(), port(), port()
    accounts = {name: {"username": "m2-" + name, "password": secrets.token_hex(32)}
                for name in ("admin", "inner", "owner-a", "owner-b")}
    mysql_password = secrets.token_hex(32)
    render(accounts, config, "127.0.0.1", repo / "components/rocketmq")
    with (config / "broker.conf").open("a") as stream:
        stream.write("".join(f"{key}={value}\n" for key, value in PARAMETERS.items()))
    proxy = json.loads((config / "proxy.json").read_text())
    proxy["grpcServerPort"] = grpc_port
    (config / "proxy.json").write_text(json.dumps(proxy))
    run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
         "-subj", "/CN=rocketmq-m2-isolated", "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost",
         "-keyout", str(config / "tls/server.key"), "-out", str(config / "tls/server.crt")])
    ca = directory / "ca.crt"
    shutil.copyfile(config / "tls/server.crt", ca)
    image = run(["docker", "image", "inspect", args.image, "--format", "{{.Id}}"]).stdout.strip()
    run(["docker", "image", "inspect", args.mysql_image], required=False)
    if run(["docker", "image", "inspect", args.mysql_image], required=False).returncode:
        run(["docker", "pull", args.mysql_image], timeout=300)
    mysql_image = run(["docker", "image", "inspect", args.mysql_image, "--format", "{{.Id}}"]).stdout.strip()
    run(["docker", "run", "--rm", "--user", "0", "--entrypoint", "bash",
         "-v", str(config) + ":/config", "-v", str(data) + ":/data", image, "-c",
         "mkdir -p /data/store /data/auth /data/logs /data/nameserver-logs; "
         "chown -R 3000:3000 /data /config; chmod 750 /config /config/tls; "
         "chmod 640 /config/broker.conf /config/proxy.json /config/tools.yml /config/tls/server.key"])
    environment = dict(os.environ, ROCKETMQ_IMAGE=image, ROCKETMQ_BIND_IP="127.0.0.1",
                       ROCKETMQ_GRPC_PORT=str(grpc_port), ROCKETMQ_METRICS_PORT=str(metrics_port),
                       ROCKETMQ_DATA_ROOT=str(data), ROCKETMQ_CONFIG_ROOT=str(config))
    spec = json.loads(run(["docker", "compose", "-f", str(repo / "components/rocketmq/docker-compose.yml"),
                          "config", "--format", "json"], env=environment).stdout)
    # Compose's rendered network names must not point at the ordinary stack.
    spec.pop("name", None)
    for network in spec["networks"].values():
        network.pop("name", None)
    broker_spec = spec["services"]["broker"]
    broker_spec["ports"][0]["target"] = grpc_port
    broker_spec["healthcheck"]["test"][-1] = f"exec 3<>/dev/tcp/127.0.0.1/{grpc_port}"
    for service in spec["services"].values():
        service["restart"] = "no"
    spec["services"]["mysql"] = {
        "image": mysql_image, "environment": {"MYSQL_ROOT_PASSWORD": mysql_password,
        "MYSQL_DATABASE": "txprobe", "MYSQL_USER": "txprobe", "MYSQL_PASSWORD": mysql_password},
        "ports": [f"127.0.0.1:{mysql_port}:3306"], "networks": ["rocketmq"],
        "mem_limit": "512m", "cpus": 1, "tmpfs": ["/var/lib/mysql"],
        "healthcheck": {"test": ["CMD-SHELL", "MYSQL_PWD=$$MYSQL_ROOT_PASSWORD mysql -uroot -e 'SELECT 1'"],
                        "interval": "3s", "timeout": "3s", "retries": 40}}
    mongo_port = port()
    mongo_image = None
    if args.sdk_api_go:
        mongo_pin = "mongo@sha256:340c1c56fb10e95cf79ff547f8664b96bc6ead9909bc355238cbf865a9695a6f"
        run(["docker", "pull", mongo_pin], timeout=300)
        mongo_image = run(["docker", "image", "inspect", mongo_pin, "--format", "{{.Id}}"]).stdout.strip()
        spec["services"]["mongo"] = {
            "image": mongo_image, "command": ["mongod", "--replSet", "sdk-proof", "--bind_ip_all", "--wiredTigerCacheSizeGB", "0.25"],
            "ports": [f"127.0.0.1:{mongo_port}:27017"], "networks": ["rocketmq"],
            "mem_limit": "512m", "cpus": 1, "tmpfs": ["/data/db", "/data/configdb"],
            "healthcheck": {"test": ["CMD", "mongosh", "--quiet", "--eval", "db.adminCommand({ping:1})"],
                            "interval": "3s", "timeout": "5s", "retries": 40}}
    compose_file = directory / "compose.json"
    compose_file.write_text(json.dumps(spec)); compose_file.chmod(0o600)
    compose = ["docker", "compose", "-p", project, "-f", str(compose_file)]
    broker, mysql = project + "-broker-1", project + "-mysql-1"
    probes, cases, received, proof = [], {}, set(), {}
    failure = None

    def admin(operation, *params, success=False):
        result = run(["docker", "exec", broker, "java", "-Xms32m", "-Xmx128m",
                      "-XX:MaxDirectMemorySize=32m", "-cp", "/opt/rocketmq/conf:/opt/rocketmq/lib/*",
                      "org.apache.rocketmq.tools.command.MQAdminStartup", operation,
                      "-b", "127.0.0.1:10911", *params], timeout=45).stdout
        if success and " success." not in result:
            raise RuntimeError("admin operation missing positive completion: " + operation)
        return result

    def sql(query):
        return run(["docker", "exec", "-i", mysql, "sh", "-c",
                    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B txprobe'], stdin=query).stdout.strip()

    def mongo_command(command):
        return run(["docker", "exec", project + "-mongo-1", "mongosh", "--quiet", "--eval", command]).stdout.strip()

    def start(language, mode, identity="", owner="owner-a", topic=None, trust=None, storage="mysql", branches=1):
        if language in ("sdk-go", "sdk-python"):
            topic = "m2-sdk-" + storage
        account = accounts[owner]
        path = directory / ("client-" + secrets.token_hex(5) + ".json")
        path.write_text(json.dumps({"endpoint": f"127.0.0.1:{grpc_port}",
            "accesskey": account["username"], "secretkey": account["password"], "ca": str(trust or ca),
            "topic": topic or "m2-tx-owner-a", "group": "m2-tx-consumer", "owner": owner,
            "storage": storage, "branches": branches, "mongouri": f"mongodb://127.0.0.1:{mongo_port}/?replicaSet=sdk-proof&directConnection=true",
            "dsn": f"txprobe:{mysql_password}@tcp(127.0.0.1:{mysql_port})/txprobe?timeout=1s&readTimeout=1s&writeTimeout=1s",
            "mysql_url": f"mysql+asyncmy://txprobe:{mysql_password}@127.0.0.1:{mysql_port}/txprobe"}))
        path.chmod(0o600)
        argv = ([str(args.go_probe or directory / "go-probe")] if language == "go" else
                [args.python, "run", "--locked", "--project", str(sources), "python", str(sources / "probe.py")])
        if language == "sdk-go":
            argv = [str(directory / "sdk-go-probe")]
        if language == "sdk-python":
            argv = [args.python, "run", "--locked", "--project", str(sdk / "python"),
                    "--extra", "rocketmq", "--extra", "nsq", "python",
                    str(sdk / "python/tests/integration/transaction_probe.py")]
        argv += ["--config", str(path), "--mode", mode, "--id", identity]
        p = Probe(argv, directory, dict(os.environ, GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=str(trust or ca)))
        probes.append(p)
        return p

    def absent(identity, seconds=7):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            consumer.drain()
            if any(e.get("event") in ("failed", "exited") for e in consumer.events):
                raise RuntimeError("consumer failed during invisibility assertion")
            if any(e.get("event") == "received" and e.get("id") == identity for e in consumer.events):
                raise RuntimeError("uncommitted or rolled-back half became visible")
            time.sleep(.1)

    def passed(name):
        cases[name] = True
        print("transaction acceptance passed: " + name, flush=True)

    try:
        run(compose + ["up", "-d", "--wait", "--wait-timeout", "180"], timeout=240)
        effective = broker_parameters(admin("getBrokerConfig"))
        if any(effective[k] != v for k, v in PARAMETERS.items()):
            raise RuntimeError("isolated accelerated Broker parameters not effective")
        proof["effective_broker_parameters"] = effective
        proof["mysql_version"] = sql("SELECT VERSION();")
        if not proof["mysql_version"].startswith("8.0."):
            raise RuntimeError("required MySQL 8.0 fixture absent")
        sql("CREATE TABLE witness(id VARCHAR(96) PRIMARY KEY, owner VARCHAR(32) NOT NULL, "
            "wire_hash CHAR(64) NOT NULL, state VARCHAR(16) NOT NULL) ENGINE=InnoDB; "
            "CREATE TABLE effects(id VARCHAR(96) PRIMARY KEY) ENGINE=InnoDB;")
        for owner in ("owner-a", "owner-b"):
            topic = "m2-tx-" + owner
            admin("updateTopic", "-t", topic, "-r", "1", "-w", "1", "-a", "+message.type=TRANSACTION", success=True)
            account = accounts[owner]
            admin("createUser", "-u", account["username"], "-p", account["password"], "-t", "Normal", success=True)
            admin("createAcl", "-s", "User:" + account["username"], "-r", "Topic:" + topic,
                  "-a", "Pub,Sub,Get", "-d", "Allow", success=True)
        admin("updateSubGroup", "-g", "m2-tx-consumer", "-r", "8", success=True)
        admin("createAcl", "-s", "User:" + accounts["owner-a"]["username"], "-r", "Group:m2-tx-consumer",
              "-a", "Sub,Get", "-d", "Allow", success=True)
        if not args.go_probe:
            run(["go", "build", "-o", str(directory / "go-probe"), "./transport/rocketmq/internal/txprobe"], cwd=sdk)
        if args.sdk_api_go:
            from sdk_acceptance import assert_absent, run_go_sdk
            run(["go", "build", "-o", str(directory / "sdk-go-probe"), "./transport/rocketmq/internal/sdkprobe"], cwd=sdk)
            mongo_command('rs.initiate({_id:"sdk-proof",members:[{_id:0,host:"mongo:27017"}]})')
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if mongo_command("db.hello().isWritablePrimary") == "true":
                    break
                time.sleep(.5)
            else:
                raise RuntimeError("owned Mongo primary not available")
            proof["mongo_version"] = mongo_command("db.version()")
            if proof["mongo_version"] != "7.0.37":
                raise RuntimeError("required Mongo version differs")
            for storage in ("mysql", "mongo"):
                topic = "m2-sdk-" + storage
                admin("updateTopic", "-t", topic, "-r", "1", "-w", "1", "-a", "+message.type=TRANSACTION", success=True)
                admin("createAcl", "-s", "User:" + accounts["owner-a"]["username"], "-r", "Topic:" + topic,
                      "-a", "Pub,Sub,Get", "-d", "Allow", success=True)
            run_go_sdk(start, assert_absent, passed, sql, mongo_command)
            if args.sdk_api_python:
                from sdk_acceptance import run_python_sdk
                run([args.python, "sync", "--locked", "--project", str(sdk / "python"),
                     "--extra", "rocketmq", "--extra", "nsq"], timeout=180)
                run_python_sdk(start, passed, sql, lambda paused: run(
                    ["docker", "pause" if paused else "unpause", mysql]))
            if len(cases) != (18 if args.sdk_api_python else 10):
                raise RuntimeError("required public SDK case count differs")
            return
        run([args.python, "sync", "--locked", "--project", str(sources)], timeout=180)
        consumer = start("go", "consume")
        consumer.wait("ready")
        wrong_ca = directory / "wrong-ca.crt"
        run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
             "-subj", "/CN=untrusted", "-keyout", str(directory / "wrong-ca.key"), "-out", str(wrong_ca)])
        for language in ("go", "python"):
            untrusted = start(language, "recover", trust=wrong_ca)
            untrusted.finish(expected=1)
            if any(e.get("event") == "ready" for e in untrusted.events):
                raise RuntimeError("untrusted CA reached producer readiness")
            passed(language + "_untrusted_ca_rejected")

            identity = language + "-commit"
            sender = start(language, "send", identity)
            sender.wait("half")
            absent(identity)
            sender.send("commit")
            sender.wait("finalized")
            sender.finish()
            consumer.wait("received", identity)
            received.add(identity)
            passed(language + "_half_invisible_then_commit_visible")

            identity = language + "-rollback"
            sender = start(language, "send", identity)
            sender.wait("half")
            sender.send("rollback")
            sender.wait("finalized")
            sender.finish()
            absent(identity)
            if sql(f"SELECT COUNT(*) FROM effects WHERE id='{identity}';") != "0":
                raise RuntimeError("rolled-back business effect exists")
            passed(language + "_rollback_invisible")

            identity = language + "-restart"
            sender = start(language, "send", identity)
            sender.wait("half")
            sender.send("crash-committed")
            sender.wait("local", identity, "COMMITTED")
            sender.finish(expected=23)
            # There is no producer left: commit can only come from a fresh
            # instance, not a saved in-process Transaction or manual invocation.
            recovery = start(language, "recover")
            recovery.wait("ready")
            recovery.wait("checked", identity, "commit", timeout=100)
            consumer.wait("received", identity)
            received.add(identity)
            recovery.send("stop")
            recovery.finish()
            if sql(f"SELECT COUNT(*) FROM effects WHERE id='{identity}';") != "1":
                raise RuntimeError("business was not committed exactly once")
            passed(language + "_new_process_real_backcheck")

            identity = language + "-lost-commit-response"
            sender = start(language, "send", identity)
            sender.wait("half")
            sender.send("lost-commit-response")
            sender.wait("finalization_unknown")
            sender.finish(expected=24)
            consumer.wait("received", identity)
            received.add(identity)
            if sql(f"SELECT COUNT(*) FROM effects WHERE id='{identity}';") != "1":
                raise RuntimeError("lost response changed business effect count")
            passed(language + "_real_commit_response_discarded")

            identity = language + "-db-unavailable"
            sender = start(language, "send", identity)
            sender.wait("half")
            run(["docker", "pause", mysql])
            try:
                sender.wait("checked", identity, "unknown_database", timeout=100)
                absent(identity, seconds=2)
            finally:
                run(["docker", "unpause", mysql])
            sender.send("commit")
            sender.wait("finalized")
            sender.finish()
            consumer.wait("received", identity)
            received.add(identity)
            passed(language + "_db_failure_is_unknown")

            identity = language + "-wrong-witness-owner"
            sender = start(language, "send", identity)
            sender.wait("half")
            sql(f"UPDATE witness SET owner='owner-b',state='COMMITTED' WHERE id='{identity}';")
            sender.wait("checked", identity, "unknown_missing", timeout=100)
            absent(identity, seconds=2)
            sql(f"UPDATE witness SET owner='owner-a',state='PREPARED' WHERE id='{identity}';")
            sender.send("rollback")
            sender.wait("finalized")
            sender.finish()
            passed(language + "_other_owner_witness_cannot_commit")

            denied = start(language, "send", language + "-wrong-owner", owner="owner-b")
            denied.finish(expected=1)
            if any(e.get("event") == "half" for e in denied.events):
                raise RuntimeError("wrong owner obtained a half confirmation")
            passed(language + "_wrong_owner_acl_denied")

        for language, checker in (("go", "python"), ("python", "go")):
            identity = language + "-to-" + checker + "-recovery"
            sender = start(language, "send", identity)
            sender.wait("half")
            sender.send("crash-committed")
            sender.wait("local", identity, "COMMITTED")
            sender.finish(expected=23)
            recovery = start(checker, "recover")
            recovery.wait("ready")
            recovery.wait("checked", identity, "commit", timeout=100)
            consumer.wait("received", identity)
            received.add(identity)
            recovery.send("stop")
            recovery.finish()
            passed(language + "_to_" + checker + "_cross_process_recovery")

        # Accelerate ONLY the owned fixture. A real Unknown half must move to
        # the native discard topic; reaching an arbitrary sleep is not proof.
        sender = start("python", "send", "finite-check-limit")
        sender.wait("half")
        # Establish a real Unknown response before exhausting the scan budget.
        # Two scans immediately after startup can both precede checker routing.
        sender.wait("checked", "finite-check-limit", "unknown_prepared", timeout=100)
        # This command uses a different completion marker than provisioning.
        # Its authoritative success proof is the immediately following readback.
        admin("updateBrokerConfig", "-k", "transactionCheckMax", "-v", "2")
        discard_parameters = broker_parameters(admin("getBrokerConfig"))
        if discard_parameters["transactionCheckMax"] != 2:
            raise RuntimeError("finite-check test setting not effective")
        proof["discard_broker_parameters"] = discard_parameters
        deadline = time.monotonic() + 100
        while time.monotonic() < deadline:
            result = run(["docker", "exec", broker, "java", "-Xms32m", "-Xmx128m",
                          "-XX:MaxDirectMemorySize=32m", "-cp", "/opt/rocketmq/conf:/opt/rocketmq/lib/*",
                          "org.apache.rocketmq.tools.command.MQAdminStartup", "queryMsgByKey",
                          "-n", "nameserver:9876", "-t", DISCARD_TOPIC,
                          "-k", "finite-check-limit"], timeout=30, required=False)
            if "@" + DISCARD_TOPIC + "@K@finite-check-limit@" in result.stdout:
                proof["finite_check_discard_topic"] = DISCARD_TOPIC
                break
            time.sleep(2)
        else:
            raise RuntimeError("Unknown half not found in native finite-check discard topic")
        absent("finite-check-limit", seconds=2)
        if sql("SELECT state FROM witness WHERE id='finite-check-limit';") != "PREPARED":
            raise RuntimeError("discard test changed local business state")
        passed("finite_unknown_moves_to_native_discard_topic")

        # All earlier cases must remain absent even after subsequent backchecks.
        consumer.drain()
        observed = {e["id"] for e in consumer.events if e.get("event") == "received"}
        if observed != received:
            raise RuntimeError("unexpected/missing committed message")
        passed("exact_committed_identity_set")
    except Exception as exc:
        failure = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        for p in reversed(probes):
            if not p.log.closed:
                p.close()
        run(["docker", "unpause", mysql], required=False)
        run(compose + ["down", "--volumes", "--remove-orphans", "--timeout", "30"], timeout=120)
        report = {"version": 1, "batch": ("M2-Go-Python-SDK" if args.sdk_api_python else "M2-Go-SDK") if args.sdk_api_go else "M2-0", "project": project, "image": image,
                  "mysql_image": mysql_image, "mongo_image": mongo_image, "clients": {"go": "5.1.4", "python": "5.1.2"},
                  "cases": cases, "passed": len(cases), "failed": int(failure is not None),
                  "skipped": 0, "failure": failure, "proof": proof,
                  "probe_receipts": [{"pid": p.process.pid, "exit_code": p.process.returncode,
                                      "events": p.events} for p in probes],
                  "limits": ["No production acceptance or throughput claim",
                             "Response loss injected after a real RPC, not at network packet layer",
                             "Public Go SDK mode proves original transaction + idle-instance recovery; Python SDK/network-packet faults remain separate" if args.sdk_api_go else "Host transaction adapters/fencing and bounded SDK queues belong to later M2 batches"],
                  "source_sha256": {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in sorted(sources.iterdir()) if p.is_file()}}
        report["sdk_source_sha256"] = {str(p.relative_to(sdk)): hashlib.sha256(p.read_bytes()).hexdigest()
                                       for p in sorted(sdk_sources.rglob("*")) if p.is_file()}
        report["sdk_sha"] = run(["git", "rev-parse", "HEAD"], cwd=sdk).stdout.strip()
        report["go_runtime_patch"] = "v5.1.4 + per-client RPC/TLS options (SDK private snapshot)"
        report["harness_sha256"] = {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in (Path(__file__).resolve(), repo / "scripts/rocketmq/render.py",
                                              repo / "components/rocketmq/docker-compose.yml", repo / "scripts/rocketmq/sdk_acceptance.py")}
        report["go_probe_sha256"] = hashlib.sha256((args.go_probe or directory / "go-probe").read_bytes()).hexdigest() if (args.go_probe or directory / "go-probe").exists() else None
        args.report.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
