import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from publish_candidates import Registry, destinations, load_plan, publish, validate_reports

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT/'docs/server/evidence/rocketmq-m3-image-publication-plan-20261025.json'


class PublicationTest(unittest.TestCase):
    def setUp(self):
        self.plan = load_plan(PLAN, hashlib.sha256(PLAN.read_bytes()).hexdigest())

    def test_reviewed_scope_and_digest_reject_drift(self):
        with self.assertRaisesRegex(ValueError,'reviewed_plan_changed'):
            load_plan(PLAN,'0'*64)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'plan.json'
            for kind in ('registry','repository','builder'):
                plan = copy.deepcopy(self.plan)
                if kind == 'registry': plan['registry'] = 'elsewhere.example'
                elif kind == 'repository': plan['targets']['iam']['repository'] = 'other'
                else: plan['targets']['iam']['builder_source_sha'] = '0'*40
                path.write_text(json.dumps(plan))
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    load_plan(path,hashlib.sha256(path.read_bytes()).hexdigest())

    def test_unique_run_attempt_tags_never_use_release_or_latest(self):
        first = destinations(self.plan,'123','1')
        self.assertEqual(len(first),5)
        self.assertNotEqual(first,destinations(self.plan,'123','2'))
        self.assertNotEqual(first,destinations(self.plan,'124','1'))
        self.assertTrue(all(':m3-candidate-' in tag and ':latest' not in tag for tag in first.values()))
        for run,attempt in (('','1'),('$(bad)','1'),('1','0')):
            with self.assertRaises(ValueError): destinations(self.plan,run,attempt)

    def test_all_preflights_before_first_write_and_partial_failure_keeps_unknown(self):
        events = []
        class Backend:
            def tags(self,repo): events.append(('read',repo));return []
            def copy(self,path,ref):
                events.append(('write',ref))
                if len([e for e in events if e[0]=='write']) == 2: raise TimeoutError()
            def verify(self,ref,digest):return ref.rsplit(':',1)[0]+'@sha256:'+'1'*64
        refs = destinations(self.plan,'123','1')
        report = dict(published={},complete=False)
        with self.assertRaises(TimeoutError):
            publish(self.plan,{k:Path('/owned') for k in refs},refs,Backend(),report,lambda:None)
        self.assertEqual([e[0] for e in events[:6]],['read']*5+['write'])
        self.assertEqual(len(report['published']),1)
        self.assertTrue(report['registry_write_attempted'])
        self.assertEqual(report['current_target'],list(refs)[1])
        self.assertFalse(report['complete'])

    def test_auth_errors_or_existing_tags_never_authorize_writes(self):
        refs = destinations(self.plan,'123','1')
        events = []
        class Backend:
            def tags(self,repo): raise PermissionError('auth failure')
            def copy(self,*args):events.append('write')
        with self.assertRaises(PermissionError):
            publish(self.plan,{},refs,Backend(),{'published':{}},lambda:None)
        class Conflict(Backend):
            def tags(self,repo):return [next(iter(refs.values())).rsplit(':',1)[1]]
        with self.assertRaisesRegex(ValueError,'tag_exists'):
            publish(self.plan,{},refs,Conflict(),{'published':{}},lambda:None)
        self.assertEqual(events,[])

    def test_remote_manifest_verifies_actual_config_and_digest_readback(self):
        raw = json.dumps(dict(schemaVersion=2,config=dict(digest='sha256:'+'2'*64),layers=[])).encode()
        calls = []
        def run(args):calls.append(args);return raw
        registry = Registry(Path('/private/auth.json'),run=run)
        result = registry.verify('registry/repo:tag','sha256:'+'2'*64)
        self.assertEqual(result,'registry/repo@sha256:'+hashlib.sha256(raw).hexdigest())
        self.assertIn('docker://'+result,calls[1])
        with self.assertRaisesRegex(ValueError,'config_differs'):
            registry.verify('registry/repo:tag','sha256:'+'3'*64)
        with self.assertRaisesRegex(ValueError,'plaintext_only_owned_loopback'):
            Registry(Path('/private/auth.json'),tls=False).tags('registry/repo')

    def test_seven_process_or_changed_restore_cannot_pass_even_with_new_report_hash(self):
        # Model the native evidence boundary, bypassing only the already-tested
        # startup parser. A new JSON digest must not authorize a weaker report.
        candidates={k:{f:r[f] for f in ('source_sha','builder_source_sha','image_config_id','archive_sha256')}
                    for k,r in self.plan['targets'].items()}
        names=('iam','ai','api','collection','collection2','worker1','worker2','worker3')
        initial=dict(sources={'frozen':True},candidates=candidates,
                     dependency_versions={'mysql':'8.0.36','mongo':'7.0.31'},actual_runtime_budgets={})
        value=dict(initial,passed=19,failed=0,skipped=0,cases={str(i):True for i in range(19)},
            infra_sha=self.plan['cutover']['head_sha'],startup_receipt_sha256=self.plan['startup']['report_sha256'],
            processes={k:dict(state=dict(Status='exited',ExitCode=0,OOMKilled=False)) for k in names},
            actual_up_after_marker=list(names),actual_cutover=dict(actual_processes=8,elapsed_seconds=51,
                poststart_refused=['old-full-backup','poststart-offline']),
            coordinator_status=dict(first_start_recorded=True,old_data_restore_eligible=False),
            full_scope_restore=dict(snapshots_before={'exact':'before'},snapshots_after={'exact':'before'}),
            mysql_runtime_ddl_attempts=0,mongo_runtime_ddl_attempts=0,sources_unchanged=True,
            cleanup=dict(complete=True),production=False,system_acceptance=False)
        with tempfile.TemporaryDirectory() as temp, patch('publish_candidates.startup_receipt',return_value=(initial,None)):
            startup=Path(temp)/'startup';startup.write_text('fixed')
            cutover=Path(temp)/'cutover'
            plan=copy.deepcopy(self.plan)
            plan['startup']['report_sha256']=hashlib.sha256(startup.read_bytes()).hexdigest()
            value['startup_receipt_sha256']=plan['startup']['report_sha256']
            for changed in ('none','count','restore','production'):
                trial=copy.deepcopy(value)
                if changed=='count':trial['actual_cutover']['actual_processes']=7
                elif changed=='restore':trial['full_scope_restore']['snapshots_after']={'changed':True}
                elif changed=='production':trial['production']=True
                cutover.write_text(json.dumps(trial));plan['cutover']['report_sha256']=hashlib.sha256(cutover.read_bytes()).hexdigest()
                if changed=='none':validate_reports(plan,startup,cutover)
                else:
                    with self.subTest(changed=changed),self.assertRaisesRegex(ValueError,'current_c1'):
                        validate_reports(plan,startup,cutover)


if __name__ == '__main__': unittest.main()
