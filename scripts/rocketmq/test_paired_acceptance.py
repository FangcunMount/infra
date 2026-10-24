import copy
import json
import unittest
import xml.etree.ElementTree as ET

from paired_acceptance import (
    CORE_CASES, CORE_TEST, FULL_CASES, FULL_TESTS, FLAGS, MARKER,
    SDK_GO_VERSION, SDK_PYTHON_VERSION, paired_manifest, parse_receipt, read_receipt,
)
from routes import validate_v2


def receipt(full=False):
    cases = FULL_CASES if full else CORE_CASES
    return dict({k:True for k in FLAGS}, cases={k:True for k in cases},
        passed=len(cases),failed=0,skipped=0,root='original_go_mysql_and_python_sqlalchemy',
        sdk_go=SDK_GO_VERSION,sdk_python=SDK_PYTHON_VERSION,client_python='5.1.2',
        python='3.11.16',profile='full' if full else 'core',go_phase='ready',
        delivery_errors=[],last_observation=dict(polls=1,payload_calls=0,ack_count=2,operation_status='accepted',projection_version=2,projection_status='queued',ai_payload_reads=0))


def xml(names):
    root = ET.Element('testsuite')
    for name in names:
        ET.SubElement(root,'testcase',name=name,classname='tests.integration.rocketmq_paired_host')
    return ET.tostring(root,encoding='unicode')


class PairedAcceptanceTests(unittest.TestCase):
    def test_core_and_full_remain_distinct_exact_gates(self):
        self.assertEqual(len(CORE_CASES),10)
        self.assertEqual(len(FULL_CASES),25)
        self.assertEqual(len(FULL_TESTS),5)
        core = MARKER+json.dumps(receipt())
        full = MARKER+json.dumps(receipt(True))
        self.assertEqual(parse_receipt(core,xml([CORE_TEST]))['passed'],10)
        self.assertEqual(parse_receipt(full,xml(FULL_TESTS),full=True)['passed'],25)
        with self.assertRaises(RuntimeError):
            parse_receipt(core,xml([CORE_TEST]),full=True)
        with self.assertRaises(RuntimeError):
            parse_receipt(full,xml(FULL_TESTS))
        with self.assertRaises(RuntimeError):
            parse_receipt(full,xml([CORE_TEST]),full=True)

    def test_incomplete_skipped_failed_duplicate_or_substituted_native_evidence_rejected(self):
        data = MARKER+json.dumps(receipt(True))
        for raw in (xml(FULL_TESTS-{CORE_TEST}),xml([*FULL_TESTS,CORE_TEST]),
                    xml(FULL_TESTS).replace('tests.integration.rocketmq_paired_host','fake')):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                parse_receipt(data,raw,full=True)
        for tag in ('skipped','failure','error'):
            root = ET.fromstring(xml(FULL_TESTS))
            ET.SubElement(root[0],tag)
            with self.subTest(tag=tag), self.assertRaises(RuntimeError):
                parse_receipt(data,ET.tostring(root,encoding='unicode'),full=True)

    def test_private_fields_wrong_scope_and_invalid_counters_never_export(self):
        for change in ({'raw_wire':'secret'},{'paired_qs_business_not_claimed':True},
                       {'passed':True},{'failed':-1},{'go_phase':['ready']},
                       {'python':None},{'go_phase':'private_dsn_123'},
                       {'system_login_not_claimed':False},{'delivery_errors':['raw private error']},
                       {'last_observation':{'raw_wire':'secret'}},
                       {'last_observation':dict(polls=True,payload_calls=0,ack_count=0,operation_status='accepted')}):
            value = receipt();value.update(change)
            with self.subTest(change=change):
                self.assertIsNone(read_receipt(MARKER+json.dumps(value)))
        good = MARKER+json.dumps(receipt())
        self.assertIsNone(read_receipt(good+'\n'+good))
        self.assertIsNone(read_receipt(MARKER+'{broken'))

    def test_fixed_profile_sdk_version_must_match_actual_receipt(self):
        value=receipt(True);value['sdk_python']='0.4.0a3'
        raw=MARKER+json.dumps(value)
        self.assertIsNone(read_receipt(raw,full=True))
        self.assertIsNotNone(read_receipt(raw,full=True,sdk_python='0.4.0a3'))
        self.assertIsNone(read_receipt(raw,full=True,sdk_python='0.4.0'))

    def test_old_go_module_receipt_cannot_satisfy_current_fixed_profile(self):
        value=receipt(True);value['sdk_go']='v0.5.0-rocketmq-tx.2'
        self.assertIsNone(read_receipt(MARKER+json.dumps(value),full=True))

    def test_partial_failure_keeps_only_known_bounded_facts(self):
        value = receipt();value['cases']={};value['passed']=0
        value['failed']=1;value['go_phase']='owner_start'
        data = MARKER+json.dumps(value)
        self.assertIsNone(read_receipt(data))
        partial = read_receipt(data,partial=True)
        self.assertEqual(partial['go_phase'],'owner_start')
        value['cases']={'unlisted':True};value['passed']=1
        self.assertIsNone(read_receipt(MARKER+json.dumps(value),partial=True))

    def test_only_actual_owner_accounts_and_production_logical_subscriptions(self):
        manifest=paired_manifest()
        self.assertEqual(set(manifest['accounts']),{'qs','ai'})
        self.assertEqual({r['subscription'] for r in manifest['routes']},
            {'qs-ai.commands.v1','qs-server.ai-events.v1','qs-ai.acks.v1'})
        self.assertEqual(manifest['accounts']['qs']['publish'],['paired-command','paired-ack'])
        self.assertEqual(manifest['accounts']['ai']['publish'],['paired-event'])
        bad=copy.deepcopy(manifest)
        bad['accounts']['qs']['publish'].append('paired-event')
        with self.assertRaises((RuntimeError,ValueError)):
            validate_v2(bad)


if __name__=='__main__':
    unittest.main()
