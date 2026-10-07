-- Custom DMF Creation Templates
-- Boilerplate for creating custom Data Metric Functions for validation patterns
-- that system DMFs (NULL_COUNT, FRESHNESS, etc.) do not cover.
--
-- Placeholders to replace per template:
--   <dmf_schema>      — schema to CREATE the DMF in (must have CREATE DATA METRIC FUNCTION privilege)
--   <dmf_name>        — name for the custom DMF
--   <column>          — column name to validate (referenced inside UPSTREAM_TABLES())
--   <table>           — fully qualified table name to ATTACH the DMF to (DATABASE.SCHEMA.TABLE)
--
-- All templates return a count of VIOLATIONS (0 = all rows pass, >0 = N rows violate the rule).
-- This is consistent with system DMF convention (NULL_COUNT, DUPLICATE_COUNT, etc.).
--
-- PREFER SYSTEM DMFs WHEN POSSIBLE:
-- - For format, categorical, or simple range checks: prefer SNOWFLAKE.CORE.ACCEPTED_VALUES
-- - For referential integrity / FK checks: prefer SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT
-- Use the custom DMF patterns below only when system DMFs cannot express the rule
-- (e.g. complex regex, cross-column, multi-table joins beyond simple FK).
-- See: https://docs.snowflake.com/en/sql-reference/functions/dmf_accepted_values
--      https://docs.snowflake.com/en/sql-reference/functions/dmf_referential_integrity_count
--      https://docs.snowflake.com/en/user-guide/data-quality-expectations
--
-- PREFERRED: ACCEPTED_VALUES examples (attach + expectation)
--
-- Categorical (value in set): e.g. status column must be in allowed list
--   ALTER TABLE <database>.<schema>.<table>
--     ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.ACCEPTED_VALUES ON (
--       order_status,
--       order_status -> order_status IN ('Pending', 'Dispatched', 'Delivered'));
--   ALTER DATA METRIC FUNCTION SNOWFLAKE.CORE.ACCEPTED_VALUES
--     ON <database>.<schema>.<table>(order_status)
--     SET EXPECTATION (EXPRESSION => 'value = 0', NAME => 'status_in_allowed_set');
--
-- Numeric range: e.g. column must be > 0
--   ALTER TABLE <database>.<schema>.<table>
--     ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.ACCEPTED_VALUES ON (price, price -> price > 0);
--   ALTER DATA METRIC FUNCTION SNOWFLAKE.CORE.ACCEPTED_VALUES
--     ON <database>.<schema>.<table>(price)
--     SET EXPECTATION (EXPRESSION => 'value = 0', NAME => 'price_positive');
--
-- Format (LIKE): when a simple pattern is enough
--   ALTER TABLE <database>.<schema>.<table>
--     ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.ACCEPTED_VALUES ON (
--       email, email -> email LIKE '%@%.%');
--   ALTER DATA METRIC FUNCTION SNOWFLAKE.CORE.ACCEPTED_VALUES
--     ON <database>.<schema>.<table>(email)
--     SET EXPECTATION (EXPRESSION => 'value = 0', NAME => 'email_format');


-- =============================================================================
-- PATTERN 1: Email Format Validation
-- Preferred: Use ACCEPTED_VALUES with a LIKE or IN expression if acceptable (e.g. domain list).
-- Alternative: Custom DMF below if you need stricter regex or need additional validation.
-- Returns count of rows where <column> does not match a valid email format.
-- =============================================================================
CREATE OR REPLACE DATA METRIC FUNCTION <dmf_schema>.<dmf_name>()
  RETURNS NUMBER
AS
$$
  SELECT COUNT_IF(
    NOT (<column> RLIKE '^[A-Za-z0-9._%+\\-]+@[A-Za-z0-9.\\-]+\\.[A-Za-z]{2,}$')
    AND <column> IS NOT NULL  -- only flag non-null values with wrong format
  )
  FROM TABLE(UPSTREAM_TABLES())
$$;

-- Attach to table:
ALTER TABLE <table>
  ADD DATA METRIC FUNCTION <dmf_schema>.<dmf_name> ON (<column>);


-- =============================================================================
-- PATTERN 2: Phone Number Format Validation (US E.164 / 10-digit)
-- Preferred: Use ACCEPTED_VALUES with IN or LIKE for known valid patterns if possible.
-- Alternative: Custom DMF below for full regex control. Adjust regex for other locales.
-- Returns count of rows where <column> does not match a US phone format.
-- =============================================================================
CREATE OR REPLACE DATA METRIC FUNCTION <dmf_schema>.<dmf_name>()
  RETURNS NUMBER
AS
$$
  SELECT COUNT_IF(
    NOT (<column> RLIKE '^\\+?1?[2-9]\\d{9}$')
    AND <column> IS NOT NULL
  )
  FROM TABLE(UPSTREAM_TABLES())
$$;

ALTER TABLE <table>
  ADD DATA METRIC FUNCTION <dmf_schema>.<dmf_name> ON (<column>);


-- =============================================================================
-- PATTERN 3: Value Range Validation (Numeric)
-- Preferred: Use ACCEPTED_VALUES with a range expression (e.g. column -> column > 0).
-- Alternative: Custom DMF below for complex ranges or multiple conditions.
-- Returns count of rows where <column> is outside an acceptable range.
-- Adjust the condition as needed (e.g., > 0, BETWEEN 0 AND 150, != 0).
-- =============================================================================
CREATE OR REPLACE DATA METRIC FUNCTION <dmf_schema>.<dmf_name>()
  RETURNS NUMBER
AS
$$
  SELECT COUNT_IF(NOT (<column> > 0))  -- replace > 0 with your range condition
  FROM TABLE(UPSTREAM_TABLES())
$$;

ALTER TABLE <table>
  ADD DATA METRIC FUNCTION <dmf_schema>.<dmf_name> ON (<column>);


-- =============================================================================
-- PATTERN 4: Referential Integrity (FK Check)
-- ** PREFER SYSTEM DMF: For simple FK validation, use the system DMF instead:
--    ALTER TABLE <table>
--      ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT
--      ON (<child_fk_column>, TABLE(<parent_table>(<parent_pk_column>)));
-- Only use this custom DMF pattern for complex scenarios (conditional FK logic,
-- multi-table joins, or business rules beyond simple FK).
-- Returns count of child rows whose FK value does not exist in the parent table.
-- The DMF owner role must have SELECT on both the child and parent tables.
-- Replace <parent_table> with fully qualified parent table name.
-- Replace <child_fk_column> and <parent_pk_column> accordingly.
-- =============================================================================
CREATE OR REPLACE DATA METRIC FUNCTION <dmf_schema>.<dmf_name>()
  RETURNS NUMBER
AS
$$
  SELECT COUNT(*)
  FROM TABLE(UPSTREAM_TABLES()) child
  WHERE child.<child_fk_column> IS NOT NULL
    AND NOT EXISTS (
      SELECT 1
      FROM <parent_table> parent
      WHERE parent.<parent_pk_column> = child.<child_fk_column>
    )
$$;

ALTER TABLE <table>
  ADD DATA METRIC FUNCTION <dmf_schema>.<dmf_name> ON (<child_fk_column>);


-- =============================================================================
-- PATTERN 5: Cross-Column Validation (e.g., start_date before end_date)
-- Returns count of rows where the ordering constraint is violated.
-- Replace <col_a> and <col_b> with the column names to compare.
-- =============================================================================
CREATE OR REPLACE DATA METRIC FUNCTION <dmf_schema>.<dmf_name>()
  RETURNS NUMBER
AS
$$
  SELECT COUNT_IF(<col_a> >= <col_b>)  -- flag rows where start >= end
  FROM TABLE(UPSTREAM_TABLES())
$$;

ALTER TABLE <table>
  ADD DATA METRIC FUNCTION <dmf_schema>.<dmf_name> ON (<col_a>);


-- =============================================================================
-- PATTERN 6: Statistical Outlier Detection
-- Returns count of rows where <column> deviates more than N standard deviations
-- from the mean. Adjust the multiplier (default 3) as needed.
-- Only meaningful for numeric columns with sufficient row counts (>30 rows).
-- =============================================================================
CREATE OR REPLACE DATA METRIC FUNCTION <dmf_schema>.<dmf_name>()
  RETURNS NUMBER
AS
$$
  WITH stats AS (
    SELECT
      AVG(<column>)    AS mean_val,
      STDDEV(<column>) AS stddev_val
    FROM TABLE(UPSTREAM_TABLES())
  )
  SELECT COUNT(*)
  FROM TABLE(UPSTREAM_TABLES()), stats
  WHERE ABS(<column> - stats.mean_val) > 3 * NULLIF(stats.stddev_val, 0)
$$;

ALTER TABLE <table>
  ADD DATA METRIC FUNCTION <dmf_schema>.<dmf_name> ON (<column>);


/*
After attaching any custom DMF, verify it runs:

SELECT METRIC_NAME, VALUE, MEASUREMENT_TIME
FROM TABLE(SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS(
    REF_ENTITY_NAME => '<table>',
    REF_ENTITY_DOMAIN => 'TABLE'
))
WHERE METRIC_NAME ILIKE '%<dmf_name>%'
ORDER BY MEASUREMENT_TIME DESC
LIMIT 5;

Permissions required:
  - CREATE DATA METRIC FUNCTION on <dmf_schema>
  - ATTACH DATA METRIC FUNCTION PRIVILEGE on the target table
  - SELECT on all tables referenced inside the DMF body
*/
