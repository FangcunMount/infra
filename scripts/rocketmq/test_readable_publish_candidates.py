import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from publish_candidates import REGISTRY, NAMESPACE, REPOSITORIES
from readable_publish_candidates import destinations, load_plan, retrieve, stable_sdk_receipt, validate_report
import test_readable_image_candidates as candidate_fixture
import test_readable_image_start as startup_fixture


class ReadablePublicationTest(unittest.TestCase):
    def setUp(self):
        source=candidate_fixture.ReadableImageCandidatesTest();source.setUp();self.candidate=source.value
        self.startup=startup_fixture.ReadableImageStartupTest().report()
        self.startup.update(infra_sha='d'*40,shutdown_failed_components=[])
        self.plan=dict(schema='readable-reviewed-candidate-publication/v1',candidate=self.candidate,
            candidate_sha256='e'*64,registry=REGISTRY,namespace=NAMESPACE,
            startup=dict(run_id=40123456790,head_sha='d'*40,report_sha256='e'*64),targets={})
        self.startup['candidates']={}
        for target,row in self.candidate['images'].items():
            role='qs' if target.startswith('qs-') else target
            self.plan['targets'][target]=dict(row,repository=REPOSITORIES[target],source_sha=self.candidate['sources'][role],
                builder_source_sha=self.candidate['builder_sha'],runtime_sdk={})
            self.startup['candidates'][target]={k:self.plan['targets'][target][k] for k in
                ('source_sha','builder_source_sha','image_config_id','archive_sha256')}

    def test_only_exact_reviewed_readable_objects_and_existing_registry_are_valid(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'plan.json';path.write_text(json.dumps(self.plan));digest=hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(load_plan(path,digest),self.plan)
            with self.assertRaises(ValueError):load_plan(path,'0'*64)
            for kind in ('registry','repository','schema','source','image','routes','missing-image'):
                bad=copy.deepcopy(self.plan)
                if kind=='registry':bad['registry']='elsewhere.invalid'
                elif kind=='repository':bad['targets']['iam']['repository']='another-service'
                elif kind=='schema':bad['schema']='m4-reviewed-candidate-publication/v1'
                elif kind=='source':bad['targets']['iam']['source_sha']='f'*40
                elif kind=='image':bad['targets']['iam']['image_config_id']='sha256:'+'0'*64
                elif kind=='routes':bad['candidate']['routes_sha256']='0'*64
                else:del bad['targets']['qs-worker']
                path.write_text(json.dumps(bad))
                with self.subTest(kind=kind),self.assertRaises(ValueError):load_plan(path,hashlib.sha256(path.read_bytes()).hexdigest())

    def test_real_startup_contract_requires_all_original_process_budget_and_exact_archives(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'startup.json'
            def validate(value):
                path.write_text(json.dumps(value));self.plan['startup']['report_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
                return validate_report(self.plan,path)
            self.assertEqual(validate(self.startup)['passed'],18)
            for kind in ('wrong-source','seven','budget','archive','ddl','skip','unfinished-shutdown','business-claim','cleanup'):
                value=copy.deepcopy(self.startup)
                if kind=='wrong-source':value['infra_sha']='0'*40
                elif kind=='seven':del value['processes']['worker3']
                elif kind=='budget':value['actual_runtime_budgets']['worker1']['memory_bytes']=1
                elif kind=='archive':value['candidates']['iam']['archive_sha256']='0'*64
                elif kind=='ddl':value['mysql_runtime_ddl_attempts']=1
                elif kind=='skip':value['skipped']=1
                elif kind=='unfinished-shutdown':value['shutdown_failed_components']=['worker1']
                elif kind=='business-claim':value['system_acceptance']=True
                else:value['cleanup']['owned_m4_material_root_removed']=False
                with self.subTest(kind=kind),self.assertRaises(ValueError):validate(value)

    def test_rc_cannot_read_secrets_or_reach_github_or_registry(self):
        run=Mock()
        with self.assertRaisesRegex(ValueError,'only_published_stable'):stable_sdk_receipt(self.candidate,run)
        run.assert_not_called()

    def test_stable_tags_same_source_and_real_official_wheel_digest_required(self):
        expected=dict(go='v0.6.0',python='0.5.0',source_sha='f'*40,wheel_sha256='a'*64,
            wheel_url='https://github.com/FangcunMount/reliable-messaging/releases/download/python/v0.5.0/fangcun_reliable_messaging-0.5.0-py3-none-any.whl')
        for damage in (None,'source','annotated','draft','prerelease','wheel','url'):
            calls=[]
            def run(args):
                path=args[-1];calls.append(path);tag='python/v0.5.0' if path.endswith('python/v0.5.0') else 'v0.6.0'
                if '/git/ref/' in path:
                    return json.dumps(dict(ref='refs/tags/'+tag,object=dict(type='tag' if damage=='annotated' else 'commit',
                        sha='0'*40 if damage=='source' else expected['source_sha'])))
                return json.dumps(dict(tag_name=tag,draft=damage=='draft',prerelease=damage=='prerelease',assets=[dict(
                    name=expected['wheel_url'].rsplit('/',1)[1],digest='sha256:'+('0'*64 if damage=='wheel' else expected['wheel_sha256']),
                    browser_download_url='https://elsewhere.invalid/wheel' if damage=='url' else expected['wheel_url'])]))
            with patch('readable_publish_candidates.sdk_profile',return_value=expected),self.subTest(damage=damage):
                if damage:
                    with self.assertRaises(ValueError):stable_sdk_receipt(self.candidate,run)
                else:self.assertTrue(stable_sdk_receipt(self.candidate,run)['tags_match'])
            self.assertTrue(all('/git/ref/' in p or '/releases/tags/' in p for p in calls))

    def test_failed_wrong_workflow_event_or_builder_stops_before_download_or_write(self):
        for damage in ('failed','source','workflow','event'):
            calls=[]
            def run(args):
                calls.append(args)
                return json.dumps(dict(id=40123456789,head_sha='0'*40 if damage=='source' else 'd'*40,
                    conclusion='failure' if damage=='failed' else 'success',event='pull_request' if damage=='event' else 'workflow_dispatch',
                    path='.github/workflows/other.yml' if damage=='workflow' else '.github/workflows/rocketmq-readable-images.yml'))
            with tempfile.TemporaryDirectory() as root,self.subTest(damage=damage),self.assertRaises(ValueError):
                retrieve(self.plan,Path(root),run)
            self.assertEqual(len(calls),1)
            self.assertEqual(calls[0][:2],['gh','api'])

    def test_unique_readable_candidate_tags_never_replace_prior_release_names(self):
        refs=destinations(self.plan,'123','1');self.assertEqual(len(refs),5)
        self.assertTrue(all(':readable-candidate-' in value for value in refs.values()))
        self.assertNotEqual(refs,destinations(self.plan,'123','2'))
        for run,attempt in [('main','1'),('1','0'),(123,'1')]:
            with self.assertRaises(ValueError):destinations(self.plan,run,attempt)
