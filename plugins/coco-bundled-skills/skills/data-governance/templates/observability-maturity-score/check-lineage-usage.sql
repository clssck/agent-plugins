-- ============================================================
-- CHECK LINEAGE USAGE
-- Assess whether GET_LINEAGE, OBJECT_DEPENDENCIES, and
-- column-level lineage (ACCESS_HISTORY) are used for
-- root cause analysis and impact analysis
-- ============================================================

-- Check 1: GET_LINEAGE usage in the last 90 days
-- Queries calling SNOWFLAKE.CORE.GET_LINEAGE for RCA/impact analysis
SELECT
    user_name,
    COUNT(*) AS query_count,
    MIN(start_time) AS first_used,
    MAX(start_time) AS last_used
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE start_time >= DATEADD('day', -90, CURRENT_TIMESTAMP())
  AND execution_status = 'SUCCESS'
  AND (
      LOWER(query_text) LIKE '%get_lineage%'
      OR LOWER(query_text) LIKE '%snowflake.core.get_lineage%'
  )
GROUP BY user_name
ORDER BY query_count DESC;

-- Check 2: GET_LINEAGE weekly frequency breakdown
-- Shows usage pattern over time to assess regularity
SELECT
    DATE_TRUNC('week', start_time) AS week_start,
    COUNT(*) AS lineage_queries,
    COUNT(DISTINCT user_name) AS distinct_users
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE start_time >= DATEADD('day', -90, CURRENT_TIMESTAMP())
  AND execution_status = 'SUCCESS'
  AND (
      LOWER(query_text) LIKE '%get_lineage%'
      OR LOWER(query_text) LIKE '%snowflake.core.get_lineage%'
  )
GROUP BY 1
ORDER BY 1 DESC;

-- Check 3: OBJECT_DEPENDENCIES view usage
-- Checks if users query the dependency graph for impact analysis
SELECT
    user_name,
    COUNT(*) AS query_count,
    MIN(start_time) AS first_used,
    MAX(start_time) AS last_used
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE start_time >= DATEADD('day', -90, CURRENT_TIMESTAMP())
  AND execution_status = 'SUCCESS'
  AND LOWER(query_text) LIKE '%object_dependencies%'
GROUP BY user_name
ORDER BY query_count DESC;

-- Check 4: Column-level lineage via ACCESS_HISTORY (OBJECTS_MODIFIED)
-- Checks if users query ACCESS_HISTORY with OBJECTS_MODIFIED for
-- column-level lineage tracking
SELECT
    user_name,
    COUNT(*) AS query_count,
    MIN(start_time) AS first_used,
    MAX(start_time) AS last_used
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE start_time >= DATEADD('day', -90, CURRENT_TIMESTAMP())
  AND execution_status = 'SUCCESS'
  AND LOWER(query_text) LIKE '%access_history%'
  AND (
      LOWER(query_text) LIKE '%objects_modified%'
      OR LOWER(query_text) LIKE '%directsources%'
      OR LOWER(query_text) LIKE '%basesourcecolumns%'
  )
GROUP BY user_name
ORDER BY query_count DESC;

-- Check 5: Overall lineage usage summary
-- Combined view of all lineage-related activity
SELECT
    CASE
        WHEN LOWER(query_text) LIKE '%get_lineage%' THEN 'GET_LINEAGE'
        WHEN LOWER(query_text) LIKE '%object_dependencies%' THEN 'OBJECT_DEPENDENCIES'
        WHEN LOWER(query_text) LIKE '%objects_modified%'
             OR LOWER(query_text) LIKE '%directsources%'
             OR LOWER(query_text) LIKE '%basesourcecolumns%' THEN 'COLUMN_LINEAGE (ACCESS_HISTORY)'
    END AS lineage_method,
    COUNT(*) AS total_queries,
    COUNT(DISTINCT user_name) AS distinct_users,
    MIN(start_time) AS first_used,
    MAX(start_time) AS last_used
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE start_time >= DATEADD('day', -90, CURRENT_TIMESTAMP())
  AND execution_status = 'SUCCESS'
  AND (
      LOWER(query_text) LIKE '%get_lineage%'
      OR LOWER(query_text) LIKE '%object_dependencies%'
      OR (
          LOWER(query_text) LIKE '%access_history%'
          AND (
              LOWER(query_text) LIKE '%objects_modified%'
              OR LOWER(query_text) LIKE '%directsources%'
              OR LOWER(query_text) LIKE '%basesourcecolumns%'
          )
      )
  )
GROUP BY 1
ORDER BY total_queries DESC;
