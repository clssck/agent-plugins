-- ============================================================
-- CHECK DMF COVERAGE
-- Assess Data Metric Function attachment and measurement coverage
-- ============================================================

-- Check 1: Count distinct DMFs in the account (system + custom)
-- Shows what DMFs exist and whether they are system or custom
SELECT
    metric_database,
    metric_schema,
    metric_name,
    CASE
        WHEN metric_database = 'SNOWFLAKE' AND metric_schema = 'CORE' THEN 'SYSTEM'
        ELSE 'CUSTOM'
    END AS dmf_type,
    COUNT(DISTINCT ref_entity_name) AS tables_attached
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_METRIC_FUNCTION_REFERENCES
WHERE deleted IS NULL
GROUP BY 1, 2, 3, 4
ORDER BY tables_attached DESC;

-- Check 2: Count distinct tables/views with DMFs attached
-- Grouped by database to show coverage distribution
SELECT
    ref_database_name AS database_name,
    ref_schema_name AS schema_name,
    COUNT(DISTINCT ref_entity_name) AS tables_with_dmfs,
    COUNT(*) AS total_dmf_associations,
    COUNT(DISTINCT metric_name) AS distinct_dmfs_used
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_METRIC_FUNCTION_REFERENCES
WHERE deleted IS NULL
GROUP BY 1, 2
ORDER BY tables_with_dmfs DESC;

-- Check 3: Recent DMF measurement results (last 7 days)
-- Confirms DMFs are actively running and producing results
SELECT
    table_database,
    table_schema,
    COUNT(DISTINCT table_name) AS tables_measured,
    COUNT(DISTINCT metric_name) AS dmfs_executed,
    COUNT(*) AS total_measurements,
    MIN(measurement_time) AS earliest_measurement,
    MAX(measurement_time) AS latest_measurement
FROM SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS
WHERE measurement_time >= DATEADD('day', -7, CURRENT_TIMESTAMP())
GROUP BY 1, 2
ORDER BY total_measurements DESC;

-- Check 4: Summary of DMF coverage across all databases
-- For cross-referencing with popular databases
SELECT
    ref_database_name AS database_name,
    COUNT(DISTINCT ref_entity_name) AS tables_with_dmfs
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_METRIC_FUNCTION_REFERENCES
WHERE deleted IS NULL
GROUP BY 1
ORDER BY tables_with_dmfs DESC;
