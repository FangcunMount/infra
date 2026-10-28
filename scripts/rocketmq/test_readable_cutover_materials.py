import copy
from pathlib import Path
import tempfile
import unittest

from readable_cutover import digest, prepare_active_configuration
from readable_cutover_materials import BASE, ROLES, COMPONENTS, documents, rebase_mounts, revision, stopped_instances
from start_boundary import Boundary, BoundaryError, initialize

PROJECT='rocketmq-m2-image-aabbccddeeff'


class ReadableCutoverMaterialsTest(unittest.TestCase):
    def test_actual_config_restore_adapter_preserves_first_start_and_data_restore_protection(self):
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)/'operation'
            binding=dict(schema='m3-start-boundary/v1',operation_id='owned-config-restore',directory=str(directory),
                scope_sha256='1'*64,protection_sha256='2'*64,restore_receipt_sha256='3'*64,
                source_bundle_sha256='4'*64,data_owner='owned-ci',recovery_owner='owned-ci')
            signature=digest(binding);initialize(directory,binding,signature)
            calls=[]
            with Boundary(directory,signature) as operation:
                prepare_active_configuration(operation,calls.append)
                self.assertEqual(calls,['active','compat','active'])
                self.assertFalse(operation.status()['runtime_may_have_started'])
                operation.start('first-runtime',lambda:calls.append('start'))
                self.assertTrue(operation.status()['runtime_may_have_started'])
                with self.assertRaises(BoundaryError):prepare_active_configuration(operation,calls.append)
                with self.assertRaises(BoundaryError):operation.restore_before_start('forbidden-data-restore',lambda:calls.append('unsafe'))
                self.assertEqual(calls,['active','compat','active','start'])

    def rows(self):
        return [dict(Name='/'+PROJECT+'-'+k,Config=dict(Labels={'com.fangcunmount.m3.fixture':PROJECT}),
            State=dict(Status='exited',Running=False,ExitCode=0,OOMKilled=False)) for k in COMPONENTS]

    def test_fixed_route_pair_preserves_logical_owner_revision_account_and_budget(self):
        value=documents();old,new=value['compat'],value['active']
        self.assertEqual(old['version'],2);self.assertEqual(new['version'],3)
        self.assertEqual(old['accounts'],new['accounts'])
        self.assertEqual(old['topic_options'],new['topic_options'])
        self.assertEqual(new['historical_routes'],old['routes'])
        self.assertEqual(len({r['physical_topic'] for r in old['routes']}),10)
        self.assertEqual(len({r['consumer_group'] for r in new['routes'] if r.get('consumer_group')}),9)

    def test_any_live_failed_oom_missing_duplicate_or_foreign_instance_prevents_selector_change(self):
        self.assertEqual(len(stopped_instances(self.rows(),PROJECT)),8)
        for kind in ('running','failed','oom','missing','duplicate','foreign','created','bool-code'):
            value=self.rows()
            if kind=='running':value[0]['State']['Running']=True
            elif kind=='failed':value[0]['State']['ExitCode']=1
            elif kind=='oom':value[0]['State']['OOMKilled']=True
            elif kind=='missing':value.pop()
            elif kind=='duplicate':value[-1]=copy.deepcopy(value[0])
            elif kind=='foreign':value[0]['Config']['Labels']['com.fangcunmount.m3.fixture']='production'
            elif kind=='created':value[0]['State']['Status']='created'
            else:value[0]['State']['ExitCode']=False
            with self.subTest(kind=kind),self.assertRaises(RuntimeError):stopped_instances(value,PROJECT)

    def test_only_same_owned_revision_immutable_mounts_are_rebased_without_mutating_inputs(self):
        original='m4-owned-aabbccddeeff';target=revision(PROJECT,'compat')
        mounts={role:[dict(source=str(BASE/stem/'versions'/original/'rocketmq/routes.json'),
            target='/run/'+role+'/routes.json',read_only=True,bind=dict(create_host_path=False))]
            for role,(stem,_) in ROLES.items() if role!='api'}
        mounts.update(api=[],collection=[]);before=copy.deepcopy(mounts)
        value=rebase_mounts(mounts,original,target)
        self.assertEqual(mounts,before)
        for role in ('iam','ai','worker'):
            self.assertIn('/versions/'+target+'/',value[role][0]['source'])
            self.assertEqual(value[role][0]['target'],mounts[role][0]['target'])
        for kind in ('foreign','writable','create','other-revision'):
            bad=copy.deepcopy(mounts);selected=target
            if kind=='foreign':bad['iam'][0]['source']='/etc/production/routes.json'
            elif kind=='writable':bad['iam'][0]['read_only']=False
            elif kind=='create':bad['iam'][0]['bind']['create_host_path']=True
            else:selected='readable-active-001122334455'
            with self.subTest(kind=kind),self.assertRaises(RuntimeError):rebase_mounts(bad,original,selected)

    def test_phase_and_project_cannot_select_arbitrary_root(self):
        for project,phase in [('production','active'),(PROJECT,'../other'),(PROJECT,'current')]:
            with self.assertRaises(RuntimeError):revision(project,phase)

    def test_actual_compose_readonly_ai_mount_may_omit_false_create_host_path(self):
        original='m4-owned-aabbccddeeff'
        source=str(BASE/ROLES['ai'][0]/'versions'/original/'rocketmq/routes.json')
        # Actual Compose output supplies bind={} for these AI file mounts.
        # FiveImageFixture still uses Docker --mount, which never creates a
        # missing host path. Explicit create=true and foreign revisions fail.
        mounts=dict(ai=[dict(source=source,target='/run/qs-ai-rocketmq/routes.json',read_only=True,bind={})])
        result=rebase_mounts(mounts,original,revision(PROJECT,'compat'))
        self.assertIn('/versions/readable-compat-aabbccddeeff/',result['ai'][0]['source'])
        self.assertEqual(mounts['ai'][0]['source'],source)
        mounts['ai'][0]['bind']['create_host_path']=True
        with self.assertRaises(RuntimeError):rebase_mounts(mounts,original,revision(PROJECT,'compat'))
