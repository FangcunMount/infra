"""Actual Python AI admission host, published SDK and isolated Broker/MySQL only."""
import hashlib
import json
import os
import re
import secrets
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


def parse_admission_receipt(output, junit):
    receipts = [json.loads(line.split('M3_AI_ADMISSION_RECEIPT ', 1)[1])
                for line in output.splitlines() if 'M3_AI_ADMISSION_RECEIPT {' in line]
    if len(receipts) != 1:
        raise RuntimeError('exact nonempty AI host receipt required')
    receipt = receipts[0]
    if (receipt.get('passed') != len(CASES) or receipt.get('failed') != 0
            or receipt.get('skipped') != 0 or set(receipt.get('cases', {})) != CASES
            or any(v is not True for v in receipt['cases'].values())
            or receipt.get('root') != 'original_mysql_sqlalchemy'
            or receipt.get('sdk') != '0.4.0a1' or receipt.get('client') != '5.1.2'
            or any(receipt.get(key) is not True for key in (
                'system_login_not_claimed', 'paired_qs_business_not_claimed', 'real_provider_not_claimed',
                'process_exit_not_claimed', 'database_commit_network_fault_not_claimed'))):
        raise RuntimeError('AI host receipt incomplete or broader than proven scope')
    tests = list(ET.fromstring(junit).iter('testcase'))
    if (len(tests) != len(TESTS) or {case.get('name') for case in tests} != TESTS
            or any(case.find(node) is not None for case in tests for node in ('failure', 'error', 'skipped'))):
        raise RuntimeError('required actual AI host tests failed, skipped, duplicate or absent')
    return receipt


def run_ai_admission_host(source, directory, broker, project, grpc_port, mysql_port, password, ca, run, proof):
    source = source.resolve()
    if not (source / 'pyproject.toml').is_file() or run(['git', 'status', '--porcelain'], cwd=source).stdout.strip():
        raise RuntimeError('exact clean AI host source required')
    proof['source_sha'] = run(['git', 'rev-parse', 'HEAD'], cwd=source).stdout.strip()
    proof['lock_sha256'] = hashlib.sha256((source / 'uv.lock').read_bytes()).hexdigest()
    python = os.environ.get('QS_AI_ACCEPTANCE_PYTHON')
    if python not in ('3.11', '3.13'):
        raise RuntimeError('fixed AI acceptance Python compatibility profile required')
    command = ['uv', 'run', '--locked', '--python', python, '--group', 'maintenance']
    manifest = admission_manifest()
    accounts = {role: {'username': 'ai-' + role + '-' + secrets.token_hex(4), 'password': secrets.token_hex(32)}
                for role in manifest['accounts']}
    proof['provision'] = provision(broker, manifest, accounts)
    schema = 'ai_admission_' + secrets.token_hex(8)
    db_user, db_password = 'ai_m3_' + secrets.token_hex(6), secrets.token_hex(32)
    mysql = project + '-mysql-1'
    run(['docker', 'exec', '-i', '-e', 'MYSQL_PWD=' + password, mysql, 'mysql', '-uroot', '--batch'],
        stdin=f"CREATE DATABASE `{schema}` CHARACTER SET utf8mb4; CREATE USER '{db_user}'@'%' IDENTIFIED BY '{db_password}'; GRANT ALL ON `{schema}`.* TO '{db_user}'@'%';")
    root_url = f'mysql+asyncmy://root:{password}@127.0.0.1:{mysql_port}/{schema}'
    application_url = f'mysql+asyncmy://{db_user}:{db_password}@127.0.0.1:{mysql_port}/{schema}'
    private_config = directory / 'ai-admission-config.json'
    private_config.write_text(json.dumps(dict(accounts, endpoint=f'127.0.0.1:{grpc_port}', client_log=str(directory / 'ai-client-private.log')))); private_config.chmod(0o600)
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
    if (runtime.get('sdk') != '0.4.0a1' or runtime.get('client') != '5.1.2'
            or not runtime.get('python', '').startswith(python + '.')
            or runtime.get('direct_url', {}).get('url') != SDK_URL
            or runtime.get('installed_in_prefix') is not True):
        raise RuntimeError('released fixed SDK wheel and client required, no editable SDK')
    proof['python_runtime'] = runtime
    junit = directory / 'ai-admission-private.xml'
    result = run([*command, 'pytest', '-q', '-s', str(source / 'tests/integration/rocketmq_admission_host.py'),
                  '--junitxml=' + str(junit)], cwd=source, env=env, timeout=900, required=False)
    raw = result.stdout + result.stderr
    capture = directory / 'ai-admission-host-private.log'; capture.write_text(raw); capture.chmod(0o600)
    if junit.exists():
        junit.chmod(0o600)
        proof['junit_sha256'] = hashlib.sha256(junit.read_bytes()).hexdigest()
    proof['private_output_sha256'] = hashlib.sha256(raw.encode()).hexdigest()
    proof['exit_code'] = result.returncode
    proof['diagnostics'] = {'failed_cases': sorted(set(re.findall(r'FAILED tests/integration/rocketmq_admission_host.py::([A-Za-z0-9_\[\]-]+)', raw)))[:16],
                            'assertion_lines': sorted(set(int(n) for n in re.findall(r'rocketmq_admission_host\.py:(\d+)', raw)))[:32]}
    if result.returncode or not junit.is_file():
        raise RuntimeError('actual AI admission SDK/Broker host failed (private output withheld)')
    proof['native_receipt'] = parse_admission_receipt(result.stdout, junit.read_text())
    proof['native_tests_passed'] = len(TESTS)
    proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if not proof['source_clean_after']:
        raise RuntimeError('AI source changed during native host acceptance')
    proof['scope'] = 'actual Python AI receiver, published SDK, original roots and real Broker; controlled QS input/observer only'
