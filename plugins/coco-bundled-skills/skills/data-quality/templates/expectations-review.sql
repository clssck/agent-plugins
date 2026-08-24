-- DMF Expectations Review
-- Shows all DMF expectations for a schema with their current pass/fail status.
-- Also surfaces DMFs with no expectations (attached but no threshold defined).
--
-- Replace <database> and <schema> with target database and schema names.
--
-- Primary data source: SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_EXPECTATION_STATUS (view)
-- Provides expectation_violated, value, expectation_expression, table/metric columns, measurement_time.
-- Access requires DATA_QUALITY_MONITORING_VIEWER (or ADMIN) application role.
-- See: https://docs.snowflake.com/en/sql-reference/local/data_quality_monitoring_expectation_status

-- Step 1: Latest expectation status per (table, metric, expectation) from the view
WITH latest_expectation_status AS (
    SELECT
        table_database,
        table_schema,
        table_name,
        metric_name,
        expectation_name,
        expectation_expression,
        value AS current_value,
        measurement_time AS last_measured,
        expectation_violated
    FROM SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_EXPECTATION_STATUS
    WHERE table_database = '<database>'
      AND table_schema = '<schema>'
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY table_name, metric_name, expectation_name
        ORDER BY measurement_time DESC
    ) = 1
),

-- Step 2: All attached DMFs in the schema (to find those with no expectations)
attached_dmfs AS (
    SELECT DISTINCT
        t.TABLE_NAME,
        r.METRIC_NAME
    FROM <database>.INFORMATION_SCHEMA.TABLES t,
    LATERAL (
        SELECT METRIC_NAME
        FROM TABLE(INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES(
            REF_ENTITY_NAME => '<database>.<schema>.' || t.TABLE_NAME,
            REF_ENTITY_DOMAIN => 'TABLE'
        ))
    ) r
    WHERE t.TABLE_SCHEMA = '<schema>'
      AND t.TABLE_TYPE = 'BASE TABLE'
)

-- Final: Join attached DMFs to latest expectation status; derive pass/fail from expectation_violated
SELECT
    COALESCE(ad.TABLE_NAME, e.table_name) AS table_name,
    COALESCE(ad.METRIC_NAME, e.metric_name) AS metric_name,
    e.expectation_name,
    e.expectation_expression,
    e.current_value,
    e.last_measured,
    CASE
        WHEN e.expectation_violated IS NULL AND e.expectation_name IS NULL
            THEN '— NO EXPECTATION'
        WHEN e.expectation_violated IS NULL
            THEN '— EVALUATION FAILED (NULL)'
        WHEN e.expectation_violated = TRUE
            THEN '❌ FAIL'
        WHEN e.expectation_violated = FALSE
            THEN '✅ PASS'
        ELSE '— NO EXPECTATION'
    END AS expectation_status
FROM attached_dmfs ad
LEFT JOIN latest_expectation_status e
    ON UPPER(ad.TABLE_NAME) = UPPER(e.table_name)
    AND ad.METRIC_NAME = e.metric_name
ORDER BY
    CASE
        WHEN e.expectation_violated = TRUE THEN 0
        WHEN e.expectation_violated IS NULL AND e.expectation_name IS NULL THEN 1
        ELSE 2
    END,
    COALESCE(ad.TABLE_NAME, e.table_name),
    COALESCE(ad.METRIC_NAME, e.metric_name);

-- Summary: count of passing, failing, no-expectation, and evaluation-failed
-- (Self-contained: reuses same CTEs so this can run as a second statement if needed.)
WITH latest_expectation_status AS (
    SELECT table_database, table_schema, table_name, metric_name, expectation_name, expectation_expression, value, measurement_time, expectation_violated
    FROM SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_EXPECTATION_STATUS
    WHERE table_database = '<database>' AND table_schema = '<schema>'
    QUALIFY ROW_NUMBER() OVER (PARTITION BY table_name, metric_name, expectation_name ORDER BY measurement_time DESC) = 1
),
attached_dmfs AS (
    SELECT DISTINCT t.TABLE_NAME, r.METRIC_NAME
    FROM <database>.INFORMATION_SCHEMA.TABLES t,
    LATERAL (SELECT METRIC_NAME FROM TABLE(INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES(REF_ENTITY_NAME => '<database>.<schema>.' || t.TABLE_NAME, REF_ENTITY_DOMAIN => 'TABLE'))) r
    WHERE t.TABLE_SCHEMA = '<schema>' AND t.TABLE_TYPE = 'BASE TABLE'
)
SELECT
    COUNT(CASE WHEN expectation_status LIKE '✅%' THEN 1 END) AS passing,
    COUNT(CASE WHEN expectation_status LIKE '❌%' THEN 1 END) AS failing,
    COUNT(CASE WHEN expectation_status LIKE '— NO%' THEN 1 END) AS no_expectation,
    COUNT(CASE WHEN expectation_status LIKE '%EVALUATION FAILED%' THEN 1 END) AS evaluation_failed,
    COUNT(*) AS total_monitors
FROM (
    SELECT
        CASE
            WHEN e.expectation_violated IS NULL AND e.expectation_name IS NULL THEN '— NO EXPECTATION'
            WHEN e.expectation_violated IS NULL THEN '— EVALUATION FAILED (NULL)'
            WHEN e.expectation_violated = TRUE THEN '❌ FAIL'
            WHEN e.expectation_violated = FALSE THEN '✅ PASS'
            ELSE '— NO EXPECTATION'
        END AS expectation_status
    FROM attached_dmfs ad
    LEFT JOIN latest_expectation_status e ON UPPER(ad.TABLE_NAME) = UPPER(e.table_name) AND ad.METRIC_NAME = e.metric_name
) summary;

/*
Query 1 columns:
  TABLE_NAME             — table name
  METRIC_NAME            — DMF metric (including custom DMFs)
  EXPECTATION_NAME       — expectation name (NULL if none set)
  EXPECTATION_EXPRESSION — threshold expression (NULL if none set)
  CURRENT_VALUE          — most recent DMF measurement value
  LAST_MEASURED          — timestamp of most recent measurement
  EXPECTATION_STATUS     — ✅ PASS | ❌ FAIL | — NO EXPECTATION | — EVALUATION FAILED (NULL)

Query 2 columns:
  PASSING                — count of monitors currently passing their expectation
  FAILING                — count of monitors currently failing their expectation
  NO_EXPECTATION         — count of monitors with no threshold defined
  EVALUATION_FAILED      — count where expectation evaluation returned NULL
  TOTAL_MONITORS         — total attached DMF count

Note: The view only returns rows for DMFs that have expectations and have been run.
Attached DMFs with no expectation appear via left join from attached_dmfs (status: — NO EXPECTATION).
*/
