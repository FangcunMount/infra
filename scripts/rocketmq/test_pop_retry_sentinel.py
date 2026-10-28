import copy
import json
from pathlib import Path
import unittest

from pop_retry_sentinel import MARKER, receipt, route_and_roles

ROOT=Path(__file__).resolve().parents[2]


class PopRetrySentinelTest(unittest.TestCase):
    def setUp(self):
        self.config=dict(manifest=json.loads((ROOT/'components/rocketmq/serverd-routes-readable-v3.json').read_bytes()))
        self.route,self.publisher,self.subscriber=route_and_roles(self.config)
        self.row=dict(schema='owned-actual-pop-v2-sentinel/v1',topic=self.route['physical_topic'],
            group=self.route['consumer_group'],retry_topic='%RETRY%'+self.route['consumer_group']+'+'+self.route['physical_topic'],
            body_sha256='a'*64,received=1,ack_calls=0,clients_closed=True)

    def test_existing_normal_input_and_minimal_application_roles_without_mutation(self):
        before=copy.deepcopy(self.config)
        self.assertEqual(self.publisher,'m3-qs-apiserver')
        self.assertEqual(self.subscriber,'m3-qs-worker')
        self.assertEqual(self.config,before)
        self.assertEqual(receipt(MARKER+json.dumps(self.row),self.route),self.row)

    def test_old_manifest_wrong_type_missing_grant_or_duplicate_input_cannot_send(self):
        for change in ('v2','type','missing-publisher','duplicate'):
            value=copy.deepcopy(self.config)
            if change=='v2':value['manifest']=json.loads((ROOT/'components/rocketmq/serverd-routes-m3-v2.json').read_bytes())
            elif change=='type':
                row=next(r for r in value['manifest']['routes'] if r['id']==self.route['id']);row['message_type']='TRANSACTION'
            elif change=='missing-publisher':
                for grants in value['manifest']['accounts'].values():
                    grants['publish']=[r for r in grants['publish'] if r!=self.route['id']]
            else:value['manifest']['routes'].append(copy.deepcopy(self.route))
            with self.subTest(change=change),self.assertRaises(ValueError):route_and_roles(value)

    def test_actual_first_delivery_no_ack_and_closed_clients_all_required(self):
        for changes in ({'received':0},{'received':True},{'received':2},{'ack_calls':1},{'ack_calls':False},
                        {'clients_closed':False},{'body_sha256':'private'},{'topic':'other'},
                        {'group':'other'},{'retry_topic':'%RETRY%other'},{'wire':'private'}):
            value=dict(self.row,**changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):receipt(MARKER+json.dumps(value),self.route)
        raw=MARKER+json.dumps(self.row)
        for value in ('',raw+'\n'+raw,MARKER+'[]'):
            with self.assertRaises(ValueError):receipt(value,self.route)
