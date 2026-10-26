#!/usr/bin/env python3
"""Current payload/receipt MySQL+mTLS gate. No Broker or production claim."""
import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib
import xml.etree.ElementTree as ET

from ai_admission_acceptance import validate_host_runtime, validate_host_sdk_lock
from ai_finalization_characterization import diagnostics

FILE = 'tests/integration/rocketmq_payload_host.py'
CASES = frozenset(('large_reference_wire', 'uncommitted_current_payload_hidden',
    'committed_current_body_exact', 'committed_business_archive_witness',
    'rolled_back_current_body_hidden', 'no_new_publish_outbox',
    *('reference_' + k for k in ('producer', 'destination', 'organization_id', 'body_sha256', 'body_length')),
    'wrong_workload_denied', 'missing_certificate_denied', 'missing_authority_unavailable',
    'restored_authority_first_body', 'receipt_atomic_6', 'receipt_atomic_7',
    'receipt_held_stored', 'receipt_conflict', 'receipt_concurrent', 'rpc_channels_and_servers_closed'))
TESTS = frozenset((
    *('test_current_payload_original_root_mtls_visibility_and_first_body[' + v + ']' for v in ('True', 'False')),
    *('test_current_payload_mtls_reference_mismatch_diagnostics[' + k + '-' + v + ']'
      for k, v in (('producer', 'qs-server'), ('destination', 'other'), ('organization_id', '999'),
                   ('body_sha256', 'b' * 64), ('body_length', '1'))),
    *('test_current_payload_mtls_wrong_or_missing_client_is_denied[' + k + ']' for k in ('other', 'missing')),
    'test_current_payload_missing_exact_witness_is_unavailable_without_fallback',
    *('test_current_receipt_original_root_atomicity_and_first_receipt[' + k + ']' for k in ('6', '7')),
    'test_current_receipt_held_then_stored_does_not_reopen_delivery',
    'test_current_receipt_conflict_and_digest_do_not_change_business',
    'test_current_receipt_concurrent_duplicate_retains_one_result'))
FLAGS = frozenset(('system_login_not_claimed', 'paired_qs_business_not_claimed',
    'broker_transaction_gate_not_claimed', 'real_database_network_fault_not_claimed',
    'synthetic_command_binding'))
FIELDS = FLAGS | {'cases', 'passed', 'failed', 'skipped', 'rpc_servers', 'root', 'sdk', 'client', 'python'}
MARKER = 'M3_AI_CURRENT_PAYLOAD_RECEIPT '
SDK = dict(sdk_version='0.4.0a2',
    sdk_url='https://github.com/FangcunMount/reliable-messaging/releases/download/python/v0.4.0a2/fangcun_reliable_messaging-0.4.0a2-py3-none-any.whl',
    sdk_sha256='570822f9ed51eee25001624858d30b7433468eb7da59e34348289c50a37cabb2')


def parse_native(output, junit, *, sdk_version="0.4.0a2"):
    if sdk_version not in {"0.4.0a2", "0.4.0"}:
        raise ValueError("exact reviewed SDK profile required")
    lines = [line.split(MARKER, 1)[1] for line in output.splitlines() if MARKER + '{' in line]
    if len(lines) != 1:
        raise ValueError('one exact current payload receipt required')
    value = json.loads(lines[0])
    if (not isinstance(value, dict) or set(value) != FIELDS
            or value['cases'] != {k: True for k in CASES}
            or any(v is not True for v in value['cases'].values())
            or any(type(value[k]) is not int for k in ('passed', 'failed', 'skipped'))
            or (value['passed'], value['failed'], value['skipped']) != (len(CASES), 0, 0)
            or value['rpc_servers'] != {'started': 10, 'closed': 10}
            or any(type(v) is not int for v in value['rpc_servers'].values())
            or any(value[k] is not True for k in FLAGS)
            or value['root'] != 'original_mysql_sqlalchemy'
            or (value['sdk'], value['client']) != (sdk_version, '5.1.2')
            or not isinstance(value['python'], str)
            or re.fullmatch(r'3\.(?:11|13)\.\d{1,3}', value['python']) is None):
        raise ValueError('current payload proof incomplete or outside scope')
    cases = list(ET.fromstring(junit).iter('testcase'))
    if (len(cases) != len(TESTS) or {c.get('name') for c in cases} != TESTS
            or any(c.get('classname') != 'tests.integration.rocketmq_payload_host' for c in cases)
            or any(c.find(tag) is not None for c in cases for tag in ('error', 'failure', 'skipped'))):
        raise ValueError('required current payload native cases failed, skipped or absent')
    return dict(receipt=value, passed=len(TESTS), failed=0, skipped=0, tests=sorted(TESTS))


def validate_mysql_binding(raw):
    ports = json.loads(raw)
    selected = ports.get('3306/tcp')
    if selected != [{'HostIp': '127.0.0.1', 'HostPort': '3306'}]:
        raise ValueError('owned MySQL must publish only the required loopback port')
    return selected


async def storage_receipt(url):
    from sqlalchemy import func, select, text
    from sqlalchemy.ext.asyncio import create_async_engine
    from qs_ai.infrastructure.persistence.mysql.messaging import inbox, outbox
    from qs_ai.infrastructure.persistence.mysql.schema import (
        artifacts, jobs, model_calls, questions, result_outbox, runs, sessions,
    )
    from qs_ai.infrastructure.persistence.mysql.transaction_schema import (
        archive, binding, event_receipts, execution, request, witness,
    )
    engine = create_async_engine(url, hide_parameters=True)
    try:
        async with engine.connect() as db:
            counts = {t.name: int(await db.scalar(select(func.count()).select_from(t)))
                      for t in (artifacts, jobs, model_calls, questions, result_outbox, runs,
                                sessions, inbox, outbox, archive, binding, event_receipts,
                                execution, request, witness)}
            return dict(mysql_version=await db.scalar(text('SELECT VERSION()')), remaining_rows=counts)
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--expected-source', required=True)
    parser.add_argument('--mysql', choices=('8.0.36', '8.0.44', '8.4.11'), required=True)
    parser.add_argument('--python', choices=('3.11', '3.13'), required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--stable', action='store_true', help='Use the M4 stable published SDK profile')
    args = parser.parse_args()
    from paired_acceptance import SDK_PYTHON_VERSION, SDK_SHA256
    sdk = dict(sdk_version=SDK_PYTHON_VERSION, sdk_url=f"https://github.com/FangcunMount/reliable-messaging/releases/download/python/v{SDK_PYTHON_VERSION}/fangcun_reliable_messaging-{SDK_PYTHON_VERSION}-py3-none-any.whl", sdk_sha256=SDK_SHA256) if args.stable else SDK
    os.umask(0o077)
    source = args.source.resolve()
    report = dict(version=1, batch='T19-current-payload-original-MySQL-and-mTLS',
        passed=0, failed=1, skipped=0, production_changed=False,
        scope='current archive RPC and ACK roots; controlled command bindings, no Broker/paired QS/system or database network-fault acceptance',
        service_teardown_owned_by_github=True)
    private = tempfile.TemporaryDirectory(prefix='ai-t19-current-payload-')
    directory, phase, code = Path(private.name), 'source', 1
    directory.chmod(0o700)
    try:
        sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
        if sha != args.expected_source or re.fullmatch('[0-9a-f]{40}', sha) is None:
            raise ValueError('exact source required')
        if subprocess.check_output(['git', 'status', '--porcelain'], cwd=source, text=True).strip():
            raise ValueError('clean source required')
        sys.path.insert(0, str(source / 'src'))
        import qs_ai
        import reliable_messaging
        if not Path(qs_ai.__file__).resolve().is_relative_to(source / 'src'):
            raise ValueError('exact host source import required')
        if '.'.join(sys.version.split()[0].split('.')[:2]) != args.python:
            raise ValueError('exact Python compatibility profile required')
        distribution = importlib.metadata.distribution('fangcun-reliable-messaging')
        runtime = dict(python=sys.version.split()[0], sdk=distribution.version,
            client=importlib.metadata.version('rocketmq-python-client'),
            installed_in_prefix=Path(reliable_messaging.__file__).resolve().is_relative_to(sys.prefix),
            package_file=reliable_messaging.__file__,
            direct_url=json.loads(distribution.read_text('direct_url.json') or '{}'))
        validate_host_runtime(runtime, sdk, args.python)
        wheel_hash = validate_host_sdk_lock(tomllib.loads((source / 'uv.lock').read_text()), sdk)
        report.update(source_sha=sha, python_runtime=runtime, locked_sdk_archive_sha256=wheel_hash,
            lock_sha256=hashlib.sha256((source / 'uv.lock').read_bytes()).hexdigest(),
            test_source_sha256=hashlib.sha256((source / FILE).read_bytes()).hexdigest(),
            harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            helper_sha256={name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                           for name in ('ai_admission_acceptance.py', 'ai_finalization_characterization.py')},
            mysql_image_id=os.environ.get('QS_AI_T19_MYSQL_IMAGE_ID'),
            mysql_binding=validate_mysql_binding(os.environ['QS_AI_T19_MYSQL_PORTS']))
        if re.fullmatch(r'sha256:[0-9a-f]{64}', report['mysql_image_id'] or '') is None:
            raise ValueError('actual owned MySQL image digest required')
        from sqlalchemy.engine import make_url
        env = dict(os.environ, PYTHONPATH=str(source / 'src'))
        url, migration_url = env['QS_AI_DATABASE_URL'], env['QS_AI_T19_MIGRATION_DATABASE_URL']
        app, installer = make_url(url), make_url(migration_url)
        if (app.host not in {'127.0.0.1', 'localhost', '::1'} or app.database != 'qs_ai_t19'
                or (app.host, app.port, app.database) != (installer.host, installer.port, installer.database)):
            raise ValueError('same explicitly disposable loopback database required')
        phase = 'explicit_schema_install'
        log = directory / 'migration-private.log'
        with log.open('wb') as stream:
            migration = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'],
                cwd=source, env=dict(env, QS_AI_DATABASE_URL=migration_url),
                stdout=stream, stderr=subprocess.STDOUT, timeout=180)
        report['migration_output_sha256'] = hashlib.sha256(log.read_bytes()).hexdigest()
        if migration.returncode:
            raise RuntimeError('explicit schema install failed')
        phase = 'native_mysql_mtls'
        junit, log = directory / 'native-private.xml', directory / 'pytest-private.log'
        with log.open('wb') as stream:
            result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-s', '-x', FILE,
                '--basetemp=' + str(directory / 'pytest'), '--junitxml=' + str(junit)],
                cwd=source, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=240)
        report.update(native_exit_code=result.returncode,
            native_output_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
        if junit.exists():
            report.update(native_junit_sha256=hashlib.sha256(junit.read_bytes()).hexdigest(),
                          diagnostics=diagnostics(junit.read_text(), tests=TESTS))
        if result.returncode or not junit.exists():
            raise RuntimeError('required current payload native gate failed')
        report['native'] = parse_native(log.read_text(), junit.read_text(), sdk_version=sdk['sdk_version'])
        phase = 'owned_row_cleanup'
        report.update(asyncio.run(storage_receipt(url)))
        if report['mysql_version'] != args.mysql or any(report['remaining_rows'].values()):
            raise ValueError('required MySQL profile or owned row cleanup differs')
        report['source_clean_after'] = not subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=source, text=True).strip()
        if not report['source_clean_after']:
            raise RuntimeError('host source changed during native gate')
        report.update(passed=len(TESTS), failed=0)
        code = 0
    except Exception as error:
        report.update(failure_phase=phase, error_class=type(error).__name__)
    finally:
        private.cleanup()
        report['private_evidence_removed'] = not directory.exists()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
        args.report.chmod(0o600)
    print(json.dumps({k: report[k] for k in ('batch', 'passed', 'failed', 'skipped')}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
