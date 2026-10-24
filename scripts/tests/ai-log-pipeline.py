#!/usr/bin/env python3
"""Disposable Docker/mTLS/WAL acceptance. Never connects to production."""
import argparse
import json
import pathlib
import re
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

parser = argparse.ArgumentParser()
parser.add_argument('--outage-seconds', type=int, default=1800)
parser.add_argument('--collector', choices=['alloy', 'vector'], default='vector')
parser.add_argument('--crash', action='store_true')
parser.add_argument('--replace', action='store_true')
args = parser.parse_args()
assert 0 <= args.outage_seconds <= 3600
root = pathlib.Path(__file__).resolve().parents[2] / 'components/ai-logging'
prefix = 'ai-log-test-' + uuid.uuid4().hex[:8]
containers = []

def run(*cmd):
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f'{cmd[0]} {cmd[1]} failed: {result.stderr[-1200:]}')
    return result.stdout.strip()

def start(role, *opts):
    name = prefix + '-' + role
    run('docker', 'run', '-d', '--name', name, '--network', prefix, *opts)
    containers.append(name)
    return name

def port(name, value):
    return run('docker', 'port', name, value).split(':')[-1]

def wait_for(check, seconds=90):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            if check():
                return
        except (OSError, urllib.error.HTTPError, ValueError):
            pass
        time.sleep(1)
    raise AssertionError('Timed out waiting for isolated acceptance condition')

with tempfile.TemporaryDirectory(prefix=prefix) as folder:
    temp = pathlib.Path(folder)
    run('docker', 'network', 'create', prefix)
    try:
        run('openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
            '-subj', '/CN=Disposable-log-test-CA', '-keyout', str(temp/'ca.key'),
            '-out', str(temp/'ca-chain.crt'))
        for name, usage in [('logs', 'serverAuth'), ('collector', 'clientAuth')]:
            run('openssl', 'req', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN='+name,
                '-keyout', str(temp/(name+'.key')), '-out', str(temp/(name+'.csr')))
            ext = temp/(name+'.ext')
            ext.write_text('extendedKeyUsage='+usage+'\nsubjectAltName=DNS:gateway,IP:127.0.0.1\n')
            run('openssl', 'x509', '-req', '-in', str(temp/(name+'.csr')),
                '-CA', str(temp/'ca-chain.crt'), '-CAkey', str(temp/'ca.key'),
                '-CAcreateserial', '-days', '1', '-extfile', str(ext),
                '-out', str(temp/(name+'-fullchain.crt')))
        loki = start('loki', '--network-alias', 'loki', '--tmpfs', '/loki:uid=10001,gid=10001',
                     '-p', '127.0.0.1::3100', '-v', f'{root}/loki.yaml:/etc/loki/config.yaml:ro',
                     'grafana/loki:3.6.0', '-config.file=/etc/loki/config.yaml')
        base = 'http://127.0.0.1:' + port(loki, '3100/tcp')
        wait_for(lambda: urllib.request.urlopen(base+'/ready', timeout=2).status == 200)
        gateway = start('gateway', '--network-alias', 'gateway', '-p', '127.0.0.1::8443',
                        '-v', f'{root}/gateway.conf:/etc/nginx/nginx.conf:ro',
                        '-v', f'{temp}:/certs:ro', 'nginx:1.27.5')
        tls = ssl.create_default_context(cafile=str(temp/'ca-chain.crt'))
        endpoint = 'https://127.0.0.1:' + port(gateway, '8443/tcp') + '/loki/api/v1/push'
        def rejected():
            try:
                urllib.request.urlopen(urllib.request.Request(endpoint, data=b'{}'), context=tls, timeout=2)
            except urllib.error.HTTPError as error:
                return error.code in (400, 403)
            return False
        wait_for(rejected)
        print('PASS: no client certificate rejected', flush=True)
        if args.collector == 'alloy':
            config = (root/'config.alloy').read_text()
            config = re.sub(r'regex\s*= "/\(qs-ai[^\n]+', 'regex = "/'+prefix+'-fixture"', config, count=1)
            (temp/'config.alloy').write_text(config)
            collector = start('alloy', '-e', 'LOKI_WRITE_URL=https://gateway:8443/loki/api/v1/push',
                          '-v', '/var/run/docker.sock:/var/run/docker.sock:ro',
                          '-v', f'{temp}:/certs:ro', '-v', f'{temp}/config.alloy:/etc/alloy/config.alloy:ro',
                          'grafana/alloy:v1.11.2', 'run', '--storage.path=/tmp/wal', '/etc/alloy/config.alloy')
        else:
            config = (root/'vector.yaml').read_text()
            (temp/'logs'/'fixture').mkdir(parents=True)
            (temp/'vector-data').mkdir()
            (temp/'vector.yaml').write_text(config)
            def start_vector():
                return start('vector', '-e', 'LOKI_ENDPOINT=https://gateway:8443',
                              '-v', '/var/run/docker.sock:/var/run/docker.sock:ro',
                              '-v', f'{temp}:/certs:ro',
                              '-v', f'{temp}/vector.yaml:/etc/vector/vector.yaml:ro',
                              '-v', f'{temp}/logs:/logs:ro',
                              '-v', f'{temp}/vector-data:/var/lib/vector',
                              'timberio/vector:0.49.0-debian', '--config', '/etc/vector/vector.yaml')
            collector = start_vector()
        # Use the same event in stdout and native Docker json-file envelope.
        event = json.dumps({'schema_version':1, 'service':'qs-ai', 'event':'smoke',
                            'request_id':prefix, 'sequence':'SEQUENCE',
                            'timestamp':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
        event = event.replace('"SEQUENCE"', '%s')
        lines = ['sleep 12', 'n=0', 'while true; do',
                 "printf '"+event+"\\n' \"$n\""]
        if args.collector == 'vector':
            envelope = json.dumps({'log':event, 'stream':'stdout'})
            lines.append("printf '"+envelope+"\\n' \"$n\" >> /fixture-logs/events-json.log")
            lines.append("printf '%s\\n' '{\"log\":\"legacy-private-sentinel\"}' >> /fixture-logs/events-json.log")
        lines.extend(['echo legacy-private-sentinel', 'n=$((n+1))', 'sleep 2', 'done'])
        script = '\n'.join(lines)+'\n'
        (temp/'fixture.sh').write_text(script)
        fixture = start('fixture', *(['-v', f'{temp}/logs/fixture:/fixture-logs'] if args.collector == 'vector' else []), '--expose', '8000', '-v', f'{temp}/fixture.sh:/fixture.sh:ro',
                        '--entrypoint', '/bin/sh', 'grafana/alloy:v1.11.2', '/fixture.sh')
        since = str(time.time_ns()-60*10**9)
        def query():
            q = urllib.parse.urlencode({'query':'{service="qs-ai"} |= "'+prefix+'"',
                                        'start':since, 'end':str(time.time_ns()), 'limit':'5000'})
            data = json.load(urllib.request.urlopen(base+'/loki/api/v1/query_range?'+q, timeout=5))
            return [json.loads(v[1]) for item in data['data']['result'] for v in item['values']]
        wait_for(lambda: len(query()) >= 2)
        print('PASS: mTLS collector push and Loki query; starting outage', flush=True)
        run('docker', 'stop', '-t', '1', gateway)
        time.sleep(args.outage_seconds / 2)
        if args.replace:
            if args.collector != 'vector':
                raise ValueError('Replacement test requires durable Vector source')
            run('docker', 'kill', collector)
            run('docker', 'rm', collector)
            containers.remove(collector)
            run('docker', 'exec', fixture, 'mv', '/fixture-logs/events-json.log', '/fixture-logs/events-json.log.1')
            time.sleep(5)
            collector = start_vector()
        elif args.crash:
            run('docker', 'kill', collector)
            time.sleep(5)
            run('docker', 'start', collector)
        else:
            run('docker', 'restart', collector)
        time.sleep(args.outage_seconds / 2)
        run('docker', 'stop', '-t', '1', fixture)
        expected = {json.loads(line)['sequence'] for line in run('docker', 'logs', fixture).splitlines() if line.startswith('{')}
        run('docker', 'start', gateway)
        try:
            wait_for(lambda: expected <= {row['sequence'] for row in query()}, seconds=360)
        except AssertionError:
            actual = {row['sequence'] for row in query()}
            print(json.dumps({'expected_count':len(expected), 'received_count':len(actual),
                              'missing_sequences':sorted(expected-actual)}), flush=True)
            for name in [collector, gateway, loki]:
                logs = subprocess.run(['docker', 'logs', '--tail', '40', name], text=True, capture_output=True)
                print(name, logs.stdout, logs.stderr, flush=True)
            raise
        if args.collector == 'vector':
            assert all('timestamp' in row for row in query())
        all_query = urllib.parse.urlencode({'query':'{service="qs-ai"}', 'start':since,
                                            'end':str(time.time_ns()), 'limit':'5000'})
        with urllib.request.urlopen(base+'/loki/api/v1/query_range?'+all_query, timeout=5) as response:
            assert 'legacy-private-sentinel' not in response.read().decode()
        print(json.dumps({'passed':True, 'outage_seconds':args.outage_seconds,
                          'unique_events':len(expected), 'collector_restart':True}), flush=True)
    finally:
        for name in reversed(containers):
            subprocess.run(['docker','rm','-f',name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['docker','network','rm',prefix], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
