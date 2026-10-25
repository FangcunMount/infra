#!/usr/bin/env python3
"""Reviewed self-password change; no application SQL, grants or automatic retry.

Run only as an explicitly named step of the stopped-writer production window.
The single cutover coordinator must issue its first-start barrier beforehand.
Default mode is a read-only preview. Inputs and receipts remain private.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import stat


class Refused(RuntimeError):
    pass


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def private_read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.geteuid() or info.st_nlink != 1 or info.st_size > 16384):
            raise Refused('private reviewed input required')
        return stream.read()


def load(path, expected):
    raw = private_read(path)
    if not re.fullmatch('[0-9a-f]{64}', expected) or digest(raw) != expected:
        raise Refused('independent reviewed digest differs')
    p = json.loads(raw)
    keys = {'schema', 'operation_id', 'host', 'port', 'username', 'current_account',
            'server_uuid', 'server_version', 'old_password', 'new_password',
            'ca_file', 'directory', 'expires_at', 'coordinator_binding_sha256'}
    if set(p) != keys or p['schema'] != 'm3-mysql-self-credential/v1':
        raise Refused('exact credential operation required')
    for key in ('host', 'username', 'current_account', 'server_version', 'old_password'):
        if not isinstance(p[key], str) or not p[key] or len(p[key]) > 1024 or any(ord(c) < 32 for c in p[key]):
            raise Refused('bounded connection identity required')
    if (type(p['port']) is not int or not 1 <= p['port'] <= 65535
            or not re.fullmatch('[A-Za-z0-9_.-]{1,64}', p['operation_id'])
            or not re.fullmatch('[0-9a-f-]{36}', p['server_uuid'])
            or not p['server_version'].startswith('8.0.36')
            or not p['current_account'].startswith(p['username'] + '@')
            or not re.fullmatch('[0-9a-f]{64}', p['new_password'])
            or p['new_password'] == p['old_password']
            or not re.fullmatch('[0-9a-f]{64}', p['coordinator_binding_sha256'])):
        raise Refused('fixed source identity and independent new credential required')
    for key in ('directory', 'ca_file'):
        value = p[key]
        if (not isinstance(value, str) or not value.startswith('/')
                or str(Path(value)) != value or '..' in Path(value).parts):
            raise Refused('fixed absolute path required')
    directory = Path(p['directory'])
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.geteuid():
        raise Refused('original private operation directory required')
    now = datetime.now(timezone.utc)
    until = datetime.fromisoformat(p['expires_at'].replace('Z', '+00:00'))
    if until.tzinfo is None or not 0 < (until - now).total_seconds() <= 86400:
        raise Refused('current bounded operation window required')
    return p


def publish(p, name, value):
    path = Path(p['directory']) / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)


async def connect(p, password):
    import asyncmy
    context = ssl.create_default_context(cafile=p['ca_file'])
    return await asyncmy.connect(host=p['host'], port=p['port'], user=p['username'],
                                 password=password, ssl=context, connect_timeout=5,
                                 autocommit=True, charset='utf8mb4')


async def snapshot(connection, p):
    async with connection.cursor() as cursor:
        await cursor.execute('SELECT @@server_uuid,VERSION(),CURRENT_USER()')
        server_uuid, version, account = await cursor.fetchone()
        await cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
        cipher = await cursor.fetchone()
        if ((server_uuid, version, account) != (p['server_uuid'], p['server_version'], p['current_account'])
                or not cipher or not cipher[1]):
            raise Refused('authenticated server or TLS binding differs')
        await cursor.execute('SHOW GRANTS FOR CURRENT_USER()')
        grants = sorted(row[0] for row in await cursor.fetchall())
    return {'server_uuid': server_uuid, 'version': version, 'account': account,
            'tls': True, 'grants_sha256': digest(json.dumps(grants).encode())}


async def verify(p):
    import asyncmy
    new = await connect(p, p['new_password'])
    try:
        value = await snapshot(new, p)
    finally:
        new.close()
    try:
        old = await connect(p, p['old_password'])
    except asyncmy.errors.OperationalError as error:
        if not error.args or error.args[0] != 1045:
            raise Refused('old credential rejection not proven') from None
    else:
        old.close()
        raise Refused('old credential remains accepted')
    return value


async def perform(p, expected, action):
    async with asyncio.timeout(30):
        if action == 'verify':
            result = await verify(p)
            return dict(status='verified', read_only=True, old_credential_rejected=True, **result)
        connection = await connect(p, p['old_password'])
        try:
            before = await snapshot(connection, p)
            if action == 'preview':
                return dict(status='preview', read_only=True, **before)
            # The marker precedes the only password statement. Unknown outcomes
            # are inspected using --action verify; apply is never repeated.
            publish(p, 'rotation-issued.json', {'schema': 'm3-mysql-rotation-issued/v1',
                    'plan_sha256': expected, 'coordinator_binding_sha256': p['coordinator_binding_sha256']})
            reply = True
            try:
                async with connection.cursor() as cursor:
                    # SET PASSWORD preserves the account's existing plugin and
                    # permissions. REPLACE proves knowledge of the old password.
                    await cursor.execute('SET PASSWORD = %s REPLACE %s', (p['new_password'], p['old_password']))
            except Exception:
                reply = False
        finally:
            connection.close()
        after = await verify(p)
        if before != after:
            raise Refused('account identity or grants changed')
        result = dict(status='verified', read_only=False, set_reply_received=reply,
                      old_credential_rejected=True, **after)
        publish(p, 'rotation-verified.json', result)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--reviewed-sha256', required=True)
    parser.add_argument('--action', choices=('preview', 'apply', 'verify'), default='preview')
    parser.add_argument('--writers-excluded', action='store_true')
    parser.add_argument('--coordinated-start-already-issued', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.action == 'apply' and not (args.writers_excluded and args.coordinated_start_already_issued):
            raise Refused('explicit named writer exclusion and first-start boundary required')
        plan = load(args.plan, args.reviewed_sha256)
        if args.action == 'apply' and (Path(plan['directory']) / 'rotation-issued.json').exists():
            raise Refused('one-shot rotation already issued; inspect instead of retrying')
        result = asyncio.run(perform(plan, args.reviewed_sha256, args.action))
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        # Driver exceptions, SQL and parameters never enter logs. A nonzero
        # result after issuance is uncertain; it is not a rollback proof.
        print('{"status":"unavailable","credential_values_omitted":true}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
