-- Schema Health Snapshot (Fallback Version)
-- Calculate overall schema health score and identify failing metrics count
-- Uses SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS() table function
-- This is the fallback for schema-health-snapshot-realtime.sql
--
-- NOTE: SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_RESULTS does NOT exist.
-- All DMF result queries MUST use SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS().

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
    r.METRIC_NAME,
    r.VALUE,
    r.MEASUREMENT_TIME
  FROM table_list t,
  LATERAL (
    SELECT *
    FROM TABLE(SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS(
      REF_ENTITY_NAME => '<database>.<schema>.' || t.TABLE_NAME,
      REF_ENTITY_DOMAIN => 'TABLE'
    ))
    QUALIFY ROW_NUMBER() OVER (PARTITION BY METRIC_NAME ORDER BY MEASUREMENT_TIME DESC) = 1
  ) r
)
SELECT
  database_name,
  schema_name,
  ROUND((COUNT_IF(VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0), 1) AS health_pct,
  COUNT_IF(VALUE = 0) AS passing_metrics,
  COUNT_IF(VALUE > 0) AS failing_metrics,
  COUNT(*) AS total_metrics,
  COUNT(DISTINCT TABLE_NAME) AS tables_monitored,
  COUNT(DISTINCT CASE WHEN VALUE > 0 THEN TABLE_NAME END) AS tables_with_issues,
  MAX(MEASUREMENT_TIME) AS measured_at
FROM latest_metrics
GROUP BY database_name, schema_name;

-- Interpretation:
-- health_pct = 100%: All metrics passing (perfect health)
-- health_pct = 90-99%: Minor issues (good health)
-- health_pct = 75-89%: Moderate issues (needs attention)
-- health_pct < 75%: Significant issues (critical)
