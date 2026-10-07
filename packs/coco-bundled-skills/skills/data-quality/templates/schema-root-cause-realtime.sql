-- Schema Root Cause Analysis (Real-Time Version - SIMPLIFIED)
-- Identify which tables/columns are failing and why
-- NO LATENCY: Uses SNOWFLAKE.LOCAL table functions for instant results

-- Replace <database> and <schema> with your target database and schema names

-- Get list of tables and query their DMF results
WITH table_list AS (
    SELECT TABLE_NAME
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_CATALOG = '<database>'
      AND TABLE_SCHEMA = '<schema>'
      AND TABLE_TYPE = 'BASE TABLE'
),
-- Get DMF results for each table
all_metrics AS (
    SELECT
        '<database>' AS database_name,
        '<schema>' AS schema_name,
        t.TABLE_NAME,
        r.METRIC_DATABASE,
        r.METRIC_SCHEMA,
        r.METRIC_NAME,
        r.VALUE AS metric_value,
        r.MEASUREMENT_TIME,
        r.ARGUMENT_NAMES
    FROM table_list t,
    LATERAL (
        SELECT *
        FROM TABLE(SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS(
            REF_ENTITY_NAME => '<database>.<schema>.' || t.TABLE_NAME,
            REF_ENTITY_DOMAIN => 'TABLE'
        ))
        QUALIFY ROW_NUMBER() OVER (PARTITION BY METRIC_DATABASE, METRIC_SCHEMA, METRIC_NAME ORDER BY MEASUREMENT_TIME DESC) = 1
    ) r
    WHERE r.VALUE > 0  -- Only get failing metrics
)
-- Show failing metrics with recommendations
-- failure_count = authoritative MEASUREMENT value — never replace with a LIMIT sample size
SELECT
    database_name,
    schema_name,
    TABLE_NAME,
    METRIC_DATABASE,
    METRIC_SCHEMA,
    METRIC_NAME,
    metric_value AS failure_count,
    MEASUREMENT_TIME AS measured_at,
    ARGUMENT_NAMES,
    CASE
        WHEN UPPER(METRIC_DATABASE) = 'SNOWFLAKE' THEN 'SYSTEM'
        ELSE 'CUSTOM'
    END AS dmf_type,
    CASE
        WHEN METRIC_NAME LIKE '%NULL_COUNT%' THEN 'Column contains null values'
        WHEN METRIC_NAME LIKE '%DUPLICATE%' THEN 'Duplicate values detected'
        WHEN METRIC_NAME LIKE '%FRESHNESS%' THEN 'Data is stale'
        WHEN METRIC_NAME LIKE '%ROW_COUNT%' THEN 'Unexpected row count'
        WHEN UPPER(METRIC_DATABASE) <> 'SNOWFLAKE' THEN 'Custom DMF threshold exceeded — see GET_DDL for rule body'
        ELSE 'Quality check failed'
    END AS issue_type,
    CASE
        WHEN METRIC_NAME LIKE '%NULL_COUNT%' THEN 'Add NOT NULL constraint or fix upstream data'
        WHEN METRIC_NAME LIKE '%DUPLICATE%' THEN 'Add UNIQUE constraint or deduplicate data'
        WHEN METRIC_NAME LIKE '%FRESHNESS%' THEN 'Check ETL schedule and pipeline'
        WHEN METRIC_NAME LIKE '%ROW_COUNT%' THEN 'Verify data load process'
        WHEN UPPER(METRIC_DATABASE) <> 'SNOWFLAKE' THEN 'Fetch custom DMF body via GET_DDL; do not paraphrase the rule'
        ELSE 'Investigate data quality rules'
    END AS recommendation
FROM all_metrics
ORDER BY
    TABLE_NAME,
    metric_value DESC,
    METRIC_NAME;

-- Summary: Tables with most issues
SELECT
    database_name,
    schema_name,
    TABLE_NAME,
    COUNT(*) AS failing_metrics,
    SUM(metric_value) AS total_failure_count,
    LISTAGG(METRIC_NAME, ', ') WITHIN GROUP (ORDER BY METRIC_NAME) AS failed_checks,
    MAX(MEASUREMENT_TIME) AS measured_at
FROM all_metrics
GROUP BY database_name, schema_name, TABLE_NAME
ORDER BY failing_metrics DESC, total_failure_count DESC;
