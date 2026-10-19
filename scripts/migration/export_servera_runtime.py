#!/usr/bin/env python3
"""Export inspected serverA services or explicit IAM scope into private pinned Compose.

The input and output contain production credentials. Never print or commit them.
This exports configuration only; it does not start containers or copy data.
"""

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


EXPECTED = {
    "qs-apiserver", "qs-collection-server-1", "qs-collection-server-2",
    "qs-ai", "nginx", "prometheus-route",
}


def escape_interpolation(value):
    if isinstance(value, str):
        return value.replace("$", "$$")
    if isinstance(value, list):
        return [escape_interpolation(v) for v in value]
    if isinstance(value, dict):
        return {k: escape_interpolation(v) for k, v in value.items()}
    return value


def database_url_at_proxy(value):
    parsed = urlsplit(value)
    if parsed.scheme != "mysql+asyncmy" or not parsed.hostname:
        raise ValueError("Unexpected AI database URL format")
    credentials = parsed.netloc.rsplit("@", 1)
    if len(credentials) != 2:
        raise ValueError("AI database URL has no credentials")
    return urlunsplit(parsed._replace(netloc=credentials[0] + "@mysql-rds-proxy:3306"))


def export_runtime(containers, scope="servera"):
    expected = EXPECTED if scope == "servera" else {"iam-apiserver"} if scope == "iam" else None
    if expected is None:
        raise ValueError("Unreviewed migration scope")
    names = [c["Name"].lstrip("/") for c in containers]
    if len(names) != len(expected) or set(names) != expected:
        raise ValueError("Source container set differs from the migration scope")
    services, networks = {}, {}
    for container in containers:
        name = container["Name"].lstrip("/")
        config, host = container["Config"], container["HostConfig"]
        environment = dict(e.split("=", 1) for e in config.get("Env", []))
        if name == "iam-apiserver":
            if "IAM_APISERVER_MYSQL_HOST" not in environment:
                raise ValueError("IAM source has no explicit MySQL endpoint")
            environment["IAM_APISERVER_MYSQL_HOST"] = "mysql-rds-proxy:3306"
        if name == "qs-apiserver":
            environment["QS_APISERVER_MYSQL_HOST"] = "mysql-rds-proxy:3306"
        if name == "qs-ai":
            environment["QS_AI_DATABASE_URL"] = database_url_at_proxy(environment["QS_AI_DATABASE_URL"])
        service = {
            "image": container["Image"], "pull_policy": "never",
            "container_name": name, "environment": environment,
            "restart": host["RestartPolicy"]["Name"],
            "labels": {k: v for k, v in (config.get("Labels") or {}).items()
                       if not k.startswith("com.docker.compose.")},
            "volumes": [], "networks": {},
        }
        for field in ["User", "WorkingDir", "Entrypoint", "Cmd", "StopSignal"]:
            if config.get(field) is not None and config[field] != "":
                key = {"User": "user", "WorkingDir": "working_dir", "Entrypoint": "entrypoint",
                       "Cmd": "command", "StopSignal": "stop_signal"}[field]
                service[key] = config[field]
        for mount in container.get("Mounts", []):
            if mount["Type"] != "bind":
                raise ValueError("Unreviewed non-bind mount in " + name)
            tls_files = {
                "/etc/iam/grpc/ca": ["ca-chain.crt"],
                "/etc/iam/grpc/server": ["iam-apiserver.crt", "iam-apiserver.key"],
            } if scope == "iam" else {}
            files = tls_files.get(mount["Destination"])
            if files and mount["RW"]:
                raise ValueError("IAM TLS mount must be read-only")
            for filename in files or [None]:
                service["volumes"].append({
                    "type": "bind",
                    "source": os.path.join(mount["Source"], filename) if filename else mount["Source"],
                    "target": os.path.join(mount["Destination"], filename) if filename else mount["Destination"],
                    "read_only": not mount["RW"], "bind": {"create_host_path": False},
                })
        for network, endpoint in container["NetworkSettings"]["Networks"].items():
            if network not in ({"infra-network"} if scope == "iam" else {"infra-network", "qs-network"}):
                raise ValueError("Unreviewed network in " + name)
            networks[network] = {"external": True, "name": network}
            service["networks"][network] = {"aliases": list(dict.fromkeys(endpoint.get("Aliases") or []))}
        for field, key in [("ReadonlyRootfs", "read_only"), ("CapDrop", "cap_drop"),
                           ("CapAdd", "cap_add"), ("SecurityOpt", "security_opt"),
                           ("ExtraHosts", "extra_hosts"),
                           ("GroupAdd", "group_add"), ("Sysctls", "sysctls"),
                           ("Dns", "dns"), ("DnsOptions", "dns_opt"),
                           ("DnsSearch", "dns_search")]:
            if host.get(field):
                service[key] = host[field]
        if host.get("Tmpfs"):
            service["tmpfs"] = [path + ":" + options for path, options in host["Tmpfs"].items()]
        if host.get("Memory"):
            service["mem_limit"] = host["Memory"]
        if host.get("NanoCpus"):
            service["cpus"] = str(host["NanoCpus"] / 1_000_000_000)
        if host.get("PidsLimit") and host["PidsLimit"] > 0:
            service["pids_limit"] = host["PidsLimit"]
        if host.get("ShmSize"):
            service["shm_size"] = host["ShmSize"]
        if host.get("Ulimits"):
            service["ulimits"] = {v["Name"]: {"soft": v["Soft"], "hard": v["Hard"]}
                                 for v in host["Ulimits"]}
        if config.get("StopTimeout") is not None:
            service["stop_grace_period"] = str(config["StopTimeout"]) + "s"
        logging = host.get("LogConfig")
        if logging and logging.get("Type"):
            service["logging"] = {"driver": logging["Type"], "options": logging.get("Config") or {}}
        health = config.get("Healthcheck")
        if health:
            service["healthcheck"] = {"test": health["Test"]}
            for field, key in [("Interval", "interval"), ("Timeout", "timeout"),
                               ("StartPeriod", "start_period"), ("StartInterval", "start_interval")]:
                if health.get(field):
                    service["healthcheck"][key] = str(health[field]) + "ns"
            if health.get("Retries"):
                service["healthcheck"]["retries"] = health["Retries"]
        ports = []
        for port, bindings in (host.get("PortBindings") or {}).items():
            target, protocol = port.split("/")
            for binding in bindings or []:
                ports.append({"target": int(target), "published": binding["HostPort"],
                              "host_ip": binding["HostIp"] or "0.0.0.0", "protocol": protocol})
        if ports:
            service["ports"] = ports
        if scope == "iam":
            # Alibaba VPC DNS cannot be used on Tencent; inherit the new host resolver.
            service.pop("dns", None)
        services[name] = service
    return escape_interpolation({"name": "docker" if scope == "iam" else "servera-migration", "services": services, "networks": networks})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--scope", choices=["servera", "iam"], default="servera")
    parser.add_argument("--legacy-proxy-rollback", action="store_true", help="Explicitly authorize this historical proxy-based export")
    args = parser.parse_args()
    if not args.legacy_proxy_rollback:
        parser.error("Historical exporter requires --legacy-proxy-rollback; current production uses public MySQL TLS")
    result = export_runtime(json.loads(args.input.read_text()), args.scope)
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print("Exported pinned services; output contains credentials and is mode 0600")


if __name__ == "__main__":
    main()
