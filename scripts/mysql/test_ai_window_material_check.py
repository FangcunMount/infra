import gzip
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from ai_backup_material import HEAD, SOURCE_ID, digest, encoded, row_hash
from ai_window_material_check import check


class WindowMaterialTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        source = dict(mysql_identity_sha256=SOURCE_ID, version='8.0.36', database='ai',
                      principal_sha256='a' * 64)
        self.header = dict(kind='header', schema='ai-full-logical-backup/v1', head=HEAD,
                           tables=51, frozen=False, source=source,
                           snapshot_started_at='2026-01-01T00:01:00+00:00')
        self.writer = dict(schema='ai-publisher-writer-exclusion/v1', source_sha='a' * 40,
                           operation_id='fixture-only', mysql_identity_sha256=SOURCE_ID,
                           recorded_at='2026-01-01T00:00:00+00:00',
                           expires_at='2026-01-01T00:15:00+00:00',
                           writers_excluded=True, all_writer_scopes_reviewed=True,
                           broker_pending_preserved=True, business_reopened=False,
                           running_writers=0, unfinished_work=0)
        definitions, summaries, snapshot, self.body = [], {}, {}, []
        names = ['alembic_version', 'messaging_outbox'] + [f'fixture_{n}' for n in range(49)]
        for name in names:
            column = 'version_num' if name == 'alembic_version' else 'payload'
            values = [[HEAD.encode().hex()]] if name == 'alembic_version' else (
                [[None], [''], ['ff00']] if name == 'fixture_0' else [])
            lengths = [len(row[0]) // 2 for row in values if row[0] is not None]
            table = dict(name=name, ddl=f'CREATE TABLE `{name}` (`{column}` varbinary(64))',
                         columns=[dict(name=column)])
            definitions.append(table)
            summary = dict(rows=len(values), data_bytes=sum(lengths), max_row_bytes=max(lengths, default=0),
                           ddl_sha256=digest(table['ddl'].encode()), columns_sha256=digest(encoded(table['columns'])),
                           rows_sha256=digest(b''.join(sorted(map(row_hash, values)))))
            summaries[name] = summary
            snapshot[name] = dict(columns=[column], **summary)
            self.body.extend([dict(kind='table', **table), *(dict(kind='row', values=row) for row in values),
                              dict(kind='endtable', name=name, **summary)])
        self.footer = dict(kind='complete', tables=summaries, definitions_sha256=digest(encoded(definitions)),
                           source=source, head=HEAD, total_rows=4, total_data_bytes=len(HEAD) + 2,
                           captured_at='2026-01-01T00:02:00+00:00', read_only=True, frozen=False,
                           execution_authorized=False, transaction_released=True, pool_released=True)
        self.protection = dict(schema='ai-publisher-protection/v1', source_sha='a' * 40,
                               operation_id='fixture-only', frozen=True, execution_approval=False,
                               consistency_basis='snapshot-plus-owner-writer-attestation',
                               transaction_released=True, pool_released=True,
                               snapshot=dict(schema='ai-publisher-snapshot/v1', state='43_intact',
                                             head=HEAD, mysql_identity_sha256=SOURCE_ID, mysql_version='8.0.36',
                                             fingerprint_codec='mysql-binary-null-length-rowhash-sorted/v1',
                                             captured_at='2026-01-01T00:03:00+00:00',
                                             target=dict(snapshot.pop('messaging_outbox'), present=True),
                                             ledger=dict(snapshot.pop('alembic_version'), heads=[HEAD]), retained=snapshot))

    def materials(self):
        args = SimpleNamespace(principal_sha256='a' * 64)
        for name, value in [('writer', self.writer), ('protection', self.protection)]:
            path = self.root / name
            raw = encoded(value)
            path.write_bytes(raw)
            path.chmod(0o600)
            setattr(args, name, path)
            setattr(args, name + '_sha256', digest(raw))
            if name == 'writer':
                self.protection['writer_sha256'] = digest(raw)
        args.backup = self.root / 'backup.gz'
        raw = gzip.compress(b'\n'.join(map(encoded, [self.header, *self.body, self.footer])) + b'\n')
        args.backup.write_bytes(raw)
        args.backup.chmod(0o600)
        args.backup_sha256 = digest(raw)
        return args

    def test_isolated_comparison_never_authorizes_execution(self):
        result = check(self.materials())
        self.assertEqual(result['tables_compared'], 51)
        self.assertFalse(result['execution_authorized'])

    def test_matching_archive_sha_does_not_hide_row_corruption(self):
        row = next(record for record in self.body if record['kind'] == 'row' and record['values'] == ['ff00'])
        row['values'] = ['ff01']
        with self.assertRaisesRegex(ValueError, 'backup_table_bytes_differ'):
            check(self.materials())

    def test_snapshot_conflict_or_principal_drift_blocks(self):
        args = self.materials()
        args.principal_sha256 = 'b' * 64
        with self.assertRaisesRegex(ValueError, 'source_or_principal_differs'):
            check(args)
        self.protection['snapshot']['retained']['fixture_0']['rows_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'protection_and_backup_differ'):
            check(self.materials())

    def test_outside_writer_interval_blocks(self):
        self.writer['expires_at'] = '2026-01-01T00:01:30+00:00'
        with self.assertRaisesRegex(ValueError, 'backup_outside_writer_interval'):
            check(self.materials())
