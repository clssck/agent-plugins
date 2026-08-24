-- Locks: Queries with active exclusive locks
-- Shows queries currently holding exclusive locks that may block others
-- Source: Crunchy Bridge CLI (heroku-pg-extras)

SELECT
  pg_stat_activity.pid,
  pg_class.relname,
  pg_locks.transactionid AS transaction_id,
  pg_locks.granted,
  CASE WHEN length(pg_stat_activity.query) <= 60 THEN pg_stat_activity.query ELSE substr(pg_stat_activity.query, 1, 59) || '…' END as query_snippet,
  age(now(),pg_stat_activity.query_start)::text AS age
FROM pg_stat_activity,pg_locks left
OUTER JOIN pg_class
  ON (pg_locks.relation = pg_class.oid)
WHERE pg_stat_activity.query <> '<insufficient privilege>'
  AND pg_locks.pid = pg_stat_activity.pid
  AND pg_locks.mode = 'ExclusiveLock'
  AND pg_stat_activity.pid <> pg_backend_pid()
ORDER BY query_start;
