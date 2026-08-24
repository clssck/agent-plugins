-- Schema Quality Trends
-- Analyze data quality trends over time to identify patterns and degradation
-- Uses SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS() table function
-- Requires: DMFs attached, sufficient historical data (3+ measurement runs recommended)
--
-- NOTE: SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_RESULTS does NOT exist.
-- All DMF result queries MUST use SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS().
-- Correct columns: MEASUREMENT_TIME, TABLE_NAME, METRIC_NAME, VALUE, ARGUMENT_NAMES

-- Replace <database> and <schema> with your target database and schema names

-- Gather all metrics from all tables in the schema
WITH table_list AS (
  SELECT TABLE_NAME
  FROM INFORMATION_SCHEMA.TABLES
  WHERE TABLE_CATALOG = '<database>'
    AND TABLE_SCHEMA = '<schema>'
    AND TABLE_TYPE = 'BASE TABLE'
),
all_metrics AS (
  SELECT
    '<database>' AS database_name,
    '<schema>' AS schema_name,
    t.TABLE_NAME,
    r.METRIC_NAME,
    r.VALUE,
    r.ARGUMENT_NAMES,
    r.MEASUREMENT_TIME
  FROM table_list t,
  LATERAL (
    SELECT *
    FROM TABLE(SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS(
      REF_ENTITY_NAME => '<database>.<schema>.' || t.TABLE_NAME,
      REF_ENTITY_DOMAIN => 'TABLE'
    ))
  ) r
)
-- Daily schema health trend
SELECT
  DATE_TRUNC('day', MEASUREMENT_TIME) AS measurement_date,
  database_name || '.' || schema_name AS full_schema_name,
  ROUND((COUNT_IF(VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0), 1) AS health_pct,
  COUNT_IF(VALUE = 0) AS passing_metrics,
  COUNT_IF(VALUE > 0) AS failing_metrics,
  COUNT(*) AS total_metrics,
  LAG(ROUND((COUNT_IF(VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0), 1))
    OVER (ORDER BY DATE_TRUNC('day', MEASUREMENT_TIME)) AS previous_day_health,
  ROUND(
    (COUNT_IF(VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0) -
    LAG((COUNT_IF(VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0))
      OVER (ORDER BY DATE_TRUNC('day', MEASUREMENT_TIME)),
    1
  ) AS day_over_day_change,
  CASE
    WHEN (COUNT_IF(VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0) >
         LAG((COUNT_IF(VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0))
           OVER (ORDER BY DATE_TRUNC('day', MEASUREMENT_TIME))
    THEN 'IMPROVING'
    WHEN (COUNT_IF(VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0) <
         LAG((COUNT_IF(VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0))
           OVER (ORDER BY DATE_TRUNC('day', MEASUREMENT_TIME))
    THEN 'DEGRADING'
    ELSE 'STABLE'
  END AS trend
FROM all_metrics
GROUP BY DATE_TRUNC('day', MEASUREMENT_TIME), database_name, schema_name
ORDER BY measurement_date DESC;

-- Metric-level trend (which metrics are consistently failing)
WITH table_list AS (
  SELECT TABLE_NAME
  FROM INFORMATION_SCHEMA.TABLES
  WHERE TABLE_CATALOG = '<database>'
    AND TABLE_SCHEMA = '<schema>'
    AND TABLE_TYPE = 'BASE TABLE'
),
all_metrics AS (
  SELECT
    t.TABLE_NAME,
    r.METRIC_NAME,
    r.VALUE,
    r.ARGUMENT_NAMES,
    r.MEASUREMENT_TIME
  FROM table_list t,
  LATERAL (
    SELECT *
    FROM TABLE(SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS(
      REF_ENTITY_NAME => '<database>.<schema>.' || t.TABLE_NAME,
      REF_ENTITY_DOMAIN => 'TABLE'
    ))
  ) r
  WHERE r.VALUE > 0  -- Only failing metrics
)
SELECT
  METRIC_NAME,
  TABLE_NAME,
  COALESCE(ARGUMENT_NAMES[0]::VARCHAR, '<table-level>') AS column_name,
  COUNT(DISTINCT DATE_TRUNC('day', MEASUREMENT_TIME)) AS days_failing,
  ROUND(AVG(VALUE), 2) AS avg_metric_value,
  MIN(VALUE) AS best_value,
  MAX(VALUE) AS worst_value,
  MIN(MEASUREMENT_TIME) AS first_failure,
  MAX(MEASUREMENT_TIME) AS last_failure
FROM all_metrics
GROUP BY METRIC_NAME, TABLE_NAME, ARGUMENT_NAMES[0]
HAVING days_failing > 1  -- Consistently failing (more than 1 day)
ORDER BY days_failing DESC, avg_metric_value DESC
LIMIT 20;

-- Table-level trend (which tables are most problematic over time)
WITH table_list AS (
  SELECT TABLE_NAME
  FROM INFORMATION_SCHEMA.TABLES
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
  ) r
)
SELECT
  TABLE_NAME,
  COUNT(DISTINCT DATE_TRUNC('day', MEASUREMENT_TIME)) AS days_monitored,
  COUNT(DISTINCT CASE WHEN VALUE > 0 THEN DATE_TRUNC('day', MEASUREMENT_TIME) END) AS days_with_failures,
  COUNT(DISTINCT CASE WHEN VALUE > 0 THEN METRIC_NAME END) AS distinct_failing_metrics,
  ROUND(
    (COUNT_IF(VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0),
    1
  ) AS avg_table_health,
  SUM(CASE WHEN VALUE > 0 THEN 1 ELSE 0 END) AS total_failures,
  MIN(MEASUREMENT_TIME) AS first_measurement,
  MAX(MEASUREMENT_TIME) AS last_measurement
FROM all_metrics
GROUP BY TABLE_NAME
HAVING total_failures > 0
ORDER BY days_with_failures DESC, total_failures DESC
LIMIT 20;

/*
Interpretation Guide:

Daily Trends:
- health_pct: Overall schema health percentage
- day_over_day_change: How much health changed from previous day
- trend: Whether quality is IMPROVING, DEGRADING, or STABLE

Metric-level Trends:
- days_failing: How many days this metric has been failing
- avg_metric_value: Average severity of failures
- Use this to identify chronic issues vs. one-off problems

Table-level Trends:
- days_with_failures: How many days the table had any failing metrics
- distinct_failing_metrics: Number of different metrics that failed
- High values indicate systemic table issues

Dashboard Visualization Suggestions:
1. Line chart: daily health_pct over time
2. Bar chart: top 10 tables by days_with_failures
3. Heatmap: metric_name vs. table_name with avg_metric_value as intensity
4. KPI cards: current health, avg health, trend direction
*/
