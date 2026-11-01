import importlib.util
from pathlib import Path
import gzip
import json
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('ai_backup_material',Path(__file__).with_name('ai_backup_material.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class BackupContracts(unittest.TestCase):
    def col(self,name='n',typ='bigint',charset=None,expression=''):
        return dict(name=name,data_type=typ,charset=charset,expression=expression,extra='STORED GENERATED' if expression else '')
    def test_numeric_hex_is_text_not_wrong_numeric_hex_context(self):
        self.assertEqual(m.value_sql('313233',self.col()),"CONVERT(X'313233' USING utf8mb4)")
    def test_binary_zero_and_ff_are_never_reinterpreted_as_unicode(self):
        self.assertEqual(m.value_sql('00FF',self.col(typ='longblob')),"X'00FF'")
    def test_json_and_unicode_use_declared_character_set(self):
        self.assertEqual(m.value_sql('7B7D',self.col(typ='json')),"CONVERT(X'7B7D' USING utf8mb4)")
        self.assertIn('USING ascii',m.value_sql('61',self.col(typ='char',charset='ascii')))
    def test_null_empty_and_field_boundaries_remain_distinct(self):
        self.assertNotEqual(m.row_hash([None]),m.row_hash(['']))
        self.assertNotEqual(m.row_hash(['00','FF']),m.row_hash(['00FF','']))
        self.assertEqual(m.value_sql(None,self.col()),'NULL')
    def test_invalid_identifiers_hex_charset_or_type_refused(self):
        for name in ['ai.x','a`;DROP','x-y']:
            with self.assertRaises(m.Refused):m.identifier(name)
        for value,col in [('0',self.col()),('GG',self.col()),('00',self.col(charset='utf8;bad')),('00',self.col(typ='unknown'))]:
            with self.assertRaises(m.Refused):m.value_sql(value,col)
    def test_generated_values_not_reinserted_but_default_generated_still_written(self):
        a=self.col();a['extra']='DEFAULT_GENERATED'
        statement=m.insert_sql('t',[a,self.col('derived',expression='1')],['31','31'])
        self.assertIn('`n`',statement);self.assertNotIn('derived',statement)
    def test_restore_original_expression_metadata_without_relaxing_other_definition(self):
        original="CREATE TABLE `t` (\n  `n` int,\n  `g` varchar(8) GENERATED ALWAYS AS ((case when (`n` = 1) then _ascii'prompt' else NULL end)) STORED,\n  PRIMARY KEY (`n`)\n) ENGINE=InnoDB"
        col=self.col('g',expression="(case when (`n` = 1) then _utf8mb4'prompt' else NULL end)")
        restored=m.restore_definition(original,[col])
        self.assertEqual(restored.replace("_utf8mb4'prompt'","_ascii'prompt'"),original)
        with self.assertRaises(m.Refused):m.restore_definition(original,[self.col('missing',expression='1')])
    def test_information_schema_quote_encoding_is_decoded_before_execution(self):
        original="CREATE TABLE `t` (\n  `g` varchar(8) GENERATED ALWAYS AS ((_ascii'prompt')) STORED\n) ENGINE=InnoDB"
        column=self.col('g',expression="(_utf8mb4"+chr(92)+"'prompt"+chr(92)+"')")
        self.assertEqual(m.restore_definition(original,[column]),original.replace("_ascii'prompt'","_utf8mb4'prompt'"))
    def test_expression_changes_or_unknown_escapes_remain_refused(self):
        original="CREATE TABLE `t` (\n  `g` int GENERATED ALWAYS AS ((1)) STORED\n) ENGINE=InnoDB"
        for expr in ['(2)','('+chr(92)+'x)']:
            with self.assertRaises(m.Refused):m.restore_definition(original,[self.col('g',expression=expr)])
    def test_restore_guard_rejects_public_target_and_network_interfaces(self):
        with self.assertRaises(m.Refused):m.require_isolated('mysql+asyncmy://x:y@source:3306/ai')
        with patch.object(m.socket,'gethostname',return_value='m5-ai-restore-test'),patch.object(m.Path,'read_text',return_value='header\nheader\n lo: 0\n eth0: 0\n'):
            with self.assertRaises(m.Refused):m.require_isolated('mysql+asyncmy://x:y@127.0.0.1:3306/ai')
    def test_archive_is_pinned_before_and_after_restoration(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'b';p.write_bytes(b'original');p.chmod(0o600);sha=m.digest(b'original');m.verify_archive(p,sha)
            p.write_bytes(b'changed')
            with self.assertRaises(m.Refused):m.verify_archive(p,sha)
    def test_archive_symlinks_and_unprivate_permissions_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'b';p.write_bytes(b'original');p.chmod(0o644)
            with self.assertRaises(m.Refused):m.verify_archive(p,m.digest(b'original'))
            q=Path(d)/'link';q.symlink_to(p)
            with self.assertRaises(OSError):m.verify_archive(q,m.digest(b'original'))
    def test_read_gzip_frames_and_refuse_oversize_frame(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'b.gz'
            with gzip.open(p,'wb') as f:f.write(json.dumps({'kind':'header'}).encode()+b'\n')
            self.assertEqual(list(m.frames(p)),[{'kind':'header'}])
            with patch.object(m,'MAX_FRAME',5):
                with self.assertRaises(m.Refused):list(m.frames(p))

if __name__=='__main__':unittest.main()
