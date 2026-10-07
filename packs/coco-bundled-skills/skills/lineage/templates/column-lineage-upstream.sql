-- Column Lineage: Upstream Source Tracing
-- Find all source columns that feed into a specific target column
-- Replace <database>, <schema>, <table>, <column> with actual values BEFORE executing
--
-- CONFIGURABLE: Adjust DATEADD day value to extend/shorten lookback period (default: 90 days)
-- ACCESS_HISTORY retention is 365 days maximum

-- Uses ACCESS_HISTORY to trace data sources through query patterns

WITH column_writers AS (
    -- Find queries that wrote to the target column
    SELECT 
        ah.query_id,
        ah.query_start_time,
        ah.user_name,
        base.value:objectName::STRING AS source_object,
        base.value:objectDomain::STRING AS source_type,
        src_col.value:columnName::STRING AS source_column
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
    LATERAL FLATTEN(input => objects_modified) AS modified,
    LATERAL FLATTEN(input => modified.value:columns, outer => true) AS dest_col,
    LATERAL FLATTEN(input => base_objects_accessed) AS base,
    LATERAL FLATTEN(input => base.value:columns, outer => true) AS src_col
    WHERE modified.value:objectName::STRING = '<database>.<schema>.<table>'
      AND modified.value:objectDomain::STRING IN ('Table', 'View', 'Dynamic Table', 'Materialized View')
      AND (dest_col.value:columnName::STRING = '<column>' OR dest_col.value IS NULL)
      AND base.value:objectName::STRING IS NOT NULL
      AND base.value:objectName::STRING != '<database>.<schema>.<table>'
      AND base.value:objectDomain::STRING IN ('Table', 'View', 'Dynamic Table', 'Materialized View', 'Stage')
      AND ah.query_start_time >= DATEADD(day, -90, CURRENT_TIMESTAMP())
),
source_summary AS (
    SELECT
        source_object,
        source_type,
        source_column,
        COUNT(DISTINCT query_id) AS occurrence_count,
        COUNT(DISTINCT user_name) AS user_count,
        MAX(query_start_time) AS last_seen
    FROM column_writers
    WHERE source_object IS NOT NULL
    GROUP BY source_object, source_type, source_column
)
SELECT
    '<database>.<schema>.<table>.<column>' AS target_column,
    source_object,
    source_type,
    source_column,
    occurrence_count,
    user_count,
    last_seen,
    -- Confidence in the source relationship
    CASE
        WHEN source_column IS NOT NULL AND occurrence_count >= 10 THEN 'HIGH'
        WHEN source_column IS NOT NULL AND occurrence_count >= 3 THEN 'MEDIUM'
        WHEN source_column IS NOT NULL THEN 'LOW'
        ELSE 'INFERRED'
    END AS confidence,
    -- Source tier from config/schema-patterns.yaml
    -- Replace with dynamic CASE from config file
    /* SCHEMA_TRUST_TIER:SPLIT_PART(source_object, '.', 2) */ AS source_tier
FROM source_summary
ORDER BY 
    occurrence_count DESC,
    last_seen DESC
LIMIT 50;
