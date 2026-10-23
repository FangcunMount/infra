import json
import tempfile
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from paired_fault_acceptance import CASES, TESTS, SCOPE, parse_receipt, read_partial_receipt, write_control
from paired_acceptance import FULL_TESTS
from test_paired_acceptance import receipt as baseline

AI='a'*40
QS='b'*40

def receipt(full=False):
    return dict(source_sha=AI,qs_source_sha=QS,profile='full' if full else 'core',
        passed=15,failed=0,skipped=0,cases={k:True for k in CASES},scope=SCOPE,
        public_http_real_provider_system_production_not_claimed=True,synthetic_read_side=True,
        proof=dict(qs_sigkill=dict(half_prepared_before_loss=1,proxy_stopped_before_root_release=True,
            original_root_lock_wait_observed=True,old_exit_code=-9,distinct_producer_pid=True,
            old_seals=1,recovered_completed_results=0,recovered_half_prepared=0,
            original_wire_unchanged=True,final_recovered_seals=2,provider_invocations=0,
            recovered_broker_commit_checks=1,resources=dict(closed=True,private_files_removed=True,
                original_exit_code=-9,replacement_exit_codes=[0])),
            broker_restart=dict(local_calls=1,half_prepared_before_kill=2,local_calls_before_kill=0,half_prepared=2,actual_final_unknown=2,
                broker_commit_checks=2,pending_calls=0,provider_invocations=0,
                resources=dict(closed=True,private_files_removed=True,original_exit_code=0,
                    replacement_exit_codes=[]))))

def output(row,full=False):
    text='M3_PAIRED_FAULT_RECEIPT '+json.dumps(row)
    if full:text+='\nM3_PAIRED_BASELINE_RECEIPT '+json.dumps(baseline(True))
    return text

def xml(full=False):
    root=ET.Element('testsuite')
    for name in TESTS | (FULL_TESTS if full else frozenset()):
        ET.SubElement(root,'testcase',name=name,classname='tests.integration.'+(
            'rocketmq_paired_faults' if name in TESTS else 'rocketmq_paired_host'))
    return ET.tostring(root,encoding='unicode')

class PairedFaultAcceptanceTests(unittest.TestCase):
    def test_development_two_and_final_seven_have_distinct_evidence(self):
        for full in (False,True):
            result=parse_receipt(output(receipt(full),full),xml(full),AI,QS,full=full)
            self.assertEqual(len(result['combined_cases']),40 if full else 15)
        with self.assertRaises(RuntimeError):parse_receipt(output(receipt()),xml(),AI,QS,full=True)

    def test_failed_skipped_empty_and_substituted_native_rejected(self):
        for tag in ('failure','error','skipped'):
            root=ET.fromstring(xml());ET.SubElement(root[0],tag)
            with self.assertRaises(RuntimeError):parse_receipt(output(receipt()),ET.tostring(root,encoding='unicode'),AI,QS,full=False)
        for raw in ('<testsuite/>',xml().replace('rocketmq_paired_faults','fake')):
            with self.assertRaises(RuntimeError):parse_receipt(output(receipt()),raw,AI,QS,full=False)

    def test_wrong_source_private_fields_false_process_and_reexecution_rejected(self):
        changes=[lambda r:r.update(source_sha='c'*40),lambda r:r.update(raw_wire='private'),
            lambda r:r.update(passed=True),lambda r:r['proof']['qs_sigkill'].update(old_exit_code=0),
            lambda r:r['proof']['qs_sigkill'].update(recovered_half_prepared=1),
            lambda r:r['proof']['qs_sigkill'].update(recovered_broker_commit_checks=0),
            lambda r:r['proof']['broker_restart'].update(local_calls=2),
            lambda r:r['proof']['qs_sigkill']['resources'].update(replacement_exit_codes=[False]),
            lambda r:r['proof']['broker_restart']['resources'].update(closed=False)]
        for change in changes:
            row=receipt();change(row)
            with self.assertRaises(RuntimeError):parse_receipt(output(row),xml(),AI,QS,full=False)

    def test_partial_failure_exports_only_known_counters_not_private_values(self):
        row=receipt();row['failed']=1
        row['proof']['broker_restart']['raw_wire']='private'
        row['proof']['broker_restart']['local_calls']=True
        partial=read_partial_receipt(output(row),AI,QS)
        self.assertFalse(partial['complete_acceptance_claimed'])
        self.assertNotIn('private',json.dumps(partial))
        self.assertNotIn('local_calls',partial['counters']['broker_restart'])
        self.assertIsNone(read_partial_receipt(output(row),'c'*40,QS))
        self.assertIsNone(read_partial_receipt(output(row)+'\n'+output(row),AI,QS))

    def test_owned_control_is_new_and_private(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'control';write_control(p,'broker-ready')
            self.assertEqual(p.stat().st_mode&0o777,0o600)
            with self.assertRaises(RuntimeError):write_control(p,'again')

if __name__=='__main__':unittest.main()
