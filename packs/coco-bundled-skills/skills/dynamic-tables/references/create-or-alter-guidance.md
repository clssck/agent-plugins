# CREATE OR ALTER DYNAMIC TABLE — Reference Guide

Complete guidance for using the `CREATE OR ALTER DYNAMIC TABLE` command.

---

## Why CREATE OR ALTER?

`CREATE OR ALTER DYNAMIC TABLE` is the **recommended default** for both creating and updating dynamic tables. It is declarative and idempotent: you describe the full desired state and Snowflake applies the minimal change.

| Command | Effect | Use When |
|---------|--------|----------|
| `CREATE OR ALTER` | Minimal-change, idempotent, protects downstream DTs | **Default for all DT changes** — property-only or otherwise |
| `ALTER DYNAMIC TABLE SET` | Simple property-only changes when idempotency isn't needed | One-shot property tweak (warehouse, lag, etc.) when the user hasn't asked for idempotent/COA deployment |
| `ALTER DYNAMIC TABLE UNSET` | Remove an optional property (e.g., `INITIALIZATION_WAREHOUSE`) | One-shot removal when idempotency isn't required |
| `CREATE OR REPLACE` | Always reinitializes; cascades to downstream incremental DTs | Changing column type or TRANSIENT flag (unsupported by CREATE OR ALTER); requires explicit approval |

---

## Reinit Trigger Reference

Which changes force a full reinitialization of the table on next refresh:

| Change | Reinit? | Notes |
|--------|---------|-------|
| Query definition changed | **YES** | Always reinit, regardless of how minor the change appears |
| REFRESH_MODE: FULL → INCREMENTAL | **YES** | Structural boundary crossing |
| REFRESH_MODE: FULL → ADAPTIVE | **YES** | Structural boundary crossing |
| REFRESH_MODE: INCREMENTAL/ADAPTIVE → FULL | **YES** (full refresh, not reinit) | Next refresh runs FULL; changes internal state |
| REFRESH_MODE: INCREMENTAL ↔ ADAPTIVE | **NO** (NO_DATA) | Safe; no reinit |
| Add or drop column in explicit-column DT (modify query) | **YES** | Query change always reinits; at least one column must remain (error 1432 if all dropped) |
| Frozen region shrink or removal | **YES** | Rows once frozen now need recompute |
| Warehouse, target lag, scheduler, clustering, EXECUTE AS USER | **NO** | Property-only, no reinit |
| Column comment (COMMENT) | **NO** | Metadata only |
| Column list evolution (same names, wider type) | **NO** (NO_DATA) | Schema-compatible |
| Column list evolution (rename existing trailing columns) | **YES** | Output schema changed |

---

## Downstream Cascade Rules

| Command | Effect on downstream incremental DTs |
|---------|--------------------------------------|
| `CREATE OR ALTER` | **Protected** — downstream DTs are NOT forced to reinitialize |
| `CREATE OR REPLACE` | **Cascades** — downstream DTs are also reinitialized |

**Special case — switching upstream DT to FULL:** If an upstream DT changes refresh mode to FULL via `CREATE OR ALTER`, downstream INCREMENTAL DTs will fail on their next refresh with error 2742 ("no longer incrementalizable"). Warn the user before making this change.

---

## Property Omission Rule

When a property is omitted from a `CREATE OR ALTER` statement, it **resets to the system default**.

**Exceptions — preserved when omitted:**
- `CHANGE_TRACKING` — preserved
- `ROW_TIMESTAMP` — preserved

**Always carry forward explicitly:** `DATA_RETENTION_TIME_IN_DAYS`, `MAX_DATA_EXTENSION_TIME_IN_DAYS`, `CLUSTER BY`, `FROZEN WHERE`, `WAREHOUSE`, `TARGET_LAG`, `SCHEDULER`, `INITIALIZATION_WAREHOUSE`, `COMMENT`, `REFRESH_MODE`, `REQUIRE USER`, `EXECUTE AS USER`, `BACKFILL FROM`, `START AT`.

**How to read retention settings:** `DATA_RETENTION_TIME_IN_DAYS` and `MAX_DATA_EXTENSION_TIME_IN_DAYS` are not in `GET_DDL` or `SHOW DYNAMIC TABLES` — use `SHOW PARAMETERS` as the source of truth. Use `SHOW PARAMETERS` as a general fallback for any property not visible in `GET_DDL` or `SHOW DYNAMIC TABLES` (e.g., `DEFAULT_DDL_COLLATION` also lives there).
```sql
SHOW PARAMETERS LIKE 'DATA_RETENTION_TIME_IN_DAYS' IN DYNAMIC TABLE <db>.<schema>.<name>;
SHOW PARAMETERS LIKE 'MAX_DATA_EXTENSION_TIME_IN_DAYS' IN DYNAMIC TABLE <db>.<schema>.<name>;
```

---

## Column Change Rules

Adding or removing columns requires modifying the AS query. Any such query change reinitializes the table.

| Operation | Allowed? | Notes |
|-----------|----------|-------|
| Add column (append to query) | ✅ — YES reinit | Query change  |
| Add column at a non-trailing position | ❌ Error 2830 | Column ordering in list is fixed; append only |
| Drop column (remove from query) | ✅ — YES reinit | Query change; at least one column must remain (error 1432 if all dropped) |
| Rename a column (drop + add) | ✅ at end only — YES reinit | Query change; drop old name, add new name at end; if old is not last, error 2830 |
| Rename ALL columns | ❌ Error 1432 | Cannot drop all columns |
| Change column type (compatible widening) | ✅ NO_DATA | E.g., `NUMBER(10,0)` → `NUMBER(20,0)` |
| Change column type (narrowing varchar) | ❌ Error 40050 | Cannot reduce VARCHAR byte-length |
| Change column type (incompatible) | ❌ Error 2108 | Cannot change type incompatibly |
| Add COLLATE to existing column | ❌ Error 40053 | Collation frozen on existing columns |
| Add COLLATE on initial CREATE OR ALTER | ✅ | First-time creation or new column addition can specify collation |
| Column COMMENT | ✅ NO_DATA | Metadata only; freely mutable |

---

## Column List Evolution

An explicit column list `(col1 TYPE, col2 TYPE, ...)` can be added, removed, or changed via `CREATE OR ALTER`:

| Transition | Result |
|-----------|--------|
| No column list → add list (matching names) | NO_DATA (no reinit) |
| No column list → add list (rename existing trailing col) | REINITIALIZE |
| Column list → remove list (matching names) | NO_DATA |
| Column list → remove list (existing trailing col mismatch) | REINITIALIZE |
| Change list (widen a type) | NO_DATA |
| Change list (rename existing trailing col) | REINITIALIZE |
| Any reorder, incompatible type, rename non-trailing | ❌ FAILS |
| Narrow VARCHAR in column list | ❌ Error 40050 |

---

## Governance Limitations

| Feature | Behavior |
|---------|----------|
| Table-level policies (RAP, agg, join, SLP) | Cannot be specified in `CREATE OR ALTER` (error 1506). Preserved when omitted. Use separate `ALTER TABLE ... ADD/SET POLICY`. |
| Column-level masking/projection policies | Cannot be specified in the column list (error 1506). Preserved when omitted. Use separate `ALTER DYNAMIC TABLE ... MODIFY COLUMN`. |
| Tags (table-level and column-level) | Cannot be specified (error 1506). Preserved when omitted. Use separate `ALTER TABLE ... SET TAG`. |
| Contacts | Not supported (parse error 1003 for DEFINE; semantic error for COA). |
| Data Metric Functions (DMF) | Cannot specify inline (error 1541). Use separate `ALTER TABLE ... ADD DATA METRIC FUNCTION`. |
| COPY GRANTS, COPY TAGS | Not supported in `CREATE OR ALTER`. |

---

## Hard Limitations

These operations are **not supported** by `CREATE OR ALTER` and require an alternative:

| Limitation | Alternative |
|-----------|-------------|
| TRANSIENT toggle | Drop and recreate the DT |
| Column type change (incompatible) | `CREATE OR REPLACE` (will reinit + cascade to downstream) |
| CUSTOM_INCREMENTAL ↔ regular mode switch | Not possible; requires a new DT with different definition |
| Full-only query to INCREMENTAL/ADAPTIVE | Error 91908 (change tracking not supported for this query) |
| Column reorder | `CREATE OR REPLACE` (with cascade warning) or restructure query |
| Iceberg dynamic tables | Not supported by `CREATE OR ALTER` |
| SWAP WITH, RENAME TO | Not supported; use `ALTER DYNAMIC TABLE` |
| SUSPEND, RESUME | Use `ALTER DYNAMIC TABLE ... SUSPEND/RESUME` |
| BACKFILL FROM / START AT modification | Cannot change after creation |
| OPERATE privilege only | OWNERSHIP is required on the existing DT; OPERATE alone is insufficient (error 3001) |

---

## Atomicity

`CREATE OR ALTER` is **not atomic** on wide tables. Property updates apply one at a time; a failure mid-way may leave the table in a partially updated state. Fix forward by re-running the full `CREATE OR ALTER` statement.

---

## SELECT * and Base Table Schema Evolution

When a `SELECT *` DT is altered via `CREATE OR ALTER` after the base table schema has changed:

| Base table change | DT behavior on next COA |
|-------------------|-------------------------|
| Column renamed | REINITIALIZE |
| Column dropped + new column added | REINITIALIZE |
| Column dropped (simple) | INCREMENTAL |
| Column added (no default) | INCREMENTAL |
| Column added (with default) | REINITIALIZE |
| GROUP BY ALL, UNION, SELECT DISTINCT + drop/add column | REINITIALIZE |
| No schema change (COA is no-op) | INCREMENTAL (unchanged) |
