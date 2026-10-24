"""Pure request/primary-read guards; never construct real clients."""
import importlib.util
from pathlib import Path
import tempfile
import json
import unittest
from managed_recovery_acceptance import fixture_manifest, physical_fingerprint, notice_key, safe_failure
from routes import validate

spec = importlib.util.spec_from_file_location('native_recheck', Path(__file__).with_name('ci-native-recheck.py'))
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


class NativeRecheckGuards(unittest.TestCase):
    def test_failure_summary_never_exports_raw_log_body_identity_or_credentials(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'owned.log'
            path.write_text('DO_NOT_EXPORT_RAW\n'+json.dumps(dict(schema='m3-native-recovery-result/v1',last_stage='native_inspection',receipt_path='DO_NOT_EXPORT_PATH',request_sha256='1'*64))+'\nM3_MANAGED_NATIVE '+json.dumps(dict(schema='m3-managed-native-recheck/v1',failure_stage='frozen_identity',failure_kind='DO_NOT_EXPORT_CLASS_VALUE',body='DO_NOT_EXPORT_BODY',outcome='NotAttempted'))+'\n')
            result=safe_failure(root)
            self.assertEqual(len(result),2)
            self.assertNotIn('DO_NOT_EXPORT',json.dumps(result))
            self.assertIn(dict(schema='m3-native-recovery-result/v1',last_stage='native_inspection'),result)
            self.assertIn('unclassified_runtime_failure',json.dumps(result))

    def test_managed_fixture_keeps_exact_m3_owner_routing(self):
        repo=Path(__file__).resolve().parents[2]
        document=fixture_manifest(repo)
        validate(document)
        self.assertEqual(len(document['routes']),3)
        self.assertEqual({r['route_revision'] for r in document['routes']},{'m3-1'})
        self.assertEqual([r['owner'] for r in document['routes'] if r['message_type']=='TRANSACTION'],['iam.mysql','qs.mongo'])

    def test_managed_physical_fingerprint_matches_existing_host_v1(self):
        document=dict(topic='TRANS_CHECK_MAX_TIME_TOPIC',key_sha256='1'*64)
        row=dict(broker_message_id='A'*32,queue_id=0,queue_offset=1,commitlog_offset=2,index_hour=3)
        first=physical_fingerprint(document,row)
        self.assertEqual(first.hex(),'c17eef089ffe8dcd195b09d54c8d7af26283362fc173a6226b964a4a4c0968d3')
        copied=physical_fingerprint(document,dict(row,queue_offset=2,commitlog_offset=3))
        self.assertEqual(copied.hex(),'61922da276bd4e4b9eced322f30aac9224929b6614dce2205f5fed99df91a878')
        self.assertNotEqual(notice_key(first),notice_key(copied))
        for bad in (dict(row,queue_id=-1),dict(row,queue_offset=True)):
            with self.assertRaises(RuntimeError):physical_fingerprint(document,bad)

    def test_only_github_hosted_with_local_context_environment(self):
        good = dict(GITHUB_ACTIONS='true', RUNNER_OS='Linux', RUNNER_ENVIRONMENT='github-hosted')
        subject.ci_guard(good)
        for bad in ({}, dict(good, RUNNER_ENVIRONMENT='self-hosted'), dict(good, RUNNER_OS='macOS'),
                    dict(good, DOCKER_HOST='tcp://remote:2375'), dict(good, DOCKER_CONTEXT='remote')):
            with self.assertRaises(RuntimeError): subject.ci_guard(bad)

    def test_exact_single_frame_no_raw_output_required(self):
        self.assertEqual(subject.frame('private\nSAFE {"passed":1}\n', 'SAFE '), {'passed':1})
        for raw in ('', 'SAFE []', 'SAFE {}\nSAFE {}'):
            with self.assertRaises(RuntimeError): subject.frame(raw, 'SAFE ')

    def test_pinned_admin_update_uses_comma_and_readback_is_separate(self):
        self.assertTrue(subject.positive_admin_reply('updateBrokerConfig', 'update broker config success, 127.0.0.1:10911'))
        self.assertFalse(subject.positive_admin_reply('updateBrokerConfig', 'update broker config failed'))
        self.assertFalse(subject.positive_admin_reply('updateBrokerConfig', ' success.'))

    def test_exact_primary_read_requires_all_three_hashes_and_states(self):
        good = '\t'.join(['1'*64,'2'*64,'3'*64,'committed','committed','not_attempted'])
        self.assertEqual(subject.authoritative_snapshot(good)['execution_state'], 'committed')
        for raw in ('', good+'\n'+good, good.replace('1'*64,'wrong'), good.replace('committed','unknown'),
                    good.replace('not_attempted','false_success')):
            with self.assertRaises(RuntimeError): subject.authoritative_snapshot(raw)


if __name__ == '__main__': unittest.main()
