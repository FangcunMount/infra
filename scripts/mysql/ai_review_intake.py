"""Bind the explicit AI246 self-review policy; never issue production approval."""
import argparse
import shutil
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
POLICY_PATH = ROOT.parents[1] / 'docs/evidence/2026-11-11-ai246-self-review-policy.json'
POLICY_ID = 'AI246-20261111-SHUJIE-SELF-REVIEW'
MODE = 'owner_self_review'
TOOL_SECONDS = 645
BEFORE_ABORT_SECONDS = 555
AFTER_ABORT_VERIFY_SECONDS = 90
WRITER_BOUND_TOOL_SECONDS = 270  # W05 two captures and W07.
WRITER_MAX_SECONDS = 3600
GATES = ('w00', 'w04', 'window')
EXTRA = ('admin_queue_and_receipt', 'two_site_preservation', 'self_review', 'reopen_observation', 'recovery_reserve')
BRIDGE_SCOPE = ('switch_schema_43', 'recover_schema_43')
BRIDGE_EVIDENCE = 'bridge-qualification.json'

def fail(message):
    raise ValueError(message)

def decode(raw):
    def unique(rows):
        result = {}
        for key, value in rows:
            if key in result:
                fail('duplicate JSON field')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)

def utc(value, field):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z', value):
        fail(field + ' must be UTC RFC3339 with Z')
    return datetime.fromisoformat(value[:-1] + '+00:00')

def filled(value, field):
    if not isinstance(value, str) or value.strip() != value or value.casefold() in ('', 'tbd', '待签', '____', 'placeholder'):
        fail(field + ' must identify an actual signer, operator or signed reference')
    return value

def bridge_qualification(raw):
    qualification = decode(raw)
    identities = ('original_image_id', 'bridge_image_id')
    digests = ('prepared_sha256', 'archive_sha256')
    if (set(qualification) != {'schema', 'source_sha', *identities, *digests}
            or qualification['schema'] != 'ai246-schema43-bridge-qualification/v1'
            or not re.fullmatch('[0-9a-f]{40}', qualification['source_sha'])
            or any(not re.fullmatch('sha256:[0-9a-f]{64}', qualification[key]) for key in identities)
            or any(not re.fullmatch('[0-9a-f]{64}', qualification[key]) for key in digests)
            or qualification['original_image_id'] == qualification['bridge_image_id']):
        fail('invalid schema-43 bridge qualification')
    return sha256(raw).hexdigest()

def bridge_appointment(window, qualification_sha):
    if qualification_sha is None:
        if 'bridge' in window:
            fail('schema-43 bridge scope requires bound qualification')
        return {}
    decision = window.get('bridge')
    fields = ('qualification_sha256', 'operation_id', 'database_operation_id',
              'approved_actions', 'budget_seconds')
    if (not isinstance(decision, dict) or set(decision) != set(fields)
            or decision['qualification_sha256'] != qualification_sha
            or decision['approved_actions'] != list(BRIDGE_SCOPE)):
        fail('schema-43 switch and recovery scope must be explicitly accepted')
    operation, database_operation = (decision[key] for key in ('operation_id', 'database_operation_id'))
    if (operation == database_operation or any(
            not isinstance(value, str) or not re.fullmatch(r'ai246-[a-z0-9]+(?:-[a-z0-9]+)*', value)
            for value in (operation, database_operation))):
        fail('distinct bridge and database operation IDs required')
    seconds = decision['budget_seconds']
    if type(seconds) is not int or seconds <= 0:
        fail('schema-43 switch requires a positive window budget')
    return dict(bridge_operation_id=operation, database_operation_id=database_operation,
                bridge_budget_seconds=seconds, bridge_qualification_sha256=qualification_sha)

def validate(evidence, evidence_sha, submitted, now):
    policy_sha = policy_binding()
    if (evidence.get('review_policy_id') != POLICY_ID or evidence.get('review_policy_sha256') != policy_sha
            or evidence.get('review_mode') != MODE or submitted.get('review_policy_id') != POLICY_ID
            or submitted.get('review_policy_sha256') != policy_sha or submitted.get('review_mode') != MODE):
        fail('self-review policy binding changed')
    if evidence.get('appointment_tool_sha256') != sha256(Path(__file__).read_bytes()).hexdigest():
        fail('appointment tool changed')
    if submitted.get('self_review_risk_acknowledged') is not True:
        fail('operation-specific self-review acknowledgement is missing')
    if evidence['status'] != 'PREPARATION_ONLY' or evidence['execution_authorized'] or evidence['w06_issued']:
        fail('unexpected appointment manifest scope')
    if submitted['schema'] != 'ai246-prewindow-self-review/v2':
        fail('appointment form is blank or has a different schema')
    if submitted['infra_review_head'] != evidence['infra_review_head'] or submitted['evidence_sha256'] != evidence_sha:
        fail('appointment review version or evidence changed')
    if (evidence['data_owner'] != 'shujie' or evidence['recovery_owner'] != 'shujie'
            or submitted['data_owner'] != evidence['data_owner'] or submitted['recovery_owner'] != evidence['recovery_owner']):
        fail('responsibility binding changed')
    decisions = submitted['decisions']
    if set(decisions) != set(GATES):
        fail('three distinct decisions are required')
    capture = utc(evidence['captured_at'].replace('+00:00','Z'), 'manifest capture')
    signature_times = {}
    for gate in GATES:
        decision = decisions[gate]
        if decision['result'] != 'accept':
            fail(gate + ' is unsigned or rejected')
        if decision['evidence_sha256'] != evidence_sha:
            fail(gate + ' evidence changed')
        filled(decision['reviewer'], gate + ' reviewer')
        filled(decision['signed_reference'], gate + ' signed reference')
        signature_times[gate] = utc(decision['signed_at'], gate + ' signature')
        if not capture <= signature_times[gate] <= now:
            fail(gate + ' signature is outside the current evidence interval')
    if decisions['w00']['route'] != evidence['reviewable_w00_route']:
        fail('W00 route lacks the required evidence in this packet')
    if decisions['w04']['account_scope'] != 'existing_qualified_account_only':
        fail('W04 alternate account requires separate qualification')
    window = decisions['window']
    operator = filled(window['operator'], 'window operator')
    if operator != 'shujie' or any(decisions[gate]['reviewer'] != 'shujie' for gate in GATES):
        fail('this exception permits only shujie to operate and self-review')
    if window['approved_preparation_actions'] != ['W03', 'W05']:
        fail('the proposed window must explicitly cover only W03 and W05 preparation')
    bridge = bridge_appointment(window, evidence.get('bridge_qualification_sha256'))
    start, abort, end = (utc(window[key], key) for key in ('start','latest_abort','end'))
    if not start < abort < end or end <= now or max(signature_times.values()) > start:
        fail('appointment timestamps or signature order are invalid')
    budgets = window['budgets_seconds']
    if set(budgets) != set(EXTRA) or any(type(value) is not int or value <= 0 for value in budgets.values()):
        fail('all extra window budgets require positive integer seconds')
    w05_sample_floor = evidence['w05_transport_and_comparison_sample_seconds']
    if type(w05_sample_floor) not in (float, int) or not isfinite(w05_sample_floor) or w05_sample_floor <= 0:
        fail('invalid W05 sample floor')
    if budgets['two_site_preservation'] < w05_sample_floor:
        fail('W05 preservation budget is below observed transfer and comparison time')
    bridge_seconds = bridge.get('bridge_budget_seconds', 0)
    before_abort = BEFORE_ABORT_SECONDS + sum(budgets[name] for name in EXTRA[:3]) + bridge_seconds
    total = TOOL_SECONDS + sum(budgets.values()) + bridge_seconds
    after_abort = AFTER_ABORT_VERIFY_SECONDS + budgets['reopen_observation'] + budgets['recovery_reserve']
    writer_interval = WRITER_BOUND_TOOL_SECONDS + budgets['two_site_preservation'] + budgets['self_review']
    if ((abort-start).total_seconds() < before_abort or (end-start).total_seconds() < total):
        fail('window budget does not fit the known tools and additional work')
    if (end-abort).total_seconds() < after_abort:
        fail('after-abort budget must fit verification, reopen observation and recovery')
    if writer_interval > WRITER_MAX_SECONDS:
        fail('writer validity budget is exceeded by W05 through W07')
    return dict(status='FORM_COMPLETE_SELF_REVIEW_IDENTITY_CHECK_PENDING', review_mode=MODE,
                review_policy_sha256=policy_sha, independent_review=False, evidence_sha256=evidence_sha,
                w05_sample_floor_seconds=w05_sample_floor, before_abort_required_seconds=before_abort, after_abort_required_seconds=after_abort,
                minimum_writer_interval_seconds=writer_interval, total_required_seconds=total,
                self_review_identity_verified=False, same_window_evidence_required=True,
                execution_authorized=False, w06_issued=False, **bridge)


def policy_binding():
    raw = POLICY_PATH.read_bytes()
    policy = decode(raw)
    if (policy.get('schema') != 'ai246-review-policy/v1' or policy.get('policy_id') != POLICY_ID
            or policy.get('review_mode') != MODE or policy.get('actor_id') != 'shujie'
            or policy.get('data_owner') != 'shujie' or policy.get('recovery_owner') != 'shujie'
            or policy.get('authorization', {}).get('mode_change_authorized') is not True
            or policy.get('authorization', {}).get('independent_review_claimed') is not False
            or any(policy.get(key) is not False for key in ('window_authorized', 'execution_authorized', 'w06_issued'))):
        fail('unexpected self-review policy scope')
    return sha256(raw).hexdigest()


def checked_bundle(root):
    manifest = (root / 'manifest.json').read_bytes()
    evidence = decode(manifest)
    if evidence['status'] != 'PREPARATION_ONLY' or evidence['execution_authorized'] or evidence['w06_issued']:
        fail('unexpected appointment manifest scope')
    for filename, field in (('timing.json', 'timing_sha256'), ('transport.json', 'transport_sha256'),
                            ('comparison.json', 'comparison_sha256')):
        if sha256((root / filename).read_bytes()).hexdigest() != evidence[field]:
            fail(f'{filename.removesuffix(".json")} evidence changed')
    if evidence['reviewable_w00_route'] == 'central_continuity':
        central = (root / 'central-binding.json').read_bytes()
        if sha256(central).hexdigest() != evidence['central_evidence_sha256']:
            fail('central evidence binding changed')
        members = decode(central)['member_sha256']
        if set(members) != {'capture.json', 'central.json', 'receipt.json'} or any(
                sha256((root / name).read_bytes()).hexdigest() != digest for name, digest in members.items()):
            fail('central original bytes changed')
    if 'qualification_manifest_sha256' in evidence:
        if sha256((root / 'source-manifest.json').read_bytes()).hexdigest() != evidence['qualification_manifest_sha256']:
            fail('qualification manifest changed')
    if 'bridge_qualification_sha256' in evidence:
        if bridge_qualification((root / BRIDGE_EVIDENCE).read_bytes()) != evidence['bridge_qualification_sha256']:
            fail('schema-43 bridge qualification changed')
    return evidence, sha256(manifest).hexdigest()


def blank_decision(evidence, evidence_sha):
    def gate():
        return dict(result=None, reviewer='shujie', signed_at=None, signed_reference=None,
                    evidence_sha256=evidence_sha)
    form = dict(schema='ai246-prewindow-self-review/TEMPLATE', review_mode=MODE,
                review_policy_id=POLICY_ID, review_policy_sha256=policy_binding(),
                self_review_risk_acknowledged=None, infra_review_head=evidence['infra_review_head'],
                evidence_sha256=evidence_sha, data_owner='shujie', recovery_owner='shujie',
                decisions=dict(w00=dict(gate(), route=evidence['reviewable_w00_route']),
                               w04=dict(gate(), account_scope='existing_qualified_account_only'),
                               window=dict(gate(), operator='shujie', start=None, latest_abort=None, end=None,
                                           approved_preparation_actions=[],
                                           budgets_seconds=dict.fromkeys(EXTRA))))
    if 'bridge_qualification_sha256' in evidence:
        form['decisions']['window']['bridge'] = dict(
            qualification_sha256=evidence['bridge_qualification_sha256'], operation_id=None,
            database_operation_id=None, approved_actions=[], budget_seconds=None)
    return form


def write_private(path, raw):
    with path.open('xb') as stream:
        path.chmod(0o600)
        stream.write(raw)


def prepare(source, output, head, bridge_evidence=None):
    if not re.fullmatch('[0-9a-f]{40}', head):
        fail('infra review head must be an exact commit')
    evidence, original_sha = checked_bundle(source)
    if evidence['data_owner'] != 'shujie' or evidence['recovery_owner'] != 'shujie':
        fail('responsibility binding changed')
    old_bridge_sha = evidence.get('bridge_qualification_sha256')
    if bridge_evidence is None and old_bridge_sha is not None:
        bridge_evidence = source / BRIDGE_EVIDENCE
    bridge_raw = bridge_evidence.read_bytes() if bridge_evidence is not None else None
    if bridge_raw is not None:
        bridge_sha = bridge_qualification(bridge_raw)
        if old_bridge_sha is not None and old_bridge_sha != bridge_sha:
            fail('schema-43 bridge qualification cannot be silently replaced')
        evidence['bridge_qualification_sha256'] = bridge_sha
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    names = ['timing.json', 'transport.json', 'comparison.json']
    if evidence['reviewable_w00_route'] == 'central_continuity':
        names += ['central-binding.json', 'capture.json', 'central.json', 'receipt.json']
    for name in names:
        shutil.copyfile(source / name, output / name)
        (output / name).chmod(0o600)
    write_private(output / 'source-manifest.json', (source / 'manifest.json').read_bytes())
    if bridge_raw is not None:
        write_private(output / BRIDGE_EVIDENCE, bridge_raw)
    evidence.update(schema='ai246-prewindow-review-manifest/v4',
                    qualification_manifest_sha256=original_sha,
                    qualification_infra_review_head=evidence['infra_review_head'],
                    infra_review_head=head, review_mode=MODE, review_policy_id=POLICY_ID,
                    review_policy_sha256=policy_binding(),
                    appointment_tool_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    # Keep original capture timestamps and freshness requirements; rebinding is not a new observation.
    raw = (json.dumps(evidence, ensure_ascii=False, indent=2) + '\n').encode()
    write_private(output / 'manifest.json', raw)
    write_private(output / 'decision-TEMPLATE.json',
                  (json.dumps(blank_decision(evidence, sha256(raw).hexdigest()), ensure_ascii=False, indent=2) + '\n').encode())
    return dict(status='SELF_REVIEW_TEMPLATE_PREPARED', evidence_sha256=sha256(raw).hexdigest(),
                review_mode=MODE, observation_refreshed=False, execution_authorized=False, w06_issued=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('prepare', help='Copy and bind historical/read-only originals; no approval is issued')
    create.add_argument('--bundle', type=Path, required=True)
    create.add_argument('--output', type=Path, required=True)
    create.add_argument('--infra-review-head', required=True)
    create.add_argument('--bridge-qualification', type=Path)
    check = sub.add_parser('check', help='Check a signed appointment form; identity remains separately verified')
    check.add_argument('--bundle', type=Path, required=True)
    check.add_argument('--decision', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            report = prepare(args.bundle, args.output, args.infra_review_head, args.bridge_qualification)
        else:
            evidence, evidence_sha = checked_bundle(args.bundle)
            incoming = args.decision.read_bytes()
            report = validate(evidence, evidence_sha, decode(incoming), datetime.now(timezone.utc))
            report['submitted_sha256'] = sha256(incoming).hexdigest()
    except (ValueError, KeyError, TypeError, IndexError, OSError) as error:
        print(json.dumps(dict(status='NO_GO', reason=str(error), execution_authorized=False, w06_issued=False)))
        return 1
    print(json.dumps(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
