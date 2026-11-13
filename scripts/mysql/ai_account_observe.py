import asyncio,hashlib,json,sys,os
from datetime import datetime, timezone
import sqlalchemy as sa
from qs_ai.infrastructure.persistence.mysql.database import Database

def sha(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
async def main():
 opts=json.load(sys.stdin);d=Database(opts['url'],pool_size=1,max_overflow=0,tls_mode=opts['tls_mode'],tls_ca_file=opts['tls_ca_file'])
 assert opts['tls_mode']=='VERIFY_IDENTITY'
 try:
  async with asyncio.timeout(45),d.engine.connect() as c:
   await c.execution_options(isolation_level='REPEATABLE READ');await c.execute(sa.text('SET SESSION TRANSACTION READ ONLY'));await c.execute(sa.text('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY'))
   out=dict(read_only=True,writer_exclusion_proved=False,execution_authorized=False,observer_uid=os.getuid())
   out['identity']=dict((await c.execute(sa.text('SELECT @@server_uuid AS server_uuid,DATABASE() AS db,CURRENT_USER() AS account,USER() AS login,CURRENT_ROLE() AS roles,@@global.partial_revokes AS partial_revokes,@@global.read_only AS server_readonly,@@global.super_read_only AS server_super_readonly,@@version AS version,@@session.transaction_read_only AS session_readonly,@@session.sql_mode AS sql_mode,@@session.time_zone AS time_zone'))).mappings().one())
   ident=out['identity'];out['mysql_identity_sha256']=sha([str(ident['server_uuid']),str(ident['db'])]);assert out['mysql_identity_sha256']=='04f119402a8b7704f84df45bd3e3fb182eaf1ea05febe7fbad38f66c76740fc3' and ident['db']=='ai' and ident['version']=='8.0.36' and ident['session_readonly']==1
   out['principal_sha256']=sha([str(ident['server_uuid']),str(ident['db']),str(ident['account'])]);out['grants']=[str(row[0]) for row in await c.execute(sa.text('SHOW GRANTS'))]
   out['tls_cipher']=str((await c.execute(sa.text("SHOW SESSION STATUS LIKE 'Ssl_cipher'"))).one()[1]);assert out['tls_cipher']
   out['head']=(await c.execute(sa.text('SELECT version_num FROM alembic_version'))).scalars().all();assert out['head']==['0043_native_transaction_limit']
   out['target_rows']=int(await c.scalar(sa.text('SELECT COUNT(*) FROM messaging_outbox')));assert out['target_rows']==0
   out['tables']=[dict(row) for row in (await c.execute(sa.text("SELECT TABLE_NAME AS name,ENGINE AS engine,TABLE_COLLATION AS collation,TABLE_TYPE AS kind FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME"))).mappings()];assert len(out['tables'])==51 and all(x['kind']=='BASE TABLE' and x['engine']=='InnoDB' for x in out['tables'])
   out['columns']=[dict(row) for row in (await c.execute(sa.text("SELECT TABLE_NAME AS tbl,ORDINAL_POSITION AS pos,COLUMN_NAME AS name,COLUMN_TYPE AS typ,DATA_TYPE AS data_type,IS_NULLABLE AS nullable,HEX(CAST(COLUMN_DEFAULT AS BINARY)) AS default_hex,EXTRA AS extra,CHARACTER_SET_NAME AS charset,COLLATION_NAME AS collation,HEX(COLUMN_COMMENT) AS comment_hex,GENERATION_EXPRESSION AS expression FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME,ORDINAL_POSITION"))).mappings()]
   out['database_definition']=str((await c.execute(sa.text('SHOW CREATE DATABASE `ai`'))).one()[1])
   for kind,query in [('views','SELECT COUNT(*) FROM information_schema.VIEWS WHERE TABLE_SCHEMA=DATABASE()'),('triggers','SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE()'),('events','SELECT COUNT(*) FROM information_schema.EVENTS WHERE EVENT_SCHEMA=DATABASE()'),('routines','SELECT COUNT(*) FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=DATABASE()')]:out[kind]=int(await c.scalar(sa.text(query)))
   out['binlog']={}
   for kind,query in [('status','SHOW MASTER STATUS'),('files','SHOW BINARY LOGS')]:
    try:out['binlog'][kind]=[dict(row) for row in (await c.execute(sa.text(query))).mappings()]
    except Exception as error:out['binlog'][kind]={'available':False,'mysql_code':int(getattr(error,'orig',error).args[0]) if getattr(error,'orig',error).args and isinstance(getattr(error,'orig',error).args[0],int) else None}
   out['binlog']['enabled']=bool(await c.scalar(sa.text('SELECT @@global.log_bin')));out['binlog']['retention_seconds']=int(await c.scalar(sa.text('SELECT @@global.binlog_expire_logs_seconds')))
   await c.rollback();out['transaction_released']=True
 finally:await d.close()
 out['pool_released']=True;out['observed_at']=datetime.now(timezone.utc).isoformat();print(json.dumps(out,default=str))
if __name__=='__main__':asyncio.run(main())
