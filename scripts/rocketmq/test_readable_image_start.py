import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from five_image_start import main
from readable_image_start import CASES, ReadableImageLoader, python_dependencies, validate_startup


class ReadableImageStartupTest(unittest.TestCase):
    def candidate(self):
        return dict(sdk_profile='readable-rc1', sources=dict(iam='a'*40, qs='b'*40, ai='c'*40),
                    builder_sha='d'*40, image_runs=dict.fromkeys(('iam','qs-api','qs-collection','qs-worker','ai'),'40123456789'))

    def report(self):
        components = ('iam', 'ai', 'api', 'collection', 'collection2', 'worker1', 'worker2', 'worker3')
        budgets = {}
        for name in components:
            mb, cpus = ((768,750000000) if name=='ai' else (1024,1000000000) if name=='iam' else
                        (1024,2000000000) if name=='api' else (320,1000000000) if name.startswith('collection') else (768,1000000000))
            budgets[name] = dict(memory_bytes=mb*1024*1024,nano_cpus=cpus)
        state = dict(Status='exited',ExitCode=0,OOMKilled=False)
        candidate = self.candidate()
        return dict(schema='readable-eight-instance-startup/v1', sdk_profile='readable-rc1', sources=candidate['sources'],
            final_candidate_manifest_sha256='e'*64, final_candidate_image_runs=candidate['image_runs'],final_candidate=True,
            production=False,system_acceptance=False,combined_cutover_rehearsal_complete=False,c1_cutover_barrier_exercised=False,
            passed=18,failed=0,skipped=0,cases=dict.fromkeys(CASES,True),
            actual_material_mounts=dict.fromkeys(components,[]),actual_runtime_budgets=budgets,
            actual_runtime_unix_identity={k:[10001,10001] if k=='ai' else [2000,2000] for k in components},
            processes={k:dict(state=state) for k in components},
            worker_restart_checks=[dict(component=k,cycle=i,result=dict(state=state)) for k in ('worker1','worker2','worker3') for i in (1,2,3)],
            final_python_dependencies=dict(sdk='0.5.0rc1',nsq_absent=True,tornado_absent=True,current_imports=True),
            m4_material_stage=dict(files=21),actual_source_worker_concurrency=48,
            mysql_runtime_ddl_attempts=0,mongo_runtime_ddl_attempts=0,sources_unchanged=True,
            cleanup=dict(compose_down_succeeded=True,private_directory_removed=True,existing_containers_unchanged=True,
                         existing_networks_unchanged=True,owned_m4_material_root_removed=True))

    def test_startup_requires_candidate_all_instances_shutdown_resources_and_cleanup(self):
        original=self.report()
        self.assertEqual(validate_startup(original,self.candidate(),'e'*64),original)
        for damage in ('old-schema','wrong-sdk','wrong-digest','skip','bool-pass','fake-case','missing-worker',
                       'budget','uid','shutdown','restart','cleanup','ddl','business-claim','source-dirty'):
            bad=copy.deepcopy(original)
            if damage=='old-schema':bad['schema']='m4-eight-instance-config-rebuild/v1'
            elif damage=='wrong-sdk':bad['final_python_dependencies']['sdk']='0.4.0'
            elif damage=='wrong-digest':bad['final_candidate_manifest_sha256']='f'*64
            elif damage=='skip':bad['skipped']=1
            elif damage=='bool-pass':bad['passed']=True
            elif damage=='fake-case':bad['cases']['invented']=bad['cases'].pop(next(iter(CASES)))
            elif damage=='missing-worker':del bad['processes']['worker3']
            elif damage=='budget':bad['actual_runtime_budgets']['worker1']['nano_cpus']=2000000000
            elif damage=='uid':bad['actual_runtime_unix_identity']['ai']=[0,0]
            elif damage=='shutdown':bad['processes']['worker1']['state']['ExitCode']=2
            elif damage=='restart':bad['worker_restart_checks'].pop()
            elif damage=='cleanup':bad['cleanup']['owned_m4_material_root_removed']=False
            elif damage=='ddl':bad['mongo_runtime_ddl_attempts']=1
            elif damage=='business-claim':bad['combined_cutover_rehearsal_complete']=True
            else:bad['sources_unchanged']=False
            with self.subTest(damage=damage),self.assertRaises(ValueError):validate_startup(bad,self.candidate(),'e'*64)

    def test_wrong_reviewed_builder_or_source_never_reaches_archive_or_docker(self):
        fixture=ReadableImageLoader();fixture.readable_candidate=self.candidate();fixture.run=Mock()
        with patch('readable_image_start.verify_archive') as archive:
            for source,builder in (('f'*40,'d'*40),('a'*40,'f'*40),(None,None)):
                with self.subTest(source=source),self.assertRaises(ValueError):
                    fixture.load(Path('/absent'),'iam',source,reviewed_builder=builder)
            archive.assert_not_called();fixture.run.assert_not_called()

    def test_actual_python_probe_cannot_substitute_legacy_sdk_or_retired_clients(self):
        original=dict(sdk='0.5.0rc1',nsq_absent=True,tornado_absent=True,current_imports=True)
        fixture=SimpleNamespace(readable_candidate=self.candidate(),select=Mock(),once=Mock(return_value=json.dumps(original)))
        self.assertEqual(python_dependencies(fixture),original)
        self.assertFalse(fixture.once.call_args.kwargs['network'])
        for key,wrong in [('sdk','0.4.0'),('nsq_absent',False),('tornado_absent',False),('current_imports',False)]:
            bad=dict(original);bad[key]=wrong;fixture.once.return_value=json.dumps(bad)
            with self.subTest(key=key),self.assertRaises(ValueError):python_dependencies(fixture)

    def test_readable_mode_rejects_legacy_cutover_before_any_side_effect(self):
        base=['five_image_start.py']
        for key in ('sources','candidate','qs-initializer','iam-initializer','consumer-contract','report'):
            base += ['--'+key,'/absent/'+key]
        base += ['--readable-candidate','/absent/readable.json']
        for extra in (['--m4-rebuild'],['--startup-receipt','/absent/receipt.json']):
            with self.subTest(extra=extra),patch('sys.argv',base+extra),patch('five_image_start.FiveImageFixture') as fixture:
                with self.assertRaisesRegex(RuntimeError,'readable_startup_is_separate'):main()
                fixture.assert_not_called()


if __name__=='__main__':unittest.main()
