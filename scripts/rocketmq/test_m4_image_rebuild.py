import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from five_image_start import FiveImageFixture

from m4_image_rebuild import BUILDER_SHA, SOURCES, bridge_binding, compose_material_mounts, owner_limits
from m4_owned_materials import FILES, owned_fixture, validate_plan


class M4RebuildContractTest(unittest.TestCase):
    def plan(self, root):
        plan = dict(schema='m4-synthetic-image-materials/v1', project='rocketmq-m2-image-'+'a'*12,
                    revision='m4-owned-'+'a'*12, files=[],
                    api_binding=dict(binding_revision='m4-owned-'+'a'*12,provider='rocketmq'))
        for role, names in FILES.items():
            for name in names:
                path=root/role/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(b'synthetic-owned-fixture')
                plan['files'].append(dict(role=role,relative=name,source=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        return plan

    def test_fixed_profile_uses_all_new_merged_sources_and_exact_builder(self):
        self.assertEqual(set(SOURCES), {'iam','qs','ai'})
        self.assertEqual(len(set(SOURCES.values())), 3)
        for value in (*SOURCES.values(), BUILDER_SHA): self.assertRegex(value, '^[a-f0-9]{40}$')
        self.assertNotIn('b75d4a52ec261275a0ffb588eeb31fd6496966d0', SOURCES.values())

    def test_fixture_root_never_accepts_production_or_traversal(self):
        self.assertEqual(owned_fixture('/tmp/m3-image-start-abcdefgh'), Path('/tmp/m3-image-start-abcdefgh'))
        for value in ('/var/lib/fangcun-m4-materials','/tmp','/tmp/../tmp/m3-image-start-abcdefgh',
                      '/tmp/m3-image-start-a','/tmp/m3-image-start-abcdefgh/nested'):
            with self.subTest(value=value), self.assertRaises(RuntimeError): owned_fixture(value)

    def test_complete_exact_21_materials_and_digests_before_root_creation(self):
        with tempfile.TemporaryDirectory(prefix='m3-image-start-',dir='/tmp') as raw:
            root=Path(raw).resolve();plan=self.plan(root);validate_plan(plan,root)
            self.assertEqual(len(plan['files']),21)
            for change in ('missing','duplicate','foreign-role','foreign-source','digest','revision','extra-field'):
                bad=copy.deepcopy(plan)
                if change=='missing':bad['files'].pop()
                elif change=='duplicate':bad['files'].append(bad['files'][0])
                elif change=='foreign-role':bad['files'][0]['role']='foreign'
                elif change=='foreign-source':bad['files'][0]['source']='/etc/passwd'
                elif change=='digest':bad['files'][0]['sha256']='f'*64
                elif change=='revision':bad['revision']='../escape'
                else:bad['files'][0]['gid']=0
                with self.subTest(change=change), self.assertRaises(RuntimeError):validate_plan(bad,root)

    def test_symlinked_synthetic_source_is_not_copied(self):
        with tempfile.TemporaryDirectory(prefix='m3-image-start-',dir='/tmp') as raw:
            root=Path(raw).resolve();plan=self.plan(root);source=Path(plan['files'][0]['source'])
            original=source.with_name('retained-original');source.rename(original);source.symlink_to(original)
            with self.assertRaises(RuntimeError):validate_plan(plan,root)

    def test_actual_compose_projection_keeps_revision_and_noncreating_readonly_files(self):
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/'compose.json'
            def document(variable,operator):
                return {'services':{'app':{'volumes':[dict(type='bind',source='/var/lib/fangcun-m4-materials/iam-messaging/versions/${'+variable+operator+'required}/rocketmq/'+name,
                    target='/etc/iam/rocketmq/'+name,read_only=True,bind={'create_host_path':False}) for name in ('credentials.json','ca.crt','routes.json')]}}}
            for operator in (':?', ':-'):
                value=document('REVISION',operator);path.write_text(json.dumps(value))
                mounts=compose_material_mounts(path,'app','REVISION','m4-owned-abc','iam')
                self.assertEqual(len(mounts),3)
                self.assertTrue(all('/versions/m4-owned-abc/' in m['source'] for m in mounts))
                for field,content in (('read_only',False),('bind',{'create_host_path':True})):
                    bad=copy.deepcopy(value);bad['services']['app']['volumes'][0][field]=content;path.write_text(json.dumps(bad))
                    with self.assertRaises(RuntimeError):compose_material_mounts(path,'app','REVISION','m4-owned-abc','iam')
            path.write_text(json.dumps(document('OTHER',':?')))
            with self.assertRaises(RuntimeError):compose_material_mounts(path,'app','REVISION','m4-owned-abc','iam')

    def test_bridge_keeps_exact_domain_identity_and_credential_without_mongo_owner(self):
        owner=dict(store_id='Original-$主',writer_epoch='Original-$$-Epoch',route_revision='m3-1',
                   credentials_file='/app/configs/rocketmq/credentials.json',limits=owner_limits(2,16,50))
        domain=dict(endpoint='broker:8081',transactions={'qs.mysql':owner,'qs.mongo':{'store_id':'other'}},publish_enabled=False)
        original=copy.deepcopy(domain);binding=bridge_binding(domain,'m4-owned-abc')
        self.assertEqual(domain,original)
        self.assertEqual(binding['rocketmq']['transactions'],{'qs.mysql':owner})
        self.assertEqual(binding['binding_revision'],'m4-owned-abc')
        self.assertFalse(binding['publish_enabled'])

    def test_real_start_keeps_compose_omitted_false_binds_noncreating_and_readonly(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            for bind in ({}, {'create_host_path':False}):
                f=FiveImageFixture.__new__(FiveImageFixture)
                f.directory=root; f.private_dirs={'api':root}; f.images={'api':'owned-image'}
                f.project='owned'; f.network='owned'; f.label='owned'; f.report={}; f.applications={}
                mount=dict(source='/var/lib/fangcun-m4-materials/fixture/credentials.json',
                           target='/app/configs/rocketmq/credentials.json',read_only=True,bind=bind)
                f.runtime_mounts={'api':[mount]};commands=[]
                def run(args,**kw):
                    commands.append(args)
                    if args[:2]==['docker','inspect']:
                        value=[dict(Config={'User':'www'},HostConfig={'Memory':1024*1024*1024,'NanoCpus':2000000000},
                                    Mounts=[dict(Source=mount['source'],Destination=mount['target'],RW=False)])]
                        return SimpleNamespace(stdout=json.dumps(value))
                    return SimpleNamespace(stdout='2000' if args[:2]==['docker','exec'] else 'owned')
                f.run=run
                f.start('api',alias='api',memory='1024m',cpus='2')
                launch=commands[0]
                self.assertIn('type=bind,src='+mount['source']+',dst='+mount['target']+',readonly',launch)
                self.assertEqual(f.report['actual_runtime_unix_identity']['api'],[2000,2000])
                mount['bind']={'create_host_path':True}
                with self.assertRaises(RuntimeError):f.start('api',alias='api',memory='1024m',cpus='2')


if __name__ == '__main__':unittest.main()
