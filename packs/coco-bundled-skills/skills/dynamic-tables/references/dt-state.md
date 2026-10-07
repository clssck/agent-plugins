# Dynamic Table State Reference

Two sources provide current state information for dynamic tables. They have **different column schemas** — do not mix columns between them.

## When to Use Which Source

| Use case | Source | Why |
|----------|--------|-----|
| Refresh mode (`FULL` vs `INCREMENTAL`) | `SHOW DYNAMIC TABLES` | Only source with `refresh_mode` and `refresh_mode_reason` |
| Warehouse assignment | `SHOW DYNAMIC TABLES` | Only source with `warehouse` |
| DT definition / SQL text | `SHOW DYNAMIC TABLES` | Only source with `text` |
| Row count, byte size | `SHOW DYNAMIC TABLES` | Only source with `rows`, `bytes` |
| Lag metrics (mean, max, % in target) | `INFORMATION_SCHEMA.DYNAMIC_TABLES()` | Only source with `mean_lag_sec`, `maximum_lag_sec`, `time_within_target_lag_ratio` |
| Last refresh outcome | `INFORMATION_SCHEMA.DYNAMIC_TABLES()` | Only source with `last_completed_refresh_state` |
| Account-wide DT listing | `INFORMATION_SCHEMA.DYNAMIC_TABLES()` | Account-scoped; `SHOW` is schema-scoped |
| Connected DTs (pipeline view) | `INFORMATION_SCHEMA.DYNAMIC_TABLES()` | Only source with `INCLUDE_CONNECTED` parameter |
| Quick single-DT check | Either | Both work; `SHOW` is simpler |

---

## SHOW DYNAMIC TABLES

Configuration, refresh mode, warehouse, and basic state.

### Syntax

```sql
SHOW DYNAMIC TABLES [ LIKE '<pattern>' ] [ IN SCHEMA <database>.<schema> ];
SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
```

### Columns

These are the **only** columns available from `SHOW DYNAMIC TABLES`:

| Column | Type | Description |
|--------|------|-------------|
| `name` | STRING | Dynamic table name |
| `database_name` | STRING | Database containing DT |
| `schema_name` | STRING | Schema containing DT |
| `warehouse` | STRING | Warehouse used for refreshes |
| `refresh_mode` | STRING | `FULL` or `INCREMENTAL` |
| `refresh_mode_reason` | STRING | Why this mode was chosen |
| `scheduling_state` | STRING | `ACTIVE` or `SUSPENDED` (plain string) |
| `target_lag` | STRING | Target lag as string (e.g., `5 minutes`) |
| `data_timestamp` | TIMESTAMP | Data freshness timestamp |
| `text` | STRING | DT definition SQL |
| `rows` | NUMBER | Current row count |
| `bytes` | NUMBER | Current size in bytes |
| `last_suspended_on` | TIMESTAMP | When last suspended (if applicable) |

### Examples

```sql
-- All DTs in a schema
SHOW DYNAMIC TABLES IN SCHEMA <database>.<schema>;

-- Specific DT
SHOW DYNAMIC TABLES LIKE '<dt_name>' IN SCHEMA <database>.<schema>;

-- Get refresh mode details via RESULT_SCAN
SHOW DYNAMIC TABLES LIKE '<dt_name>' IN SCHEMA <database>.<schema>;
SELECT "name", "refresh_mode", "refresh_mode_reason", "scheduling_state", "warehouse"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
```

---

## INFORMATION_SCHEMA.DYNAMIC_TABLES()

Lag metrics, refresh status, and aggregate statistics.

**Reference**: https://docs.snowflake.com/en/sql-reference/functions/dynamic_tables

### Scope

**This function is ACCOUNT-SCOPED** — it returns dynamic tables from ALL databases visible to your current role, not just the current database.

### Syntax

```sql
SELECT * FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES(
  [ NAME => '<string>' ]
  [ , REFRESH_DATA_TIMESTAMP_START => <constant_expr> ]
  [ , RESULT_LIMIT => <integer> ]
  [ , INCLUDE_CONNECTED => { TRUE | FALSE } ]
));
```

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `NAME` | - | Optional. Name of a dynamic table (case-insensitive). Can be unqualified (`dt_name`), partially qualified (`schema.dt_name`), or fully qualified (`db.schema.dt_name`) |
| `REFRESH_DATA_TIMESTAMP_START` | 7 days ago | Optional. TIMESTAMP_LTZ for computing lag metrics. Includes refreshes with `LATEST_DATA_TIMESTAMP >= REFRESH_DATA_TIMESTAMP_START` |
| `RESULT_LIMIT` | 100 | Optional. Max rows returned (range: 1-10000). Results are sorted by last completed refresh state: FAILED → UPSTREAM_FAILED → SKIPPED → SUCCEEDED → CANCELED |
| `INCLUDE_CONNECTED` | FALSE | Optional. When TRUE, returns metadata for all DTs connected to the DT specified by NAME. Requires NAME, cannot use with RESULT_LIMIT |

**⚠️ RESULT_LIMIT GUIDANCE**: 
- **Always use `RESULT_LIMIT => 10000`** unless:
  1. You're querying a specific DT by fully qualified `NAME` (e.g., `NAME => 'DB.SCHEMA.MY_DT'`)
  2. You're just checking if any DTs exist (not counting total)
- The default is 100, so queries without `RESULT_LIMIT` will silently truncate results
- If you see exactly 100 rows, you're hitting the default limit — add `RESULT_LIMIT => 10000`
- If you see exactly 10,000 rows, you're hitting the max limit — inform the user there are more than 10k dynamic tables and use `SHOW DYNAMIC TABLES IN DATABASE <db>` or `SHOW DYNAMIC TABLES IN SCHEMA <db.schema>` to count by database/schema

**⚠️ SORTING/FILTERING**: To sort by a different order or apply filters across all DTs, you must specify a large `RESULT_LIMIT` value first. The default sorting/limit is applied before any ORDER BY or WHERE clauses.

### Columns

These are the **only** columns available from `INFORMATION_SCHEMA.DYNAMIC_TABLES()`. Do **not** use `warehouse`, `refresh_mode`, `refresh_mode_reason`, `target_lag`, `text`, `rows`, or `bytes` — those exist only in `SHOW DYNAMIC TABLES`.

| Column | Type | Description |
|--------|------|-------------|
| `name` | STRING | Dynamic table name |
| `database_name` | STRING | Database containing DT |
| `schema_name` | STRING | Schema containing DT |
| `qualified_name` | STRING | Fully qualified name |
| `target_lag_sec` | NUMBER | Target lag in seconds |
| `target_lag_type` | STRING | USER_DEFINED or DOWNSTREAM |
| `mean_lag_sec` | NUMBER | Average observed lag |
| `maximum_lag_sec` | NUMBER | Longest observed lag |
| `time_above_target_lag_sec` | NUMBER | Total seconds above target lag |
| `time_within_target_lag_ratio` | FLOAT | % of time meeting lag (0-1) |
| `latest_data_timestamp` | TIMESTAMP | Data freshness timestamp |
| `last_completed_refresh_state` | STRING | `SUCCEEDED`, `FAILED`, `UPSTREAM_FAILED`, `SKIPPED`, `CANCELED` |
| `last_completed_refresh_state_code` | STRING | Error code if failed |
| `last_completed_refresh_state_message` | STRING | Error message if failed |
| `scheduling_state` | STRING | JSON object — extract `:"STATE"` for `ACTIVE` or `SUSPENDED` |

**Key difference — `scheduling_state` format:**
- **SHOW:** plain string — `ACTIVE` or `SUSPENDED`
- **INFORMATION_SCHEMA:** JSON object — extract with `scheduling_state:"STATE"` → `ACTIVE` or `SUSPENDED`

### Examples

```sql
USE DATABASE ANY_DB;  -- Any database works, just need context to execute

-- Count all DTs in account (ALWAYS use RESULT_LIMIT for counting)
SELECT COUNT(*) as total_dynamic_tables
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES(RESULT_LIMIT => 10000));

-- List all DTs in account with status
SELECT name, database_name, schema_name, scheduling_state, 
       last_completed_refresh_state, time_within_target_lag_ratio
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES(RESULT_LIMIT => 10000))
ORDER BY database_name, schema_name, name;

-- Specific DT with full details
SELECT *
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES(
  NAME => 'MY_DB.MY_SCHEMA.MY_DT'
));

-- Get all DTs connected to a specific DT (pipeline/DAG view)
SELECT name, target_lag_sec, mean_lag_sec, latest_data_timestamp
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES(
  NAME => 'MY_DB.MY_SCHEMA.MY_DT',
  INCLUDE_CONNECTED => TRUE
))
ORDER BY target_lag_sec;

-- DTs with issues (account-wide) - must use high RESULT_LIMIT to filter all
SELECT name, database_name, schema_name, scheduling_state, 
       last_completed_refresh_state, last_completed_refresh_state_message
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES(RESULT_LIMIT => 10000))
WHERE last_completed_refresh_state != 'SUCCEEDED'
   OR time_within_target_lag_ratio < 0.9;

-- Compute lag metrics for a specific time window
SELECT name, mean_lag_sec, maximum_lag_sec, time_within_target_lag_ratio
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES(
  REFRESH_DATA_TIMESTAMP_START => DATEADD('day', -1, CURRENT_TIMESTAMP()),
  RESULT_LIMIT => 10000
));
```
