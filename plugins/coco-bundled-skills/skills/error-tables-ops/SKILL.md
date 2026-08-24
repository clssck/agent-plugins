---
name: error-tables-ops
description: "Assess, enable, monitor, and manage Error Tables (DML Error Logging) across your Snowflake account. Use when: error tables, error logging, ERROR_TABLE, DML errors, which tables should I enable, which tables have error logging, analyze errors, error table storage, error table retention, clean up errors, monitor errors, error table health, error table report, set up alerting, failed DML queries, string truncation, NOT NULL violation, numeric overflow, check constraint violation, constraint failed."
category: operate
tags:
  - error-tables
  - dml-error-logging
  - data-quality
  - data-engineering
---

# Error Tables Operations

Assess, enable, monitor, and manage Error Tables to streamline your Snowflake data pipelines. Instead of failing entire DML statements on bad data, Error Tables let good rows succeed while capturing rejected rows for analysis and repair.

**Docs:** [DML Error Logging](https://docs.snowflake.com/en/user-guide/data-load-overview#dml-error-logging)

## Stopping Points

- Before executing any DDL (`CREATE ALERT`, `CREATE TASK`, `ALTER TABLE`, `TRUNCATE`): present the DDL and get user approval
- Before enabling error logging on production tables: confirm the user understands the behavioral change (partial success instead of full rollback)
- **Before executing any Fix re-insert:** present the error breakdown from Step 1, ask the user how to handle each error type, and only generate/execute the INSERT after they approve
- After the Getting Started demo: ask if the user wants to proceed to Assess or clean up the test table

## Routing

Read the user's request and pick the right sub-skill:

| User intent | Sub-skill |
|------------|-----------|
| "Walk me through it" / "Set up error tables" / "Test error tables" / "Getting started" / "What are error tables" | **Getting Started** |
| "Which tables should I enable this on?" / "Where are my DML failures?" / "Would I benefit?" | **Assess** |
| "Which tables have error logging?" / "Find my error tables" / "List enabled tables" | **Discover** |
| "What errors am I catching?" / "Analyze my error table" / "Error breakdown" | **Analyze** |
| "Set up monitoring" / "Alert me when errors spike" / "Error table alerting" | **Monitor** |
| "Fix the rejected rows" / "Re-insert error data" / "Repair my data" | **Fix** |
| "Clean up old errors" / "Retention" / "Archive errors" / "Truncate" | **Manage** |
| "Temporarily disable" / "Opt out" / "Turn off for my session" / "Debug without error logging" | **Session Opt-Out** |
| "How much storage?" / "Error table size" / "Cost of error tables" | **Storage** |
| "Error tables report" / "Health summary" / "How are my error tables doing?" | **Report** |
| "MERGE/UPDATE with error tables" / "Which DML types are supported?" / "Column changes" | **MERGE & UPDATE** |
| "Transaction behavior" / "What happens in a transaction?" / "Rollback with error tables" | **Transactions** |
| "Iceberg tables" / "DR/replication" / "Failover" | **Iceberg & DR** |
| "Check constraint" / "constraint violation" / "CHECK failed" | **Analyze** (or **Getting Started** if they need a demo) |

If the user asks "what are error tables?" or mentions error tables without a clear operational intent, start with **Getting Started** to show a hands-on demo. If they already have error tables enabled, use **Report**; if exploring which tables to enable, use **Assess**.

---

## Reference: Error Codes

**Load** `references/notes.md` § "Error Codes" for the full table. Key codes used in all queries: 100072 (NOT NULL), 100078 (truncation), 100046 (overflow), 100038 (numeric), 100035 (type mismatch), 100040 (date/time), 100051 (div by zero), 100069 (unsupported conversion), 100320 (CHECK constraint — `error_source` is NULL; use `error_message` for constraint details).

---

## Sub-skill 0: Getting Started

**When to use:** User wants to try error tables, set up a test, or asks "walk me through it" or "what are error tables." Even for informational questions like "what are error tables?" — demonstrate with live SQL instead of explaining conceptually. Showing beats telling.

**What it does:** Executes each SQL step below against the user's Snowflake account, shows the results, and explains what happened. This is a hands-on demo, not a lecture.

> **EXECUTE the SQL** — run each step via the SQL tool, show the result, then explain. The user learns by seeing real output, not reading code blocks.

> **How Error Logging Works:** Error logging is a **TABLE property**, not a per-statement clause. `ERROR_LOGGING = TRUE` on a table automatically diverts bad rows during INSERT/UPDATE/MERGE — good rows succeed, bad rows go to `ERROR_TABLE()`. There is **NO** `ERROR_LOGGING = CONTINUE` clause on DML statements. Never suggest it.

> **What it captures:** Column-level data errors (NOT NULL, truncation, overflow, type mismatch, date/time, division by zero, unsupported conversion, CHECK constraint — see `references/notes.md` for codes). Errors deeper in query execution (subqueries, CTEs, expressions) fail the statement normally and are not diverted.

### Step 1: Create a table with error logging enabled

```sql
CREATE OR REPLACE TABLE {DATABASE}.{SCHEMA}.{TABLE_NAME} (
    ID NUMBER(10,0) NOT NULL,
    NAME VARCHAR(20) NOT NULL,
    EMAIL VARCHAR(30),
    BALANCE NUMBER(8,2),
    SIGNUP_DATE DATE NOT NULL
) ERROR_LOGGING = TRUE;
```

Or enable on an existing table:

```sql
ALTER TABLE {DATABASE}.{SCHEMA}.{TABLE_NAME} SET ERROR_LOGGING = TRUE;
```

### Step 2: Insert data — bad rows are automatically diverted

Use a standard INSERT. No special clause needed — errors are captured automatically:

```sql
INSERT INTO {DATABASE}.{SCHEMA}.{TABLE_NAME} VALUES
    (1, 'Alice Smith', 'alice@example.com', 1500.00, '2025-01-15'),
    (2, 'Bob Jones', 'bob@example.com', 2500.50, '2025-02-20'),
    -- String truncation: NAME > 20 chars
    (3, 'Bartholomew Christopherson III', 'bart@example.com', 500.00, '2025-04-01'),
    -- Numeric overflow: BALANCE > NUMBER(8,2) max
    (4, 'Eve Green', 'eve@example.com', 12345678.99, '2025-06-20'),
    -- NOT NULL violation: NULL NAME
    (5, NULL, 'nobody@example.com', 100.00, '2025-07-01');
```

Result: good rows are inserted, bad rows are diverted to the error table. The statement succeeds.

### Step 3: Query the error table

```sql
SELECT
    ERROR_CODE,
    CASE ERROR_CODE
        WHEN 100072 THEN 'NOT NULL violation'
        WHEN 100078 THEN 'String truncation'
        WHEN 100046 THEN 'Numeric overflow'
    END AS error_type,
    ERROR_METADATA:error_source::STRING AS offending_column,
    ERROR_DATA,
    TIMESTAMP
FROM ERROR_TABLE({DATABASE}.{SCHEMA}.{TABLE_NAME})
ORDER BY TIMESTAMP DESC;
```

### Step 4: Verify the base table has only good rows

```sql
SELECT * FROM {DATABASE}.{SCHEMA}.{TABLE_NAME} ORDER BY ID;
```

### Output guidance

Execute each step sequentially — show result, then explain. Key points: Step 2 → "INSERT succeeded, bad rows diverted"; Step 3 → explain `ERROR_DATA` JSON with `[]` brackets and `error_source`; Step 4 → only good rows landed. If permissions fail, try a different database/schema via `SELECT CURRENT_DATABASE(), CURRENT_SCHEMA()`.

---

## Sub-skill 1: Assess

**When to use:** Customer wants to know which tables would benefit from Error Tables before enabling it.

**What it does:** Scans `QUERY_HISTORY` for failed INSERT/UPDATE/MERGE with runtime error codes, extracts the target table from the error message, and ranks tables by failure volume.

**Parameters:**
- `{DAYS}` — lookback period (default: 30)

### Query: Find tables that would benefit

```sql
SELECT
    REGEXP_SUBSTR(error_message, 'to table ([^\\s]+)', 1, 1, 'e') AS target_table,
    CASE error_code
        WHEN 100072 THEN 'NOT NULL violation'
        WHEN 100078 THEN 'String truncation'
        WHEN 100046 THEN 'Numeric overflow'
        WHEN 100038 THEN 'Numeric not recognized'
        WHEN 100035 THEN 'Type mismatch'
        WHEN 100040 THEN 'Invalid date/time'
        WHEN 100051 THEN 'Division by zero'
        WHEN 100069 THEN 'Unsupported conversion'
        WHEN 100320 THEN 'CHECK constraint violation'
    END AS error_type,
    query_type AS statement_type,
    COUNT(*) AS failed_queries,
    COUNT(DISTINCT query_id) AS distinct_queries,
    MIN(start_time) AS first_failure,
    MAX(start_time) AS last_failure
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE execution_status = 'FAIL'
  AND query_type IN ('INSERT', 'UPDATE', 'MERGE')
  AND error_code IN (100072, 100078, 100046, 100038, 100035, 100040, 100051, 100069, 100320)
  AND start_time >= DATEADD('day', -{DAYS}, CURRENT_TIMESTAMP())
  AND error_message LIKE '%DML operation to table%'
GROUP BY 1, 2, 3
ORDER BY failed_queries DESC
LIMIT 20;
```

### Output guidance

Present a ranked table of tables with failed DML counts. **Always** end with `ALTER TABLE {table} SET ERROR_LOGGING = TRUE;` enable commands for each recommended table. Even when no results are found, still explain that `ALTER TABLE ... SET ERROR_LOGGING = TRUE` is how to enable error logging.

---

## Sub-skill 2: Discover

**When to use:** Customer wants to find which tables already have `ERROR_LOGGING = true` in their account.

**What it does:** Scans tables via `GET_DDL` and reports which have error logging enabled, plus the row count in each error table.

**Parameters:**
- `{DATABASE}` — database to scan (required)
- `{SCHEMA}` — schema to scan (required)

### Queries

**Load** `references/queries.md` § "Discover" for the `_find_error_logging_tables` stored procedure and the error table row count query.

The procedure uses `GET_DDL` + `ILIKE '%ERROR_LOGGING%true%'` to find enabled tables, then for each you query `ERROR_TABLE()` for row counts.

### Output guidance

Present a table showing each enabled table with its error row count, oldest/newest error, and distinct queries. Summarize: "N tables enabled, M actively catching errors." If none found: "No tables with ERROR_LOGGING = true found in {DATABASE}.{SCHEMA}."

**Account-wide discovery:** The stored procedure and `GET_DDL` scan are **per database/schema** — not a single account-wide sweep. If the user asks for "all tables in my account," say that they need to run discovery once per database/schema (or loop `INFORMATION_SCHEMA` / automate across schemas). Do not imply a single query lists every enabled table in the account.

---

## Sub-skill 3: Analyze

**When to use:** Customer wants to understand the error patterns in a specific error table.

**What it does:** Queries `ERROR_TABLE()` and breaks down errors by type, column, time period, and frequency.

**Parameters:**
- `{DATABASE}` — database
- `{SCHEMA}` — schema
- `{TABLE_NAME}` — base table name (not the error table — we use `ERROR_TABLE()`)
- `{DAYS}` — lookback period (default: 7)

### Query: Error breakdown by type and column

```sql
SELECT
    ERROR_CODE,
    CASE ERROR_CODE
        WHEN 100072 THEN 'NOT NULL violation'
        WHEN 100078 THEN 'String truncation'
        WHEN 100046 THEN 'Numeric overflow'
        WHEN 100038 THEN 'Numeric not recognized'
        WHEN 100035 THEN 'Type mismatch'
        WHEN 100040 THEN 'Invalid date/time'
        WHEN 100051 THEN 'Division by zero'
        WHEN 100069 THEN 'Unsupported conversion'
        WHEN 100320 THEN 'CHECK constraint violation'
    END AS error_type,
    COALESCE(ERROR_METADATA:error_source::STRING, ERROR_METADATA:error_message::STRING) AS offending_column,
    COUNT(*) AS error_count,
    MIN(TIMESTAMP) AS first_seen,
    MAX(TIMESTAMP) AS last_seen,
    COUNT(DISTINCT QUERY_ID) AS distinct_queries
FROM ERROR_TABLE({DATABASE}.{SCHEMA}.{TABLE_NAME})
WHERE TIMESTAMP >= DATEADD('day', -{DAYS}, CURRENT_TIMESTAMP())
GROUP BY 1, 2, 3
ORDER BY error_count DESC;
```

### Query: Error trend by day

```sql
SELECT
    TIMESTAMP::DATE AS error_date,
    COUNT(*) AS errors,
    COUNT(DISTINCT QUERY_ID) AS queries_with_errors,
    COUNT(DISTINCT ERROR_CODE) AS error_types
FROM ERROR_TABLE({DATABASE}.{SCHEMA}.{TABLE_NAME})
WHERE TIMESTAMP >= DATEADD('day', -{DAYS}, CURRENT_TIMESTAMP())
GROUP BY 1
ORDER BY 1 DESC;
```

### Output guidance

Present error breakdown table, then daily trend. Suggest fixes: string truncation → widen column, NOT NULL → check upstream NULLs, numeric overflow → increase precision, type mismatch → fix ETL transformation, CHECK constraint → correct values or adjust the constraint. **Note:** For CHECK constraint violations (100320), `error_source` is NULL — the constraint name and expression appear in `error_message` instead. The `COALESCE` in the query handles this automatically.

---

## Sub-skill 3b: Fix

**When to use:** Customer wants to use error table contents to fix rejected rows and re-insert them into the base table.

**What it does:** Shows how to extract rejected rows from `ERROR_TABLE()`, correct the offending values, and re-insert them. Requires `{DATABASE}`, `{SCHEMA}`, `{TABLE_NAME}`, and `{QUERY_ID}` (from the error table's `QUERY_ID` column).

### Step 1: Review what was rejected

```sql
SELECT
    ERROR_CODE,
    CASE ERROR_CODE
        WHEN 100072 THEN 'NOT NULL violation'
        WHEN 100078 THEN 'String truncation'
        WHEN 100046 THEN 'Numeric overflow'
    END AS error_type,
    ERROR_METADATA:error_source::STRING AS offending_column,
    ERROR_DATA
FROM ERROR_TABLE({DATABASE}.{SCHEMA}.{TABLE_NAME})
WHERE QUERY_ID = '{QUERY_ID}'
ORDER BY TIMESTAMP DESC
LIMIT 20;
```

> **⛔ STOP AFTER STEP 1 — DO NOT EXECUTE ANY INSERT UNTIL THE USER APPROVES THE FIX PLAN.**
> After executing Step 1 (review), you MUST present the error breakdown and ask the user how to handle each error type BEFORE generating or executing any INSERT. This is a data modification — the user decides what happens to their data, not the agent.

### Step 2: Ask the user how to fix each error type

Present each distinct error type from Step 1 with options: truncation → truncate to fit / drop; NOT NULL → default value / drop; overflow → cap at max / drop; type mismatch → TRY_CAST / drop; date → TRY_TO_DATE / drop; CHECK (100320) → adjust value / drop.

**Fast path:** If the user said "just fix them" or "auto-fix" — skip the ask and apply sensible defaults (truncate strings, replace NULLs with `'UNKNOWN'`/`0`/`CURRENT_DATE()`, cap overflow, use `TRY_*` for type/date). Otherwise, always ask first.

### Step 3: Generate and execute the re-insert

Only after approval (or fast path). Use `TRY_TO_NUMBER` / `TRY_TO_DATE` in **ALL** numeric/date ELSE branches — Snowflake evaluates all CASE branches, so bare `::NUMBER` casts fail on array-wrapped overflow values. `::STRING` is safe for VARCHAR.

```sql
INSERT INTO {DATABASE}.{SCHEMA}.{TABLE_NAME} (ID, NAME, BALANCE)
SELECT
    CASE WHEN ERROR_CODE = 100072 AND ERROR_METADATA:error_source::STRING = 'ID'
         THEN {replacement_id}
         ELSE TRY_TO_NUMBER(ERROR_DATA:ID::STRING) END AS ID,
    CASE WHEN ERROR_CODE = 100078 AND ERROR_METADATA:error_source::STRING = 'NAME'
         THEN LEFT(ERROR_DATA:NAME[0]::STRING, 20)
         WHEN ERROR_CODE = 100072 AND ERROR_METADATA:error_source::STRING = 'NAME'
         THEN 'UNKNOWN'
         ELSE ERROR_DATA:NAME::STRING END AS NAME,
    CASE WHEN ERROR_CODE = 100046 AND ERROR_METADATA:error_source::STRING = 'BALANCE'
         THEN 999999.99
         ELSE TRY_TO_NUMBER(ERROR_DATA:BALANCE::STRING) END AS BALANCE
FROM ERROR_TABLE({DATABASE}.{SCHEMA}.{TABLE_NAME})
WHERE QUERY_ID = '{QUERY_ID}';
```

Rows the user chose to "Drop" → exclude via `WHERE NOT (ERROR_CODE = ... AND ...)`.

### Output guidance

Adapt CASE logic to the customer's schema. Never use bare `::NUMBER` on `ERROR_DATA` fields — always `TRY_TO_NUMBER(ERROR_DATA:col::STRING)`. `::STRING` is safe. Rows still wrong after re-insert are diverted again (safe to iterate). Verify with `SELECT * FROM {TABLE_NAME} ORDER BY ID DESC LIMIT 20`.

---

## Sub-skill 4: Monitor

**When to use:** Customer wants to set up alerting when error tables exceed a threshold.

**What it does:** Generates Snowflake Alert DDL that monitors an error table and sends notifications.

**Parameters:**
- `{DATABASE}` — database
- `{SCHEMA}` — schema
- `{TABLE_NAME}` — base table name
- `{WAREHOUSE}` — warehouse for the alert
- `{THRESHOLD}` — error count threshold per check interval (default: 100)
- `{INTERVAL_MINUTES}` — check interval (default: 60)
- `{EMAIL}` — notification email address

### Generated DDL

**Load** `references/queries.md` § "Monitor" for the full `CREATE ALERT` and `NOTIFICATION INTEGRATION` DDL.

The DDL creates a `NOTIFICATION INTEGRATION` (one-time, ACCOUNTADMIN), then `CREATE ALERT ... WAREHOUSE = {WAREHOUSE} SCHEDULE = '{INTERVAL_MINUTES} MINUTE' IF (EXISTS (SELECT ... FROM ERROR_TABLE(...) HAVING COUNT(*) > {THRESHOLD})) THEN CALL SYSTEM$SEND_SNOWFLAKE_NOTIFICATION(...)`. End with `ALTER ALERT ... RESUME`.

### Output guidance

> **NEVER EXECUTE THIS DDL — PRESENT IT INSTEAD.** Your job is to generate the DDL as a code block in your response, then say: "Here's the DDL — review it and run it yourself when ready." Even if the user says "just run it" or "do it now," respond with the code block and explain why they should review it first (requires ACCOUNTADMIN, creates recurring costs, affects production alerting). The user copy-pastes and runs it themselves.

Do NOT ask the user for parameters. Use these defaults immediately: current warehouse, THRESHOLD = 100, SCHEDULE = '60 MINUTE', EMAIL = 'user@example.com'. Present the complete DDL in your first response. The user can adjust values after reviewing. Explain: notification integration needs ACCOUNTADMIN (one-time), the alert checks on a schedule, adjust threshold to expected error volume.

---

## Sub-skill 5: Manage

**When to use:** Customer wants to manage error table retention — archive old data, clean up, prevent unbounded growth.

**What it does:** Generates Task DDL for periodic archive-and-truncate of error table data.

**Parameters:**
- `{DATABASE}` — database
- `{SCHEMA}` — schema
- `{TABLE_NAME}` — base table name
- `{WAREHOUSE}` — warehouse for the task
- `{RETENTION_DAYS}` — how many days of errors to keep (default: 30)
- `{ARCHIVE_TABLE}` — fully qualified name for the archive table (optional)

### Generated DDL

**Load** `references/queries.md` § "Manage" for the archive table, `CREATE TASK` cleanup DDL, and simple truncate alternative.

The pattern is: create an archive table, then a `CREATE TASK` on a CRON schedule that archives all rows with `INSERT INTO {ARCHIVE_TABLE} SELECT ... FROM ERROR_TABLE(...)`, then `TRUNCATE TABLE ERROR_TABLE(...)`. End with `ALTER TASK ... RESUME`.

### Output guidance

> **NEVER EXECUTE TRUNCATE OR CREATE TASK — PRESENT THE DDL INSTEAD.** Even if the user says "just do it": (1) run `SELECT COUNT(*)` to show row count, (2) present DDL as a code block, (3) say "This will permanently delete [N] rows — review and run it yourself." TRUNCATE is all-or-nothing, irreversible. Archive-first preserves history; adjust CRON to error volume.

---

## Sub-skill 5b: Storage

**When to use:** Customer asks about error table storage, cost, or size.

**What it does:** Provides a **best-effort estimate** of how much rejected-row data is currently in the error table (row counts + approximate payload size).

> **Note:** Error tables are **nested objects under the base table** — they are not standalone tables with their own DB/SCHEMA identity. How (or whether) their storage appears in `TABLE_STORAGE_METRICS` or billing views is unconfirmed. Do **not** claim inclusion/exclusion in `TABLE_STORAGE_METRICS`. If the customer asks about billing attribution, call this out as unknown.

### Query: Estimate error table payload size

```sql
SELECT COUNT(*) AS error_rows,
    ROUND(AVG(52 + LENGTH(TO_VARCHAR(ERROR_METADATA)) + LENGTH(TO_VARCHAR(ERROR_DATA))), 0) AS avg_bytes_per_row,
    ROUND(SUM(52 + LENGTH(TO_VARCHAR(ERROR_METADATA)) + LENGTH(TO_VARCHAR(ERROR_DATA))) / (1024*1024), 2) AS estimated_raw_mb
FROM ERROR_TABLE({DATABASE}.{SCHEMA}.{TABLE_NAME});
```

### Output guidance

Lead with: this provides a **best-effort estimate** based on `ERROR_TABLE()` contents. Show row count, estimated raw payload, and average bytes per error row. If empty: "No error rows found." Do **not** reference `TABLE_STORAGE_METRICS` or claim error table storage is included/excluded from base table billing.

---

## Sub-skill 6: Report

**When to use:** Customer wants a health summary across all their error tables.

**What it does:** Combines Discover + Analyze across all enabled tables in a schema to produce a cross-table health summary.

**Parameters:**
- `{DATABASE}` — database
- `{SCHEMA}` — schema
- `{DAYS}` — lookback period (default: 7)

### Workflow

1. Run the **Discover** stored procedure (`_find_error_logging_tables`) to find all tables with error logging enabled
2. For each discovered table, query `ERROR_TABLE()` with the **Analyze** error breakdown query to get error counts, types, and trends
3. Combine into a single health summary showing enabled table count, total error rows, and per-table breakdown

### Output guidance

Present a summary table showing: enabled table count, total error rows, and per-table breakdown with columns for errors, trend (↑/↓/→ flat/NEW), top error type, and top column. End with actionable recommendations per table.

Calculate trend by comparing current period error count to the prior period of the same length (↑ increasing, ↓ decreasing, → flat within 10%, NEW if no prior errors).

---

## Sub-skill 7: Session Opt-Out

**When to use:** User wants to temporarily disable error logging for their session, or asks about opting out.

The **only** session parameter is `OPT_OUT_ERROR_LOGGING`:

```sql
ALTER SESSION SET OPT_OUT_ERROR_LOGGING = TRUE;   -- disable for this session
ALTER SESSION SET OPT_OUT_ERROR_LOGGING = FALSE;  -- re-enable (default)
```

When `TRUE`, DML errors fail normally — table property unchanged, other sessions unaffected, resets at session end. No other session parameter exists for error logging — do not invent names like `ENABLE_ERROR_TABLE`.

---

## Sub-skill 8: MERGE & UPDATE

**When to use:** User asks about MERGE, UPDATE, or INSERT behavior with error tables, or about column/schema changes.

Error Tables support all three DML types: **INSERT, UPDATE, and MERGE**. All three divert bad rows to the error table when `ERROR_LOGGING = TRUE` is set on the target table.

For MERGE specifically:
- Bad rows from WHEN MATCHED (UPDATE) or WHEN NOT MATCHED (INSERT) clauses are captured
- `ERROR_DATA` contains the full rejected row as a JSON VARIANT with the offending column value in `[]` brackets
- `ERROR_METADATA:error_source` identifies the column that caused the error

**Column evolution:** The error table structure (5 fixed columns) is never altered by base table DDL. Renames, adds, and drops only affect the **contents** of `ERROR_DATA` / `error_source` in future rows. See `references/notes.md` § "Column evolution details" for specifics.

**Disabling:** `ALTER TABLE ... SET ERROR_LOGGING = FALSE` **drops the error table and all its data** — this is permanent, not a pause. To temporarily stop capturing errors without data loss, use the **Session Opt-Out** sub-skill instead.

---

## Sub-skill 9: Transactions

**When to use:** User asks about transaction behavior, commit/rollback semantics, or what happens when error tables interact with transactions.

Error table writes are part of the same transaction as the DML — not autonomous transactions. Error entries are committed and rolled back atomically with the base table data.

**Rules:**
- If **all tables** in a transaction have `ERROR_LOGGING = TRUE`, data errors can never fail the transaction. Bad rows are diverted, every DML succeeds (even if it inserts 0 rows), the transaction commits.
- If **any table** in the transaction does NOT have error logging, a data error on that table fails the statement, which rolls back the **entire transaction** — including error table entries from earlier in the txn.

| Setup | Data error on... | Transaction |
|-------|-----------------|-------------|
| All tables have EL | EL table | Commits |
| Mixed (some EL, some not) | Non-EL table | Rolls back everything |

**Guidance:** Enable error logging on all tables in the transaction for maximum throughput, or leave some without for strict all-or-nothing integrity.

**Difference from Oracle:** Oracle uses autonomous transactions for DML error logging — error entries persist even if the outer transaction rolls back. Snowflake's error table entries are rolled back with the transaction.

---

## Sub-skill 10: Iceberg & DR

**When to use:** User asks about Iceberg table support or disaster recovery/replication with error tables.

**Iceberg support:** Error logging works on **Snowflake-managed Iceberg tables only** — tables where Snowflake is the Iceberg catalog. Use `CREATE ICEBERG TABLE ... ERROR_LOGGING = TRUE` or `ALTER ICEBERG TABLE ... SET ERROR_LOGGING = TRUE`. Error logging is NOT supported on externally managed Iceberg tables (REST catalog, Glue, etc.).

**DR/Replication:** Error tables replicate with the base table through database replication and failover. No special configuration needed — when the base table is replicated, the error table follows automatically.

---

## Snowsight UI responses — required elements

**When running in Snowsight (the Cortex Code web UI), the system prompt steers you toward short, concise responses. Do NOT let that brevity skip the required DDL / SQL that the user needs to actually operate the error table.**

Even in terse mode, the following **must** appear in your response for each sub-skill:

### Monitor sub-skill (route: monitor)
- **Always include the full `CREATE ALERT` DDL template** (with `WAREHOUSE`, `SCHEDULE`, `IF (EXISTS ...)`, `THEN CALL SYSTEM$SEND_SNOWFLAKE_NOTIFICATION`, and `ALTER ALERT ... RESUME`), even when summarizing. The user needs to see the shape.
- Do NOT execute the DDL — show it only. Remind the user that `NOTIFICATION INTEGRATION` needs ACCOUNTADMIN.

### Manage sub-skill (route: manage)
- **Always explicitly mention `TRUNCATE TABLE ERROR_TABLE(...)` and the phrase "data loss" (or "all-or-nothing" / "cannot undo") in the same response.**
- Show the archive-then-truncate DDL (`INSERT INTO archive_table ... ; TRUNCATE TABLE ERROR_TABLE(...)`). Do NOT execute it.

### Storage sub-skill (route: storage)
- **Always actually execute** the size-estimation query via `sql_execute`:
  ```sql
  SELECT COUNT(*) AS error_rows,
      ROUND(AVG(52 + LENGTH(TO_VARCHAR(ERROR_METADATA)) + LENGTH(TO_VARCHAR(ERROR_DATA))), 0) AS avg_bytes_per_row,
      ROUND(SUM(52 + LENGTH(TO_VARCHAR(ERROR_METADATA)) + LENGTH(TO_VARCHAR(ERROR_DATA))) / (1024*1024), 2) AS estimated_raw_mb
  FROM ERROR_TABLE({DATABASE}.{SCHEMA}.{TABLE_NAME});
  ```
  Do not just describe how to do it — run it and report the numbers.

### Enable-existing (route: assess / getting-started when user asks to enable on an existing table)
- **Always execute `ALTER TABLE {fqn} SET ERROR_LOGGING = TRUE` as a SQL tool call** — do not just quote the statement in prose.
- Follow up by confirming the change with `DESCRIBE TABLE {fqn}` or `SHOW TABLES LIKE ...`.

### Discover sub-skill (route: discover)
- UI agents should use `INFORMATION_SCHEMA.TABLES` combined with `GET_DDL('TABLE', fqn)` to find `ERROR_LOGGING = true` — this is the only metadata surface that exposes the setting. `SHOW TABLES` alone does not reveal `ERROR_LOGGING`.

**These rules apply regardless of response length guidance from the UI system prompt.** Concise means "no filler prose" — it does NOT mean "skip the required SQL/DDL."

---

## Important Notes

**Load** `references/notes.md` for additional reference on performance overhead and column evolution details.

Key points to always remember:
- `ERROR_TABLE()` requires the base table name, not the error table name
- Only the **owner** of the base table can SELECT from the error table
- Supported operations on error tables: **SELECT and TRUNCATE only**
- The Monitor and Manage sub-skills generate DDL for you to review and run — **DDL is not executed automatically**
- Supported DML types: **INSERT, UPDATE, and MERGE**