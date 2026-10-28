"""Explicit owned host cross-route Replan; never installed in a runtime image."""
import hashlib
import json
import os
from pathlib import Path
import re

from final_image_candidate import ci_guard
from iam_acceptance import host_failure_summary
from routes import validate

CASES = frozenset(('old_unknown_replan_refused_without_business', 'historical_ordinary_retry_refused',
    'explicit_aborted_replan_retains_wire_and_prior_evidence', 'actual_readable_publish_original_root_and_one_effect',
    'committed_replan_refused_no_duplicate_execution'))
STAGES = frozenset(('configuration', 'construct_owner', 'start_owner', 'reserve_old', 'refuse_unknown',
    'refuse_historical_retry', 'abort_old', 'replan', 'verify_artifacts', 'start_consumer', 'commit',
    'consume', 'refuse_committed'))
PROTECTION_REASONS = frozenset(('', 'native_transaction_limit', 'invalid_check', 'binding_conflict',
    'observation_unavailable', 'invalid_observation', 'metadata_conflict', 'confirmation_age_unavailable',
    'committed_half_unobserved', 'confirmation_gap', 'preparation_expired', 'checker_saturated'))


def commit_states(raw):
    """Parse fixed classifications only, even if an untrusted error mimics a record."""
    states=[]
    for line in raw.splitlines():
        if not line.startswith('READABLE_REPLAN_COMMIT_STATE '):continue
        try:value=json.loads(line.removeprefix('READABLE_REPLAN_COMMIT_STATE '))
        except (ValueError,TypeError):continue
        if not isinstance(value,dict):continue
        state={key:value[key] for key in ('lease_expired','ready','admission_closed','stale_execution',
            'binding_error','invalid_plan','root_required','schema_error','deadline','canceled')
            if type(value.get(key)) is bool}
        if value.get('local') in ('not_started','committed','aborted','unknown'):state['local']=value['local']
        for key,maximum in (('business_calls',16),('mysql_number',65535)):
            if type(value.get(key)) is int and 0<=value[key]<=maximum:state[key]=value[key]
        protection=value.get('protection')
        if isinstance(protection,dict):
            safe={key:protection[key] for key in ('available','fresh','protected') if type(protection.get(key)) is bool}
            if isinstance(protection.get('reason'),str) and protection['reason'] in PROTECTION_REASONS:safe['reason']=protection['reason']
            state['protection']=safe
        branches=value.get('branches')
        if isinstance(branches,list):
            safe=[]
            for branch in branches[:16]:
                if not isinstance(branch,dict):continue
                row={}
                for key,allowed in (('half',('not_attempted','prepared','rejected','unknown')),
                    ('final',('not_attempted','commit_confirmed','rollback_confirmed','unknown')),
                    ('code',('', 'unclassified','half_unknown','half_rejected_grpc_permission_denied',
                             'half_rejected_grpc_unauthenticated','invalid_half_receipt','half_audit_failed','final_audit_failed'))):
                    if isinstance(branch.get(key),str) and branch[key] in allowed:row[key]=branch[key]
                safe.append(row)
            state['branches']=safe
        states.append(state)
    return states[-4:]


def diagnostics(raw):
    """Only reviewed stage names, source line numbers and fixed classifications."""
    result = host_failure_summary(raw)
    assertion_output = '\n'.join(line for line in raw.splitlines() if 'READABLE_REPLAN_STAGE' not in line)
    result['assertion_lines'] = sorted(set(int(n) for n in re.findall(
        r'readable_owned_replan_test\.go:(\d+)', assertion_output)))[:32]
    result['stages'] = [stage for stage in re.findall(r'READABLE_REPLAN_STAGE ([a-z_]+)',raw)
                        if stage in STAGES][-32:]
    result['error_markers'] = [key for key,text in (
        ('invalid_plan','invalid frozen transaction plan'),
        ('binding','transaction owner, store identity or epoch mismatch'),
        ('stale_execution','transaction execution is not owned or no longer prepared'),
        ('missing_table','Error 1146'),('access_denied','Error 1045')) if text in raw]
    result['commit_states'] = commit_states(raw)
    return result


def enabled(environment, readable):
    mode = environment.get('QS_M3_READABLE_REPLAN', '0')
    if mode not in ('0', '1') or (mode == '1' and not readable):
        raise ValueError('explicit_readable_replan_profile_required')
    if mode == '1':ci_guard(environment)
    return mode == '1'


def receipt(raw, source):
    rows = [json.loads(line.split('READABLE_REPLAN_RECEIPT ',1)[1]) for line in raw.splitlines()
            if 'READABLE_REPLAN_RECEIPT {' in line]
    if (len(rows) != 1 or rows[0].get('source_sha') != source
            or rows[0].get('passed') != len(CASES) or type(rows[0].get('passed')) is not int
            or rows[0].get('failed') != 0 or rows[0].get('skipped') != 0
            or set(rows[0].get('cases',{})) != CASES or not all(v is True for v in rows[0]['cases'].values())
            or rows[0].get('scope') != 'actual_mysql_host_root_and_readable_broker_no_provider_or_system'
            or not re.search(r'--- PASS: TestReadableCrossRouteReplanBrokerHost \(',raw)
            or re.search(r'--- (?:FAIL|SKIP):|WARNING: DATA RACE',raw)):
        raise RuntimeError('actual_readable_replan_receipt_missing_or_invalid')
    return rows[0]


def run_replan(source, directory, route_path, environment, run, proof):
    ci_guard(os.environ)
    if not enabled(environment, True):raise ValueError('explicit_readable_replan_profile_required')
    from qs_evaluation_acceptance import evaluation_manifest
    original = route_path.read_bytes()
    manifest = json.loads(original)
    if manifest != evaluation_manifest(readable=True):raise ValueError('exact_owned_evaluation_manifest_required')
    manifest['historical_routes'] = evaluation_manifest()['routes']
    validate(manifest)
    fixture = Path(__file__).parent/'image_fixtures/readable_replan_test.go'
    target = source/'internal/apiserver/infra/mysql/eventtransaction/readable_owned_replan_test.go'
    if target.exists() or target.is_symlink():raise ValueError('existing_host_test_overlay_refused')
    code = fixture.read_bytes()
    proof['route_replan'] = detail = dict(fixture_sha256=hashlib.sha256(code).hexdigest(),
        original_route_sha256=hashlib.sha256(original).hexdigest(),source_sha=proof['source_sha'],
        production=False,system_acceptance=False,
        diagnostic_only=environment.get('DIAGNOSTIC_ONLY')=='true')
    try:
        target.write_bytes(code)
        route_path.write_text(json.dumps(manifest));route_path.chmod(0o600)
        result = run(['go','test','-p','1','-race','-tags=integration,m3_evaluation_broker','-count=1',
            '-timeout=4m','-v','./internal/apiserver/infra/mysql/eventtransaction',
            '-run','^TestReadableCrossRouteReplanBrokerHost$'],cwd=source,timeout=300,required=False,
            env=dict(environment,QS_M3_REPLAN_SOURCE_SHA=proof['source_sha']))
        raw = result.stdout + result.stderr
        log = directory/'readable-replan-private.log';log.write_text(raw);log.chmod(0o600)
        detail.update(exit_code=result.returncode,private_output_sha256=hashlib.sha256(raw.encode()).hexdigest(),
                      diagnostics=diagnostics(raw))
        if result.returncode:raise RuntimeError('actual_readable_replan_failed_private_output_withheld')
        detail['native_receipt'] = receipt(raw,proof['source_sha'])
    finally:
        if target.exists():
            if target.is_symlink() or target.read_bytes()!=code:raise RuntimeError('owned_overlay_changed_refuse_removal')
            target.unlink()
        route_path.write_bytes(original);route_path.chmod(0o600)
        detail['source_clean_after'] = not run(['git','status','--porcelain'],cwd=source).stdout.strip()
        if not detail['source_clean_after']:raise RuntimeError('host_source_changed_during_replan')
    base = proof['native_receipt']
    cases = dict(base['cases'], **{'route_replan_'+k:v for k,v in detail['native_receipt']['cases'].items()})
    proof['native_receipt'] = dict(base,passed=len(cases),failed=0,skipped=0,cases=cases)
