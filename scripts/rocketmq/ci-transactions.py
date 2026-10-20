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
import signal
import shutil
import socket
import subprocess
import tempfile
import threading
import time

from render import render
from failure_diagnostics import summarize, startup_internal_description
from published_runtime import interpreter_path


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


def mysql_fixture_supported(version, *, sdk_api_go=False, iam_host=False):
    return version.startswith('8.0.') or ((sdk_api_go or iam_host) and version.startswith('8.4.'))


def run(argv, *, timeout=120, env=None, cwd=None, required=True, stdin=None):
    try:
        result = subprocess.run(argv, input=stdin, capture_output=True, text=True,
                                env=env, cwd=cwd, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        raise RuntimeError("private acceptance operation timed out or unavailable") from None
    if required and result.returncode:
        # Admin output and driver logs can contain private credentials/DSNs.
        raise RuntimeError(Path(str(argv[0])).name + " operation failed (private output withheld)")
    return result


def fixture_images(broker_tag, mysql_tag, directory, project, report, command=run):
    """Resolve images before chown/Compose; retain failures without private output."""
    try:
        image = command(["docker", "image", "inspect", broker_tag, "--format", "{{.Id}}"]).stdout.strip()
        if command(["docker", "image", "inspect", mysql_tag], required=False).returncode:
            command(["docker", "pull", mysql_tag], timeout=300)
        mysql_image = command(["docker", "image", "inspect", mysql_tag, "--format", "{{.Id}}"]).stdout.strip()
        return image, mysql_image
    except Exception:
        # This exact directory was allocated by this process; no container or
        # permission helper has been started yet. Never remove Docker images.
        if not directory.name.startswith("rocketmq-m2-") or not project.startswith("rocketmq-m2-"):
            raise RuntimeError("fixture ownership missing during image preflight") from None
        shutil.rmtree(directory)
        report.write_text(json.dumps({
            "version": 1, "batch": "isolated-fixture-image-preflight", "project": project,
            "phase": "image_acquisition_before_compose", "passed": 0, "failed": 1, "skipped": 0,
            "failure": "Docker image acquisition failed before fixture startup; private output withheld",
            "cases": {}, "cleanup": {"compose_not_started": True,
                "project_containers_remaining": False, "private_fixture_directory_removed": not directory.exists()},
            "limits": ["No database, Broker, business, production or system acceptance"]
        }, indent=2) + "\n")
        report.chmod(0o600)
        raise


def port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


class Probe:
    def __init__(self, argv, directory, env, prefix="TXPROBE "):
        self.events = []
        self.incoming = queue.Queue()
        self.log = open(directory / ("probe-" + secrets.token_hex(5) + ".log"), "x")
        os.chmod(self.log.name, 0o600)
        self.client_logs = directory / (Path(self.log.name).stem + "-client")
        self.client_logs.mkdir(mode=0o700)
        env = dict(env, **{'rocketmq.client.logRoot': str(self.client_logs),
                          'rocketmq.client.logLevel': 'error'})
        self.process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.log, text=True, env=env, bufsize=1,
                                        start_new_session=True)

        def collect():
            for line in self.process.stdout:
                if line.startswith(prefix):
                    try:
                        self.incoming.put(json.loads(line[len(prefix):]))
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
        if self.reader.is_alive():
            raise RuntimeError("probe child still owns stdout after launcher exited")

    def signal_group(self, signum):
        # Each fixture owns its own session. In particular uv run is a launcher,
        # not the Python producer PID; signaling only Popen.pid can orphan it.
        try:
            os.killpg(self.process.pid, signum)
        except ProcessLookupError:
            pass

    def kill_group(self):
        if self.process.poll() is not None:
            raise RuntimeError("producer exited before the controlled SIGKILL")
        self.signal_group(signal.SIGKILL)

    def close(self):
        if self.process.poll() is None or self.reader.is_alive():
            self.signal_group(signal.SIGTERM)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.signal_group(signal.SIGKILL)
                self.process.wait(timeout=5)
        self.reader.join(timeout=2)
        if self.reader.is_alive():
            self.signal_group(signal.SIGKILL)
            self.reader.join(timeout=2)
        if self.reader.is_alive():
            return False
        self.process.stdin.close()
        self.process.stdout.close()
        self.log.close()
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--mysql-image", default="mysql:8.0.36")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--iam-host", type=Path, help="exact IAM checkout; require actual host SDK/Broker acceptance in the owned fixture")
    parser.add_argument("--qs-evaluation-host", type=Path, help="exact QS checkout; require real MySQL evaluation application/Broker profile")
    parser.add_argument("--qs-evaluation-private-log", type=Path, help="new0600 diagnostic in an owned0700 directory; never a CI artifact")
    parser.add_argument("--qs-task-host", type=Path, help="exact QS checkout; require original MySQL task transaction and NORMAL fanout")
    parser.add_argument("--qs-task-private-log", type=Path, help="new0600 diagnostic in an owned0700 directory; never a CI artifact")
    parser.add_argument("--qs-report-host", type=Path, help="exact QS checkout; require report terminal with original Mongo and Broker")
    parser.add_argument("--qs-report-private-log", type=Path, help="new0600 diagnostic in an owned0700 directory; never a CI artifact")
    parser.add_argument("--qs-answer-host", type=Path, help="exact QS checkout; require answer submission with real Mongo and Broker")
    parser.add_argument("--qs-answer-private-log", type=Path, help="new0600 local diagnostic in an owned0700 directory; never a CI artifact")
    parser.add_argument("--iam-fanout-qs", type=Path, help="fixed clean QS source; require two IAM instances and the real QS subscriber in separate groups")
    parser.add_argument("--iam-operation-results", action="store_true", help="also require schema44 business-result atomicity from the actual IAM owner")
    parser.add_argument("--iam-private-log", type=Path, help="explicit owned0700 directory / new0600 local IAM log; never upload as CI artifact")
    parser.add_argument("--go-probe", type=Path)
    parser.add_argument("--sdk-api-python", action="store_true", help="also require public Python/MySQL and cross-language recovery")
    parser.add_argument("--sdk-api-go", action="store_true", help="required public Go SDK acceptance; separate from raw M2-0")
    parser.add_argument("--python", default="uv")
    parser.add_argument("--sdk-faults", action="store_true", help="require actual packet commit faults and owned Broker restarts")
    parser.add_argument("--sdk-limits", action="store_true", help="require public SDK finite native check audit and admission alarm")
    parser.add_argument("--sdk-go-probe", type=Path, help="prebuilt public SDK executable from a verified published Go module")
    parser.add_argument("--installed-python", type=Path, help="isolated Python interpreter with a verified downloaded release wheel installed")
    parser.add_argument("--qs-retry-store-host", type=Path, help="exact QS checkout; original dual-store future authorization atomicity only")
    parser.add_argument("--qs-retry-store-private-log", type=Path, help="new0600 private diagnostic; never a CI artifact")
    parser.add_argument("--qs-retry-dispatch-host", type=Path, help="exact QS candidate; real original failure/report roots and due Broker dispatch")
    args = parser.parse_args()
    if args.qs_retry_dispatch_host and (args.iam_host or args.sdk_api_go or args.qs_answer_host or args.qs_evaluation_host or args.qs_report_host or args.qs_task_host or args.qs_retry_store_host):
        parser.error("QS retry dispatch is a separate required profile")
    if args.qs_retry_store_private_log and not args.qs_retry_store_host:
        parser.error("QS retry private output requires its storage profile")
    if args.qs_retry_store_host and (args.iam_host or args.sdk_api_go or args.qs_answer_host or args.qs_evaluation_host or args.qs_report_host or args.qs_task_host):
        parser.error("QS retry store is a separate required profile")
    if args.qs_task_private_log and not args.qs_task_host:
        parser.error("QS task private output requires its host profile")
    if args.qs_task_host and (args.iam_host or args.sdk_api_go or args.qs_answer_host or args.qs_evaluation_host or args.qs_report_host):
        parser.error("QS task host is a separate required profile")
    if args.qs_report_private_log and not args.qs_report_host:
        parser.error("QS report output requires its host profile")
    if args.qs_report_host and (args.iam_host or args.sdk_api_go or args.qs_answer_host or args.qs_evaluation_host):
        parser.error("QS report host is a separate required profile")
    if args.qs_evaluation_private_log and not args.qs_evaluation_host:
        parser.error("QS evaluation private output requires its host profile")
    if args.qs_evaluation_host and (args.iam_host or args.sdk_api_go or args.qs_answer_host):
        parser.error("QS evaluation host is a separate required profile")
    if args.qs_answer_private_log and not args.qs_answer_host:
        parser.error("QS private output requires an explicit QS answer host")
    if args.qs_answer_host and (args.iam_host or args.sdk_api_go):
        parser.error("QS answer host is a separate required profile")
    if (args.iam_operation_results or args.iam_private_log or args.iam_fanout_qs) and not args.iam_host:
        parser.error("IAM result/capture options require an explicit IAM host source")
    if bool(args.installed_python) != bool(args.sdk_go_probe) or (args.installed_python and not args.sdk_api_python):
        parser.error("published installation requires both runtimes and full cross-language acceptance")
    if args.sdk_limits and not args.sdk_faults:
        parser.error("limit proofs require the packet fault matrix first")
    if args.sdk_faults and not args.sdk_api_go:
        parser.error("packet faults require public SDK acceptance")
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
                for name in ("admin", "inner", "owner-a", "owner-b", "observer")}
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
    fault_key = directory / "fault-server.key"
    shutil.copyfile(config / "tls/server.key", fault_key); fault_key.chmod(0o600)
    image, mysql_image = fixture_images(args.image, args.mysql_image, directory, project, args.report)
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
    if args.iam_host or args.qs_evaluation_host or args.qs_task_host or args.qs_retry_store_host or args.qs_retry_dispatch_host:
        # Host profiles explicitly create/drop their OWN random schema.
        # This root login exists only in this private loopback Compose project.
        spec['services']['mysql']['environment']['MYSQL_ROOT_HOST'] = '%'
    mongo_port = port()
    mongo_image = None
    if args.sdk_api_go or args.qs_answer_host or args.qs_report_host or args.qs_retry_store_host or args.qs_retry_dispatch_host:
        mongo_pin = "mongo@sha256:340c1c56fb10e95cf79ff547f8664b96bc6ead9909bc355238cbf865a9695a6f"
        run(["docker", "pull", mongo_pin], timeout=300)
        mongo_image = run(["docker", "image", "inspect", mongo_pin, "--format", "{{.Id}}"]).stdout.strip()
        spec["services"]["mongo"] = {
            "image": mongo_image, "command": ["mongod", "--replSet", "sdk-proof", "--bind_ip_all", "--wiredTigerCacheSizeGB", "0.25"],
            "ports": [f"127.0.0.1:{mongo_port}:27017"], "networks": ["rocketmq"],
            "mem_limit": "512m", "cpus": 1, "tmpfs": ["/data/db", "/data/configdb"],
            "healthcheck": {"test": ["CMD", "mongosh", "--quiet", "--eval", "db.adminCommand({ping:1})"],
                            "interval": "3s", "timeout": "5s", "retries": 40}}
        if args.qs_answer_host or args.qs_report_host or args.qs_retry_dispatch_host:
            spec['services']['mongo']['command'] += ['--setParameter', 'enableTestCommands=1']
    compose_file = directory / "compose.json"
    compose_file.write_text(json.dumps(spec)); compose_file.chmod(0o600)
    compose = ["docker", "compose", "-p", project, "-f", str(compose_file)]
    broker, mysql = project + "-broker-1", project + "-mysql-1"
    probes, cases, received, proof = [], {}, set(), {}
    failure = None
    sdk_manifest = None

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

    def start(language, mode, identity="", owner="owner-a", topic=None, trust=None,
              storage="mysql", branches=1, revision="sdk-v2", subscription=None, principal=None,
              database_proxy=None, mq_proxy=None, lease_millis=15000):
        is_sdk = language in ("sdk-go", "sdk-python")
        logical_owner, inputs, owner_routes = owner, [], []
        group = "m2-tx-consumer"
        if is_sdk:
            from routes import consumer_group_v2
            if sdk_manifest is None:
                raise RuntimeError("required typed fixture manifest not provisioned")
            logical_owner = "iam.mysql" if storage == "mysql" else "qs.mongo"
            kind = "NORMAL" if mode == "normal" else "TRANSACTION"
            matches = [r for r in sdk_manifest["routes"] if r["owner"] == logical_owner
                       and r["route_revision"] == revision and r["message_type"] == kind]
            if len(matches) != 1:
                raise RuntimeError("fixture owner/type/revision route ambiguous or missing")
            topic = topic or matches[0]["physical_topic"]
            subscription = subscription or ("sdk-" + storage + "-observer")
            group = consumer_group_v2("sdk.logical", subscription)
            physical_inputs = ([r for r in sdk_manifest["routes"] if r.get("subscription") == subscription]
                               if mode == "shared-consume" else matches)
            inputs = [{k: v for k, v in r.items() if k != "id"} for r in physical_inputs]
            role = principal or ("observer" if mode in ("consume", "shared-consume") else
                                 ("owner-a" if storage == "mysql" else "owner-b"))
            account = accounts[role]
            owner_routes = [{"topic":r["topic"],"physical_topic":r["physical_topic"],
                             "route_revision":r["route_revision"]} for r in sdk_manifest["routes"]
                            if r["owner"] == logical_owner and r["message_type"] == "TRANSACTION"]
        else:
            account = accounts[owner]
        actual_mysql_port = int(database_proxy.rsplit(":",1)[1]) if database_proxy and storage == "mysql" else mysql_port
        actual_mongo_port = int(database_proxy.rsplit(":",1)[1]) if database_proxy and storage == "mongo" else mongo_port
        path = directory / ("client-" + secrets.token_hex(5) + ".json")
        path.write_text(json.dumps({"endpoint": mq_proxy or f"127.0.0.1:{grpc_port}",
            "accesskey": account["username"], "secretkey": account["password"], "ca": str(trust or ca),
            "topic": topic or "m2-tx-owner-a", "group": group, "owner": logical_owner,
            "subscription": subscription or "", "inputs":inputs, "owner_routes":owner_routes,
            "route_revision":revision, "storage": storage, "branches": branches, "lease_millis":lease_millis,
            "mongouri": f"mongodb://127.0.0.1:{actual_mongo_port}/?replicaSet=sdk-proof&directConnection=true",
            "dsn": f"txprobe:{mysql_password}@tcp(127.0.0.1:{actual_mysql_port})/txprobe?timeout=1s&readTimeout=5s&writeTimeout=5s",
            "mysql_url": f"mysql+asyncmy://txprobe:{mysql_password}@127.0.0.1:{actual_mysql_port}/txprobe"}))
        path.chmod(0o600)
        argv = ([str(args.go_probe or directory / "go-probe")] if language == "go" else
                [args.python, "run", "--locked", "--project", str(sources), "python", str(sources / "probe.py")])
        if language == "sdk-go":
            argv = [str(args.sdk_go_probe or directory / "sdk-go-probe")]
        if language == "sdk-python":
            argv = [args.python, "run", "--locked", "--project", str(sdk / "python"),
                    "--extra", "rocketmq", "--extra", "nsq", "python",
                    str(sdk / "python/tests/integration/transaction_probe.py")]
        if language == "sdk-python" and args.installed_python:
            argv = [interpreter_path(args.installed_python), "-I", str(sdk / "python/tests/integration/transaction_probe.py")]
        argv += ["--config", str(path), "--mode", mode, "--id", identity]
        p = Probe(argv, directory, dict(os.environ, GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=str(trust or ca)))
        probes.append(p)
        return p

    def proxy_start(kind):
        endpoint = grpc_port if kind == "rocketmq" else (mysql_port if kind == "mysql" else mongo_port)
        argv = [str(directory / "fault-proxy"), "--kind", kind,
                "--upstream", f"127.0.0.1:{endpoint}", "--cert", str(ca), "--key", str(fault_key)]
        proxy = Probe(argv, directory, dict(os.environ), prefix="FAULTPROXY ")
        probes.append(proxy)
        proxy.address = proxy.wait("ready")["address"]
        return proxy

    def restart_broker():
        run(compose + ["restart", "broker"], timeout=90)
        deadline = time.monotonic() + 100
        while time.monotonic() < deadline:
            health = run(["docker", "inspect", "--format", "{{.State.Health.Status}}", broker]).stdout.strip()
            if health == "healthy":
                return
            time.sleep(.5)
        raise RuntimeError("owned Broker did not become healthy after restart")

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
        if not mysql_fixture_supported(proof["mysql_version"], sdk_api_go=args.sdk_api_go, iam_host=bool(args.iam_host or args.qs_answer_host or args.qs_evaluation_host or args.qs_report_host or args.qs_task_host or args.qs_retry_store_host or args.qs_retry_dispatch_host)):
            raise RuntimeError("required MySQL 8.0 fixture absent")
        if args.qs_task_host:
            from qs_task_acceptance import run_qs_task_host
            proof['qs_task_host'] = {}
            run_qs_task_host(args.qs_task_host, directory, broker, project, grpc_port, mysql_port,
                             mysql_password, ca, run, proof['qs_task_host'], args.qs_task_private_log)
            for name in proof['qs_task_host']['native_receipt']['cases']:
                passed('qs_task_' + name)
            return
        if args.qs_evaluation_host:
            from qs_evaluation_acceptance import run_qs_evaluation_host
            proof['qs_evaluation_host'] = {}
            run_qs_evaluation_host(args.qs_evaluation_host, directory, broker, project, grpc_port, mysql_port,
                                   mysql_password, ca, run, proof['qs_evaluation_host'], args.qs_evaluation_private_log)
            for name in proof['qs_evaluation_host']['native_receipt']['cases']:
                passed('qs_evaluation_' + name)
            return
        if args.qs_answer_host or args.qs_report_host or args.qs_retry_store_host or args.qs_retry_dispatch_host:
            mongo_command('rs.initiate({_id:"sdk-proof",members:[{_id:0,host:"mongo:27017"}]})')
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if mongo_command("db.hello().isWritablePrimary") == "true":
                    break
                time.sleep(.5)
            else:
                raise RuntimeError("owned Mongo primary not available")
            proof['mongo_version'] = mongo_command('db.version()')
            if proof['mongo_version'] != '7.0.37':
                raise RuntimeError('required Mongo version differs')
            if args.qs_retry_dispatch_host:
                from qs_retry_dispatch_acceptance import run_qs_retry_dispatch_host
                proof['qs_retry_dispatch_host'] = {}
                run_qs_retry_dispatch_host(args.qs_retry_dispatch_host, directory, broker, project, grpc_port,
                                           mysql_port, mongo_port, mysql_password, ca, run, proof['qs_retry_dispatch_host'])
                for name in proof['qs_retry_dispatch_host']['native_receipt']['cases']:
                    passed('qs_retry_dispatch_' + name)
                return
            if args.qs_retry_store_host:
                from qs_retry_acceptance import run_qs_retry_store_host
                proof['qs_retry_store_host'] = {}
                run_qs_retry_store_host(args.qs_retry_store_host, directory, project, mysql_port, mongo_port,
                                        mysql_password, run, proof['qs_retry_store_host'], args.qs_retry_store_private_log)
                for backend, receipt in proof['qs_retry_store_host']['native_receipts'].items():
                    for name in receipt['cases']:
                        passed('qs_retry_store_' + backend + '_' + name)
                return
            if args.qs_report_host:
                from qs_report_acceptance import run_qs_report_host
                proof['qs_report_host'] = {}
                run_qs_report_host(args.qs_report_host, directory, broker, project, grpc_port, mongo_port,
                                   ca, run, proof['qs_report_host'], args.qs_report_private_log)
                for name in proof['qs_report_host']['native_receipt']['cases']:
                    passed('qs_report_' + name)
                return
            from qs_answer_acceptance import run_qs_answer_host
            proof['qs_answer_host'] = {}
            run_qs_answer_host(args.qs_answer_host, directory, broker, project, grpc_port, mongo_port,
                               ca, run, proof['qs_answer_host'], args.qs_answer_private_log)
            for name in proof['qs_answer_host']['native_receipt']['cases']:
                passed('qs_answer_' + name)
            return
        if not args.sdk_api_go:
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
            if not args.sdk_go_probe:
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
            from v2_acceptance import setup
            sdk_manifest, proof["routing_v2"] = setup(repo,sdk,broker,project,accounts,directory,admin,run,passed)
            # Explicit HOST fixture installation precedes authorization tests;
            # constructors and Start still never install schema. Run v2 owner
            # negatives before the longer positive SDK/fault suites.
            for storage in ("mysql", "mongo"):
                initializer = start("sdk-go", "init", storage=storage)
                initializer.wait("installed"); initializer.finish()
            if args.sdk_api_python:
                if not args.installed_python:
                    run([args.python, "sync", "--locked", "--project", str(sdk / "python"),
                         "--extra", "rocketmq", "--extra", "nsq"], timeout=180)
            from v2_acceptance import denied_owners, shared_budget
            denied_owners(start,sql,mongo_command,passed,python=args.sdk_api_python)
            wrong_ca = directory / "sdk-wrong-ca.crt"
            run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
                 "-subj", "/CN=untrusted-sdk", "-keyout", str(directory / "sdk-wrong-ca.key"), "-out", str(wrong_ca)])
            pause_mysql = lambda paused: run(["docker", "pause" if paused else "unpause", mysql])
            run_go_sdk(start, assert_absent, passed, sql, mongo_command, pause_mysql, wrong_ca)
            if args.sdk_api_python:
                from sdk_acceptance import run_python_sdk
                run_python_sdk(start, passed, sql, pause_mysql, wrong_ca)
            shared_budget(start,passed,language="sdk-go")
            if args.sdk_api_python:
                shared_budget(start,passed,language="sdk-python")
            if args.sdk_faults:
                from sdk_faults import run_faults
                run(["go", "build", "-o", str(directory / "fault-proxy"),
                     "./transport/rocketmq/internal/faultproxy"], cwd=sdk)
                proof["packet_faults"] = run_faults(start,proxy_start,passed,sql,mongo_command,
                                                  restart_broker,python=args.sdk_api_python)
            if args.sdk_limits:
                from sdk_limits import run_limits
                proof["finite_sdk_limit"] = run_limits(start,passed,sql,admin,broker_parameters,
                                                       broker,project,directory,python=args.sdk_api_python)
            required_cases = (31 if args.sdk_api_python else 19) + ((15 if args.sdk_api_python else 9) if args.sdk_faults else 0) + ((2 if args.sdk_api_python else 1) if args.sdk_limits else 0)
            if len(cases) != required_cases:
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

        if args.iam_host:
            from iam_acceptance import run_iam_host
            proof['iam_host'] = {}
            run_iam_host(args.iam_host, directory, broker, project, grpc_port, mysql_port,
                         mysql_password, ca, run, proof['iam_host'], args.iam_private_log, args.iam_operation_results, args.iam_fanout_qs)
            passed('iam_host_actual_sdk_original_root_and_application')
            if args.iam_fanout_qs:
                passed('iam_two_instances_and_qs_separate_business_subscription')

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
        failure_diagnostics = None
        if failure:
            # Only hashes and fixed labels leave the private fixture. Never
            # publish raw client/Broker logs, message bytes or credentials.
            try:
                client_diagnostics = []
                for probe in probes[-16:]:
                    for path in list(probe.client_logs.glob('*.log'))[:1]:
                        with path.open('rb') as stream:
                            stream.seek(max(0, path.stat().st_size - 1048576))
                            raw_log = stream.read(1048576)
                            item = summarize(raw_log)
                        probe.drain()
                        if (any(e.get('event') == 'closed' and e.get('decision') == 'failed_start_drained'
                                for e in probe.events)
                                and not any(e.get('event') in ('ready', 'half', 'result') for e in probe.events)):
                            # The public probe creates its message only AFTER
                            # Ready. This failed process has no business wire.
                            sensitive = [mysql_password, *[v for a in accounts.values() for v in a.values()]]
                            description = startup_internal_description(raw_log, sensitive)
                            if description is not None:
                                item['startup_internal_description'] = description
                        item['pid'] = probe.process.pid
                        client_diagnostics.append(item)
                broker_logs = run(['docker', 'exec', '--user', '0', broker, 'sh', '-c',
                    'tail -c 524288 /home/rocketmq/logs/rocketmqlogs/proxy.log '
                    '/home/rocketmq/logs/rocketmqlogs/broker.log 2>/dev/null'],
                    required=False, timeout=20)
                failure_diagnostics = {'clients': client_diagnostics,
                                       'broker': summarize(broker_logs.stdout + broker_logs.stderr)}
            except Exception:
                # Diagnostics must never prevent the actual owned cleanup.
                failure_diagnostics = {'capture_failed': True}
        probes_drained = True
        for p in reversed(probes):
            if not p.log.closed:
                probes_drained = p.close() and probes_drained
        if not probes_drained:
            failure = failure or "owned probe process group did not drain"
        run(["docker", "unpause", mysql], required=False)
        run(compose + ["down", "--volumes", "--remove-orphans", "--timeout", "30"], timeout=120)
        remaining = run(["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + project]).stdout.strip()
        if remaining:
            failure = failure or "owned Compose containers remain after cleanup"
        report = {"version": 1, "batch": ("M2-Go-Python-SDK" if args.sdk_api_python else "M2-Go-SDK") if args.sdk_api_go else "M2-0", "project": project, "image": image,
                  "mysql_image": mysql_image, "mongo_image": mongo_image, "clients": {"go": "5.1.4", "python": "5.1.2"},
                  "cases": cases, "passed": len(cases), "failed": int(failure is not None),
                  "skipped": 0, "failure": failure, "proof": proof,
                  "failure_diagnostics": failure_diagnostics,
                  "cleanup": {"project_containers_remaining": bool(remaining), "compose_down_succeeded": True,
                              "probe_process_groups_drained": probes_drained},
                  "probe_receipts": [{"pid": p.process.pid, "exit_code": p.process.returncode,
                                      "events": p.events} for p in probes],
                  "limits": (["No production acceptance or throughput claim",
                              "Public producer/consumer SDK, original transaction stores and scoped v2 owner ACLs",
                              ("Actual packet commit faults and native-limit audit required in this report" if args.sdk_limits else
                               "Packet faults/native-limit audit are separate gates not claimed by this profile")]
                             if args.sdk_api_go else ["No production acceptance or throughput claim",
                              "Raw-client feasibility only; not public SDK transaction acceptance",
                              "Response loss is client-side discard after real RPC, not packet-level loss"]),
                  "source_sha256": {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in sorted(sources.iterdir()) if p.is_file()}}
        report["sdk_source_sha256"] = {str(p.relative_to(sdk)): hashlib.sha256(p.read_bytes()).hexdigest()
                                       for p in sorted(sdk_sources.rglob("*")) if p.is_file()}
        report["sdk_sha"] = run(["git", "rev-parse", "HEAD"], cwd=sdk).stdout.strip()
        report["go_version"] = run(["go", "env", "GOVERSION"], cwd=sdk).stdout.strip()
        api_binary = args.sdk_go_probe or directory / "sdk-go-probe"
        if args.sdk_api_go and api_binary.is_file():
            report["sdk_go_probe_sha256"] = hashlib.sha256(api_binary.read_bytes()).hexdigest()
            source_paths = [*sdk.glob("transaction/*.go"), *sdk.glob("storage/transaction/**/*.go"),
                            *sdk.glob("storage/transaction/**/*.sql"),
                            *sdk.glob("transport/rocketmq/transaction*.go"),
                            *sdk.glob("transport/routing*.go"), sdk / "contracts/rocketmq-routing-v2.json",
                            sdk / "python/src/reliable_messaging/transport.py",
                            *sdk.glob("python/src/reliable_messaging/transaction*"),
                            sdk / "python/src/reliable_messaging/rocketmq_transaction.py",
                            sdk / "python/src/reliable_messaging/_rocketmq_transaction_driver.py",
                            sdk / "python/tests/integration/transaction_probe.py"]
            report["sdk_api_source_sha256"] = {str(path.relative_to(sdk)): hashlib.sha256(path.read_bytes()).hexdigest()
                                               for path in sorted(set(source_paths)) if path.is_file()}
            report["sdk_tracked_sources_clean"] = run(["git", "diff", "--quiet", "HEAD"], cwd=sdk, required=False).returncode == 0
        if args.sdk_api_python:
            metadata_command = ([interpreter_path(args.installed_python), "-I"] if args.installed_python else
                [args.python,"run","--locked","--project",str(sdk / "python"),"--extra","rocketmq","--extra","nsq","python"])
            try:
                metadata = run(metadata_command + ["-c",
                    "import sys,json,reliable_messaging as r,importlib.metadata as m; print(json.dumps({'python':sys.version.split()[0],'client':m.version('rocketmq-python-client'),'sdk_version':m.version('fangcun-reliable-messaging'),'package_file':r.__file__}))"]).stdout
                report["python_runtime"] = json.loads(metadata)
            except Exception:
                failure = failure or "Python runtime metadata unavailable"
                report["failed"] = 1
                report["failure"] = failure
                report["python_runtime"] = {"unavailable": True}
            report["published_installation"] = bool(args.installed_python)
            if (args.installed_python and report["python_runtime"].get("package_file")
                    and Path(report["python_runtime"]["package_file"]).resolve().is_relative_to(sdk)):
                failure = failure or "published Python acceptance imported source checkout"
                report["failed"] = 1
                report["failure"] = failure
        if args.iam_host:
            report['batch'] = 'M3-IAM-host-with-M2-0-baseline'
            report['limits'].append('IAM host acceptance uses released SDK; base raw-client cases remain separately scoped')
            report['iam_harness_sha256'] = hashlib.sha256((repo / 'scripts/rocketmq/iam_acceptance.py').read_bytes()).hexdigest()
        if args.qs_answer_host:
            report['batch'] = 'M3-QS-answer-original-Mongo-host'
            report['limits'] = ['No production/system acceptance or throughput claim',
                                'Actual host SDK and original Mongo transactions, not raw-client feasibility',
                                'Root ACK discard is client-level; packet-loss and process-exit acceptance remain separate gates']
            report['qs_answer_harness_sha256'] = hashlib.sha256((repo / 'scripts/rocketmq/qs_answer_acceptance.py').read_bytes()).hexdigest()
        if args.qs_report_host:
            report['batch'] = 'M3-QS-report-original-Mongo-host'
            report['limits'] = ['No production/system acceptance or throughput claim',
                                'Actual host terminal Sender and original Mongo/Broker; running claims and report body supplied by fixtures',
                                'Root reply discard is client-level; no packet-loss, SIGKILL, model invocation or T13 handoff claim']
            report['qs_report_harness_sha256'] = hashlib.sha256((repo / 'scripts/rocketmq/qs_report_acceptance.py').read_bytes()).hexdigest()
        if args.qs_retry_dispatch_host:
            report['batch'] = 'M3-QS-retry-original-roots-and-real-due-dispatch'
            report['limits'] = ['No production/system acceptance or throughput claim',
                                'Actual evaluation failure/report terminal hosts and real due Broker dispatch',
                                'Observer ACK only; no next business consumer, provider call, SIGKILL, packet-loss or ownership handoff claim']
            report['qs_retry_dispatch_harness_sha256'] = hashlib.sha256((repo / 'scripts/rocketmq/qs_retry_dispatch_acceptance.py').read_bytes()).hexdigest()
        if args.qs_retry_store_host:
            report['batch'] = 'M3-QS-retry-original-dual-store-authorizations'
            report['limits'] = ['No production/system acceptance or throughput claim',
                                'Original MySQL/Mongo authorization and explicit legacy future ownership handoff',
                                'No due dispatcher, Broker visibility, packet loss, SIGKILL or production handoff claim']
            report['qs_retry_harness_sha256'] = hashlib.sha256((repo / 'scripts/rocketmq/qs_retry_acceptance.py').read_bytes()).hexdigest()
        if args.qs_task_host:
            report['batch'] = 'M3-QS-task-original-MySQL-and-NORMAL'
            report['limits'] = ['No production/system acceptance or throughput claim',
                                'Actual original task MySQL committer and best_effort NORMAL fanout; deterministic fixture input',
                                'Fresh owner recovery is not SIGKILL; no packet-loss or T13 dispatch claim']
            report['qs_task_harness_sha256'] = hashlib.sha256((repo / 'scripts/rocketmq/qs_task_acceptance.py').read_bytes()).hexdigest()
        if args.qs_evaluation_host:
            report['batch'] = 'M3-QS-evaluation-original-MySQL-host'
            report['limits'] = ['No production/system acceptance or throughput claim',
                                'Actual submission/outcome application roots and original MySQL/Broker',
                                'No packet loss, SIGKILL or future retry handoff claim']
            report['qs_evaluation_harness_sha256'] = hashlib.sha256((repo / 'scripts/rocketmq/qs_evaluation_acceptance.py').read_bytes()).hexdigest()
        report["go_runtime_patch"] = "v5.1.4 + per-client RPC/TLS options (SDK private snapshot)"
        report["harness_sha256"] = {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in (Path(__file__).resolve(), repo / "scripts/rocketmq/render.py",
                                              repo / "components/rocketmq/docker-compose.yml", repo / "scripts/rocketmq/sdk_acceptance.py",
                                              repo / "scripts/rocketmq/v2_acceptance.py", repo / "scripts/rocketmq/sdk_faults.py", repo / "scripts/rocketmq/sdk_limits.py",
                                              repo / "scripts/rocketmq/audit_transaction_limit.py", repo / "scripts/rocketmq/routes.py",
                                              repo / "scripts/rocketmq/provision_v2.py")}
        report['harness_sha256']['scripts/rocketmq/failure_diagnostics.py'] = hashlib.sha256(
            (repo / 'scripts/rocketmq/failure_diagnostics.py').read_bytes()).hexdigest()
        report['harness_sha256']['scripts/rocketmq/published_runtime.py'] = hashlib.sha256(
            (repo / 'scripts/rocketmq/published_runtime.py').read_bytes()).hexdigest()
        report["go_probe_sha256"] = hashlib.sha256((args.go_probe or directory / "go-probe").read_bytes()).hexdigest() if (args.go_probe or directory / "go-probe").exists() else None
        dirty_sdk = args.sdk_api_go and not report.get("sdk_tracked_sources_clean", False)
        if dirty_sdk:
            report["failed"] = 1
            report["failure"] = report["failure"] or "tracked SDK source changed during acceptance"
        # All evidence needed for the public report is now captured. Restore
        # ownership only under THIS random private fixture mount, then remove its
        # credentials, TLS key, audit files, logs and Broker store. Never prune
        # images or touch another Compose project's directories/volumes.
        private_removed = False
        try:
            if directory.parent != Path(tempfile.gettempdir()) or not directory.name.startswith("rocketmq-m2-"):
                raise RuntimeError("private fixture directory guard failed")
            run(["docker","run","--rm","--user","0","--entrypoint","chown",
                 "-v",str(directory)+":/owned",image,"-R",f"{os.getuid()}:{os.getgid()}","/owned"],timeout=45)
            shutil.rmtree(directory)
            private_removed = not directory.exists()
        except Exception:
            report["failed"] = 1
            report["failure"] = report["failure"] or "private fixture cleanup failed"
        report["cleanup"]["private_fixture_directory_removed"] = private_removed
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        if remaining or dirty_sdk or not private_removed or not probes_drained:
            raise RuntimeError("owned cleanup or exact SDK source verification failed")
        if report["failed"]:
            raise RuntimeError("transaction acceptance failed; see the retained report")


if __name__ == "__main__":
    main()
