"""Apply four frozen M2 configuration assets; preserve monitoring data volumes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time
import urllib.request

REVISION = 'bcb5a32501f39ae5b0463a9316c11e3c548f7a01'
ASSETS = {
    'rules/qs-event-system.yml': 'components/prometheus/rules/qs-event-system.yml',
    'rules/rocketmq-transactions.yml': 'components/prometheus/rules/rocketmq-transactions.yml',
    'grafana/dashboards/event-overview.json': 'components/grafana/dashboards/event-overview.json',
    'grafana/dashboards/event-transactions.json': 'components/grafana/dashboards/event-transactions.json',
}
REMOVED = 'grafana/dashboards/event-outbox.json'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def state(root):
    return {n: digest((root / n).read_bytes()) if (root / n).exists() else None
            for n in [*ASSETS, REMOVED]}


def state_hash(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def run(*args, content=None):
    p = subprocess.run(args, input=content, capture_output=True, timeout=30)
    if p.returncode:
        raise RuntimeError('Monitoring command failed; raw output withheld')
    return p.stdout


def api(path):
    with urllib.request.urlopen('http://127.0.0.1:19090' + path, timeout=5) as response:
        return json.load(response)


def guard(runtime):
    if socket.gethostname() != 'macmini-001.local' or not (runtime / 'docker-compose.yml').is_file():
        raise RuntimeError('Expected the inspected monitoring host/runtime')
    for name, destination, directory in [('prometheus', '/etc/prometheus/rules', 'rules'),
                                          ('grafana', '/var/lib/grafana/dashboards', 'grafana/dashboards')]:
        template = '{"project":{{json (index .Config.Labels "com.docker.compose.project")}},"mounts":{{json .Mounts}}}'
        row = json.loads(run('docker', 'inspect', '--format', template, name))
        mounts = [m for m in row['mounts'] if m['Destination'] == destination]
        if row['project'] != 'macmini-monitoring' or len(mounts) != 1 or mounts[0]['Source'].removeprefix('/host_mnt') != str(runtime / 'config' / directory):
            raise RuntimeError('Monitoring project/mount differs from inspected runtime')
    for url in ('http://127.0.0.1:19090/-/ready', 'http://127.0.0.1:13000/api/health'):
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.status != 200:
                raise RuntimeError('Existing monitoring service is not healthy')


def replace(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.m2m3-', delete=False) as output:
        temporary = Path(output.name)
        output.write(raw)
    try:
        temporary.chmod(0o644)  # Public configuration must remain readable by Grafana UID472.
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def apply(root, payload, expected, backup, reload):
    if state_hash(state(root)) != expected:
        raise RuntimeError('Monitoring assets changed since dry-run')
    before = {n: (root / n).read_bytes() if (root / n).exists() else None for n in [*ASSETS, REMOVED]}
    backup.mkdir(parents=True, exist_ok=False)
    for name, raw in before.items():
        if raw is not None:
            replace(backup / name, raw)
    (backup / 'state.json').write_text(json.dumps(state(root), indent=2) + '\n')
    try:
        for name, raw in payload.items():
            replace(root / name, raw)
        (root / REMOVED).unlink(missing_ok=True)
        reload()
    except Exception:
        for name, raw in before.items():
            if raw is None:
                (root / name).unlink(missing_ok=True)
            else:
                replace(root / name, raw)
        run('docker', 'kill', '--signal=HUP', 'prometheus')
        raise


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['dry-run', 'apply'])
    parser.add_argument('--expected-state', default='')
    args = parser.parse_args()
    runtime = Path.home() / 'infra-monitoring'
    guard(runtime)
    root = runtime / 'config'
    payload = {name: run('git', 'show', REVISION + ':' + source) for name, source in ASSETS.items()}
    provider = 'grafana/provisioning/dashboards/dashboards.yml'
    if (root / provider).read_bytes() != run('git', 'show', REVISION + ':components/' + provider):
        raise RuntimeError('Existing dashboard provisioning differs; inspect before changing files')
    for name, raw in payload.items():
        if name.endswith('.yml'):
            run('docker', 'exec', '-i', 'prometheus', '/bin/promtool', 'check', 'rules', '/dev/stdin', content=raw)
        elif json.loads(raw)['uid'] != Path(name).stem:
            raise RuntimeError('Dashboard UID differs from reviewed filename')
    current = state(root)
    report = dict(host=socket.gethostname(), source_sha=REVISION, before=current,
                  expected_state_sha256=state_hash(current), desired={n: digest(b) for n, b in payload.items()},
                  applied=False, direct_database_operations=False, dashboard_api_verified=False)
    if args.operation == 'apply':
        expected_rules = {Path(n).stem: set(re.findall(r'^\s+- (?:record|alert): (.+)$', b.decode(), re.M))
                          for n, b in payload.items() if n.endswith('.yml')}

        def reload():
            started = time.time()
            run('docker', 'kill', '--signal=HUP', 'prometheus')
            for _ in range(30):
                samples = api('/api/v1/query?query=prometheus_config_last_reload_success_timestamp_seconds').get('data', {}).get('result', [])
                if samples and float(samples[0]['value'][1]) >= started:
                    break
                time.sleep(1)
            else:
                raise RuntimeError('Prometheus did not confirm loading the new configuration')
            loaded = {g['name']: {r['name'] for r in g['rules']} for g in api('/api/v1/rules')['data']['groups']}
            if any(loaded.get(n) != rules for n, rules in expected_rules.items()):
                raise RuntimeError('Loaded Prometheus rules differ')
            time.sleep(20)  # Existing Grafana file provisioner polls every 10s.
            guard(runtime)

        backup = runtime / 'config-backups' / ('m2m3-' + str(time.time_ns()))
        apply(root, payload, args.expected_state, backup, reload)
        report.update(applied=True, after=state(root), backup=str(backup), prometheus_rules_verified=True,
                      dashboard_files_verified=True, dashboard_provisioning_config_unchanged=True)
    Path('monitoring-assets-receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit('Monitoring asset update failed: ' + type(error).__name__) from None
