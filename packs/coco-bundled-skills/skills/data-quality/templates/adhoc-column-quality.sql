-- Ad-Hoc Column Quality Assessment
-- Uses SNOWFLAKE.CORE.* system DMFs called inline — no pre-attached DMFs required.
-- Replace <db>, <schema>, <table>, <col> with actual values before executing.

-- ============================================================================
-- IMPORTANT: _PERCENT DMF functions return values on the 0–100 scale.
-- 0.7968 means 0.7968%, NOT 79.68%. Always cross-validate:
--   NULL_COUNT / total_rows should equal NULL_PERCENT / 100
-- ============================================================================



-- ── 1. FRESHNESS ─────────────────────────────────────────────────────────────
-- Use for DATE, TIMESTAMP_*, TIMESTAMP_LTZ, TIMESTAMP_TZ columns.
-- Returns seconds since the most recent non-NULL value.

SELECT
    '<table>'            AS table_name,
    '<col>'              AS column_name,
    'FRESHNESS'          AS metric,
    SNOWFLAKE.CORE.FRESHNESS(
        SELECT <col> FROM <db>.<schema>.<table>
    )                    AS value_seconds,
    ROUND(SNOWFLAKE.CORE.FRESHNESS(
        SELECT <col> FROM <db>.<schema>.<table>
    ) / 86400, 2)        AS value_days
;


-- ── 2. NULL ANALYSIS ─────────────────────────────────────────────────────────
-- Use for all columns EXCEPT BOOLEAN (DMFs not supported on BOOLEAN).
-- NULL_PERCENT is on 0–100 scale (e.g., 5.0 = 5%).

SELECT
    '<table>'                AS table_name,
    '<col>'                  AS column_name,
    SNOWFLAKE.CORE.NULL_COUNT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS null_count,
    SNOWFLAKE.CORE.NULL_PERCENT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS null_pct       -- 0–100 scale; 5.0 means 5%
;

-- BOOLEAN fallback (no DMF support — use raw SQL):
SELECT
    COUNT(*) - COUNT(<col>) AS null_count,
    (COUNT(*) - COUNT(<col>)) * 100.0 / NULLIF(COUNT(*), 0) AS null_pct
FROM <db>.<schema>.<table>
;


-- ── 3. BLANK DETECTION ───────────────────────────────────────────────────────
-- Use for VARCHAR / TEXT columns only.
-- BLANK_PERCENT is on 0–100 scale.

SELECT
    '<table>'                AS table_name,
    '<col>'                  AS column_name,
    SNOWFLAKE.CORE.BLANK_COUNT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS blank_count,
    SNOWFLAKE.CORE.BLANK_PERCENT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS blank_pct      -- 0–100 scale; 1.5 means 1.5%
;


-- ── 4. UNIQUENESS / DUPLICATE DETECTION ──────────────────────────────────────
-- Use for Critical columns (ID columns, primary keys, deduplication keys).
-- Indicates cardinality and integrity of key columns.

SELECT
    '<table>'                AS table_name,
    '<col>'                  AS column_name,
    SNOWFLAKE.CORE.DUPLICATE_COUNT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS duplicate_count,
    SNOWFLAKE.CORE.UNIQUE_COUNT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS unique_count
;


-- ── 5. ACCEPTED VALUES (Ad-Hoc) ─────────────────────────────────────────────
-- Use SYSTEM$DATA_METRIC_SCAN to run ACCEPTED_VALUES without attaching a DMF.
-- Returns the actual violating rows, not just a count.
-- Supports: comparison operators, logical operators, LIKE, RLIKE, IN, IS [NOT] NULL.

-- Categorical: find rows where status is not in the allowed set
SELECT *
FROM TABLE(SYSTEM$DATA_METRIC_SCAN(
    REF_ENTITY_NAME  => '<db>.<schema>.<table>',
    METRIC_NAME      => 'SNOWFLAKE.CORE.ACCEPTED_VALUES',
    ARGUMENT_NAME    => '<col>',
    ARGUMENT_EXPRESSION => '<col> IN (''Value1'', ''Value2'', ''Value3'')'
));

-- Numeric range: find rows where price is not positive
SELECT *
FROM TABLE(SYSTEM$DATA_METRIC_SCAN(
    REF_ENTITY_NAME  => '<db>.<schema>.<table>',
    METRIC_NAME      => 'SNOWFLAKE.CORE.ACCEPTED_VALUES',
    ARGUMENT_NAME    => '<col>',
    ARGUMENT_EXPRESSION => '<col> > 0'
));

-- Email format (RLIKE): find rows with invalid email format
SELECT *
FROM TABLE(SYSTEM$DATA_METRIC_SCAN(
    REF_ENTITY_NAME  => '<db>.<schema>.<table>',
    METRIC_NAME      => 'SNOWFLAKE.CORE.ACCEPTED_VALUES',
    ARGUMENT_NAME    => '<col>',
    ARGUMENT_EXPRESSION => '<col> RLIKE ''^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'''
));


-- ── 6. REFERENTIAL INTEGRITY (Scan after attach) ────────────────────────────
-- After attaching REFERENTIAL_INTEGRITY_COUNT via ALTER TABLE, use
-- SYSTEM$DATA_METRIC_SCAN to retrieve the actual orphan rows (not just the count).
-- The reference table is resolved from the stored DMF association.
-- NULL FK values are excluded (standard FK semantics).

-- Prerequisite: attach the DMF first
-- ALTER TABLE <db>.<schema>.<table> ADD DATA METRIC FUNCTION
--   SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT
--   ON (<fk_col>, TABLE(<ref_db>.<ref_schema>.<ref_table>(<ref_col>)));

-- Single-column FK check: find rows where <fk_col> has no match in reference table
SELECT *
FROM TABLE(SYSTEM$DATA_METRIC_SCAN(
    REF_ENTITY_NAME  => '<db>.<schema>.<table>',
    METRIC_NAME      => 'SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT',
    ARGUMENT_NAME    => '<fk_col>'
));

-- Compound key FK check: find rows where (col1, col2) has no match in reference table
SELECT *
FROM TABLE(SYSTEM$DATA_METRIC_SCAN(
    REF_ENTITY_NAME  => '<db>.<schema>.<table>',
    METRIC_NAME      => 'SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT',
    ARGUMENT_NAME    => '<fk_col1>, <fk_col2>'
));


-- ── 7a. NUMERIC STATISTICS ────────────────────────────────────────────────────
-- Use for NUMBER, FLOAT, DECIMAL columns only.
-- Helps detect anomalous distributions or broken numeric ranges.

SELECT
    '<table>'                AS table_name,
    '<col>'                  AS column_name,
    SNOWFLAKE.CORE.AVG(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS avg_value,
    SNOWFLAKE.CORE.MIN(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS min_value,
    SNOWFLAKE.CORE.MAX(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS max_value,
    SNOWFLAKE.CORE.STDDEV(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS stddev_value
;


-- ── 7b. EXTENDED NUMERIC VALIDATION ──────────────────────────────────────────
-- Use for NUMBER, FLOAT, DECIMAL columns only.
-- Note: These DMFs may not be available in all deployments.

SELECT
    '<table>'                AS table_name,
    '<col>'                  AS column_name,
    SNOWFLAKE.CORE.VARIANCE(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS variance_value,
    SNOWFLAKE.CORE.MEDIAN(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS median_value,
    SNOWFLAKE.CORE.ZERO_COUNT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS zero_count,
    SNOWFLAKE.CORE.ZERO_PERCENT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS zero_pct,        -- 0–100 scale
    SNOWFLAKE.CORE.NEGATIVE_COUNT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS negative_count,
    SNOWFLAKE.CORE.NEGATIVE_PERCENT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS negative_pct     -- 0–100 scale
;


-- ── 7c. STRING LENGTH ANALYSIS ───────────────────────────────────────────────
-- Use for VARCHAR / TEXT columns only.
-- Note: These DMFs may not be available in all deployments.

SELECT
    '<table>'                AS table_name,
    '<col>'                  AS column_name,
    SNOWFLAKE.CORE.STRING_LENGTH_MIN(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS min_length,
    SNOWFLAKE.CORE.STRING_LENGTH_MAX(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS max_length,
    SNOWFLAKE.CORE.STRING_LENGTH_AVG(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS avg_length
;


-- ── 7d. STRING / FORMAT VALIDATION ───────────────────────────────────────────
-- Use for VARCHAR / TEXT columns only. Returns count and percentage of violations.
-- Note: These DMFs may not be available in all deployments.

SELECT
    '<table>'                AS table_name,
    '<col>'                  AS column_name,
    SNOWFLAKE.CORE.UNTRIMMED_STRING_COUNT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS untrimmed_count,
    SNOWFLAKE.CORE.UNTRIMMED_STRING_PERCENT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS untrimmed_pct,        -- 0–100 scale
    SNOWFLAKE.CORE.INVALID_NUMERIC_TYPE_CAST_COUNT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS invalid_numeric_count,
    SNOWFLAKE.CORE.INVALID_NUMERIC_TYPE_CAST_PERCENT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS invalid_numeric_pct,   -- 0–100 scale
    SNOWFLAKE.CORE.SPECIAL_CHARACTER_COUNT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS special_char_count,
    SNOWFLAKE.CORE.SPECIAL_CHARACTER_PERCENT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS special_char_pct,      -- 0–100 scale
    SNOWFLAKE.CORE.CASE_FORMAT_VIOLATION_COUNT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS case_violation_count,
    SNOWFLAKE.CORE.CASE_FORMAT_VIOLATION_PERCENT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS case_violation_pct     -- 0–100 scale
;


-- ── 7e. JSON VALIDATION ──────────────────────────────────────────────────────
-- Use for VARCHAR columns that may contain JSON data.
-- Note: These DMFs may not be available in all deployments.

SELECT
    '<table>'                AS table_name,
    '<col>'                  AS column_name,
    SNOWFLAKE.CORE.INVALID_JSON_COUNT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS invalid_json_count,
    SNOWFLAKE.CORE.INVALID_JSON_PERCENT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS invalid_json_pct  -- 0–100 scale
;


-- ── 7f. TEMPORAL VALIDATION ──────────────────────────────────────────────────
-- Use for DATE, TIMESTAMP_LTZ, TIMESTAMP_TZ columns.
-- Detects future-dated records relative to DMF evaluation time.
-- Note: These DMFs may not be available in all deployments.

SELECT
    '<table>'                AS table_name,
    '<col>'                  AS column_name,
    SNOWFLAKE.CORE.FUTURE_TIMESTAMP_COUNT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS future_count,
    SNOWFLAKE.CORE.FUTURE_TIMESTAMP_PERCENT(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS future_pct        -- 0–100 scale
;


-- ── 7g. APPROXIMATE QUANTILES ───────────────────────────────────────────────
-- Use for NUMBER, FLOAT, DECIMAL columns only.
-- Note: These DMFs may not be available in all deployments.

SELECT
    '<table>'                AS table_name,
    '<col>'                  AS column_name,
    SNOWFLAKE.CORE.APPROX_QUANTILE_25(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS p25,
    SNOWFLAKE.CORE.APPROX_QUANTILE_50(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS p50_median,
    SNOWFLAKE.CORE.APPROX_QUANTILE_99(
        SELECT <col> FROM <db>.<schema>.<table>
    )                        AS p99
;


-- ── 8. LISTING CONTEXT: Objects Granted to a Share ────────────────────────────
-- Use for provider listings to enumerate tables/views included in the listing.

SHOW GRANTS TO SHARE <share_name>;

-- Then query table metadata from the underlying database (after parsing share objects):
SELECT TABLE_NAME, TABLE_TYPE, ROW_COUNT, LAST_ALTERED
FROM <underlying_db>.INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA NOT IN ('INFORMATION_SCHEMA')
  AND TABLE_NAME NOT LIKE '%_HISTORY'
  AND TABLE_NAME NOT LIKE '%_PIT'
ORDER BY TABLE_NAME
;


-- ── 9. CONSUMER LISTING: Imported Databases ──────────────────────────────────
-- For consumers, the listing appears as a shared/imported database.
-- Use SHOW DATABASES to identify which databases came from shares.

SHOW DATABASES;
-- Look for rows where ORIGIN is not empty — these are imported from listings.

-- Access columns from an imported listing database normally:
SELECT TABLE_NAME, TABLE_TYPE, ROW_COUNT
FROM <imported_db>.INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA NOT IN ('INFORMATION_SCHEMA')
ORDER BY TABLE_NAME
;


-- ── 10. DMF ATTACH TEMPLATES (Continuous Monitoring Setup) ────────────────────
-- If user wants to switch from ad-hoc to continuous monitoring.
-- Requires OWNERSHIP or ALTER privilege on the table.
-- ⚠️ CONFIRM with user before executing — state-changing operation.

-- Set schedule (TRIGGER_ON_CHANGES or a cron, e.g., '60 MINUTE')
ALTER TABLE <db>.<schema>.<table>
  SET DATA_METRIC_SCHEDULE = 'TRIGGER_ON_CHANGES';

-- Attach null count to a VARCHAR column
ALTER TABLE <db>.<schema>.<table>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT ON (<column>);

-- Attach blank percent to a VARCHAR column
ALTER TABLE <db>.<schema>.<table>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.BLANK_PERCENT ON (<column>);

-- Attach duplicate count to an ID/key column
ALTER TABLE <db>.<schema>.<table>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.DUPLICATE_COUNT ON (<id_column>);

-- Attach freshness to a timestamp column
ALTER TABLE <db>.<schema>.<table>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.FRESHNESS ON (<timestamp_column>);


/*
Quick Reference — SNOWFLAKE.CORE.* System DMFs:

  Core DMFs (available in all deployments):
  FRESHNESS(<col>)        → seconds since latest non-NULL value (timestamp/date columns)
  NULL_COUNT(<col>)       → absolute count of NULL rows
  NULL_PERCENT(<col>)     → % NULL rows (0–100 scale)
  BLANK_COUNT(<col>)      → count of rows with empty string '' (VARCHAR only)
  BLANK_PERCENT(<col>)    → % blank rows (0–100 scale)
  DUPLICATE_COUNT(<col>)  → count of rows with a non-unique value
  UNIQUE_COUNT(<col>)     → count of distinct non-NULL values
  ROW_COUNT()             → total row count (table-level, no column)
  AVG(<col>)              → average (numeric only)
  MIN(<col>)              → minimum (numeric/date)
  MAX(<col>)              → maximum (numeric/date)
  STDDEV(<col>)           → standard deviation (numeric only)
  ACCEPTED_VALUES(<col>, <col> -> <expr>) → count of rows failing a Boolean check (via ALTER TABLE)
  REFERENTIAL_INTEGRITY_COUNT(<col>, TABLE(<ref_table>(<ref_col>))) → count of orphan rows (via ALTER TABLE)

  Extended DMFs (may not be available in all deployments — verify with SHOW DATA METRIC FUNCTIONS):
  VARIANCE(<col>)                        → variance (NUMBER/FLOAT only)
  MEDIAN(<col>)                          → median (NUMBER/FLOAT only)
  APPROX_QUANTILE_25(<col>)              → 25th percentile (NUMBER/FLOAT only)
  APPROX_QUANTILE_50(<col>)              → 50th percentile (NUMBER/FLOAT only)
  APPROX_QUANTILE_99(<col>)              → 99th percentile (NUMBER/FLOAT only)
  ZERO_COUNT(<col>)                      → count of zero values (NUMBER/FLOAT only)
  ZERO_PERCENT(<col>)                    → % zero values (0–100 scale)
  NEGATIVE_COUNT(<col>)                  → count of negative values (NUMBER/FLOAT only)
  NEGATIVE_PERCENT(<col>)                → % negative values (0–100 scale)
  STRING_LENGTH_MIN(<col>)               → min string length (VARCHAR only)
  STRING_LENGTH_MAX(<col>)               → max string length (VARCHAR only)
  STRING_LENGTH_AVG(<col>)               → avg string length (VARCHAR only)
  UNTRIMMED_STRING_COUNT(<col>)          → count with leading/trailing whitespace (VARCHAR only)
  UNTRIMMED_STRING_PERCENT(<col>)        → % with whitespace (0–100 scale)
  INVALID_NUMERIC_TYPE_CAST_COUNT(<col>) → count failing TRY_TO_NUMBER (VARCHAR only)
  INVALID_NUMERIC_TYPE_CAST_PERCENT(<col>) → % failing numeric parse (0–100 scale)
  SPECIAL_CHARACTER_COUNT(<col>)         → count with non-alphanumeric chars (VARCHAR only)
  SPECIAL_CHARACTER_PERCENT(<col>)       → % with non-alphanumeric chars (0–100 scale)
  CASE_FORMAT_VIOLATION_COUNT(<col>)     → count with mixed casing (VARCHAR only)
  CASE_FORMAT_VIOLATION_PERCENT(<col>)   → % with mixed casing (0–100 scale)
  INVALID_JSON_COUNT(<col>)              → count of invalid JSON values (VARCHAR only)
  INVALID_JSON_PERCENT(<col>)            → % invalid JSON (0–100 scale)
  FUTURE_TIMESTAMP_COUNT(<col>)          → count of future-dated values (DATE/TIMESTAMP only)
  FUTURE_TIMESTAMP_PERCENT(<col>)        → % future-dated (0–100 scale)

Note: Not all DMFs work on all data types. Boolean columns fall back to SQL.
Listing consumers may have read-only access — DDL operations (ALTER TABLE) will fail.
*/
