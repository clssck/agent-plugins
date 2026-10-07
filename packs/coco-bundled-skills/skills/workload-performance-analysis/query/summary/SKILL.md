# Single Query Summary

**This is a Phase 1 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Fetch execution metrics for a single query and present a high-level overview.

## Prerequisites

- Specific query ID (UUID-like format, e.g. `01b24bb0-0007-9627-0000-0001234abcde`)
- Access to `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` or `INFORMATION_SCHEMA.QUERY_HISTORY()`

## Workflow

### Step 1: Fetch Query Metrics

**Try data sources in order:**

1. **ACCOUNT_USAGE.QUERY_HISTORY** (default 7-day window):
   ```sql
   SELECT
       query_id,
       query_type,
       query_parameterized_hash,
       query_parameterized_hash_version,
       database_name,
       schema_name,
       user_name,
       warehouse_name,
       warehouse_size,
       execution_status,
       ROUND(execution_time / 1000.0, 2) AS execution_seconds,
       ROUND(total_elapsed_time / 1000.0, 2) AS total_elapsed_seconds,
       ROUND(compilation_time / 1000.0, 2) AS compilation_seconds,
       ROUND(queued_overload_time / 1000.0, 2) AS queued_overload_seconds,
       ROUND(queued_provisioning_time / 1000.0, 2) AS queued_provisioning_seconds,
       ROUND(queued_repair_time / 1000.0, 2) AS queued_repair_seconds,
       ROUND(bytes_scanned / 1024.0 / 1024 / 1024, 2) AS gb_scanned,
       ROUND(percentage_scanned_from_cache * 100, 1) AS cache_hit_pct,
       partitions_scanned,
       partitions_total,
       ROUND(bytes_spilled_to_local_storage / 1024.0 / 1024 / 1024, 2) AS local_spill_gb,
       ROUND(bytes_spilled_to_remote_storage / 1024.0 / 1024 / 1024, 2) AS remote_spill_gb,
       rows_produced,
       start_time,
       LEFT(query_text, 200) AS query_text_preview
   FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
   WHERE query_id = '<QUERY_ID>'
     AND start_time >= DATEADD('day', -7, CURRENT_DATE());
   ```

2. **If not found**, try `INFORMATION_SCHEMA.QUERY_HISTORY()` (real-time, limited to 7 days):

   **Important differences from ACCOUNT_USAGE.QUERY_HISTORY:**
   - **Row limit**: Returns only **100 rows by default**. Use `RESULT_LIMIT => 10000` to retrieve up to 10,000 rows. The RESULT_LIMIT is applied **before** any WHERE clause — so without increasing it, your WHERE filter only applies to the most recent 100 queries.
   - **RBAC scoped**: Returns only queries run by the **current user** by default. To see other users' queries, the executing role must have MONITOR or OPERATE privilege on the warehouses where the queries ran, or MONITOR EXECUTION privilege on the account.

   ```sql
   SELECT
       query_id,
       query_type,
       query_parameterized_hash,
       query_parameterized_hash_version,
       database_name,
       schema_name,
       user_name,
       warehouse_name,
       warehouse_size,
       execution_status,
       ROUND(execution_time / 1000.0, 2) AS execution_seconds,
       ROUND(total_elapsed_time / 1000.0, 2) AS total_elapsed_seconds,
       ROUND(compilation_time / 1000.0, 2) AS compilation_seconds,
       ROUND(queued_overload_time / 1000.0, 2) AS queued_overload_seconds,
       ROUND(queued_provisioning_time / 1000.0, 2) AS queued_provisioning_seconds,
       ROUND(queued_repair_time / 1000.0, 2) AS queued_repair_seconds,
       ROUND(bytes_scanned / 1024.0 / 1024 / 1024, 2) AS gb_scanned,
       rows_produced,
       start_time,
       LEFT(query_text, 200) AS query_text_preview
   FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(RESULT_LIMIT => 10000))
   WHERE query_id = '<QUERY_ID>';
   ```

   **Columns NOT available in INFORMATION_SCHEMA** (only in ACCOUNT_USAGE.QUERY_HISTORY): `percentage_scanned_from_cache`, `partitions_scanned`, `partitions_total`, `bytes_spilled_to_local_storage`, `bytes_spilled_to_remote_storage`. If these metrics are needed, wait for the query to appear in ACCOUNT_USAGE (45-min latency) and use the primary lookup.

3. **If still not found**, ask user before expanding time window:
   ```
   Query ID <query_id> not found in the default time window (last 7 days).

   Would you like to:
   A. Expand search to last 14 days
   B. Expand search to last 30 days
   C. Expand search to last 90 days
   D. Specify a custom time range
   E. Cancel and provide a different query ID
   ```

   **MANDATORY STOPPING POINT:** Do NOT automatically expand the time window.

### Step 2: Present Query Summary

```
## Query Analysis: <query_id>

| Metric | Value |
|---|---|
| Execution Time | Xs |
| Total Elapsed Time | Xs |
| Compilation Time | Xs |
| Queue Time (Overload) | Xs |
| Queue Time (Provisioning) | Xs |
| Queue Time (Repair) | Xs |
| GB Scanned | X |
| Cache Hit | X% |
| Partitions Scanned | X / Y (Z% pruning) |
| Local Spilling | X GB |
| Remote Spilling | X GB |
| Rows Produced | X |
| Warehouse | NAME (SIZE) |
| User | X |
| Status | SUCCESS/FAILED |
| Pattern Hash | <hash> (version <version>) |
```

**[STOP]** Present the summary table. Ask: "Want me to identify root causes or provide recommendations?"
