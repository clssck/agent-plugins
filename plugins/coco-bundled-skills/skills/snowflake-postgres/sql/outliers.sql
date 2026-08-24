-- Outliers: Queries with longest running time in aggregate
-- Requires pg_stat_statements extension
-- Note: sync_io_time requires track_io_timing=on (shows N/A if disabled)

SELECT
  (interval '1 millisecond' * total_exec_time)::text AS total_exec_time,
  to_char((total_exec_time/sum(total_exec_time) OVER()) * 100, 'FM90D0') || '%' AS prop_exec_time,
  to_char(calls, 'FM999G999G999G990') AS ncalls,
  'N/A' AS sync_io_time,
  CASE WHEN length(query) <= 60 THEN query ELSE substr(query, 1, 59) || '…' END AS query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;
