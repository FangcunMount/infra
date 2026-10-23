"""Original QS AnswerSheet/Mongo root; driver retries remain real packet faults."""
import hashlib
import json
import re

from iam_acceptance import retain_private_host_output

SCOPE = 'actual QS AnswerSheet original Mongo root with wire-level commitTransaction faults; component only'
CASES = frozenset(('actual_answer_root_once', 'business_witness_match_boundary',
    'duplicate_keeps_original_plan_and_result', 'broker_visibility_or_new_paused_checker',
    'published_outboxes_empty', 'owned_owner_and_transport_drained_primary_retained'))


def parse_receipt(output, source, boundary):
    rows = [json.loads(line.removeprefix('M3_QS_ANSWER_FAULT_RECEIPT ')) for line in output.splitlines()
            if line.startswith('M3_QS_ANSWER_FAULT_RECEIPT ')]
    if len(rows) != 1:
        raise RuntimeError('one exact original answer packet-fault receipt required')
    r = rows[0]
    integers = ('passed', 'failed', 'skipped', 'local_calls', 'mongo_callbacks', 'half_prepared',
                'new_half_prepared', 'new_check_commit', 'new_check_rollback', 'business_rows', 'new_local_calls')
    if (not isinstance(r, dict) or not isinstance(r.get('cases'), dict)
            or any(type(r.get(k)) is not int for k in integers)
            or not re.fullmatch('[0-9a-f]{40}', source) or r.get('source_sha') != source
            or boundary not in ('before', 'after') or r.get('boundary') != boundary
            or r.get('scope') != SCOPE or r['passed'] != 6 or r['failed'] != 0 or r['skipped'] != 0
            or set(r['cases']) != CASES or any(v is not True for v in r['cases'].values())
            or r['local_calls'] != 1 or not 1 <= r['mongo_callbacks'] <= 16
            or r['half_prepared'] != 1 or r['new_half_prepared'] != 0 or r['new_local_calls'] != 0
            or r['business_rows'] != int(boundary == 'after') or r.get('wire_unchanged') is not True
            or not 0 <= r['new_check_commit'] <= 1024 or not 0 <= r['new_check_rollback'] <= 1024
            or (boundary == 'before' and (r['new_check_rollback'] < 1 or r['new_check_commit'] != 0))
            or (boundary == 'after' and r['new_check_rollback'] != 0)
            or r.get('full_api_process_provider_system_not_claimed') is not True
            or not re.search(r'--- PASS: TestM3AnswerOriginalCommitPacketFault \(', output)
            or re.search(r'--- (?:FAIL|SKIP):|WARNING: DATA RACE', output)):
        raise RuntimeError('original AnswerSheet packet-fault proof incomplete or outside exact scope')
    return r


def wire_evidence(events, stats, boundary):
    # The pinned Mongo proxy intentionally blocks every matching COMMIT retry,
    # unlike the MySQL one-shot proxy. Successful server ACKs are counted alone.
    if (boundary not in ('before', 'after') or not events
            or any(e.get('kind') != 'mongo' or e.get('boundary') != boundary
                   or e.get('backend_ack') is not (boundary == 'after') for e in events)
            or stats.get('event') != 'stats'
            or any(type(stats.get(k)) is not int or not 1 <= stats[k] <= 1024 for k in ('seen', 'dropped'))
            or type(stats.get('backend_commit_acks')) is not int
            or stats['seen'] != stats['dropped'] or len(events) != stats['dropped']
            or stats['backend_commit_acks'] != (stats['dropped'] if boundary == 'after' else 0)):
        raise RuntimeError('matching original Mongo session COMMIT TCP boundary not established')
    return dict(boundary=boundary, seen=stats['seen'], dropped=stats['dropped'],
                backend_commit_acks=stats['backend_commit_acks'])


def run_profile(source, directory, env, run, proof, native_runner, proxy_start):
    if native_runner is None or proxy_start is None:
        raise RuntimeError('owned native process and wire proxy supervision required')
    proof['faults'] = {}
    for boundary in ('before', 'after'):
        proxy = proxy_start('mongo')
        proxy.send(json.dumps({'Action': 'arm', 'Boundary': boundary, 'Method': 'commit', 'Nth': 1}))
        proxy.wait('armed')
        current = dict(env, QS_M3_FAULT_BOUNDARY=boundary, QS_M3_FAULT_MONGO_PROXY=proxy.address)
        result = native_runner(['go', 'test', '-race', '-p', '1',
            '-tags=integration,m3_answersheet_integration,m3_host_faults', '-count=1', '-timeout=5m', '-v',
            './internal/apiserver/container/internal/transaction', '-run', '^TestM3AnswerOriginalCommitPacketFault$'],
            cwd=source, env=current, timeout=720, required=False)
        raw = result.stdout + result.stderr
        retain_private_host_output(directory / ('qs-answer-original-' + boundary + '-private.log'), raw)
        evidence = dict(native_exit_code=result.returncode, native_output_sha256=hashlib.sha256(raw.encode()).hexdigest(),
            assertion_lines=sorted(set(map(int, re.findall(r'm3_answersheet_packet_fault_integration_test\.go:(\d+)', raw))))[:32],
            test_timeout='panic: test timed out' in raw, race_reports=raw.count('WARNING: DATA RACE'))
        proof['faults'][boundary] = evidence
        if result.returncode:
            raise RuntimeError('actual original AnswerSheet packet fault failed; private output withheld')
        evidence['receipt'] = parse_receipt(raw, proof['source_sha'], boundary)
        proxy.send(json.dumps({'Action': 'stats'})); stats = proxy.wait('stats')
        proxy.drain()
        evidence['wire'] = wire_evidence([e for e in proxy.events if e.get('event') == 'injected'], stats, boundary)
        proxy.send(json.dumps({'Action': 'stop'})); proxy.wait('closed'); proxy.finish()
    proof['scope'] = SCOPE
    proof['source_clean_after'] = not run(['git', 'status', '--porcelain'], cwd=source).stdout.strip()
    if not proof['source_clean_after']:
        raise RuntimeError('QS source changed during original Mongo packet fault proof')
