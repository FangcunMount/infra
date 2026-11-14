"""Start and stop the two pinned H04 containers within one approved window."""
from collections import Counter
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
import time

from render_cutoff import OPERATION, WINDOWS, units, utc_second

PROJECT = "qlume-servera-monitoring"
SERVICES = ("query-bridge", "servera-collector")
DISCOVERY = "qlume-servera-monitoring-discovery"
ID = r"[a-f0-9]{64}"


def invoke(executable, *args):
    return subprocess.check_output([executable, *args], timeout=35)


def docker(*args):
    return invoke("/usr/bin/docker", "--host", "unix:///var/run/docker.sock", *args)


def systemctl(*args):
    return invoke("/usr/bin/systemctl", *args)


def inspect(kind, key):
    (value,) = json.loads(docker(kind, "inspect", key))
    return value


def utc():
    return now().isoformat()


def now():
    return datetime.now(timezone.utc)


def start_container(cid, timeout):
    subprocess.check_output(
        [
            "/usr/bin/docker",
            "--host",
            "unix:///var/run/docker.sock",
            "container",
            "start",
            cid,
        ],
        timeout=timeout,
    )


def copy_receipt(path, payload):
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    folder = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(folder)
    finally:
        os.close(folder)


def validate_container(row, service, bound):
    if row["Id"] != bound["id"] or row["Image"] != bound["image"]:
        raise ValueError("candidate ID or image drift")
    labels = row["Config"]["Labels"]
    if (
        labels["com.docker.compose.project"] != PROJECT
        or labels["com.docker.compose.service"] != service
    ):
        raise ValueError("candidate project or service mismatch")
    if labels["com.docker.compose.config-hash"] != bound["compose_hash"]:
        raise ValueError("candidate Compose hash drift")
    if row["State"]["Status"] not in {"created", "running", "exited", "restarting"}:
        raise ValueError("candidate process state requires review")


def route_identity(route):
    return (
        route["Id"],
        route["Image"],
        route["State"]["StartedAt"],
        route["State"]["Running"],
    )


def inspect_plan(plan, docker_read, inspect_read):
    if set(plan["containers"]) != set(SERVICES):
        raise ValueError("candidate inventory mismatch")
    for item in plan["containers"].values():
        if (
            not re.fullmatch(ID, item["id"])
            or not re.fullmatch("sha256:" + ID, item["image"])
            or not re.fullmatch(ID, item["compose_hash"])
        ):
            raise ValueError("full candidate identity required")
    enumerated = (
        docker_read(
            "container",
            "ls",
            "-aq",
            "--no-trunc",
            "--filter",
            "label=com.docker.compose.project=" + PROJECT,
        )
        .decode()
        .splitlines()
    )
    ids = [plan["containers"][k]["id"] for k in SERVICES]
    if len(set(ids)) != 2 or Counter(enumerated) != Counter(ids):
        raise ValueError("candidate inventory drift")
    bridge, collector = [inspect_read("container", cid) for cid in ids]
    for service, row in zip(SERVICES, (bridge, collector), strict=True):
        validate_container(row, service, plan["containers"][service])
    if bridge["HostConfig"]["NetworkMode"] != "container:" + collector["Id"]:
        raise ValueError("query bridge is outside the expected collector namespace")
    volume = inspect_read("volume", plan["data_volume"])
    mounted = [
        item
        for item in collector["Mounts"]
        if item["Destination"] == "/prometheus" and item.get("Name") == volume["Name"]
    ]
    if len(mounted) != 1 or mounted[0]["Type"] != "volume" or not mounted[0]["RW"]:
        raise ValueError("candidate TSDB volume mismatch")
    route = inspect_read("container", "prometheus-route")
    query = plan["private_query_network"]
    if (
        query in route["NetworkSettings"]["Networks"]
        or query not in collector["NetworkSettings"]["Networks"]
    ):
        raise ValueError(
            "candidate private query network no longer matches the H04 phase"
        )
    return {
        "volume": volume,
        "route": route_identity(route),
        "containers": (bridge, collector),
    }


def stop(root, plan):
    before = inspect_plan(plan, docker, inspect)
    volume = before["volume"]
    payload = dict(
        operation=plan["operation"],
        started_at=utc(),
        sealed_inputs=True,
        stopped={},
        preserved={},
    )
    problems = []
    try:
        for command in (
            ("disable", "--now", DISCOVERY + ".timer"),
            ("stop", DISCOVERY + ".service"),
        ):
            try:
                systemctl(*command)
            except (OSError, subprocess.SubprocessError) as error:
                problems.append(f"discovery {command[-1]}: {error}")
        for service in SERVICES:
            bound = plan["containers"][service]
            try:
                row = inspect("container", bound["id"])
                validate_container(row, service, bound)
            except (KeyError, OSError, ValueError, subprocess.SubprocessError) as error:
                problems.append(f"{service} pre-stop identity check: {error}")
                continue
            if row["State"]["Status"] in {"running", "restarting"}:
                try:
                    docker("container", "stop", "--time", "15", bound["id"])
                except (OSError, subprocess.SubprocessError) as error:
                    problems.append(f"{service} stop command: {error}")
            try:
                observed = inspect("container", bound["id"])
                validate_container(observed, service, bound)
                state = observed["State"]
                payload["stopped"][service] = {
                    "id": bound["id"],
                    "status": state["Status"],
                    "exit": state["ExitCode"],
                    "oom_killed": state["OOMKilled"],
                    "state_error": bool(state["Error"]),
                }
                if state["Running"] or state["Status"] not in {"created", "exited"}:
                    problems.append(f"{service} still active")
                if state["ExitCode"] != 0 or state["OOMKilled"] or state["Error"]:
                    problems.append(f"{service} has an abnormal stop outcome")
            except (KeyError, OSError, ValueError, subprocess.SubprocessError) as error:
                problems.append(f"{service} stop outcome unknown: {error}")
        for key, query_identity in (
            (
                "candidate_tsdb",
                lambda: inspect("volume", volume["Name"]) == before["volume"],
            ),
            (
                "original_proxy",
                lambda: route_identity(inspect("container", "prometheus-route"))
                == before["route"],
            ),
        ):
            try:
                payload["preserved"][key] = query_identity()
            except (KeyError, OSError, ValueError, subprocess.SubprocessError) as error:
                problems.append(f"{key} readback unavailable: {error}")
            else:
                if not payload["preserved"][key]:
                    problems.append(f"{key} drift")
        if problems:
            raise RuntimeError("; ".join(problems))
    except (
        KeyError,
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as error:
        payload["error"] = str(error)
        raise
    finally:
        payload["finished_at"] = utc()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        copy_receipt(root / ("cutoff-" + stamp + ".json"), payload)


def require_timer(
    plan, digest, read_systemctl, unit_directory=Path("/etc/systemd/system")
):
    unit, service, timer = units(plan["operation"], plan["cutoff_utc"], digest)
    timer_file = unit_directory / (unit + ".timer")
    service_file = unit_directory / (unit + ".service")
    for path, expected in ((timer_file, timer), (service_file, service)):
        if path.is_symlink() or path.read_text() != expected:
            raise ValueError("installed cutoff unit differs from the sealed plan")
        raw = read_systemctl(
            "show",
            "--no-pager",
            "--property=LoadState,ActiveState,SubState,FragmentPath,DropInPaths,NeedDaemonReload,UnitFileState",
            path.name,
        ).decode()
        state = dict(line.split("=", 1) for line in raw.splitlines())
        if (
            state.get("LoadState") != "loaded"
            or state.get("FragmentPath") != str(path)
            or state.get("DropInPaths") != ""
            or state.get("NeedDaemonReload") != "no"
        ):
            raise ValueError("loaded cutoff unit differs from the sealed plan")
        phase = ("active", "waiting") if path == timer_file else ("inactive", "dead")
        if (state.get("ActiveState"), state.get("SubState")) != phase:
            raise ValueError("cutoff timer must be waiting before startup")
        if path == timer_file and state.get("UnitFileState") != "enabled":
            raise ValueError("cutoff timer must persist across reboot")


def close(root, plan, digest, reason):
    try:
        copy_receipt(
            root / "closed.json",
            dict(
                operation=plan["operation"],
                plan_sha256=digest,
                recorded_at=utc(),
                reason=reason,
            ),
        )
    except FileExistsError:
        # A prior attempt closed admission. Repeat exact stop and readback.
        pass
    stop(root, plan)


def startup_budget(earliest, latest):
    observed = now()
    remaining = (latest - observed).total_seconds()
    if observed < earliest or remaining <= 0:
        raise ValueError("outside approved startup interval")
    return min(20, remaining)


def read_docker_for_start(timeout, *args):
    return subprocess.check_output(
        ["/usr/bin/docker", "--host", "unix:///var/run/docker.sock", *args],
        timeout=timeout,
    )


def read_systemctl_for_start(timeout, *args):
    return subprocess.check_output(["/usr/bin/systemctl", *args], timeout=timeout)


def wait_ready(inspect_candidate, role, bound, earliest, latest):
    while True:
        observed = inspect_candidate("container", bound["id"])
        validate_container(observed, role, bound)
        state = observed["State"]
        if not state["Running"] or state["Status"] != "running":
            raise RuntimeError(f"{role} failed startup readback")
        if state.get("Health", {}).get("Status", "healthy") == "healthy":
            return
        time.sleep(min(1, startup_budget(earliest, latest)))


def start(root, plan, digest, earliest, latest):
    if (root / "closed.json").exists() or (root / "start-issued.json").exists():
        raise ValueError("operation already closed or startup already issued")
    startup_budget(earliest, latest)

    def docker_before_latest(*args):
        return read_docker_for_start(startup_budget(earliest, latest), *args)

    def inspect_before_latest(kind, key):
        (row,) = json.loads(docker_before_latest(kind, "inspect", key))
        return row

    before = inspect_plan(plan, docker_before_latest, inspect_before_latest)
    if any(row["State"]["Status"] != "created" for row in before["containers"]):
        raise ValueError("initial startup requires the two created containers")
    if any(
        row["HostConfig"]["RestartPolicy"]["Name"] != "no"
        for row in before["containers"]
    ):
        raise ValueError("H04 requires restart disabled on both candidates")
    require_timer(
        plan,
        digest,
        lambda *args: read_systemctl_for_start(startup_budget(earliest, latest), *args),
    )
    startup_budget(earliest, latest)
    payload = dict(operation=plan["operation"], plan_sha256=digest, issued_at=utc())
    copy_receipt(root / "start-issued.json", payload)
    try:
        for role in reversed(SERVICES):
            bound = plan["containers"][role]
            start_container(bound["id"], startup_budget(earliest, latest))
            wait_ready(inspect_before_latest, role, bound, earliest, latest)
        startup_budget(earliest, latest)
        copy_receipt(root / "started.json", dict(payload, verified_at=utc()))
    except (KeyError, OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        # A timed-out Docker client can leave an unknown daemon outcome. Close
        # admission first, read back both IDs, and leave the armed timer intact.
        close(root, plan, digest, "startup failed or outcome unknown")
        raise


def lifecycle(root, plan, digest, action):
    earliest, latest, cutoff = map(
        utc_second,
        (plan["window_start_utc"], plan["latest_start_utc"], plan["cutoff_utc"]),
    )
    if not earliest < latest < cutoff:
        raise ValueError("H04 window timestamps are out of order")
    if action not in {"start", "stop"}:
        raise ValueError("expected start or stop")
    lock = os.open(root / "cutoff.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if action == "start":
            start(root, plan, digest, earliest, latest)
        else:
            close(root, plan, digest, "cutoff or operator stop")
    finally:
        os.close(lock)


def main():
    if not __debug__:
        raise SystemExit("verification must run without Python optimization")
    os.umask(0o077)
    if len(sys.argv) not in {3, 4}:
        raise SystemExit("usage: stop-candidate.py STATE PLAN_SHA256 [start|stop]")
    root = Path(sys.argv[1])
    if (
        root != root.resolve()
        or root.parent != WINDOWS
        or os.geteuid() != 0
        or socket.gethostname().split(".")[0].lower() != "servera"
    ):
        raise SystemExit("root on ServerA and an absolute private state path required")
    if (
        not stat.S_ISDIR(root.lstat().st_mode)
        or root.stat().st_uid != 0
        or stat.S_IMODE(root.stat().st_mode) != 0o700
    ):
        raise SystemExit("root-only operation directory required")
    source = root / "stop-plan.json"
    if (
        source != source.resolve()
        or not stat.S_ISREG(source.lstat().st_mode)
        or source.stat().st_uid != 0
        or stat.S_IMODE(source.stat().st_mode) != 0o600
    ):
        raise SystemExit("root-only plan required")
    raw = source.read_bytes()
    if sha256(raw).hexdigest() != sys.argv[2]:
        raise SystemExit("stop plan SHA-256 mismatch")
    plan = json.loads(raw)
    if (
        plan["data_volume"] != PROJECT + "-data"
        or plan["private_query_network"] != PROJECT + "-query"
        or plan["operation"] != root.name
        or not re.fullmatch(OPERATION, plan["operation"])
    ):
        raise SystemExit("unexpected operation or TSDB volume")
    lifecycle(root, plan, sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else "stop")


if __name__ == "__main__":
    main()
