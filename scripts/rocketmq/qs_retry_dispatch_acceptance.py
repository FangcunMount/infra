"""T13 actual due dispatch over the original evaluation/report host entrypoints."""
import json
import os
import re

from qs_evaluation_acceptance import run_qs_evaluation_host
from qs_report_acceptance import run_qs_report_host

CASES = frozenset(('no_half_before_real_due', 'first_wire_and_dispatch_witness',
                   'no_business_attempt_or_input_repeat', 'repeat_dispatch_is_empty',
                   'automatic_pause_before_reservation', 'real_root_abort_witness',
                   'scan_does_not_retry_aborted', 'explicit_retry_same_plan_new_fence',
                   'old_aborted_evidence_retained'))


def parse_dispatch_receipt(output, owner):
    expected_test = {'qs.mysql': 'TestM3FailureBrokerHost', 'qs.mongo': 'TestM3ReportTerminalBrokerHost'}.get(owner)
    receipts = [json.loads(line.split('M3_QS_RETRY_DISPATCH_RECEIPT ', 1)[1])
                for line in output.splitlines() if 'M3_QS_RETRY_DISPATCH_RECEIPT {' in line]
    if (expected_test is None or len(receipts) != 1 or receipts[0].get('owner') != owner
            or receipts[0].get('passed') != len(CASES) or receipts[0].get('failed') != 0
            or receipts[0].get('skipped') != 0 or set(receipts[0].get('cases', {})) != CASES
            or any(value is not True for value in receipts[0]['cases'].values())
            or receipts[0].get('system_login_not_claimed') is not True
            or receipts[0].get('business_consumer_not_claimed') is not True
            or not re.search(r'--- PASS: ' + expected_test + r' \(', output)
            or re.search(r'--- (?:SKIP|FAIL):|WARNING: DATA RACE', output)):
        raise RuntimeError('QS due dispatch receipt absent, wrong owner, incomplete, failed or skipped')
    return receipts[0]


def readable_future_mode(env):
    mode = env.get('QS_M3_READABLE_FUTURE', '0')
    if mode not in ('0', '1'):
        raise ValueError('explicit owned readable future profile required')
    if mode == '1':
        from final_image_candidate import ci_guard
        ci_guard(env)
    return mode == '1'


def run_qs_retry_dispatch_host(source, directory, broker, project, grpc_port, mysql_port, mongo_port, password, ca, run, proof):
    readable = readable_future_mode(os.environ)
    proof['evaluation'], proof['report'] = {}, {}
    run_qs_evaluation_host(source, directory, broker, project, grpc_port, mysql_port, password, ca, run, proof['evaluation'], readable=readable)
    evaluation = parse_dispatch_receipt((directory / 'qs-evaluation-host-private.log').read_text(), 'qs.mysql')
    run_qs_report_host(source, directory, broker, project, grpc_port, mongo_port, ca, run, proof['report'], readable=readable)
    report = parse_dispatch_receipt((directory / 'qs-report-host-private.log').read_text(), 'qs.mongo')
    if proof['evaluation']['source_sha'] != proof['report']['source_sha']:
        raise RuntimeError('paired due dispatch used different source revisions')
    proof['source_sha'] = proof['evaluation']['source_sha']
    proof['readable'] = readable
    proof['dispatch_receipts'] = {'qs.mysql': evaluation, 'qs.mongo': report}
    cases = {}
    for domain in ('evaluation', 'report'):
        cases.update({domain + '_' + name: value for name, value in proof[domain]['native_receipt']['cases'].items()})
    for owner, receipt in proof['dispatch_receipts'].items():
        cases.update({owner + '_' + name: value for name, value in receipt['cases'].items()})
    if len(cases) != 41:
        raise RuntimeError('paired host and due-dispatch matrix incomplete')
    proof['native_receipt'] = {'passed': len(cases), 'failed': 0, 'skipped': 0, 'cases': cases}
    proof['scope'] = ('actual original evaluation failure/report terminal roots, real future deadline, pause, root rollback and explicitly authorized same-plan Broker redispatch; '
                      'observer ACK only, no next business consumer, provider call, system, packet-loss or ownership handoff claim')
