---
name: document-multi-step-pipeline
description: "Build persistent document processing pipelines using Snowflake streams, tasks, and dynamic tables with Cortex AI functions. Use when: building automated document pipelines, processing invoices/contracts/receipts continuously, chaining OCR + extraction + translation + classification + enrichment, document pipeline with dynamic tables, AI_PARSE_DOCUMENT pipeline, AI_EXTRACT pipeline, PDF processing pipeline, OCR pipeline, invoice pipeline, document ingestion pipeline. Triggers: document processing pipeline, process documents automatically, extract data from documents continuously, build document pipeline, invoice processing pipeline, PDF pipeline, OCR pipeline, document ingestion, document chain, parse and extract pipeline."
parent_skill: ai-functions-pipeline-builder
---

# Document Processing Pipeline

Build persistent document processing pipelines using a hybrid architecture: a stream+task for event-driven document ingestion, then dynamic tables for declarative AI processing.

## When to Use

Use this skill when users want to:
- Build a **persistent pipeline** that automatically processes new documents as they arrive
- Chain multiple AI operations (OCR → extract → translate/classify/enrich) declaratively
- Set up continuous invoice, contract, receipt, or form processing

**Do NOT use for:**
- One-off document extraction or parsing → use this skill's [One-off tasks](../SKILL.md#one-off-tasks) path instead
- General dynamic table operations without documents → use `dynamic-tables` skill instead

## For Specializations (use-case templates)

This skill is the **generic base** for use-case-specific pipeline templates (e.g. `templates/invoice-processing/`). A specialization reuses this file's mechanics and overrides only its own domain concerns:

| Base owns (do not re-implement) | Specialization may override |
|--------------------------------|---------------------------|
| Hybrid architecture, AI-function rules, block palette + shape contract | Domain intake (replaces Step 2), domain defaults (schemas, categories, thresholds), domain-specific smoke-test checks |
| Steps 6–10 (verify, lag, test, go-live, monitor) | Which blocks to compose and their parameters |

A specialization should declare at its top that it reads this base first, then list its overrides. Never silently fork base-owned mechanics — that's the drift this split prevents.

## Architecture

```
@STAGE (directory-enabled)
    │
    ▼
STREAM on stage ──► TASK (triggered)
                      │
                      ▼
              TABLE: File Log    ← Append-only log of new files (regular table)
                      │
                      ▼
              DT: Parse/OCR      ← AI_PARSE_DOCUMENT for text extraction
                      │             REFRESH_MODE = INCREMENTAL, TARGET_LAG = DOWNSTREAM
                      ▼
              DT: Extract         ← AI_EXTRACT for structured field extraction
                      │             REFRESH_MODE = INCREMENTAL, TARGET_LAG = DOWNSTREAM
                      ▼
              DT: Enrich          ← AI_TRANSLATE, AI_CLASSIFY, AI_SUMMARIZE, etc. (optional)
                (optional)          REFRESH_MODE = INCREMENTAL, TARGET_LAG = '<user-chosen>'
```

**Why hybrid:** Directory tables have no change tracking, so an all-DT pipeline is forced to `REFRESH_MODE = FULL` — re-running AI on every file every refresh. The stream+task writes each file exactly once into the File Log (a regular table with change tracking), which downstream DTs read incrementally. AI functions run only on new files.

## ⚠️ CRITICAL: AI Function Rules

1. **AI function names: no `SNOWFLAKE.CORTEX` prefix** — write `AI_EXTRACT(...)`, not `SNOWFLAKE.CORTEX.AI_EXTRACT(...)`
2. **Display pricing before any AI execution** — see the parent [`../SKILL.md`](../SKILL.md) § Pricing
3. **`TO_FILE` takes two separate arguments** — `TO_FILE('@stage', 'filename.pdf')`, never `TO_FILE('@stage/filename.pdf')`
4. **Stage files inside DTs: `TO_FILE('@<stage>', RELATIVE_PATH)` only** — call it inline in the DT body. Never `BUILD_SCOPED_FILE_URL`/`SCOPED_FILE_URL` (non-deterministic in DT definitions; URLs expire on next refresh).
5. **No `LATERAL`-join to AI/UDTFs in incremental DTs** — demotes to `FULL` refresh. Call AI inline. Exception: `LATERAL FLATTEN` over an already-materialized VARIANT/array stays incremental; select `f.index`, never `f.seq`.

---

## ⚠️ Operating mode: autonomous vs interactive

`[WAIT]` / **MANDATORY STOPPING POINT** markers are for interactive use. In autonomous mode ("build it live", non-interactive session): pick the sensible default, state the assumption in one line, and proceed — halting for input that never comes leaves the pipeline half-built.

## ⚠️ Definition of done (NOT done until the pipeline is live AND populated)

Creating objects is not the finish line. Before reporting complete:

1. **Initial refresh forced** — a DT created with `INITIALIZE = ON_SCHEDULE` is empty until its first refresh; trigger it and poll until done (Step 8a). Never accept a printed SQL string as proof — only a state query counts.
2. **Terminal deliverable verified** — `SELECT COUNT(*)` for rows, then confirm key extracted columns are non-NULL: `SELECT COUNT(*), COUNT(<key_col>) FROM <deliverable>`. If the second count is 0, rows are hollow (almost always a missing `:response:` hop or classifier token mismatch — fix per `blocks/extract/`).
3. **Refresh confirmed SUCCEEDED** — poll `last_completed_refresh_state` until `SUCCEEDED`; a SQL timeout on a large AI backfill is not a failure, not a reason to drop/rebuild.
4. **Ingestion triad present** — run these and verify a non-zero count for each:
   ```sql
   SHOW STREAMS IN SCHEMA <db>.<schema>;          -- MUST be >= 1
   SHOW TASKS IN SCHEMA <db>.<schema>;            -- MUST be >= 1
   SHOW DYNAMIC TABLES IN SCHEMA <db>.<schema>;   -- MUST be >= 1, per-grain AI DTs INCREMENTAL
   ```
   Count = 0 means not done. Most common gaps: no stream, a stream with no task, or a task+MERGE into a static table with no INCREMENTAL DT.
5. **Every lane built AND populated** — `SELECT COUNT(*)` the terminal object of each lane the requirement named. A second lane silently dropped delivers nothing even when the dominant lane is correct.

## ⚠️ Required architecture (don't improvise — this is load-bearing)

The pipeline MUST have:
- **≥ 1 STREAM** on the stage (event-driven ingestion)
- **≥ 1 TASK** that loads new files into the File Log
- **≥ 1 INCREMENTAL DYNAMIC TABLE** doing the AI processing

Do NOT substitute CTAS, plain tables refreshed by a stored procedure, or a DT demoted to `REFRESH_MODE = FULL`. Adapt `blocks/` DDL rather than writing DT DDL from memory.

**Not done** if any SHOW returns 0, a per-grain AI DT is `FULL`, or a deliverable is empty. Aggregate/rollup DTs `FULL` are correct — leave them.

## ⚠️ Fix the query — never demote the architecture

DT empty → force refresh + poll `last_completed_refresh_state` (population timing; `CREATE OR REPLACE` resets the baseline and back-fills from upstream on first run). All-NULL column → wiring bug: wrong key or missing `:response:` hop, fix the SELECT. Foreground AI timeout → expected on large batches; put AI in an INCREMENTAL DT. Always `CREATE OR REPLACE` the one object — never drop or rebuild as CTAS/stored-proc.

## ⚠️ NEVER run AI functions inline in a blocking statement

Do **not** call AI functions inside a foreground `INSERT … SELECT`, CTAS, or a batch proc you wait on. Over many documents these time out — a 50-PDF synchronous parse can burn the entire task budget. Put the AI call in an **INCREMENTAL dynamic table** and poll it (Step 8a); move on while it refreshes.

## ⚠️ `DIRECTORY()` is not allowed inside a dynamic table

`CREATE DYNAMIC TABLE … AS SELECT … FROM DIRECTORY(@stage)` fails (`Object ref … of type DIRECTORY_TABLE not supported`): directory tables have no change tracking. The fix is never CTAS, stored-proc, or File Log + task without a STREAM: it is always **(1)** `CREATE STREAM … ON STAGE`, **(2)** `CREATE TASK` inserting stream rows into the File Log, **(3)** DTs reading the File Log. A pivot that keeps the File Log + task but drops the STREAM is still incomplete — verify `SHOW STREAMS >= 1`. A DT timeout on initial AI refresh is a population-timing issue (Definition of done, item 3), not a reason to rebuild as a static table.

**Name collision** (`Object '<name>' already exists as TABLE`): drop the plain table (`DROP TABLE <name>`) and re-issue the DT creation. The architecture is unchanged.

## ⚠️ Use the real warehouse and fully-qualified names

Discover the warehouse (`SELECT CURRENT_WAREHOUSE()`, `$SNOWFLAKE_WAREHOUSE`, or `SHOW WAREHOUSES`) — never guess a name; a wrong one silently prevents the task/DT from running. Qualify every object as `<db>.<schema>.<name>`. Resolve env vars (`$SCRATCH_DATABASE`, `$SCRATCH_SCHEMA`) via `echo` before use — shell variables, not SQL session variables.

---
## Workflow

### Step 1: Present Pipeline Options [WAIT]

Confirm the user wants the **dynamic-tables-based pipeline**:

> This skill builds a hybrid pipeline: a stream + task detects new files and loads them into a File Log; dynamic tables do the AI processing incrementally — each new file triggers AI only on that file. Alternatives are pure streams + tasks (imperative) or dbt (if already in use). Let me know if you'd prefer one and I'll step out of this skill.

**⚠️ MANDATORY STOPPING POINT**: Proceed only after confirmation.

---

### Step 2: Gather Requirements [WAIT]

Ask for: document type (PDFs/images/Office/mixed), extraction goal (fields/text/classification/combination), target db.schema, existing or new stage, and warehouse name.

**⚠️ MANDATORY STOPPING POINT**: Do NOT proceed until the user provides requirements.

Based on the response, determine which layers are needed:

| Requirement | Layers Needed |
|-------------|---------------|
| Full text only | File Log → Parse/OCR |
| Structured fields from PDFs | File Log → Parse/OCR → Extract |
| Structured fields + translation | File Log → Parse/OCR → Extract → Enrich (translate) |
| Fields extracted directly from files | File Log → Extract (direct on file) |
| Classification + extraction | File Log → Parse/OCR → Extract → Enrich (classify) |

---

### Step 3: Create Stage

Create a directory-enabled stage if the user doesn't have one:

```sql
CREATE STAGE IF NOT EXISTS <db>.<schema>.<stage_name>
  DIRECTORY = (ENABLE = TRUE)
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');
```

---

### Step 4: Create the Ingestion Layer (Stream + Task + File Log Table)

This layer detects new file uploads and appends them to a regular table.

#### 4a. Create the File Log table

```sql
CREATE TABLE IF NOT EXISTS <db>.<schema>.<prefix>_FILE_LOG (
  RELATIVE_PATH STRING,
  FILE_NAME STRING,
  FILE_SIZE NUMBER,
  LAST_MODIFIED TIMESTAMP_LTZ,
  FILE_URL STRING,
  INGESTED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- This table is the base for the downstream dynamic tables. Snowflake auto-enables
-- change tracking when the first DT is created on it, but set it explicitly so
-- incremental refresh works deterministically from the first run.
ALTER TABLE <db>.<schema>.<prefix>_FILE_LOG SET CHANGE_TRACKING = TRUE;
```

#### 4b. Create the stream on the stage

```sql
CREATE OR REPLACE STREAM <db>.<schema>.<prefix>_STAGE_STREAM
  ON STAGE <db>.<schema>.<stage_name>;
```

#### 4c. Create the ingestion task

```sql
CREATE OR REPLACE TASK <db>.<schema>.<prefix>_INGEST_TASK
  WAREHOUSE = <warehouse>
  SCHEDULE = '5 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('<db>.<schema>.<prefix>_STAGE_STREAM')
AS
  INSERT INTO <db>.<schema>.<prefix>_FILE_LOG (RELATIVE_PATH, FILE_NAME, FILE_SIZE, LAST_MODIFIED, FILE_URL)
  SELECT
    RELATIVE_PATH,
    SPLIT_PART(RELATIVE_PATH, '/', -1),
    SIZE,
    LAST_MODIFIED::TIMESTAMP_LTZ,
    FILE_URL
  FROM <db>.<schema>.<prefix>_STAGE_STREAM
  WHERE METADATA$ACTION = 'INSERT'
    AND (RELATIVE_PATH ILIKE '%.pdf'    -- ILIKE = case-insensitive; also matches .PDF/.Pdf. Adjust extensions as needed.
      OR RELATIVE_PATH ILIKE '%.png'
      OR RELATIVE_PATH ILIKE '%.jpg');
-- Leave the task SUSPENDED for now (CREATE TASK starts suspended). It stays suspended
-- through build, verification, and testing. Step 9 resumes it only after Step 6 confirms
-- INCREMENTAL refresh and Step 8 confirms quality — so scheduled ingestion never starts
-- AI spend before the pipeline is verified safe.
```

The task only runs when new files are detected. Each file is inserted into the File Log exactly once.

#### 4d. Seed the backlog (only if the stage already has files)

A stream captures only files added **after** it is created, so any files already on the stage when you
build the pipeline never flow through the task. Seed them into the File Log once, directly from the
directory table:

```sql
ALTER STAGE <db>.<schema>.<stage_name> REFRESH;  -- refresh the directory table first
INSERT INTO <db>.<schema>.<prefix>_FILE_LOG (RELATIVE_PATH, FILE_NAME, FILE_SIZE, LAST_MODIFIED, FILE_URL)
SELECT RELATIVE_PATH, SPLIT_PART(RELATIVE_PATH, '/', -1), SIZE, LAST_MODIFIED::TIMESTAMP_LTZ, FILE_URL
FROM DIRECTORY(@<db>.<schema>.<stage_name>)
WHERE RELATIVE_PATH ILIKE '%.pdf';  -- match the same extensions as the task
```

> **Path gotcha:** `DIRECTORY()` and `TO_FILE()` use the **bare** `RELATIVE_PATH` returned by `DIRECTORY()`,
> which can differ from what `LIST @stage` prints (LIST may show a prefixed path). Always use the
> directory-table value, or `TO_FILE` will fail with "file not found".

---

### Step 4½: Confirm the AI models exist before wiring them into DTs

A wrong or unavailable model name fails **only on refresh** and cascades silently. Before writing any AI DT, probe each distinct model:

```sql
SELECT AI_COMPLETE('<model>', 'ping');                              -- text/reasoning model
SELECT AI_COMPLETE('<vision_model>', 'Describe this file.',
                   TO_FILE('@<db>.<schema>.<stage>', '<one file>')); -- vision model, on a real file
```

**Vision lanes must be probed with an actual file** — a text-only model compiles and returns non-NULL text for a file argument yet produces useless output. See [`../blocks/conventions.md`](../blocks/conventions.md) § Choosing models.

---

### Step 5: Build the Processing Chain (Dynamic Tables)

Since the File Log is a regular table, downstream DTs can use `REFRESH_MODE = INCREMENTAL` — they only process newly inserted rows.

Present all CREATE statements together, then get approval before executing.

All processing layers live as composable **blocks** in [`../blocks/`](../blocks/) — the single source of truth for layer SQL. This base owns only the workflow around them (Steps 5–10) and the AI Function Rules above.

**Compose the chain from the palette:**

1. Read [`../blocks/conventions.md`](../blocks/conventions.md) — the data-shape vocabulary every block's
   `Reads`/`Produces` is written in, plus the compose rules and the refresh-mode contract.
2. Use the router [`../blocks/README.md`](../blocks/README.md) to pick the blocks the requirement needs
   (the table in Step 2 maps each requirement to a layer). Load only those files.
3. Order them by matching each block's `Reads` shape to an upstream block's `Produces` shape — `ingest/` is
   always the head, a `serve/` view/app the tail. Intermediate DTs use `TARGET_LAG = DOWNSTREAM`; only the
   terminal DT takes the user's lag.

Backbone for a typical extract pipeline: `ingest/ingestion` → `ingest/parse-text` → `extract/fields` → `serve/final-shape` (add `extract/classify`, `records/*`, `analyze/*`, or `search/*` as needed). Each block carries its own refresh-mode tag and gotchas; don't reproduce SQL here.

**⚠️ MANDATORY STOPPING POINT**: compile-validate every statement (`sql_execute only_compile: true`; fix root cause, re-validate), display the pricing estimate (see [`../SKILL.md`](../SKILL.md) § Pricing — applies to dry-run SELECTs too), then wait: present the compile-validated CREATEs + pricing before executing.

Once the CREATEs execute, the DTs backfill from the File Log on their first refresh. Leave the ingest task **suspended** — it's resumed in Step 9, after the safety gates.

---

### Step 6: Verify Incremental Refresh Mode

**⚠️ MANDATORY CHECK — run immediately after creating all DTs.** A `FULL` AI DT re-runs on every file on every refresh.

> **Naming:** every DT must be `DT_<prefix>_*`. The query below filters on that prefix — an unprefixed DT is silently skipped. Expose user-facing names as **views** over `DT_<prefix>_*` DTs, never as bare dynamic tables.

```sql
SHOW DYNAMIC TABLES LIKE 'DT_<prefix>%' IN SCHEMA <db>.<schema>;
SELECT "name", "refresh_mode", "refresh_mode_reason"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
ORDER BY "name";
```

> `refresh_mode`/`refresh_mode_reason` are columns of **`SHOW DYNAMIC TABLES`**, not of `INFORMATION_SCHEMA.DYNAMIC_TABLES()` (which exposes lag and refresh-*state* columns, not the mode). Read them via `SHOW … ` + `RESULT_SCAN`; the column names are lowercase and must be double-quoted.

**Expected:** All DTs show `refresh_mode = 'INCREMENTAL'`.

**If any DT shows `refresh_mode = 'FULL'`:**

1. Read `refresh_mode_reason` — it explains why Snowflake chose FULL
2. Common causes and fixes:

| `refresh_mode_reason` | Cause | Fix |
|----------------------|-------|-----|
| `QUERY_NOT_SUPPORTED_FOR_INCREMENTAL` | Query pattern not eligible | Simplify the SELECT — avoid non-deterministic functions, certain JOINs, or subqueries. Check `dynamic-tables/references/incremental-operators.md` for supported patterns. |
| `UPSTREAM_IS_FULL_REFRESH` | An upstream DT is FULL | Fix the upstream DT first — the problem cascades down the chain |
| `USER_SPECIFIED_FULL` | `REFRESH_MODE = FULL` was explicitly set | Change to `REFRESH_MODE = INCREMENTAL` via ALTER or recreate |

3. **Fix and re-verify** before proceeding. Do NOT continue with a FULL-refresh DT that calls AI functions.

**Incremental-eligible patterns (verified):** window functions, `QUALIFY`, `ROW_NUMBER`/`COUNT(*) OVER (… )`, `GROUP BY` aggregates, and self-joins (e.g. a vendor 12-month rolling mean joined back to the header) all stay `INCREMENTAL`. Known exclusions: `PERCENT_RANK`/`DENSE_RANK`/`RANK` with *sliding* window frames, `ANY_VALUE`, `GROUP BY ROLLUP`/`CUBE`/`GROUPING SETS`, and `LATERAL`-joins to UDTFs/AI functions (see AI Function Rules). Non-deterministic functions like `CURRENT_DATE` are fine only inside `WHERE`/`HAVING`/`QUALIFY`. When in doubt, this Step 6 check is the backstop.

**⚠️ MANDATORY**: If any AI-function DT is not INCREMENTAL, stop and fix it. The cost difference is significant — FULL refresh on 1,000 files at 5-minute lag = ~288 AI calls/day per file vs 1 call per file with INCREMENTAL.

---

### Step 7: Configure Target Lag [WAIT]

- **Intermediate DTs**: Always `TARGET_LAG = DOWNSTREAM`
- **Final DT** (the last in the chain): Ask user for freshness requirement

> **⚠️ DOWNSTREAM-only chains never self-start.** If the head of the chain (the
> first AI DT reading the File Log) is `TARGET_LAG = DOWNSTREAM` and all
> consumers below it are also `DOWNSTREAM`, nothing demands data and the chain
> never auto-populates. Either give the **terminal** DT a concrete lag (which
> pulls the whole `DOWNSTREAM` chain), or force an explicit initial refresh from
> the terminal DT down after creation. Always trigger and confirm the first
> population (Step 8a) — `INITIALIZE = ON_SCHEDULE` DTs are empty until then.

Ask: how fresh should results be after ingestion? (1 min / 5 min / 30 min / 1 hour). Total end-to-end latency = task schedule + DT target lag.

**⚠️ MANDATORY STOPPING POINT**: Confirm target lag before executing.

---

### Step 8: Test with Sample Documents

1. **Upload a test file:**
   ```bash
   snow stage copy "<local_path>" @<db>.<schema>.<stage> --connection <conn>
   ```

2. **Refresh the stage directory** (so the stream picks up the new file):
   ```sql
   ALTER STAGE <db>.<schema>.<stage> REFRESH;
   ```

3. **Verify ingestion** — the task is still suspended (it goes live in Step 9), so trigger a single manual run. `EXECUTE TASK` runs a suspended task without resuming it:
   ```sql
   EXECUTE TASK <db>.<schema>.<prefix>_INGEST_TASK;
   ```

4. **Check File Log table:**
   ```sql
   SELECT * FROM <db>.<schema>.<prefix>_FILE_LOG ORDER BY INGESTED_AT DESC;
   ```

5. **Verify DT layers**, waiting for refresh between layers:
   ```sql
   SELECT name, scheduling_state, last_completed_refresh_state
   FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
   WHERE name LIKE 'DT_<prefix>%';
   ```

6. **Display results** from the final DT and ask if the extraction quality is satisfactory.

**⚠️ MANDATORY STOPPING POINT**: Confirm extraction quality before considering pipeline complete.

---

### Step 9: Go Live (Resume Ingestion)

The task stayed suspended through build, verification, and testing. Resume it now — only after Step 6 confirmed every DT is `INCREMENTAL` and Step 8 confirmed extraction quality — so scheduled ingestion never starts before the pipeline is verified safe:

```sql
ALTER TASK <db>.<schema>.<prefix>_INGEST_TASK RESUME;
```

The pipeline is now live: the task ingests new files on schedule, and the DTs process them incrementally.

---

### Step 10: Monitor

Provide monitoring queries:

```sql
-- Task execution history (ingestion layer)
SELECT name, state, scheduled_time, error_code, error_message
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
  TASK_NAME => '<prefix>_INGEST_TASK',
  SCHEDULED_TIME_RANGE_START => DATEADD('hour', -24, CURRENT_TIMESTAMP())
))
ORDER BY scheduled_time DESC
LIMIT 10;

-- DT pipeline health overview (processing layers)
-- Note: refresh_mode is not exposed here — verify it in Step 6 via SHOW DYNAMIC TABLES.
SELECT name, scheduling_state, last_completed_refresh_state,
       time_within_target_lag_ratio
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
WHERE name LIKE 'DT_<prefix>%'
ORDER BY name;

-- DT refresh errors
SELECT name, state, state_message, refresh_start_time, refresh_end_time
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
  NAME_PREFIX => '<db>.<schema>',
  ERROR_ONLY => TRUE
))
WHERE name LIKE 'DT_<prefix>%'
ORDER BY refresh_start_time DESC
LIMIT 10;

-- Pipeline throughput: files ingested vs processed
SELECT
  (SELECT COUNT(*) FROM <db>.<schema>.<prefix>_FILE_LOG) AS files_ingested,
  (SELECT COUNT(*) FROM <db>.<schema>.DT_<prefix>_EXTRACTED) AS files_extracted;
```

---

## Pricing

**⚠️ MANDATORY: Check current rates before any AI execution** — see [`../SKILL.md`](../SKILL.md) § Pricing. INCREMENTAL refresh means AI runs only on new files; cost scales with new-file volume, not total.

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| No files in File Log | Stream empty or task not resumed | Check: `SHOW TASKS LIKE '%INGEST%';` — verify state is `started`. Run `ALTER STAGE ... REFRESH;` to update directory. |
| Task runs but File Log empty | Extension filter mismatch | Check the `WHERE` clause in the task — ensure it matches your file extensions |
| `EXECUTE TASK` inserted nothing | Stream was empty, so the run was **skipped** (`WHEN` clause), not executed | Normal when there's no new data. `TASK_HISTORY` shows `state = SKIPPED`, `error_code 0040003`. Upload a file + `ALTER STAGE ... REFRESH`, then re-run. |
| DT fails with "Failed to cast variant value None" | AI_EXTRACT returns string `"None"` instead of SQL NULL | Use `TRY_CAST` for numeric/boolean fields: `TRY_CAST(RAW_EXTRACT:response:field::STRING AS FLOAT)` |
| Parse DT shows NULL content | Unsupported file format or corrupt file | Check file extension filter, verify file opens manually |
| Extract DT has empty fields | Field descriptions too vague | Refine `responseFormat` field descriptions |
| DT stuck in SUSPENDED | Upstream DT failed | Check `DYNAMIC_TABLE_REFRESH_HISTORY()` with `ERROR_ONLY => TRUE` |
| `ALTER DYNAMIC TABLE … REFRESH` times out or chain stays uninitialized | Long AI backfill exceeds the SQL tool timeout, or the head DT has no consumer demanding data (`DOWNSTREAM`-only chain) | Poll `last_completed_refresh_state` until `SUCCEEDED` in short separate queries; give the terminal DT a concrete lag or force a refresh from the terminal DT down. Do **not** drop the DTs, switch to `INITIALIZE = ON_SCHEDULE`, or fall back to CTAS. |
| A recreated DT refreshes to "No new data" though upstream has rows | `CREATE OR REPLACE` resets the DT's incremental baseline; if the upstream table/DT has not changed since the re-create, there is no delta to process | Force a refresh of the recreated DT explicitly (`ALTER DYNAMIC TABLE … REFRESH`) and poll `last_completed_refresh_state`; it back-fills from the full upstream on that first run. Do not drop the DT or conclude it is broken. |
| DT falls back to FULL refresh | Query not eligible for incremental | Check `refresh_mode_reason` in `SHOW DYNAMIC TABLES`. Common cause: a `LATERAL` join to an AI/table function — call AI functions inline instead. (`LATERAL FLATTEN` over a materialized column is fine; just don't select its `seq`.) |
| Cortex Search returns 0 results though chunks exist | Service was created before `DT_<prefix>_CHUNKS` was populated; it indexed 0 rows and hasn't re-indexed on its lag | `SELECT COUNT(*)` the source DT; if >0, `DESCRIBE CORTEX SEARCH SERVICE` and check `source_data_num_rows`. If 0, refresh source then `CREATE OR REPLACE` the service (see `blocks/search/chunk-index.md`). |
| Router assigns the fallback class to nearly everything → downstream extractors return 0 rows | Verbose / ambiguous `AI_CLASSIFY` labels, or downstream `WHERE DOC_TYPE=` string doesn't match the emitted token | Shorten labels to distinct tokens, move definitions into `task_description`, match the filter string exactly (see `blocks/extract/classify.md`). |

---

## Stopping Points Summary

Steps 1, 2, 4-5, 6, 7, 8. Proceed only after explicit user approval (unless user granted autonomy upfront). Irreversible `DROP`s always require approval.
