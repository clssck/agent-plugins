-- Within Group DMF Operations (Grouped Monitoring)
-- Feature parameter: FEATURE_DATA_QUALITY_WITHIN_GROUP
--
-- This file is a REFERENCE MENU of variant statements — do NOT execute every
-- statement in order. Pick the section(s) that match the user's request,
-- substitute placeholders, and execute only the chosen statements.
--
-- Replace <database>, <schema>, <table_name> with target names.
-- Replace <metric_column>, <group_by_column> with user's chosen columns.
-- Replace <numeric_limit> with desired GROUP LIMIT value.
-- Replace <expectation_name> and <condition> with user's expectation definition.
--
-- Compatible system DMFs: NULL_COUNT, DUPLICATE_COUNT, ACCEPTED_VALUES, ROW_COUNT
-- NOT compatible: FRESHNESS, ANOMALY_DETECTION, REFERENTIAL_INTEGRITY_COUNT, schema-level

-- =============================================================================
-- 1. ADD DMF WITH WITHIN GROUP
-- =============================================================================

-- NULL_COUNT grouped by a single column
ALTER TABLE <database>.<schema>.<table_name>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT
    ON (<metric_column>)
    WITHIN GROUP (<group_by_column>);

-- NULL_COUNT grouped by multiple columns
ALTER TABLE <database>.<schema>.<table_name>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT
    ON (<metric_column>)
    WITHIN GROUP (<group_by_column>, <group_by_column_2>);

-- DUPLICATE_COUNT grouped by a column
ALTER TABLE <database>.<schema>.<table_name>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.DUPLICATE_COUNT
    ON (<metric_column>)
    WITHIN GROUP (<group_by_column>);

-- ROW_COUNT grouped by a column (no metric column needed)
ALTER TABLE <database>.<schema>.<table_name>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.ROW_COUNT
    ON ()
    WITHIN GROUP (<group_by_column>);

-- ACCEPTED_VALUES grouped by a column
ALTER TABLE <database>.<schema>.<table_name>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.ACCEPTED_VALUES
    ON (<metric_column>, <metric_column> -> '<value1>,<value2>,<value3>')
    WITHIN GROUP (<group_by_column>);

-- With GROUP LIMIT (caps the number of distinct groups evaluated, range 1-1000, default 1000)
ALTER TABLE <database>.<schema>.<table_name>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT
    ON (<metric_column>)
    WITHIN GROUP (<group_by_column>)
    GROUP LIMIT <numeric_limit>;

-- With EXPECTATION (per-group pass/fail threshold)
ALTER TABLE <database>.<schema>.<table_name>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT
    ON (<metric_column>)
    WITHIN GROUP (<group_by_column>)
    EXPECTATION <expectation_name> (value = 0);

-- Combined: GROUP LIMIT + EXPECTATION
ALTER TABLE <database>.<schema>.<table_name>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT
    ON (<metric_column>)
    WITHIN GROUP (<group_by_column>)
    GROUP LIMIT <numeric_limit>
    EXPECTATION <expectation_name> (<condition>);


-- =============================================================================
-- 2. CHANGE GROUPING CONFIGURATION
-- =============================================================================
-- IMPORTANT: Grouping columns and GROUP LIMIT are IMMUTABLE after creation.
-- To change them, DROP the association and recreate with new settings.

-- Drop existing, then recreate with different grouping columns
ALTER TABLE <database>.<schema>.<table_name>
  DROP DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT
    ON (<metric_column>);

ALTER TABLE <database>.<schema>.<table_name>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT
    ON (<metric_column>)
    WITHIN GROUP (<new_group_by_column>)
    GROUP LIMIT <numeric_limit>;


-- =============================================================================
-- 3. SUSPEND / RESUME GROUPED DMF
-- =============================================================================

-- Suspend a grouped DMF association
ALTER TABLE <database>.<schema>.<table_name>
  MODIFY DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT
    ON (<metric_column>)
    SUSPEND;

-- Resume a grouped DMF association
ALTER TABLE <database>.<schema>.<table_name>
  MODIFY DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT
    ON (<metric_column>)
    RESUME;


-- =============================================================================
-- 4. DROP GROUPED DMF ASSOCIATION
-- =============================================================================

ALTER TABLE <database>.<schema>.<table_name>
  DROP DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT
    ON (<metric_column>);


-- =============================================================================
-- 5. CHECK GROUPED DMF REFERENCES
-- =============================================================================
-- The PROPERTIES column in DATA_METRIC_FUNCTION_REFERENCES includes within_group
-- (array of column refs) and group_limit when set.
SELECT
    REF_ENTITY_NAME   AS table_name,
    METRIC_NAME,
    ARGUMENT_NAMES,
    SCHEDULE_STATUS,
    PROPERTIES:within_group AS within_group_cols,
    PROPERTIES:group_limit  AS group_limit
FROM TABLE(
    INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES(
        REF_ENTITY_NAME   => '<database>.<schema>.<table_name>',
        REF_ENTITY_DOMAIN => 'table'
    )
)
WHERE PROPERTIES:within_group IS NOT NULL;


-- =============================================================================
-- 6. VIEW PER-GROUP RESULTS
-- =============================================================================

-- Query per-group results from DATA_QUALITY_MONITORING_RESULTS
-- GROUP_BY_INFO column contains per-group values as VARIANT
SELECT
    MEASUREMENT_TIME,
    METRIC_NAME,
    VALUE,
    GROUP_BY_INFO
FROM TABLE(
    SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS(
        REF_ENTITY_NAME   => '<database>.<schema>.<table_name>',
        REF_ENTITY_DOMAIN => 'table'
    )
)
WHERE GROUP_BY_INFO IS NOT NULL
ORDER BY MEASUREMENT_TIME DESC;

-- Evaluate expectations with per-group output
-- Returns one row per (expectation, group_value) combination
SELECT *
FROM TABLE(
    SYSTEM$EVALUATE_DATA_QUALITY_EXPECTATIONS(
        '<database>.<schema>.<table_name>'
    )
);

-- Scan with WITHIN_GROUP_VALUES filter
SELECT *
FROM TABLE(
    SYSTEM$DATA_METRIC_SCAN(
        REF_ENTITY_NAME       => '<database>.<schema>.<table_name>',
        WITHIN_GROUP_VALUES   => PARSE_JSON('{"<group_by_column>": "<value>"}')
    )
);


/*
Supported system DMFs with WITHIN GROUP:
  - Most system DMFs in SNOWFLAKE.CORE (NULL_COUNT, DUPLICATE_COUNT, ROW_COUNT, etc.)

NOT supported with WITHIN GROUP:
  - SNOWFLAKE.CORE.FRESHNESS (operates on entire table)
  - SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT (requires cross-table joins)
  - ANOMALY_DETECTION = TRUE (automatically disabled with WITHIN GROUP)
  - Schema-level DMF associations (ALTER SCHEMA ... ADD DATA METRIC FUNCTION)

Custom DMF body compatibility:
  Supported: single-table queries, subqueries, FLATTEN
  NOT supported: CTEs (WITH), JOINs, UNION/UNION ALL, DISTINCT, window functions

IMMUTABLE CONFIGURATION:
  Grouping columns and GROUP LIMIT cannot be modified after creation.
  To change them, DROP the association and recreate with new settings.

GROUP LIMIT behavior:
  - Range: 1–1000 (default 1000)
  - Caps the number of distinct group values evaluated per measurement
  - Exceeding distinct groups causes evaluation failure

Notifications:
  Snowflake fires at most one notification per association, based on the
  worst-group value (maximum metric value across all groups).

Introspection:
  PROPERTIES column in DATA_METRIC_FUNCTION_REFERENCES exposes:
    properties:within_group — JSON array of column references
    properties:group_limit  — maximum group threshold

Output format:
  - GROUP_BY_INFO: ARRAY column in DATA_QUALITY_MONITORING_RESULTS with
    objects containing id, name, and value for each grouping column
  - NULL values in grouping columns form their own distinct group

Requires Snowflake Enterprise Edition.
*/
