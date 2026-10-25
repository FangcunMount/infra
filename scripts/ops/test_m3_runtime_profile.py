import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

from m3_runtime_profile import ProfileError, main, validate


class EffectiveProfileTests(unittest.TestCase):
    def setUp(self):
        self.worker = {'messaging': {'provider': 'rocketmq', 'rocketmq': {
            'publish_enabled': False, 'transactions': {}}}}
        self.api = {'iam': {'authz-sync': {'enabled': True, 'provider': 'rocketmq',
            'topic': 'iam.authz.version.v2', 'channel-prefix': 'qs-authz-sync',
            'rocketmq': {'instance_id': 'qs-apiserver-1', 'transactions': {}}}}}
        self.routes = {'routes': [{'topic': 'iam.authz.version.v2',
            'subscription': 'qs-authz-sync-apiserver-qs-apiserver-1',
            'message_type': 'TRANSACTION', 'owner': 'iam.mysql',
            'physical_topic': 'frozen_topic', 'consumer_group': 'frozen_group'}]}

    def test_consumer_only_worker(self):
        self.assertTrue(validate('worker', self.worker, self.routes)['consumer_only'])

    def test_rejected_actual_acceptance_publisher_mistake(self):
        self.worker['messaging']['rocketmq']['publish_enabled'] = True
        with self.assertRaisesRegex(ProfileError, 'consumer_only'):
            validate('worker', self.worker, self.routes)

    def test_missing_or_nonboolean_publish_flag_is_not_consumer_only(self):
        for value in [None, 0, 'false']:
            self.worker['messaging']['rocketmq']['publish_enabled'] = value
            with self.subTest(value=value), self.assertRaises(ProfileError):
                validate('worker', self.worker, self.routes)

    def test_worker_cannot_claim_transaction_ownership(self):
        self.worker['messaging']['rocketmq']['transactions'] = {'qs.mysql': {}}
        with self.assertRaises(ProfileError):
            validate('worker', self.worker, self.routes)

    def test_exact_subscription_binding(self):
        self.assertTrue(validate('apiserver', self.api, self.routes)['authz_subscription_bound'])

    def test_rejected_actual_instance_mismatch(self):
        self.api['iam']['authz-sync']['rocketmq']['instance_id'] = 'qs-authz-sync-1'
        with self.assertRaisesRegex(ProfileError, 'match_one_frozen_route'):
            validate('apiserver', self.api, self.routes)

    def test_disabled_or_wrong_provider_not_accepted(self):
        for key, value in [('enabled', False), ('provider', 'nsq')]:
            config = copy.deepcopy(self.api)
            config['iam']['authz-sync'][key] = value
            with self.subTest(key=key), self.assertRaises(ProfileError):
                validate('apiserver', config, self.routes)

    def test_ambiguous_or_wrong_owner_or_type_is_rejected(self):
        for change in ['duplicate', 'owner', 'message_type']:
            routes = copy.deepcopy(self.routes)
            if change == 'duplicate':
                routes['routes'].append(copy.deepcopy(routes['routes'][0]))
            else:
                routes['routes'][0][change] = 'wrong'
            with self.subTest(change=change), self.assertRaises(ProfileError):
                validate('apiserver', self.api, routes)

    def test_cli_never_echoes_config_or_parse_failure_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);config = root/'effective.json';routes = root/'routes.json'
            config.write_text('{"password":"SENSITIVE_TEST_SENTINEL",BROKEN}')
            routes.write_text(json.dumps(self.routes))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                status = main(['--role', 'worker', '--effective-config', str(config), '--routes', str(routes)])
            self.assertEqual(status, 1)
            self.assertNotIn('SENSITIVE_TEST_SENTINEL', out.getvalue())
            self.assertEqual(json.loads(out.getvalue())['reason'], 'input_unreadable_or_invalid')


if __name__ == '__main__':
    unittest.main()
