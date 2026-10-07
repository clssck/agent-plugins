-- Root Cause Analysis: Column-Level Lineage
-- Trace a specific column back to its source columns
-- Replace <database>, <schema>, <table>, <column> with actual values BEFORE executing

-- Note: Column-level lineage in ACCESS_HISTORY depends on query patterns
-- This query attempts to trace column origins through access patterns

WITH column_access AS (
    -- Find queries that wrote to the target column
    SELECT 
        ah.query_id,
        ah.query_start_time,
        ah.user_name,
        col.value:columnName::STRING AS target_column,
        base.value:objectName::STRING AS source_object,
        src_col.value:columnName::STRING AS source_column
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
    LATERAL FLATTEN(input => objects_modified) AS modified,
    LATERAL FLATTEN(input => modified.value:columns, outer => true) AS col,
    LATERAL FLATTEN(input => base_objects_accessed) AS base,
    LATERAL FLATTEN(input => base.value:columns, outer => true) AS src_col
    WHERE modified.value:objectDomain::STRING IN ('Table', 'View', 'Dynamic Table')
      AND modified.value:objectName::STRING = '<database>.<schema>.<table>'
      AND (col.value:columnName::STRING = '<column>' OR col.value IS NULL)
      AND base.value:objectDomain::STRING IN ('Table', 'View', 'Dynamic Table')
      AND base.value:objectName::STRING != '<database>.<schema>.<table>'
      AND ah.query_start_time >= DATEADD(day, -90, CURRENT_TIMESTAMP())
),
source_columns AS (
    SELECT
        source_object,
        source_column,
        COUNT(DISTINCT query_id) AS occurrence_count,
        MAX(query_start_time) AS last_seen
    FROM column_access
    WHERE source_column IS NOT NULL
    GROUP BY source_object, source_column
)
SELECT
    '<database>.<schema>.<table>.<column>' AS target_column,
    source_object,
    source_column,
    occurrence_count,
    last_seen,
    CASE 
        WHEN occurrence_count >= 10 THEN 'HIGH'
        WHEN occurrence_count >= 3 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS confidence
FROM source_columns
ORDER BY occurrence_count DESC, last_seen DESC
LIMIT 20;
