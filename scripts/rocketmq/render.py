#!/usr/bin/env python3
"""Render private RocketMQ configuration. No network, no service changes."""
import argparse
import json
import os
from pathlib import Path


def render(credentials, output, advertised_host, templates):
    admin = credentials["admin"]
    inner = credentials["inner"]
    for account in (admin, inner):
        if not account.get("username") or len(account.get("password", "")) < 32:
            raise ValueError("distinct admin/inner credentials of at least32 characters required")
    if admin["username"] == inner["username"]:
        raise ValueError("admin and internal account must differ")
    output.mkdir(parents=True, exist_ok=True, mode=0o750)
    broker = (templates / "broker.conf.example").read_text()
    broker += "brokerIP1=" + advertised_host + "\n"
    broker += "initAuthenticationUser=" + json.dumps(admin, separators=(",", ":")) + "\n"
    internal = {"accessKey": inner["username"], "secretKey": inner["password"]}
    broker += "innerClientAuthenticationCredentials=" + json.dumps(internal, separators=(",", ":")) + "\n"
    proxy = json.loads((templates / "proxy.json.example").read_text())
    proxy.update(localServeAddr=advertised_host, initAuthenticationUser=json.dumps(admin),
                 innerClientAuthenticationCredentials=json.dumps(internal),
                 tlsKeyPath="/etc/rocketmq/tls/server.key", tlsCertPath="/etc/rocketmq/tls/server.crt")
    tools = "accessKey: " + json.dumps(admin["username"]) + "\nsecretKey: " + json.dumps(admin["password"]) + "\n"
    for name, content in (("tools.yml", tools), ("broker.conf", broker), ("proxy.json", json.dumps(proxy, indent=2) + "\n")):
        path = output / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
        os.chmod(path, 0o640)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--credentials", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--advertised-host", required=True)
    args = p.parse_args()
    mode = args.credentials.stat().st_mode & 0o777
    if mode & 0o077:
        p.error("credential file must have mode0600 or0400")
    if any(c in args.advertised_host for c in "\r\n= "):
        p.error("invalid advertised host")
    render(json.loads(args.credentials.read_text()), args.output, args.advertised_host,
           Path(__file__).resolve().parents[2] / "components/rocketmq")


if __name__ == "__main__":
    main()
