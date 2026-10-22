"""Actual Python AI admission host, published SDK and isolated Broker/MySQL only."""
import hashlib
import json
import os
import re
import secrets
import tomllib
from pathlib import Path
import xml.etree.ElementTree as ET

from provision_v2 import provision
from routes import consumer_group_v2, physical_topic_v2, validate_v2

CASES = frozenset(('all_halves_before_local', 'constructor_inert', 'no_new_publish_outbox',
    'fresh_checker', 'original_first_wire', 'half_invisible', 'duplicate_no_reseal', 'start',
    'change_answer', 'change_cancel', 'participant_retry', 'evaluation_start', 'evaluation_cancel',
    'technical_hold', 'lost_final_reply'))
TESTS = frozenset((
    'test_actual_start_half_gate_and_duplicate_reuses_original_plan',
    'test_actual_change_original_root_over_broker[answer]',
    'test_actual_change_original_root_over_broker[cancel]',
    'test_actual_participant_retry_does_not_add_model_invocations',
    'test_actual_evaluation_original_root_over_broker[4]',
    'test_actual_evaluation_original_root_over_broker[5]',
    'test_actual_local_technical_budget_only_publishes_one_held_receipt',
    'test_real_commit_reply_deliberately_discarded_keeps_local_commit_and_first_wire'))
SDK_URL = 'https://github.com/FangcunMount/reliable-messaging/releases/download/python/v0.4.0a1/fangcun_reliable_messaging-0.4.0a1-py3-none-any.whl'


def admission_manifest():
    routes = []
    for name, topic, subscription, owner in (
            ('command', 'qs.ai.commands.v1', 'qs-ai.commands.v1', 'qs.mysql'),
            ('event', 'qs.ai.events.v1', 'qs-m3-ai-admission-observer', 'ai.mysql')):
        routes.append({'id': 'ai-admission-' + name, 'topic': topic, 'subscription': subscription,
                       'message_type': 'TRANSACTION', 'owner': owner, 'route_revision': 'm3-1',
                       'physical_topic': physical_topic_v2(topic, 'TRANSACTION', owner, 'm3-1'),
                       'consumer_group': consumer_group_v2(topic, subscription)})
    command, event = (r['id'] for r in routes)
    manifest = {'version': 2, 'routes': routes,
        'topic_options': {'read_queue_nums': 1, 'write_queue_nums': 1, 'perm': 6},
        'group_options': {'retry_queue_nums': 8},
        'accounts': {
            'input': {'owner': 'qs.mysql', 'publish': [command], 'subscriptions': []},
            'ai': {'owner': 'ai.mysql', 'publish': [event], 'subscriptions': [command]},
            'observer': {'publish': [], 'subscriptions': [event]}}}
    validate_v2(manifest)
    return manifest


_FLAGS = frozenset(('system_login_not_claimed', 'paired_qs_business_not_claimed',
    'real_provider_not_claimed', 'process_exit_not_claimed', 'database_commit_network_fault_not_claimed'))
_FIELDS = _FLAGS | {'cases', 'passed', 'failed', 'skipped', 'root', 'sdk', 'client', 'python'}


def read_host_receipt(output, *, marker='M3_AI_ADMISSION_RECEIPT', cases=CASES, sdk_version='0.4.0a1'):
    """Export only bounded counters, fixed labels and known scope; never raw diagnostics."""
    lines = [line.split(marker + ' ', 1)[1]
             for line in output.splitlines() if marker + ' {' in line]
    if len(lines) != 1:
        return None
    try:
        receipt = json.loads(lines[0])
    except (ValueError, TypeError):
        return None
    if (not isinstance(receipt, dict) or set(receipt) != _FIELDS
            or not isinstance(receipt.get('cases'), dict) or not set(receipt['cases']) <= cases
            or any(v is not True for v in receipt['cases'].values())
            or any(type(receipt.get(k)) is not int or not 0 <= receipt[k] <= max(100, len(cases))
                   for k in ('passed', 'failed', 'skipped'))
            or receipt['passed'] != len(receipt['cases'])
            or receipt.get('root') != 'original_mysql_sqlalchemy'
            or receipt.get('sdk') != sdk_version or receipt.get('client') != '5.1.2'
            or not isinstance(receipt.get('python'), str)
            or re.fullmatch(r'3\.(?:11|13)\.\d{1,3}', receipt['python']) is None
            or any(receipt.get(k) is not True for k in _FLAGS)):
        return None
    return receipt


def parse_host_receipt(output, junit, *, marker='M3_AI_ADMISSION_RECEIPT', cases=CASES, tests=TESTS, sdk_version='0.4.0a1'):
    receipt = read_host_receipt(output, marker=marker, cases=cases, sdk_version=sdk_version)
    if (receipt is None or receipt['passed'] != len(cases)
            or receipt['failed'] != 0 or receipt['skipped'] != 0
            or set(receipt['cases']) != cases):
        raise RuntimeError('AI host receipt absent, incomplete or broader than proven scope')
    executed = list(ET.fromstring(junit).iter('testcase'))
    if (len(executed) != len(tests) or {case.get('name') for case in executed} != tests
            or any(case.find(node) is not None for case in executed for node in ('failure', 'error', 'skipped'))):
        raise RuntimeError('required actual AI host tests failed, skipped, duplicate or absent')
    return receipt


def read_partial_receipt(output):
    return read_host_receipt(output)


def parse_admission_receipt(output, junit):
    return parse_host_receipt(output, junit)


def acceptance_profile(kind):
    if kind == 'admission':
        return dict(name=kind, sdk_version='0.4.0a1', sdk_url=SDK_URL, sdk_sha256=None, file='rocketmq_admission_host.py', manifest=admission_manifest,
                    partial=read_partial_receipt, parse=parse_admission_receipt, tests=TESTS,
                    scope='actual Python AI receiver, published SDK, original roots and real Broker; controlled QS input/observer only')
    if kind == 'state':
        from ai_state_acceptance import CASES as STATE_CASES, TESTS as STATE_TESTS, state_manifest
        return dict(name=kind, sdk_version='0.4.0a2', sdk_url=SDK_URL.replace('0.4.0a1', '0.4.0a2'),
                    sdk_sha256='570822f9ed51eee25001624858d30b7433468eb7da59e34348289c50a37cabb2', file='rocketmq_state_host.py', manifest=state_manifest,
                    partial=lambda output: read_host_receipt(output, marker='M3_AI_STATE_RECEIPT', cases=STATE_CASES, sdk_version='0.4.0a2'),
                    parse=lambda output, junit: parse_host_receipt(output, junit, marker='M3_AI_STATE_RECEIPT', cases=STATE_CASES, tests=STATE_TESTS, sdk_version='0.4.0a2'),
                    tests=STATE_TESTS,
                    scope='actual Python worker/preflight, governance/review/correction/Solution and unknown-resolution handlers plus serial dispatch, claim and durable generation/semantic terminal senders, published SDK, default DI/transport/worker assembly, original state roots and real Broker; controlled authenticated ACK and event observer only')
    raise RuntimeError('explicit known AI acceptance profile required')


def host_failure_diagnostics(raw, filename, tests):
    names = set(re.findall(r'(?:FAILED|ERROR) tests/integration/' + re.escape(filename) +
                           r'::([A-Za-z0-9_\[\]-]+)', raw))
    return {'failed_cases': sorted(names & tests)[:16],
            'assertion_lines': sorted(set(int(n) for n in re.findall(
                re.escape(filename) + r':(\d{1,6})(?!\d)', raw)))[:32]}



def validate_host_sdk_lock(lock, profile):
    """uv verifies the archive hash from its immutable lock, not direct_url.json."""
    if profile['sdk_sha256'] is None:
        return None  # Historical admission profile keeps its original provenance contract.
    packages = [p for p in lock.get('package', []) if p.get('name') == 'fangcun-reliable-messaging']
    expected = {'url': profile['sdk_url'], 'hash': 'sha256:' + profile['sdk_sha256']}
    if (len(packages) != 1 or packages[0].get('version') != profile['sdk_version']
            or packages[0].get('source') != {'url': profile['sdk_url']}
            or packages[0].get('wheels') != [expected]):
        raise RuntimeError('Exact released SDK version, URL and wheel hash required in uv lock')
    return profile['sdk_sha256']


def validate_host_runtime(runtime, profile, python):
    direct = runtime.get('direct_url', {})
    if (runtime.get('sdk') != profile['sdk_version'] or runtime.get('client') != '5.1.2'
            or not runtime.get('python', '').startswith(python + '.')
            or direct.get('url') != profile['sdk_url']
            or runtime.get('installed_in_prefix') is not True
            or (profile['sdk_sha256'] is not None
                and direct.get('archive_info', {}).get('hashes', {}).get('sha256') not in (None, profile['sdk_sha256']))):
        raise RuntimeError('released fixed SDK wheel and client required, no editable SDK')


def run_ai_admission_host(source, directory, broker, project, grpc_port, mysql_port, password, ca, run, proof):
    profile = acceptance_profile(os.environ.get('QS_AI_ACCEPTANCE_KIND', 'admission'))
    source = source.resolve()
    if not (source / 'pyproject.toml').is_file() or run(['git', 'status', '--porcelain'], cwd=source).stdout.strip():
        raise RuntimeError('exact clean AI host source required')
    proof['source_sha'] = run(['git', 'rev-parse', 'HEAD'], cwd=source).stdout.strip()
    proof['host_profile'] = profile['name']
    proof['lock_sha256'] = hashlib.sha256((source / 'uv.lock').read_bytes()).hexdigest()
    proof['locked_sdk_archive_sha256'] = validate_host_sdk_lock(tomllib.loads((source / 'uv.lock').read_text()), profile)
    python = os.environ.get('QS_AI_ACCEPTANCE_PYTHON')
    if python not in ('3.11', '3.13'):
        raise RuntimeError('fixed AI acceptance Python compatibility profile required')
    command = ['uv', 'run', '--locked', '--python', python, '--group', 'maintenance']
    manifest = profile['manifest']()
    accounts = {role: {'username': 'ai-' + role + '-' + secrets.token_hex(4), 'password': secrets.token_hex(32)}
                for role in manifest['accounts']}
    proof['provision'] = provision(broker, manifest, accounts)
    schema = 'ai_' + profile['name'] + '_' + secrets.token_hex(8)
    db_user, db_password = 'ai_m3_' + secrets.token_hex(6), secrets.token_hex(32)
    mysql = project + '-mysql-1'
    run(['docker', 'exec', '-i', '-e', 'MYSQL_PWD=' + password, mysql, 'mysql', '-uroot', '--batch'],
        stdin=f"CREATE DATABASE `{schema}` CHARACTER SET utf8mb4; CREATE USER '{db_user}'@'%' IDENTIFIED BY '{db_password}'; GRANT ALL ON `{schema}`.* TO '{db_user}'@'%';")
    root_url = f'mysql+asyncmy://root:{password}@127.0.0.1:{mysql_port}/{schema}'
    application_url = f'mysql+asyncmy://{db_user}:{db_password}@127.0.0.1:{mysql_port}/{schema}'
    private_config = directory / ('ai-' + profile['name'] + '-config.json')
    private_config.write_text(json.dumps(dict(accounts, endpoint=f'127.0.0.1:{grpc_port}',
        client_log=str(directory / 'ai-client-private.log'), routes=manifest['routes'],
        ca_file=str(ca)))); private_config.chmod(0o600)
    env = dict(os.environ, QS_AI_DATABASE_URL=application_url,
               QS_AI_TEST_MYSQL_DSN=application_url.replace('mysql+asyncmy://', 'mysql://', 1),
               QS_MQ_FAULT_DDL_MYSQL_URL=root_url, QS_AI_M3_BROKER_CONFIG=str(private_config),
               GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=str(ca), QS_AI_ACCEPTANCE_PYTHON=python)
    migration = run([*command, 'alembic', 'upgrade', 'head'], cwd=source,
                    env=dict(env, QS_AI_DATABASE_URL=root_url), timeout=180, required=False)
    if migration.returncode:
        proof['migration_exit_code'] = migration.returncode
        raise RuntimeError('explicit isolated AI migration failed (private output withheld)')
    info = run([*command, 'python', '-I', '-c',
        "import sys,json,pathlib,importlib.metadata as m,reliable_messaging as r; d=m.distribution('fangcun-reliable-messaging'); print(json.dumps({'python':sys.version.split()[0],'sdk':d.version,'client':m.version('rocketmq-python-client'),'package_file':r.__file__,'installed_in_prefix':pathlib.Path(r.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()),'direct_url':json.loads(d.read_text('direct_url.json'))}))"], cwd=source, env=env).stdout
    runtime = json.loads(info)
    validate_host_runtime(runtime, profile, python)
    proof['python_runtime'] = runtime
    junit = directory / ('ai-' + profile['name'] + '-private.xml')
    filename = profile['file']
    result = run([*command, 'pytest', '-q', '-s', str(source / 'tests/integration' / filename),
                  '--junitxml=' + str(junit)], cwd=source, env=env, timeout=900, required=False)
    raw = result.stdout + result.stderr
    capture = directory / ('ai-' + profile['name'] + '-host-private.log'); capture.write_text(raw); capture.chmod(0o600)
    if junit.exists():
        junit.chmod(0o600)
        proof['junit_sha256'] = hashlib.sha256(junit.read_bytes()).hexdigest()
    proof['private_output_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
    proof['exit_code'] = result.returncode
    proof['diagnostics'] = host_failure_diagnostics(raw, filename, profile['tests'])
    if result.returncode or not junit.is_file():
        partial = profile['partial'](result.stdout)
        if partial is not None:
            proof['partial_native_receipt'] = partial
        raise RuntimeError('actual AI SDK/Broker host failed (private output withheld)')
    proof['native_receipt'] = profile['parse'](result.stdout, junit.read_text())
    proof['native_tests_passed'] = len(profile['tests'])
    proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if not proof['source_clean_after']:
        raise RuntimeError('AI source changed during native host acceptance')
    proof['scope'] = profile['scope']
