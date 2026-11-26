"""Import a B05-verified Prometheus archive into the separately signed H06 history volume."""
import argparse
import fcntl
import os
from datetime import datetime, timezone
from hashlib import file_digest, sha256
import json
from pathlib import Path
import re
import secrets
import socket
import subprocess
from tempfile import TemporaryDirectory
import tarfile

from verify_monitoring_archive import verify

HISTORY = "qlume-servera-monitoring-history"
OWNER = "org.fangcunmount.monitoring.h06-operation"


def require(check, message):
    if not check:
        raise ValueError(message)


def digest(path):
    with path.open("rb") as value:
        return file_digest(value, "sha256").hexdigest()


def import_tree(
    archive, archive_sha, expected_files, *, helper, volume, operation, fixture, expiry
):
    engine = (
        ["docker"]
        if fixture
        else ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock"]
    )

    def docker(*args, timeout=30):
        return subprocess.check_output(
            [*engine, *args], timeout=timeout, text=True
        ).strip()

    def identity():
        (item,) = json.loads(docker("volume", "inspect", volume))
        require(
            (item.get("Labels") or {}).get(OWNER) == operation,
            "history volume owner label differs",
        )
        require(
            item["Driver"] == "local"
            and item["Scope"] == "local"
            and not item.get("Options"),
            "history volume must use the verified local Docker driver",
        )
        return dict(
            name=volume, created_at=item["CreatedAt"], mount_source=item["Mountpoint"]
        )

    before = identity()
    require(
        not docker("ps", "-aq", "--filter", f"volume={volume}"),
        "volume is referenced by a container",
    )
    (image,) = json.loads(docker("image", "inspect", helper))
    require(
        image["Id"] == helper
        and image["Os"] == "linux"
        and image["Architecture"] in ({"amd64", "arm64"} if fixture else {"amd64"}),
        "import helper identity or platform differs",
    )

    with TemporaryDirectory(prefix="m5-history-volume-") as tmp:
        root = Path(tmp)
        # The temporary tree is on the executor and the importer uses a read-only mount.
        root.chmod(0o755)
        with tarfile.open(archive, "r|gz") as source:
            seen = set()
            for member in source:
                relative = Path(member.name)
                require(
                    not relative.is_absolute() and ".." not in relative.parts,
                    "unsafe member",
                )
                if member.isdir():
                    continue
                name = relative.as_posix()
                require(
                    member.isfile() and name in expected_files and name not in seen,
                    "archive member changed",
                )
                seen.add(name)
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                expected = expected_files[name]
                require(member.size == expected["bytes"], "archive member size changed")
                h = sha256()
                with path.open("xb") as output, source.extractfile(member) as data:
                    for chunk in iter(lambda: data.read(1024 * 1024), b""):
                        output.write(chunk)
                        h.update(chunk)
                require(
                    h.hexdigest() == expected["sha256"], "archive member digest changed"
                )
        require(
            seen == expected_files.keys() and digest(archive) == archive_sha,
            "archive changed since validation",
        )
        require(
            identity() == before
            and not docker("ps", "-aq", "--filter", f"volume={volume}"),
            "volume identity or use changed during verification",
        )
        container = "m5-h06-import-" + secrets.token_hex(8)
        flags = (
            "run",
            "--rm",
            "--name",
            container,
            "--label",
            f"{OWNER}={operation}",
            "--pull",
            "never",
            "--network",
            "none",
            "--user",
            "0:0",
            "--mount",
            f"type=bind,src={root},dst=/archive,readonly",
            "--mount",
            f"type=volume,src={volume},dst=/prometheus,volume-nocopy",
            "--entrypoint",
            "/bin/sh",
            helper,
            "-ceu",
        )
        script = """
test -z "$(ls -A /prometheus)" || { echo 'history volume is nonempty' >&2; exit 1; }
cp -a /archive/. /prometheus/
chown -R 65534:65534 /prometheus
sync
cd /prometheus
find . -type f -exec sha256sum {} +
"""
        remaining = int((expiry - datetime.now(timezone.utc)).total_seconds())
        require(
            remaining >= 360,
            "import window has insufficient time for the bounded write and readback",
        )
        try:
            readback = docker(*flags, script, timeout=350)
        finally:
            # A timed-out Docker client can leave its helper running.
            status = subprocess.run(
                [
                    *engine,
                    "inspect",
                    "--type",
                    "container",
                    "--format",
                    '{{index .Config.Labels "' + OWNER + '"}}',
                    container,
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if status.returncode == 0:
                require(
                    status.stdout.strip() == operation,
                    "import helper ownership changed",
                )
                docker("rm", "-f", container, timeout=5)
            else:
                require(
                    "no such" in status.stderr.lower()
                    or "not found" in status.stderr.lower(),
                    "import helper state cannot be verified",
                )
    found = {}
    for line in readback.splitlines():
        value, name = line.split(None, 1)
        name = name.removeprefix("./")
        require(name not in found, "duplicate file readback")
        found[name] = value
    require(
        found == {name: item["sha256"] for name, item in expected_files.items()},
        "imported file digest differs",
    )
    require(
        identity() == before
        and not docker("ps", "-aq", "--filter", f"volume={volume}"),
        "history volume identity or ownership changed",
    )
    finished = datetime.now(timezone.utc)
    require(finished < expiry, "history import readback exceeded the approved window")
    return dict(
        volume=before,
        archive_members=len(found),
        fsynced=True,
        fixture=fixture,
        readback_verified_at=finished.isoformat(),
    )


def approved_inputs(b05_raw, approval_raw, fixture):
    b05, approval = map(json.loads, (b05_raw, approval_raw))
    b05_digest = sha256(b05_raw).hexdigest()
    require(
        b05["schema"] == "monitoring-h03-b05-restore/v1"
        and b05["rehearsal"] is fixture
        and b05["restored_from_verified_second_copy"] is True
        and b05["isolated_restore_verified"] is True
        and b05["production_mutation"] is False,
        "B05 must bind the same type of verified second-copy restore",
    )
    require(
        approval["schema"] == "monitoring-h06-history-import-approval/v1"
        and approval["fixture"] is fixture
        and approval["b05_sha256"] == b05_digest
        and approval["h03_operation_id"] == b05["operation_id"],
        "approval does not cover B05",
    )
    require(
        approval["operator"].strip()
        and approval["reviewer"].strip()
        and approval["operator"].strip() != approval["reviewer"].strip()
        and approval["decision_reference"].strip(),
        "named independent approval is required",
    )
    now = datetime.now(timezone.utc)
    expiry = datetime.fromisoformat(approval["expires_at"])
    start = datetime.fromisoformat(approval["starts_at"])
    require(
        start.utcoffset() is not None
        and expiry.utcoffset() is not None
        and start <= now < expiry,
        "import window is not open",
    )
    archive_sha = b05["h06_prometheus_archive_sha256"]
    require(
        re.fullmatch("[a-f0-9]{64}", archive_sha)
        and approval["archive_sha256"] == archive_sha
        and b05["prometheus"]["archive_sha256"] == archive_sha
        and b05["prometheus"]["isolated"] is True
        and b05["prometheus"]["wal_replay_complete"] is True,
        "archive fingerprint or WAL recovery differs",
    )
    operation, volume, helper = (
        approval[k] for k in ("operation_id", "volume", "helper")
    )
    require(
        re.fullmatch("[a-z0-9][a-z0-9-]{5,70}", operation)
        and re.fullmatch("sha256:[a-f0-9]{64}", helper),
        "exact operation and helper image are required",
    )
    return b05, operation, volume, helper, expiry


def main():
    require(__debug__, "run the history importer without Python optimization")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--b05", required=True, type=Path)
    parser.add_argument("--approved-import", required=True, type=Path)
    parser.add_argument("--max-bytes", required=True, type=int)
    parser.add_argument("--fixture", action="store_true")
    args = parser.parse_args()
    b05_raw = args.b05.read_bytes()
    approval_raw = args.approved_import.read_bytes()
    b05, operation, volume, helper, expiry = approved_inputs(
        b05_raw, approval_raw, args.fixture
    )
    archive_sha = b05["h06_prometheus_archive_sha256"]
    if args.fixture:
        require(
            volume == operation and volume.startswith("m5-h06-fixture-"),
            "fixture volume must be private to the run",
        )
    else:
        require(
            os.geteuid() == 0
            and socket.gethostname().split(".")[0].lower() == "servera"
            and volume == HISTORY,
            "production history import must target the named ServerA history volume",
        )
    index = verify(args.archive, "prometheus", args.max_bytes)
    require(
        index["archive_sha256"] == archive_sha
        and len(index["files"]) == b05["prometheus"]["archive_members_verified"],
        "archive does not match B05",
    )
    lock_name = (
        f"/tmp/{volume}.lock"
        if args.fixture
        else "/run/lock/qlume-servera-monitoring-history.lock"
    )
    fd = os.open(lock_name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = import_tree(
            args.archive,
            archive_sha,
            index["files"],
            helper=helper,
            volume=volume,
            operation=operation,
            fixture=args.fixture,
            expiry=expiry,
        )
    print(
        json.dumps(
            dict(
                schema="monitoring-h06-history-import/v1",
                h03_operation_id=b05["operation_id"],
                archive_sha256=archive_sha,
                restore_verified=True,
                b05_sha256=sha256(b05_raw).hexdigest(),
                approval_sha256=sha256(approval_raw).hexdigest(),
                operation_id=operation,
                **result,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
