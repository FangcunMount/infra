import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from image_full_protection import FullImageProtection, validate_databases


class FullScopeProtectionAdmissionTest(unittest.TestCase):
    def test_original_unicode_dump_is_restored_in_one_explicit_utf8mb4_session(self):
        f = FullImageProtection.__new__(FullImageProtection)
        f.f = SimpleNamespace(sql=Mock(return_value='utf8mb4\tutf8mb4\tutf8mb4'))
        f.databases = {'iam':'iam_m3_image_owned'}
        f.definitions = {'iam':'CREATE DATABASE `iam_m3_image_owned` CHARACTER SET utf8mb4'}
        original = "INSERT INTO retained VALUES ('受控事实🚀',0x00ff03);"
        f.sql = {'iam':original}
        f.restore_mysql('iam')
        statement = f.f.sql.call_args.args[0]
        self.assertEqual(f.f.sql.call_count,1)
        self.assertTrue(statement.startswith('SET NAMES utf8mb4; SELECT '))
        self.assertIn(original,statement)
        self.assertLess(statement.index('SET NAMES'),statement.index('DROP DATABASE'))
        self.assertEqual(f.sql['iam'],original)
        f.f.sql.return_value='latin1\tlatin1\tlatin1'
        with self.assertRaisesRegex(RuntimeError,'exact_restore_session_charset'):f.restore_mysql('iam')

    def test_exact_owned_selected_set_is_required_before_any_database_mutation(self):
        selected={'iam':'iam_m3_image_owned','qs':'qs_m3_image_owned','ai':'ai_m3_image_owned'}
        self.assertEqual(validate_databases(selected),selected)
        for value in ({'iam':'iam','qs':selected['qs'],'ai':selected['ai']},
                      dict(selected,qs='qs_m3_image_owned`; DROP DATABASE mysql;'),
                      {'iam':selected['iam'],'qs':selected['qs']},dict(selected,other='production')):
            with self.subTest(value=value),self.assertRaises(RuntimeError):validate_databases(value)
