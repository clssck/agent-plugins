-- Schema Root Cause Analysis (Fallback Version)
-- Identify which tables have failing quality metrics and why
-- Uses SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS() table function
-- This is the fallback for schema-root-cause-realtime.sql
--
-- NOTE: SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_RESULTS does NOT exist.
-- All DMF result queries MUST use SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS().
-- Correct columns: MEASUREMENT_TIME, TABLE_NAME, METRIC_NAME, VALUE (not metric_value)
-- The LOCAL function does NOT have column_name or threshold columns.
-- Use ARGUMENT_NAMES array to identify which column a metric applies to.

-- Replace <database> and <schema> with your target database and schema names

WITH table_list AS (
  SELECT TABLE_NAME
  FROM INFORMATION_SCHEMA.TABLES
  WHERE TABLE_CATALOG = '<database>'
    AND TABLE_SCHEMA = '<schema>'
    AND TABLE_TYPE = 'BASE TABLE'
),
latest_metrics AS (
  SELECT
    '<database>' AS database_name,
    '<schema>' AS schema_name,
    t.TABLE_NAME,
    r.METRIC_DATABASE,
    r.METRIC_SCHEMA,
    r.METRIC_NAME,
    r.VALUE AS metric_value,
    r.ARGUMENT_NAMES,
    r.MEASUREMENT_TIME
  FROM table_list t,
  LATERAL (
    SELECT *
    FROM TABLE(SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS(
      REF_ENTITY_NAME => '<database>.<schema>.' || t.TABLE_NAME,
      REF_ENTITY_DOMAIN => 'TABLE'
    ))
    QUALIFY ROW_NUMBER() OVER (PARTITION BY METRIC_DATABASE, METRIC_SCHEMA, METRIC_NAME, REFERENCE_ID ORDER BY MEASUREMENT_TIME DESC) = 1
  ) r
  WHERE r.VALUE > 0  -- Only failing metrics
)
SELECT
  database_name || '.' || schema_name || '.' || TABLE_NAME AS full_table_name,
  COALESCE(ARGUMENT_NAMES[0]::VARCHAR, '<table-level>') AS column_name,
  METRIC_DATABASE,
  METRIC_SCHEMA,
  METRIC_NAME,
  metric_value AS current_value,
  CASE
    WHEN UPPER(METRIC_DATABASE) = 'SNOWFLAKE' THEN 'SYSTEM'
    ELSE 'CUSTOM'
  END AS dmf_type,
  CASE
    WHEN metric_value > 100 THEN 'CRITICAL'
    WHEN metric_value > 10 THEN 'HIGH'
    WHEN metric_value > 0 THEN 'MEDIUM'
    ELSE 'LOW'
  END AS severity,
  CASE
    WHEN METRIC_NAME LIKE '%NULL_COUNT%' THEN 'Add NOT NULL constraint or fix upstream data pipeline'
    WHEN METRIC_NAME LIKE '%FRESHNESS%' THEN 'Check ETL schedule - data may be stale'
    WHEN METRIC_NAME LIKE '%DUPLICATE%' THEN 'Add UNIQUE constraint or deduplicate data'
    WHEN METRIC_NAME LIKE '%ROW_COUNT%' THEN 'Check if table is unexpectedly empty or too large'
    WHEN UPPER(METRIC_DATABASE) <> 'SNOWFLAKE' THEN 'Fetch custom DMF body via GET_DDL; do not paraphrase the rule'
    ELSE 'Review custom DMF logic and fix data issues'
  END AS recommended_action,
  MEASUREMENT_TIME AS measured_at
FROM latest_metrics
ORDER BY
  CASE
    WHEN metric_value > 100 THEN 1
    WHEN metric_value > 10 THEN 2
    WHEN metric_value > 0 THEN 3
    ELSE 4
  END,
  metric_value DESC;

-- Summary by table
SELECT
  TABLE_NAME,
  COUNT(*) AS failing_metric_count,
  LISTAGG(DISTINCT METRIC_NAME, ', ') WITHIN GROUP (ORDER BY METRIC_NAME) AS failing_metrics,
  MAX(CASE
    WHEN metric_value > 100 THEN 'CRITICAL'
    WHEN metric_value > 10 THEN 'HIGH'
    WHEN metric_value > 0 THEN 'MEDIUM'
    ELSE 'LOW'
  END) AS max_severity
FROM latest_metrics
GROUP BY TABLE_NAME
ORDER BY failing_metric_count DESC;
