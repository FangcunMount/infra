"""Actual IAM role entry/original roots plus independent wire-proxy evidence."""
import hashlib
import json
import re
from iam_acceptance import retain_private_host_output

SCOPE = 'actual IAM role.create original GORM root with wire-level MySQL COMMIT faults; component only'
CASES = frozenset(('actual_role_root_once', 'business_version_witness_match_boundary',
    'duplicate_keeps_original_plan_and_result', 'broker_visibility_or_new_paused_checker',
    'published_outboxes_empty', 'owned_owner_and_transport_drained_primary_retained'))


def parse_receipt(output, source, boundary):
    rows = [json.loads(line.removeprefix('M3_IAM_FAULT_RECEIPT ')) for line in output.splitlines()
            if line.startswith('M3_IAM_FAULT_RECEIPT ')]
    if len(rows) != 1:
        raise RuntimeError('one exact original-role fault receipt required')
    r = rows[0]
    if (not isinstance(r, dict) or not isinstance(r.get('cases'), dict)
            or any(type(r.get(k)) is not int for k in ('passed', 'failed', 'skipped', 'callback_calls', 'half_prepared'))
            or r.get('source_sha') != source or not re.fullmatch('[0-9a-f]{40}', source)
            or boundary not in ('before', 'after') or r.get('boundary') != boundary
            or r.get('scope') != SCOPE or r.get('passed') != 6
            or r.get('failed') != 0 or r.get('skipped') != 0
            or set(r.get('cases', {})) != CASES or any(v is not True for v in r['cases'].values())
            or r.get('callback_calls') != 1 or r.get('half_prepared') != 1
            or type(r.get('new_paused_rollback_checks')) is not int
            or (boundary == 'before' and r['new_paused_rollback_checks'] < 1)
            or (boundary == 'after' and r['new_paused_rollback_checks'] != 0)
            or r.get('full_api_process_provider_system_not_claimed') is not True
            or not re.search(r'--- PASS: TestM3IAMOriginalCommitPacketFault \(', output)
            or re.search(r'--- (?:FAIL|SKIP):|WARNING: DATA RACE', output)):
        raise RuntimeError('original role fault receipt wrong source, boundary, scope or incomplete')
    return r


def wire_evidence(injection, stats, boundary):
    expected_ack = boundary == 'after'
    if (boundary not in ('before', 'after') or injection.get('event') != 'injected'
            or injection.get('kind') != 'mysql' or injection.get('boundary') != boundary
            or injection.get('backend_ack') is not expected_ack or injection.get('dropped') != 1
            or stats.get('event') != 'stats' or stats.get('dropped') != 1 or stats.get('seen') != 1
            or stats.get('backend_commit_acks') != int(expected_ack)):
        raise RuntimeError('actual original COMMIT wire boundary not established')
    return {'boundary': boundary, 'backend_ack': expected_ack, 'seen': 1,
            'dropped': 1, 'backend_commit_acks': int(expected_ack)}


def fixed_diagnostics(output):
    values = []
    fields = {'boundary', 'api_error', 'business_rows', 'version_delta', 'decision', 'callback_calls'}
    for line in output.splitlines():
        if not line.startswith('M3_IAM_FAULT_DIAGNOSTIC '):
            continue
        value = json.loads(line.removeprefix('M3_IAM_FAULT_DIAGNOSTIC '))
        if (set(value) != fields or value['boundary'] not in ('before', 'after')
                or type(value['api_error']) is not bool
                or any(type(value[k]) is not int or not 0 <= value[k] <= 16 for k in
                       ('business_rows', 'version_delta', 'callback_calls'))
                or value['decision'] not in ('unknown', 'commit', 'rollback') or len(values) >= 4):
            raise RuntimeError('original-root diagnostic outside safe schema')
        values.append(value)
    return values


def run_profile(source, directory, env, run, proof, native_runner, proxy_start):
    if native_runner is None or proxy_start is None:
        raise RuntimeError('owned native process and wire proxy supervision required')
    results = {}
    for boundary in ('before', 'after'):
        proxy = proxy_start('mysql')
        proxy.send(json.dumps({'Action': 'arm', 'Boundary': boundary, 'Method': 'commit', 'Nth': 1}))
        proxy.wait('armed')
        current = dict(env, IAM_M3_FAULT_BOUNDARY=boundary, IAM_M3_FAULT_MYSQL_PROXY=proxy.address)
        result = native_runner(['go', 'test', '-race', '-p', '1', '-tags=integration,m3_iam_faults',
            '-count=1', '-timeout=5m', '-v', './internal/pkg/migration',
            '-run', '^TestM3IAMOriginalCommitPacketFault$'], cwd=source, env=current,
            timeout=720, required=False)
        raw = result.stdout + result.stderr
        private = directory / ('iam-original-' + boundary + '-private.log')
        retain_private_host_output(private, raw)
        evidence = {'native_exit_code': result.returncode,
            'native_output_sha256': hashlib.sha256(raw.encode()).hexdigest(),
            'diagnostics': fixed_diagnostics(raw),
            'assertion_lines': sorted(set(map(int, re.findall(r'transaction_packet_fault_integration_test\.go:(\d+)', raw))))[:32],
            'test_timeout': 'panic: test timed out' in raw,
            'race_reports': raw.count('WARNING: DATA RACE')}
        results[boundary] = evidence
        proof['faults'] = results
        if result.returncode:
            raise RuntimeError('actual original IAM role packet fault failed; private output withheld')
        evidence['receipt'] = parse_receipt(raw, proof['source_sha'], boundary)
        injected = proxy.wait('injected', timeout=10)
        proxy.send(json.dumps({'Action': 'stats'}))
        stats = proxy.wait('stats')
        evidence['wire'] = wire_evidence(injected, stats, boundary)
        proxy.send(json.dumps({'Action': 'stop'})); proxy.wait('closed'); proxy.finish()
    proof['scope'] = SCOPE
    proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if not proof['source_clean_after']:
        raise RuntimeError('IAM source changed during original-root fault proof')
