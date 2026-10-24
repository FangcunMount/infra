"""Synthetic approval serialization tests only; never real restore evidence."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from image_cutover_offline import offline_approval


class OfflineEvidenceBindingTest(unittest.TestCase):
    def build(self, **updates):
        inputs = dict(snapshot=dict(source_sha='a'*40,migration_resources_sha256='b'*64,
            mysql_database='qs_m3_image_unit',mongo_database='qs_m3_image_unit',
            mysql_identity_sha256='c'*64,mongo_cluster_sha256='d'*64),
            operation_id='owned-unit',started=datetime.now(timezone.utc)-timedelta(seconds=2),
            protection=SimpleNamespace(manifest_sha='1'*64,receipt_sha='2'*64,restore_seconds=7,
                f=SimpleNamespace(directory=Path('/tmp/owned-unit'))),
            startup_sha='3'*64,scope_sha='4'*64,responsibility_sha='5'*64)
        inputs.update(updates)
        return offline_approval(**inputs)

    def test_original_cli_approval_uses_actual_references_and_old_pair(self):
        value = self.build()
        self.assertEqual(value['protection_manifest_sha256'],'1'*64)
        self.assertEqual(value['restore_receipt_sha256'],'2'*64)
        self.assertEqual(value['startup_receipt_sha256'],'3'*64)
        self.assertEqual(value['responsibility_sha256'],'5'*64)
        self.assertEqual((value['initial_mysql_version'],value['initial_mongo_version']),(105,40))
        self.assertEqual((value['target_mysql_version'],value['target_mongo_version']),(110,43))
        self.assertEqual(value['protection_scope'],'full_database_pair')
        self.assertTrue(value['runtime_frozen'] and value['runtime_not_started'])
        self.assertEqual(json.loads(json.dumps(value)),value)

    def test_missing_evidence_or_elapsed_window_is_refused(self):
        for update in (dict(startup_sha='unknown'),dict(scope_sha=''),dict(responsibility_sha='missing'),
            dict(started=datetime.now(timezone.utc)-timedelta(minutes=26)),
            dict(started=datetime.now(timezone.utc)+timedelta(minutes=1))):
            with self.subTest(update=update),self.assertRaises(RuntimeError):self.build(**update)


if __name__ == '__main__':unittest.main()
