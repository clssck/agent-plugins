-- Long Running: Queries running for more than five minutes
-- Identifies queries that may need optimization or termination
-- Source: Crunchy Bridge CLI (heroku-pg-extras)

SELECT
  pid,
  (now() - pg_stat_activity.query_start)::text AS duration,
  query AS query
FROM
  pg_stat_activity
WHERE
  pg_stat_activity.query <> ''::text
  AND state <> 'idle'
  AND now() - pg_stat_activity.query_start > interval '5 minutes'
ORDER BY
  now() - pg_stat_activity.query_start DESC;
