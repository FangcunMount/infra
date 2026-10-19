import copy
import json
from pathlib import Path
import unittest

from routes import consumer_group_v2, permissions_v2, physical_topic_v2, validate
from provision_v2 import desired_topics, parse_acl, preflight

ROOT = Path(__file__).resolve().parents[2]


class V2Tests(unittest.TestCase):
    def test_shared_canonical_vectors_and_manifest(self):
        vectors = json.loads((ROOT / 'components/rocketmq/routing-v2-vectors.json').read_text())
        self.assertEqual(len(vectors['vectors']), 6)
        for r in vectors['vectors']:
            self.assertEqual(physical_topic_v2(r['topic'],r['message_type'],r['owner'],r['route_revision']),r['physical_topic'])
            if r['subscription']:
                self.assertEqual(consumer_group_v2(r['topic'],r['subscription']),r['consumer_group'])
        for name in ('test-routes-v2.json','transaction-routes-v2.example.json'):
            validate(json.loads((ROOT / 'components/rocketmq' / name).read_text()))

    def test_owner_grants_and_conflicting_existing_resources_fail_before_mutation(self):
        m=json.loads((ROOT/'components/rocketmq/test-routes-v2.json').read_text())
        bad=copy.deepcopy(m);bad['accounts']['owner-a']['publish'].append('sdk-v2-mongo')
        with self.assertRaises(ValueError):validate(bad)
        metadata={'topicConfigTable':{},'subscriptionGroupTable':{}}
        accounts={role:{'username':role,'password':str(i)*64} for i,role in enumerate(m['accounts'],1)}
        topics,groups,users,acl=preflight(m,accounts,metadata,{}, {})
        self.assertEqual(len(topics),9);self.assertEqual(len(groups),4);self.assertEqual(len(users),3)
        topic,expected=topics[0]
        metadata['topicConfigTable'][topic]={**expected,'attributes':{'message.type':'NORMAL' if expected['message_type']=='TRANSACTION' else 'TRANSACTION'}}
        with self.assertRaises(RuntimeError):preflight(m,accounts,metadata,{}, {})
        metadata['topicConfigTable']={}
        with self.assertRaises(RuntimeError):preflight(m,accounts,metadata,{}, {'owner-a':{'Topic:*':{'Pub','Get'}}})
        with self.assertRaises(RuntimeError):preflight(m,accounts,metadata,{'owner-a':('wrong','Normal','Enable')},{})
        permissions=permissions_v2(m,m['accounts']['owner-a'])
        self.assertTrue(all(actions=={'Pub','Get'} for actions in permissions.values()))
        self.assertFalse(any(r['physical_topic'] in str(permissions) for r in m['routes'] if r['owner']=='qs.mongo'))

    def test_acl_snapshot_does_not_accept_wildcards_denies_or_extra_actions(self):
        row='#Subject #PolicyType #Resource #Actions #SourceIp #Decision\nUser:fixture Custom Topic:rmq2_t_fixture [Pub, Get] [] Allow\n'
        self.assertEqual(parse_acl(row,'User:fixture'),{'Topic:rmq2_t_fixture':{'Pub','Get'}})
        for bad in (row.replace('Allow','Deny'),row.replace('Custom','Default'),row.replace('[] Allow','[10.0.0.1] Allow')):
            with self.assertRaises(RuntimeError):parse_acl(bad,'User:fixture')


if __name__=='__main__':unittest.main()
