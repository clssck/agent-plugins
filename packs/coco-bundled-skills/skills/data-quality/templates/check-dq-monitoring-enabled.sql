-- Check DMF Results Availability
-- Verify if DMF results are available for the target schema
-- Uses SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS() table function
--
-- NOTE: SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_RESULTS does NOT exist.
-- DMF results are accessed via SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS() table function.
-- For DMF credit/usage tracking, use SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_USAGE_HISTORY.

-- Replace <database> and <schema> with your target values

-- Check if DMF results are available by sampling tables
WITH table_list AS (
    SELECT TABLE_NAME
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_CATALOG = '<database>'
      AND TABLE_SCHEMA = '<schema>'
      AND TABLE_TYPE = 'BASE TABLE'
    LIMIT 5  -- Sample a few tables for speed
),
sample_results AS (
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
    '<database>' AS database_name,
    '<schema>' AS schema_name,
    COUNT(DISTINCT TABLE_NAME) AS tables_with_results,
    COUNT(DISTINCT METRIC_NAME) AS distinct_metrics,
    COUNT(DISTINCT DATE_TRUNC('day', MEASUREMENT_TIME)) AS days_of_data,
    MIN(MEASUREMENT_TIME) AS oldest_result,
    MAX(MEASUREMENT_TIME) AS newest_result,
    COUNT(*) AS total_measurements,
    CASE
        WHEN COUNT(*) = 0 THEN 'NO_DATA'
        WHEN COUNT(DISTINCT DATE_TRUNC('day', MEASUREMENT_TIME)) = 1 THEN 'LIMITED'
        ELSE 'AVAILABLE'
    END AS data_availability
FROM sample_results;

-- Check DMF usage/credit history (separate from metric results)
SELECT
    DATABASE_NAME,
    SCHEMA_NAME,
    COUNT(DISTINCT TABLE_NAME) AS tables_tracked,
    COUNT(DISTINCT DATE_TRUNC('day', START_TIME)) AS days_of_data,
    MIN(START_TIME) AS oldest_record,
    MAX(END_TIME) AS newest_record,
    ROUND(SUM(CREDITS_USED), 4) AS total_credits_used
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_USAGE_HISTORY
WHERE DATABASE_NAME = '<database>'
GROUP BY DATABASE_NAME, SCHEMA_NAME
ORDER BY SCHEMA_NAME;

/*
Interpretation:

data_availability values:
  NO_DATA   → DMFs haven't run yet or no DMFs are attached
              → Run preflight-check.sql to diagnose
              → Wait for DMFs to execute (based on schedule)

  LIMITED   → Only 1 day of data available
              → Health check works
              → Regression detection needs 2+ measurement times
              → Trend analysis needs 3+ days

  AVAILABLE → Sufficient historical data
              → All workflows are available

IMPORTANT - Correct View/Function Locations:
  DMF Metric Results: SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS()  (table function)
  DMF Credit Usage:   SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_USAGE_HISTORY  (view)
  DMF References:     INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES()  (table function)
                      SNOWFLAKE.ACCOUNT_USAGE.DATA_METRIC_FUNCTION_REFERENCES  (view)

  *** SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_RESULTS does NOT exist ***

Prerequisites for Different Queries:

| Query Type                    | Requires DMFs | Requires Results | Min History |
|-------------------------------|---------------|------------------|-------------|
| schema-health-snapshot.sql    | Yes           | Yes              | 1 run       |
| schema-root-cause.sql         | Yes           | Yes              | 1 run       |
| schema-regression-detection.sql| Yes          | Yes              | 2 runs      |
| schema-quality-trends.sql     | Yes           | Yes              | 3+ runs     |
| schema-sla-alert.sql          | Yes           | Yes              | 1 run       |
| check-dmf-status.sql          | Yes           | No               | N/A         |
| preflight-check.sql           | No            | No               | N/A         |
*/
