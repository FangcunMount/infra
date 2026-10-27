import copy
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
import m4_legacy_disposition as d

class Guards(unittest.TestCase):
    def plan(self):
        return dict(operation=d.OP, authorization='user-20261027-dispose-now', kind='archives', host='serverA', files=[dict(path=d.OLD_ROOT+'three-full-databases.sql',bytes=1,sha256='0'*64)])
    def test_exact_old_backup_accepted(self):self.assertEqual(d.validate_plan(self.plan())['host'],'serverA')
    def test_active_material_refused(self):
        p=self.plan();p['files'][0]['path']='/var/lib/fangcun-m4-materials/qs-ai-messaging/current.json'
        with self.assertRaises(ValueError):d.validate_plan(p)
    def test_arbitrary_backup_refused(self):
        p=self.plan();p['files'][0]['path']=d.OLD_ROOT+'anything.sql'
        with self.assertRaises(ValueError):d.validate_plan(p)
    def test_cross_host_refused(self):
        p=self.plan();p['host']='serverC'
        with self.assertRaises(ValueError):d.validate_plan(p)
    def test_prior_policy_does_not_authorize_delete(self):
        p=self.plan();p['authorization']='retain_under_policy'
        with self.assertRaises(ValueError):d.validate_plan(p)
    def test_unsupported_kind(self):
        p=self.plan();p['kind']='drop_database'
        with self.assertRaises(ValueError):d.validate_plan(p)
    def test_duplicate_refused(self):
        p=self.plan();p['files']*=2
        with self.assertRaises(ValueError):d.validate_plan(p)
    def test_content_change_refused(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td).resolve()/'old';p.write_bytes(b'old');r=dict(path=str(p),bytes=3,sha256=hashlib.sha256(b'old').hexdigest(),inode=p.stat().st_ino);d.check_files([r]);p.write_bytes(b'new')
            with self.assertRaises(ValueError):d.check_files([r])
    def test_symlink_refused(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td).resolve()/'old';p.write_text('x');q=Path(td).resolve()/'link';q.symlink_to(p)
            with self.assertRaises(ValueError):d.regular(str(q))
    def test_inode_change_refused(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td).resolve()/'old';p.write_bytes(b'old');r=dict(path=str(p),bytes=3,sha256=hashlib.sha256(b'old').hexdigest(),inode=p.stat().st_ino+1)
            with self.assertRaises(ValueError):d.check_files([r])
    def test_current_sql_stores_excluded(self):
        for owner,table in [('ai','interpretation_result_outbox'),('iam','identity_session_revocation_outbox'),('qs','ai_messaging_inbox'),('qs','rm_tx_witness')]:self.assertNotIn((owner,table),d.SQL_QUEUES)
    def test_queue_state_allowlist(self):self.assertEqual(set(d.SQL_QUEUES.values()),{('status','published'),('state','published'),('stage','confirmed')})
if __name__=='__main__':unittest.main()
