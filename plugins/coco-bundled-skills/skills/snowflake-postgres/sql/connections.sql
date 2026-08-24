-- Connections: Connection counts per role
-- Useful for identifying connection pool issues or runaway connections
-- Source: Crunchy Bridge CLI

SELECT count(*) AS connection_count, usename AS role_name
FROM pg_stat_activity
WHERE usename IS NOT NULL
GROUP by 2
ORDER by 1 DESC;
