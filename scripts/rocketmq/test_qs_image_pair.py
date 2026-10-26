import copy
import json
import unittest

from qs_image_pair import QS_SHA, canonical_dump, initializer_receipt, mongo_snapshot_program, verify_current_pair


class QSPairImageContractTest(unittest.TestCase):
    def test_actual_offline_readback_requires_current_pair_and_exact_resources(self):
        receipt={'resources_sha256':'a'*64}
        snapshot=dict(read_only=True,snapshot=dict(source_sha=QS_SHA,migration_resources_sha256='a'*64,mysql_version=110,mongo_version=44))
        verify_current_pair(snapshot,receipt)
        for key,value in (('source_sha','b'*40),('migration_resources_sha256','c'*64),('mysql_version',109),('mongo_version',43)):
            bad=copy.deepcopy(snapshot);bad['snapshot'][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):verify_current_pair(bad,receipt)
        with self.assertRaises(RuntimeError):verify_current_pair(dict(snapshot,read_only=False),receipt)

    def test_only_redundant_column_charset_rendering_is_canonicalized(self):
        before="  `value` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'retained'\n"
        after=before.replace('COLLATE','CHARACTER SET utf8mb4 COLLATE')
        self.assertEqual(canonical_dump(before),canonical_dump(after))
        for changed in (after.replace('unicode_ci','bin'),after.replace('NOT NULL','NULL'),after.replace('retained','changed')):
            self.assertNotEqual(canonical_dump(before),canonical_dump(changed))
        body="INSERT INTO `archive` VALUES (' CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci');\n"
        self.assertEqual(canonical_dump(body),body)
        mismatched=after.replace('SET utf8mb4','SET utf8mb3')
        self.assertEqual(canonical_dump(mismatched),mismatched)

    def test_original_initializer_receipt_requires_full_source_and_both_heads(self):
        value = dict(source_sha=QS_SHA, profile='current', mysql=110, mongo=44,
                     resources_sha256='a' * 64, original_templates_applied=True,
                     journal_force_used=False, production=False)
        def check(v): return initializer_receipt('QS_IMAGE_INIT ' + json.dumps(v), 'current')
        self.assertEqual(check(value), value)
        for field, bad in (('source_sha', 'b' * 40), ('mysql', 105), ('mongo', 40),
                           ('profile', 'pre_m3'), ('resources_sha256', ''),
                           ('journal_force_used', True), ('production', True)):
            altered = copy.deepcopy(value); altered[field] = bad
            with self.subTest(field=field), self.assertRaises(RuntimeError): check(altered)
        with self.assertRaises(RuntimeError): initializer_receipt('', 'current')
        with self.assertRaises(RuntimeError): initializer_receipt(('QS_IMAGE_INIT ' + json.dumps(value) + '\n') * 2, 'current')

    def test_pre_m3_is_explicit_and_not_current_head_evidence(self):
        value = dict(source_sha=QS_SHA, profile='pre_m3', mysql=105, mongo=40,
                     resources_sha256='c' * 64, original_templates_applied=True,
                     journal_force_used=False, production=False)
        self.assertEqual(initializer_receipt('QS_IMAGE_INIT ' + json.dumps(value), 'pre_m3'), value)
        with self.assertRaises(RuntimeError): initializer_receipt('QS_IMAGE_INIT ' + json.dumps(value), 'current')

    def test_new_current_source_requires_explicit_identity_without_changing_old_default(self):
        value = dict(source_sha='a'*40, profile='current', mysql=110, mongo=44,
                     resources_sha256='c'*64, original_templates_applied=True,
                     journal_force_used=False, production=False)
        raw = 'QS_IMAGE_INIT ' + json.dumps(value)
        self.assertEqual(initializer_receipt(raw, 'current', source_sha='a'*40), value)
        with self.assertRaises(RuntimeError): initializer_receipt(raw, 'current')
        with self.assertRaises(RuntimeError): initializer_receipt(raw, 'current', source_sha='b'*40)

    def test_mongo_snapshot_retains_uuid_indexes_and_canonical_binary_documents(self):
        program = mongo_snapshot_program('qs_m3_image_owned_1')
        for required in ('c.info.uuid', 'getIndexes()', 'EJSON.stringify', 'relaxed:false', 'Object.keys(v).sort()', 'sort({_id:1})'):
            self.assertIn(required, program)
        for wrong in ('qs', 'production', 'qs_m3_image_a\";dropDatabase();'):
            with self.assertRaises(RuntimeError): mongo_snapshot_program(wrong)
