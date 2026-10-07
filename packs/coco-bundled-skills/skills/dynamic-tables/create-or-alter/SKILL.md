---
name: dynamic-tables-create-or-alter
description: "Create, modify, or redeploy Snowflake Dynamic Tables using CREATE OR ALTER. Use for: modify DT, change DT query, add column to DT, change refresh mode, update target lag, warehouse swap, schema evolution, idempotent deploy. Do NOT route here for first-time CREATE without idempotency needs."
parent_skill: dynamic-tables
---

# CREATE OR ALTER DYNAMIC TABLE

## When to Load

Route here when the user wants to:
- Modify an existing dynamic table: change query, refresh mode, columns, warehouse, lag, frozen region, or any property
- Deploy or redeploy a dynamic table idempotently in a pipeline or CI/CD script
- Evolve the schema of a dynamic table (add/drop columns, change query)
- Understand whether a change will reinitialize a table or affect downstream DTs

---

## Workflow

### Step 1: Load Reference and Establish Context

**Load**: [`../references/create-or-alter-guidance.md`](../references/create-or-alter-guidance.md)

**If the table already exists**, run **all three** of these to capture current state:

```sql
-- Get current DDL (query, column list, most properties)
SELECT GET_DDL('DYNAMIC_TABLE', '<db>.<schema>.<name>');

-- Get scheduling_state, refresh_mode, target_lag, warehouse, frozen_where
SHOW DYNAMIC TABLES LIKE '<name>' IN SCHEMA <db>.<schema>;

-- Get DATA_RETENTION_TIME_IN_DAYS and MAX_DATA_EXTENSION_TIME_IN_DAYS
-- These are NOT in GET_DDL or SHOW DYNAMIC TABLES — SHOW PARAMETERS is the source of truth.
-- Use SHOW PARAMETERS as a general fallback for any property not visible in GET_DDL or SHOW DT
-- (e.g., DEFAULT_DDL_COLLATION also lives here).
SHOW PARAMETERS LIKE 'DATA_RETENTION_TIME_IN_DAYS' IN DYNAMIC TABLE <db>.<schema>.<name>;
SHOW PARAMETERS LIKE 'MAX_DATA_EXTENSION_TIME_IN_DAYS' IN DYNAMIC TABLE <db>.<schema>.<name>;
```

Use all three outputs together as the baseline for the property omission check in Step 3.
`DATA_RETENTION_TIME_IN_DAYS` and `MAX_DATA_EXTENSION_TIME_IN_DAYS` are only accessible via `SHOW PARAMETERS` and **must** be read from there before generating the statement.

---

### Step 2: Classify the Change

Determine which category the requested change falls into:

| Category | Examples | Key action |
|----------|----------|------------|
| **Safe** (no reinit) | Warehouse, lag, scheduler, clustering keys, column comment, EXECUTE AS USER, INCREMENTAL↔ADAPTIVE mode | Use `CREATE OR ALTER` (Step 4) for idempotency, or `ALTER DYNAMIC TABLE SET` for a minimal one-shot change if the user hasn't asked for idempotent deployment; no reinit warning needed |
| **Reinit-triggering** | Query change (including add/drop column in explicit-column DT), FULL → INCREMENTAL or FULL → ADAPTIVE mode, frozen region shrink/removal | Warn reinit on THIS table; confirm downstream is safe (downstream DTs are protected) |
| **Full refresh (not reinit)** | INCREMENTAL/ADAPTIVE → FULL mode | Do NOT show the reinit warning; show the Upstream → FULL warning from Step 4 (error 2742 risk for downstream INCREMENTAL DTs) |
| **Unsupported** | Column type change, TRANSIENT toggle, column reorder, policies/tags/DMF inline, CUSTOM_INCREMENTAL↔regular mode switch | Redirect to the right alternative (see below) |
| **First-time creation** | Table does not exist | Create it; warn null-gap if INITIALIZE = ON_SCHEDULE |

Consult the **Reinit Trigger Reference**, **Column Change Rules**, and **Hard Limitations** sections in the loaded `create-or-alter-guidance.md` for the full classification detail and redirect targets.

**⚠️ STOPPING POINT**: Present the classification and any warnings before generating SQL. Wait for user confirmation.

---

### Step 3: Property Omission Check

Before generating the statement, compare the desired state against the current state captured in Step 1.

For every property currently set on the DT that the user has NOT mentioned:
- **Warn**: "Omitting `<property>` will reset it to the system default. I'll carry it forward unless you want to reset it."
- Carry it forward explicitly in the generated statement.

Apply the **Property Omission Rule** from the loaded reference (`create-or-alter-guidance.md`) for the full list of which properties are preserved automatically vs. which must be carried forward explicitly.

---

### Step 4: Generate the Statement

**Default form — CREATE OR ALTER:**

```sql
CREATE OR ALTER [ TRANSIENT ] DYNAMIC TABLE <db>.<schema>.<name>
  [ (<col_name> <col_type> [ COLLATE '<collation>' ] [ COMMENT '<col_comment>' ] [, ...]) ]
  TARGET_LAG = { '<time>' | DOWNSTREAM }
  [ SCHEDULER = { DISABLE | ENABLE } ]
  WAREHOUSE = <warehouse_name>
  [ INITIALIZATION_WAREHOUSE = <warehouse_name> ]
  [ REFRESH_MODE = { AUTO | FULL | INCREMENTAL | ADAPTIVE | CUSTOM_INCREMENTAL } ]
  [ INITIALIZE = { ON_CREATE | ON_SCHEDULE } ]
  [ CLUSTER BY (<expr>, ...) ]
  [ DATA_RETENTION_TIME_IN_DAYS = <n> ]
  [ MAX_DATA_EXTENSION_TIME_IN_DAYS = <n> ]
  [ COMMENT = '<text>' ]
  [ REQUIRE USER ]
  [ FROZEN WHERE (<predicate>) ]
  [ BACKFILL FROM <source_table> ]
  [ START AT ... ]
  [ EXECUTE AS USER <user_name> ... ]
  [ ROW_TIMESTAMP = { TRUE | FALSE } ]
  { AS <SELECT query> | REFRESH USING ( <dml_statement> ) }
```

**Reinit-triggering change** — include this block in the approval checkpoint:
```
This change will reinitialize <table_name>.
The table will do a full recompute on its next refresh.
Downstream DTs are NOT affected — CREATE OR ALTER does not cascade reinitialization.
(If you used CREATE OR REPLACE instead, all downstream incremental DTs would also reinitialize.)
```

**Upstream → FULL mode change** — include this warning (do NOT also show the reinit block above):
```
Switching this DT to FULL refresh means downstream INCREMENTAL DTs
will fail on their next refresh with "no longer incrementalizable" (error 2742).
Review your downstream DTs before applying this change.
```

**Unsupported op redirected to CREATE OR REPLACE** — require explicit approval:
```
<operation> is not supported by CREATE OR ALTER.
This requires CREATE OR REPLACE, which will:
- Force a full reinitialization of <table_name>
- Cascade reinitialization to all downstream incremental DTs
Do you want to proceed with CREATE OR REPLACE?
```

**⚠️ STOPPING POINT**: Present the generated statement with all warnings. Wait for explicit approval before executing.

---

### Step 5: Execute and Verify

1. **Execute** the approved statement.

   **Pipeline changes (multiple DTs)**: execute each `CREATE OR ALTER` in a separate SQL call. If Snowflake returns an internal transaction error (e.g. "Nested Transaction detected", `NESTED_FDB_TXN`), wait 2–3 seconds and retry the same statement before considering any alternative. Do NOT fall back to `CREATE OR REPLACE` because of a transient internal error — the fallback would cascade reinitialization to all downstream DTs.

2. **Verify** the result:
   ```sql
   SHOW DYNAMIC TABLES LIKE '<name>' IN SCHEMA <db>.<schema>;
   ```
   Check: `scheduling_state`, `refresh_mode`, `target_lag`, `warehouse`, `frozen_where`.

3. **Definition changes do NOT trigger an immediate refresh.** The table refreshes on its normal schedule. Inform the customer of this and mention they can force an immediate refresh themselves if needed:
   ```sql
   ALTER DYNAMIC TABLE <name> REFRESH;
   ```
   Do **not** run this automatically — only if the customer explicitly asks.

4. **First-time creation with `INITIALIZE = ON_CREATE`** — poll for the initial refresh same as in [create/SKILL.md](../create/SKILL.md).

---

## Command Choice Guidance

Always prefer `CREATE OR ALTER` over `CREATE OR REPLACE`. For property-only changes, both `CREATE OR ALTER` and `ALTER DYNAMIC TABLE SET` are valid — prefer `CREATE OR ALTER` when the user asks for idempotent deployment or mentions a CI/CD pipeline; `ALTER DYNAMIC TABLE SET` is fine for a simple one-shot property tweak.

When `CREATE OR REPLACE` is unavoidable (type change, TRANSIENT toggle, column reorder): surface the downstream reinit cascade cost and require explicit approval.

See the **Why CREATE OR ALTER?** and **Downstream Cascade Rules** sections in `create-or-alter-guidance.md` for the full comparison.

---

## Never Do

- Silently omit an existing property — always carry it forward or explicitly warn about the reset
- Claim a reinit-triggering change is "non-destructive"
- Claim downstream tables will reinitialize when using `CREATE OR ALTER` (they are protected)
- Insert a column except at the end of the column list
- Include policies, tags, or DMFs in the `CREATE OR ALTER` statement — these require separate `ALTER` statements
- Change or drop COLLATE on an existing column (error 40053)
- Attempt to switch between CUSTOM_INCREMENTAL and regular refresh modes via `CREATE OR ALTER`
- Execute DDL without explicit user approval
