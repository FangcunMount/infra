#!/usr/bin/env python3
"""Discover cloud replicas through the existing monitoring inventory helper."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
import time


LOCAL_INVENTORY = '/usr/local/sbin/infra-monitoring-discovery'
DIRECT_PORTS = {'iam': 9080, 'qs-ai': 8000, 'qs-apiserver': 8080,
                'qs-collection-server': 8080, 'qs-worker': 9092}


def groups(items, gateway):
    if not isinstance(items, list):
        raise ValueError('unexpected endpoint inventory')
    out = []
    seen = set()
    for item in items:
        ip = str(ipaddress.ip_address(item['ip']))
        port = int(item['port'])
        job = item['job']
        if ipaddress.ip_address(ip) not in ipaddress.ip_network('172.20.0.0/24') or port not in {8000, 8080, 9080, 9092}:
            raise ValueError('unexpected endpoint')
        if job not in DIRECT_PORTS:
            raise ValueError('unexpected job')
        if (job == 'iam') != (port == 9080) or (job == 'iam' and item['instance'] != 'iam-apiserver:9080'):
            raise ValueError('unexpected IAM monitoring identity')
        instance = item['instance']
        if not isinstance(instance, str) or not instance:
            raise ValueError('unexpected instance label')
        if 'component' in item and not isinstance(item['component'], str):
            raise ValueError('unexpected component label')
        key = (job, instance)
        if key in seen:
            raise ValueError('duplicate monitored instance')
        seen.add(key)
        labels = {'job': job, 'instance': instance}
        if 'component' in item:
            labels['component'] = item['component']
        if gateway is None:
            if port != DIRECT_PORTS[job]:
                raise ValueError('unexpected direct scrape port')
            address = f'{ip}:{port}'
        else:
            labels['__metrics_path__'] = f'/metrics/{ip}/{port}'
            address = gateway
        out.append({'targets': [address], 'labels': labels})
    return out


def atomic_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


def log_source(name, *fields, file=None):
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    print(timestamp, name, *fields, file=file, flush=True)


def refresh_source(config, source):
    target = Path(config['output']) / (source['name'] + '.json')
    direct = config.get('target_mode') == 'direct'
    try:
        if direct and source.get('transport') == 'local':
            command = [LOCAL_INVENTORY]
        else:
            command = [
                '/usr/bin/ssh', '-i', config['identity'], '-o', 'IdentitiesOnly=yes',
                '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                '-o', 'UserKnownHostsFile=' + config['known_hosts'], '-o', 'ConnectTimeout=10',
                '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=2',
                'root@' + source['host'],
            ]
        result = subprocess.run(command, text=True, capture_output=True, timeout=35, check=True)
        value = groups(json.loads(result.stdout), None if direct else config['gateway'])
        atomic_write(target, value)
        log_source(source['name'], 'targets', len(value))
    except (subprocess.SubprocessError, ValueError, TypeError, KeyError, OSError) as exc:
        log_source(source['name'], type(exc).__name__, file=sys.stderr)
        # Expire old addresses rather than scrape a reused container IP indefinitely.
        if target.exists() and time.time() - target.stat().st_mtime > 120:
            atomic_write(target, [])
        return False
    return True


def discover(config):
    sources = config['sources']
    names = {source['name'].casefold() for source in sources}
    if len(names) != len(sources):
        raise ValueError('duplicate discovery source name')
    mode = config.get('target_mode', 'gateway')
    if mode not in {'gateway', 'direct'}:
        raise ValueError('unexpected discovery target mode')
    transports = [source.get('transport', 'ssh') for source in sources]
    if mode == 'direct' and sorted(transports) != ['local', 'ssh']:
        raise ValueError('direct discovery requires one local and one SSH source')
    if mode == 'gateway' and (any(transport != 'ssh' for transport in transports) or not config['gateway']):
        raise ValueError('gateway discovery requires SSH sources and a gateway address')
    # Each source publishes its own file as soon as SSH completes.
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [pool.submit(refresh_source, config, source) for source in sources]
        results = [result.result() for result in pending]
    return int(not all(results))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--config', required=True)
    args = p.parse_args()
    sys.exit(discover(json.loads(Path(args.config).read_text())))
