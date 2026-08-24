-- Check DMF Status (SIMPLIFIED)
-- Verify that Data Metric Functions (DMFs) are attached to tables and functioning
-- Use this as a prerequisite check before running schema health queries

-- Replace <database> and <schema> with your target database and schema names

-- Get all tables in the schema
WITH all_tables AS (
    SELECT TABLE_NAME
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_CATALOG = '<database>'
      AND TABLE_SCHEMA = '<schema>'
      AND TABLE_TYPE = 'BASE TABLE'
),
-- Get DMF references for each table
dmf_refs AS (
    SELECT
        '<database>' AS database_name,
        '<schema>' AS schema_name,
        t.TABLE_NAME,
        r.METRIC_NAME,
        r.SCHEDULE,
        r.SCHEDULE_STATUS
    FROM all_tables t,
    LATERAL (
        SELECT *
        FROM TABLE(INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES(
            REF_ENTITY_NAME => '<database>.<schema>.' || t.TABLE_NAME,
            REF_ENTITY_DOMAIN => 'TABLE'
        ))
    ) r
)
-- Summary: Overall DMF coverage
SELECT
    COUNT(DISTINCT TABLE_NAME) AS tables_with_dmfs,
    (SELECT COUNT(*) FROM all_tables) AS total_tables_in_schema,
    COUNT(*) AS total_dmfs,
    COUNT(DISTINCT METRIC_NAME) AS distinct_metrics,
    LISTAGG(DISTINCT METRIC_NAME, ', ') WITHIN GROUP (ORDER BY METRIC_NAME) AS all_metrics_used
FROM dmf_refs;

-- Summary: Count of DMFs by table
SELECT
    database_name,
    schema_name,
    TABLE_NAME,
    COUNT(*) AS dmf_count,
    LISTAGG(DISTINCT METRIC_NAME, ', ') WITHIN GROUP (ORDER BY METRIC_NAME) AS metrics_attached,
    MAX(SCHEDULE) AS schedule_setting
FROM dmf_refs
GROUP BY database_name, schema_name, TABLE_NAME
ORDER BY dmf_count DESC;

-- Check for tables WITHOUT DMFs
SELECT
    '<database>' AS database_name,
    '<schema>' AS schema_name,
    t.TABLE_NAME,
    'NO DMFs ATTACHED' AS status
FROM all_tables t
WHERE NOT EXISTS (
    SELECT 1 FROM dmf_refs d
    WHERE d.TABLE_NAME = t.TABLE_NAME
)
ORDER BY t.TABLE_NAME;

/*
Interpretation:

If total_dmfs = 0:
- No DMFs are attached to any tables in the schema
- Schema health queries will return empty results
- User needs to attach DMFs before monitoring quality

Next Steps:
1. If no DMFs found: Attach DMFs using ALTER TABLE/SCHEMA commands
2. If schedule is NULL: Set DATA_METRIC_SCHEDULE at schema or table level
3. If DMFs are attached: Proceed with schema health queries

Example DMF Attachment:
-- Set schedule
ALTER SCHEMA <database>.<schema>
  SET DATA_METRIC_SCHEDULE = 'TRIGGER_ON_CHANGES';

-- Attach common DMFs
ALTER TABLE <database>.<schema>.<table>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.ROW_COUNT ON (),
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT ON (column_name);
*/
