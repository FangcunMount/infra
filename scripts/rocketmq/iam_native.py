#!/usr/bin/env python3
"""Required IAM original-root/storage tests on an owned local Docker MySQL.

No supplied DSN, existing database, production endpoint or schema is accepted.
This is storage/HTTP evidence; half messages are explicit stored fixtures.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import shutil
import socket
import subprocess
import tempfile
import time


REQUIRED = {
    'TestM3TransactionSchemaNative', 'TestM3PlannedPolicyNative',
    'TestM3TransactionMaintenanceRoleModel', 'TestM3TransactionMaintenanceScope',
    'TestM3TransactionMaintenanceReviewerScope', 'TestM3TransactionMaintenanceConditionRetirement',
    'TestM3TransactionMaintenanceOperationsCatalog',
    'TestPlannedRoleModelPreviewApplyAndCompensation', 'TestPlannedScopeCopiesMappingAndPreservesCompensation',
    'TestPlannedReviewerScopeRetainsCredentialsOutsideFrozenInput',
    'TestPlannedRetirementPreservesReceiptAndRollbackBoundaries', 'TestPlannedCatalogPreviewsNoopAndRejectsDrift',
}


def run(argv, *, env=None, cwd=None, timeout=120):
    result = subprocess.run(argv, env=env, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('owned native operation failed; private output withheld')
    return result.stdout.strip()


def inspect_existing():
    identifiers = run(['docker', 'ps', '-aq']).split()
    if not identifiers:
        return []
    # Never inspect complete configs, credentials, environment or volume data.
    value = run(['docker', 'inspect', '--format',
                 '{{.Id}} {{.Name}} {{.State.StartedAt}} {{.RestartCount}} {{.State.Status}}', *identifiers])
    return sorted(value.splitlines())


def test_counts(raw):
    counts = {'pass': 0, 'fail': 0, 'skip': 0}
    passed = set()
    for line in raw.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        action, name = item.get('Action'), item.get('Test')
        if name and action in counts:
            counts[action] += 1
            if action == 'pass':
                passed.add(name)
    if counts['fail'] or counts['skip'] or not REQUIRED.issubset(passed):
        raise RuntimeError('required IAM native cases absent, failed or skipped')
    return counts, sorted(REQUIRED)


def live_test_group(group):
    # signal0 can return EPERM for an already dead/orphaned group on macOS.
    # Zombie processes own no running DB/RPC work; their supervisor owns reaping.
    result = subprocess.run(['ps', '-o', 'pid=,stat=', '-g', str(group)],
                            capture_output=True, text=True, timeout=5)
    if result.returncode == 1 and not result.stdout.strip():
        return False
    if result.returncode:
        raise RuntimeError('owned test process state unavailable')
    states = [line.split() for line in result.stdout.splitlines() if line.strip()]
    if any(len(row) != 2 or not row[0].isdigit() for row in states):
        raise RuntimeError('owned test process state unreadable')
    return any(not row[1].startswith('Z') for row in states)


def run_test_group(argv, *, cwd, env, stream, timeout):
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=stream,
                               stderr=subprocess.STDOUT, start_new_session=True)
    try:
        return process.wait(timeout=timeout)
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            # Permission errors are not completion proof. Inspect actual live
            # processes below and fail closed if any still owns work.
            pass
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            process.poll()
            if not live_test_group(process.pid):
                break
            time.sleep(.02)
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        process.wait(timeout=5)
        deadline = time.monotonic() + 2
        while live_test_group(process.pid):
            if time.monotonic() >= deadline:
                raise RuntimeError('owned Go test process group has not drained')
            time.sleep(.02)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iam', type=Path, required=True)
    parser.add_argument('--mysql-image', required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    source = args.iam.resolve()
    if not (source / 'go.mod').is_file() or run(['git', 'status', '--porcelain'], cwd=source):
        raise RuntimeError('exact clean IAM checkout required')
    if args.report.exists() or args.report.with_suffix('.private.log').exists():
        raise RuntimeError('native report/log destination already exists')
    parent = args.report.resolve().parent
    if parent.stat().st_uid != os.getuid() or parent.stat().st_mode & 0o077:
        raise RuntimeError('native report/log needs an owned0700 directory')
    sha = run(['git', 'rev-parse', 'HEAD'], cwd=source)
    image = run(['docker', 'image', 'inspect', args.mysql_image, '--format', '{{.Id}}'])
    before = inspect_existing()
    directory = Path(tempfile.mkdtemp(prefix='iam-m3-native-')); directory.chmod(0o700)
    project = 'iam-m3-native-' + secrets.token_hex(6)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
    password = secrets.token_hex(32)
    spec = {'services': {'mysql': {
        'image': image, 'restart': 'no', 'mem_limit': '512m', 'cpus': 1,
        'command': ['--innodb-buffer-pool-size=128M', '--max-connections=80'],
        'environment': {'MYSQL_ROOT_PASSWORD': password, 'MYSQL_ROOT_HOST': '%'},
        'ports': [f'127.0.0.1:{port}:3306'], 'tmpfs': ['/var/lib/mysql'],
        'networks': ['native'],
        'healthcheck': {'test': ['CMD-SHELL', 'MYSQL_PWD=$$MYSQL_ROOT_PASSWORD mysql -uroot -e "SELECT 1"'],
                        'interval': '3s', 'timeout': '3s', 'retries': 40}}}, 'networks': {'native': {}}}
    specfile = directory / 'compose.json'; specfile.write_text(json.dumps(spec)); specfile.chmod(0o600)
    compose = ['docker', 'compose', '-p', project, '-f', str(specfile)]
    proof = {'scope': 'IAM native storage/HTTP; stored half fixture, not Broker/system acceptance',
             'source_sha': sha, 'image': image, 'project': project, 'failed': 1,
             'source_clean_before': True, 'go_version': run(['go', 'version'])}
    failure = None
    try:
        run(compose + ['up', '-d', '--wait', '--wait-timeout', '150'], timeout=180)
        version = run(compose + ['exec', '-T', 'mysql', 'sh', '-c',
                      'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -Nse "SELECT VERSION()"'])
        proof['mysql_version'] = version
        if not re.fullmatch(r'8\.(?:0\.(?:36|44)|4\.\d+)(?:[-+].*)?', version):
            raise RuntimeError('required fixed MySQL8.0/8.4 runtime absent')
        dsn = f'root:{password}@tcp(127.0.0.1:{port})/?parseTime=true&multiStatements=true'
        env = dict(os.environ, GOWORK='off', GOFLAGS='-mod=readonly', IAM_M3_TEST_MYSQL_DSN=dsn)
        for prefix in ('ROLE_MODEL', 'SCOPE_MIGRATION', 'ACCOUNT_PROVISION', 'OPERATIONS_CATALOG'):
            env[prefix + '_REQUIRE_MYSQL'] = 'true'; env[prefix + '_MYSQL_DSN'] = dsn
        packages = ['./internal/pkg/migration', *['./internal/apiserver/maintenance/' + name for name in
                    ('rolemodel', 'conditionretire', 'scopemigrate', 'accountprovision', 'operationscatalog')]]
        argv = ['go', 'test', '-race', '-tags=integration', '-count=1', '-timeout=3m', '-json',
                *packages, '-run', '^Test(M3(TransactionSchemaNative|PlannedPolicyNative|TransactionMaintenance.*)|Planned.*)$']
        log = args.report.with_suffix('.private.log')
        descriptor = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            exit_code = run_test_group(argv, cwd=source, env=env, stream=stream, timeout=240)
        proof['test_process_group_drained'] = True
        raw = log.read_text(); proof['private_log_sha256'] = hashlib.sha256(log.read_bytes()).hexdigest()
        if exit_code:
            raise RuntimeError('required IAM native Go command failed; inspect owned0600 log')
        proof['tests'], proof['required_named_tests'] = test_counts(raw)
        proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source)
        if not proof['source_clean_after']:
            raise RuntimeError('IAM source changed during native acceptance')
        proof['failed'] = 0
    except Exception as error:
        # Only this harness's fixed messages go into the receipt.
        failure = type(error).__name__
        proof['failure_category'] = failure
    finally:
        try:
            run(compose + ['down', '--volumes', '--remove-orphans', '--timeout', '30'])
            remaining = run(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project=' + project])
            if remaining:
                raise RuntimeError('owned native containers remain')
            shutil.rmtree(directory)
            proof['cleanup'] = {'owned_containers_remaining': False, 'private_fixture_removed': True}
            proof['existing_containers_unchanged'] = inspect_existing() == before
            if not proof['existing_containers_unchanged']:
                raise RuntimeError('existing containers changed during native acceptance')
        except Exception:
            failure = 'cleanup_or_existing_runtime_changed'; proof['failed'] = 1
        descriptor = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(proof, stream, indent=2); stream.write('\n')
    if failure:
        raise RuntimeError('IAM native verification failed; see private local receipt')
    print(json.dumps({key: proof.get(key) for key in ('source_sha', 'mysql_version', 'tests', 'cleanup', 'existing_containers_unchanged')}))


if __name__ == '__main__':
    main()
