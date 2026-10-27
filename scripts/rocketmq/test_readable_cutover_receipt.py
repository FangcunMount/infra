import copy
import json
from pathlib import Path
import tempfile
import unittest

import test_readable_image_start as startup_test
from readable_cutover_receipt import read_startup, validate_cutover
from readable_cutover import CASES, COMPONENTS


class ReadableCutoverReceiptTest(unittest.TestCase):
    def fixture(self):
        original = startup_test.ReadableImageStartupTest()
        candidate = original.candidate()
        value = original.report()
        value.update(schema='readable-eight-instance-cutover/v1', startup_receipt_sha256='a'*64,
                     combined_cutover_rehearsal_complete=True)
        value['cases'].update(dict.fromkeys(CASES, True));value['passed']=len(value['cases'])
        state = {k:dict(state=dict(Status='exited',ExitCode=0,OOMKilled=False)) for k in COMPONENTS}
        binding = {k:dict(binding_sha256='b'*64,protocol_rows=0) for k in ('iam.mysql','qs.mysql','qs.mongo','ai.mysql')}
        value['readable_cutover']=dict(original_production_images_tested=False,production=False,
            system_acceptance=False,real_provider_not_claimed=True,initial_readable_shutdown=copy.deepcopy(state),
            compat_shutdown=copy.deepcopy(state),bindings_before=copy.deepcopy(binding),bindings_after=copy.deepcopy(binding),
            empty_inputs={str(i):dict(min_offset=0,max_offset=0) for i in range(20)},
            poststart_refused=['old-config','normal-retry'],actual_failed_start=dict(exit_code=125),
            coordinator_status=dict(runtime_may_have_started=True),elapsed_seconds=500,
            target_seconds=900,upper_seconds=1800,within_target=True,max_application_slots=8)
        return candidate,value

    def test_runtime_receipt_cannot_substitute_startup_business_or_weaken_bounds(self):
        candidate, value=self.fixture()
        self.assertIs(validate_cutover(value,candidate,'e'*64,'a'*64),value)
        for damage in ('schema','prior','skip','missing-case','budget','ddl','cleanup','business','old-image',
                       'binding','old-running','inputs','barrier','restored','deadline','nan','slots','target'):
            bad=copy.deepcopy(value);proof=bad['readable_cutover']
            if damage=='schema':bad['schema']='readable-eight-instance-startup/v1'
            elif damage=='prior':bad['startup_receipt_sha256']='f'*64
            elif damage=='skip':bad['skipped']=1
            elif damage=='missing-case':bad['cases'].pop(next(iter(CASES)))
            elif damage=='budget':bad['actual_runtime_budgets']['worker1']['nano_cpus']=2000000000
            elif damage=='ddl':bad['mysql_runtime_ddl_attempts']=1
            elif damage=='cleanup':bad['cleanup']['owned_m4_material_root_removed']=False
            elif damage=='business':bad['system_acceptance']=True
            elif damage=='old-image':proof['original_production_images_tested']=True
            elif damage=='binding':proof['bindings_after']['qs.mysql']['protocol_rows']=1
            elif damage=='old-running':proof['compat_shutdown']['worker2']['state']['ExitCode']=2
            elif damage=='inputs':proof['empty_inputs']['0']['max_offset']=1
            elif damage=='barrier':proof['coordinator_status']['runtime_may_have_started']=False
            elif damage=='restored':proof['poststart_refused'].pop()
            elif damage=='deadline':proof['elapsed_seconds']=1801
            elif damage=='nan':proof['elapsed_seconds']=float('nan')
            elif damage=='slots':proof['max_application_slots']=9
            else:proof['within_target']=False
            with self.subTest(damage=damage),self.assertRaises(ValueError):validate_cutover(bad,candidate,'e'*64,'a'*64)

    def test_independent_startup_requires_original_regular_bounded_file(self):
        original=startup_test.ReadableImageStartupTest();value=original.report();value['infra_sha']='a'*40
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'startup.json';path.write_text(json.dumps(value))
            report,digest=read_startup(path,original.candidate(),'e'*64)
            self.assertEqual(report,value);self.assertEqual(len(digest),64)
            link=Path(directory)/'linked';link.symlink_to(path)
            with self.assertRaises(ValueError):read_startup(link,original.candidate(),'e'*64)
            path.write_text(' '*(1024*1024+1))
            with self.assertRaises(ValueError):read_startup(path,original.candidate(),'e'*64)
