"""AI read-only snapshot export and credential-free, network-none restore proof.

Raw gzip frames contain real business data: private host files only, never CI.
No source writes, FLUSH, locks, grants or business/SDK lifecycle are issued.
"""
import asyncio
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import sys
from urllib.parse import urlsplit

SOURCE_ID = '04f119402a8b7704f84df45bd3e3fb182eaf1ea05febe7fbad38f66c76740fc3'
HEAD = '0043_native_transaction_limit'
MAX_ROWS = 20000
MAX_BYTES = 134217728
MAX_FRAME = 40 * 1024 * 1024
TRACE = {}
COLS = ("SELECT TABLE_NAME AS tbl,ORDINAL_POSITION AS pos,COLUMN_NAME AS name,COLUMN_TYPE AS typ,"
        "DATA_TYPE AS data_type,IS_NULLABLE AS nullable,HEX(CAST(COLUMN_DEFAULT AS BINARY)) AS default_hex,"
        "EXTRA AS extra,CHARACTER_SET_NAME AS charset,COLLATION_NAME AS collation,"
        "HEX(COLUMN_COMMENT) AS comment_hex,GENERATION_EXPRESSION AS expression "
        "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME,ORDINAL_POSITION")


class Refused(ValueError):
    pass


def require(value, reason):
    if not value:
        raise Refused(reason)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def identifier(value):
    require(isinstance(value, str) and re.fullmatch('[A-Za-z0-9_]{1,64}', value), 'unsafe_identifier')
    return '`' + value + '`'


def row_hash(values):
    h = hashlib.sha256()
    for value in values:
        if value is None:
            h.update(b'\x00')
        else:
            require(isinstance(value, str) and re.fullmatch('(?:[0-9A-Fa-f]{2})*', value), 'invalid_hex')
            b = bytes.fromhex(value)
            h.update(b'\x01' + len(b).to_bytes(8, 'big') + b)
    return h.digest()


def value_sql(value, column):
    if value is None:
        return 'NULL'
    row_hash([value])
    literal = "X'" + value + "'"
    if column['data_type'] in {'binary', 'varbinary', 'tinyblob', 'blob', 'mediumblob', 'longblob', 'bit'}:
        return literal
    require(column['data_type'] in {'char', 'varchar', 'text', 'tinytext', 'mediumtext', 'longtext',
                                   'json', 'int', 'integer', 'bigint', 'smallint', 'tinyint', 'mediumint',
                                   'decimal', 'float', 'double', 'date', 'datetime', 'timestamp', 'time', 'year', 'enum', 'set'},
            'unknown_column_type')
    charset = column['charset'] or 'utf8mb4'
    require(re.fullmatch('[a-z0-9_]+', charset), 'unsafe_charset')
    return 'CONVERT(' + literal + ' USING ' + charset + ')'


def insert_sql(name, columns, values):
    require(len(values) == len(columns), 'row_width_differs')
    writable = [(c, v) for c, v in zip(columns, values) if not c['expression']]
    require(writable, 'no_writable_columns')
    return ('INSERT INTO ' + identifier(name) + ' (' + ','.join(identifier(c['name']) for c, v in writable)
            + ') VALUES (' + ','.join(value_sql(v, c) for c, v in writable) + ')')


def restore_definition(ddl, columns):
    """Rebuild generated expressions from original metadata, not SHOW CREATE's lossy rendering.

    Both original forms are retained; restored SHOW CREATE and full column metadata
    must still match. This never alters the source or relaxes the comparison.
    """
    lines = ddl.splitlines(keepends=True)
    for column in columns:
        if not column['expression']:
            continue
        prefix = '  ' + identifier(column['name']) + ' '
        indices = [i for i, line in enumerate(lines) if line.startswith(prefix)]
        require(len(indices) == 1, 'generated_column_missing')
        i = indices[0]
        marker = ' GENERATED ALWAYS AS ('
        require(lines[i].count(marker) == 1, 'generated_definition_unknown')
        before, expr = lines[i].split(marker, 1)
        ends = [(expr.rfind(') ' + kind), kind) for kind in ('STORED', 'VIRTUAL')]
        pos, kind = max(ends)
        require(pos >= 0 and kind in column['extra'], 'generated_storage_unknown')
        # INFORMATION_SCHEMA escapes literal quotes; it is metadata, not executable SQL.
        # Only the source-reviewed AI literal encoding and charset-introducer
        # difference are accepted. Raw restored metadata is still compared exactly.
        restored_expression = column['expression'].replace(chr(92) + chr(39), chr(39))
        require(chr(92) not in restored_expression, 'unreviewed_expression_escaping')
        canonical = lambda value: re.sub(r"_(?:ascii|utf8mb4|utf8mb3|utf8)(?=')", '', value)
        require(canonical(restored_expression) == canonical(expr[:pos]), 'expression_structure_differs')
        lines[i] = before + marker + restored_expression + expr[pos:]
    return ''.join(lines)


def verify_archive(path, expected):
    require(isinstance(expected,str) and re.fullmatch('[0-9a-f]{64}',expected), 'archive_hash_required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode)==0o600 and info.st_uid==os.geteuid(), 'private_archive_required')
        h=hashlib.sha256();size=0
        while block:=stream.read(1024*1024):
            size+=len(block);require(size<=320*1024*1024,'archive_size_budget');h.update(block)
    require(h.hexdigest()==expected,'archive_hash_differs')


def frames(path):
    total = 0
    with gzip.open(path, 'rb') as stream:
        while raw := stream.readline(MAX_FRAME + 1):
            total += len(raw)
            require(len(raw) <= MAX_FRAME and total <= 310 * 1024 * 1024, 'backup_decode_budget')
            value = json.loads(raw)
            require(isinstance(value, dict), 'backup_frame_object_required')
            yield value


async def metadata(c):
    import sqlalchemy as sa
    rows = [dict(v) for v in (await c.execute(sa.text(COLS))).mappings()]
    tables = [dict(v) for v in (await c.execute(sa.text("SELECT TABLE_NAME AS name,ENGINE AS engine,TABLE_TYPE AS kind FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME"))).mappings()]
    require(len(tables) == 51 and all(v['engine'] == 'InnoDB' and v['kind'] == 'BASE TABLE' for v in tables), 'exact51_innodb_required')
    result = []
    for item in tables:
        name = item['name']; ddl = str((await c.exec_driver_sql('SHOW CREATE TABLE ' + identifier(name))).one()[1])
        columns = [v for v in rows if v['tbl'] == name]
        require(columns, 'columns_missing')
        result.append(dict(name=name, ddl=ddl, columns=columns))
    return result


async def identity(c):
    import sqlalchemy as sa
    uuid, db, version, account = (await c.execute(sa.text('SELECT @@server_uuid,DATABASE(),VERSION(),CURRENT_USER()'))).one()
    return dict(mysql_identity_sha256=digest(encoded([str(uuid), str(db)])), version=str(version), database=str(db), principal_sha256=digest(encoded([str(uuid),str(db),str(account)])))


async def begin_read(c):
    import sqlalchemy as sa
    await c.execution_options(isolation_level='REPEATABLE READ')
    await c.execute(sa.text("SET SESSION time_zone='+00:00'"))
    await c.execute(sa.text('SET SESSION TRANSACTION READ ONLY'))
    await c.execute(sa.text('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY'))


async def scan(c, table, emit=None):
    import sqlalchemy as sa
    names = [v['name'] for v in table['columns']]
    query = 'SELECT ' + ','.join('HEX(CAST(' + identifier(v) + ' AS BINARY))' for v in names) + ' FROM ' + identifier(table['name'])
    hashes = []; size = 0; maximum = 0
    async with c.stream(sa.text(query), execution_options={'yield_per': 1}) as rows:
        async for row in rows:
            values = list(row); n = sum(len(v) // 2 for v in values if v is not None)
            size += n; maximum = max(maximum, n)
            require(len(hashes) < MAX_ROWS and size <= MAX_BYTES and n <= 16 * 1024 * 1024, 'table_backup_budget')
            hashes.append(row_hash(values))
            if emit:
                emit(dict(kind='row', values=values))
    return dict(rows=len(hashes), data_bytes=size, max_row_bytes=maximum, rows_sha256=digest(b''.join(sorted(hashes))),
                ddl_sha256=digest(table['ddl'].encode()), columns_sha256=digest(encoded(table['columns'])))


async def capture(db, expected_principal):
    import sqlalchemy as sa
    from qs_ai.maintenance.schema_refactor.validation import require_runtime_schema
    result = None
    with gzip.GzipFile(fileobj=sys.stdout.buffer, mode='wb', compresslevel=1, mtime=0) as archive:
        def emit(value):archive.write(encoded(value) + b'\n')
        async with asyncio.timeout(90), db.engine.connect() as c:
            await begin_read(c); source = await identity(c)
            require(source['mysql_identity_sha256'] == SOURCE_ID and source['version'] == '8.0.36' and source['principal_sha256']==expected_principal, 'source_identity_differs')
            await c.run_sync(require_runtime_schema)
            heads = (await c.exec_driver_sql('SELECT version_num FROM alembic_version')).scalars().all()
            require(heads == [HEAD], 'intact43_required')
            for table, column in [('VIEWS','TABLE_SCHEMA'),('TRIGGERS','TRIGGER_SCHEMA'),('EVENTS','EVENT_SCHEMA'),('ROUTINES','ROUTINE_SCHEMA')]:
                require(await c.scalar(sa.text('SELECT COUNT(*) FROM information_schema.' + table + ' WHERE ' + column + '=DATABASE()')) == 0, 'extra_objects_require_review')
            original = await metadata(c)
            header = dict(kind='header', schema='ai-full-logical-backup/v1', source=source, head=HEAD, tables=51,
                          database_definition=str((await c.exec_driver_sql('SHOW CREATE DATABASE `ai`')).one()[1]),
                          sql_mode=str(await c.scalar(sa.text('SELECT @@sql_mode'))), time_zone='+00:00',
                          snapshot_started_at=datetime.now(timezone.utc).isoformat(), frozen=False, production_approval=False)
            emit(header); result = dict(tables={}, total_rows=0, total_data_bytes=0)
            for table in original:
                emit(dict(kind='table', **table)); item = await scan(c, table, emit)
                result['tables'][table['name']] = item; result['total_rows'] += item['rows'];result['total_data_bytes'] += item['data_bytes']
                require(result['total_rows'] <= MAX_ROWS and result['total_data_bytes'] <= MAX_BYTES, 'full_backup_budget')
                emit(dict(kind='endtable', name=table['name'], **item))
            require(result['tables']['messaging_outbox']['rows'] == 0 and await metadata(c) == original, 'source_definition_drift')
            await c.run_sync(require_runtime_schema);await c.rollback();result['transaction_released'] = True
        await db.close();result['pool_released'] = True
        result.update(kind='complete', source=source, head=HEAD, read_only=True, frozen=False, execution_authorized=False,
                      captured_at=datetime.now(timezone.utc).isoformat(), definitions_sha256=digest(encoded(original)))
        emit(result)
    return result


def require_isolated(url):
    parsed = urlsplit(url)
    require(parsed.hostname == '127.0.0.1' and parsed.port == 3306 and parsed.path == '/ai', 'owned_loopback_only')
    require(socket.gethostname().startswith('m5-ai-restore-'), 'owned_hostname_required')
    interfaces = {v.split(':')[0].strip() for v in Path('/proc/net/dev').read_text().splitlines()[2:]}
    require(interfaces == {'lo'}, 'network_none_required')


async def restore_or_verify(db, path, mode):
    import sqlalchemy as sa
    from qs_ai.maintenance.schema_refactor.validation import require_runtime_schema
    records = frames(path);header = next(records)
    require(header['kind'] == 'header' and header['schema'] == 'ai-full-logical-backup/v1' and header['source']['mysql_identity_sha256'] == SOURCE_ID and header['head'] == HEAD, 'backup_source_required')
    expected = {}; current = None; complete = None; row_count = 0; definitions = []
    async with asyncio.timeout(600), db.engine.connect() as c:
        actual = await identity(c)
        require(actual['mysql_identity_sha256'] != SOURCE_ID and actual['version'] == '8.0.36' and actual['database'] == 'ai', 'isolated_identity_required')
        await c.exec_driver_sql("SET SESSION time_zone='+00:00'")
        if mode == 'restore':
            require(await c.scalar(sa.text('SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()')) == 0, 'empty_restore_target_required')
            await c.exec_driver_sql('SET SESSION FOREIGN_KEY_CHECKS=0')
            sql_mode = ','.join(sorted(set(header['sql_mode'].split(',')) | {'NO_AUTO_VALUE_ON_ZERO'}))
            await c.execute(sa.text('SET SESSION sql_mode=:value'),{'value':sql_mode})
        for frame in records:
            kind = frame.get('kind');TRACE.update(stage='frame_'+str(kind),table=frame.get('name',current['name'] if current else None))
            require(complete is None, 'trailing_backup_frames')
            if kind == 'table':
                require(current is None and frame['name'] not in expected, 'table_order_invalid');current = frame;definitions.append({k:frame[k] for k in ('name','ddl','columns')});row_count = 0
                require(frame['ddl'].startswith('CREATE TABLE ' + identifier(frame['name']) + ' ('), 'literal_create_required')
                if mode == 'restore':await c.exec_driver_sql(restore_definition(frame['ddl'],frame['columns']))
            elif kind == 'row':
                require(current is not None, 'orphan_backup_row');row_hash(frame['values']);row_count += 1
                require(row_count <= MAX_ROWS, 'restore_rows_budget')
                if mode == 'restore':await c.exec_driver_sql(insert_sql(current['name'],current['columns'],frame['values']))
            elif kind == 'endtable':
                require(current is not None and frame['name'] == current['name'] and row_count == frame['rows'], 'table_footer_invalid');expected[frame['name']]={k:frame[k] for k in ('rows','data_bytes','max_row_bytes','rows_sha256','ddl_sha256','columns_sha256')};current = None
                if mode == 'restore':await c.commit()
            elif kind == 'complete':
                require(current is None and len(expected) == 51 and frame['tables'] == expected and frame['transaction_released'] and frame['pool_released'], 'complete_backup_required');complete=frame
            else:raise Refused('unknown_backup_frame')
        require(complete is not None and digest(encoded(definitions)) == complete['definitions_sha256'], 'backup_truncated_or_changed')
        if mode == 'restore':
            await c.exec_driver_sql('SET SESSION FOREIGN_KEY_CHECKS=1');await c.commit()
        else:await c.rollback()
        await begin_read(c)
        TRACE.update(stage='verify_definitions',table=None)
        restored = await metadata(c)
        if restored != definitions:
            TRACE['definition_differences']=[a['name'] for a,b in zip(definitions,restored) if a!=b]
        require(restored == definitions, 'restored_definitions_or_columns_differ')
        observed = {}
        for table in restored:observed[table['name']] = await scan(c,table)
        require(observed == expected, 'restored_original_bytes_differ')
        await c.run_sync(require_runtime_schema)
        require((await c.exec_driver_sql('SELECT version_num FROM alembic_version')).scalars().all()==[HEAD], 'restored43_ledger_differs')
        require(str((await c.exec_driver_sql('SHOW CREATE DATABASE `ai`')).one()[1])==header['database_definition'], 'database_definition_differs')
        await c.rollback()
    await db.close()
    return dict(schema='ai-full-backup-restore-qualification/v1',source_identity=SOURCE_ID,restore_identity=actual['mysql_identity_sha256'],
                tables=51,total_rows=complete['total_rows'],total_data_bytes=complete['total_data_bytes'],head=HEAD,
                all_definitions_columns_and_original_bytes_identical=True,transaction_released=True,pool_released=True,
                snapshot_complete_sha256=digest(encoded(complete)),production_DDL=False,production_backup_restore_target=False,
                model_or_upstream_requests=False,mode=mode)


async def main():
    from qs_ai.infrastructure.persistence.mysql.database import Database
    opts=json.load(sys.stdin);mode=opts['mode'];require(mode in {'capture','restore','verify'}, 'fixed_mode_required')
    if mode!='capture':
        require_isolated(opts['url']);verify_archive(Path('/backup/capture.jsonl.gz'),opts['backup_sha256'])
    else:require(opts['tls_mode']=='VERIFY_IDENTITY', 'verified_source_TLS_required')
    db=Database(opts['url'],pool_size=1,max_overflow=0,tls_mode=opts['tls_mode'],tls_ca_file=opts.get('tls_ca_file'))
    try:
        result=await capture(db, opts['expected_principal']) if mode=='capture' else await restore_or_verify(db,Path('/backup/capture.jsonl.gz'),mode)
    finally:await db.close()
    if mode=='capture':print(json.dumps(result),file=sys.stderr)
    else:
        verify_archive(Path('/backup/capture.jsonl.gz'),opts['backup_sha256']);result['backup_archive_sha256']=opts['backup_sha256'];print(json.dumps(result))


if __name__=='__main__':
    try:asyncio.run(main())
    except BaseException as error:
        # No arbitrary exception text: SQL drivers can contain full original rows.
        orig=getattr(error,'orig',error);args=getattr(orig,'args',());number=args[0] if args and isinstance(args[0],int) else None
        print(json.dumps(dict(error_type=type(error).__name__,mysql_number=number,trace=TRACE,refusal=str(error) if isinstance(error,Refused) else None,qualified=False)),file=sys.stderr);raise SystemExit(1)
