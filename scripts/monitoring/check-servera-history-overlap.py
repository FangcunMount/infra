"""Check that an overlapping history backup preserves raw samples at the local TSDB boundary."""

import json
import os
from pathlib import Path
import secrets
import subprocess
from tempfile import TemporaryDirectory
import time
from urllib.parse import urlencode


MONITORING = Path(__file__).resolve().parents[2] / "deploy/serverA/monitoring"
IMAGE = os.environ.get("SERVERA_MONITORING_PROMTOOL_IMAGE", "prom/prometheus:v2.54.1")
SERIES = 'handoff_sample{owner="qs.mysql"}'
LABEL = "org.fangcunmount.monitoring.history-overlap"


def docker(*args, check=True):
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=30)


def start(name, label, network, store, config, port):
    return docker("run", "-d", "--name", name, "--label", label, "--pull", "never", "--network", network,
                  "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                  "-v", f"{store}:/prometheus", "-v", f"{config}:/etc/prometheus/prometheus.yml:ro", IMAGE,
                  "--config.file=/etc/prometheus/prometheus.yml", "--storage.tsdb.path=/prometheus",
                  "--storage.tsdb.retention.time=30d", f"--web.listen-address=127.0.0.1:{port}").stdout.strip()


def remove(name, label):
    info = docker("inspect", "--type", "container", "--format", '{{index .Config.Labels "' + LABEL + '"}}',
                  name, check=False)
    if info.returncode == 0:
        assert f"{LABEL}={info.stdout.strip()}" == label
        docker("rm", "-v", "-f", name)


def query(container, path, parameters):
    url = "http://127.0.0.1:9090/api/v1/" + path + "?" + urlencode(parameters)
    reply = json.loads(docker("exec", container, "/bin/wget", "-T", "8", "-qO-", url).stdout)
    assert reply["status"] == "success" and not reply.get("warnings") and not reply.get("infos")
    assert reply["data"]["resultType"] == "matrix"
    row, = reply["data"]["result"]
    assert row["metric"] == {"__name__": "handoff_sample", "owner": "qs.mysql"}
    return {int(stamp): int(value) for stamp, value in row["values"]}


def write_block(work, role, samples):
    store = work / role
    store.mkdir()
    store.chmod(0o777)
    file = work / f"{role}.om"
    file.write_text("# TYPE handoff_sample gauge\n" + "".join(
        f"{SERIES} {value} {stamp}\n" for stamp, value in samples.items()
    ) + "# EOF\n")
    file.chmod(0o644)
    args = ("/bin/promtool", IMAGE, "tsdb", "create-blocks-from", "openmetrics", f"/fixture/{file.name}", f"/fixture/{role}")
    docker("run", "--rm", "--pull", "never", "--network", "none", "-v", f"{work}:/fixture", "--entrypoint", *args)
    return store


def main():
    fixture = "m5-history-" + secrets.token_hex(6)
    label = f"{LABEL}={fixture}"
    candidate, history = fixture + "-candidate", fixture + "-history"
    boundary = int(time.time()) // 15 * 15 - 120
    old = {stamp: 100 + i for i, stamp in enumerate(range(boundary - 90, boundary + 31, 15))}
    new = {stamp: 200 + i for i, stamp in enumerate(range(boundary, boundary + 76, 15))}
    early = {stamp: value for stamp, value in old.items() if stamp <= boundary - 45}
    expected = {**old, **new}

    with TemporaryDirectory(prefix=fixture) as directory:
        work = Path(directory)
        work.chmod(0o755)
        candidate_config = work / "candidate.yml"
        config = (MONITORING / "history/prometheus.yml").read_text()
        candidate_config.write_text("scrape_configs: []\n" + config[config.index("remote_read:"):])
        candidate_config.chmod(0o644)
        history_config = work / "history.yml"
        history_config.write_bytes((MONITORING / "history/history-prometheus.yml").read_bytes())
        history_config.chmod(0o644)
        stores = {name: write_block(work, name, samples) for name, samples in
                  (("early", early), ("old", old), ("new", new))}

        def wait(port):
            for _ in range(20):
                result = docker("exec", candidate, "/bin/wget", "-T", "4", "-qO-",
                                f"http://127.0.0.1:{port}/-/ready", check=False)
                if result.returncode == 0:
                    return
                time.sleep(1)
            raise RuntimeError(f"fixture port {port} did not become ready")

        def raw_samples():
            return query(candidate, "query", dict(query=SERIES + "[180s]", time=max(new)))

        try:
            main_id = start(candidate, label, "none", stores["new"], candidate_config, 9090)
            wait(9090)
            start(history, label, "container:" + main_id, stores["early"], history_config, 19092)
            wait(19092)
            before = raw_samples()
            assert before == {**early, **new}
            gaps = set(expected) - before.keys()
            assert gaps == {boundary - 30, boundary - 15}
            chart = query(candidate, "query_range", dict(query=SERIES, start=min(old), end=max(new), step=15))
            assert all(chart[stamp] == early[max(early)] for stamp in gaps)
            remove(history, label)

            start(history, label, "container:" + main_id, stores["old"], history_config, 19092)
            wait(19092)
            after = raw_samples()
            assert after == expected
            shared = old.keys() & new.keys()
            assert len(shared) == 3 and all(after[stamp] == new[stamp] for stamp in shared)
        finally:
            remove(history, label)
            remove(candidate, label)
            assert not docker("ps", "-aq", "--filter", "label=" + label).stdout.strip()

    print(json.dumps(dict(expected=len(expected), before_overlap=len(before), after_overlap=len(after),
                          masked_gap_timestamps=sorted(gaps), overlapping_local_samples=len(shared),
                          network_disabled=True, fixture_removed=True), indent=2))


if __name__ == "__main__":
    main()
