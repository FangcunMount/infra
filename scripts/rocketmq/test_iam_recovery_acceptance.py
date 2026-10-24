import unittest
from pathlib import Path
from managed_recovery_acceptance import fixture_manifest
from routes import validate_v2,consumer_group_v2
from iam_recovery_acceptance import metadata


class IAMRecoveryMetadata(unittest.TestCase):
    def good(self):
        return dict(database='iam_m3_broker_test_1792800000000000000',owner='iam.mysql',store_id='iam-native-primary',writer_epoch='m3-1',operation_id='original-op',branch_id='policy-version',fence=1,message_id='original-message')

    def test_original_metadata_is_private_host_locator_not_connection_authority(self):
        value=metadata(self.good())
        self.assertEqual(value['user'],'root')
        self.assertIn('actual IAM',value['writer'])
        self.assertNotIn('database_uri',value)

    def test_wrong_or_unbounded_identities_refused(self):
        for field,value in [('owner','ai.mysql'),('store_id','other'),('writer_epoch','other'),('database','mysql'),('operation_id',"x';DROP DATABASE mysql"),('branch_id',''),('message_id','x'*129),('fence',0),('fence',True),('fence',2**63)]:
            with self.subTest(field=field,value=value):
                candidate=self.good();candidate[field]=value
                with self.assertRaises(RuntimeError):metadata(candidate)

    def test_extra_fields_cannot_select_an_endpoint(self):
        value=self.good();value['database_uri']='external'
        with self.assertRaises(RuntimeError):metadata(value)


class IAMRecoveryRoutes(unittest.TestCase):
    def test_actual_host_logical_route_recomputes_both_physical_names(self):
        value=fixture_manifest(Path(__file__).resolve().parents[2],iam=True)
        validate_v2(value)
        route=next(r for r in value['routes'] if r['owner']=='iam.mysql' and r['message_type']=='TRANSACTION')
        self.assertEqual(route['topic'],'iam.authz.version.v2')
        self.assertEqual(route['consumer_group'],consumer_group_v2(route['topic'],route['subscription']))
