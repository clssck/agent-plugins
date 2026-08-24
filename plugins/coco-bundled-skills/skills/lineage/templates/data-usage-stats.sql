-- Data Usage Statistics: Who Uses This Data and How
-- Get detailed usage patterns for trust assessment
-- Replace <database>, <schema>, <table> with actual values BEFORE executing

WITH access_patterns AS (
    SELECT
        ah.user_name,
        qh.query_type,
        qh.warehouse_name,
        ah.query_start_time,
        qh.execution_status,
        qh.total_elapsed_time / 1000 AS execution_seconds
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah
    JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY qh ON ah.query_id = qh.query_id,
    LATERAL FLATTEN(input => ah.base_objects_accessed) AS base
    WHERE base.value:objectName::STRING = '<database>.<schema>.<table>'
      AND ah.query_start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
),
user_summary AS (
    SELECT
        user_name,
        COUNT(*) AS total_queries,
        COUNT(DISTINCT DATE(query_start_time)) AS active_days,
        MAX(query_start_time) AS last_access,
        ROUND(AVG(execution_seconds), 2) AS avg_execution_seconds
    FROM access_patterns
    GROUP BY user_name
),
query_type_summary AS (
    SELECT
        query_type,
        COUNT(*) AS query_count,
        COUNT(DISTINCT user_name) AS unique_users
    FROM access_patterns
    GROUP BY query_type
),
daily_usage AS (
    SELECT
        DATE(query_start_time) AS usage_date,
        COUNT(*) AS query_count,
        COUNT(DISTINCT user_name) AS unique_users
    FROM access_patterns
    GROUP BY usage_date
)
-- Main output: User summary
SELECT
    'USER_SUMMARY' AS section,
    user_name,
    total_queries,
    active_days,
    last_access,
    avg_execution_seconds,
    NULL AS additional_info
FROM user_summary
ORDER BY total_queries DESC
LIMIT 10;

-- Also useful: Query type breakdown
-- SELECT 'QUERY_TYPES' AS section, query_type, query_count, unique_users FROM query_type_summary;

-- Also useful: Daily usage trend
-- SELECT 'DAILY_TREND' AS section, usage_date, query_count, unique_users FROM daily_usage ORDER BY usage_date;
