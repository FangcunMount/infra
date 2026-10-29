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
                    processing_lease_observed=True, processing_lease_ttl_ms=299000)

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
        for field in ('processing_lease_observed', 'real_redis', 'broker_sigkill', 'worker_sigkill', 'worker_pids_distinct', 'owned_databases_dropped'):
            with self.subTest(field=field):
                row=self.receipt(); row[field]=False
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
