import unittest

from image_full_protection import validate_databases


class FullScopeProtectionAdmissionTest(unittest.TestCase):
    def test_exact_owned_selected_set_is_required_before_any_database_mutation(self):
        selected={'iam':'iam_m3_image_owned','qs':'qs_m3_image_owned','ai':'ai_m3_image_owned'}
        self.assertEqual(validate_databases(selected),selected)
        for value in ({'iam':'iam','qs':selected['qs'],'ai':selected['ai']},
                      dict(selected,qs='qs_m3_image_owned`; DROP DATABASE mysql;'),
                      {'iam':selected['iam'],'qs':selected['qs']},dict(selected,other='production')):
            with self.subTest(value=value),self.assertRaises(RuntimeError):validate_databases(value)
