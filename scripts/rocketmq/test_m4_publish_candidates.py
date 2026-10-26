import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from m4_publish_candidates import destinations, load_plan, retrieve, validate_report

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / 'docs/server/evidence/rocketmq-m4-image-publication-plan-20261027-v2.json'
REPORT = ROOT / 'docs/server/evidence/rocketmq-m4-c08-final-eight-instance-native-20261027.json'


class M4PublicationTest(unittest.TestCase):
    def setUp(self):
        self.plan = load_plan(PLAN, hashlib.sha256(PLAN.read_bytes()).hexdigest())

    def test_actual_final_eight_instance_receipt_matches_five_reviewed_archives(self):
        value = validate_report(self.plan, REPORT)
        self.assertEqual(len(value['processes']), 8)
        self.assertEqual(value['passed'], 18)

    def test_immutable_reviewed_plan_and_original_registry_scope(self):
        with self.assertRaisesRegex(ValueError, 'reviewed_plan_changed'):
            load_plan(PLAN, '0' * 64)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'plan.json'
            for kind in ('repository', 'builder', 'source', 'mutable-run', 'sdk'):
                plan = copy.deepcopy(self.plan)
                if kind == 'repository': plan['targets']['iam']['repository'] = 'other'
                elif kind == 'builder': plan['targets']['iam']['builder_source_sha'] = '0' * 40
                elif kind == 'source': plan['targets']['iam']['source_sha'] = '0' * 40
                elif kind == 'mutable-run': plan['candidate']['image_runs']['iam'] = 'main'
                else: plan['candidate']['sdk']['go'] = 'latest'
                path.write_text(json.dumps(plan))
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    load_plan(path, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_changed_native_report_even_with_recomputed_digest_cannot_weaken_gate(self):
        original = json.loads(REPORT.read_bytes())
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'report.json'
            for kind in ('seven-process', 'failed-case', 'skip', 'unclean-exit', 'runtime-ddl',
                         'source', 'candidate', 'archive', 'worker-budget', 'cleanup', 'retired-client', 'production'):
                value = copy.deepcopy(original)
                if kind == 'seven-process': del value['processes']['worker3']
                elif kind == 'failed-case': value['cases'][next(iter(value['cases']))] = False
                elif kind == 'skip': value['skipped'] = 1
                elif kind == 'unclean-exit': value['processes']['iam']['state']['ExitCode'] = 1
                elif kind == 'runtime-ddl': value['mysql_runtime_ddl_attempts'] = 1
                elif kind == 'source': value['sources']['qs'] = '0' * 40
                elif kind == 'candidate': value['final_candidate'] = False
                elif kind == 'archive': value['candidates']['iam']['image_config_id'] = 'sha256:' + '0' * 64
                elif kind == 'worker-budget': value['actual_source_worker_concurrency'] = 49
                elif kind == 'cleanup': value['cleanup']['private_directory_removed'] = False
                elif kind == 'retired-client': value['final_python_dependencies']['nsq_absent'] = False
                else: value['production'] = True
                path.write_text(json.dumps(value))
                plan = copy.deepcopy(self.plan)
                plan['startup']['report_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    validate_report(plan, path)

    def test_changed_report_rejected_before_content_read(self):
        plan = copy.deepcopy(self.plan)
        plan['startup']['report_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'native_report_changed'):
            validate_report(plan, REPORT)

    def test_failed_or_wrong_producer_run_rejected_before_download_or_registry(self):
        for kind in ('failure', 'wrong-sha', 'wrong-workflow', 'wrong-event'):
            calls = []
            def run(args):
                calls.append(args)
                value = dict(id=int(args[-1].split('/')[-1]), conclusion='success',
                             head_sha=self.plan['candidate']['builder_sha'], event='workflow_dispatch',
                             path='.github/workflows/rocketmq-final-images.yml')
                if kind == 'failure': value['conclusion'] = 'failure'
                elif kind == 'wrong-sha': value['head_sha'] = '0' * 40
                elif kind == 'wrong-workflow': value['path'] = '.github/workflows/other.yml'
                else: value['event'] = 'pull_request'
                return json.dumps(value).encode()
            with tempfile.TemporaryDirectory() as temp, self.subTest(kind=kind):
                with self.assertRaisesRegex(ValueError, 'exact_m4_build'):
                    retrieve(self.plan, Path(temp), run)
            self.assertEqual(len(calls), 1)

    def test_new_unique_m4_tags_cannot_overwrite_m3_or_stable_names(self):
        one = destinations(self.plan, '123', '1')
        self.assertEqual(len(one), 5)
        self.assertNotEqual(one, destinations(self.plan, '123', '2'))
        self.assertNotEqual(one, destinations(self.plan, '124', '1'))
        self.assertTrue(all(':m4-candidate-' in x for x in one.values()))
        for run, attempt in (('main', '1'), ('1', '0')):
            with self.assertRaises(ValueError): destinations(self.plan, run, attempt)


if __name__ == '__main__':
    unittest.main()
