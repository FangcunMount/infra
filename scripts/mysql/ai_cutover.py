#!/usr/bin/env python3
"""Cut over a prepared AI release without running migrations or image cleanup."""
import argparse
import copy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

ROOT = Path('/opt/qs-ai')
CA = {'type': 'bind', 'source': '/data/infra/ssl/mysql/ca-chain.pem',
      'target': '/etc/qlume/mysql/ca-chain.pem', 'read_only': True,
      'bind': {'create_host_path': False}}
BASELINE = '7c71d1e95500aa20c3d82f57a7304578c8a794dd'
HEADS = ['0040_module_table_names']


def connection_only(previous, target):
    before, after = copy.deepcopy(previous), copy.deepcopy(target)
    old, new = before['services']['qs-ai'], after['services']['qs-ai']
    old_url = urlsplit(old['environment']['QS_AI_DATABASE_URL'])
    new_url = urlsplit(new['environment']['QS_AI_DATABASE_URL'])
    if old_url._replace(netloc='') != new_url._replace(netloc='') or (
        old_url.netloc.rsplit('@', 1)[0] != new_url.netloc.rsplit('@', 1)[0]
    ):
        raise ValueError('AI database credentials or database name changed')
    if new['environment'].get('QS_AI_DATABASE_TLS_MODE') != 'VERIFY_IDENTITY' or (
        new['environment'].get('QS_AI_DATABASE_TLS_CA_FILE') != CA['target']
    ):
        raise ValueError('AI MySQL TLS policy is invalid')
    if not re.fullmatch('[0-9a-f]{40}', new['environment'].get('MYSQL_TLS_CA_REF', '')):
        raise ValueError('AI CA commit is not pinned')
    for field in ('QS_AI_DATABASE_TLS_MODE', 'QS_AI_DATABASE_TLS_CA_FILE', 'MYSQL_TLS_CA_REF'):
        new['environment'].pop(field)
    new['environment']['QS_AI_DATABASE_URL'] = old['environment']['QS_AI_DATABASE_URL']
    new['image'] = old['image']
    mounts = new.get('volumes', [])
    if mounts.count(CA) != 1:
        raise ValueError('Expected one read-only MySQL CA mount')
    mounts.remove(CA)
    if before != after:
        raise ValueError('AI frozen release changes exceed the MySQL connection allowlist')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}-[0-9]+-[0-9]+', args.release):
        raise ValueError('An immutable prepared release is required')
    target = ROOT/'releases'/args.release
    spec = importlib.util.spec_from_file_location('deploy', target/'deploy.py')
    deploy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(deploy)
    os.umask(0o077)
    with deploy.global_deploy_lock(), (ROOT/'deploy.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = json.loads((ROOT/'state.json').read_text())
        previous = deploy.release_path(state['current'])
        if not previous.name.startswith(BASELINE+'-'):
            raise ValueError('Live AI source differs from the approved business baseline')
        deploy.schema_followup_guard()
        if (ROOT/'schema-maintenance/active-v2.json').exists():
            raise ValueError('An active schema followup prevents this migration')
        old = json.loads(deploy.run('old frozen contract', deploy.compose(previous, 'config', '--format', 'json')))
        new = json.loads(deploy.run('new frozen contract', deploy.compose(target, 'config', '--format', 'json')))
        connection_only(old, new)
        ref = new['services']['qs-ai']['environment']['MYSQL_TLS_CA_REF']
        deploy.run('MySQL pinned CA', ['python3', '/opt/infra/scripts/mysql/ca.py', 'verify', '--ref', ref])
        ca_manifest = json.loads(deploy.run('MySQL endpoint source', ['git', '-c',
                    'safe.directory=/opt/infra', '-C', '/opt/infra', 'show',
                    ref+':components/mysql-client/manifest.json']))
        url = urlsplit(new['services']['qs-ai']['environment']['QS_AI_DATABASE_URL'])
        if url.hostname != ca_manifest['public_endpoint'] or (url.port or 3306) != 3306:
            raise ValueError('AI endpoint differs from the verified public instance binding')
        manifest = json.loads((target/'manifest.json').read_text())
        if manifest['messaging_binding_sha256'] != json.loads((previous/'manifest.json').read_text())['messaging_binding_sha256']:
            raise ValueError('AI frozen message binding changed')
        deploy.loaded_image_binding(target)
        deploy.messaging_transition(previous, target)
        before = deploy.probe(target)
        if before['current'] != HEADS or before['expected'] != HEADS:
            raise ValueError('AI schema differs; no migration is allowed in this operation')
        actual = deploy.release_image_id(target, verify_identity=True)
        if not args.apply:
            print(json.dumps({'service': 'qs-ai', 'cutover': 'preflight_passed', 'release': target.name,
                              'image_id': actual, 'heads': HEADS, 'migrations_executed': False}))
            return
        deploy.stop_release(previous)
        try:
            deploy.verify(target)
            after = deploy.probe(target, True)
            if after['current'] != HEADS or after['expected'] != HEADS:
                raise ValueError('AI schema identity changed during cutover')
        except Exception:
            deploy.stop_release(target)
            deploy.verify(previous)
            raise
        deploy.write_json(target/'verification.json', {'phase': 'ready', 'database': after,
                          'image_id': actual, 'source_image_id': manifest['image_id'],
                          'migrations_executed': False})
        deploy.write_json(ROOT/'state.json', {'current': target.name, 'previous': previous.name})
        receipt = {'service': 'qs-ai', 'cutover': 'passed', 'release': target.name,
                   'previous_release': previous.name, 'image_id': actual,
                   'schema_heads': HEADS, 'migrations_executed': False, 'images_pruned': False}
        directory = ROOT/'mysql-public-tls'
        directory.mkdir(mode=0o700, exist_ok=True)
        deploy.write_json(directory/'ai-cutover.json', receipt)
        print(json.dumps(receipt))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'mysql_tls_ai_cutover': 'failed', 'error_type': type(error).__name__}))
        raise SystemExit(1) from None
