-- Schema SLA Alert
-- Create a Snowflake Alert to monitor schema health and notify on SLA violations
-- Uses SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS() table function
-- Requires: DMFs attached, CREATE ALERT privilege
--
-- NOTE: SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_RESULTS does NOT exist.
-- The alert query MUST use SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS().

-- Replace the following placeholders:
-- <alert_name>: Name for the alert (e.g., sales_schema_quality_alert)
-- <warehouse>: Warehouse to use for alert evaluation (e.g., COMPUTE_WH)
-- <database>: Target database name
-- <schema>: Target schema name
-- <health_threshold>: Minimum acceptable health percentage (e.g., 90)
-- <log_database>: Database for alert log table
-- <log_schema>: Schema for alert log table

-- IMPORTANT: This template creates a DQ_ALERT_LOG table to store alert history.
-- Ensure you have CREATE TABLE privileges in the target location.

-- Step 1: Create alert log table (run this FIRST)
CREATE TABLE IF NOT EXISTS <log_database>.<log_schema>.DQ_ALERT_LOG (
  alert_name VARCHAR,
  database_name VARCHAR,
  schema_name VARCHAR,
  health_pct FLOAT,
  failing_metrics INTEGER,
  measured_at TIMESTAMP_NTZ,
  alert_fired_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Step 2: Create the alert
CREATE OR REPLACE ALERT <alert_name>
  WAREHOUSE = <warehouse>
  SCHEDULE = '60 MINUTE'  -- Check every hour (adjust as needed)
IF (EXISTS (
  WITH table_list AS (
    SELECT TABLE_NAME
    FROM <database>.INFORMATION_SCHEMA.TABLES
    WHERE TABLE_CATALOG = '<database>'
      AND TABLE_SCHEMA = '<schema>'
      AND TABLE_TYPE = 'BASE TABLE'
  ),
  all_metrics AS (
    SELECT
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
  ),
  health_check AS (
    SELECT
      '<database>' AS database_name,
      '<schema>' AS schema_name,
      ROUND((COUNT_IF(VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0), 1) AS health_pct,
      COUNT_IF(VALUE > 0) AS failing_metrics,
      COUNT(*) AS total_metrics,
      MAX(MEASUREMENT_TIME) AS measured_at
    FROM all_metrics
  )
  SELECT 1
  FROM health_check
  WHERE health_pct < <health_threshold>
))
THEN
  -- Log the SLA violation
  INSERT INTO <log_database>.<log_schema>.DQ_ALERT_LOG (
    alert_name,
    database_name,
    schema_name,
    health_pct,
    failing_metrics,
    measured_at,
    alert_fired_at
  )
  WITH table_list AS (
    SELECT TABLE_NAME
    FROM <database>.INFORMATION_SCHEMA.TABLES
    WHERE TABLE_CATALOG = '<database>'
      AND TABLE_SCHEMA = '<schema>'
      AND TABLE_TYPE = 'BASE TABLE'
  ),
  all_metrics AS (
    SELECT
      t.TABLE_NAME,
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
    '<alert_name>',
    '<database>',
    '<schema>',
    ROUND((COUNT_IF(VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0), 1),
    COUNT_IF(VALUE > 0),
    MAX(MEASUREMENT_TIME),
    CURRENT_TIMESTAMP()
  FROM all_metrics
  WHERE (COUNT_IF(VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0) < <health_threshold>;

-- Step 3: Resume the alert (alerts are created in suspended state)
ALTER ALERT <alert_name> RESUME;

-- Step 4: Verify alert was created
SHOW ALERTS LIKE '<alert_name>';

-- Step 5: View alert history
SELECT *
FROM TABLE(INFORMATION_SCHEMA.ALERT_HISTORY(
  SCHEDULED_TIME_RANGE_START => DATEADD(day, -7, CURRENT_TIMESTAMP())
))
WHERE NAME = '<alert_name>'
ORDER BY SCHEDULED_TIME DESC;

-- Optional: Query alert log to see violations
SELECT
  alert_name,
  database_name || '.' || schema_name AS full_schema_name,
  health_pct,
  failing_metrics,
  measured_at,
  alert_fired_at
FROM <log_database>.<log_schema>.DQ_ALERT_LOG
ORDER BY alert_fired_at DESC
LIMIT 20;

-- Optional: Suspend the alert (to disable)
-- ALTER ALERT <alert_name> SUSPEND;

-- Optional: Drop the alert (to remove)
-- DROP ALERT <alert_name>;

/*
Example Configuration:

CREATE ALERT sales_schema_quality_alert
  WAREHOUSE = COMPUTE_WH
  SCHEDULE = '60 MINUTE'
IF (EXISTS (
  SELECT 1 FROM ... WHERE health_pct < 90
))
THEN
  INSERT INTO DQ_ALERT_LOG ...;

This alert will:
- Check schema health every hour using SNOWFLAKE.LOCAL
- Fire if health drops below the threshold
- Log violations to DQ_ALERT_LOG table
- Can be extended to send emails, Slack notifications, etc.
*/
