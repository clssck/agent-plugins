# FROZEN WHERE Guidance

How to guide a customer through adding a `FROZEN WHERE` clause to an existing dynamic table. This guidance applies whenever a recommendation handler surfaces `FROZEN WHERE` as an option or mitigation — see the per-code handlers that reference this file.

For full documentation, see [Frozen regions for dynamic tables](https://docs.snowflake.com/en/user-guide/dynamic-tables/frozen-regions).

---

## What FROZEN WHERE does

A `FROZEN WHERE` clause marks output rows that match a predicate as **frozen** — the engine stops re-scanning and re-processing them on subsequent refreshes. This reduces refresh cost by shrinking the active region the engine must maintain. Rows matching the predicate on the first refresh after the clause is set enter the frozen region and are not revisited until the clause is removed or replaced.

The clause is declared in the DT's options, not in the query body. Frozen rows remain queryable and are returned by `SELECT` as normal; only refresh processing skips them.

---

## Step 1 — Identify the column(s) that define the immutable slice

Ask the customer: **which output columns of the dynamic table can be used to identify the rows that will never change again?**

Two things to confirm:
1. **The column must be an output column of the DT itself** — not a base-table column that is not projected into the DT's `SELECT`. The predicate references the DT's output, not its sources.
2. The most common pattern is a **date or timestamp column** representing when the row was created or closed (e.g. `order_date`, `closed_at`, `event_ts`). However, any deterministic condition on DT output columns works — a status flag, a numeric threshold, a boolean column.

If the customer names a column that is not in the DT's SELECT, point this out and ask which projected column best approximates the boundary (or whether the query can be extended to project one).

---

## Step 2 — Define the predicate

Once the column is identified, work with the customer to phrase the condition. The predicate must satisfy **all** of the constraints below:

| Constraint | Detail |
|---|---|
| **Deterministic** | Allowed; most predicates qualify |
| **Timestamp functions** | Allowed — `CURRENT_TIMESTAMP()`, `CURRENT_DATE()`, `DATEADD(...)`, etc. These make the frozen region grow over time as more rows cross the threshold, which is the typical intent |
| **No subqueries** | The predicate cannot contain a nested `SELECT` |
| **No UDFs or external functions** | User-defined or external functions are not permitted |
| **No metadata columns** | Columns starting with `METADATA$` cannot be referenced |
| **No aggregate / window results** | Columns that are the output of aggregates, window functions, or nondeterministic functions (as defined in the DT's query) cannot appear in the predicate |
| **Frozen region must not shrink** | The predicate must grow or remain stable over time. A condition like `ts < CURRENT_TIMESTAMP()` is valid (it grows as time passes). A condition like `ts > CURRENT_TIMESTAMP()` would shrink — it is invalid and will be rejected |
| **One predicate per DT** | A DT can have at most one `FROZEN WHERE` clause. Setting a new one replaces the existing one |

Typical examples:
```sql
-- Everything older than 90 days (grows as time passes)
order_date < DATEADD('day', -90, CURRENT_DATE())

-- Records created before a fixed cutoff date
created_at < '2024-01-01'::DATE

-- Closed records with a timestamp boundary
closed_at < DATEADD('day', -30, CURRENT_DATE()) AND closed_at IS NOT NULL
```

---

## Step 3 — Compose the DDL

**Default to Case A. Only use Case B if some *other accepted* code already requires a `CREATE OR ALTER` on this same DT** (e.g. an `ADAPTIVE` switch, a column addition, a split) — check what the rest of Step 5 is actually composing for this DT *before* writing any SQL, don't reach for `CREATE OR ALTER` first and see if it works. If `FROZEN WHERE` is the only thing changing on this DT, there is no other DDL to fold it into — go straight to Case A and stop; do not also draft, run, or discard a `CREATE OR ALTER` attempt along the way.

### Case A — FROZEN WHERE is the only change (standalone ALTER)

```sql
ALTER DYNAMIC TABLE <db>.<schema>.<dt_name>
  SET FROZEN WHERE (<predicate>);
```

This is the lightest-touch form — it adds or replaces the frozen clause without touching the query body or any other settings.

### Case B — FROZEN WHERE combined with other DDL changes (CREATE OR ALTER)

When you are already drafting a `CREATE OR ALTER` for this DT (e.g. to change `REFRESH_MODE` or restructure the query), fold `FROZEN WHERE` into that single statement as a table-option clause. Do **not** emit a separate `ALTER ... SET FROZEN WHERE` alongside a `CREATE OR ALTER` for the same DT.

```sql
CREATE OR ALTER DYNAMIC TABLE <db>.<schema>.<dt_name>
  TARGET_LAG   = <original_target_lag>
  WAREHOUSE    = <original_warehouse>
  REFRESH_MODE = <new_or_original_mode>
  FROZEN WHERE (<predicate>)
  AS
    <original_query>;
```

Preserve all other settings (`INITIALIZE`, `CLUSTER BY`, comments, etc.) as you would for any `CREATE OR ALTER` composed for this DT.

---

## Step 4 — Verify (optional, for the customer)

The customer can verify which rows are frozen after the next refresh by querying the `METADATA$IS_FROZEN` pseudo-column:

```sql
SELECT COUNT(*) AS total_rows,
       SUM(IFF(METADATA$IS_FROZEN, 1, 0)) AS frozen_rows
FROM <db>.<schema>.<dt_name>;
```

The `immutable_where` column of `SHOW DYNAMIC TABLES` also shows the active predicate (NULL if none is set).

---

## Caveats

- **Removing or shrinking the frozen region triggers full reinitialization.** If the customer later removes the clause (`ALTER DYNAMIC TABLE ... UNSET FROZEN WHERE`) or replaces it with a narrower predicate, the engine reprocesses all rows — including previously frozen ones — on the next refresh. This can be expensive for large tables. Warn the customer before they commit.
- **Expanding the predicate does not trigger reinitialization.** Adding more rows to the frozen region (wider predicate) is safe.
- **Use `FROZEN WHERE` by default; `IMMUTABLE WHERE` only when it's already there.** `FROZEN WHERE` is the current keyword — use it for every new clause you add, including in the examples above (Case A's `ALTER ... SET FROZEN WHERE` and Case B's inline `FROZEN WHERE (...)`). The **only** exception: if `GET_DDL` shows the DT already has an `IMMUTABLE WHERE` clause (the legacy alias) — preserve that exact keyword when altering it, don't silently rename it to `FROZEN WHERE`. Never introduce `IMMUTABLE WHERE` on a DT that had neither keyword before.
- **Only one predicate at a time.** Setting a new `FROZEN WHERE` via `ALTER ... SET FROZEN WHERE` replaces the existing one entirely.
