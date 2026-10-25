#!/usr/bin/env python3
"""Fixed SSH command: return monitoring endpoints, never environment/secrets."""
import ipaddress
import json
import subprocess


def endpoints(containers):
    result = []
    for c in containers:
        if not c['State']['Running']:
            continue
        name = c['Name'].lstrip('/')
        labels = c['Config'].get('Labels') or {}
        if name == 'iam-apiserver':
            job, port, instance = 'iam', 9080, 'iam-apiserver:9080'
        elif name == 'qs-ai':
            job, port, instance = 'qs-ai', 8000, 'qs-ai-api:8000'
        elif labels.get('prometheus.scrape') == 'true':
            job = labels.get('prometheus.job', '')
            port = int(labels.get('prometheus.metrics_port', '0'))
            instance = name
        else:
            continue
        ip = c['NetworkSettings']['Networks'].get('infra-network', {}).get('IPAddress')
        if not ip or ipaddress.ip_address(ip) not in ipaddress.ip_network('172.20.0.0/24'):
            raise ValueError('monitored container has no expected overlay address')
        if job not in {'iam', 'qs-ai', 'qs-apiserver', 'qs-collection-server', 'qs-worker'} or port not in {8000, 8080, 9080, 9092}:
            raise ValueError('unexpected monitoring job or port')
        if job == 'iam' and (name != 'iam-apiserver' or port != 9080):
            raise ValueError('unexpected IAM monitoring identity')
        if job != 'iam' and port == 9080:
            raise ValueError('IAM port is not a general monitoring endpoint')
        if job == 'qs-apiserver':
            instance = 'qs-apiserver:8080'
        elif job == 'qs-collection-server':
            instance = f'{ip}:{port}'
        item = {'ip': ip, 'port': port, 'job': job, 'instance': instance}
        if job == 'qs-worker':
            item['component'] = labels.get('prometheus.component', 'qs-worker')
        result.append(item)
    return result


if __name__ == '__main__':
    ids = subprocess.check_output(['docker', 'ps', '-q'], text=True, timeout=10).split()
    cs = json.loads(subprocess.check_output(['docker', 'inspect', *ids], text=True, timeout=10)) if ids else []
    print(json.dumps(endpoints(cs), separators=(',', ':')))
