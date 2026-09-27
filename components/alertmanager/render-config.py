#!/usr/bin/env python3
"""Render an Alertmanager email route without embedding SMTP credentials."""

import argparse
import json
import os
import re
import tempfile
from pathlib import Path


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is required")
    if "\n" in value or "\r" in value:
        raise SystemExit(f"{name} must be a single line")
    return value


def address(name: str) -> str:
    value = required(name)
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+", value):
        raise SystemExit(f"{name} must be a single email address")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    smarthost = required("ALERTMANAGER_SMTP_SMARTHOST")
    if not re.fullmatch(r"[A-Za-z0-9.-]+:[0-9]{1,5}", smarthost):
        raise SystemExit("ALERTMANAGER_SMTP_SMARTHOST must be host:port")
    sender = address("ALERTMANAGER_SMTP_FROM")
    recipient = address("ALERTMANAGER_EMAIL_TO")
    username = required("ALERTMANAGER_SMTP_AUTH_USERNAME")

    # JSON string literals are valid YAML scalars and prevent config injection.
    config = (
        "global:\n"
        f"  smtp_smarthost: {json.dumps(smarthost)}\n"
        f"  smtp_from: {json.dumps(sender)}\n"
        f"  smtp_auth_username: {json.dumps(username)}\n"
        "  smtp_auth_password_file: /etc/alertmanager/secrets/smtp_password\n"
        "  smtp_require_tls: true\n"
        "route:\n"
        "  receiver: discard\n"
        "  group_by: [alertname, service, store]\n"
        "  group_wait: 30s\n"
        "  group_interval: 5m\n"
        "  repeat_interval: 4h\n"
        "  routes:\n"
        "    - receiver: reliable-messaging-email\n"
        "      matchers:\n"
        "        - 'subsystem=\"event\"'\n"
        "receivers:\n"
        "  - name: discard\n"
        "  - name: reliable-messaging-email\n"
        "    email_configs:\n"
        f"      - to: {json.dumps(recipient)}\n"
        "        send_resolved: true\n"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=args.output.parent, delete=False
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(config)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, 0o640)
        os.replace(temporary_name, args.output)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


if __name__ == "__main__":
    main()
