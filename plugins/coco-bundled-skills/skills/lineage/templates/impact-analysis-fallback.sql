-- Impact Analysis Fallback: Use DDL parsing when ACCOUNT_USAGE is empty
-- This handles newly created objects (within 45min-3hr latency window)
-- Replace <database>, <schema>, <table> with actual values BEFORE executing

-- Step 1: Get all views/dynamic tables in the account that might reference the target
WITH all_views AS (
    SELECT
        table_catalog AS database_name,
        table_schema AS schema_name,
        table_name,
        table_type
    FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
    WHERE table_type IN ('VIEW', 'DYNAMIC TABLE', 'MATERIALIZED VIEW')
      AND deleted IS NULL
),
-- Step 2: Check each view's DDL for references to target object
-- Note: This query structure shows the approach - actual execution requires
-- calling GET_DDL() for each view individually

-- For production use, execute this pattern:
-- 1. List all views: SELECT * FROM all_views
-- 2. For each view, run: SELECT GET_DDL('VIEW', 'DB.SCHEMA.VIEW_NAME')
-- 3. Parse DDL for references to '<database>.<schema>.<table>' or '<schema>.<table>'
-- 4. Build dependency list from matches

-- Quick check using INFORMATION_SCHEMA (current database only, real-time)
downstream_from_info_schema AS (
    SELECT
        referencing_database AS dep_database,
        referencing_schema AS dep_schema,
        referencing_object_name AS dep_object,
        referencing_object_type AS dep_type
    FROM TABLE(INFORMATION_SCHEMA.OBJECT_DEPENDENCIES(
        OBJECT_NAME => '<database>.<schema>.<table>'
    ))
    WHERE dependency_type = 'BY_NAME'
)
SELECT
    dep_database || '.' || dep_schema || '.' || dep_object AS dependent_object,
    dep_type AS object_type,
    'UNKNOWN' AS queries_last_7_days,
    'UNKNOWN' AS unique_users_7_days,
    NULL AS last_accessed,
    0 AS downstream_dependents,
    CASE
        WHEN dep_schema IN ('FINANCE', 'REVENUE', 'REPORTING', 'ANALYTICS') THEN 'CRITICAL'
        WHEN dep_type = 'DYNAMIC TABLE' THEN 'CRITICAL'
        ELSE 'MODERATE'
    END AS risk_level,
    'BY_NAME' AS dependency_type
FROM downstream_from_info_schema;
