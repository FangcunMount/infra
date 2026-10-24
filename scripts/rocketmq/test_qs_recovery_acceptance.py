import copy
from pathlib import Path
import unittest
from qs_recovery_acceptance import metadata
from qs_runtime_acceptance import runtime_manifest
from routes import validate_v2


class QSRecoveryMetadata(unittest.TestCase):
    def good(self):
        return dict(database='qs_m3_host_1792800000000000000',original_root_calls=2,original_owners_stopped=True,broker_sigkill_after_commit=True,
            branches=[dict(owner=owner,store_id=owner+'-original-runtime',writer_epoch='m3-1',operation_id='original-'+owner,branch_id='event',fence=1,message_id='original-'+owner,wire_hash='1'*64) for owner in ('qs.mysql','qs.mongo')])
    def test_original_dual_inventory_and_binding_required(self):
        value=self.good();self.assertEqual(metadata(value),value)
        for change in ('duplicate','extra','wrong_database','wrong_fence','wrong_owner'):
            value=copy.deepcopy(self.good())
            if change=='duplicate':value['branches'][1]=value['branches'][0]
            elif change=='extra':value['uri']='external'
            elif change=='wrong_database':value['database']='production'
            elif change=='wrong_fence':value['branches'][0]['fence']=True
            else:value['branches'][0]['owner']='iam.mysql'
            with self.subTest(change=change),self.assertRaises(RuntimeError):metadata(value)
    def test_full_runtime_routes_keep_both_inputs_in_one_logical_subscription(self):
        value=runtime_manifest(Path(__file__).resolve().parents[2]);validate_v2(value)
        inputs=[r for r in value['routes'] if r['id'] in ('qs-evaluation-mysql','qs-evaluation-mongo')]
        self.assertEqual({r['owner'] for r in inputs},{'qs.mysql','qs.mongo'})
        self.assertEqual(len({r['consumer_group'] for r in inputs}),1)
