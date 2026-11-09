"""Drive the same AI SQLAlchemy root and native Broker limit in an owned stack."""
import hashlib
import json
from pathlib import Path
import re
import time
from xml.etree import ElementTree

from audit_transaction_limit import export
from provision_v2 import Admin


def run_origin(source, directory, broker, project, command, env, run, native_runner,
               read_parameters, proof, evidence_path):
    if not project.startswith('rocketmq-m2-') or directory.stat().st_mode & 0o077:
        raise RuntimeError('owned private AI origin fixture required')
    admin = Admin(broker)
    before = read_parameters(admin('getBrokerConfig'))
    network = run(['docker', 'inspect', '--format',
                   '{{range $name,$config := .NetworkSettings.Networks}}{{$name}}{{end}}', broker]).stdout.strip()
    if not network.startswith(project + '_') or (
        json.loads(run(['docker', 'network', 'inspect', network]).stdout)[0]['Labels']['com.docker.compose.project'] != project
    ):
        raise RuntimeError('owned Broker network required')
    test_file = Path(__file__).with_name('ai_native_origin_case.py').resolve()
    proof['case_sha256'] = hashlib.sha256(test_file.read_bytes()).hexdigest()
    proof['stage'] = 'configuration'

    def supervise(native):
        proof['stage'] = 'original_half'
        half = native.wait('half', timeout=90)
        if set(half) != {'event', 'key'} or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', half['key']):
            raise RuntimeError('bounded original message identity required')
        proof['stage'] = 'commit_without_broker'
        run(['docker', 'network', 'disconnect', network, broker])
        try:
            native.send('commit')
            closed = native.wait('closed', timeout=85)
        finally:
            run(['docker', 'network', 'connect', '--alias', 'broker', network, broker])
        if set(closed) != {'event', 'reference_sha256', 'wire_sha256'} or not all(
            re.fullmatch('[0-9a-f]{64}', closed[field]) for field in ('reference_sha256', 'wire_sha256')
        ):
            raise RuntimeError('original durable witness and wire proof required')
        proof.update(reference_sha256=closed['reference_sha256'], wire_sha256=closed['wire_sha256'],
                     disconnected_root_commit_and_sender_drained=True, stage='original_sys_index')
        deadline = time.monotonic() + 110
        index = None
        while time.monotonic() < deadline:
            try:
                index = export(broker, project, half['key'], evidence_path)
                break
            except RuntimeError:
                time.sleep(2)
        if not index or len(index['records']) != 1 or index['truncated_possible'] or not (
            index['read_only'] and not index['body_exported']
        ):
            raise RuntimeError('one original native SYS index required')
        digest = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        proof.update(native_index_sha256=digest, native_index_records=1, stage='original_notice')
        native.send('record')
        if native.wait('blocked', timeout=35) != {'event': 'blocked', 'evidence_sha256': digest}:
            raise RuntimeError('exact original native notice required')

    try:
        admin('updateBrokerConfig', '-k', 'transactionCheckMax', '-v', '2')
        effective = read_parameters(admin('getBrokerConfig'))
        if effective != dict(before, transactionCheckMax=2):
            raise RuntimeError('isolated Broker check budget required')
        junit = directory / 'ai-native-origin-private.xml'
        result = native_runner([*command, 'python', '-m', 'pytest', '-q', '-s',
                                 '-c', str(source / 'pyproject.toml'), str(test_file), '--junitxml=' + str(junit)],
                                cwd=source, env=env, timeout=355,
                                prefix='AI_NATIVE_ORIGIN ', supervise=supervise)
        if result.returncode or not junit.is_file():
            raise RuntimeError('isolated original AI host acceptance failed')
        cases = ElementTree.parse(junit).findall('.//testcase')
        if len(cases) != 1 or cases[0].get('name') != 'test_original_ai_root_reaches_native_limit' or any(cases[0].find(tag) is not None for tag in ('failure', 'error', 'skipped')):
            raise RuntimeError('one actual AI original case must pass without skip')
    finally:
        admin('updateBrokerConfig', '-k', 'transactionCheckMax', '-v', str(before['transactionCheckMax']))
        proof['broker_parameters_restored'] = read_parameters(admin('getBrokerConfig')) == before
    if not proof['broker_parameters_restored']:
        raise RuntimeError('isolated Broker parameters were not restored')
    proof['stage'] = 'verified'
    return {'cases': {'actual_ai_original_root': True, 'same_root_sys_limit': True,
                      'original_notice_keeps_witness': True}}
