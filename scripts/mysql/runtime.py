#!/usr/bin/env python3
"""Private, locked, one-container MySQL TLS cutover with retained rollback.

Plan/receipt files contain credentials and must never be committed or printed.
Only an image, MySQL binding and read-only CA mount may change.
"""
import argparse
import copy
import fcntl
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
from urllib.parse import quote, urlsplit, urlunsplit

CA = '/data/infra/ssl/mysql/ca-chain.pem'
CONTAINER_CA = '/etc/qlume/mysql/ca-chain.pem'
PREFIXES = {'qs-apiserver': 'QS_APISERVER_MYSQL_', 'iam-apiserver': 'IAM_APISERVER_MYSQL_'}


class Docker(http.client.HTTPConnection):
    def __init__(self):
        super().__init__('localhost', timeout=260)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect('/var/run/docker.sock')


def api(method, path, value=None):
    connection = Docker()
    try:
        connection.request(method, '/v1.45' + path,
                           body=None if value is None else json.dumps(value).encode(),
                           headers={'Content-Type': 'application/json'})
        response = connection.getresponse()
        body = response.read()
        if response.status >= 300 and response.status != 304:
            raise RuntimeError('Docker operation failed: HTTP ' + str(response.status))
        return json.loads(body) if body and response.status != 304 else None
    finally:
        connection.close()


def save(path, value):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())


def payload(before, image, host, port, ref, revision=None):
    name = before['Name'].lstrip('/')
    prefix = PREFIXES.get(name)
    if re.fullmatch('qs-worker-runtime-[123]', name):
        prefix = 'QS_WORKER_MYSQL_'
    if prefix is None and name != 'qs-ai':
        raise ValueError('Container is outside the migration scope')
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]+\.[a-z]+', host) or not 0 < port < 65536:
        raise ValueError('A public DNS endpoint is required')
    if not re.fullmatch('sha256:[0-9a-f]{64}', image) or not re.fullmatch('[0-9a-f]{40}', ref):
        raise ValueError('Immutable image and CA commit are required')
    config = copy.deepcopy(before['Config'])
    environment = dict(item.split('=', 1) for item in config['Env'])
    changes = {'MYSQL_TLS_CA_REF': ref}
    if prefix:
        changes.update({prefix+'HOST': host+':'+str(port), prefix+'TLS_MODE': 'VERIFY_IDENTITY',
                        prefix+'TLS_CA_FILE': CONTAINER_CA})
    else:
        url = urlsplit(environment['QS_AI_DATABASE_URL'])
        if url.scheme != 'mysql+asyncmy' or '@' not in url.netloc:
            raise ValueError('Unexpected AI database URL')
        # Keep byte-for-byte encoded credentials, database and URL options.
        changes['QS_AI_DATABASE_URL'] = urlunsplit(url._replace(
            netloc=url.netloc.rsplit('@', 1)[0]+'@'+host+':'+str(port)))
        changes.update(QS_AI_DATABASE_TLS_MODE='VERIFY_IDENTITY',
                       QS_AI_DATABASE_TLS_CA_FILE=CONTAINER_CA)
    environment.update(changes)
    config['Env'] = [key+'='+value for key, value in environment.items()]
    config['Image'] = image
    if revision is not None:
        if not re.fullmatch('[0-9a-f]{40}', revision):
            raise ValueError('Image source revision is missing')
        config.setdefault('Labels', {})['org.opencontainers.image.revision'] = revision
    hostconfig = copy.deepcopy(before['HostConfig'])
    binds = hostconfig.setdefault('Binds', []) or []
    if any(CONTAINER_CA in item for item in binds):
        raise ValueError('A CA mount already exists; inspect before replanning')
    binds.append(CA+':'+CONTAINER_CA+':ro')
    hostconfig['Binds'] = binds
    endpoints = {}
    for network, endpoint in before['NetworkSettings']['Networks'].items():
        endpoints[network] = {
            key: copy.deepcopy(endpoint[key]) for key in ('IPAMConfig', 'DriverOpts')
            if endpoint.get(key) is not None
        }
        endpoints[network]['Aliases'] = [alias for alias in endpoint.get('Aliases') or []
                                          if alias not in (before['Id'], before['Id'][:12])]
    return dict(config, HostConfig=hostconfig, NetworkingConfig={'EndpointsConfig': endpoints})


def public_endpoint(host, port):
    if port != 3306:
        raise ValueError('Production MySQL must use organization port 3306')
    addresses = [ipaddress.ip_address(item[4][0]) for item in
                 socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]
    if not addresses or not all(address.is_global for address in addresses):
        raise ValueError('MySQL endpoint must resolve only to public addresses')


def stable(container):
    return {key: container[key] for key in ('Id', 'Image', 'Config', 'HostConfig')}


def wait_healthy(name):
    deadline = time.monotonic()+240
    while time.monotonic() < deadline:
        state = api('GET', '/containers/'+name+'/json')['State']
        if not state['Running'] or state.get('Health', {}).get('Status') == 'unhealthy':
            raise RuntimeError('Replacement did not become healthy')
        if state.get('Health', {}).get('Status') == 'healthy':
            return
        if 'Health' not in state and re.fullmatch('qs-worker-runtime-[123]', name):
            probe = subprocess.run(['docker', 'exec', name, 'wget', '-qO-', '-T', '3',
                                    'http://127.0.0.1:9092/readyz'], capture_output=True)
            if probe.returncode == 0:
                snapshot = json.loads(probe.stdout)
                if snapshot.get('status') == 'ready':
                    return
        elif 'Health' not in state:
            raise RuntimeError('No recognized readiness policy for replacement')
        time.sleep(3)
    raise RuntimeError('Replacement health deadline exceeded')


def cutover(plan, directory):
    name, old = plan['name'], plan['before']
    public_endpoint(plan['host'], plan['port'])
    expected = payload(old, plan['image'], plan['host'], plan['port'], plan['ca_ref'], plan['revision'])
    if plan['payload'] != expected:
        raise ValueError('Migration exceeds the configuration allowlist')
    current = api('GET', '/containers/'+name+'/json')
    if stable(current) != stable(old) or not current['State']['Running']:
        raise ValueError('Runtime differs from the reviewed private plan')
    subprocess.run(['python3', str(Path(__file__).with_name('ca.py')), 'verify', '--ref', plan['ca_ref']], check=True)
    if not Path(CA).is_file():
        raise ValueError('CA mount is missing')
    new_image = api('GET', '/images/'+plan['payload']['Image']+'/json')
    if (new_image['Id'] != plan['payload']['Image']
        or new_image['Config']['Labels'].get('org.opencontainers.image.revision') != plan['revision']):
        raise ValueError('Image identity differs')
    retained = name+'-before-mysql-tls-'+str(int(time.time()))
    save(directory/'intent.json', {'name': name, 'retained': retained, 'old_id': old['Id']})
    api('POST', '/containers/'+old['Id']+'/stop?t=210')
    renamed = False
    created = None
    try:
        api('POST', '/containers/'+old['Id']+'/rename?name='+quote(retained))
        renamed = True
        created = api('POST', '/containers/create?name='+quote(name), plan['payload'])['Id']
        api('POST', '/containers/'+created+'/start')
        wait_healthy(name)
        save(directory/'applied.json', {'name': name, 'new_id': created, 'old_id': old['Id'],
                                       'retained': retained, 'image': new_image['Id']})
        # Retained stopped containers must not auto-start after a Docker restart.
        api('POST', '/containers/'+old['Id']+'/update', {'RestartPolicy': {'Name': 'no'}})
        print(json.dumps({'service': name, 'state': 'healthy', 'image': new_image['Id']}))
    except Exception:
        if created:
            api('POST', '/containers/'+created+'/stop?t=30')
            api('POST', '/containers/'+created+'/update', {'RestartPolicy': {'Name': 'no'}})
            api('POST', '/containers/'+created+'/rename?name='+quote(name+'-failed-mysql-tls-'+str(int(time.time()))))
        if renamed:
            api('POST', '/containers/'+old['Id']+'/rename?name='+quote(name))
        api('POST', '/containers/'+old['Id']+'/start')
        raise


def rollback(directory):
    plan = json.loads((directory/'plan.json').read_text())
    receipt = json.loads((directory/'applied.json').read_text())
    name = receipt['name']
    if api('GET', '/containers/'+name+'/json')['Id'] != receipt['new_id']:
        raise ValueError('Current runtime differs from this migration receipt')
    api('POST', '/containers/'+receipt['new_id']+'/stop?t=210')
    api('POST', '/containers/'+receipt['new_id']+'/rename?name='+quote(name+'-tls-rollback-'+str(int(time.time()))))
    api('POST', '/containers/'+receipt['new_id']+'/update', {'RestartPolicy': {'Name': 'no'}})
    api('POST', '/containers/'+receipt['old_id']+'/rename?name='+quote(name))
    api('POST', '/containers/'+receipt['old_id']+'/update', {'RestartPolicy': plan['before']['HostConfig']['RestartPolicy']})
    api('POST', '/containers/'+receipt['old_id']+'/start')
    wait_healthy(name)
    save(directory/'rolled-back.json', {'name': name, 'old_id': receipt['old_id']})
    print(json.dumps({'service': name, 'state': 'rolled_back'}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['plan', 'apply', 'rollback'])
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--name')
    parser.add_argument('--image')
    parser.add_argument('--host')
    parser.add_argument('--port', type=int, default=3306)
    parser.add_argument('--ca-ref')
    args = parser.parse_args()
    os.umask(0o077)
    args.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.directory.is_symlink() or args.directory.stat().st_mode & 0o077:
        raise ValueError('Migration directory must be private')
    lockpath = Path('/var/lib/fangcun-image-retention/deploy.lock')
    lockpath.parent.mkdir(parents=True, exist_ok=True)
    with lockpath.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'plan':
            public_endpoint(args.host, args.port)
            old = api('GET', '/containers/'+quote(args.name, safe='')+'/json')
            revision = api('GET', '/images/'+args.image+'/json')['Config']['Labels'].get('org.opencontainers.image.revision')
            if not revision:
                raise ValueError('Image has no immutable source revision')
            value = {'revision': revision, 'name': args.name, 'before': old, 'ca_ref': args.ca_ref,
                     'image': args.image, 'host': args.host, 'port': args.port,
                     'payload': payload(old, args.image, args.host, args.port, args.ca_ref, revision)}
            save(args.directory/'plan.json', value)
            print(json.dumps({'service': args.name, 'state': 'planned', 'image': args.image}))
        elif args.command == 'apply':
            cutover(json.loads((args.directory/'plan.json').read_text()), args.directory)
        else:
            rollback(args.directory)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Raw Docker/SQL errors may contain secrets. Private snapshots support diagnosis.
        print(json.dumps({'mysql_tls_migration': 'failed', 'error_type': type(error).__name__}))
        raise SystemExit(1) from None
