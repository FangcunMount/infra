"""Manage one time-limited ServerA discovery key on ServerD."""
from base64 import b64decode, b64encode
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import tempfile

from render_deadline import render
from render_withdrawal import ROOT, units

KEYS = Path("/root/.ssh/authorized_keys")
SOURCE = "100.74.123.45"
COMMAND = "/usr/local/sbin/infra-monitoring-discovery"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def utc(value):
    require(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value),
        "expected a whole second in UTC",
    )
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def auth_line(operation, plan):
    deadline = render(plan["cutoff_utc"], "Asia/Shanghai")
    start, latest, cutoff = map(
        utc, (plan["starts_utc"], plan["latest_start_utc"], plan["cutoff_utc"])
    )
    require(start < latest < cutoff, "authorization window timestamps are out of order")
    blob = b64decode(plan["key_blob"], validate=True)
    require(
        len(blob) == 51 and blob[:19] == b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20",
        "expected one ED25519 public key",
    )
    require(b64encode(blob).decode() == plan["key_blob"], "noncanonical public key")
    fingerprint = "SHA256:" + b64encode(sha256(blob).digest()).decode().rstrip("=")
    require(fingerprint == plan["public_fingerprint"], "public key fingerprint differs")
    require(
        re.fullmatch("[a-f0-9]{64}", plan["original_line_sha256"]),
        "original key line digest required",
    )
    row = (
        f'restrict,from="{SOURCE}",expiry-time="{deadline["sshd_expiry_time"]}",'
        f'command="{COMMAND}" ssh-ed25519 {plan["key_blob"]} {operation}\n'
    ).encode()
    return row, start, latest


def read_keys(path):
    require(path.resolve() == path, "authorized_keys path changed")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        meta = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(meta.st_mode)
            and meta.st_uid == 0
            and not meta.st_mode & 0o022,
            "root-owned authorized_keys required",
        )
        data = stream.read(1048577)
        require(
            0 < len(data) <= 1048576 and data.endswith(b"\n"),
            "invalid key file size or terminator",
        )
    return meta, data


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def replace(path, raw, meta=None, previous=None):
    fd, name = tempfile.mkstemp(prefix=".qlume-h04-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            if meta is not None:
                os.fchown(stream.fileno(), meta.st_uid, meta.st_gid)
                os.fchmod(stream.fileno(), stat.S_IMODE(meta.st_mode))
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if meta is not None:
            current, observed = read_keys(path)
            require(
                observed == previous
                and (current.st_dev, current.st_ino, current.st_mtime_ns)
                == (meta.st_dev, meta.st_ino, meta.st_mtime_ns),
                "authorized_keys changed during operation",
            )
        os.replace(name, path)
        sync_directory(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def require_timer(operation, plan, digest):
    name, service, timer, _ = units(
        operation, plan["cutoff_utc"], "Asia/Shanghai", digest
    )
    directory = Path("/etc/systemd/system")
    for suffix, expected in (("timer", timer), ("service", service)):
        path = directory / f"{name}.{suffix}"
        require(
            not path.is_symlink() and path.read_text() == expected,
            "installed withdrawal units differ",
        )
        raw = subprocess.check_output(
            [
                "/usr/bin/systemctl",
                "show",
                "--no-pager",
                "--property=LoadState,ActiveState,SubState,UnitFileState,FragmentPath,DropInPaths,NeedDaemonReload",
                path.name,
            ],
            text=True,
            timeout=6,
        )
        values = dict(line.split("=", 1) for line in raw.splitlines())
        require(
            values["LoadState"] == "loaded"
            and values["FragmentPath"] == str(path)
            and values["DropInPaths"] == ""
            and values["NeedDaemonReload"] == "no",
            "loaded withdrawal units differ",
        )
        if suffix == "timer":
            require(
                (values["ActiveState"], values["SubState"], values["UnitFileState"])
                == ("active", "waiting", "enabled"),
                "persistent withdrawal timer is not waiting",
            )


def main():
    os.umask(0o077)
    require(
        len(sys.argv) == 3 and sys.argv[1] in {"append", "withdraw"},
        "usage: serverd-auth.py append|withdraw PLAN_SHA256",
    )
    action, digest = sys.argv[1:]
    root = Path(__file__).resolve().parent
    require(
        os.geteuid() == 0
        and socket.gethostname().split(".")[0].lower() == "serverd"
        and root.parent == Path(ROOT)
        and root.stat().st_uid == 0
        and stat.S_IMODE(root.stat().st_mode) == 0o700,
        "root on ServerD and private H04 operation directory required",
    )
    path = root / "auth-plan.json"
    info = path.lstat()
    require(
        stat.S_ISREG(info.st_mode)
        and info.st_uid == 0
        and stat.S_IMODE(info.st_mode) == 0o600,
        "root-owned private authorization plan required",
    )
    raw = path.read_bytes()
    require(sha256(raw).hexdigest() == digest, "authorization plan SHA-256 differs")
    plan = json.loads(raw)
    operation = root.name
    require(
        re.fullmatch(r"h04-[a-z0-9][a-z0-9-]{4,38}", operation)
        and plan["operation_id"] == operation,
        "operation identity differs",
    )
    row, start, latest = auth_line(operation, plan)
    lock = os.open(
        "/run/lock/qlume-servera-pilot-auth.lock",
        os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
        0o600,
    )
    with os.fdopen(lock, "rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        if action == "append":
            require(
                not (root / "withdraw-receipt.json").exists(),
                "operation already withdrawn",
            )
            require(
                Path("/etc/timezone").read_text().strip() == "Asia/Shanghai",
                "ServerD timezone differs",
            )
            require_timer(operation, plan, digest)
        meta, before = read_keys(KEYS)
        lines = before.splitlines(keepends=True)
        old = plan["original_line_sha256"]
        require(
            sum(sha256(line).hexdigest() == old for line in lines) == 1,
            "original discovery key differs",
        )
        token = plan["key_blob"].encode()
        matching = [line for line in lines if token in line.split()]
        if action == "append":
            require(
                start <= datetime.now(timezone.utc) < latest,
                "outside the approved append interval",
            )
            require(not matching, "candidate key already present")
            require(
                not Path("/root/.ssh/authorized_keys2").exists(),
                "secondary key file requires review",
            )
            after = before + row
        else:
            require(
                matching in ([], [row]), "candidate key occurs with unexpected controls"
            )
            after = b"".join(line for line in lines if line != row)
        if after != before:
            replace(KEYS, after, meta, before)
        require(read_keys(KEYS)[1] == after, "authorized_keys readback differs")
        result = dict(
            operation=action,
            operation_id=operation,
            plan_sha256=digest,
            changed=after != before,
            original_line_sha256=old,
            original_line_preserved=True,
            pilot_line_sha256=sha256(row).hexdigest(),
            pilot_present=action == "append",
            public_fingerprint=plan["public_fingerprint"],
            at=datetime.now(timezone.utc).isoformat(),
        )
        receipt = root / f"{action}-receipt.json"
        if receipt.exists():
            receipt = (
                root
                / f"{action}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json"
            )
        replace(receipt, (json.dumps(result, indent=2) + "\n").encode())
        print(json.dumps(result))


if __name__ == "__main__":
    main()
