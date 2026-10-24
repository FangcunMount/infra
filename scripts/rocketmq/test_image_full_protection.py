import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from image_full_protection import FullImageProtection, ai_expression_companion, validate_databases


class FullScopeProtectionAdmissionTest(unittest.TestCase):
    def test_original_unicode_dump_is_restored_in_one_explicit_utf8mb4_session(self):
        f = FullImageProtection.__new__(FullImageProtection)
        f.f = SimpleNamespace(compose=['docker','compose','-p','owned'],report={},
            run=Mock(return_value=SimpleNamespace(returncode=0,stdout='utf8mb4\tutf8mb4\tutf8mb4',stderr='')))
        f.databases = {'iam':'iam_m3_image_owned'}
        f.definitions = {'iam':'CREATE DATABASE `iam_m3_image_owned` CHARACTER SET utf8mb4'}
        original = "INSERT INTO retained VALUES ('受控事实🚀',0x00ff03);"
        f.sql = {'iam':original}
        f.companions = {}
        f.restore_mysql('iam')
        statement = f.f.run.call_args.kwargs['stdin']
        self.assertEqual(f.f.run.call_count,1)
        self.assertTrue(statement.startswith('SET NAMES utf8mb4; SELECT '))
        self.assertIn(original,statement)
        self.assertLess(statement.index('SET NAMES'),statement.index('DROP DATABASE'))
        self.assertEqual(f.sql['iam'],original)
        f.f.run.return_value.stdout='latin1\tlatin1\tlatin1'
        with self.assertRaisesRegex(RuntimeError,'exact_restore_session_charset'):f.restore_mysql('iam')
        f.f.run.return_value=SimpleNamespace(returncode=1,stdout='',stderr='ERROR 1832 (HY000): private SQL withheld')
        with self.assertRaisesRegex(RuntimeError,'full_scope_mysql_restore_failed_iam'):f.restore_mysql('iam')
        self.assertEqual(f.f.report['mysql_restore_error']['code'],1832)
        self.assertNotIn('private SQL',str(f.f.report))

    def test_original_expression_sidecar_requires_the_exact_source_metadata(self):
        rows=[]
        for kind,pos,collation in [('prompt','6','utf8mb4_0900_ai_ci'),('semantic','7','utf8mb4_bin')]:
            expression="(case when (`draft_kind` = _utf8mb4" + chr(92)*2 + "'" + kind + chr(92)*2 + "') then `draft_id` else NULL end)"
            rows.append('\t'.join(['governance_draft_heads',pos,kind+'_draft_id_key','char(36)','YES','NULL',
                'STORED GENERATED','utf8mb4',collation,'',expression]))
        original='\n'.join(rows)
        statement=ai_expression_companion('ai_m3_image_owned',original)
        self.assertEqual(statement.count('MODIFY COLUMN'),2)
        self.assertIn("draft_kind=_utf8mb4'prompt'",statement)
        self.assertIn("draft_kind=_utf8mb4'semantic'",statement)
        for invalid in (original.replace('char(36)','char(35)'),rows[0],original.replace('_utf8mb4','_ascii')):
            with self.assertRaisesRegex(RuntimeError,'exact_original_ai_expression_metadata'):ai_expression_companion('ai_m3_image_owned',invalid)

    def test_exact_owned_selected_set_is_required_before_any_database_mutation(self):
        selected={'iam':'iam_m3_image_owned','qs':'qs_m3_image_owned','ai':'ai_m3_image_owned'}
        self.assertEqual(validate_databases(selected),selected)
        for value in ({'iam':'iam','qs':selected['qs'],'ai':selected['ai']},
                      dict(selected,qs='qs_m3_image_owned`; DROP DATABASE mysql;'),
                      {'iam':selected['iam'],'qs':selected['qs']},dict(selected,other='production')):
            with self.subTest(value=value),self.assertRaises(RuntimeError):validate_databases(value)
