import json
import unittest
from qs_recovery_acceptance import CASES, RECOVERY_MODULE, parse_recovery_receipt, validate_recovery_module


class CurrentRecoveryReceiptTest(unittest.TestCase):
    def receipt(self):
        return dict(source_sha='a'*40, passed=len(CASES), failed=0, skipped=0,
                    cases={k: True for k in CASES}, real_redis=True,
                    broker_sigkill=True, worker_sigkill=True, controlled_provider=True,
                    owned_databases_dropped=True, no_existing_storage=True,
                    no_production=True, worker_pids_distinct=True,
                    processing_lease_observed=True, processing_lease_ttl_ms=299000,
                    proxy_routes_ready=True, proxy_routes_checked=8)

    def output(self, value, tail=''):
        return 'M3C_QS_RECOVERY_RECEIPT '+json.dumps(value)+'\n--- PASS: TestM3HostRetirementRecovery (1s)\n'+tail

    def test_published_module_is_exact_without_replacement(self):
        validate_recovery_module(dict(RECOVERY_MODULE))
        for field in ('Path', 'Version', 'Sum', 'GoModSum', 'Replace'):
            with self.subTest(field=field):
                row=dict(RECOVERY_MODULE);row[field]='wrong'
                with self.assertRaises(RuntimeError):validate_recovery_module(row)

    def test_current_profile_uses_readable_routes_and_full_worker_subscriptions(self):
        from pathlib import Path
        from qs_runtime_acceptance import runtime_manifest
        from m3_resources import manifest
        root=Path(__file__).resolve().parents[2]
        current=runtime_manifest(root, recovery=True)
        self.assertEqual(current['version'], 3)
        self.assertTrue(all(r['naming_scheme']=='readable-v1' for r in current['routes']))
        required=set(manifest(root)['accounts']['m3-qs-worker']['subscriptions'])
        self.assertTrue(required <= set(current['accounts']['m3-qs-worker']['subscriptions']))
        self.assertIn('qs-recovery-hotrank', current['accounts']['m3-qs-worker']['subscriptions'])

    def test_complete_current_source_receipt(self):
        self.assertEqual(parse_recovery_receipt(self.output(self.receipt()), 'a'*40)['passed'], 14)

    def test_missing_or_false_physical_boundaries_rejected(self):
        for field in ('proxy_routes_ready', 'processing_lease_observed', 'real_redis', 'broker_sigkill', 'worker_sigkill', 'worker_pids_distinct', 'owned_databases_dropped'):
            with self.subTest(field=field):
                row=self.receipt(); row[field]=False
                with self.assertRaises(RuntimeError):parse_recovery_receipt(self.output(row), 'a'*40)

    def test_actual_proxy_route_coverage_is_required(self):
        for value in (None, True, 0, 129):
            with self.subTest(routes=value):
                row=self.receipt();row['proxy_routes_checked']=value
                with self.assertRaises(RuntimeError):parse_recovery_receipt(self.output(row), 'a'*40)

    def test_actual_lease_ttl_is_required_and_bounded(self):
        for value in (None, True, 0, -1, 300001):
            with self.subTest(ttl=value):
                row=self.receipt();row['processing_lease_ttl_ms']=value
                with self.assertRaises(RuntimeError):parse_recovery_receipt(self.output(row), 'a'*40)

    def test_wrong_source_missing_case_and_old_receipt_rejected(self):
        for change in ('source', 'case', 'old'):
            with self.subTest(change=change):
                row=self.receipt()
                if change=='source':row['source_sha']='b'*40
                if change=='case':row['cases'].pop(next(iter(CASES)))
                output=self.output(row)
                if change=='old':output=output.replace('M3C_QS_RECOVERY_RECEIPT ', 'M3_QS_DEFAULT_OWNER_RECEIPT ')
                with self.assertRaises(RuntimeError):parse_recovery_receipt(output, 'a'*40)

    def test_skipped_failed_duplicate_or_race_output_rejected(self):
        for suffix in ('--- SKIP: hidden (1s)', '--- FAIL: hidden (1s)', 'WARNING: DATA RACE', self.output(self.receipt())):
            with self.subTest(suffix=suffix[:20]):
                with self.assertRaises(RuntimeError):parse_recovery_receipt(self.output(self.receipt(), suffix), 'a'*40)


if __name__=='__main__':unittest.main()

class RecoveryDiagnosticTest(unittest.TestCase):
    def sample(self):
        return dict(stage='failure', ensure_calls=2, reminder_visits=[True]*4, provider_calls=4,
            assessment_read_ok=True, assessments=[dict(status='evaluated',count=1)], run_read_ok=True,
            runs=[dict(status='succeeded',attempt=1,disposition='',lease_expired=True)],
            dead_letter_read_ok=True, dead_letters=[dict(event_type='evaluation.outcome.committed',attempt=8,disposition='manual_required')],
            hold_read_ok=True, held_deliveries=None, redis_read_ok=True, worker_lock_pttl_ms=0,
            mongo={k:dict(count=0,statuses=[],expired_leases=0,read_ok=True) for k in ('report_generations','interpretation_runs','interpret_report_artifacts')})

    def test_fixed_states_only_private_output_ignored(self):
        from qs_recovery_acceptance import recovery_diagnostics
        value=self.sample()
        self.assertEqual(recovery_diagnostics('private log without marker'), [])
        self.assertEqual(recovery_diagnostics('M3C_COMPLETION_DIAGNOSTIC '+json.dumps(value)),[value])

    def test_refuse_free_text_unbounded_unknown_or_duplicate_records(self):
        from qs_recovery_acceptance import recovery_diagnostics
        for change in (dict(raw_error='private DSN'),dict(ensure_calls=True),dict(stage='private'),
                       dict(worker_lock_pttl_ms=300001),dict(reminder_visits=[True]),
                       dict(dead_letters=[dict(event_type='credentials://private',attempt=1,disposition='')]),
                       dict(runs=[dict(status='running',attempt=1,disposition='',lease_expired='true')]),
                       dict(mongo={})): 
            with self.subTest(change=change):
                with self.assertRaises(RuntimeError):
                    recovery_diagnostics('M3C_COMPLETION_DIAGNOSTIC '+json.dumps(dict(self.sample(),**change)))
        output='M3C_COMPLETION_DIAGNOSTIC '+json.dumps(self.sample())
        with self.assertRaises(RuntimeError):recovery_diagnostics(output+'\n'+output)
