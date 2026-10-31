import json
from pathlib import Path
import unittest

from qs_runtime_acceptance import CASES, SCOPE, parse_runtime_receipt, runtime_manifest, runtime_diagnostics
from routes import permissions_v2


class DefaultRuntimeReceiptTest(unittest.TestCase):
    def output(self):
        value = dict(source_sha='a'*40, passed=13, failed=0, skipped=0, cases={k: True for k in CASES},
            scope=SCOPE, domain_api_provider_system_not_claimed=True, producer_process_exit_not_claimed=True,
            owned_databases_dropped=True, owned_runtimes_drained=True, same_broker_container_restarted=True,
            local_executor_calls=[1, 1], new_half_prepared_results=[0, 0], mongo_database_callbacks=2, new_checker_commits=[1, 1],
            observed_callbacks={'running': 2, 'queued': 1}, duplicate_deliveries=1, close_wait_ms=101)
        return 'M3_QS_DEFAULT_OWNER_RECEIPT '+json.dumps(value)+'\n--- PASS: TestM3DefaultOwnerRuntime (1s)'

    def test_exact_current_instance_checker_and_owned_lifecycle(self):
        self.assertEqual(parse_runtime_receipt(self.output(), 'a'*40)['passed'], 13)

    def test_refuse_partial_wrong_source_scope_skips_races_or_bounds(self):
        output = self.output()
        for bad in ('', output+'\n'+output, output.replace('a'*40, 'b'*40), output.replace('true', 'false', 1),
                    output.replace('"passed": 13', '"passed": 0'), output.replace('"skipped": 0', '"skipped": 1'),
                    output.replace('[1, 1]', '[2, 1]', 1), output.replace('"new_half_prepared_results": [0, 0]', '"new_half_prepared_results": [1, 0]'), output.replace('"new_checker_commits": [1, 1]', '"new_checker_commits": [0, 1]'),
                    output.replace('"running": 2', '"running": 5'), output.replace('"close_wait_ms": 101', '"close_wait_ms": 3000'), output.replace('"queued": 1', '"queued": 33'),
                    output.replace(SCOPE, 'whole API'), output.replace('TestM3DefaultOwnerRuntime', 'TestSDKProbe'),
                    output+'\nWARNING: DATA RACE', output+'\n--- SKIP: optional (1s)'):
            with self.subTest(bad=bad[:60]):
                with self.assertRaises(RuntimeError): parse_runtime_receipt(bad, 'a'*40)

    def test_recovery_grants_actual_api_only_its_original_hotrank_subscription(self):
        value=runtime_manifest(Path(__file__).resolve().parents[2], recovery=True)
        self.assertEqual(value['accounts']['m3-qs-apiserver']['subscriptions'], ['qs-recovery-hotrank'])
        self.assertEqual(value['accounts']['m3-qs-worker']['publish'], [])
        rows={r['id']:r for r in value['routes']}
        hot=rows['qs-recovery-hotrank'];permissions=permissions_v2(value,value['accounts']['m3-qs-apiserver'])
        self.assertIn('Sub', permissions['Topic:'+hot['physical_topic']])
        self.assertNotIn('Pub', permissions['Topic:'+hot['physical_topic']])
        self.assertIn('Sub', permissions['Group:'+hot['consumer_group']])
        self.assertIn('qs-recovery-hotrank', value['accounts']['m3-qs-worker']['subscriptions'])

    def test_full_owner_topic_registration_and_consume_only_observer(self):
        value = runtime_manifest(Path(__file__).resolve().parents[2])
        self.assertEqual(set(value['accounts']), {'m3-qs-apiserver', 'm3-qs-mongo', 'm3-qs-worker'})
        rows = {r['id']: r for r in value['routes']}
        logical = {rows[i]['topic'] for i in value['accounts']['m3-qs-apiserver']['publish'] if rows[i]['message_type']=='TRANSACTION'}
        self.assertEqual(logical, {'qs.evaluation.lifecycle', 'qs.plan.task', 'qs.ai.commands.v1', 'qs.ai.acks.v1'})
        self.assertEqual(value['accounts']['m3-qs-apiserver']['subscriptions'], [])
        self.assertEqual(value['accounts']['m3-qs-worker']['publish'], [])
        permissions = permissions_v2(value, value['accounts']['m3-qs-worker'])
        self.assertTrue(all(actions == {'Sub', 'Get'} for actions in permissions.values()))


class RuntimeProfileIsolationTest(unittest.TestCase):
    def test_mixed_profiles_fail_before_any_fixture_or_docker_work(self):
        import os
        import subprocess
        import sys
        script = Path(__file__).with_name('ci-transactions.py')
        for option in ('--qs-deferred-consumer-host', '--iam-host', '--ai-admission-host'):
            result = subprocess.run([sys.executable, str(script), '--sdk', '.', '--image', 'unused',
                '--report', '/not-created-native-report.json', '--qs-runtime-host', '.', option, '.'],
                capture_output=True, text=True, timeout=5, env=dict(os.environ, PATH=''))
            self.assertEqual(result.returncode, 2)
            self.assertIn('default QS owner runtime is a separate required profile', result.stderr)


class DefaultRuntimeDiagnosticTest(unittest.TestCase):
    def sample(self):
        return dict(stage='local_committed', owner_index=1, local='unknown',
                    error=dict(kind='deadline', code=0), root_phases=[5, 2],
                    lease_remaining_ms=[-100, 20], elapsed_ms=60100)

    def test_only_fixed_synthetic_counters_are_retained(self):
        value = self.sample()
        self.assertEqual(runtime_diagnostics('private non-marker text'), [])
        self.assertEqual(runtime_diagnostics('M3_QS_OWNER_DIAGNOSTIC '+json.dumps(value)), [value])

    def test_next_owner_start_exports_only_fixed_failure_categories(self):
        for kind in ('deadline', 'metrics_registration', 'protocol_protection', 'host_admission'):
            value = dict(self.sample(), stage='next_owner_start', owner_index=-1, error=dict(kind=kind, code=0))
            self.assertEqual(runtime_diagnostics('M3_QS_OWNER_DIAGNOSTIC '+json.dumps(value)), [value])

    def test_refuse_raw_errors_unknown_fields_and_unbounded_values(self):
        for changes in (dict(wire='private'), dict(stage='arbitrary'), dict(elapsed_ms=True),
                        dict(root_phases=[9, 0]), dict(lease_remaining_ms=[1]),
                        dict(error=dict(kind='private error text', code=0)),
                        dict(error=dict(kind='mysql', code=-1))):
            value = dict(self.sample(), **changes)
            with self.assertRaises(RuntimeError):
                runtime_diagnostics('M3_QS_OWNER_DIAGNOSTIC '+json.dumps(value))


class ProtocolProtectionReceiptTest(unittest.TestCase):
    def output(self):
        return DefaultRuntimeReceiptTest().output()
    def protection_output(self):
        from qs_runtime_acceptance import PROTECTION_CASES
        value = dict(source_sha='a'*40, passed=len(PROTECTION_CASES), failed=0, skipped=0,
                     cases={k: True for k in PROTECTION_CASES}, fixture_timestamp_aging_seconds=600,
                     real_ten_minute_elapsed_not_claimed=True, owner_count=2,
                     domain_api_provider_system_not_claimed=True, owned_databases_dropped=True)
        return self.output()+'\nM3_QS_PROTOCOL_PROTECTION_RECEIPT '+json.dumps(value)

    def test_both_receipts_and_fixed_aging_scope(self):
        from qs_runtime_acceptance import parse_protection_receipt, PROTECTION_CASES
        self.assertEqual(parse_protection_receipt(self.protection_output(), 'a'*40)['passed'], len(PROTECTION_CASES))

    def test_refuse_missing_duplicate_wrong_source_partial_or_expanded_scope(self):
        from qs_runtime_acceptance import parse_protection_receipt
        output = self.protection_output()
        for bad in (self.output(), output+'\n'+output, output.replace('a'*40, 'b'*40),
                    output.replace('"passed": 8', '"passed": 0'),
                    output.replace('"owner_count": 2', '"owner_count": true'),
                    output.replace('"fixture_timestamp_aging_seconds": 600', '"fixture_timestamp_aging_seconds": 300'),
                    output.replace('"real_ten_minute_elapsed_not_claimed": true', '"real_ten_minute_elapsed_not_claimed": false'),
                    output+'\nWARNING: DATA RACE', output+'\n--- SKIP: dependency (0s)'):
            with self.subTest(bad=bad[:60]):
                with self.assertRaises(RuntimeError): parse_protection_receipt(bad, 'a'*40)

    def test_exact_published_protection_module_and_legacy_profile_separate(self):
        from qs_runtime_acceptance import validate_module, PROTECTION_MODULE
        module = dict(Path='github.com/FangcunMount/reliable-messaging',
                      **dict(zip(('Version', 'Sum', 'GoModSum'), PROTECTION_MODULE)))
        validate_module(module, True)
        for changes in (dict(Replace={}), dict(Version='v0.5.0-rocketmq-tx.2'),
                        dict(Sum='forged'), dict(GoModSum='forged'), dict(Path='other')):
            with self.assertRaises(RuntimeError): validate_module(dict(module, **changes), True)
        with self.assertRaises(RuntimeError): validate_module(module, False)
        validate_module(dict(module, Version='v0.5.0-rocketmq-tx.2'), False)

    def test_protection_flag_without_runtime_fails_before_dependency_work(self):
        import subprocess
        import sys
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('ci-transactions.py')),
            '--sdk', '.', '--image', 'unused', '--report', '/not-created-protection-report.json',
            '--qs-protocol-protection'], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn('protocol protection requires', result.stderr)
