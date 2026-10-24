import copy
from pathlib import Path
import tempfile
import unittest

from final_image_candidate import GO_SUM
from iam_image_start import IAM_SHA, configuration, inventory, protocol_metrics, fixture_diagnostic, source_failure_markers


class ImageStartContractTest(unittest.TestCase):
    def test_startup_marker_only_exports_authored_source_identity(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root);folder=source/'internal/apiserver';folder.mkdir(parents=True)
            (folder/'startup.go').write_text('return fmt.Errorf("explicit fixture startup failed: %w", err)\n')
            body='explicit fixture startup failed: private-password wire payload SELECT personal-data'
            markers=source_failure_markers(body,source)
            self.assertEqual(len(markers),1)
            self.assertEqual(set(markers[0]),{'path','line','template_sha256'})
            self.assertNotIn('private-password',str(markers))
    def test_diagnostics_cannot_export_sql_or_credentials(self):
        raw='IAM_IMAGE_FIXTURE_FAILURE {"phase":"migrate_31","kind":"*mysql.MySQLError","server_code":1146}'
        self.assertEqual(fixture_diagnostic(raw)['server_code'],1146)
        for bad in (raw+ '\n'+raw,raw.replace('migrate_31','private body'),raw[:-1]+',"sql":"private"}'):
            with self.assertRaises(RuntimeError):fixture_diagnostic(bad)
    def test_old_source_wrong_sdk_and_unverified_cleanup_are_rejected(self):
        valid = dict(target='iam',source_sha=IAM_SHA,passed=1,failed=0,skipped=0,
                     deferred_tools_absent=True,verified_uid_gid=[2000,2000],
                     runtime_sdk=dict(version='v0.5.0',sum=GO_SUM,replace=False),
                     cleanup=dict(owned_container_absent=True,owned_image_tag_absent=True,existing_containers_unchanged=True))
        inventory(valid)
        for mutation in (dict(source_sha='8be32adea54ad354257e54122cca923edd00572b'),
                         dict(runtime_sdk=dict(version='v0.5.0-rocketmq-tx.4',sum=GO_SUM,replace=False)),
                         dict(cleanup={}),dict(skipped=1),dict(verified_uid_gid=[0,0])):
            with self.subTest(mutation=mutation),self.assertRaises(RuntimeError):
                inventory(dict(valid,**mutation))

    def test_new_runtime_is_paused_without_ddl_or_old_relay(self):
        base=dict(mysql={},migration={},redis=dict(cache={}),seed_mock_auth={},idp={},sms={},insecure={},
                  grpc=dict(mtls={}),events=dict(reliable_messaging={}))
        original=copy.deepcopy(base)
        new=configuration(base,'owned','private',transaction=True)
        self.assertEqual(base,original)
        self.assertFalse(new['migration']['enabled'])
        self.assertFalse(new['messaging']['publish_enabled'])
        self.assertFalse(new['events']['reliable_messaging']['enabled'])
        self.assertFalse(new['nsq']['enabled'])
        self.assertEqual(set(new['messaging']['transactions']),{'iam.mysql'})
        self.assertEqual(new['messaging']['instance_id'],'iam-primary-1')
        self.assertEqual(new['events']['catalog_path'],'/app/configs/events-m3.yaml')
        self.assertNotIn('limits',new['messaging']['transactions']['iam.mysql'])
        old=configuration(base,'owned','private',transaction=False)
        self.assertTrue(old['events']['reliable_messaging']['enabled'])
        self.assertFalse(old['messaging']['transactions'])

    def test_readiness_requires_live_checker_and_closed_admission(self):
        values={'sdk_ready':1,'sampler_running':1,'observation_available':1,'admission_open':0,
                'check_workers_limit':4,'check_queue_limit':32}
        raw='\n'.join(f'reliable_messaging_transaction_{key}{{owner="iam.mysql"}} {value}' for key,value in values.items())
        self.assertEqual(protocol_metrics(raw),values)
        for invalid in (raw.replace('sdk_ready{owner="iam.mysql"} 1','sdk_ready{owner="iam.mysql"} 10'),
                        raw.replace('admission_open{owner="iam.mysql"} 0','admission_open{owner="iam.mysql"} 1'),
                        raw.replace('iam.mysql','wrong.owner')):
            with self.assertRaises(RuntimeError):protocol_metrics(invalid)
