import json
import unittest
from recovery_fixture_store import MongoFixtureStore,SQLFixtureStore


class FixtureStores(unittest.TestCase):
    def test_original_database_name_cannot_inject_script_or_choose_external_database(self):
        for name in ('mysql','qs_m3_host_1','x);db.dropDatabase()','qs_m3_host_1234567890/other'):
            with self.assertRaises(RuntimeError):MongoFixtureStore(lambda q:'',name)
    def test_counts_are_exact_nonnegative_integers_not_boolean_or_missing(self):
        for value in ([1,1,1,1],[True,1,1,1],[-1,1,1,1],[1,1,1]):
            db=MongoFixtureStore(lambda query:json.dumps(value),'qs_m3_host_1792800000000000000')
            if value==[1,1,1,1] and type(value[0]) is int:self.assertEqual(db.counts(),'1\t1\t1\t1')
            else:
                with self.assertRaises(RuntimeError):db.counts()
    def test_read_projections_never_request_plan_token_or_wire(self):
        seen=[]
        def query(value):seen.append(value);return json.dumps('commit_confirmed\t2026-10-24T00:00:00.000Z')
        db=MongoFixtureStore(query,'qs_m3_host_1792800000000000000');self.assertIn('commit_confirmed',db.audit())
        self.assertNotIn('"plan"',seen[0]);self.assertNotIn('"token"',seen[0]);self.assertNotIn('"wire"',seen[0])
    def test_sql_fixture_queries_remain_read_only(self):
        seen=[]
        db=SQLFixtureStore(lambda query:seen.append(query) or '1','SELECT COUNT(*) FROM m3_owner_runtime_facts')
        db.governance();db.counts();db.audit()
        self.assertEqual(len(seen),3);self.assertTrue(all(s.startswith('SELECT ') for s in seen))
