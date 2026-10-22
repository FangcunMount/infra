#!/usr/bin/env python3
"""Required T18-A MySQL characterization; no Broker/provider/production claim."""
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
import xml.etree.ElementTree as ET


TEST_FILE = 'tests/integration/test_finalization_characterization.py'
TESTS = {
    'test_original_worker_live_claim_ordinary_finish_leaves_aborted_terminal_unresolved',
    'test_original_worker_new_lease_reuses_model_response_but_conflicts_with_old_finish',
}


def parse_native(raw):
    cases = list(ET.fromstring(raw).iter('testcase'))
    if len(cases) != len(TESTS) or {c.get('name') for c in cases} != TESTS:
        raise ValueError('required characterization test set differs')
    if any(c.get('classname') != 'tests.integration.test_finalization_characterization'
           or any(c.find(tag) is not None for tag in ('error', 'failure', 'skipped'))
           for c in cases):
        raise ValueError('required characterization failed or skipped')
    return {'passed': len(cases), 'failed': 0, 'skipped': 0,
            'tests': sorted(TESTS), 'known_recovery_gap_reproduced': True}


def diagnostics(raw):
    # Never export traceback values, body/wire, DSNs or credentials.
    root = ET.fromstring(raw)
    rows = []
    for c in root.iter('testcase'):
        name = c.get('name') if c.get('name') in TESTS else 'unlisted'
        nodes = [n for tag in ('error', 'failure', 'skipped') for n in c.findall(tag)]
        if nodes:
            text = '\n'.join((n.text or '') for n in nodes)
            rows.append({'test': name, 'statuses': [n.tag for n in nodes],
                         'error_classes': sorted(set(re.findall(
                             r'\b[A-Za-z_][A-Za-z_.]*(?:Error|Exception|Pending)\b', text))),
                         'source_locations': sorted(set(re.findall(
                             r'(?:tests|src)/[A-Za-z0-9_./-]+\.py:[0-9]+', text)))})
    return rows


async def remaining_rows(url):
    from sqlalchemy import func, select, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine
    from qs_ai.infrastructure.persistence.mysql.schema import artifacts, jobs, model_calls, sessions
    from qs_ai.infrastructure.persistence.mysql.transaction_schema import (
        archive, binding, execution, request, witness,
    )
    if make_url(url).host not in {'127.0.0.1', 'localhost', '::1'}:
        raise ValueError('explicit disposable loopback database required')
    engine = create_async_engine(url, hide_parameters=True)
    try:
        async with engine.connect() as db:
            rows = {t.name: int(await db.scalar(select(func.count()).select_from(t)))
                    for t in (artifacts, jobs, model_calls, sessions,
                              archive, binding, execution, request, witness)}
            return rows, await db.scalar(text('SELECT VERSION()'))
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--expected-source', required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    report = {'version': 1, 'batch': 'T18-A-original-worker-MySQL-characterization',
              'passed': 0, 'failed': 1, 'skipped': 0,
              'scope': 'known missing recovery characterization, not repaired finalization',
              'broker_fault_claimed': False, 'external_http_counter_claimed': False,
              'process_restart_claimed': False, 'production_changed': False}
    private = tempfile.TemporaryDirectory(prefix='ai-t18-characterization-')
    directory = Path(private.name)
    directory.chmod(0o700)
    phase = 'source'
    exit_code = 1
    try:
        sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
        if sha != args.expected_source or re.fullmatch('[0-9a-f]{40}', sha) is None:
            raise ValueError('exact source required')
        if subprocess.check_output(['git', 'status', '--porcelain'], cwd=source, text=True).strip():
            raise ValueError('clean source required')
        sys.path.insert(0, str(source / 'src'))
        import qs_ai
        if not Path(qs_ai.__file__).resolve().is_relative_to(source / 'src'):
            raise ValueError('exact host source import required')
        report.update(source_sha=sha,
            python=sys.version.split()[0],
            sdk=importlib.metadata.version('fangcun-reliable-messaging'),
            client=importlib.metadata.version('rocketmq-python-client'),
            lock_sha256=hashlib.sha256((source / 'uv.lock').read_bytes()).hexdigest(),
            test_source_sha256=hashlib.sha256((source / TEST_FILE).read_bytes()).hexdigest(),
            harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            mysql_image_id=os.environ.get('QS_AI_T18_MYSQL_IMAGE_ID'))
        if re.fullmatch(r'sha256:[0-9a-f]{64}', report['mysql_image_id'] or '') is None:
            raise ValueError('actual MySQL image digest required')
        if (report['sdk'], report['client']) != ('0.4.0a2', '5.1.2'):
            raise ValueError('fixed SDK/client required')
        env = dict(os.environ, PYTHONPATH=str(source / 'src'))
        from sqlalchemy.engine import make_url
        url = env['QS_AI_DATABASE_URL']
        if make_url(url).host not in {'127.0.0.1', 'localhost', '::1'}:
            raise ValueError('disposable loopback database required')
        phase = 'explicit_schema_install'
        log = directory / 'migration-private.log'
        with log.open('wb') as stream:
            log.chmod(0o600)
            migration = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'],
                cwd=source, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=180)
        report['migration_output_sha256'] = hashlib.sha256(log.read_bytes()).hexdigest()
        if migration.returncode:
            raise RuntimeError('explicit schema installation failed')
        phase = 'native_characterization'
        junit = directory / 'native-private.xml'
        log = directory / 'pytest-private.log'
        with log.open('wb') as stream:
            log.chmod(0o600)
            result = subprocess.run([sys.executable, '-m', 'pytest', '-q', TEST_FILE,
                '--junitxml=' + str(junit)], cwd=source, env=env,
                stdout=stream, stderr=subprocess.STDOUT, timeout=180)
        report['native_exit_code'] = result.returncode
        report['native_output_sha256'] = hashlib.sha256(log.read_bytes()).hexdigest()
        if junit.exists():
            junit.chmod(0o600)
            raw = junit.read_text()
            report['native_junit_sha256'] = hashlib.sha256(junit.read_bytes()).hexdigest()
            report['diagnostics'] = diagnostics(raw)
        if result.returncode or not junit.exists():
            raise RuntimeError('required native characterization failed')
        report['native'] = parse_native(raw)
        phase = 'test_row_cleanup'
        rows, mysql = asyncio.run(remaining_rows(url))
        report['remaining_rows'] = rows
        report['mysql_version'] = mysql
        if mysql != '8.0.36':
            raise ValueError('fixed characterization MySQL version required')
        if any(rows.values()):
            raise RuntimeError('test business or protocol rows remain')
        report['source_clean_after'] = not subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=source, text=True).strip()
        if not report['source_clean_after']:
            raise RuntimeError('source changed during characterization')
        report.update(passed=len(TESTS), failed=0)
        exit_code = 0
    except Exception as error:
        report.update(failure_phase=phase, error_class=type(error).__name__)
    finally:
        private.cleanup()
        report['private_evidence_removed'] = not directory.exists()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
        args.report.chmod(0o600)
    print(json.dumps({k: report[k] for k in ('batch', 'passed', 'failed', 'skipped')}))
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
