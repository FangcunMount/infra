"""Stage original MQ/JOSE files into a new immutable revision, never activate it.

The root operator supplies a reviewed plan and its exact SHA. Production paths,
roles and Unix identities are fixed here; the CLI has no destination override.
It does not install deployment sudo rules or change any active binding pointer.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile

BASE = Path('/var/lib/fangcun-m4-materials')
LEGACY_BASE = Path('/data/infra')
LOCK = Path('/var/lib/fangcun-image-retention/deploy.lock')
ROLES = {
    'iam': ('serverA', 'iam-messaging', 2000),
    'qs-api': ('serverA', 'qs-server-messaging', 2000),
    'ai': ('serverA', 'qs-ai-messaging', 10001),
    'worker': ('serverD', 'qs-worker-messaging', 2000),
}
REVISION = re.compile(r'm4-[a-z0-9][a-z0-9-]{0,59}')
HASH = re.compile(r'[0-9a-f]{64}')
JWK = re.compile(r'(qs\.sign|qs\.encrypt|ai\.sign|ai\.encrypt)(?:\.[a-z0-9][a-z0-9._-]{0,63})?\.json')
RECEIPT = 'material-receipt.json'


class Refused(RuntimeError):
    pass


def require(value, reason):
    if not value:
        raise Refused(reason)


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')) + '\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'duplicate_key')
        value[key] = item
    return value


def read_file(path, limit=1 << 20):
    """Never follow a symlink, accept a special file, or trust only its size."""
    path = Path(path)
    require(path.resolve() == path.absolute(), 'source_symlink')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit and before.st_mode & 0o022 == 0, 'source_metadata')
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    current = path.lstat()
    require(os.path.samestat(before, after) and os.path.samestat(after, current)
            and before.st_size == after.st_size == len(raw) <= limit
            and before.st_mtime_ns == after.st_mtime_ns == current.st_mtime_ns
            and before.st_mode == after.st_mode == current.st_mode, 'source_changed')
    return raw


def declarations(role, files):
    require(isinstance(files, list) and len(files) <= 8, 'file_count')
    wanted = {'rocketmq/credentials.json', 'rocketmq/ca.crt', 'rocketmq/routes.json'}
    if role == 'qs-api':
        wanted.add('rocketmq/mongo-credentials.json')
    keys = set()
    result = []
    for entry in files:
        require(isinstance(entry, dict) and set(entry) == {'source', 'target', 'sha256', 'bytes', 'source_uid', 'source_gid', 'source_mode'}, 'file_schema')
        source, target = entry['source'], entry['target']
        require(isinstance(source, str) and Path(source).is_absolute() and str(Path(source)) == source and '..' not in Path(source).parts, 'source_path')
        require(isinstance(target, str) and str(PurePosixPath(target)) == target and '\\' not in target and '..' not in PurePosixPath(target).parts, 'target_path')
        match = JWK.fullmatch(target)
        if match:
            require(role in ('qs-api', 'ai') and match[1] not in keys, 'jose_role')
            keys.add(match[1])
        else:
            require(target in wanted, 'target_path')
        require(isinstance(entry['sha256'], str) and HASH.fullmatch(entry['sha256']), 'file_hash')
        require(type(entry['bytes']) is int and 0 < entry['bytes'] <= (16384 if match else 1 << 20), 'file_size')
        require(all(type(entry[k]) is int and entry[k] >= 0 for k in ('source_uid', 'source_gid', 'source_mode')) and entry['source_mode'] <= 0o777, 'source_identity')
        private = target.endswith('credentials.json') or (match and match[1].startswith('ai.' if role == 'ai' else 'qs.'))
        require(not private or entry['source_mode'] & 0o007 == 0, 'private_source_permissions')
        result.append(entry.copy())
    require(len({r['target'] for r in result}) == len(result), 'duplicate_target')
    require({r['target'] for r in result if '/' in r['target']} == wanted, 'missing_transport')
    require(keys == ({'qs.sign', 'qs.encrypt', 'ai.sign', 'ai.encrypt'} if role in ('qs-api', 'ai') else set()), 'missing_jose')
    return sorted(result, key=lambda r: r['target'])


def validate(plan):
    require(isinstance(plan, dict) and set(plan) == {'schema', 'host', 'role', 'revision', 'source_receipt_sha256', 'files'}, 'plan_schema')
    require(plan['schema'] == 'm4-material-stage/v1' and isinstance(plan['role'], str) and plan['role'] in ROLES, 'role')
    require(plan['host'] == ROLES[plan['role']][0], 'host')
    require(isinstance(plan['revision'], str) and REVISION.fullmatch(plan['revision']), 'revision')
    require(isinstance(plan['source_receipt_sha256'], str) and HASH.fullmatch(plan['source_receipt_sha256']), 'source_receipt')
    return declarations(plan['role'], plan['files'])


def expected_receipt(plan, files, uid, gid, material_root):
    return dict(schema='m4-material-receipt/v1', plan_sha256=sha(encoded(plan)), role=plan['role'],
                host=plan['host'], revision=plan['revision'], source_receipt_sha256=plan['source_receipt_sha256'],
                material_root=str(material_root), uid=uid, gid=gid, file_mode='0440', directory_mode='0750',
                files=[{k: row[k] for k in ('target', 'sha256', 'bytes')} for row in files], activated=False)


def safe_directory(path, uid):
    require(path.is_dir() and not path.is_symlink() and path.resolve() == path.absolute(), 'directory_path')
    info = path.stat()
    require(info.st_uid == uid and info.st_mode & 0o022 == 0, 'directory_owner_or_mode')


def verify_directory(destination, receipt, uid, gid):
    safe_directory(destination, uid)
    actual = json.loads(read_file(destination / RECEIPT, 32768), object_pairs_hook=unique)
    require(actual == receipt, 'existing_revision_conflict')
    wanted = {row['target'] for row in receipt['files']} | {RECEIPT, 'rocketmq'}
    seen = set()
    for path in destination.rglob('*'):
        relative = str(path.relative_to(destination))
        require(relative in wanted and not path.is_symlink(), 'unexpected_file')
        seen.add(relative)
    require(seen == wanted, 'missing_file')
    for directory in (destination, destination / 'rocketmq'):
        safe_directory(directory, uid)
        info = directory.stat()
        require(stat.S_IMODE(info.st_mode) == 0o750 and info.st_gid == gid, 'published_directory_mode')
    for row in receipt['files'] + [{'target': RECEIPT, 'sha256': sha(encoded(receipt)), 'bytes': len(encoded(receipt))}]:
        path = destination / row['target']
        raw = read_file(path, 32768 if row['target'] == RECEIPT else 1 << 20)
        info = path.stat()
        require(info.st_uid == uid and info.st_gid == gid and stat.S_IMODE(info.st_mode) == 0o440, 'published_file_mode')
        require(len(raw) == row['bytes'] and sha(raw) == row['sha256'], 'published_file_hash')


def write_new(path, raw, uid, gid):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400), 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fchown(stream.fileno(), uid, gid)
        os.fchmod(stream.fileno(), 0o440)
        os.fsync(stream.fileno())


def verify_staged(plan, *, role, revision, root=BASE, uid=0, gid=None):
    """Read only the installed revision; callable under a parent's deploy lock.

    Source files are provenance in the reviewed plan, not a runtime dependency.
    No copy, mkdir, flock, pointer update or activation occurs in this path.
    Python-only root/UID/GID overrides keep tests inside their owned directory.
    """
    files = validate(plan)
    require(role in ROLES and plan['role'] == role and plan['revision'] == revision,
            'expected_role_or_revision')
    gid = ROLES[role][2] if gid is None else gid
    destination = root / ROLES[role][1] / 'versions' / revision
    receipt = expected_receipt(plan, files, uid, gid, root)
    for parent in (root.parent, root, destination.parent.parent, destination.parent):
        safe_directory(parent, uid)
    verify_directory(destination, receipt, uid, gid)
    return {'status': 'verified', 'role': role, 'host': plan['host'],
            'revision': revision, 'material_root': str(root),
            'receipt_sha256': sha(encoded(receipt)), 'activated': False,
            'read_only': True}


def stage(plan, *, apply=False, root=BASE, uid=0, gid=None, source_roots=None):
    """Test parameters are Python-only; the production CLI cannot override them."""
    files = validate(plan)
    role = plan['role']
    gid = ROLES[role][2] if gid is None else gid
    source_roots = (Path('/opt/fangcun-m3/releases'), LEGACY_BASE / ROLES[role][1] / 'versions', BASE / ROLES[role][1] / 'versions') if source_roots is None else tuple(source_roots)
    destination = root / ROLES[role][1] / 'versions' / plan['revision']
    receipt = expected_receipt(plan, files, uid, gid, root)
    require(not destination.is_symlink(), 'destination_symlink')
    safe_directory(root.parent, uid)
    # Validate every source before creating even a parent directory.
    bodies = {}
    for row in files:
        path = Path(row['source'])
        require(any(path.is_relative_to(p) and path != p for p in source_roots), 'source_scope')
        raw = read_file(path, 16384 if JWK.fullmatch(row['target']) else 1 << 20)
        require(len(raw) == row['bytes'] and sha(raw) == row['sha256'], 'source_hash')
        info = path.stat()
        require((info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (row['source_uid'], row['source_gid'], row['source_mode']), 'source_identity_changed')
        bodies[row['target']] = raw
    for parent in (root, destination.parent.parent, destination.parent):
        require(parent.resolve() == parent.absolute(), 'directory_path')
        if parent.exists() or parent.is_symlink():
            safe_directory(parent, uid)
    if destination.exists():
        verify_directory(destination, receipt, uid, gid)
        return {'status': 'already-staged', 'role': role, 'revision': plan['revision'], 'material_root': str(root), 'receipt_sha256': sha(encoded(receipt)), 'activated': False}
    if not apply:
        return {'status': 'ready', 'role': role, 'revision': plan['revision'], 'material_root': str(root), 'files': len(files), 'activated': False}
    created = []
    temporary = None
    try:
        for parent in (root, destination.parent.parent, destination.parent):
            if not parent.exists():
                parent.mkdir(mode=0o750)
                created.append(parent)
                os.chown(parent, uid, gid)
                os.chmod(parent, 0o750)
            safe_directory(parent, uid)
        temporary = Path(tempfile.mkdtemp(prefix='.m4-stage-', dir=destination.parent))
        os.chown(temporary, uid, gid)
        temporary.chmod(0o750)
        (temporary / 'rocketmq').mkdir(mode=0o750)
        os.chown(temporary / 'rocketmq', uid, gid)
        (temporary / 'rocketmq').chmod(0o750)
        for target, raw in bodies.items():
            write_new(temporary / target, raw, uid, gid)
        write_new(temporary / RECEIPT, encoded(receipt), uid, gid)
        verify_directory(temporary, receipt, uid, gid)
        for row in files:
            require(sha(read_file(Path(row['source']))) == row['sha256'], 'source_changed_before_publish')
        require(not destination.exists() and not destination.is_symlink(), 'revision_appeared')
        # Existing ancestors are root-owned/non-writable; the original deploy
        # lock serializes publishers. An existing revision is never replaced.
        os.rename(temporary, destination)
        temporary = None
        descriptor = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        verify_directory(destination, receipt, uid, gid)
        return {'status': 'staged', 'role': role, 'revision': plan['revision'], 'material_root': str(root), 'files': len(files), 'receipt_sha256': sha(encoded(receipt)), 'activated': False}
    finally:
        if temporary is not None:
            shutil.rmtree(temporary)  # Only this call's private temporary directory.
        for parent in reversed(created):
            try:
                parent.rmdir()  # Only owned, still-empty parents; never a published revision.
            except OSError:
                pass


@contextmanager
def deployment_lock():
    with os.fdopen(os.open(LOCK, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK), 'r+b') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and stat.S_IMODE(before.st_mode) == 0o666, 'deployment_lock_metadata')
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(os.path.samestat(before, LOCK.lstat()), 'deployment_lock_replaced')
        yield
        require(os.path.samestat(before, LOCK.lstat()), 'deployment_lock_replaced')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--host', choices=('serverA', 'serverD'), required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--verify-staged', action='store_true')
    parser.add_argument('--expect-role', choices=tuple(ROLES))
    parser.add_argument('--expect-revision')
    args = parser.parse_args()
    require(os.geteuid() == 0 and HASH.fullmatch(args.expected_sha256), 'root_and_reviewed_plan_required')
    raw = read_file(args.plan, 32768)
    require(sha(raw) == args.expected_sha256, 'plan_hash')
    plan = json.loads(raw, object_pairs_hook=unique)
    require(plan['host'] == args.host, 'host')
    if args.verify_staged:
        require(args.expect_role is not None and args.expect_revision is not None,
                'explicit_verification_identity_required')
        print(json.dumps(verify_staged(plan, role=args.expect_role,
                                      revision=args.expect_revision), sort_keys=True))
        return
    require(args.expect_role is None and args.expect_revision is None,
            'verification_identity_without_mode')
    with deployment_lock():
        print(json.dumps(stage(plan, apply=args.apply), sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('M4 material staging refused; original assets retained') from None
