"""Actual QS command store/original root plus independent wire-proxy evidence."""
import hashlib
import json
import re
from iam_acceptance import retain_private_host_output
from iam_fault_acceptance import wire_evidence

SCOPE = 'actual QS command store original MySQL root with wire-level COMMIT faults; component only'
CASES = frozenset(('actual_command_original_root', 'business_witness_match_boundary',
    'first_seal_plan_and_operation_reused', 'broker_visibility_or_new_paused_checker',
    'new_publish_outbox_empty', 'owned_runtimes_drained_primary_retained'))


def parse_receipt(output, source, boundary):
    rows = [json.loads(line.removeprefix('M3_QS_COMMAND_FAULT_RECEIPT ')) for line in output.splitlines()
            if line.startswith('M3_QS_COMMAND_FAULT_RECEIPT ')]
    if len(rows) != 1:
        raise RuntimeError('one exact original command fault receipt required')
    r = rows[0]
    if (not isinstance(r, dict) or not isinstance(r.get('cases'), dict)
            or any(type(r.get(k)) is not int for k in ('passed', 'failed', 'skipped', 'sdk_executions', 'half_prepared', 'seals', 'new_half_prepared', 'business_rows'))
            or r.get('source_sha') != source or not re.fullmatch('[0-9a-f]{40}', source)
            or boundary not in ('before', 'after') or r.get('boundary') != boundary
            or r.get('scope') != SCOPE or r.get('passed') != 6
            or r.get('failed') != 0 or r.get('skipped') != 0
            or set(r.get('cases', {})) != CASES or any(v is not True for v in r['cases'].values())
            or r.get('seals') != 1 or r.get('new_half_prepared') != 0
            or r.get('business_rows') != int(boundary == 'after')
            or r.get('sdk_executions') != 1 or r.get('half_prepared') != 1
            or type(r.get('new_check_rollback')) is not int
            or (boundary == 'before' and r['new_check_rollback'] < 1)
            or (boundary == 'after' and r['new_check_rollback'] != 0)
            or r.get('full_api_process_paired_provider_system_not_claimed') is not True
            or not re.search(r'--- PASS: TestM3AICommandOriginalCommitPacketFault \(', output)
            or re.search(r'--- (?:FAIL|SKIP):|WARNING: DATA RACE', output)):
        raise RuntimeError('original command fault receipt wrong source, boundary, scope or incomplete')
    return r


def run_profile(source, directory, env, run, proof, native_runner, proxy_start):
    if native_runner is None or proxy_start is None:
        raise RuntimeError('owned native process and wire proxy supervision required')
    results = {}
    for boundary in ('before', 'after'):
        proxy = proxy_start('mysql')
        proxy.send(json.dumps({'Action': 'arm', 'Boundary': boundary, 'Method': 'commit', 'Nth': 1}))
        proxy.wait('armed')
        current = dict(env, QS_M3_FAULT_BOUNDARY=boundary, QS_M3_FAULT_MYSQL_PROXY=proxy.address)
        result = native_runner(['go', 'test', '-race', '-p', '1', '-tags=integration,m3_ai_command_broker,m3_host_faults',
            '-count=1', '-timeout=5m', '-v', './internal/apiserver/infra/mysql/aibridge',
            '-run', '^TestM3AICommandOriginalCommitPacketFault$'], cwd=source, env=current,
            timeout=720, required=False)
        raw = result.stdout + result.stderr
        private = directory / ('qs-command-original-' + boundary + '-private.log')
        retain_private_host_output(private, raw)
        evidence = {'native_exit_code': result.returncode,
            'native_output_sha256': hashlib.sha256(raw.encode()).hexdigest(),
            'assertion_lines': sorted(set(map(int, re.findall(r'transaction_command_packet_fault_integration_test\.go:(\d+)', raw))))[:32],
            'test_timeout': 'panic: test timed out' in raw,
            'race_reports': raw.count('WARNING: DATA RACE')}
        results[boundary] = evidence
        proof['faults'] = results
        if result.returncode:
            raise RuntimeError('actual original QS command packet fault failed; private output withheld')
        evidence['receipt'] = parse_receipt(raw, proof['source_sha'], boundary)
        injected = proxy.wait('injected', timeout=10)
        proxy.send(json.dumps({'Action': 'stats'}))
        stats = proxy.wait('stats')
        evidence['wire'] = wire_evidence(injected, stats, boundary)
        proxy.send(json.dumps({'Action': 'stop'})); proxy.wait('closed'); proxy.finish()
    proof['scope'] = SCOPE
    proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if not proof['source_clean_after']:
        raise RuntimeError('QS source changed during original-root fault proof')
