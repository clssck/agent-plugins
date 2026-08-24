# Snowflake APIs Reference

## ⚠️ Common SQL mistakes (read first)

These seven errors account for nearly all SQL compilation failures observed in lineage agent runs:

| # | Wrong | Right |
|---|---|---|
| 1 | `SNOWFLAKE.ACCOUNT_USAGE.GET_LINEAGE(...)` | `SNOWFLAKE.CORE.GET_LINEAGE(...)` — function lives in `CORE`, not `ACCOUNT_USAGE` |
| 2 | `GET_LINEAGE(object_name => '...', object_domain => 'TABLE', direction => 'DOWNSTREAM', distance => 5)` | `GET_LINEAGE('<db>.<sch>.<obj>', 'TABLE', 'DOWNSTREAM', 5)` — positional args only for native (`'TABLE'`/`'COLUMN'`) anchors. Exception: external-anchor calls (`OBJECT_DOMAIN => 'EXTERNAL'`) *do* use named args, and the 4th parameter there is named `MAX_DISTANCE`, not `distance`. Only attempt this on an account past the version cutover (check `VERSION_GET_LINEAGE`) — see `external-row-output.md` for the version check and exact call shape. |
| 3 | `SELECT DOWNSTREAM_OBJECT_NAME, UPSTREAM_OBJECT_NAME FROM TABLE(...)` | `SELECT SOURCE_OBJECT_NAME, TARGET_OBJECT_NAME FROM TABLE(...)` — output columns are `SOURCE_*` / `TARGET_*` only |
| 4 | `WHERE objects_modified ILIKE '%X%'` on `ACCESS_HISTORY` | Use `LATERAL FLATTEN(input => ah.objects_modified) m` then filter `m.value:objectName::STRING ILIKE '%X%'` — `objects_modified` and `base_objects_accessed` are VARIANT arrays |
| 5 | `SHOW TABLES IN SCHEMA DB."my_schema"` (quoted) | `SHOW TABLES IN SCHEMA DB.MY_SCHEMA` (unquoted) — Snowflake stores unquoted identifiers in UPPER CASE. Quoting a mixed-case name that was created unquoted will miss the actual (upper) stored identifier. |
| 6 | `ACCESS_HISTORY.ROLE_NAME` | `ACCESS_HISTORY` has **no `ROLE_NAME` column**. It has `user_name`, `query_id`, `query_start_time`, `base_objects_accessed`, `objects_modified`. To get the role, join to `QUERY_HISTORY` on `query_id`. |
| 7 | `QUERY_HISTORY.QUERY_START_TIME` | The timestamp column in `QUERY_HISTORY` is **`start_time`**, not `query_start_time`. (`ACCESS_HISTORY` uses `query_start_time`; `QUERY_HISTORY` uses `start_time`.) |

## Lineage: Primary vs Fallback

| API | Description | Use Case | Privileges |
|-----|-------------|----------|------------|
| **`SNOWFLAKE.CORE.GET_LINEAGE()`** | **Primary.** Object and data-movement lineage (upstream/downstream). | All table/column lineage workflows. | Object resolve + **VIEW LINEAGE** (granted to PUBLIC). No account admin. |
| `ACCOUNT_USAGE.OBJECT_DEPENDENCIES` | **Fallback.** Object dependency graph only (target depends on source). | Use when GET_LINEAGE returns no rows or privilege errors. | **Account admin** (e.g. `GRANT IMPORTED PRIVILEGES` on SNOWFLAKE). |

**Object dependency vs data movement:**
- **Object dependency:** Target object’s definition or data *depends on* the source (e.g. view on table). OBJECT_DEPENDENCIES captures this only.
- **Data movement:** Data is copied from source to target (e.g. CTAS, COPY INTO); target does not depend on source still existing. GET_LINEAGE captures both dependency and data movement.

Use GET_LINEAGE first; fall back to OBJECT_DEPENDENCIES when GET_LINEAGE is empty or not allowed.

**GET_LINEAGE usage:**
```sql
-- Downstream from a table (what depends on / is built from this)
SELECT * FROM TABLE(SNOWFLAKE.CORE.GET_LINEAGE('<db>.<schema>.<table>', 'TABLE', 'DOWNSTREAM', 5));

-- Upstream from a table (where this gets data from)
SELECT * FROM TABLE(SNOWFLAKE.CORE.GET_LINEAGE('<db>.<schema>.<table>', 'TABLE', 'UPSTREAM', 5));

-- Column-level: use object_name as db.schema.table.column, domain 'COLUMN'
SELECT * FROM TABLE(SNOWFLAKE.CORE.GET_LINEAGE('<db>.<schema>.<table>.<column>', 'COLUMN', 'DOWNSTREAM', 5));
```

**Domains:** `'TABLE'` (covers tables, views, materialized views, dynamic tables, semantic views, stages — do not pass `'VIEW'`), `'COLUMN'`. Direct anchoring on external entities (`OBJECT_DOMAIN => 'EXTERNAL'`) depends on producer family. Anchoring on a **Horizon Catalog connector** entity is confirmed blocked — a live call against the Private Preview account fails with "Anchoring GET_LINEAGE on an external object is not enabled for this account." Anchoring on an **OpenLineage-sourced** entity is confirmed supported (gated independently, by the account's `GET_LINEAGE` external read-path) — pass `OBJECT_NAME`, `OBJECT_DOMAIN => 'EXTERNAL'`, and the entity's `NAMESPACE`/`OBJECT_TYPE`/`EXTERNAL_ID` (read off a prior row's `*_NAMESPACE`/`*_DATASET_TYPE`/`*_EXTERNAL_ID`). There's still no cold/enumeration path for either family — you need those identifiers from somewhere first. `'EXTERNAL_COLUMN'` anchoring is untested; treat as unsupported. See `external-row-output.md` for the exact anchor call shape. External entities surface in output rows (from a native anchor) under either of two independent gates — **Horizon Catalog connectors** (Private Preview), which gates Horizon-Catalog-connector-sourced entities, or a `GET_LINEAGE` version new enough to support OpenLineage-sourced entities (dbt, Airflow, Databricks, etc.) — whenever the lineage path crosses into them, including chains of several consecutive external hops. See `external-row-output.md`.

**Output columns (canonical — use these names exactly):**
- `SOURCE_OBJECT_DATABASE`, `SOURCE_OBJECT_SCHEMA`, `SOURCE_OBJECT_NAME`, `SOURCE_OBJECT_DOMAIN`, `SOURCE_OBJECT_VERSION`, `SOURCE_COLUMN_NAME`, `SOURCE_STATUS`
- `TARGET_OBJECT_DATABASE`, `TARGET_OBJECT_SCHEMA`, `TARGET_OBJECT_NAME`, `TARGET_OBJECT_DOMAIN`, `TARGET_OBJECT_VERSION`, `TARGET_COLUMN_NAME`, `TARGET_STATUS`
- `DISTANCE` (1–5), `PROCESS` (VARIANT — query id or process metadata)

**Additional output columns, present when `GET_LINEAGE` is on version >= 7** (this is a function of the `GET_LINEAGE` version alone — independent of which of the two gates above is what's actually populating a given external row):

- `SOURCE_NAMESPACE`, `SOURCE_DATASET_TYPE`, `SOURCE_EXTERNAL_ID`
- `TARGET_NAMESPACE`, `TARGET_DATASET_TYPE`, `TARGET_EXTERNAL_ID`

For **external rows** that appear in results, `*_OBJECT_DATABASE` and `*_OBJECT_SCHEMA` are `NULL`, `*_OBJECT_DOMAIN` is `'EXTERNAL'`, and the entity is identified by `*_NAMESPACE` + `*_OBJECT_NAME` + `*_DATASET_TYPE`. See `external-row-output.md` for presentation rules.

There are **no** `DOWNSTREAM_OBJECT_NAME` / `UPSTREAM_OBJECT_NAME` / `DOWNSTREAM_COLUMNS` columns. Referencing them produces `SQL compilation error: invalid identifier`. Max 5 levels; max 10M rows.

## Account Usage Views

| API | Description | Use Case | Latency |
|-----|-------------|----------|---------|
| `ACCOUNT_USAGE.OBJECT_DEPENDENCIES` | Object dependency graph (fallback for lineage) | When GET_LINEAGE empty/fails | Near real-time |
| `ACCOUNT_USAGE.ACCESS_HISTORY` | Runtime data access patterns | Usage patterns, user attribution | 45min-3hr |
| `ACCOUNT_USAGE.QUERY_HISTORY` | Query execution details | Change attribution, debugging | 45min-3hr |
| `ACCOUNT_USAGE.TABLES` | Table metadata and timestamps | Schema change detection | 45min-3hr |
| `ACCOUNT_USAGE.COLUMNS` | Column metadata | Schema change detection | 45min-3hr |
| `ACCOUNT_USAGE.TABLE_STORAGE_METRICS` | Storage and freshness metrics | Trust scoring | 45min-3hr |
| `INFORMATION_SCHEMA.OBJECT_DEPENDENCIES` | Real-time deps (current DB only) | Fallback for real-time needs | Real-time |

**Key columns reference:**

- `ACCESS_HISTORY`: `query_id`, `user_name`, `query_start_time`, `base_objects_accessed` (VARIANT array), `objects_modified` (VARIANT array). **No `role_name`** — join to `QUERY_HISTORY` on `query_id` to get role.
- `QUERY_HISTORY`: `query_id`, `user_name`, `role_name`, `start_time` (**not** `query_start_time`), `end_time`, `query_text`, `database_name`.

## Privilege Requirements

```sql
-- GET_LINEAGE (primary): VIEW LINEAGE is granted to PUBLIC by default.
-- Ensure role can resolve the object (USAGE on database/schema, REFERENCE on object).

-- OBJECT_DEPENDENCIES fallback: requires account-level access to SNOWFLAKE
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE <role_name>;
```

Without IMPORTED PRIVILEGES, ACCOUNT_USAGE views return empty or access denied.

## Performance Notes

- **GET_LINEAGE:** Table function; use with TABLE() and optional distance (1–5). Up to 10M rows.
- **ACCOUNT_USAGE queries:** Fast for targeted queries, slow for full scans
- **ACCESS_HISTORY:** Limited to 365 days retention
- **OBJECT_DEPENDENCIES:** May have large result sets for heavily-used tables
- **Always filter by time** where applicable
- **Use specific object names** when possible
