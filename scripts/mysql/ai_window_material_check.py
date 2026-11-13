"""Offline W05 comparison of private AI protection and logical backup bytes."""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import stat

from ai_backup_material import HEAD, MAX_BYTES, MAX_ROWS, SOURCE_ID, Refused, digest, encoded, frames, require, row_hash, verify_archive


def private_document(path, expected):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_uid == os.geteuid(), 'private_document_required')
        raw = stream.read(1024 * 1024 + 1)
    require(len(raw) <= 1024 * 1024 and digest(raw) == expected, 'document_hash_differs')
    return json.loads(raw)


def backup_contents(path):
    records = iter(frames(path))
    header = next(records)
    require(header['kind'] == 'header' and header['schema'] == 'ai-full-logical-backup/v1'
            and header['head'] == HEAD and header['tables'] == 51 and header['frozen'] is False,
            'original_backup_header_required')
    definitions, summaries, complete = [], {}, None
    current, hashes, size, maximum = None, [], 0, 0
    total_rows, total_bytes = 0, 0
    for frame in records:
        require(complete is None, 'trailing_backup_frames')
        kind = frame['kind']
        if kind == 'table':
            require(current is None and frame['name'] not in summaries and len(definitions) < 51,
                    'backup_table_order_invalid')
            current = {key: frame[key] for key in ('name', 'ddl', 'columns')}
            definitions.append(current)
            hashes, size, maximum = [], 0, 0
        elif kind == 'row':
            values = frame['values']
            require(current is not None and isinstance(values, list) and len(values) == len(current['columns']),
                    'backup_row_width_invalid')
            hashes.append(row_hash(values))
            length = sum(len(value) // 2 for value in values if value is not None)
            size += length
            maximum = max(maximum, length)
            total_rows += 1
            total_bytes += length
            require(total_rows <= MAX_ROWS and total_bytes <= MAX_BYTES and maximum <= 16 * 1024 * 1024,
                    'backup_row_budget_exceeded')
        elif kind == 'endtable':
            require(current is not None and frame['name'] == current['name'], 'backup_table_footer_invalid')
            expected = dict(rows=len(hashes), data_bytes=size, max_row_bytes=maximum,
                            ddl_sha256=digest(current['ddl'].encode()),
                            columns_sha256=digest(encoded(current['columns'])),
                            rows_sha256=digest(b''.join(sorted(hashes))))
            require(frame == dict(kind='endtable', name=current['name'], **expected), 'backup_table_bytes_differ')
            summaries[current['name']] = expected
            current = None
        elif kind == 'complete':
            complete = frame
        else:
            raise ValueError('unexpected_backup_frame')
    require(complete is not None and current is None and len(summaries) == 51
            and complete['tables'] == summaries and complete['head'] == HEAD
            and complete['total_rows'] == total_rows and complete['total_data_bytes'] == total_bytes
            and complete['source'] == header['source'] and complete['read_only'] is True
            and complete['frozen'] is False and complete['execution_authorized'] is False
            and complete['transaction_released'] is True and complete['pool_released'] is True
            and complete['definitions_sha256'] == digest(encoded(definitions)), 'complete_backup_required')
    return header, definitions, complete


def compare_snapshot(snapshot, header, definitions, complete, principal):
    source = header['source']
    require(snapshot['schema'] == 'ai-publisher-snapshot/v1' and snapshot['state'] == '43_intact'
            and snapshot['head'] == HEAD and snapshot['ledger']['heads'] == [HEAD]
            and snapshot['target']['present'] is True and snapshot['target']['rows'] == 0
            and snapshot['mysql_identity_sha256'] == source['mysql_identity_sha256'] == SOURCE_ID
            and snapshot['mysql_version'] == source['version'] == '8.0.36'
            and source['database'] == 'ai' and re.fullmatch('[0-9a-f]{64}', principal)
            and source['principal_sha256'] == principal,
            'source_or_principal_differs')
    require(snapshot['fingerprint_codec'] == 'mysql-binary-null-length-rowhash-sorted/v1'
            and len(snapshot['retained']) == 49
            and not {'messaging_outbox', 'alembic_version'} & snapshot['retained'].keys(),
            'protection_catalog_invalid')
    original = dict(snapshot['retained'], messaging_outbox=snapshot['target'], alembic_version=snapshot['ledger'])
    require(original.keys() == complete['tables'].keys(), 'backup_catalog_differs')
    for table in definitions:
        name = table['name']
        before, after = original[name], complete['tables'][name]
        require(before['columns'] == [column['name'] for column in table['columns']]
                and all(before[k] == after[k] for k in ('rows', 'data_bytes', 'ddl_sha256', 'rows_sha256')),
                'protection_and_backup_differ')


def check(args):
    protection = private_document(args.protection, args.protection_sha256)
    writer = private_document(args.writer, args.writer_sha256)
    require(protection['schema'] == 'ai-publisher-protection/v1' and protection['frozen'] is True
            and protection['consistency_basis'] == 'snapshot-plus-owner-writer-attestation'
            and protection['transaction_released'] is True and protection['pool_released'] is True
            and protection['execution_approval'] is False and protection['writer_sha256'] == args.writer_sha256
            and writer['schema'] == 'ai-publisher-writer-exclusion/v1'
            and writer['source_sha'] == protection['source_sha']
            and writer['operation_id'] == protection['operation_id']
            and writer['mysql_identity_sha256'] == SOURCE_ID
            and writer['writers_excluded'] is True and writer['all_writer_scopes_reviewed'] is True
            and writer['broker_pending_preserved'] is True and writer['business_reopened'] is False
            and type(writer['running_writers']) is int and type(writer['unfinished_work']) is int
            and writer['running_writers'] == writer['unfinished_work'] == 0, 'same_window_protection_required')
    verify_archive(args.backup, args.backup_sha256)
    header, definitions, complete = backup_contents(args.backup)
    verify_archive(args.backup, args.backup_sha256)
    compare_snapshot(protection['snapshot'], header, definitions, complete, args.principal_sha256)
    issued, expires, snapshot_at, start, end = (
        datetime.fromisoformat(value) for value in (writer['recorded_at'], writer['expires_at'],
            protection['snapshot']['captured_at'], header['snapshot_started_at'], complete['captured_at'])
    )
    require(all(value.utcoffset() is not None for value in (issued, expires, snapshot_at, start, end))
            and 0 < (expires - issued).total_seconds() <= 3600
            and issued <= snapshot_at <= expires and issued <= start <= end <= expires,
            'backup_outside_writer_interval')
    return dict(schema='ai-window-material-comparison/v1', operation_id=protection['operation_id'],
                protection_sha256=args.protection_sha256, writer_sha256=args.writer_sha256,
                backup_sha256=args.backup_sha256, tables_compared=51, matched=True,
                continuous_writer_exclusion_verified=False, execution_authorized=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('protection', 'writer', 'backup'):
        parser.add_argument('--' + name, type=Path, required=True)
        parser.add_argument('--' + name + '-sha256', required=True)
    parser.add_argument('--principal-sha256', required=True)
    try:
        print(json.dumps(check(parser.parse_args()), sort_keys=True))
    except Refused as error:
        print(json.dumps(dict(matched=False, refusal=str(error))))
        return 1
    except (OSError, ValueError, KeyError, TypeError, StopIteration, EOFError) as error:
        print(json.dumps(dict(matched=False, error_type=type(error).__name__)))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
