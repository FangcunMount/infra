"""AI original command root with query-aware MySQL COMMIT TCP loss."""
import hashlib
import json
import re
from urllib.parse import urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from ai_admission_acceptance import admission_manifest
from iam_acceptance import retain_private_host_output
from iam_fault_acceptance import wire_evidence

SCOPE = 'actual AI command receiver original SQLAlchemy root with wire-level MySQL COMMIT faults; component only'
CASES = frozenset(('actual_command_root_once', 'business_inbox_witness_match_boundary',
    'duplicate_keeps_original_plan_and_result', 'broker_visibility_or_new_paused_checker',
    'published_outbox_empty_provider_invocations_zero', 'owned_runtimes_drained_primary_retained'))
TEST = 'test_actual_command_original_commit_packet_fault'


def profile():
    return dict(name='db_faults', sdk_version='0.4.0a2',
        sdk_url='https://github.com/FangcunMount/reliable-messaging/releases/download/python/v0.4.0a2/fangcun_reliable_messaging-0.4.0a2-py3-none-any.whl',
        sdk_sha256='570822f9ed51eee25001624858d30b7433468eb7da59e34348289c50a37cabb2',
        manifest=admission_manifest, file='rocketmq_database_faults.py', scope=SCOPE)


def parse_receipt(output, junit, source, boundary):
    rows = [json.loads(line.removeprefix('M3_AI_DATABASE_FAULT_RECEIPT ')) for line in output.splitlines()
            if line.startswith('M3_AI_DATABASE_FAULT_RECEIPT ')]
    if len(rows) != 1:
        raise RuntimeError('one actual AI original root packet-fault receipt required')
    r = rows[0]
    integers = ('passed', 'failed', 'skipped', 'local_calls', 'half_prepared', 'new_half_prepared',
                'new_check_rollback', 'business_rows', 'inbox_rows', 'provider_invocations')
    if (not isinstance(r, dict) or not isinstance(r.get('cases'), dict)
            or any(type(r.get(k)) is not int for k in integers)
            or not re.fullmatch('[0-9a-f]{40}', source) or r.get('source_sha') != source
            or boundary not in ('before', 'after') or r.get('boundary') != boundary or r.get('scope') != SCOPE
            or r['passed'] != 6 or r['failed'] != 0 or r['skipped'] != 0
            or set(r['cases']) != CASES or any(v is not True for v in r['cases'].values())
            or r['local_calls'] != 1 or r['half_prepared'] != 2 or r['new_half_prepared'] != 0
            or r['business_rows'] != int(boundary == 'after') or r['inbox_rows'] != int(boundary == 'after')
            or r['provider_invocations'] != 0 or r.get('fixed_two_branch_wire') is not True
            or (boundary == 'before' and not 1 <= r['new_check_rollback'] <= 1024)
            or (boundary == 'after' and r['new_check_rollback'] != 0)
            or r.get('full_api_process_real_provider_system_not_claimed') is not True):
        raise RuntimeError('AI original root packet-fault receipt incomplete or wrong source/scope')
    tests = list(ET.fromstring(junit).iter('testcase'))
    if (len(tests) != 1 or tests[0].get('name') != TEST
            or tests[0].get('classname') != 'tests.integration.rocketmq_database_faults'
            or any(tests[0].find(key) is not None for key in ('failure', 'error', 'skipped'))):
        raise RuntimeError('required AI original root native test missing, duplicated, failed or skipped')
    return r


def proxy_database_url(url, address):
    parsed = urlsplit(url)
    if (parsed.scheme != 'mysql+asyncmy' or parsed.hostname != '127.0.0.1'
            or not re.fullmatch(r'127\.0\.0\.1:[1-9][0-9]{0,4}', address)
            or int(address.rsplit(':', 1)[1]) > 65535 or not parsed.username or not parsed.password):
        raise RuntimeError('owned literal-loopback original MySQL URL/proxy required')
    # Keep the original encoded credentials and owned database byte-for-byte.
    return urlunsplit(parsed._replace(netloc=parsed.netloc.rsplit('@', 1)[0] + '@' + address))


def run_profile(source, directory, env, command, run, proof, native_runner, proxy_start, primary_port):
    if native_runner is None or proxy_start is None:
        raise RuntimeError('owned native process and proxy supervision required')
    proof['faults'] = {}
    for boundary in ('before', 'after'):
        proxy = proxy_start('mysql')
        proxy.send(json.dumps({'Action': 'arm', 'Boundary': boundary, 'Method': 'commit', 'Nth': 1}))
        proxy.wait('armed')
        application_url = proxy_database_url(env['QS_AI_DATABASE_URL'], proxy.address)
        current = dict(env, QS_AI_DATABASE_URL=application_url,
            QS_AI_TEST_MYSQL_DSN=application_url.replace('mysql+asyncmy://', 'mysql://', 1),
            QS_AI_M3_FAULT_BOUNDARY=boundary, QS_AI_M3_FAULT_MYSQL_PRIMARY=f'127.0.0.1:{primary_port}')
        junit = directory / ('ai-original-root-' + boundary + '-private.xml')
        result = native_runner([*command, 'pytest', '-q', '-s', '-x',
            str(source / 'tests/integration/rocketmq_database_faults.py'), '--junitxml=' + str(junit)],
            cwd=source, env=current, timeout=360, required=False)
        raw = result.stdout + result.stderr
        retain_private_host_output(directory / ('ai-original-root-' + boundary + '-private.log'), raw)
        if junit.exists(): junit.chmod(0o600)
        evidence = dict(native_exit_code=result.returncode, native_output_sha256=hashlib.sha256(raw.encode()).hexdigest(),
            assertion_lines=sorted(set(map(int, re.findall(r'rocketmq_database_faults\.py:(\d+)', raw))))[:32])
        proof['faults'][boundary] = evidence
        if result.returncode or not junit.is_file():
            raise RuntimeError('actual AI original command root packet fault failed; private output withheld')
        evidence['junit_sha256'] = hashlib.sha256(junit.read_bytes()).hexdigest()
        evidence['receipt'] = parse_receipt(raw, junit.read_text(), proof['source_sha'], boundary)
        injection = proxy.wait('injected', timeout=10)
        proxy.send(json.dumps({'Action': 'stats'})); stats = proxy.wait('stats')
        evidence['wire'] = wire_evidence(injection, stats, boundary)
        proxy.send(json.dumps({'Action': 'stop'})); proxy.wait('closed'); proxy.finish()
    proof['native_tests_passed'] = 2
    proof['scope'] = SCOPE
    proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if not proof['source_clean_after']:
        raise RuntimeError('AI source changed during native original root fault proof')
