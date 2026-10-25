#!/usr/bin/env python3
"""Derive restore bytes for two verified 0040 generated-column expressions.

Pure file operation. Never connects to MySQL or authorizes data restoration.
Original protection bytes are retained; all data and unrelated DDL stay exact.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

EXPECTED = {'4257a573673fb143338cc38dfd9657fab1480251d6d6bee74725f0c7915f7117',
            '0f8608f1f2237f1d08794f2b85d0fec80dc3e4cc84a7eea9871d6019ba6741a5'}


def private_open(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.geteuid() or info.st_nlink != 1 or info.st_size > limit):
        os.close(fd)
        raise ValueError('bounded private original file required')
    return os.fdopen(fd, 'rb')


def derive(source, columns, target, source_sha, columns_sha, database='ai'):
    if (not re.fullmatch('[a-z0-9_]{1,64}', database)
            or any(not re.fullmatch('[0-9a-f]{64}', x) for x in (source_sha, columns_sha))):
        raise ValueError('exact reviewed source and database required')
    with private_open(columns, 1024*1024) as file:
        metadata = file.read().strip()
    if hashlib.sha256(metadata).hexdigest() != columns_sha:
        raise ValueError('original column metadata differs')
    hashes = [hashlib.sha256(row).hexdigest() for row in metadata.splitlines()]
    if not all(hashes.count(x) == 1 for x in EXPECTED):
        raise ValueError('exact original 0040 expressions required')
    before, after = hashlib.sha256(), hashlib.sha256()
    changed = {'prompt': 0, 'semantic': 0}
    current = None
    inside = False
    definitions = 0
    total = 0
    with private_open(source, 8*1024**3) as file:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as output:
            for original in file:
                before.update(original)
                value = original
                selected = re.fullmatch(rb'USE `([a-z0-9_]+)`;\r?\n?', original)
                if selected:
                    current = selected.group(1).decode()
                if current == database and original.rstrip(b'\r\n') == b'CREATE TABLE `governance_draft_heads` (':
                    if inside:
                        raise ValueError('nested table definition refused')
                    definitions += 1
                    inside = True
                if inside:
                    for kind in changed:
                        if original.startswith(('  `'+kind+'_draft_id_key` ').encode()):
                            literal = ("_ascii'"+kind+"'").encode()
                            if (b' GENERATED ALWAYS AS (' not in original or b' STORED' not in original
                                    or original.count(literal) != 1 or original.count(b'_ascii') != 1):
                                raise ValueError('original dump expression differs')
                            value = original.replace(literal, ("_utf8mb4'"+kind+"'").encode(), 1)
                            changed[kind] += 1
                    if original.startswith(b') ENGINE='):
                        inside = False
                output.write(value)
                after.update(value)
                total += len(value)
            if before.hexdigest() != source_sha or definitions != 1 or inside or changed != {'prompt': 1, 'semantic': 1}:
                raise ValueError('exact complete original snapshot required; partial output is not usable')
            output.flush()
            os.fsync(output.fileno())
    return {'schema': 'm3-mysql-restore-byte-derivation/v1', 'source_sha256': before.hexdigest(),
            'column_metadata_sha256': columns_sha, 'output_sha256': after.hexdigest(),
            'output_bytes': total, 'known_literal_replacements': 2, 'database': database,
            'database_connected': False, 'restoration_authorized': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'columns', 'target'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--expected-source-sha256', required=True)
    parser.add_argument('--expected-columns-sha256', required=True)
    args = parser.parse_args(argv)
    try:
        result = derive(args.source, args.columns, args.target,
                        args.expected_source_sha256, args.expected_columns_sha256)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError):
        print('{"status":"unavailable","restoration_authorized":false}')
        return 1


if __name__ == '__main__': raise SystemExit(main())
