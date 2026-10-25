import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import m3_mysql_restore_sql as tool

SQL = b"""USE `iam`;
CREATE TABLE `untouched` (id INT);
USE `ai`;
CREATE TABLE `governance_draft_heads` (
  `prompt_draft_id_key` varchar(36) GENERATED ALWAYS AS ((case when kind = _ascii'prompt' then id end)) STORED,
  `semantic_draft_id_key` varchar(36) GENERATED ALWAYS AS ((case when kind = _ascii'semantic' then id end)) STORED
) ENGINE=InnoDB;
INSERT INTO `untouched` VALUES('_ascii''prompt''');
USE `qs`;
CREATE TABLE `still_untouched` (id INT);
"""
METADATA=b'owned-test-column-a\nowned-test-column-b\n'


def private(path, value):
    path.write_bytes(value);path.chmod(0o600)
    return hashlib.sha256(value).hexdigest()


class RestoreByteDerivationTest(unittest.TestCase):
    def run_fixture(self, root, sql=SQL):
        root=Path(root);source=root/'source';columns=root/'columns';target=root/'derived'
        a=private(source,sql);private(columns,METADATA)
        b=hashlib.sha256(METADATA.strip()).hexdigest()
        return source,columns,target,a,b

    def test_only_two_ddl_literals_change_data_and_other_databases_exact(self):
        with tempfile.TemporaryDirectory() as root:
            source,columns,target,a,b=self.run_fixture(root)
            expected={hashlib.sha256(row).hexdigest() for row in METADATA.strip().splitlines()}
            with patch.object(tool,'EXPECTED',expected):report=tool.derive(source,columns,target,a,b)
            output=target.read_bytes();wanted=SQL.replace(b"_ascii'prompt'",b"_utf8mb4'prompt'").replace(b"_ascii'semantic'",b"_utf8mb4'semantic'")
            self.assertEqual(output,wanted);self.assertEqual(source.read_bytes(),SQL)
            self.assertFalse(report['database_connected']);self.assertFalse(report['restoration_authorized'])
            self.assertEqual(target.stat().st_mode & 0o777,0o600)

    def test_unrecognized_original_metadata_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as root:
            source,columns,target,a,b=self.run_fixture(root)
            with self.assertRaises(ValueError):tool.derive(source,columns,target,a,b)
            self.assertFalse(target.exists())

    def test_wrong_source_missing_expression_and_wrong_database_refused(self):
        for sql,sha in ((SQL,'0'*64),(SQL.replace(b"_ascii'semantic'",b"_latin1'semantic'"),None),
                        (SQL.replace(b'USE `ai`;',b'USE `other`;'),None)):
            with tempfile.TemporaryDirectory() as root:
                source,columns,target,a,b=self.run_fixture(root,sql)
                expected={hashlib.sha256(row).hexdigest() for row in METADATA.strip().splitlines()}
                with patch.object(tool,'EXPECTED',expected):
                    with self.assertRaises(ValueError):tool.derive(source,columns,target,sha or a,b)

    def test_existing_target_and_non_private_original_refused(self):
        with tempfile.TemporaryDirectory() as root:
            source,columns,target,a,b=self.run_fixture(root);private(target,b'protected')
            expected={hashlib.sha256(row).hexdigest() for row in METADATA.strip().splitlines()}
            with patch.object(tool,'EXPECTED',expected):
                with self.assertRaises(FileExistsError):tool.derive(source,columns,target,a,b)
                source.chmod(0o644)
                with self.assertRaises(ValueError):tool.derive(source,columns,target,a,b)
            self.assertEqual(target.read_bytes(),b'protected')


if __name__=='__main__':unittest.main()
