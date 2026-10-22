import json
from pathlib import Path
import unittest

from qs_runtime_acceptance import CASES, SCOPE, parse_runtime_receipt, runtime_manifest
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
