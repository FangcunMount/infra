"""Receipt admission only; these synthetic unit inputs are never audit evidence."""
import json
from pathlib import Path
import tempfile
import unittest

from image_cutover_boundary import COMPONENTS, SOURCES, parse_private_hashes, startup_receipt


def synthetic_unit_receipt():
    return dict(schema='m3-five-actual-image-startup-trial/v2', passed=15, failed=0, skipped=0,
        cases={str(n):True for n in range(15)}, sources=SOURCES, sources_unchanged=True,
        mysql_runtime_ddl_attempts=0,mongo_runtime_ddl_attempts=0,
        mongo_ddl_audit=dict(positive_controls=4,commands=[]),
        production=False,system_acceptance=False,combined_cutover_rehearsal_complete=False,c1_cutover_barrier_exercised=False,
        processes={c:{'state':dict(Status='exited',ExitCode=0,OOMKilled=False)} for c in COMPONENTS},
        cleanup=dict(compose_down_succeeded=True,private_directory_removed=True,existing_containers_unchanged=True,existing_networks_unchanged=True),
        candidates={target:dict(source_sha=SOURCES[source],archive_sha256='1'*64,image_config_id='sha256:'+'2'*64)
            for target,source in [('iam','iam'),('ai','ai'),('qs-api','qs'),('qs-worker','qs'),('qs-collection','qs')]})


class CutoverReceiptAdmissionTest(unittest.TestCase):
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

    def test_all_seven_processes_and_original_cleanup_are_required(self):
        value=synthetic_unit_receipt();value['processes'].pop('worker3')
        with self.assertRaises(RuntimeError):self.check(value)
        value=synthetic_unit_receipt();value['processes']['api']['state']['ExitCode']=137
        with self.assertRaises(RuntimeError):self.check(value)
        value=synthetic_unit_receipt();value['cleanup']['private_directory_removed']=False
        with self.assertRaises(RuntimeError):self.check(value)

    def test_matching_versions_do_not_replace_frozen_image_identity(self):
        value=synthetic_unit_receipt();value['candidates']['qs-worker']['source_sha']=SOURCES['iam']
        with self.assertRaises(RuntimeError):self.check(value)
        value=synthetic_unit_receipt();value['candidates']['ai']['archive_sha256']='unverified'
        with self.assertRaises(RuntimeError):self.check(value)
