#!/usr/bin/env python3
"""Required real Broker acceptance using infra's disposable Docker Compose stack.

No production host, database, reset-offset, prune or external credential input.
Missing SDK/image/dependencies fail this run. SDK DB proofs run in SDK CI.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time

from render import render

REDACT = []


def command(args, *, env=None, cwd=None, timeout=180, required=True):
    result = subprocess.run(args, env=env, cwd=cwd, capture_output=True,
                            text=True, timeout=timeout)
    if required and result.returncode:
        # Driver/CLI diagnostics may include credentials. Preserve categories;
        # no complete command line or stdout/stderr is emitted into CI logs.
        diagnostic = (result.stdout + "\n" + result.stderr)[-6000:]
        for secret in REDACT:
            diagnostic = diagnostic.replace(secret, "[withheld]")
        raise RuntimeError(Path(str(args[0])).name + " acceptance operation failed: " + diagnostic)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--build-log", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    import re
    build_log = args.build_log.read_text()
    if not re.search(r"\[GNUPG:\] VALIDSIG 09D58134D2DA90B296ABCB77D5C871BAC9D394D2", build_log) or "rocketmq.zip: OK" not in build_log:
        raise SystemExit("required fresh build SHA512/PGP verification evidence absent")
    sdk = args.sdk.resolve()
    if not (sdk / "examples/rocketmq/main.go").is_file():
        raise SystemExit("required pinned SDK checkout missing")
    sdk_sha = command(["git", "-C", str(sdk), "rev-parse", "HEAD"]).stdout.strip()
    infra_sha = command(["git", "-C", str(repo), "rev-parse", "HEAD"]).stdout.strip()
    image = command(["docker", "image", "inspect", args.image, "--format", "{{.Id}}"])
    image = image.stdout.strip()
    if not image.startswith("sha256:"):
        raise SystemExit("immutable test image missing")
    directory = Path(tempfile.mkdtemp(prefix="rocketmq-m1-"))
    directory.chmod(0o700)
    config, data = directory / "config", directory / "data"
    config.mkdir(); data.mkdir(); (config / "tls").mkdir()
    credentials = {role: {"username": "ci-" + role, "password": secrets.token_hex(32)}
                   for role in ("admin", "inner", "interop", "denied")}
    REDACT.extend(account["password"] for account in credentials.values())
    secret = directory / "credentials.json"
    secret.write_text(json.dumps(credentials)); secret.chmod(0o600)
    render(credentials, config, "127.0.0.1", repo / "components/rocketmq")
    command(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
             "-subj", "/CN=rocketmq-m1-ci", "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost",
             "-keyout", str(config / "tls/server.key"), "-out", str(config / "tls/server.crt")])
    ca = directory / "ca.crt"
    shutil.copyfile(config / "tls/server.crt", ca)
    command(["docker", "run", "--rm", "--user", "0", "--entrypoint", "bash",
             "-v", str(config) + ":/config", "-v", str(data) + ":/data", image, "-c",
             "mkdir -p /data/store /data/auth /data/logs /data/nameserver-logs; "
             "chown -R 3000:3000 /data /config; chmod 750 /config /config/tls; "
             "chmod 640 /config/broker.conf /config/proxy.json /config/tools.yml /config/tls/server.key"])
    env_file = directory / "compose.env"
    env_file.write_text(f"ROCKETMQ_IMAGE={image}\nROCKETMQ_BIND_IP=127.0.0.1\n"
                        f"ROCKETMQ_DATA_ROOT={data}\nROCKETMQ_CONFIG_ROOT={config}\n")
    project = "rocketmq-m1-ci-" + str(os.getpid())
    compose = ["docker", "compose", "-p", project, "--env-file", str(env_file),
               "-f", str(repo / "components/rocketmq/docker-compose.yml")]
    broker = project + "-broker-1"
    cases = {}

    def admin(operation, *parameters):
        result = command(["docker", "exec", broker, "java", "-Xms32m", "-Xmx128m",
                          "-XX:MaxDirectMemorySize=32m", "-cp",
                          "/opt/rocketmq/conf:/opt/rocketmq/lib/*",
                          "org.apache.rocketmq.tools.command.MQAdminStartup", operation,
                          "-b", "127.0.0.1:10911", *parameters], timeout=45)
        return result.stdout

    def probe(language, mode, identity, account="interop", required=True):
        environment = dict(os.environ, ROCKETMQ_CREDENTIALS_FILE=str(secret),
                           ROCKETMQ_CA_FILE=str(ca), ROCKETMQ_ACCOUNT=account,
                           GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=str(ca))
        if language == "go":
            argv = [str(directory / "go-probe"), "-mode", mode, "-id", identity]
        else:
            argv = ["uv", "run", "--project", str(sdk / "python"), "python",
                    str(sdk / "python/examples/rocketmq_probe.py"), mode, "--id", identity]
        result = command(argv, env=environment, cwd=sdk, required=required, timeout=75)
        if required:
            marker = "broker_confirmed " if mode == "publish" else (
                "received_and_acknowledged " if language == "go" else "received ")
            if marker + identity not in result.stdout:
                raise RuntimeError(language + " probe completion marker missing")
            if language == "python" and mode == "consume" and "acknowledged_after_handler_commit" not in result.stdout:
                raise RuntimeError("Python consumer did not finish ACK/drain")
        return result

    def await_topic_route():
        # A listening local Proxy is insufficient after a Broker restart: the
        # NameServer must have received the Broker's persisted topic routes.
        manifest = json.loads((repo / "components/rocketmq/test-routes.json").read_text())
        topic = manifest["routes"][0]["physical_topic"]
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            result = command(["docker", "exec", broker, "java", "-Xms32m", "-Xmx128m",
                              "-XX:MaxDirectMemorySize=32m", "-cp",
                              "/opt/rocketmq/conf:/opt/rocketmq/lib/*",
                              "org.apache.rocketmq.tools.command.MQAdminStartup", "topicRoute",
                              "-n", "nameserver:9876", "-t", topic], required=False, timeout=20)
            try:
                route = json.loads(result.stdout[result.stdout.index("{"):])
                if result.returncode == 0 and route.get("brokerDatas") and route.get("queueDatas"):
                    return
            except (ValueError, TypeError):
                pass
            time.sleep(2)
        raise RuntimeError("persisted topic route was not registered with NameServer")

    try:
        command(compose + ["up", "-d", "--wait", "--wait-timeout", "180"], timeout=240)
        command(["python3", str(repo / "scripts/rocketmq/provision.py"), "--container", broker,
                 "--project", project, "--manifest", str(repo / "components/rocketmq/test-routes.json"),
                 "--credentials", str(secret)], timeout=300)
        denied = credentials["denied"]
        if " success." not in admin("createUser", "-u", denied["username"], "-p", denied["password"], "-t", "Normal"):
            raise RuntimeError("negative-test principal was not provisioned")
        command(["go", "build", "-o", str(directory / "go-probe"), "./examples/rocketmq"], cwd=sdk)
        command(["uv", "sync", "--locked", "--all-extras", "--group", "dev", "--project", str(sdk / "python")])
        await_topic_route()
        for publisher in ("go", "python"):
            identity = "ci-" + publisher + "-" + secrets.token_hex(4)
            probe(publisher, "publish", identity)
            for consumer in ("go", "python"):
                print(publisher + "_to_" + consumer + " starting", flush=True)
                probe(consumer, "consume", identity)
                print(publisher + "_to_" + consumer + " passed", flush=True)
                cases[publisher + "_to_" + consumer] = True
        for language in ("go", "python"):
            if probe(language, "publish", "forbidden", account="denied", required=False).returncode == 0:
                raise RuntimeError("unprivileged account was able to publish")
            cases[language + "_acl_denied"] = True
        broker_config = admin("getBrokerConfig")
        if not re.search(r"flushDiskType\s*=\s*SYNC_FLUSH", broker_config):
            raise RuntimeError("synchronous flush not active")
        cases["sync_flush"] = True
        flags = command(["docker", "exec", broker, "cat", "/proc/1/cmdline"]).stdout.split("\0")
        if not flags[0].endswith("/java") or "-Xmx512m" not in flags or "-XX:MaxDirectMemorySize=128m" not in flags:
            raise RuntimeError("PID1/effective bounded JVM options differ")
        if any(option in flags for option in ("-Xmx8g", "-XX:MaxDirectMemorySize=15g")):
            raise RuntimeError("unbounded upstream JVM defaults leaked into runtime")
        cases["java_pid1_and_limits"] = True
        identity = "confirmed-before-kill-" + secrets.token_hex(4)
        probe("go", "publish", identity)
        command(["docker", "kill", "--signal", "KILL", broker])
        command(["docker", "start", broker])
        command(compose + ["up", "-d", "--wait", "--wait-timeout", "180"], timeout=240)
        await_topic_route()
        probe("go", "consume", identity)
        cases["confirmed_message_survives_broker_kill"] = True
        began = time.monotonic()
        command(["docker", "stop", "--time", "30", broker], timeout=45)
        state = json.loads(command(["docker", "inspect", broker]).stdout)[0]["State"]
        if state["ExitCode"] == 137 or state["OOMKilled"]:
            raise RuntimeError("Docker SIGTERM required a kill or hit OOM")
        cases["graceful_sigterm"] = True
        report = {"version": 1, "infra_sha": infra_sha, "sdk_sha": sdk_sha, "image": image,
                  "cases": cases, "passed": len(cases), "failed": 0, "skipped": 0,
                  "graceful_stop_seconds": round(time.monotonic() - began, 3),
                  "signature_verified": True, "sync_flush_verified": True,
                  "persistence_verified": True, "acl_verified": True,
                  "sdk_interop_verified": True}
        # Signature evidence comes from the required Dockerfile build step;
        # production deployment still binds the exact image and source receipts.
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"passed": len(cases), "failed": 0, "skipped": 0}))
    finally:
        command(compose + ["down", "--volumes", "--remove-orphans", "--timeout", "30"],
                timeout=120, required=True)


if __name__ == "__main__":
    main()
