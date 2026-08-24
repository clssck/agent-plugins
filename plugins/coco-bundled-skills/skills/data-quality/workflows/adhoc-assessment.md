---
parent_skill: data-quality
---

# Workflow: Ad-Hoc Quality Assessment

Use when DMFs are not attached, or when the user wants a one-time snapshot of data quality
without requiring any monitoring setup. Works for any Snowflake tables, schemas, or
Marketplace / private listing data products.

## Trigger Phrases
- "check quality of my tables" (without DMFs set up)
- "how good is my data"
- "quality of my listing"
- "check listing health / freshness / completeness"
- "assess listing data quality"
- "consumer data quality"
- "provider data quality"
- "one-time quality check"
- "quick quality scan"

## When to Load
- Step 0 preflight detects `total_dmfs_attached = 0`  AND user chose ad-hoc assessment
- User explicitly asks for a listing quality check or one-time assessment

---

## Execution Steps

### Step 1: Detect Context

Determine what the user is assessing and whether this is a listing or a regular schema.

**1a. Check for listing context** — try `SHOW LISTINGS`:

```sql
SHOW LISTINGS;
```

- If results returned → user is a **provider**. Ask which listing to assess if not specified.
- If error / empty → not a provider. Check if user is a **consumer** (imported database):

```sql
SHOW DATABASES;
```

Filter for databases where `origin` is populated (created from a share).

- If neither → user is asking about a **regular schema**. Ask for `DATABASE.SCHEMA`.

**1b. Extract the target scope:**

For providers, after `SHOW LISTINGS` use fuzzy matching if the user provided a name:

```sql
SHOW LISTINGS LIKE '%<listing_name>%';
```

Then get full listing details:

```sql
DESCRIBE LISTING <listing_name>;
```

Extract: `title`, `state` (DRAFT / PUBLISHED), `share_name`, `created_on`.

| Context | What to Extract |
|---------|----------------|
| Provider listing | `listing_name`, `title`, `state`, `share_name`, underlying database |
| Consumer listing | The imported database name |
| Regular schema | `DATABASE.SCHEMA` |

**Output:** Target database, schema (or share object list), role (provider / consumer / regular), and listing title/state if applicable.

---

### Step 2: Discover Tables and Columns

**For provider listings** — get objects granted to the share:

```sql
SHOW GRANTS TO SHARE <share_name>;
```

Filter to TABLE and VIEW objects. Skip `_HISTORY` and `_PIT` table variants.

**For consumers and regular schemas:**

```sql
SELECT TABLE_NAME, TABLE_TYPE, ROW_COUNT, LAST_ALTERED
FROM <database>.INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA NOT IN ('INFORMATION_SCHEMA')
  AND TABLE_NAME NOT LIKE '%_HISTORY'
  AND TABLE_NAME NOT LIKE '%_PIT'
ORDER BY TABLE_NAME;
```

**For all contexts** — get column metadata for all discovered tables:

```sql
SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE
FROM <database>.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = '<schema>'
  AND TABLE_NAME IN (<discovered_tables>)
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

**Classify each column by type:**
- **Timestamp/Date**: DATE, TIMESTAMP_NTZ, TIMESTAMP_LTZ, TIMESTAMP_TZ → run FRESHNESS + FUTURE_TIMESTAMP_COUNT (if available; DATE, TIMESTAMP_LTZ, TIMESTAMP_TZ only)
- **VARCHAR**: run NULL_PERCENT + BLANK_PERCENT + UNTRIMMED_STRING_COUNT + STRING_LENGTH_MIN/MAX (if available)
- **Numeric**: NUMBER, FLOAT, DECIMAL → run NULL_PERCENT + AVG/MIN/MAX/STDDEV + ZERO_COUNT + NEGATIVE_COUNT + VARIANCE + MEDIAN (if available)
- **Boolean**: SQL fallback only (`COUNT(*) - COUNT(col)` for nulls — DMFs not supported)
- **All columns**: NULL_COUNT, NULL_PERCENT (except BOOLEAN)

> **Note:** Some extended DMFs (FUTURE_TIMESTAMP_COUNT, UNTRIMMED_STRING_COUNT, STRING_LENGTH_*, ZERO_COUNT, NEGATIVE_COUNT, VARIANCE, MEDIAN, INVALID_JSON_COUNT, etc.) may not be available in all deployments. If a DMF call fails, fall back to equivalent SQL per the error handling rules below.

**Classify each column by business importance:**
- **Critical**: columns ending in `_ID`, first column of table, or named like primary keys
- **Standard**: columns named DATE, STATUS, NAME, EMAIL, TOTAL, AMOUNT, PRICE
- **Optional**: columns named RATING, SCORE, REVIEW, ESTIMATE, COMMENT, NOTES, or supplementary metrics

> Internal classification only — do NOT show importance labels to the user.

**Output:** Complete inventory of all tables and their columns with type and importance classification.

---

### Step 3: Run Ad-Hoc Quality Metrics

> Read `templates/adhoc-column-quality.sql` for the exact DMF call patterns.

Run metrics per column using `SNOWFLAKE.CORE.*` system DMFs called inline.
Do NOT require DMFs to be pre-attached. These are standalone ad-hoc calls.

**⚠️ CRITICAL: `_PERCENT` DMFs return values already on the 0–100 scale.**
`0.796800` means **0.8%**, NOT 79.68%. Always validate: `NULL_COUNT / row_count` should match `NULL_PERCENT / 100`.

#### Per-column metric calls:

**Freshness** (timestamp/date columns only):
```sql
SELECT SNOWFLAKE.CORE.FRESHNESS(SELECT <col> FROM <db>.<schema>.<table>);
```
Returns seconds since the most recent value.

**Null analysis** (all non-BOOLEAN columns):
```sql
SELECT SNOWFLAKE.CORE.NULL_COUNT(SELECT <col> FROM <db>.<schema>.<table>);
SELECT SNOWFLAKE.CORE.NULL_PERCENT(SELECT <col> FROM <db>.<schema>.<table>);
```

**Blank detection** (VARCHAR columns only):
```sql
SELECT SNOWFLAKE.CORE.BLANK_COUNT(SELECT <col> FROM <db>.<schema>.<table>);
SELECT SNOWFLAKE.CORE.BLANK_PERCENT(SELECT <col> FROM <db>.<schema>.<table>);
```

**Uniqueness** (Critical columns / ID columns only):
```sql
SELECT SNOWFLAKE.CORE.DUPLICATE_COUNT(SELECT <col> FROM <db>.<schema>.<table>);
SELECT SNOWFLAKE.CORE.UNIQUE_COUNT(SELECT <col> FROM <db>.<schema>.<table>);
```

**Accepted values** (categorical, range, or format validation — any column type):
Use `SYSTEM$DATA_METRIC_SCAN` to run `ACCEPTED_VALUES` ad-hoc without attaching a DMF. Returns the actual violating rows.
```sql
-- Categorical: rows where status is not in allowed set
SELECT * FROM TABLE(SYSTEM$DATA_METRIC_SCAN(
    REF_ENTITY_NAME => '<db>.<schema>.<table>',
    METRIC_NAME => 'SNOWFLAKE.CORE.ACCEPTED_VALUES',
    ARGUMENT_NAME => '<col>',
    ARGUMENT_EXPRESSION => '<col> IN (''Val1'', ''Val2'')'
));
-- Numeric range: rows where price is not positive
SELECT * FROM TABLE(SYSTEM$DATA_METRIC_SCAN(
    REF_ENTITY_NAME => '<db>.<schema>.<table>',
    METRIC_NAME => 'SNOWFLAKE.CORE.ACCEPTED_VALUES',
    ARGUMENT_NAME => '<col>',
    ARGUMENT_EXPRESSION => '<col> > 0'
));
-- Format (RLIKE): rows with invalid email
SELECT * FROM TABLE(SYSTEM$DATA_METRIC_SCAN(
    REF_ENTITY_NAME => '<db>.<schema>.<table>',
    METRIC_NAME => 'SNOWFLAKE.CORE.ACCEPTED_VALUES',
    ARGUMENT_NAME => '<col>',
    ARGUMENT_EXPRESSION => '<col> RLIKE ''^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'''
));
```

**Referential integrity** (FK columns that reference another table):
After attaching `REFERENTIAL_INTEGRITY_COUNT` via `ALTER TABLE`, use `SYSTEM$DATA_METRIC_SCAN` to retrieve the actual violating rows (not just the count). NULL FK values are excluded.
```sql
-- Prerequisite: attach the DMF first
-- ALTER TABLE <db>.<schema>.<table> ADD DATA METRIC FUNCTION
--   SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT ON (<fk_col>, TABLE(<ref_table>(<ref_col>)));

-- Single-column FK: find rows where fk_col has no match in reference table
SELECT * FROM TABLE(SYSTEM$DATA_METRIC_SCAN(
    REF_ENTITY_NAME => '<db>.<schema>.<table>',
    METRIC_NAME => 'SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT',
    ARGUMENT_NAME => '<fk_col>'
));
-- Compound key FK: find rows where (col1, col2) has no match in reference table
SELECT * FROM TABLE(SYSTEM$DATA_METRIC_SCAN(
    REF_ENTITY_NAME => '<db>.<schema>.<table>',
    METRIC_NAME => 'SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT',
    ARGUMENT_NAME => '<fk_col1>, <fk_col2>'
));
```

**Numeric statistics** (NUMBER, FLOAT, DECIMAL columns):
```sql
SELECT SNOWFLAKE.CORE.AVG(SELECT <col> FROM <db>.<schema>.<table>);
SELECT SNOWFLAKE.CORE.MIN(SELECT <col> FROM <db>.<schema>.<table>);
SELECT SNOWFLAKE.CORE.MAX(SELECT <col> FROM <db>.<schema>.<table>);
SELECT SNOWFLAKE.CORE.STDDEV(SELECT <col> FROM <db>.<schema>.<table>);
```

**Extended numeric validation** (NUMBER, FLOAT — if available):
```sql
SELECT SNOWFLAKE.CORE.ZERO_COUNT(SELECT <col> FROM <db>.<schema>.<table>);
SELECT SNOWFLAKE.CORE.NEGATIVE_COUNT(SELECT <col> FROM <db>.<schema>.<table>);
SELECT SNOWFLAKE.CORE.VARIANCE(SELECT <col> FROM <db>.<schema>.<table>);
SELECT SNOWFLAKE.CORE.MEDIAN(SELECT <col> FROM <db>.<schema>.<table>);
SELECT SNOWFLAKE.CORE.APPROX_QUANTILE_25(SELECT <col> FROM <db>.<schema>.<table>);
SELECT SNOWFLAKE.CORE.APPROX_QUANTILE_50(SELECT <col> FROM <db>.<schema>.<table>);
SELECT SNOWFLAKE.CORE.APPROX_QUANTILE_99(SELECT <col> FROM <db>.<schema>.<table>);
```

**String length analysis** (VARCHAR columns — if available):
```sql
SELECT SNOWFLAKE.CORE.STRING_LENGTH_MIN(SELECT <col> FROM <db>.<schema>.<table>);
SELECT SNOWFLAKE.CORE.STRING_LENGTH_MAX(SELECT <col> FROM <db>.<schema>.<table>);
SELECT SNOWFLAKE.CORE.STRING_LENGTH_AVG(SELECT <col> FROM <db>.<schema>.<table>);
```

**String/format validation** (VARCHAR columns — if available):
```sql
SELECT SNOWFLAKE.CORE.UNTRIMMED_STRING_COUNT(SELECT <col> FROM <db>.<schema>.<table>);
SELECT SNOWFLAKE.CORE.INVALID_NUMERIC_TYPE_CAST_COUNT(SELECT <col> FROM <db>.<schema>.<table>);
SELECT SNOWFLAKE.CORE.SPECIAL_CHARACTER_COUNT(SELECT <col> FROM <db>.<schema>.<table>);
SELECT SNOWFLAKE.CORE.CASE_FORMAT_VIOLATION_COUNT(SELECT <col> FROM <db>.<schema>.<table>);
```

**JSON validation** (VARCHAR columns with JSON-like data — if available):
```sql
SELECT SNOWFLAKE.CORE.INVALID_JSON_COUNT(SELECT <col> FROM <db>.<schema>.<table>);
```

**Temporal validation** (DATE, TIMESTAMP_LTZ, TIMESTAMP_TZ columns — if available):
```sql
SELECT SNOWFLAKE.CORE.FUTURE_TIMESTAMP_COUNT(SELECT <col> FROM <db>.<schema>.<table>);
```

**Boolean column null fallback** (BOOLEAN columns — DMFs not supported):
```sql
SELECT COUNT(*) - COUNT(<col>) AS null_count FROM <db>.<schema>.<table>;
```

**If a DMF call fails** (e.g., permissions, unsupported type):
- Fall back to equivalent SQL
- Note the fallback in results but do not fail the assessment

**Completeness thresholds by importance tier (internal — do not show to user):**
- **Critical columns**: Flag any with **> 0%** nulls/blanks — these matter most
- **Standard columns**: Flag any with **> 5%** nulls/blanks
- **Optional columns**: Flag any with **> 50%** nulls (informational only; does not affect pass/fail)

**Scoring rules (internal — do not show to user):**
- **Pass (≥ 80%)**: All critical columns clean AND no critical uniqueness failures
- **Warning (60–80%)**: Issues in standard columns OR minor issues (< 5%) in critical columns
- **Fail (< 60%)**: Any critical column > 5% issues OR critical ID column has ≥ 5% duplicates

---

### Step 4: Present Quality Report

Present the listing/schema-level summary:

```
## Data Quality Report: <listing_title or DATABASE.SCHEMA>

**Scope:** <listing name / schema> | **State:** <DRAFT / PUBLISHED — omit for non-listings> | **Tables:** <count> | **Total Rows:** <sum> | **Assessed:** <date>

### Overall Quality Score: <X>% — PASS / WARNING / FAIL

| Dimension    | Status   | Summary                                        |
|--------------|----------|------------------------------------------------|
| Freshness    | 🟢/🟡/🔴 | Most recent data: <X> ago, stalest: <Y> ago   |
| Completeness | 🟢/🟡/🔴 | <X> columns clean, <Y> issues noted            |
| Uniqueness   | 🟢/🟡/🔴 | <X> key columns verified, <Y> duplicates found |

**Status thresholds:**
- Freshness: 🟢 < 1 day | 🟡 1–7 days | 🔴 > 7 days
- Completeness: 🟢 < 5% nulls in critical columns | 🟡 5–20% | 🔴 > 20%
- Uniqueness: 🟢 no duplicates in critical IDs | 🟡 < 5% | 🔴 ≥ 5%

### Table Overview (up to 8 tables)

| Table      | Rows    | Freshness        | Issues |
|------------|---------|------------------|--------|
| <table_1>  | <count> | <human-readable> | None   |
| <table_2>  | <count> | <human-readable> | 2      |

### Warnings
<List optional-column issues here if any — e.g., "<col> in <table> is 59% null (informational)". Omit section if none.>

### Key Findings
1. **Freshness**: <which tables are fresh or stale>
2. **Completeness**: <critical column issues, then standard>
3. **Uniqueness**: <key column status>
4. **Recommendations**: <actionable items>
```

**After presenting**, ask:

> "Would you like to drill into the quality details for a specific table?
> Available: [list table names]"

**⚠️ STOP HERE and wait for user response.**

---

### Step 5: Per-Table Drill-Down (On Request)

When the user asks about a specific table, provide column-level detail.

First fetch the full column inventory including defaults and comments:

```sql
SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COMMENT
FROM <database>.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = '<schema>'
  AND TABLE_NAME = '<table>'
ORDER BY ORDINAL_POSITION;
```

Then run the per-column DMF calls from Step 3, and present:

```
## Quality Detail: <table_name>

**Rows:** <count> | **Columns:** <count> | **Last Altered:** <date>
**Freshness:** <human-readable> (via <timestamp_col>)

### Column-Level Quality

| Column    | Type      | Nulls | Null % | Blanks | Blank % | Duplicates | Unique |
|-----------|-----------|-------|--------|--------|---------|------------|--------|
| <col_1>   | VARCHAR   | 0     | 0.0%   | 2      | 1.5%    | —          | —      |
| <col_2>   | NUMBER    | 5     | 3.8%   | —      | —       | 0          | 125    |

### Numeric Statistics

| Column   | Min  | Max    | Avg   | Std Dev |
|----------|------|--------|-------|---------|
| <col_1>  | 0.5  | 1000.0 | 245.3 | 102.7   |
```

After presenting, ask if they want to explore another table.

---

### Step 6: Offer Continuous Monitoring

After presenting the results (Step 4 or 5), always offer to set up ongoing monitoring:

> "This was a one-time snapshot. Would you like me to set up continuous DMF monitoring so
> you get notified automatically when quality drops?
> 
> With DMFs attached, you'll get: trend history, regression detection, and SLA alerts."

If user says yes → guide them to attach DMFs:
```sql
-- Attach core DMFs to a table
ALTER TABLE <db>.<schema>.<table>
  SET DATA_METRIC_SCHEDULE = 'TRIGGER_ON_CHANGES';

ALTER TABLE <db>.<schema>.<table>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT ON (<column>);

ALTER TABLE <db>.<schema>.<table>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.DUPLICATE_COUNT ON (<id_column>);
```

Then load `workflows/sla-alerting.md` if they want automated alerts.

---

## Stopping Points
- ✋ **Step 1**: Multiple listings exist and user didn't specify — ask which one
- ✋ **Step 4**: After listing/schema summary — wait for drill-down request
- ✋ **Step 5**: After per-table detail — wait for next table or end
- ✋ **Step 6**: Before attaching DMFs — confirm which tables and columns to monitor

## Error Handling

| Issue | Resolution |
|-------|-----------|
| DMF call fails on shared/imported data | Fall back to equivalent SQL (e.g., `COUNT(*) - COUNT(col)` for nulls) |
| No timestamp columns | Use `LAST_ALTERED` from INFORMATION_SCHEMA as freshness proxy |
| Very large tables (>1B rows) | Inform user, offer to sample: `SELECT ... FROM table SAMPLE (10 PERCENT)` |
| `_PERCENT` returns unexpected large value | Validate with `NULL_COUNT / row_count` — `_PERCENT` is already 0-100 scale |
| Consumer can't see listing metadata | Query the imported database via INFORMATION_SCHEMA directly |
