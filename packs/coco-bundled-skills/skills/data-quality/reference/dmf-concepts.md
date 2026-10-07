---
parent_skill: data-quality
---

# Data Metric Functions (DMF) Concepts

## Overview

Snowflake Data Metric Functions (DMFs) provide built-in data quality monitoring capabilities to automatically track and measure data quality metrics across your tables and schemas. Understanding these concepts is essential before working with schema-level data quality monitoring workflows.

## Key Concepts

### 1. Data Metric Functions (DMFs)

A **Data Metric Function (DMF)** is a Snowflake function that computes a quality metric for a table or column. DMFs run automatically when data changes, enabling continuous data quality monitoring.

**Two types of DMFs:**

| Type | Description | Use Case |
|------|-------------|----------|
| **System DMFs** | Pre-built metrics by Snowflake | Common quality checks (nulls, freshness, uniqueness) |
| **Custom DMFs** | User-defined quality metrics | Domain-specific quality rules |

### 2. System DMFs

Snowflake provides built-in system DMFs for common quality checks:

**Data Freshness:**
```sql
SNOWFLAKE.CORE.FRESHNESS(
  TABLE_NAME => 'schema.table',
  TIMESTAMP_COLUMN => 'updated_at'
)
```
Measures how recent the data is based on a timestamp column.

**Null Count:**
```sql
SNOWFLAKE.CORE.NULL_COUNT(
  TABLE_NAME => 'schema.table',
  COLUMN_NAME => 'customer_id'
)
```
Counts null values in a column.

**Unique Count:**
```sql
SNOWFLAKE.CORE.UNIQUE_COUNT(
  TABLE_NAME => 'schema.table',
  COLUMN_NAME => 'email'
)
```
Counts unique values in a column.

**Duplicate Count:**
```sql
SNOWFLAKE.CORE.DUPLICATE_COUNT(
  TABLE_NAME => 'schema.table',
  COLUMN_NAME => 'email'
)
```
Counts duplicate values in a column.

**Row Count:**
```sql
SNOWFLAKE.CORE.ROW_COUNT(
  TABLE_NAME => 'schema.table'
)
```
Counts total rows in a table.

**Accepted Values:**
```sql
SNOWFLAKE.CORE.ACCEPTED_VALUES ON (
  <column>,
  <column> -> <boolean_expression>
)
```
Returns the number of records where the column value does **not** match the Boolean expression (i.e., violation count). Supports comparison operators, logical operators, `LIKE`, `RLIKE`, `IN`, and `IS [NOT] NULL`. Cannot be called directly — must be associated via `ALTER TABLE ... ADD DATA METRIC FUNCTION`. Works with VARCHAR, NUMBER, FLOAT, DATE, and TIMESTAMP types.

**Attach examples:**
```sql
-- Categorical: status must be in allowed set
ALTER TABLE my_schema.orders
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.ACCEPTED_VALUES ON (
    order_status,
    order_status -> order_status IN ('Pending', 'Dispatched', 'Delivered'));

-- Numeric range: price must be positive
ALTER TABLE my_schema.products
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.ACCEPTED_VALUES ON (
    price, price -> price > 0);

-- Combined logic: age must be between 0 and 120 (AND operator)
ALTER TABLE my_schema.customers
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.ACCEPTED_VALUES ON (
    age, age -> age >= 0 AND age <= 120);

-- Email format: strict regex validation
ALTER TABLE my_schema.customers
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.ACCEPTED_VALUES ON (
    email, email -> email RLIKE '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$');
```

**Ad-hoc scan (no attach required):**
Use `SYSTEM$DATA_METRIC_SCAN` to run ACCEPTED_VALUES on-demand and get the actual violating rows:
```sql
SELECT *
FROM TABLE(SYSTEM$DATA_METRIC_SCAN(
    REF_ENTITY_NAME  => 'MY_DATABASE.MY_SCHEMA.MY_TABLE',
    METRIC_NAME      => 'SNOWFLAKE.CORE.ACCEPTED_VALUES',
    ARGUMENT_NAME    => 'order_status',
    ARGUMENT_EXPRESSION => 'order_status IN (''Pending'', ''Dispatched'', ''Delivered'')'
));
```
See [SYSTEM$DATA_METRIC_SCAN](https://docs.snowflake.com/en/sql-reference/functions/system_data_metric_scan).

**When to use ACCEPTED_VALUES vs. Custom DMFs:**
- **Use ACCEPTED_VALUES** for: value-in-set, simple range checks, LIKE patterns, RLIKE/regex patterns, NULL checks, comparison operators
- **Use Custom DMFs** for: cross-column validation, statistical outliers, complex multi-table joins beyond simple FK

See [ACCEPTED_VALUES documentation](https://docs.snowflake.com/en/sql-reference/functions/dmf_accepted_values).

**Referential Integrity Count:**
```sql
SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT ON (
  <source_column>,
  TABLE(<ref_db>.<ref_schema>.<ref_table>(<ref_column>))
)
```
Returns the count of rows in the source table where the column value does not have a corresponding match in the referenced table. These unmatched rows are known as **orphaned rows** and represent violations of referential integrity. A return value of 0 means full referential integrity. NULL values in the source column are **not** counted as violations (standard FK semantics).

For compound (multi-column) keys:
```sql
SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT ON (
  <col1>, <col2>, ...,
  TABLE(<ref_db>.<ref_schema>.<ref_table>(<ref_col1>, <ref_col2>, ...))
)
```
The number and order of source columns must match the reference columns (validated at association time).

**Allowed data types:** DATE, FLOAT, NUMBER, TIMESTAMP_LTZ, TIMESTAMP_NTZ, TIMESTAMP_TZ, VARCHAR.

**Attach examples:**
```sql
-- Single-column FK check: salesorders.sp_id must exist in salespeople.sp_id
ALTER TABLE salesorders
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT
  ON (sp_id, TABLE(my_db.sch1.salespeople(sp_id)));

-- Compound key: order_items.(order_id, product_id) must exist in order_products
ALTER TABLE order_items
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT
  ON (order_id, product_id, TABLE(my_db.sch1.order_products(order_id, product_id)));

-- Drop the association
ALTER TABLE salesorders
  DROP DATA METRIC FUNCTION SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT
  ON (sp_id, TABLE(my_db.sch1.salespeople(sp_id)));
```

**Associate with an expectation** (zero orphaned rows = full integrity):
```sql
ALTER TABLE salesorders
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT
  ON (sp_id, TABLE(my_db.sch1.salespeople(sp_id)))
  EXPECTATION no_orphans (VALUE = 0);

-- Add expectation to existing association
ALTER TABLE salesorders
  MODIFY DATA METRIC FUNCTION SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT
  ON (sp_id, TABLE(my_db.sch1.salespeople(sp_id)))
  ADD EXPECTATION no_orphans (VALUE = 0);
```

**Retrieve actual orphan rows via SYSTEM$DATA_METRIC_SCAN** (requires DMF to be attached first):
```sql
-- Prerequisite: attach REFERENTIAL_INTEGRITY_COUNT to the table first
-- ALTER TABLE salesorders ADD DATA METRIC FUNCTION
--   SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT ON (sp_id, TABLE(my_db.sch1.salespeople(sp_id)));

-- Single-column: find rows in salesorders where sp_id has no match in salespeople
SELECT *
FROM TABLE(SYSTEM$DATA_METRIC_SCAN(
    REF_ENTITY_NAME  => 'MY_DB.MY_SCHEMA.SALESORDERS',
    METRIC_NAME      => 'SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT',
    ARGUMENT_NAME    => 'SP_ID'
));

-- Compound key: find orphan rows based on (order_id, product_id)
-- Prerequisite: ALTER TABLE order_items ADD DATA METRIC FUNCTION
--   SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT
--   ON (order_id, product_id, TABLE(my_db.sch1.order_products(order_id, product_id)));
SELECT *
FROM TABLE(SYSTEM$DATA_METRIC_SCAN(
    REF_ENTITY_NAME  => 'MY_DB.MY_SCHEMA.ORDER_ITEMS',
    METRIC_NAME      => 'SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT',
    ARGUMENT_NAME    => 'ORDER_ID, PRODUCT_ID'
));
```

**Usage notes:**
- `SYSTEM$DATA_METRIC_SCAN` for `REFERENTIAL_INTEGRITY_COUNT` requires the DMF to be attached via `ALTER TABLE ... ADD DATA METRIC FUNCTION` first. The reference table is resolved from the stored association, not from call parameters. The scan returns the actual violating rows (not just the count), which is its value over reading metric results alone.
- Cannot be called directly as an inline function (no ad-hoc `SELECT SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT(SELECT ...)`). Associate via `ALTER TABLE` for scheduled monitoring, then use `SYSTEM$DATA_METRIC_SCAN` to retrieve violating rows on demand.
- If you need to monitor NULL values in the FK column, use `NULL_COUNT` alongside this function.
- The source table owner's role must have SELECT access to the referenced table.
- This system DMF replaces the need for custom referential integrity DMFs using LEFT JOIN patterns. Use custom DMFs only for complex multi-table joins or business logic beyond simple FK validation.

See [REFERENTIAL_INTEGRITY_COUNT documentation](https://docs.snowflake.com/en/sql-reference/functions/dmf_referential_integrity_count).

**Additional System DMFs:**

> **Availability note:** The DMFs below may not be available in all deployments. Run `SHOW DATA METRIC FUNCTIONS IN SNOWFLAKE.CORE` to verify availability before recommending or attaching them.

**Statistical DMFs** (NUMBER or FLOAT columns):

| DMF | Returns | Description |
|-----|---------|-------------|
| `SNOWFLAKE.CORE.VARIANCE` | FLOAT | Variance of column values. Detects unexpected changes in data spread. |
| `SNOWFLAKE.CORE.MEDIAN` | FLOAT | Median value. More robust than AVG for skewed distributions. |
| `SNOWFLAKE.CORE.APPROX_QUANTILE_25` | FLOAT | 25th percentile (P25). Tracks lower quartile boundary. |
| `SNOWFLAKE.CORE.APPROX_QUANTILE_50` | FLOAT | 50th percentile (P50). Approximate median for large datasets. |
| `SNOWFLAKE.CORE.APPROX_QUANTILE_99` | FLOAT | 99th percentile (P99). Detects outliers and tail behavior. |

```sql
ALTER TABLE my_schema.orders
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.VARIANCE ON (order_amount);
```

**Numeric Validation DMFs** (NUMBER or FLOAT columns):

| DMF | Returns | Description |
|-----|---------|-------------|
| `SNOWFLAKE.CORE.ZERO_COUNT` | NUMBER | Count of values that are zero. Detects placeholder data. |
| `SNOWFLAKE.CORE.ZERO_PERCENT` | FLOAT | Percentage of values that are zero (0-100 scale). |
| `SNOWFLAKE.CORE.NEGATIVE_COUNT` | NUMBER | Count of negative values. Validates non-negative columns (price, age). |
| `SNOWFLAKE.CORE.NEGATIVE_PERCENT` | FLOAT | Percentage of negative values (0-100 scale). |

```sql
ALTER TABLE my_schema.products
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.NEGATIVE_COUNT ON (price)
  EXPECTATION no_negatives (VALUE = 0);
```

**String Length DMFs** (VARCHAR columns):

| DMF | Returns | Description |
|-----|---------|-------------|
| `SNOWFLAKE.CORE.STRING_LENGTH_MIN` | NUMBER | Minimum string length of non-NULL values. Detects truncation. |
| `SNOWFLAKE.CORE.STRING_LENGTH_MAX` | NUMBER | Maximum string length. Detects overflow or unexpected long values. |
| `SNOWFLAKE.CORE.STRING_LENGTH_AVG` | FLOAT | Average string length. Monitors length drift over time. |

```sql
ALTER TABLE my_schema.customers
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.STRING_LENGTH_MIN ON (zip_code),
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.STRING_LENGTH_MAX ON (zip_code);
```

**String/Format Validation DMFs** (VARCHAR columns):

| DMF | Returns | Description |
|-----|---------|-------------|
| `SNOWFLAKE.CORE.UNTRIMMED_STRING_COUNT` | NUMBER | Count of non-NULL values with leading/trailing whitespace. |
| `SNOWFLAKE.CORE.UNTRIMMED_STRING_PERCENT` | FLOAT | Percentage with leading/trailing whitespace (0-100 scale). |
| `SNOWFLAKE.CORE.INVALID_NUMERIC_TYPE_CAST_COUNT` | NUMBER | Count of non-NULL values that fail to parse as numeric (TRY_TO_NUMBER). |
| `SNOWFLAKE.CORE.INVALID_NUMERIC_TYPE_CAST_PERCENT` | FLOAT | Percentage failing numeric parse (0-100 scale). |
| `SNOWFLAKE.CORE.SPECIAL_CHARACTER_COUNT` | NUMBER | Count of non-NULL values containing non-alphanumeric characters (outside A-Z, a-z, 0-9). |
| `SNOWFLAKE.CORE.SPECIAL_CHARACTER_PERCENT` | FLOAT | Percentage with non-alphanumeric characters (0-100 scale). |
| `SNOWFLAKE.CORE.CASE_FORMAT_VIOLATION_COUNT` | NUMBER | Count of non-NULL values with inconsistent casing (not all-upper, all-lower, or title-case). |
| `SNOWFLAKE.CORE.CASE_FORMAT_VIOLATION_PERCENT` | FLOAT | Percentage with inconsistent casing (0-100 scale). |

```sql
ALTER TABLE my_schema.customers
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.UNTRIMMED_STRING_COUNT ON (name)
  EXPECTATION no_whitespace (VALUE = 0);

ALTER TABLE my_schema.imports
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.INVALID_NUMERIC_TYPE_CAST_COUNT ON (amount_text)
  EXPECTATION all_numeric (VALUE = 0);
```

**JSON Validation DMFs** (VARCHAR columns):

| DMF | Returns | Description |
|-----|---------|-------------|
| `SNOWFLAKE.CORE.INVALID_JSON_COUNT` | NUMBER | Count of non-NULL values that are not valid JSON (TRY_PARSE_JSON). |
| `SNOWFLAKE.CORE.INVALID_JSON_PERCENT` | FLOAT | Percentage of invalid JSON values (0-100 scale). |

```sql
ALTER TABLE my_schema.events
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.INVALID_JSON_COUNT ON (payload)
  EXPECTATION valid_json (VALUE = 0);
```

**Temporal Validation DMFs** (DATE, TIMESTAMP_LTZ, or TIMESTAMP_TZ columns):

| DMF | Returns | Description |
|-----|---------|-------------|
| `SNOWFLAKE.CORE.FUTURE_TIMESTAMP_COUNT` | NUMBER | Count of values in the future relative to the DMF evaluation time. |
| `SNOWFLAKE.CORE.FUTURE_TIMESTAMP_PERCENT` | FLOAT | Percentage of future-dated values (0-100 scale). |

```sql
ALTER TABLE my_schema.transactions
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.FUTURE_TIMESTAMP_COUNT ON (transaction_date)
  EXPECTATION no_future_dates (VALUE = 0);
```

**NULL handling for all new DMFs:** NULLs are excluded from violation counts (NULLs = absent data, not invalid data). Percent DMFs use total row count (including NULLs) as denominator.

### 3. Custom DMFs

For domain-specific quality rules, create **Custom DMFs**:

```sql
CREATE OR REPLACE DATA METRIC FUNCTION my_schema.valid_email_pct()
RETURNS NUMBER
AS
$$
SELECT
  (COUNT_IF(email RLIKE '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}$') * 100.0) /
  NULLIF(COUNT(*), 0)
FROM TABLE(UPSTREAM_TABLES())
$$;
```

**Use cases:**
- Business rule validation (e.g., price > 0)
- Format validation (e.g., email patterns, phone formats)
- Referential integrity (e.g., foreign key checks)
- Statistical outliers (e.g., values outside 3 standard deviations)
- Cross-column validation (e.g., start_date < end_date)

### 4. Attaching DMFs to Tables

DMFs must be attached to tables to monitor them:

```sql
-- Attach a single DMF to a table
ALTER TABLE my_schema.customers
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT
  ON (email);

-- Attach multiple DMFs
ALTER TABLE my_schema.customers
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.FRESHNESS ON (updated_at),
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.DUPLICATE_COUNT ON (email),
  ADD DATA METRIC FUNCTION my_schema.valid_email_pct ON ();
```

**Schema-wide attachment:**
```sql
-- Attach DMF to all tables in a schema
ALTER SCHEMA my_schema
  SET DATA_METRIC_SCHEDULE = 'TRIGGER_ON_CHANGES';
```

### 5. DMF Scheduling

DMFs can run on different schedules:

| Schedule Type | Description | Use Case |
|--------------|-------------|----------|
| `TRIGGER_ON_CHANGES` | Run when data changes | Real-time quality monitoring |
| `CRON` | Run on a schedule (e.g., hourly, daily) | Periodic quality checks |
| `MANUAL` | Run only when explicitly triggered | Ad-hoc quality audits |

```sql
-- Set schedule for a schema
ALTER SCHEMA my_schema
  SET DATA_METRIC_SCHEDULE = 'USING CRON 0 */6 * * * UTC';
```

### 6. Accessing DMF Results

DMF metric results are accessed via the `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS()` **table function**.

**IMPORTANT:** `SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_RESULTS` does **NOT** exist. Never query it.

**Correct way to query DMF results:**
```sql
-- Query results for a specific table
SELECT *
FROM TABLE(SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS(
  REF_ENTITY_NAME => 'MY_DATABASE.MY_SCHEMA.MY_TABLE',
  REF_ENTITY_DOMAIN => 'TABLE'
))
ORDER BY MEASUREMENT_TIME DESC;
```

**Columns returned by `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS()`:**

| Column | Type | Description |
|--------|------|-------------|
| `MEASUREMENT_TIME` | TIMESTAMP_LTZ | When the metric was measured |
| `TABLE_NAME` | VARCHAR | Table being monitored |
| `TABLE_SCHEMA` | VARCHAR | Schema of the table |
| `TABLE_DATABASE` | VARCHAR | Database of the table |
| `METRIC_NAME` | VARCHAR | Name of the DMF |
| `METRIC_SCHEMA` | VARCHAR | Schema of the DMF |
| `METRIC_DATABASE` | VARCHAR | Database of the DMF |
| `VALUE` | VARIANT | The metric result value |
| `REFERENCE_ID` | VARCHAR | Unique reference for this metric attachment |
| `ARGUMENT_NAMES` | ARRAY | Column names the metric applies to |
| `ARGUMENT_TYPES` | ARRAY | Data types of the arguments |
| `ARGUMENT_IDS` | ARRAY | IDs of the arguments |

**Key differences from what you might expect:**
- The column for metric values is `VALUE`, not `metric_value`
- There is no `column_name` column — use `ARGUMENT_NAMES[0]` instead
- There is no `threshold` column — thresholds are in `DATA_METRIC_FUNCTION_EXPECTATIONS`
- This is a table function (requires `TABLE()` and per-table calls), not a view

**Related ACCOUNT_USAGE views (different purposes):**

| View | Purpose | Key Columns |
|------|---------|-------------|
| `DATA_QUALITY_MONITORING_USAGE_HISTORY` | Credit/cost tracking | `START_TIME`, `CREDITS_USED`, `TABLE_NAME` |
| `DATA_METRIC_FUNCTION_REFERENCES` | DMF configurations | `REF_DATABASE_NAME`, `REF_SCHEMA_NAME`, `METRIC_NAME`, `SCHEDULE` |
| `DATA_METRIC_FUNCTION_EXPECTATIONS` | DMF thresholds/rules | `REF_DATABASE_NAME`, `REF_SCHEMA_NAME`, `EXPECTATION_NAME`, `EXPECTATION_EXPRESSION` |

### 7. Viewing DMF Results

**Check which DMFs are attached (per table):**
```sql
-- See DMF references for a specific table
SELECT *
FROM TABLE(INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES(
    REF_ENTITY_NAME => 'MY_DATABASE.MY_SCHEMA.MY_TABLE',
    REF_ENTITY_DOMAIN => 'TABLE'
));
```

**Query DMF metric results:**
```sql
-- Get latest results for a specific table
SELECT
    METRIC_NAME,
    VALUE,
    ARGUMENT_NAMES[0]::VARCHAR AS column_name,
    MEASUREMENT_TIME
FROM TABLE(SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS(
    REF_ENTITY_NAME => 'MY_DATABASE.MY_SCHEMA.MY_TABLE',
    REF_ENTITY_DOMAIN => 'TABLE'
))
QUALIFY ROW_NUMBER() OVER (PARTITION BY METRIC_NAME, REFERENCE_ID ORDER BY MEASUREMENT_TIME DESC) = 1
ORDER BY MEASUREMENT_TIME DESC;
```

### 8. Schema-Level Health Score

A **Schema Health Score** aggregates all DMF results across tables:

```sql
-- Calculate schema health percentage using SNOWFLAKE.LOCAL
WITH table_list AS (
    SELECT TABLE_NAME
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_CATALOG = 'MY_DATABASE'
      AND TABLE_SCHEMA = 'MY_SCHEMA'
      AND TABLE_TYPE = 'BASE TABLE'
),
all_metrics AS (
    SELECT t.TABLE_NAME, r.METRIC_NAME, r.VALUE, r.MEASUREMENT_TIME
    FROM table_list t,
    LATERAL (
        SELECT *
        FROM TABLE(SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS(
            REF_ENTITY_NAME => 'MY_DATABASE.MY_SCHEMA.' || t.TABLE_NAME,
            REF_ENTITY_DOMAIN => 'TABLE'
        ))
        QUALIFY ROW_NUMBER() OVER (PARTITION BY METRIC_NAME ORDER BY MEASUREMENT_TIME DESC) = 1
    ) r
)
SELECT
  ROUND((COUNT_IF(VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0), 1) AS health_pct,
  COUNT_IF(VALUE > 0) AS failing_metrics,
  COUNT(*) AS total_metrics
FROM all_metrics;
```

**Interpretation:**
- 100% = All metrics passing (perfect health)
- 90-99% = Minor issues (good health)
- 75-89% = Moderate issues (needs attention)
- <75% = Significant issues (critical)

### 9. SLA Enforcement

Set quality SLAs and alert when violated:

```sql
-- Alert if schema health drops below 90%
-- Uses SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS() table function
-- See templates/schema-sla-alert.sql for the full production-ready template
CREATE ALERT my_schema_sla_alert
  WAREHOUSE = compute_wh
  SCHEDULE = '60 MINUTE'
IF (EXISTS (
  WITH table_list AS (
    SELECT TABLE_NAME
    FROM MY_DATABASE.INFORMATION_SCHEMA.TABLES
    WHERE TABLE_CATALOG = 'MY_DATABASE'
      AND TABLE_SCHEMA = 'MY_SCHEMA'
      AND TABLE_TYPE = 'BASE TABLE'
  ),
  all_metrics AS (
    SELECT t.TABLE_NAME, r.VALUE, r.MEASUREMENT_TIME
    FROM table_list t,
    LATERAL (
      SELECT *
      FROM TABLE(SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS(
        REF_ENTITY_NAME => 'MY_DATABASE.MY_SCHEMA.' || t.TABLE_NAME,
        REF_ENTITY_DOMAIN => 'TABLE'
      ))
      QUALIFY ROW_NUMBER() OVER (PARTITION BY METRIC_NAME ORDER BY MEASUREMENT_TIME DESC) = 1
    ) r
  ),
  health_check AS (
    SELECT ROUND((COUNT_IF(VALUE = 0) * 100.0) / NULLIF(COUNT(*), 0), 1) AS health_pct
    FROM all_metrics
  )
  SELECT 1 FROM health_check WHERE health_pct < 90
))
THEN CALL send_notification('Schema health SLA violated!');
```

### 10. Regression Detection

Compare current quality vs. previous run:

```sql
-- Detect tables with quality degradation
-- Uses SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS() table function
-- See templates/schema-regression-detection.sql for the full production-ready template
WITH table_list AS (
    SELECT TABLE_NAME
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_CATALOG = 'MY_DATABASE'
      AND TABLE_SCHEMA = 'MY_SCHEMA'
      AND TABLE_TYPE = 'BASE TABLE'
),
all_metrics AS (
    SELECT t.TABLE_NAME, r.METRIC_NAME, r.REFERENCE_ID, r.VALUE, r.MEASUREMENT_TIME
    FROM table_list t,
    LATERAL (
        SELECT *
        FROM TABLE(SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS(
            REF_ENTITY_NAME => 'MY_DATABASE.MY_SCHEMA.' || t.TABLE_NAME,
            REF_ENTITY_DOMAIN => 'TABLE'
        ))
    ) r
),
measurement_times AS (
    SELECT DISTINCT MEASUREMENT_TIME FROM all_metrics ORDER BY MEASUREMENT_TIME DESC LIMIT 2
),
current_run AS (
    SELECT TABLE_NAME, METRIC_NAME, REFERENCE_ID, VALUE
    FROM all_metrics WHERE MEASUREMENT_TIME = (SELECT MAX(MEASUREMENT_TIME) FROM measurement_times)
),
previous_run AS (
    SELECT TABLE_NAME, METRIC_NAME, REFERENCE_ID, VALUE
    FROM all_metrics WHERE MEASUREMENT_TIME = (SELECT MIN(MEASUREMENT_TIME) FROM measurement_times)
)
SELECT
  c.TABLE_NAME,
  c.METRIC_NAME,
  p.VALUE AS previous_value,
  c.VALUE AS current_value,
  c.VALUE - p.VALUE AS change
FROM current_run c
JOIN previous_run p
    ON c.TABLE_NAME = p.TABLE_NAME
    AND c.METRIC_NAME = p.METRIC_NAME
    AND c.REFERENCE_ID = p.REFERENCE_ID
WHERE c.VALUE > p.VALUE  -- Quality degraded
ORDER BY change DESC;
```

### 11. Within Group (Grouped DMF Monitoring)

The `WITHIN GROUP` clause on DMF associations enables per-group quality metrics. Instead of a single aggregate value for the entire table, Snowflake computes separate metric results for each distinct value of the specified grouping column(s).

**Feature parameter:** `FEATURE_DATA_QUALITY_WITHIN_GROUP` (must be enabled on the account).

**Syntax:**
```sql
ALTER TABLE <table_name>
  ADD DATA METRIC FUNCTION <dmf_name>
    ON (<metric_column>)
    WITHIN GROUP (<group_by_column_1> [, <group_by_column_2>, ...])
    [GROUP LIMIT <numeric_limit>]
    [EXPECTATION <expectation_name> (<condition>)];
```

**Compatible system DMFs:**

| DMF | Example Use Case |
|-----|------------------|
| `SNOWFLAKE.CORE.NULL_COUNT` | Null count per region |
| `SNOWFLAKE.CORE.DUPLICATE_COUNT` | Duplicates per department |
| `SNOWFLAKE.CORE.ACCEPTED_VALUES` | Value validation per category |
| `SNOWFLAKE.CORE.ROW_COUNT` | Row count per segment |

**NOT compatible with WITHIN GROUP:**
- `SNOWFLAKE.CORE.FRESHNESS` — not meaningful per-group (freshness is table-level)
- `SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT` — multi-table join based
- `ANOMALY_DETECTION = TRUE` — incompatible with grouped evaluation
- Schema-level DMF associations (`ALTER SCHEMA`) — cannot use WITHIN GROUP

**GROUP LIMIT:** Caps the number of distinct group values evaluated per measurement. Recommended when the grouping column has high cardinality (e.g., user_id).

**EXPECTATION with WITHIN GROUP:** Per-group pass/fail thresholds. `SYSTEM$EVALUATE_DATA_QUALITY_EXPECTATIONS` returns one row per (expectation, group_value) combination with a `GROUP_BY_VALUES` column (VARIANT containing column:value pairs).

**Custom DMF body restrictions with WITHIN GROUP:**
Custom DMFs used with WITHIN GROUP must NOT contain:
- CTE bodies (WITH clauses)
- Multi-table joins (comma-joins, explicit JOINs)
- UNION operations
- SELECT DISTINCT
- Window functions

These are rejected at ALTER TABLE ADD time with error 510189 when validation is enabled.

**Example:**
```sql
-- Track null count per region
ALTER TABLE my_db.my_schema.sales
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT
    ON (customer_email)
    WITHIN GROUP (region);

-- Track duplicates per region and category with a limit
ALTER TABLE my_db.my_schema.sales
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.DUPLICATE_COUNT
    ON (product_id)
    WITHIN GROUP (region, category)
    GROUP LIMIT 100;

-- With per-group expectation (zero nulls per region)
ALTER TABLE my_db.my_schema.sales
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT
    ON (customer_email)
    WITHIN GROUP (region)
    EXPECTATION zero_nulls (value = 0);
```

**Querying per-group results:**
```sql
-- Results include GROUP_BY_INFO column for grouped DMFs
SELECT MEASUREMENT_TIME, METRIC_NAME, VALUE, GROUP_BY_INFO
FROM TABLE(SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS(
    REF_ENTITY_NAME => 'MY_DB.MY_SCHEMA.SALES',
    REF_ENTITY_DOMAIN => 'table'
))
WHERE GROUP_BY_INFO IS NOT NULL
ORDER BY MEASUREMENT_TIME DESC;

-- Filter results by specific group value
SELECT *
FROM TABLE(SYSTEM$DATA_METRIC_SCAN(
    REF_ENTITY_NAME     => 'MY_DB.MY_SCHEMA.SALES',
    WITHIN_GROUP_VALUES => PARSE_JSON('{"region": "US-EAST"}')
));
```

## Privilege Requirements

| Operation | Required Privilege |
|-----------|-------------------|
| Create DMF | CREATE DATA METRIC FUNCTION on schema |
| Attach DMF to table | MODIFY on table |
| View DMF references | SELECT on `INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES()` (per table) |
| View DMF results | Access to `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS()` |
| View DMF usage/credits | Access to `SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_USAGE_HISTORY` |
| Create alerts | CREATE ALERT on schema + EXECUTE TASK |

## Best Practices

1. **Start with system DMFs** - Use built-in metrics before creating custom ones
2. **Attach at schema level** - Automatically monitor all tables in a schema
3. **Run preflight check first** - Always run `preflight-check.sql` before any workflow
4. **Set appropriate schedules** - Balance freshness vs. compute costs
5. **Define SLAs upfront** - Know what "healthy" means for your data
6. **Test custom DMFs** - Validate logic before attaching to production tables
7. **Monitor compute usage** - DMFs consume warehouse credits (check `DATA_QUALITY_MONITORING_USAGE_HISTORY`)

## DMF Verification (CRITICAL)

**Always verify DMFs are attached and functioning:**

```sql
-- Check if DMFs are attached to a specific table
SELECT *
FROM TABLE(INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES(
    REF_ENTITY_NAME => 'MY_DATABASE.MY_SCHEMA.MY_TABLE',
    REF_ENTITY_DOMAIN => 'TABLE'
));
```

**If no rows returned:**
- No DMFs attached to this table
- Schema health queries will return empty results
- User needs to attach DMFs first

```sql
-- Check if DMF results exist
SELECT COUNT(*) AS result_count
FROM TABLE(SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS(
    REF_ENTITY_NAME => 'MY_DATABASE.MY_SCHEMA.MY_TABLE',
    REF_ENTITY_DOMAIN => 'TABLE'
));
```

**If result_count = 0:**
- DMFs are attached but haven't run yet
- Wait for the next scheduled run (check SCHEDULE_STATUS)
- Only current snapshot is available after first run

## Workflow Integration

```
                    ┌─────────────────────┐
                    │   Define DMFs       │
                    │  (System + Custom)  │
                    └──────────┬──────────┘
                               │
                               ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│  Attach DMFs    │──▶│  Set Schedule   │──▶│  Enable Results │
│  to Tables      │   │ (Trigger/Cron)  │   │    Tracking     │
└─────────────────┘   └─────────────────┘   └────────┬────────┘
                                                     │
                                                     ▼
                                            ┌─────────────────┐
                                            │   Monitor &     │
                                            │  Alert on SLAs  │
                                            └─────────────────┘
```

## Common Patterns

### Pattern 1: Schema Health Dashboard
1. Attach DMFs to all tables in schema
2. Run `preflight-check.sql` to verify setup
3. Query schema health score periodically using `SNOWFLAKE.LOCAL`
4. Visualize trends in dashboard

### Pattern 2: Automated Quality Gates
1. Define quality SLAs (e.g., 95% health)
2. Create alerts for SLA violations
3. Integrate with CI/CD pipelines
4. Block deployments if quality degrades

### Pattern 3: Root Cause Analysis
1. Detect schema health drop
2. Query failing tables and metrics
3. Drill down to column-level issues
4. Remediate data quality problems

## Next Steps

After understanding DMF concepts:

1. **For schema health checks**: Use `schema-health-snapshot.sql` template
2. **For root cause analysis**: Use `schema-root-cause.sql` template
3. **For regression detection**: Use `schema-regression-detection.sql` template
4. **For SLA enforcement**: Use `schema-sla-alert.sql` template
5. **For trend analysis**: Use `schema-quality-trends.sql` template
