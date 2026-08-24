# Snowflake Postgres Mirroring Troubleshooting

Use with `snowflake-postgres/mirror/SKILL.md` when a managed mirror fails to create, lags, or returns surprising query results.

## Quick Decision Tree

| Symptom | Likely cause | First action |
|---------|--------------|--------------|
| Permission/extension error during `CREATE_MIRROR` | Existing instance has not been refreshed for mirroring extensions | Stop and send user to Snowsight UI refresh |
| Target database error | Target DB pre-exists or partial failed create left objects | Use a new target DB name; only drop with approval |
| `SNAPSHOTTING` for a long time | Large initial copy or table-level error | `LIST_MIRRORED_TABLES`, named-arg `QUERY_ADMIN_LOG`, task history |
| Updates/deletes missing | Source table has no primary key | Explain insert-only; add PK then consider `RESTART_MIRROR` with warning |
| Mirror auth starts failing | Snowflake app lost instance USAGE | Re-run `GRANT USAGE ON POSTGRES INSTANCE ... TO APPLICATION snowflake` |
| `$live` inconsistent / partial transaction | `$live` is non-transactional | Query base table for consistency |
| `$live` stale | Changes metadata lag/backlog | `REFRESH_CHANGES_TABLE(mirror, table)` then inspect task history |
| Publication/type error | Blocked source type | Load `type-mapping.md`; adjust or omit source table |

## Instance Refresh Required — UI-only Stopping Point

Existing Snowflake Postgres instances created before mirroring may lack the current extensions. The symptom is usually a permission or extension-related failure from `CREATE_MIRROR`.

There is **no SQL or CLI refresh procedure**. `ALTER POSTGRES INSTANCE` does not refresh extensions. Do not suggest a major version upgrade (`SET POSTGRES_VERSION`) as a substitute.

**Stop and tell the user:**

```text
This looks like the instance needs the Snowflake Postgres mirroring refresh.
I can't perform that from SQL/Cortex Code.

Please open Snowsight → Postgres → Manage for <instance>, run the available refresh/update action, then come back and say it's done. After that I'll retry CREATE_MIRROR.
```

## Permission and Grant Issues

Required grants:

```sql
GRANT APPLICATION ROLE snowflake.postgres_mirror_admin TO ROLE <role>;
GRANT USAGE ON POSTGRES INSTANCE <instance_name> TO APPLICATION snowflake;
```

If the role cannot call mirror procedures, use an elevated role picker. If the mirror later loses access to the instance, re-run the `GRANT USAGE ... TO APPLICATION snowflake` statement.

## Target Database Must Not Pre-exist

`CREATE_MIRROR` creates the target database itself. If the target DB already exists, choose a new name. If a failed attempt left a partial target DB, inspect before deleting and get explicit approval before `DROP DATABASE`.

## Table State / Lag Checks

```sql
CALL SNOWFLAKE.POSTGRES.LIST_MIRRORED_TABLES('<mirror_name>');
CALL SNOWFLAKE.POSTGRES.DESCRIBE_MIRROR('<mirror_name>');
CALL SNOWFLAKE.POSTGRES.QUERY_ADMIN_LOG(
  MIRROR_NAME => '<mirror_name>',
  POSTGRES_INSTANCE => '<instance_name>',
  LEVEL => 'ERROR',
  SINCE_TS => NULL,
  MAX_ROWS => 100
);

SELECT name, state, scheduled_time, completed_time, error_code, error_message
FROM TABLE(SNOWFLAKE.INFORMATION_SCHEMA.TASK_HISTORY(
  SCHEDULED_TIME_RANGE_START => DATEADD('hour', -24, CURRENT_TIMESTAMP()),
  RESULT_LIMIT => 10000,
  ERROR_ONLY => TRUE
))
WHERE name LIKE 'APPLY_MIRROR_%'
ORDER BY scheduled_time DESC
LIMIT 50;
```

Push filters into `TASK_HISTORY` args (`SCHEDULED_TIME_RANGE_START`, `RESULT_LIMIT`, `ERROR_ONLY`) — the default `RESULT_LIMIT` of 100 is applied before `WHERE`, so a bare call can return 0 relevant rows on busy accounts even when apply tasks are failing.

`LIST_MIRRORED_TABLES` is the per-table `STATE` source; observed `LIST_MIRRORS` and `DESCRIBE_MIRROR` outputs do not include a mirror-level `STATE` column. Immediately after create or table-add, `LIST_MIRRORED_TABLES` rows and `LIST_MIRRORS.TABLE_COUNT` can populate asynchronously, so re-poll before treating an empty list or stale count as failure. A null `LAST_APPLY_TIME` on an idle mirror with successful recent runs or repeated `no operations to process` admin-log messages is not by itself a failure.

For `$live` lag on one table:

```sql
CALL SNOWFLAKE.POSTGRES.REFRESH_CHANGES_TABLE('<mirror_name>', '<schema.table>');
```

`REFRESH_CHANGES_TABLE(mirror, table)` refreshes one table's `$changes` metadata and can reduce `$live` view lag. It does not replace the normal apply task or make `$live` transactional.

## No Primary Key = Insert-only

Tables without a primary key can be mirrored, but UPDATE/DELETE replication requires a PK. For no-PK tables:

- Inserts replicate.
- Updates/deletes are not represented as normal row changes.
- If the user adds a PK later and needs full correctness, discuss `RESTART_MIRROR` — but warn that restart is a full re-snapshot and loses the current 7-day change feed.

## `$live` Partial Transactions

Base target tables are transactionally consistent. `$live` combines base tables with not-yet-merged changes for lower latency (~30s), but is non-transactional and can expose partial source transactions.

Guidance:
- Use base tables for financial reports, FK/cross-table invariants, and repeatable analytics.
- Use `$live` for operational dashboards where lower latency matters more than transaction boundaries.
- Keep `$live` scans small; cost grows with unmerged backlog.

## `$changes` / Watermark / Sequence Reset Notes

`$changes` is a 7-day feed with system columns `_COMMIT_LSN`, `_LSN`, `_XID`, `_COMMIT_TIME`, `_CHANGE_TYPE`, `_IS_UPDATE`, and `_DATA_VERSION`. `_CHANGE_TYPE` values are `S` (snapshot), `I` (insert), and `D` (delete/update pre-image). An UPDATE decomposes into a `D` + `I` pair sharing one `_XID`, with both rows `_IS_UPDATE = TRUE`; a standalone DELETE is `_CHANGE_TYPE = 'D' AND _IS_UPDATE = FALSE`. Consumers must use `_IS_UPDATE` to distinguish real deletes from update pre-images. `_DATA_VERSION` changes across schema boundaries such as truncate, PK add/drop, or rename; downstream consumers should reset dedup/watermarks when `_DATA_VERSION` changes.

For the DIY pg_lake `pg_incremental` path, truncating/reloading source data requires resetting the pipeline state (`last_processed_sequence_number`) or new low-ID rows can be skipped. That is not a managed-mirror procedure, but it is the same bookmark/watermark class of issue and matters for demo resets that combine both paths.

## Full Demo Reset Recipe

For demos that use both DIY pg_lake/CLD and managed mirror concepts, reset all state deliberately:

1. Truncate PG source tables.
2. For DIY `pg_incremental`, reset sequence counters / pipeline state to 0 or call the appropriate reset routine.
3. Truncate CDC landing tables if present.
4. Drop Snowflake Iceberg tables and wipe old S3 metadata (`REMOVE @STAGE/frompg/`) for the DIY path.
5. Recreate the catalog-linked database using `LINKED_CATALOG = (CATALOG = ..., ALLOWED_WRITE_OPERATIONS = NONE)`.
6. For managed mirrors, prefer creating a fresh mirror/target DB for a clean demo. If reusing the mirror, `RESTART_MIRROR` does a full re-snapshot and loses the current 7-day feed — warn first.

Never run destructive reset steps without explicit user approval.
