from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from ai_review_intake import decode, validate, policy_binding, POLICY_ID, MODE, prepare
from hashlib import sha256
import ai_review_intake

NOW = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
HASH = 'a' * 64

class ReviewIntakeTests(unittest.TestCase):
    def setUp(self):
        self.evidence = dict(status='PREPARATION_ONLY', execution_authorized=False, w06_issued=False,
                             infra_review_head='b'*40, data_owner='shujie', recovery_owner='shujie',
                             captured_at='2026-01-01T10:00:00+00:00', reviewable_w00_route='named_direct',
                             w05_transport_and_comparison_sample_seconds=37.098,
                             review_policy_id=POLICY_ID, review_policy_sha256=policy_binding(), review_mode=MODE,
                             appointment_tool_sha256=sha256(Path(ai_review_intake.__file__).read_bytes()).hexdigest())
        def decision():
            return dict(result='accept', reviewer='shujie', signed_at='2026-01-01T11:00:00Z',
                        signed_reference='test-fixture-signature', evidence_sha256=HASH)
        self.submitted = dict(schema='ai246-prewindow-self-review/v2', review_mode=MODE,
                              review_policy_id=POLICY_ID, review_policy_sha256=policy_binding(),
                              self_review_risk_acknowledged=True, infra_review_head='b'*40, evidence_sha256=HASH,
                              data_owner='shujie', recovery_owner='shujie',
                              decisions=dict(w00=dict(decision(),route='named_direct'),
                                  w04=dict(decision(),account_scope='existing_qualified_account_only'),
                                  window=dict(decision(),operator='shujie',approved_preparation_actions=['W03','W05'],
                                      start='2026-01-01T13:00:00Z',latest_abort='2026-01-01T13:25:00Z',end='2026-01-01T13:40:00Z',
                                      budgets_seconds=dict(admin_queue_and_receipt=120,two_site_preservation=90,self_review=120,
                                                           reopen_observation=120,recovery_reserve=600))))

    def result(self):
        return validate(self.evidence, HASH, self.submitted, NOW)

    def test_complete_form_cannot_authorize_execution(self):
        out = self.result()
        self.assertEqual('FORM_COMPLETE_SELF_REVIEW_IDENTITY_CHECK_PENDING', out['status'])
        self.assertFalse(out['self_review_identity_verified'])
        self.assertFalse(out['execution_authorized'])
        self.assertFalse(out['w06_issued'])

    def test_rejected_gate(self):
        self.submitted['decisions']['w00']['result'] = 'reject'
        with self.assertRaisesRegex(ValueError, 'unsigned or rejected'):
            self.result()

    def test_alternate_account(self):
        self.submitted['decisions']['w04']['account_scope'] = 'different'
        with self.assertRaisesRegex(ValueError, 'separate qualification'):
            self.result()

    def test_stale_evidence(self):
        self.submitted['decisions']['w04']['evidence_sha256'] = 'c'*64
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            self.result()

    def test_exception_cannot_be_used_by_another_actor(self):
        self.submitted['decisions']['w04']['reviewer'] = 'another-actor'
        with self.assertRaisesRegex(ValueError, 'only shujie'):
            self.result()

    def test_missing_recovery_time(self):
        self.submitted['decisions']['window']['latest_abort'] = '2026-01-01T13:39:00Z'
        with self.assertRaisesRegex(ValueError, 'budget'):
            self.result()

    def test_after_abort_requires_verification_and_reopen_in_addition_to_recovery(self):
        self.submitted['decisions']['window']['latest_abort'] = '2026-01-01T13:29:00Z'
        with self.assertRaisesRegex(ValueError, 'after-abort budget'):
            self.result()

    def test_long_preservation_cannot_fit_one_hour_writer_validity(self):
        window=self.submitted['decisions']['window']
        window['budgets_seconds']['two_site_preservation']=3500
        window['latest_abort']='2026-01-01T14:15:00Z'
        window['end']='2026-01-01T14:40:00Z'
        with self.assertRaisesRegex(ValueError, 'writer validity budget'):
            self.result()

    def test_budget_fields_cover_separate_tail_and_writer_interval(self):
        result=self.result()
        self.assertEqual(result['after_abort_required_seconds'],810)
        self.assertEqual(result['minimum_writer_interval_seconds'],480)

    def test_w05_budget_cannot_be_below_the_sample(self):
        budgets = self.submitted['decisions']['window']['budgets_seconds']
        budgets['two_site_preservation'] = 37
        with self.assertRaisesRegex(ValueError, 'below observed transfer and comparison'):
            self.result()
        budgets['two_site_preservation'] = 38
        self.assertEqual(self.result()['w05_sample_floor_seconds'], 37.098)

    def test_nonfinite_w05_floor_is_rejected(self):
        self.evidence['w05_transport_and_comparison_sample_seconds'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'invalid W05 sample floor'):
            self.result()

    def test_disallow_production_execution_scope(self):
        self.submitted['decisions']['window']['approved_preparation_actions'].append('W07')
        with self.assertRaisesRegex(ValueError, 'only W03 and W05'):
            self.result()

    def test_bridge_acceptance_binds_both_operations_and_window_budget(self):
        window = self.submitted['decisions']['window']
        self.evidence['bridge_qualification_sha256'] = HASH
        with self.assertRaisesRegex(ValueError, 'explicitly accepted'):
            self.result()
        window['bridge'] = dict(
            qualification_sha256=HASH, operation_id='ai246-bridge-test',
            database_operation_id='ai246-ddl-test', approved_actions=list(ai_review_intake.BRIDGE_SCOPE),
            budget_seconds=300)
        result = self.result()
        self.assertEqual(result['bridge_operation_id'], 'ai246-bridge-test')
        self.assertEqual(result['database_operation_id'], 'ai246-ddl-test')
        self.assertEqual(result['before_abort_required_seconds'], 1185)
        self.assertEqual(result['minimum_writer_interval_seconds'], 480)
        self.assertFalse(result['execution_authorized'])
        self.assertFalse(result['w06_issued'])
        bridge = window['bridge']
        with self.subTest('same ID'):
            bridge['database_operation_id'] = bridge['operation_id']
            with self.assertRaisesRegex(ValueError, 'distinct'):
                self.result()
            bridge['database_operation_id'] = 'ai246-ddl-test'
        with self.subTest('insufficient time before abort'):
            bridge['budget_seconds'] = 700
            with self.assertRaisesRegex(ValueError, 'window budget'):
                self.result()
            bridge['budget_seconds'] = 300
        with self.subTest('qualification drift'):
            bridge['qualification_sha256'] = 'c'*64
            with self.assertRaisesRegex(ValueError, 'explicitly accepted'):
                self.result()
            bridge['qualification_sha256'] = HASH
        with self.subTest('undeclared scope'):
            self.evidence.pop('bridge_qualification_sha256')
            with self.assertRaisesRegex(ValueError, 'bound qualification'):
                self.result()

    def test_prepare_binds_bridge_original_and_rejects_drift(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            source = root / 'source'
            source.mkdir()
            evidence = dict(self.evidence)
            for name in ('timing', 'transport', 'comparison'):
                raw = b'{}'
                (source / (name + '.json')).write_bytes(raw)
                evidence[name + '_sha256'] = sha256(raw).hexdigest()
            (source / 'manifest.json').write_text(json.dumps(evidence))
            qualification = root / 'qualification.json'
            raw = json.dumps(dict(schema='ai246-schema43-bridge-qualification/v1',
                                  source_sha='a'*40, original_image_id='sha256:'+'a'*64,
                                  bridge_image_id='sha256:'+'b'*64, prepared_sha256='c'*64,
                                  archive_sha256='d'*64)).encode()
            qualification.write_bytes(raw)
            output = root / 'bound'
            prepare(source, output, 'c'*40, qualification)
            bound, _ = ai_review_intake.checked_bundle(output)
            form = decode((output / 'decision-TEMPLATE.json').read_bytes())
            bridge = form['decisions']['window']['bridge']
            self.assertEqual(bound['bridge_qualification_sha256'], sha256(raw).hexdigest())
            self.assertEqual(bridge['qualification_sha256'], bound['bridge_qualification_sha256'])
            self.assertIsNone(bridge['operation_id'])
            self.assertIsNone(bridge['database_operation_id'])
            self.assertEqual(bridge['approved_actions'], [])
            proof = output / ai_review_intake.BRIDGE_EVIDENCE
            self.assertEqual(proof.read_bytes(), raw)
            self.assertEqual(proof.stat().st_mode & 0o777, 0o600)
            proof.write_bytes(raw+b' ')
            with self.assertRaisesRegex(ValueError, 'qualification changed'):
                ai_review_intake.checked_bundle(output)

    def test_cli_rejects_timing_evidence_drift(self):
        for name in ('timing', 'transport', 'comparison'):
            with self.subTest(name=name):
                self.assert_rejects_drift(name)

    def assert_rejects_drift(self, drift):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            evidence = dict(self.evidence)
            for name in ('timing', 'transport', 'comparison'):
                raw = b'{}'
                (root / (name + '.json')).write_bytes(raw)
                evidence[name + '_sha256'] = sha256(raw).hexdigest()
            (root / 'manifest.json').write_text(json.dumps(evidence))
            (root / 'decision.json').write_text(json.dumps(self.submitted))
            (root / f'{drift}.json').write_bytes(b'{} ')
            result = subprocess.run([sys.executable, ai_review_intake.__file__, 'check',
                                     '--bundle', str(root), '--decision', str(root / 'decision.json')],
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['reason'], f'{drift} evidence changed')

    def test_old_signature_and_duplicate_json(self):
        self.submitted['decisions']['w00']['signed_at'] = '2026-01-01T09:00:00Z'
        with self.assertRaisesRegex(ValueError, 'signature'):
            self.result()
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            decode(b'{"evidence_sha256":1,"evidence_sha256":2}')

    def test_explicit_operation_acknowledgement_is_required(self):
        self.submitted['self_review_risk_acknowledged'] = None
        with self.assertRaisesRegex(ValueError, 'acknowledgement'):
            self.result()

    def test_policy_or_tool_drift_rejects(self):
        for target, field, value in ((self.submitted, 'review_policy_sha256', 'c'*64),
                                     (self.submitted, 'review_mode', 'independent'),
                                     (self.evidence, 'review_policy_id', 'other'),
                                     (self.evidence, 'appointment_tool_sha256', 'd'*64)):
            with self.subTest(field=field):
                old = target[field]
                target[field] = value
                with self.assertRaises(ValueError):
                    self.result()
                target[field] = old

    def test_legacy_form_is_not_implicitly_converted(self):
        self.submitted['schema'] = 'ai246-prewindow-decision/v1'
        with self.assertRaisesRegex(ValueError, 'schema'):
            self.result()

    def test_prepare_preserves_original_time_and_does_not_sign(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            source = root / 'source'
            source.mkdir()
            evidence = dict(self.evidence)
            for name in ('timing', 'transport', 'comparison'):
                raw = b'{}'
                (source / (name + '.json')).write_bytes(raw)
                evidence[name + '_sha256'] = sha256(raw).hexdigest()
            raw = json.dumps(evidence).encode()
            (source / 'manifest.json').write_bytes(raw)
            output = root / 'bound'
            result = prepare(source, output, 'c'*40)
            bound = decode((output / 'manifest.json').read_bytes())
            form = decode((output / 'decision-TEMPLATE.json').read_bytes())
            self.assertEqual(bound['captured_at'], evidence['captured_at'])
            self.assertEqual(bound['qualification_manifest_sha256'], sha256(raw).hexdigest())
            self.assertEqual((source / 'manifest.json').read_bytes(), raw)
            self.assertEqual(bound['infra_review_head'], 'c'*40)
            self.assertFalse(result['observation_refreshed'])
            self.assertFalse(result['execution_authorized'])
            self.assertIsNone(form['self_review_risk_acknowledged'])
            self.assertTrue(all(form['decisions'][gate]['result'] is None for gate in ('w00', 'w04', 'window')))
            with self.assertRaisesRegex(ValueError, 'acknowledgement'):
                validate(bound, result['evidence_sha256'], form, NOW)
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            self.assertEqual((output / 'decision-TEMPLATE.json').stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                prepare(source, output, 'c'*40)

    def test_central_original_drift_and_missing_original_reject(self):
        from ai_review_intake import checked_bundle
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            evidence = dict(self.evidence, reviewable_w00_route='central_continuity')
            for name in ('timing', 'transport', 'comparison'):
                (root / (name + '.json')).write_bytes(b'{}')
                evidence[name + '_sha256'] = sha256(b'{}').hexdigest()
            members = dict.fromkeys(('capture.json', 'central.json', 'receipt.json'), sha256(b'{}').hexdigest())
            for name in members:
                (root / name).write_bytes(b'{}')
            central = json.dumps(dict(member_sha256=members)).encode()
            (root / 'central-binding.json').write_bytes(central)
            evidence['central_evidence_sha256'] = sha256(central).hexdigest()
            (root / 'manifest.json').write_text(json.dumps(evidence))
            checked_bundle(root)
            (root / 'central.json').write_bytes(b'{} ')
            with self.assertRaisesRegex(ValueError, 'central original bytes changed'):
                checked_bundle(root)
            (root / 'central.json').unlink()
            with self.assertRaises(OSError):
                checked_bundle(root)
