import copy
import json
from pathlib import Path
import unittest

from m3_resources import manifest, expected_cases, parse_receipt, bootstrap_manifest
from provision_v2 import desired_topics
from routes import permissions_v2, validate_v2

ROOT = Path(__file__).resolve().parents[2]


class M3ResourceTests(unittest.TestCase):
    def setUp(self):
        self.document = manifest(ROOT)

    def test_final_owners_normal_routes_fanout_and_original_catalog_mapping(self):
        m = self.document
        self.assertEqual(len(m['routes']),12)
        self.assertEqual(len(desired_topics(m)),10)
        self.assertEqual({r['route_revision'] for r in m['routes']},{'m3-1'})
        self.assertEqual({r['owner'] for r in m['routes']},{'iam.mysql','qs.mysql','qs.mongo','ai.mysql'})
        self.assertEqual({r['topic'] for r in m['routes'] if r['message_type']=='NORMAL'},
                         {'iam.notify.sms','qs.survey.lifecycle','qs.plan.task'})
        catalog = next(r for r in m['routes'] if r['id']=='qs-survey-catalog')
        self.assertEqual((catalog['topic'],catalog['message_type']),('qs.survey.lifecycle','NORMAL'))
        evaluations = [r for r in m['routes'] if r['topic']=='qs.evaluation.lifecycle']
        self.assertEqual({r['owner'] for r in evaluations},{'qs.mysql','qs.mongo'})
        self.assertEqual(len({r['consumer_group'] for r in evaluations}),1)
        authz = [r for r in m['routes'] if r['topic']=='iam.authz.version.v2']
        self.assertEqual(len({r['consumer_group'] for r in authz}),2)
        self.assertEqual(len({r['physical_topic'] for r in authz}),1)

    def test_bootstrap_is_a_distinct_development_profile_and_cannot_pass_full_receipt(self):
        doc=bootstrap_manifest(self.document)
        self.assertEqual(len(doc['accounts']),2)
        self.assertEqual(len(doc['routes']),3)
        cases=expected_cases(doc)
        self.assertEqual(len(cases),22)
        self.assertEqual(sum(v==40100 for v in cases.values()),6)
        receipt=dict(client='5.1.2',passed=22,failed=0,skipped=0,cases=cases,
            scope='isolated_transport_acl_and_broker_type_only',denial_path='direct_signed_send_receive_rpc',diagnostic=None)
        raw='M3_RESOURCE_RECEIPT '+json.dumps(receipt)
        self.assertEqual(parse_receipt(raw,doc),receipt)
        with self.assertRaises(RuntimeError):parse_receipt(raw,self.document)

    def test_minimum_effective_permissions_do_not_publish_cross_owner_or_use_wildcards(self):
        m = self.document
        routes = {r['id']:r for r in m['routes']}
        for role, grants in m['accounts'].items():
            with self.subTest(role=role):
                if grants['publish']:
                    self.assertEqual({routes[r]['owner'] for r in grants['publish']},{grants['owner']})
                permissions = permissions_v2(m,grants)
                self.assertTrue(all('*' not in key and actions <= {'Pub','Sub','Get'} for key,actions in permissions.items()))
                for route in routes.values():
                    if route['owner'] != grants.get('owner'):
                        self.assertNotIn('Pub',permissions.get('Topic:'+route['physical_topic'],()))
        bad = copy.deepcopy(m)
        bad['accounts']['m3-qs-apiserver']['publish'].append('qs-evaluation-mongo')
        with self.assertRaises(ValueError):validate_v2(bad)
        self.assertFalse(m['accounts']['m3-qs-mongo']['subscriptions'])
        self.assertEqual(m['accounts']['m3-qs-worker']['publish'],[])
        self.assertNotIn('owner',m['accounts']['m3-qs-worker'])

    def test_required_real_matrix_cannot_accept_missing_negative_positive_or_tls_proof(self):
        expected = expected_cases(self.document)
        self.assertEqual(len(expected),130)
        self.assertEqual(sum(value==40100 for value in expected.values()),84)
        self.assertEqual(sum(value==40014 for value in expected.values()),10)
        receipt = dict(client='5.1.2',passed=130,failed=0,skipped=0,cases=expected,
            scope='isolated_transport_acl_and_broker_type_only',denial_path='direct_signed_send_receive_rpc',diagnostic=None)
        output = lambda v:'M3_RESOURCE_RECEIPT '+json.dumps(v)
        self.assertEqual(parse_receipt(output(receipt),self.document),receipt)
        for field,value in [('skipped',1),('failed',1),('client','5.1.1'),('passed',True),('wire','private'),('denial_path','query_route_only')]:
            bad=copy.deepcopy(receipt);bad[field]=value
            with self.subTest(field=field),self.assertRaises(RuntimeError):parse_receipt(output(bad),self.document)
        for key in ('tls/wrong_ca',next(k for k,v in expected.items() if v==40100)):
            bad=copy.deepcopy(receipt);del bad['cases'][key];bad['passed']-=1
            with self.assertRaises(RuntimeError):parse_receipt(output(bad),self.document)
            self.assertEqual(parse_receipt(output(bad),self.document,partial=True)['passed'],129)
        # A generic 403 or an absent positive credential control is not the
        # pinned 5.5.1 authorization result and cannot stand in for this proof.
        for key in ('m3-iam/authentication/before','m3-iam/authentication/after'):
            bad=copy.deepcopy(receipt);del bad['cases'][key];bad['passed']-=1
            with self.assertRaises(RuntimeError):parse_receipt(output(bad),self.document)
        bad=copy.deepcopy(receipt)
        bad['cases'][next(k for k,v in expected.items() if v==40100)]=40300
        with self.assertRaises(RuntimeError):parse_receipt(output(bad),self.document)
        with self.assertRaises(RuntimeError):parse_receipt(output(receipt)+'\n'+output(receipt),self.document)
        partial=copy.deepcopy(receipt);partial.update(passed=0,failed=1,cases={},diagnostic=dict(
            phase='producer_bootstrap:m3-iam/settings',kind='RuntimeError',status=None))
        self.assertEqual(parse_receipt(output(partial),self.document,partial=True),partial)
        for diagnostic in ({'wire':'private'},dict(phase='private-token',kind='RuntimeError',status=None),
                           dict(phase='native_started',kind='raw private exception',status=None)):
            partial['diagnostic']=diagnostic
            with self.assertRaises(RuntimeError):parse_receipt(output(partial),self.document,partial=True)


if __name__ == '__main__':
    unittest.main()
