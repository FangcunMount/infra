-- AI246 DB07 query inventory; read-only review material, not an executor/approval.
-- Future fixed administrator transport must independently bind source, server_uuid
-- plus DATABASE() identity, execution UID, private outputs and query deadlines.
-- PROCESS alone does not prove metadata/lock/global dependency visibility.
-- No routine definitions, SQL INFO, secrets, business bodies, KILL, GRANT or DDL.
START TRANSACTION READ ONLY;
SELECT @@server_uuid AS server_uuid, DATABASE() AS database_name,
       @@performance_schema AS performance_schema_enabled;
SELECT version_num FROM ai.alembic_version;
SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE
  FROM information_schema.PROCESSLIST;
SELECT trx_id, trx_state, trx_started, trx_mysql_thread_id,
       trx_tables_locked, trx_rows_locked, trx_rows_modified
  FROM information_schema.INNODB_TRX;
SELECT THREAD_ID, PROCESSLIST_ID, PROCESSLIST_DB, PROCESSLIST_COMMAND,
       PROCESSLIST_TIME, PROCESSLIST_STATE
  FROM performance_schema.threads
 WHERE TYPE='FOREGROUND';
SELECT OBJECT_TYPE, OBJECT_SCHEMA, OBJECT_NAME, OWNER_THREAD_ID,
       LOCK_TYPE, LOCK_DURATION, LOCK_STATUS
  FROM performance_schema.metadata_locks
 WHERE OBJECT_SCHEMA='ai' OR OBJECT_SCHEMA IS NULL;
SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME,
       REFERENCED_TABLE_SCHEMA, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
  FROM information_schema.KEY_COLUMN_USAGE
 WHERE REFERENCED_TABLE_SCHEMA='ai' AND REFERENCED_TABLE_NAME='messaging_outbox';
SELECT TRIGGER_SCHEMA, TRIGGER_NAME, EVENT_OBJECT_SCHEMA, EVENT_OBJECT_TABLE
  FROM information_schema.TRIGGERS WHERE EVENT_OBJECT_SCHEMA='ai';
SELECT EVENT_SCHEMA, EVENT_NAME, STATUS
  FROM information_schema.EVENTS WHERE EVENT_SCHEMA='ai';
ROLLBACK;
-- Views/dynamic SQL, schedulers, manual scripts and users with invisible schemas
-- still require independent source/inventory/privilege review. Zero observed
-- rows at one time never certify writer exclusion or permission to execute DDL.
