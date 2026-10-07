# Custom Incrementalization Reference

Syntax, semantics, and limitations for custom incremental dynamic tables (CI DTs).

---

## Syntax

```sql
CREATE [ OR REPLACE ] DYNAMIC TABLE <name> (
  <col_name> <col_type> [ , ... ]
)
  TARGET_LAG = { '<time>' | DOWNSTREAM }
  WAREHOUSE = <warehouse_name>
  [ REFRESH_MODE = { CUSTOM_INCREMENTAL | AUTO } ]
  [ INITIALIZE = { ON_CREATE | ON_SCHEDULE } ]
  [ BACKFILL FROM <table_name> ]
  [ START AT ({ STREAM => '<stream_name>' | TIMESTAMP => <timestamp> | OFFSET => <time_difference> | STATEMENT => <id> }) ]
  [ COMMENT = '<comment>' ]
  REFRESH USING (
    { <merge_statement> | <insert_statement> }
  );
```

**Notes:**
- `REFRESH_MODE` defaults to `CUSTOM_INCREMENTAL` when `REFRESH USING` is present. `AUTO` also resolves to `CUSTOM_INCREMENTAL`. Explicitly specifying is optional but valid.
- `BACKFILL FROM` populates the CI DT from an existing table before incremental processing begins.
- `START AT` sets the initial change-tracking offset. Critical for migrations — use `START AT (STREAM => '<stream_name>')` with `BACKFILL FROM` to carry over a stream's offset. Note: START AT requires BACKFILL FROM.

### MERGE Form

```sql
REFRESH USING (
  MERGE INTO SELF [ AS <target_alias> ]
  USING ( <select_query> ) AS <src_alias>
  ON <join_condition>
  [ WHEN MATCHED [ AND <condition> ] THEN UPDATE SET ... ]
  [ WHEN MATCHED [ AND <condition> ] THEN DELETE ]
  [ WHEN NOT MATCHED [ AND <condition> ] THEN INSERT (...) VALUES (...) ]
)
```

**Note:** The target alias (`AS <target_alias>`) is optional. Nondeterministic MERGE behavior applies — if multiple source rows match a single target row, results are nondeterministic. Add deduplication (e.g., `QUALIFY ROW_NUMBER()`) in the USING subquery to avoid this.

### INSERT Form

```sql
REFRESH USING (
  INSERT INTO SELF
  <select_query>
)
```

The `<select_query>` supports CTEs, subqueries, JOINs, window functions, etc. — any valid SELECT that produces rows matching the column list.

**Important:** INSERT INTO SELF is best suited for append-only sources. If your source has updates and deletes, use MERGE instead — INSERT cannot remove or modify existing rows.

---

## Key Constructs

### SELF

Refers to the CI DT's own current materialized state. Must be referenced using the keyword `SELF` or a target alias — you cannot refer to the dynamic table by its own name.

Use in:
- `MERGE INTO SELF` — the target of the MERGE
- `FROM SELF` — read current rows (e.g., in a FULL OUTER JOIN within the USING subquery)
- `NOT EXISTS (SELECT 1 FROM SELF ...)` — deduplication against existing rows

**Restriction:** `CHANGES()` cannot be applied to `SELF`. You can only read SELF's current state, not its change history.

### CHANGES() Clause

Reads incremental changes from a source table since the last successful refresh.

```sql
FROM <source> CHANGES( [ INFORMATION => { DEFAULT | APPEND_ONLY } ] ) [ AS <alias> ]
```

| Option | Returns | Use When |
|--------|---------|----------|
| `CHANGES()` | All changes (insert, update, delete) with metadata columns | Source has mixed DML |
| `CHANGES(INFORMATION => DEFAULT)` | Same as bare `CHANGES()` | Explicit default |
| `CHANGES(INFORMATION => APPEND_ONLY)` | Only inserts (no metadata columns) | Source is append-only (more efficient) |

**Multiple sources:** You can apply `CHANGES()` to multiple source tables in a single query (e.g., joining changes from two fact tables).

**On views:** `CHANGES()` can be applied to views under certain conditions:
- The view must be defined over tables with change tracking enabled
- If the view references another dynamic table, wrap that reference in `DYNAMIC_TABLE_REFRESH_BOUNDARY(<dt_name>)` inside the view definition
- **Supported view shapes for CHANGES():**
  - Simple SELECT with WHERE/projections
  - JOINs (inner, left outer, right outer, full outer)
  - GROUP BY aggregations (incremental-compatible aggregates only: SUM, COUNT, MIN, MAX, AVG)
  - UNION / UNION ALL
- **Unsupported view shapes** (will force full recompute or fail):
  - Views with non-deterministic functions (RANDOM(), CURRENT_TIMESTAMP(), etc.)
  - Views with correlated subqueries in SELECT list
  - Views with LATERAL joins to table functions
  - Views with CONNECT BY / recursive CTEs
- **If the customer's view falls outside these shapes**: Recommend creating a standard DT for that view first, then using `CHANGES()` on that DT instead

**On dynamic tables:** `CHANGES()` can read from other dynamic tables directly. If a downstream CI DT needs row-level change tracking from an upstream CI DT, the upstream CI DT must have a RELY primary key constraint (see RELY PK section below).

### Metadata Pseudo-Columns

Available when using `CHANGES()` (not APPEND_ONLY):

| Column | Type | Description |
|--------|------|-------------|
| `METADATA$ACTION` | VARCHAR | `'INSERT'` or `'DELETE'` |
| `METADATA$ISUPDATE` | BOOLEAN | `TRUE` if this row is part of an UPDATE (updates appear as DELETE + INSERT pair) |

**Interpreting changes:**

| METADATA$ACTION | METADATA$ISUPDATE | Meaning |
|-----------------|-------------------|---------|
| `'INSERT'` | `FALSE` | New row inserted |
| `'DELETE'` | `FALSE` | Row deleted |
| `'INSERT'` | `TRUE` | New value of an updated row |
| `'DELETE'` | `TRUE` | Old value of an updated row |

**RELY PK behavior:** When the source has a RELY primary key, delete+reinsert of the same key within a single change window cancels out (net-zero change). Without RELY PK, both the DELETE and INSERT appear as separate rows. This affects MERGE correctness — ensure deduplication handles this.

**Note:** `METADATA$ROW_ID` is NOT available in CI DTs.

---

## RELY Primary Keys

CI DTs don't automatically derive primary keys like standard DTs. If a downstream dynamic table (standard or CI) needs to consume `CHANGES()` from a CI DT using primary key-based change tracking, you must explicitly add a RELY primary key constraint:

```sql
ALTER DYNAMIC TABLE my_ci_dt ADD PRIMARY KEY (id) RELY;
```

Without this, downstream DTs reading CHANGES() from the CI DT may fail or fall back to less efficient change tracking.

---

## Column Definition

CI DTs **require** an explicit column list in the CREATE statement:

```sql
CREATE DYNAMIC TABLE my_dt (
  id INT,
  name STRING,
  amount NUMBER(10,2)
)
  ...
  REFRESH USING (...);
```

This differs from standard DTs where columns are inferred from the AS SELECT query.

---

## Refresh Semantics

### Transaction Model

Each CI DT refresh executes as a single autocommit transaction:
- **Success:** Changes are committed, downstream DTs can proceed.
- **Failure:** The entire DML is rolled back. The refresh state is marked `COMPLETED_FAILED`. Downstream DTs are skipped until the next successful refresh.

### Data Retention

If the source table's data retention period expires before the CI DT processes changes, the refresh will fail. Ensure `DATA_RETENTION_TIME_IN_DAYS` on source tables is sufficient for your `TARGET_LAG` setting.

### No-op Refreshes

Unlike `SYSTEM$STREAM_HAS_DATA()` (which skips task execution entirely), CI DT refreshes run even when `CHANGES()` returns 0 rows. The no-op DML still consumes warehouse credits. For high-frequency TARGET_LAG on low-change sources, this may have cost implications.

---

## Schema Evolution

CI DTs support adding columns without full reinitialization via CREATE OR ALTER:

```sql
CREATE OR ALTER DYNAMIC TABLE my_ci_dt (
  id INT,
  name STRING,
  new_col VARCHAR  -- new column added
)
  TARGET_LAG = ...
  WAREHOUSE = ...
  REFRESH USING (...);  -- updated to populate new_col
```

Note: `ALTER DYNAMIC TABLE ... ADD COLUMN` is not supported. Use CREATE OR ALTER to evolve schema.

---

## Limitations

| Limitation | Details |
|-----------|---------|
| Single DML statement | REFRESH USING accepts exactly one MERGE or one INSERT statement |
| No procedural logic | No IF/ELSE, loops, EXECUTE IMMEDIATE, or multi-statement blocks |
| No DDL | Cannot ALTER, CREATE, or DROP objects during refresh |
| No external functions | Cannot call functions with side effects |
| No stored procedure calls | Cannot CALL procedures |
| Column list required | Must declare columns explicitly in CREATE |
| CHANGES() scope | Returns changes since last successful refresh only (not arbitrary time windows) |
| CHANGES() on SELF not allowed | Cannot read change history of the CI DT itself — only current state via SELF |
| Source change tracking | Tables referenced with CHANGES() must have change tracking enabled |
| Source data retention | Retention must not expire before changes are consumed, or refresh fails |
| No cloning | CI DTs cannot be cloned |
| No replication | CI DTs cannot be replicated |
| No DCM projects | CI DTs cannot be used in DCM (Data Cloud Manager) projects |
| No dbt projects | CI DTs cannot be used in dbt projects on Snowflake |
| Iceberg v2 with external catalog | Reading CHANGES from Iceberg v2 tables using external catalog or externally managed writes requires a RELY primary key on the source |
| No METADATA$ROW_ID | Row ID pseudo-column not available |
| Multi-table writes | One CI DT = one target. Split into multiple CI DTs for multiple targets |
| Imperative, not view semantics | CI DTs accumulate/mutate state imperatively — not equivalent to a materialized SELECT. If user needs view semantics, use standard DTs |
| GET_DDL not roundtrip-safe | `GET_DDL('DYNAMIC_TABLE', ...)` emits column names without data types — output cannot be re-executed directly |

**Supported operations:**
- **DML**: Direct DML (INSERT, UPDATE, DELETE, MERGE) into CI DTs is supported outside of the refresh cycle
- **Storage Lifecycle Policies (SLP)**: Can be defined on CI DTs (if SLP feature is GA in your account)

---

## Integration with Standard DTs

CI DTs participate in the same DAG as standard dynamic tables:

```
base_table → standard_dt (SELECT ... GROUP BY)
                  ↓
             ci_dt (MERGE INTO SELF USING ... FROM standard_dt CHANGES())
```

- Standard DTs can feed CI DTs (via CHANGES())
- CI DTs can feed standard DTs (standard DT reads CI DT as a regular source)
- CI DTs can feed other CI DTs (upstream needs RELY PK for row-level tracking)
- TARGET_LAG = DOWNSTREAM works the same as for standard DTs

---

## Comparison: Standard DT vs CI DT

| Aspect | Standard DT | CI DT |
|--------|------------|-------|
| Definition | `AS SELECT ...` | `REFRESH USING (MERGE/INSERT INTO SELF ...)` |
| Refresh mode | AUTO / INCREMENTAL / FULL | CUSTOM_INCREMENTAL (or AUTO → resolves to CUSTOM_INCREMENTAL) |
| Change handling | Automatic (Snowflake decides) | Explicit (you write the DML) |
| Schema inference | From SELECT columns | Explicit column list required |
| Schema evolution | Often triggers reinit | Column additions without reinit |
| View semantics | Yes (always reflects SELECT result) | No (imperative — accumulates/mutates state) |
| Stream-static join | Not supported (full recompute) | Supported via CHANGES() + regular JOIN |
| State access | Not possible | Via SELF keyword |
| Primary keys | Automatically derived | Must explicitly add RELY PK if needed downstream |
| Cloning/Replication | Supported | Not supported |
