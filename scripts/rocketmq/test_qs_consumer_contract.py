import copy
import json
from pathlib import Path
import unittest

from m3_resources import manifest
from qs_consumer_contract import parse_contract, validate_manifest
from routes import consumer_group_v2, physical_topic_v2

ROOT=Path(__file__).resolve().parents[2]


class OriginalConsumerContractTest(unittest.TestCase):
    def setUp(self):
        self.contract=json.loads((ROOT/'scripts/rocketmq/image_fixtures/qs_consumer_contract.json').read_text())
        self.document=manifest(ROOT)

    def test_manifest_covers_the_actual_go_registry_consumer(self):
        self.assertEqual(validate_manifest(self.document,self.contract),1)

    def test_old_survey_normal_binding_cannot_substitute_answersheet_transaction(self):
        bad=copy.deepcopy(self.document)
        route=next(r for r in bad['routes'] if r['subscription']=='qs-apiserver-modelcatalog-hot-rank-v1')
        route.update(topic='qs.survey.lifecycle',message_type='NORMAL',owner='qs.mysql')
        route['physical_topic']=physical_topic_v2(route['topic'],route['message_type'],route['owner'],route['route_revision'])
        route['consumer_group']=consumer_group_v2(route['topic'],route['subscription'])
        with self.assertRaises(RuntimeError):validate_manifest(bad,self.contract)

    def test_reading_the_right_topic_alone_does_not_grant_the_subscription(self):
        bad=copy.deepcopy(self.document)
        bad['accounts']['m3-qs-apiserver']['subscriptions']=[]
        with self.assertRaises(RuntimeError):validate_manifest(bad,self.contract)

    def test_source_identity_and_bounded_original_receipt_required(self):
        raw='QS_CONSUMER_CONTRACT '+json.dumps(self.contract)
        self.assertEqual(parse_contract(raw),self.contract)
        for bad in ('',raw+'\n'+raw,raw.replace(self.contract['source_sha'],'0'*40)):
            with self.assertRaises(RuntimeError):parse_contract(bad)

    def test_new_rehearsal_keeps_exact_source_and_original_route_checks(self):
        contract=copy.deepcopy(self.contract);contract['source_sha']='a'*40
        raw='QS_CONSUMER_CONTRACT '+json.dumps(contract)
        self.assertEqual(parse_contract(raw,source_sha='a'*40),contract)
        self.assertEqual(validate_manifest(self.document,contract,source_sha='a'*40),1)
        with self.assertRaises(RuntimeError):parse_contract(raw)
        with self.assertRaises(RuntimeError):validate_manifest(self.document,contract)
        with self.assertRaises(RuntimeError):parse_contract(raw,source_sha='b'*40)
        bad=copy.deepcopy(self.document);bad['accounts']['m3-qs-apiserver']['subscriptions']=[]
        with self.assertRaises(RuntimeError):validate_manifest(bad,contract,source_sha='a'*40)
