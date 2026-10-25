import unittest

from m3_mongo_protection import drop_program, profile_identity_program, restore_selection, snapshot_program


class MongoProtectionTest(unittest.TestCase):
    def test_exact_profile_exception_keeps_all_business_collections(self):
        before = ['answersheets', 'profile_records', 'schema_migrations', 'system.profile']
        self.assertEqual(restore_selection(before, before + ['rm_tx_binding'], ['rm_tx_binding']),
                         ['answersheets', 'profile_records', 'rm_tx_binding', 'schema_migrations'])

    def test_missing_original_business_collection_can_be_restored_from_archive(self):
        self.assertEqual(restore_selection(['facts', 'system.profile'], ['system.profile'], []), [])

    def test_unknown_postfreeze_objects_reject_before_any_drop_plan(self):
        with self.assertRaises(ValueError):
            restore_selection(['facts', 'system.profile'], ['facts', 'system.profile', 'unreviewed'], [])

    def test_profile_loss_addition_or_declaration_rejects(self):
        for before, current, new in [(['facts', 'system.profile'], ['facts'], []),
                                     (['facts'], ['facts', 'system.profile'], []),
                                     (['facts', 'system.profile'], ['facts', 'system.profile'], ['system.profile'])]:
            with self.subTest(before=before, current=current, new=new), self.assertRaises(ValueError):
                restore_selection(before, current, new)

    def test_other_reserved_names_and_ambiguous_inventory_reject(self):
        for names in [['facts', 'system.views'], ['facts', 'facts'], ['facts', 'bad;drop'], ['facts', None]]:
            with self.subTest(names=names), self.assertRaises(ValueError):
                restore_selection(names, names, [])

    def test_profile_cannot_be_an_explicit_drop_target(self):
        with self.assertRaises(ValueError):
            drop_program('qs', ['system.profile'])
        value = drop_program('qs', ['facts'])
        self.assertNotIn('dropDatabase', value)
        self.assertIn('["facts"]', value)

    def test_only_fixed_production_or_owned_test_database_is_encoded(self):
        for name in ['admin', 'local', 'qs;db.dropDatabase()', 'other', None]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                snapshot_program(name)
        self.assertIn('system.profile', snapshot_program('qs'))
        self.assertNotIn('documents:', profile_identity_program('qs'))


if __name__ == '__main__':
    unittest.main()
