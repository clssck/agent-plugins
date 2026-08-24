-- Column Change Detection
-- Detect schema changes affecting a specific column
-- Replace <database>, <schema>, <table>, <column> with actual values BEFORE executing
--
-- CONFIGURABLE: Adjust DATEADD day values to extend/shorten lookback periods
-- - DDL history lookback: 30 days (default)
-- - Usage stats lookback: 30 days (default)
-- QUERY_HISTORY retention is 365 days maximum

-- Check current column definition and recent changes

WITH current_column AS (
    -- Get current column metadata
    SELECT
        c.table_catalog AS database_name,
        c.table_schema AS schema_name,
        c.table_name,
        c.column_name,
        c.ordinal_position,
        c.data_type,
        c.character_maximum_length,
        c.numeric_precision,
        c.numeric_scale,
        c.is_nullable,
        c.column_default,
        c.comment
    FROM SNOWFLAKE.ACCOUNT_USAGE.COLUMNS c
    WHERE c.table_catalog = '<database>'
      AND c.table_schema = '<schema>'
      AND c.table_name = '<table>'
      AND c.column_name = '<column>'
      AND c.deleted IS NULL
),
table_history AS (
    -- Get table modification history
    SELECT
        t.table_catalog,
        t.table_schema,
        t.table_name,
        t.created,
        t.last_altered,
        t.last_ddl,
        t.table_owner
    FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES t
    WHERE t.table_catalog = '<database>'
      AND t.table_schema = '<schema>'
      AND t.table_name = '<table>'
      AND t.deleted IS NULL
),
recent_ddl_queries AS (
    -- Find DDL queries that modified the table
    SELECT
        qh.query_id,
        qh.query_text,
        qh.user_name,
        qh.start_time,
        qh.query_type
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY qh
    WHERE qh.query_type IN ('ALTER_TABLE', 'ALTER', 'CREATE_TABLE_AS_SELECT')
      AND UPPER(qh.query_text) LIKE '%<table>%'
      AND (UPPER(qh.query_text) LIKE '%<column>%' OR UPPER(qh.query_text) LIKE '%ALTER%COLUMN%')
      AND qh.start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
    ORDER BY qh.start_time DESC
    LIMIT 10
),
column_stats AS (
    -- Check if column is used in recent queries
    SELECT
        COUNT(DISTINCT ah.query_id) AS read_count_30d,
        COUNT(DISTINCT ah.user_name) AS users_30d,
        MAX(ah.query_start_time) AS last_read
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
    LATERAL FLATTEN(input => base_objects_accessed) AS base,
    LATERAL FLATTEN(input => base.value:columns, outer => true) AS col
    WHERE base.value:objectName::STRING = '<database>.<schema>.<table>'
      AND col.value:columnName::STRING = '<column>'
      AND ah.query_start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
)
SELECT 
    '=== COLUMN DEFINITION ===' AS section,
    cc.column_name,
    cc.data_type,
    cc.numeric_precision,
    cc.numeric_scale,
    cc.is_nullable,
    cc.comment AS column_comment
FROM current_column cc

UNION ALL

SELECT 
    '=== TABLE HISTORY ===' AS section,
    th.table_name AS column_name,
    'Created: ' || th.created::STRING AS data_type,
    NULL AS numeric_precision,
    NULL AS numeric_scale,
    'Last Altered: ' || th.last_altered::STRING AS is_nullable,
    'Owner: ' || th.table_owner AS column_comment
FROM table_history th

UNION ALL

SELECT 
    '=== USAGE STATS ===' AS section,
    'Read Count (30d)' AS column_name,
    cs.read_count_30d::STRING AS data_type,
    NULL AS numeric_precision,
    NULL AS numeric_scale,
    'Users: ' || cs.users_30d::STRING AS is_nullable,
    'Last Read: ' || cs.last_read::STRING AS column_comment
FROM column_stats cs

UNION ALL

SELECT 
    '=== RECENT DDL ===' AS section,
    ddl.query_type AS column_name,
    ddl.user_name AS data_type,
    NULL AS numeric_precision,
    NULL AS numeric_scale,
    ddl.start_time::STRING AS is_nullable,
    LEFT(ddl.query_text, 200) AS column_comment
FROM recent_ddl_queries ddl;
