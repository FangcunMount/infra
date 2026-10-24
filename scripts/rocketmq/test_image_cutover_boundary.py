"""Receipt admission only; these synthetic unit inputs are never audit evidence."""
import json
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from image_cutover_boundary import ActualImageBoundary, COMPONENTS, SOURCES, parse_private_hashes, startup_receipt, write_reviewed_start_plan
from start_boundary import Boundary, BoundaryError, _encoded
from test_start_boundary import fixture
from test_runtime_start import target_fixture
import runtime_start
from audit_transaction_limit import write_private
from image_start_fixture import IMAGE_PROVENANCE


def synthetic_unit_receipt():
    return dict(schema='m3-five-actual-image-startup-trial/v4', passed=16, failed=0, skipped=0,
        workers_prepared={name:True for name in ('worker1','worker2','worker3')},
        worker_restart_checks=[dict(component=name,cycle=cycle,result={'state':dict(Status='exited',ExitCode=0,OOMKilled=False)})
            for name in ('worker1','worker2','worker3') for cycle in range(1,4)],
        cases={str(n):True for n in range(16)}, sources=SOURCES, sources_unchanged=True,
        dependency_versions=dict(mysql='8.0.36',mongo='7.0.31'),
        actual_runtime_budgets={name:dict(memory_bytes=memory*1024*1024,nano_cpus=int(cpu*1_000_000_000))
          for name,memory,cpu in (('iam',1024,1),('ai',768,.75),('api',1024,2),('collection',320,1),('collection2',320,1),('worker1',768,1),('worker2',768,1),('worker3',768,1))},
        mysql_runtime_ddl_attempts=0,mongo_runtime_ddl_attempts=0,
        mongo_ddl_audit=dict(positive_controls=4,commands=[]),
        production=False,system_acceptance=False,combined_cutover_rehearsal_complete=False,c1_cutover_barrier_exercised=False,
        processes={c:{'state':dict(Status='exited',ExitCode=0,OOMKilled=False)} for c in COMPONENTS},
        cleanup=dict(compose_down_succeeded=True,private_directory_removed=True,existing_containers_unchanged=True,existing_networks_unchanged=True),
        candidates={target:dict(source_sha=SOURCES[source],builder_source_sha=IMAGE_PROVENANCE[(target,SOURCES[source])],archive_sha256='1'*64,image_config_id='sha256:'+'2'*64)
            for target,source in [('iam','iam'),('ai','ai'),('qs-api','qs'),('qs-worker','qs'),('qs-collection','qs')]})


class CutoverReceiptAdmissionTest(unittest.TestCase):
    def test_generated_plan_is_accepted_by_the_original_canonical_consumer(self):
        with tempfile.TemporaryDirectory() as root:
            _,_,value=target_fixture(root)
            path=Path(root)/'actual-generated-plan.json'
            self.assertEqual(write_reviewed_start_plan(path,value),value)
            self.assertEqual(path.read_bytes(),_encoded(value))
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            with self.assertRaises(FileExistsError):write_reviewed_start_plan(path,value)
            wrong=Path(root)/'report-style-plan.json';write_private(wrong,value)
            with self.assertRaisesRegex(BoundaryError,'canonical reviewed object'):
                runtime_start.load(wrong,hashlib.sha256(wrong.read_bytes()).hexdigest())

    def test_private_file_hashes_cannot_substitute_similar_paths_or_partial_output(self):
        raw='1'*64+'  /fixture/runtime.json\n'+'2'*64+'  /fixture/routes.json\n'
        self.assertEqual(set(parse_private_hashes(raw,('runtime.json','routes.json'))),{'/fixture/runtime.json','/fixture/routes.json'})
        for bad in (raw.splitlines()[0],raw+raw,raw.replace('/fixture/routes.json','/fixture/routes.json.extra'),raw.replace('/fixture/runtime.json','/other/runtime.json')):
            with self.assertRaises(RuntimeError):parse_private_hashes(bad,('runtime.json','routes.json'))

    def check(self,value):
        with tempfile.TemporaryDirectory(prefix='m3-receipt-unit-') as root:
            p=Path(root)/'synthetic-unit-only.json';p.write_text(json.dumps(value));p.chmod(0o600)
            return startup_receipt(p)

    def test_separate_successful_startup_trial_can_be_referenced(self):
        value=synthetic_unit_receipt();self.assertEqual(self.check(value)[0],value)

    def test_partial_health_or_tampered_source_is_rejected(self):
        for update in (dict(passed=7,failed=1),dict(sources_unchanged=False),dict(mysql_runtime_ddl_attempts=1),dict(production=True),dict(c1_cutover_barrier_exercised=True)):
            value=synthetic_unit_receipt();value.update(update)
            with self.subTest(update=update),self.assertRaises(RuntimeError):self.check(value)
        value=synthetic_unit_receipt();value['sources']=dict(value['sources'],qs='3'*40)
        with self.assertRaises(RuntimeError):self.check(value)

    def test_all_eight_processes_and_original_cleanup_are_required(self):
        value=synthetic_unit_receipt();value['processes'].pop('worker3')
        with self.assertRaises(RuntimeError):self.check(value)
        value=synthetic_unit_receipt();value['processes']['api']['state']['ExitCode']=137
        with self.assertRaises(RuntimeError):self.check(value)
        value=synthetic_unit_receipt();value['cleanup']['private_directory_removed']=False
        with self.assertRaises(RuntimeError):self.check(value)

    def test_http_only_worker_receipts_cannot_authorize_cutover(self):
        value=synthetic_unit_receipt();value.pop('workers_prepared')
        with self.assertRaises(RuntimeError):self.check(value)
        value=synthetic_unit_receipt();value['workers_prepared']['worker3']=False
        with self.assertRaises(RuntimeError):self.check(value)
        value=synthetic_unit_receipt();value['schema']='m3-five-actual-image-startup-trial/v2'
        with self.assertRaises(RuntimeError):self.check(value)

    def test_incomplete_or_nonzero_restarts_cannot_authorize_cutover(self):
        value=synthetic_unit_receipt();value['worker_restart_checks'].pop()
        with self.assertRaises(RuntimeError):self.check(value)
        value=synthetic_unit_receipt();value['worker_restart_checks'][0]['result']['state']['ExitCode']=2
        with self.assertRaises(RuntimeError):self.check(value)
        value=synthetic_unit_receipt();value['worker_restart_checks'][0]['cycle']=4
        with self.assertRaises(RuntimeError):self.check(value)

    def test_matching_versions_do_not_replace_frozen_image_identity(self):
        value=synthetic_unit_receipt();value['candidates']['qs-worker']['source_sha']=SOURCES['iam']
        with self.assertRaises(RuntimeError):self.check(value)
        value=synthetic_unit_receipt();value['candidates']['ai']['archive_sha256']='unverified'
        with self.assertRaises(RuntimeError):self.check(value)

    def test_failed_target_start_keeps_real_barrier_and_owned_process_diagnostic(self):
        # Real fsync-backed coordinator; target command/readback are controlled
        # unit seams. This test never claims an actual Docker process existed.
        for owner in ('owned-unit', 'different-owner'):
            with self.subTest(owner=owner),tempfile.TemporaryDirectory() as root:
                directory,_,sha=fixture(root)
                adapter=ActualImageBoundary.__new__(ActualImageBoundary)
                adapter.directory=directory;adapter.binding_sha=sha;adapter.plans={'api':{}}
                adapter.private_inputs={};adapter.started=set()
                adapter.global_lock=Path(root)/'global.lock';adapter.ai_lock=Path(root)/'ai.lock'
                adapter.f=SimpleNamespace(project='owned-unit',report={},applications={},
                    run=lambda *a,**k:SimpleNamespace(returncode=0,stdout=owner))
                def failed(_):
                    self.assertTrue((directory/'first-runtime-start.json').is_file())
                    raise RuntimeError('controlled_target_failure')
                with patch('image_cutover_boundary.private_input_hashes',return_value={}),patch('image_cutover_boundary.runtime_start.execute',side_effect=failed):
                    with self.assertRaisesRegex(RuntimeError,'controlled_target_failure'):adapter.start('api')
                self.assertEqual(adapter.f.applications,{'api':'owned-unit-api'} if owner=='owned-unit' else {})
                self.assertFalse(adapter.started)
                with Boundary(directory,sha) as operation:
                    self.assertEqual(operation.status()['phase'],'runtime_start_failed')
                    self.assertFalse(operation.status()['old_data_restore_eligible'])
                    with self.assertRaises(BoundaryError):operation.restore_before_start('forbidden',lambda:self.fail('old restore ran'))

class LiveProductionProfileTest(unittest.TestCase):
    def test_current_replica_scope_cannot_accept_the_old_seven_process_receipt(self):
        self.assertEqual(set(COMPONENTS), {'iam','ai','api','collection','collection2','worker1','worker2','worker3'})
        value=synthetic_unit_receipt();value['processes'].pop('collection2')
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'old-seven-process.json';path.write_text(json.dumps(value))
            with self.assertRaises(RuntimeError):startup_receipt(path)

    def test_old_database_versions_or_small_iam_budget_cannot_authorize_cutover(self):
        cases=[]
        for key,value in (('mysql','8.0.44'),('mongo','7.0.37')):
            r=synthetic_unit_receipt();r['dependency_versions'][key]=value;cases.append(r)
        r=synthetic_unit_receipt();r['actual_runtime_budgets']['iam']['memory_bytes']=512*1024*1024;cases.append(r)
        r=synthetic_unit_receipt();r['schema']='m3-five-actual-image-startup-trial/v3';cases.append(r)
        for value in cases:
            with self.subTest(value=value),tempfile.TemporaryDirectory() as root:
                path=Path(root)/'wrong-profile.json';path.write_text(json.dumps(value))
                with self.assertRaises(RuntimeError):startup_receipt(path)

    def test_final_receipt_counts_the_verified_eight_started_processes(self):
        import time
        with tempfile.TemporaryDirectory() as root:
            directory,_,sha=fixture(root)
            with Boundary(directory,sha) as operation:
                operation.start('unit-runtime',lambda:None)
            adapter=ActualImageBoundary.__new__(ActualImageBoundary)
            adapter.directory=directory;adapter.binding_sha=sha;adapter.started=set(COMPONENTS)
            adapter.window_started=time.monotonic();adapter.lock_inodes={}
            result=adapter.finish()
            self.assertEqual(result['actual_processes'],8)
            self.assertEqual(result['actual_processes'],len(adapter.started))
            self.assertEqual(result['poststart_refused'],['old-full-backup','poststart-offline'])
            self.assertFalse(result['production_authorized'])
