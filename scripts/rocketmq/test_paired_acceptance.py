import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
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
    def test_stable_qs_profile_still_requires_exact_published_module(self):
        from image_sdk_profile import sdk_profile
        from paired_acceptance import prepare_qs
        from readable_host_acceptance import MODULE
        fixed = sdk_profile('readable-stable')
        module = dict(Path='github.com/FangcunMount/reliable-messaging',
            Version=fixed['go'], Sum=fixed['go_sum'], GoModSum=MODULE['GoModSum'])
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,
                QS_AI_READABLE_SDK_PROFILE='readable-stable'):
            root = Path(tmp)
            (root/'go.mod').write_text('module fixture\n')
            helper = root/'tests/m3_ai_paired_probe/main.go'
            helper.parent.mkdir(parents=True)
            helper.write_text('package main\n')
            def run(argv, **kwargs):
                output = ''
                if argv[:3] == ['git','rev-parse','HEAD']: output = 'a'*40
                elif argv[:3] == ['go','list','-m']: output = json.dumps(module)
                elif argv == ['go','version']: output = 'go version go1.25.12 linux/amd64'
                elif argv[:2] == ['go','build']: (root/'qs-paired-host').write_bytes(b'fixture')
                return SimpleNamespace(stdout=output)
            proof = {}
            value = prepare_qs(root,root,'rocketmq-m2-fixture',3306,'fixture',run,proof,readable=True)
            self.assertEqual(value['sdk_go_version'], fixed['go'])
            self.assertEqual(proof['paired_qs']['sdk_module'], module)
            for key, bad in [('Sum','wrong'),('Version','v0.6.0-rc.1'),('Replace',{})]:
                before = dict(module)
                module[key] = bad
                with self.assertRaises(ValueError):
                    prepare_qs(root,root,'rocketmq-m2-fixture',3306,'fixture',run,{},readable=True)
                module.clear(); module.update(before)

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

    def test_readable_receipt_cannot_pass_legacy_gate_and_requires_both_fixed_versions(self):
        value=receipt(True)
        value.update(sdk_go='v0.6.0-rc.1',sdk_python='0.5.0rc1')
        raw=MARKER+json.dumps(value)
        native=xml(FULL_TESTS)
        with self.assertRaises(RuntimeError):parse_receipt(raw,native,full=True)
        for go,python in [('v0.5.0','0.5.0rc1'),('v0.6.0-rc.1','0.4.0')]:
            with self.subTest(go=go,python=python),self.assertRaises(RuntimeError):
                parse_receipt(raw,native,full=True,sdk_go=go,sdk_python=python)
        self.assertEqual(parse_receipt(raw,native,full=True,sdk_go='v0.6.0-rc.1',
            sdk_python='0.5.0rc1')['passed'],25)

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
