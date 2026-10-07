# Refresh Analysis Reference

How to understand what happened in a dynamic table refresh and how to analyze its performance. Covers the available data sources, refresh history schema, how to interpret results, and privilege requirements.

---

## Query Performance Data Sources

Once you have a `query_id` from refresh history, four data sources exist for deeper analysis. They are **not interchangeable** — each serves a different purpose:

| Source | What it provides | Latency | Key privilege |
|---|---|---|---|
| `DYNAMIC_TABLE_REFRESH_HISTORY()` | Refresh outcome, refresh action, trigger, `query_id`, warehouse name, and `statistics` JSON with DT-specific metrics | **Real-time** | MONITOR or OWNERSHIP on the DT |
| `GET_QUERY_OPERATOR_STATS(query_id)` | **Operator-level breakdown** — which joins, scans, aggregations are expensive, execution time per operator, input/output rows per operator | Real-time (14-day window) | **MONITOR or OPERATE on the warehouse** |
| `INFORMATION_SCHEMA.QUERY_HISTORY_BY_WAREHOUSE()` | Query-level I/O metrics — bytes scanned, partitions scanned vs total (pruning efficiency), spill to local/remote, warehouse size, credits. Since `DYNAMIC_TABLE_REFRESH_HISTORY` gives you the warehouse name, use this to look up the refresh query. | **Real-time** (7-day window) | **MONITOR or OPERATE on the warehouse** |
| `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` | Same query-level metrics as `QUERY_HISTORY_BY_WAREHOUSE` but with a **365-day** retention window. Use when the query is outside the 7-day INFORMATION_SCHEMA retention, or when the user lacks MONITOR/OPERATE on the warehouse. | Up to **45-minute latency** | **IMPORTED PRIVILEGES on the SNOWFLAKE database** |

**Use them in this order:**
1. **`DYNAMIC_TABLE_REFRESH_HISTORY`** first — get the `query_id`, warehouse name, confirm refresh type, and extract `statistics` JSON for timing and row-change metrics. **If the user already provided a `query_id`, skip this step** and go directly to step 2. Only call `DYNAMIC_TABLE_REFRESH_HISTORY` if you also need the DT-specific `statistics` metrics.
2. **`GET_QUERY_OPERATOR_STATS`** — this is where real performance debugging happens (identifying which operator is the bottleneck)
3. **`QUERY_HISTORY_BY_WAREHOUSE`** — fallback when operator stats are inaccessible, or to get I/O metrics (bytes scanned, partition pruning, spill) that neither of the above provides. Use the warehouse name from `DYNAMIC_TABLE_REFRESH_HISTORY`.
4. **`SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`** — fallback when the query is outside the 7-day `INFORMATION_SCHEMA` retention window, or when the user lacks MONITOR/OPERATE on the warehouse. Provides the same query-level metrics as `QUERY_HISTORY_BY_WAREHOUSE` but with 365-day retention. Requires **IMPORTED PRIVILEGES on the SNOWFLAKE database** (a separate grant from warehouse privileges). Has up to 45-minute latency for recent queries.

---

## DYNAMIC_TABLE_REFRESH_HISTORY()

Returns per-refresh outcomes: state, duration, refresh action, query_id, and DT-specific statistics.

### Syntax

```sql
SELECT * FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
  [ NAME => '<dt_name>' ]
  [ , NAME_PREFIX => '<database>.<schema>' ]
  [ , ERROR_ONLY => TRUE | FALSE ]
  [ , DATA_TIMESTAMP_START => <timestamp> ]
  [ , DATA_TIMESTAMP_END => <timestamp> ]
  [ , RESULT_LIMIT => <integer> ]
));
```

### Key Columns

| Column | Type | Description |
|--------|------|-------------|
| `name` | STRING | Dynamic table name |
| `state` | STRING | `SUCCEEDED`, `FAILED`, `SKIPPED`, `CANCELLED`, `UPSTREAM_FAILED` |
| `state_code` | STRING | Error code if failed |
| `state_message` | STRING | Error message if failed |
| `refresh_start_time` | TIMESTAMP | When refresh started |
| `refresh_end_time` | TIMESTAMP | When refresh completed |
| `data_timestamp` | TIMESTAMP | Data freshness after refresh |
| `refresh_action` | STRING | `NO_DATA` (no new data in base tables — does not apply to initial refresh), `REINITIALIZE` (changes to base objects — e.g., base table replaced or schema changed, ...), `FULL` (full refresh — query not incrementalizable or full was cheaper), `INCREMENTAL` (normal incremental refresh) |
| `refresh_trigger` | STRING | `SCHEDULED` (normal background refresh), `MANUAL` (user/task ran `ALTER DYNAMIC TABLE ... REFRESH`), `CREATION` (refresh during creation DDL — triggered by `CREATE` or `CREATE OR REPLACE`, or by creation of a downstream consumer DT) |
| `query_id` | STRING | Query ID for performance analysis |
| `statistics` | VARIANT | JSON with DT-specific metrics (see below) |
| `target_lag_sec` | NUMBER | Target lag value for the DT at the time the refresh occurred |
| `graph_history_valid_from` | TIMESTAMP_NTZ | Encodes the `VALID_FROM` timestamp from `DYNAMIC_TABLE_GRAPH_HISTORY` when the refresh occurred — use this to identify which version of a DT (before/after `CREATE OR REPLACE`) a refresh belongs to. NULL if the DT hasn't been created yet. |
| `inputs_with_changed_data` | ARRAY | JSON array of upstream inputs that had changed data for this refresh. Each entry includes `kind`, `name`, and `statistics` with partition-level detail (`numAddedPartitions`, `numRemovedPartitions`, `numRegisteredRows`, `numUnregisteredRows`). NULL for `NO_DATA` refreshes. Use to identify which base table triggered a refresh in multi-input DTs. |
| `reinit_reason` | STRING | Explains why a `REINITIALIZE` refresh occurred. NULL for refresh actions other than `REINITIALIZE`.|

### State Values

| State | Meaning |
|-------|---------|
| `SUCCEEDED` | Refresh completed successfully |
| `FAILED` | Refresh failed with error |
| `SKIPPED` | No changes to process |
| `CANCELLED` | Refresh was cancelled |
| `UPSTREAM_FAILED` | Upstream DT failed |

### Example Queries

```sql
USE DATABASE MY_DB;

-- Recent refresh details with statistics — diagnostic snapshot.
-- Use NAME => '<db>.<schema>.<dt>' for a single DT, or NAME_PREFIX for a schema.
SELECT 
  name,
  data_timestamp,
  refresh_start_time,
  refresh_end_time,
  DATEDIFF('second', refresh_start_time, refresh_end_time) as duration_sec,
  state, state_code, state_message,
  refresh_action, refresh_trigger,
  query_id,
  graph_history_valid_from,
  statistics:"compilationTimeMs"::INT / 1000 as compilation_sec,
  statistics:"executionTimeMs"::INT / 1000 as execution_sec,
  statistics:"numInsertedRows"::INT as rows_inserted,
  statistics:"numDeletedRows"::INT as rows_deleted,
  statistics:"numCopiedRows"::INT as rows_copied,
  statistics:"numAddedPartitions"::INT as partitions_added,
  statistics:"numRemovedPartitions"::INT as partitions_removed
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
  NAME_PREFIX => 'MY_DB.MY_SCHEMA'
))
ORDER BY refresh_start_time DESC
LIMIT 20;

-- Errors only
SELECT name, refresh_start_time, state, state_code, state_message
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
  ERROR_ONLY => TRUE
))
ORDER BY refresh_start_time DESC;

-- Refresh statistics (last 7 days) — canonical steady-state aggregates.
-- Adjust the WHERE window (e.g. DATEADD('hour', -1, ...)) for shorter before/after comparisons.
SELECT 
  name,
  COUNT(*) as total_refreshes,
  AVG(IFF(refresh_action IN ('INCREMENTAL','FULL') AND refresh_trigger != 'CREATION', DATEDIFF('second', refresh_start_time, refresh_end_time), NULL)) as avg_duration_sec,
  MAX(IFF(refresh_action IN ('INCREMENTAL','FULL') AND refresh_trigger != 'CREATION', DATEDIFF('second', refresh_start_time, refresh_end_time), NULL)) as max_duration_sec,
  AVG(IFF(refresh_trigger = 'CREATION' OR refresh_action = 'REINITIALIZE', DATEDIFF('second', refresh_start_time, refresh_end_time), NULL)) as avg_init_duration_sec,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY 
        IFF(refresh_action IN ('INCREMENTAL','FULL') AND refresh_trigger != 'CREATION', DATEDIFF('second', refresh_start_time, refresh_end_time), NULL)) as p95_duration_sec,
  COUNT_IF(refresh_action = 'INCREMENTAL' AND refresh_trigger != 'CREATION') as incremental_count,
  COUNT_IF(refresh_action = 'FULL'        AND refresh_trigger != 'CREATION') as full_count,
  COUNT_IF(refresh_action = 'REINITIALIZE')  as reinitialize_count,
  COUNT_IF(refresh_action = 'NO_DATA')       as no_data_count,
  COUNT_IF(refresh_trigger = 'CREATION')     as creation_count,
  COUNT_IF(state = 'FAILED')                 as failed_count
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(NAME => 'MY_DT'))
WHERE refresh_start_time > DATEADD('day', -7, CURRENT_TIMESTAMP())
GROUP BY name;
```

### `statistics` JSON Fields

The `statistics` column contains a JSON object with DT-specific metrics:

| Field | Description |
|---|---|
| `compilationTimeMs` | Time spent compiling the refresh query (milliseconds) |
| `executionTimeMs` | Time spent executing the refresh query (milliseconds) |
| `numInsertedRows` | Number of rows inserted during this refresh |
| `numDeletedRows` | Number of rows deleted during this refresh |
| `numCopiedRows` | Number of rows copied (unchanged rows rewritten during full refresh) |
| `numAddedPartitions` | Number of micro-partitions added |
| `numRemovedPartitions` | Number of micro-partitions removed |
| `queuedTimeMs` | Time the refresh spent queued before execution (milliseconds) |

**Example query extracting statistics:**
```sql
SELECT 
  query_id,
  refresh_start_time,
  refresh_action,
  DATEDIFF('second', refresh_start_time, refresh_end_time) as duration_sec,
  statistics:"compilationTimeMs"::INT / 1000 as compilation_sec,
  statistics:"executionTimeMs"::INT / 1000 as execution_sec,
  statistics:"numInsertedRows"::INT as rows_inserted,
  statistics:"numDeletedRows"::INT as rows_deleted,
  statistics:"numCopiedRows"::INT as rows_copied,
  statistics:"numAddedPartitions"::INT as partitions_added,
  statistics:"numRemovedPartitions"::INT as partitions_removed
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(name=>'<database>.<schema>.<dt_name>'))
WHERE state = 'SUCCEEDED'
ORDER BY refresh_start_time DESC
LIMIT 1;
```

---

## Interpreting Refresh Categories

Not all refreshes are comparable. Categorize them before analyzing performance:

- **CREATION / REINITIALIZE**: Full recomputation using a FULL refresh strategy, plus row-level metadata overhead. `CREATION` fires on DT create/replace; `REINITIALIZE` fires on base object or base object property changes (check `reinit_reason`). REINITIALIZE is NOT necessarily slower than INCREMENTAL — it can be faster or slower depending on the query and data volume. If REINITIALIZE is consistently faster than INCREMENTAL refreshes, this suggests the DT may perform better with `REFRESH_MODE = FULL` (provided downstream DTs are not incremental). Exclude both from steady-state performance trends.
- **Steady-state**: Everything else (`INCREMENTAL`, `FULL` with trigger `SCHEDULED` or `MANUAL`). This is what performance tuning targets.
- **NO_DATA**: No changes in base tables — zero-cost refresh. Ignore for performance analysis.

---

## Comparing Performance Across REINITIALIZE Boundaries

After a REINITIALIZE, the underlying query characteristics may have changed (e.g., a base view was replaced with a different join structure, or a base table was swapped). This means refreshes before and after a REINITIALIZE may have entirely different query shapes and operator plans.

Within a single "reinit epoch" (the refreshes between two REINITIALIZE / CREATION events), steady-state performance differences reflect only the volume of changes to the base tables. But comparing refreshes across a reinit boundary is only valid if the query shape did not change.

**Checking whether the query shape changed:**

1. Use `graph_history_valid_from` from `DYNAMIC_TABLE_REFRESH_HISTORY` to correlate refreshes with `DYNAMIC_TABLE_GRAPH_HISTORY` entries.
2. If `inputs` or `query_text` changed between epochs, the performance profiles are not directly comparable.
3. **View inputs are opaque**: `inputs` only captures top-level object names. If a view is listed as an input and its underlying definition changed (e.g., different joins, added columns, replaced source tables), `inputs` will still show the same view name. In this case, `inputs` alone cannot detect the change.
   - When any input is a view, also compare `GET_QUERY_OPERATOR_STATS` output for a representative refresh from each epoch. If the operator tree differs (different joins, scans, or aggregation structure), the query shape changed.
   - If the DT reads from views and a REINITIALIZE occurred, **assume refreshes are not comparable across the boundary** unless operator stats confirm the same execution plan.

Always report pre-reinit and post-reinit steady-state metrics separately when a REINITIALIZE occurred, and note whether the query shape changed.

---

<a id="verify-warehouse-access-before-deep-diving"></a>

## Verify Warehouse Access Before Deep-Diving

Before calling `GET_QUERY_OPERATOR_STATS`, check that you can see the warehouse:

```sql
SHOW GRANTS ON WAREHOUSE <warehouse_name>;
```

`GET_QUERY_OPERATOR_STATS()` requires one of:
- **MONITOR** on the warehouse
- **OPERATE** on the warehouse
- **MONITOR WAREHOUSES** at the account level
- **MANAGE WAREHOUSES** at the account level

**USAGE alone is insufficient.** If the `SHOW GRANTS` query returns `SQL compilation error: Warehouse '<warehouse_name>' does not exist or not authorized.`, or `GET_QUERY_OPERATOR_STATS` fails with a privilege error, **alert the user explicitly:**

> **Your current role does not have sufficient privileges on warehouse `<warehouse_name>`.** Without MONITOR or OPERATE on the warehouse, I cannot use `GET_QUERY_OPERATOR_STATS`, which provides operator-level breakdowns (per-join, per-scan, per-aggregation cost) that allow significantly more precise root-cause analysis than query-level metrics alone.

Then check whether the `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` fallback is available before committing to it:

```sql
SELECT 1 FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY LIMIT 1;
```

If this succeeds, the fallback is usable. If it fails with a privilege error, the user also lacks IMPORTED PRIVILEGES on the SNOWFLAKE database.

Present the user with options based on what is available:

1. **Grant MONITOR on the warehouse** (recommended — least privilege, enables full operator-level analysis):
   ```sql
   GRANT MONITOR ON WAREHOUSE <warehouse_name> TO ROLE <current_role>;
   ```

2. **Use ACCOUNT_USAGE fallback** (only if the check above succeeded — query-level stats only, no operator breakdown):
   ```sql
   SELECT 
     query_id, query_type, execution_status,
     total_elapsed_time / 1000 as elapsed_sec,
     bytes_scanned / 1024 / 1024 / 1024 as gb_scanned,
     rows_produced,
     compilation_time, execution_time,
     partitions_scanned, partitions_total,
     ROUND(partitions_scanned / NULLIF(partitions_total, 0) * 100, 1) as partition_scan_pct,
     bytes_spilled_to_local_storage / 1024 / 1024 / 1024 as gb_spilled_local,
     bytes_spilled_to_remote_storage / 1024 / 1024 / 1024 as gb_spilled_remote,
     warehouse_size
   FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
   WHERE query_id = '<query_id>';
   ```
   **If you do not have a `query_id` yet** (for example to sample recent refresh runs for a DT): use the same view with `WHERE query_type = 'DYNAMIC_TABLE_REFRESH' AND query_text ILIKE '%<dt_name>%' ORDER BY start_time DESC LIMIT 5` — same privileges, latency, and column set as above (adjust the `SELECT` list if you only need `query_id`, warehouse, and timing).

   If the ACCOUNT_USAGE probe above also failed, inform the user:
   > **`SNOWFLAKE.ACCOUNT_USAGE` is also not accessible** — your role lacks IMPORTED PRIVILEGES on the SNOWFLAKE database. You'll need either warehouse MONITOR or ACCOUNT_USAGE access to proceed with query analysis.

3. **Skip operator analysis** and proceed with `DYNAMIC_TABLE_REFRESH_HISTORY` statistics alone.

---

<a id="account-level-refresh-history-optional"></a>

## Account-level refresh history (optional)

`SNOWFLAKE.ACCOUNT_USAGE.DYNAMIC_TABLE_REFRESH_HISTORY` exposes the same per-refresh semantics as `INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY()` with account-usage retention and latency. It requires **IMPORTED PRIVILEGES** on `SNOWFLAKE` (use the probe in [Verify Warehouse Access](#verify-warehouse-access-before-deep-diving)). Apply steady-state filters consistently with [Interpreting Refresh Categories](#interpreting-refresh-categories). For column definitions and example predicates, see [Dynamic Table Refresh History (account usage)](https://docs.snowflake.com/en/sql-reference/account-usage/dynamic_table_refresh_history) in the Snowflake documentation.

<a id="account-level-daily-rollup-example"></a>

**Example: daily steady-state rollup** (last 30 days; ~45-minute latency for recent rows):

```sql
SELECT
  refresh_start_time::DATE AS refresh_date,
  COUNT(*)                                                   AS refreshes,
  AVG(IFF(refresh_action IN ('INCREMENTAL','FULL')
          AND refresh_trigger != 'CREATION',
          DATEDIFF('second', refresh_start_time, refresh_end_time),
          NULL))                                             AS avg_duration_sec,
  COUNT_IF(state = 'FAILED')                                 AS failed_count,
  COUNT_IF(refresh_action = 'FULL'
           AND refresh_trigger != 'CREATION')                AS full_count
FROM SNOWFLAKE.ACCOUNT_USAGE.DYNAMIC_TABLE_REFRESH_HISTORY
WHERE database_name = '<DB>'
  AND schema_name   = '<SCHEMA>'
  AND name          = '<DT_NAME>'
  AND refresh_start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
GROUP BY refresh_date
ORDER BY refresh_date DESC;
```
