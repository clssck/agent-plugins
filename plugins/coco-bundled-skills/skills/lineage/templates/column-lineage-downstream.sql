-- Column Lineage: Downstream Impact Analysis
-- Find all downstream objects and columns that depend on a specific column
-- Replace <database>, <schema>, <table>, <column> with actual values BEFORE executing
--
-- CONFIGURABLE: Adjust DATEADD day value to extend/shorten lookback period (default: 90 days)
-- ACCESS_HISTORY retention is 365 days maximum

-- Uses ACCESS_HISTORY to find queries that read the target column
-- and wrote to other objects (showing downstream data flow)

WITH column_readers AS (
    -- Find queries that read the target column
    SELECT 
        ah.query_id,
        ah.query_start_time,
        ah.user_name,
        modified.value:objectName::STRING AS downstream_object,
        modified.value:objectDomain::STRING AS downstream_type,
        dest_col.value:columnName::STRING AS downstream_column
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
    LATERAL FLATTEN(input => base_objects_accessed) AS base,
    LATERAL FLATTEN(input => base.value:columns, outer => true) AS src_col,
    LATERAL FLATTEN(input => objects_modified, outer => true) AS modified,
    LATERAL FLATTEN(input => modified.value:columns, outer => true) AS dest_col
    WHERE base.value:objectName::STRING = '<database>.<schema>.<table>'
      AND base.value:objectDomain::STRING IN ('Table', 'View', 'Dynamic Table', 'Materialized View')
      AND (src_col.value:columnName::STRING = '<column>' OR src_col.value IS NULL)
      AND modified.value:objectName::STRING IS NOT NULL
      AND modified.value:objectName::STRING != '<database>.<schema>.<table>'
      AND ah.query_start_time >= DATEADD(day, -90, CURRENT_TIMESTAMP())
),
downstream_summary AS (
    SELECT
        downstream_object,
        downstream_type,
        downstream_column,
        COUNT(DISTINCT query_id) AS query_count,
        COUNT(DISTINCT user_name) AS user_count,
        MAX(query_start_time) AS last_accessed
    FROM column_readers
    WHERE downstream_object IS NOT NULL
    GROUP BY downstream_object, downstream_type, downstream_column
)
SELECT
    '<database>.<schema>.<table>.<column>' AS source_column,
    downstream_object,
    downstream_type,
    downstream_column,
    query_count,
    user_count,
    last_accessed,
    -- Risk assessment based on usage
    CASE
        WHEN query_count >= 50 THEN 'CRITICAL'
        WHEN query_count >= 10 THEN 'HIGH'
        WHEN query_count >= 3 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS impact_level,
    -- Confidence in the lineage
    CASE
        WHEN downstream_column IS NOT NULL AND query_count >= 5 THEN 'HIGH'
        WHEN downstream_column IS NOT NULL THEN 'MEDIUM'
        ELSE 'LOW'
    END AS confidence
FROM downstream_summary
ORDER BY 
    CASE WHEN query_count >= 50 THEN 1 WHEN query_count >= 10 THEN 2 ELSE 3 END,
    query_count DESC,
    last_accessed DESC
LIMIT 50;
