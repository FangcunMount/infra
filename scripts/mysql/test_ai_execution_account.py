import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('account',Path(__file__).with_name('ai_execution_account.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class AccountReview(unittest.TestCase):
 def test_existing_wide_account_is_reported_not_disguised_as_minimum(self):
  r=m.review(['GRANT ALL PRIVILEGES ON `ai`.* TO `u`@`%`','GRANT ALL PRIVILEGES ON `qs`.* TO `u`@`%`'],'NONE',0)
  self.assertTrue(r['required_capabilities_present']);self.assertFalse(r['least_privilege_account']);self.assertEqual(r['other_scope_count'],1)
 def test_similar_database_name_does_not_grant_ai_drop(self):
  r=m.review(['GRANT SELECT ON `ai`.* TO `u`@`%`','GRANT ALL PRIVILEGES ON `aix`.* TO `u`@`%`'],'NONE',0)
  self.assertFalse(r['required_capabilities_present'])
 def test_table_only_select_is_not_full_schema_read(self):
  r=m.review(['GRANT SELECT, DROP ON `ai`.`messaging_outbox` TO `u`@`%`','GRANT UPDATE ON `ai`.`alembic_version` TO `u`@`%`'],'NONE',0)
  self.assertFalse(r['capabilities']['read_all_ai'])
 def test_roles_partial_revokes_and_unknown_shapes_refused(self):
  for roles,revokes,grants in [('r',0,['GRANT ALL PRIVILEGES ON `ai`.* TO `u`@`%`']),('NONE',1,['GRANT ALL PRIVILEGES ON `ai`.* TO `u`@`%`']),('NONE',0,['REVOKE DROP ON `ai`.* FROM `u`@`%`'])]:
   with self.assertRaises(ValueError):m.review(grants,roles,revokes)
if __name__=='__main__':unittest.main()
