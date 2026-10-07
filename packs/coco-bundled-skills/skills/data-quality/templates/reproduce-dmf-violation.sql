-- Reproduce / explain a DMF violation (READ-ONLY)
--
-- CRITICAL RULES:
-- 1. The authoritative violation count is VALUE from
--    SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS() and/or
--    SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_EXPECTATION_STATUS.
--    NEVER report a LIMIT-capped preview size as the total.
-- 2. Example rows are OPTIONAL and must be labeled as examples of N total.
-- 3. For custom DMFs (METRIC_DATABASE <> 'SNOWFLAKE'), fetch the body with
--    GET_DDL — do NOT paraphrase the predicate from the metric name.
--
-- Replace placeholders: <database>, <schema>, <table>, <metric_database>,
-- <metric_schema>, <metric_name>, <fq_metric_name>
--
-- IDENTIFIER SAFETY (fill these from RESULTS / EXPECTATION_STATUS columns only):
--   - <database>, <schema>, <table>, <metric_database>, <metric_schema>,
--     <metric_name> must each match ^[A-Za-z_][A-Za-z0-9_$]*$ (unquoted Snowflake
--     identifier). Reject / do not substitute any other string.
--   - <fq_metric_name> must be exactly three such identifiers joined by '.'
--     (e.g. DB.SCHEMA.METRIC). Do not accept quotes, spaces, or SQL fragments.
--   - Prefer binding values taken from monitoring views rather than free-form
--     user text when populating this template.

-- ---------------------------------------------------------------------------
-- A. Authoritative measurement (always run first; report VALUE as the count)
-- ---------------------------------------------------------------------------
SELECT
    TABLE_DATABASE,
    TABLE_SCHEMA,
    TABLE_NAME,
    METRIC_DATABASE,
    METRIC_SCHEMA,
    METRIC_NAME,
    VALUE AS violation_count_from_measurement,
    MEASUREMENT_TIME,
    ARGUMENT_NAMES
FROM TABLE(SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS(
    REF_ENTITY_NAME => '<database>.<schema>.<table>',
    REF_ENTITY_DOMAIN => 'TABLE'
))
WHERE UPPER(METRIC_NAME) = UPPER('<metric_name>')
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY METRIC_DATABASE, METRIC_SCHEMA, METRIC_NAME
    ORDER BY MEASUREMENT_TIME DESC
) = 1;

-- ---------------------------------------------------------------------------
-- B. Expectation status (when the incident is expectation-backed — preferred)
--    Use expectation_violated + value + expectation_expression from this view.
-- ---------------------------------------------------------------------------
SELECT
    table_database,
    table_schema,
    table_name,
    metric_name,
    expectation_name,
    expectation_expression,
    value AS measured_value,
    expectation_violated,
    measurement_time
FROM SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_EXPECTATION_STATUS
WHERE table_database = '<database>'
  AND table_schema = '<schema>'
  AND UPPER(table_name) = UPPER('<table>')
  AND UPPER(metric_name) = UPPER('<metric_name>')
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY expectation_name ORDER BY measurement_time DESC
) = 1;

-- ---------------------------------------------------------------------------
-- C. Custom DMF only: fetch the exact function body (never invent the SQL)
-- ---------------------------------------------------------------------------
-- REQUIRED for CUSTOM DMFs (METRIC_DATABASE <> 'SNOWFLAKE').
-- Skip only when METRIC_DATABASE = 'SNOWFLAKE' (system DMF — semantics are known).
-- SELECT GET_DDL('FUNCTION', '<fq_metric_name>');
-- Example: SELECT GET_DDL('FUNCTION', 'ANALYTICS.DQ.UNPOPULAR_VIDEO_COUNT');

-- Optional: re-evaluate expectations without inventing a predicate
-- SELECT *
-- FROM TABLE(SYSTEM$EVALUATE_DATA_QUALITY_EXPECTATIONS(
--     REF_ENTITY_NAME => '<database>.<schema>.<table>',
--     REF_ENTITY_DOMAIN => 'TABLE'
-- ));

-- ---------------------------------------------------------------------------
-- D. Optional example rows ONLY (never use row count here as the total)
--    Prefer SYSTEM$DATA_METRIC_SCAN when the metric supports it.
--    Otherwise, apply the VERBATIM predicate from GET_DDL with a small LIMIT.
--    Label output: "Example rows (showing K of <violation_count_from_measurement>)".
-- ---------------------------------------------------------------------------
-- SELECT * FROM TABLE(SYSTEM$DATA_METRIC_SCAN(
--     REF_ENTITY_NAME => '<database>.<schema>.<table>',
--     METRIC_NAME => '<metric_database>.<metric_schema>.<metric_name>'
-- ))
-- LIMIT 5;
--
-- -- Custom DMF fallback (predicate must come from GET_DDL, not paraphrased):
-- SELECT *
-- FROM <database>.<schema>.<table>
-- WHERE <verbatim_predicate_from_get_ddl>
-- LIMIT 5;
