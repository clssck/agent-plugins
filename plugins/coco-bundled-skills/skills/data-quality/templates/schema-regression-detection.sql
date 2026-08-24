-- Schema Regression Detection
-- Compare current quality vs. previous run to detect degradation
-- Uses SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS() table function
-- Requires: DMFs attached, at least 2 historical measurement times
--
-- NOTE: SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_RESULTS does NOT exist.
-- All DMF result queries MUST use SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS().
-- Correct columns: MEASUREMENT_TIME, TABLE_NAME, METRIC_NAME, VALUE, REFERENCE_ID, ARGUMENT_NAMES

-- Replace <database> and <schema> with your target database and schema names

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
    r.REFERENCE_ID,
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
),
measurement_times AS (
  SELECT DISTINCT MEASUREMENT_TIME
  FROM all_metrics
  ORDER BY MEASUREMENT_TIME DESC
  LIMIT 2
),
current_run AS (
  SELECT TABLE_NAME, METRIC_NAME, REFERENCE_ID, VALUE, ARGUMENT_NAMES, MEASUREMENT_TIME
  FROM all_metrics
  WHERE MEASUREMENT_TIME = (SELECT MAX(MEASUREMENT_TIME) FROM measurement_times)
),
previous_run AS (
  SELECT TABLE_NAME, METRIC_NAME, REFERENCE_ID, VALUE, ARGUMENT_NAMES, MEASUREMENT_TIME
  FROM all_metrics
  WHERE MEASUREMENT_TIME = (SELECT MIN(MEASUREMENT_TIME) FROM measurement_times)
)
-- Overall schema health change
SELECT
  'OVERALL SCHEMA HEALTH' AS analysis_type,
  ROUND((COUNT_IF(p.VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0), 1) AS previous_health_pct,
  ROUND((COUNT_IF(c.VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0), 1) AS current_health_pct,
  ROUND(
    (COUNT_IF(c.VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0) -
    (COUNT_IF(p.VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0),
    1
  ) AS health_change,
  CASE
    WHEN (COUNT_IF(c.VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0) >
         (COUNT_IF(p.VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0)
    THEN 'IMPROVED'
    WHEN (COUNT_IF(c.VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0) <
         (COUNT_IF(p.VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0)
    THEN 'DEGRADED'
    ELSE 'STABLE'
  END AS trend,
  MAX(p.MEASUREMENT_TIME) AS previous_run_time,
  MAX(c.MEASUREMENT_TIME) AS current_run_time
FROM current_run c
FULL OUTER JOIN previous_run p
  ON c.TABLE_NAME = p.TABLE_NAME
  AND c.METRIC_NAME = p.METRIC_NAME
  AND c.REFERENCE_ID = p.REFERENCE_ID
GROUP BY analysis_type;

-- Tables with quality regressions (metrics that got worse)
SELECT
  c.TABLE_NAME,
  COALESCE(c.ARGUMENT_NAMES[0]::VARCHAR, '<table-level>') AS column_name,
  c.METRIC_NAME,
  p.VALUE AS previous_value,
  c.VALUE AS current_value,
  c.VALUE - p.VALUE AS absolute_change,
  CASE
    WHEN p.VALUE = 0 THEN NULL
    ELSE ROUND(((c.VALUE - p.VALUE) * 100.0) / p.VALUE, 1)
  END AS pct_change,
  CASE
    WHEN c.VALUE - p.VALUE > p.VALUE THEN 'CRITICAL'
    WHEN c.VALUE - p.VALUE > p.VALUE * 0.5 THEN 'HIGH'
    WHEN c.VALUE - p.VALUE > 0 THEN 'MEDIUM'
    ELSE 'LOW'
  END AS severity,
  p.MEASUREMENT_TIME AS previous_run_time,
  c.MEASUREMENT_TIME AS current_run_time
FROM current_run c
JOIN previous_run p
  ON c.TABLE_NAME = p.TABLE_NAME
  AND c.METRIC_NAME = p.METRIC_NAME
  AND c.REFERENCE_ID = p.REFERENCE_ID
WHERE c.VALUE > p.VALUE  -- Quality degraded (higher metric value = worse)
ORDER BY
  c.VALUE - p.VALUE DESC,
  c.TABLE_NAME;

-- New failures (metrics that were passing, now failing)
SELECT
  c.TABLE_NAME,
  COALESCE(c.ARGUMENT_NAMES[0]::VARCHAR, '<table-level>') AS column_name,
  c.METRIC_NAME,
  p.VALUE AS previous_value,
  c.VALUE AS current_value,
  'NEW_FAILURE' AS status,
  c.MEASUREMENT_TIME AS failed_at
FROM current_run c
JOIN previous_run p
  ON c.TABLE_NAME = p.TABLE_NAME
  AND c.METRIC_NAME = p.METRIC_NAME
  AND c.REFERENCE_ID = p.REFERENCE_ID
WHERE p.VALUE = 0  -- Was passing
  AND c.VALUE > 0  -- Now failing
ORDER BY c.TABLE_NAME;

-- Summary by table
SELECT
  c.TABLE_NAME,
  COUNT(*) AS total_metrics,
  COUNT_IF(c.VALUE > p.VALUE) AS degraded_metrics,
  COUNT_IF(p.VALUE = 0 AND c.VALUE > 0) AS new_failures,
  COUNT_IF(c.VALUE < p.VALUE) AS improved_metrics,
  ROUND(
    (COUNT_IF(c.VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0) -
    (COUNT_IF(p.VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0),
    1
  ) AS health_change_pct
FROM current_run c
FULL OUTER JOIN previous_run p
  ON c.TABLE_NAME = p.TABLE_NAME
  AND c.METRIC_NAME = p.METRIC_NAME
  AND c.REFERENCE_ID = p.REFERENCE_ID
WHERE c.TABLE_NAME IS NOT NULL
GROUP BY c.TABLE_NAME
HAVING degraded_metrics > 0 OR new_failures > 0
ORDER BY new_failures DESC, degraded_metrics DESC;
