#!/usr/bin/env python3
"""Run on the Mac mini; discover every cloud replica through restricted SSH."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def groups(items, gateway):
    out = []
    seen = set()
    for item in items:
        ip = str(ipaddress.ip_address(item['ip']))
        port = int(item['port'])
        job = item['job']
        if ipaddress.ip_address(ip) not in ipaddress.ip_network('172.20.0.0/24') or port not in {8000, 8080, 9080, 9092}:
            raise ValueError('unexpected endpoint')
        if job not in {'iam', 'qs-ai', 'qs-apiserver', 'qs-collection-server', 'qs-worker'}:
            raise ValueError('unexpected job')
        if (job == 'iam') != (port == 9080) or (job == 'iam' and item['instance'] != 'iam-apiserver:9080'):
            raise ValueError('unexpected IAM monitoring identity')
        key = (job, item['instance'])
        if key in seen:
            raise ValueError('duplicate monitored instance')
        seen.add(key)
        labels = {'job': job, 'instance': item['instance'], '__metrics_path__': f'/metrics/{ip}/{port}'}
        if 'component' in item:
            labels['component'] = item['component']
        out.append({'targets': [gateway], 'labels': labels})
    return out


def atomic_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


def discover(config):
    failed = False
    for source in config['sources']:
        target = Path(config['output']) / (source['name'] + '.json')
        try:
            result = subprocess.run([
                '/usr/bin/ssh', '-i', config['identity'], '-o', 'IdentitiesOnly=yes',
                '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                '-o', 'UserKnownHostsFile=' + config['known_hosts'], '-o', 'ConnectTimeout=10',
                '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=2',
                'root@' + source['host'],
            ], text=True, capture_output=True, timeout=35, check=True)
            value = groups(json.loads(result.stdout), config['gateway'])
            atomic_write(target, value)
            print(source['name'], 'targets', len(value), flush=True)
        except (subprocess.SubprocessError, ValueError, KeyError, OSError) as exc:
            failed = True
            print(source['name'], type(exc).__name__, file=sys.stderr, flush=True)
            # Expire old addresses rather than scrape a reused container IP indefinitely.
            if target.exists() and time.time() - target.stat().st_mtime > 120:
                atomic_write(target, [])
    return 1 if failed else 0


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--config', required=True)
    args = p.parse_args()
    sys.exit(discover(json.loads(Path(args.config).read_text())))
