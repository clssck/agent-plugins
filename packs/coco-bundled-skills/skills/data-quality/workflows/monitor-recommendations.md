---
parent_skill: data-quality
---

# Workflow: Monitor Recommendations

AI-driven DMF monitor recommendations based on column types, data patterns, downstream criticality, and access frequency. Ranks tables by priority and generates deployment DDL. The primary path for onboarding a schema to continuous DMF monitoring.

**Closes gaps:** G2, MA-01 (AI Monitor Recommendations), MA-02 (Column-Level Pattern Detection), MA-03 (Auto-Threshold guidance), MA-04 (Coverage Gap Analysis), MA-05 (One-Click Deployment).

## Trigger Phrases
- "Recommend monitors for my schema"
- "What should I monitor?"
- "Which DMFs should I attach?"
- "Set up DMFs for continuous monitoring"
- "Improve my DQ coverage"
- "What monitors am I missing?"
- "DQ gaps"
- "Which tables need monitoring?"
- "Help me attach DMFs"
- "Add DMF to schema"
- "Monitor whole schema"
- "Schema-level DMF"
- "ALTER SCHEMA ADD DATA METRIC FUNCTION"
- "Bulk attach DMF"
- "Enable anomaly detection for my schema"
- "Monitor all tables in my schema at once"
- "Recommend monitors based on my pipeline / lineage"
- "Use lineage dependencies to pick DMFs"
- "Which dependency are most critical to monitor?"
- "Monitor my source/ingestion tables"
- "Prioritize monitoring for high blast-radius tables"
- "Recommend quality for my data pipeline?"

## When to Load
- User has a schema with no or partial DMF coverage and wants recommendations
- User chose option 1 ("Set up DMFs") from the Step 0 preflight menu
- User explicitly wants guidance on which DMFs to attach
- User wants to use schema-level DMF association (ROW_COUNT or FRESHNESS on all objects in a schema at once)

**Scope recommendations to critical assets:** Prioritize DMFs on contract surfaces (gold/shared tables, data products), business keys and identifiers used in joins, high-risk fields (PII, financial), and SLA-sensitive pipelines (FRESHNESS + ROW_COUNT). Avoid recommending heavy DMFs on every transient staging table by default.

---

## Execution Steps

### Step 1: Establish Scope

Extract target scope from user message:
- **Preferred**: `DATABASE.SCHEMA`
- **Acceptable**: database only (will profile all schemas)
- **Acceptable**: `DATABASE.SCHEMA.TABLE` (single table recommendations)

If not provided, ask:
> "Which schema would you like me to analyze for DMF recommendations? Please provide `DATABASE.SCHEMA`."

---

### Step 1b: Check Available System DMFs

Before profiling, discover which system DMFs are available in this deployment:

```sql
SHOW DATA METRIC FUNCTIONS IN SNOWFLAKE.CORE;
```

Capture the list of available DMF names from the `name` column. In Step 4, **only recommend DMFs that appear in this list**. Some newer DMFs (e.g., `UNTRIMMED_STRING_COUNT`, `FUTURE_TIMESTAMP_COUNT`, `STRING_LENGTH_*`, `ZERO_COUNT`, `NEGATIVE_COUNT`, `INVALID_JSON_COUNT`, `INVALID_NUMERIC_TYPE_CAST_COUNT`, `SPECIAL_CHARACTER_COUNT`, `CASE_FORMAT_VIOLATION_COUNT`, `VARIANCE`, `MEDIAN`, `APPROX_QUANTILE_*`) may not be available in all deployments.

---

### Step 1c: Schema-Level Fast Path (ROW_COUNT + FRESHNESS)

**When to use:** User explicitly asks for schema-level DMF attachment, mentions `ALTER SCHEMA ADD DATA METRIC FUNCTION`, wants to monitor all tables at once, or asks about anomaly detection at the schema level.

This is a GA feature (Enterprise Edition+) that covers volume and freshness monitoring for all objects in a schema with a **single SQL statement**. It is the fastest path to baseline coverage.

**Ask the user:**
> "Snowflake now supports attaching ROW_COUNT and FRESHNESS DMFs at the schema level — one statement covers all tables and views automatically. I can also enable **anomaly detection** to have Snowflake learn your data patterns and flag unusual spikes or drops.
>
> A few quick questions:
> 1. Which DMF(s) would you like? (ROW_COUNT / FRESHNESS / both)
> 2. Enable anomaly detection? (recommended — Snowflake trains on historical patterns per object)
> 3. Any object types to exclude? e.g. DYNAMIC_TABLE, EVENT_TABLE, EXTERNAL_TABLE, ICEBERG_TABLE, MATERIALIZED_VIEW, VIEW — leave blank to monitor everything"

Then read and execute `templates/schema-level-dmf.sql` with the user's choices substituted.

**Access control requirements** (check before executing — warn user if likely missing):
- `OWNERSHIP` on the schema
- `MANAGE DATA QUALITY` privilege on the account
- `EXECUTE DATA METRIC FUNCTION` privilege on the account
- `SNOWFLAKE.DATA_METRIC_USER` database role

**⚠️ MANDATORY STOPPING POINT**: Present the exact DDL and get explicit approval before executing any `ALTER SCHEMA` statement.

After executing, **STOP** — do NOT continue to per-table Steps 2–6. The schema-level operation is complete. Briefly confirm success and offer next steps:
> "Schema-level DMFs are attached — one statement covered all tables. Next steps if needed:
> - Column-level checks (NULLs, duplicates, accepted values) require per-table DMFs — ask me if you want those too.
> - To confirm associations: `DATA_METRIC_FUNCTION_REFERENCES` with `REF_ENTITY_DOMAIN => 'schema'`.
> - To override settings for one table: `ALTER TABLE ... MODIFY DATA METRIC FUNCTION`."

**⚠️ Do NOT proceed to Step 2 (per-table analysis) unless the user explicitly asks for column-level DMFs.** The entire point of schema-level DMF is that it replaces per-table ROW_COUNT/FRESHNESS attachment. Never generate per-table `ALTER TABLE ADD DATA METRIC FUNCTION ROW_COUNT/FRESHNESS` statements after a successful schema-level attachment — that would be redundant and defeat the purpose.

---

### Step 2: Profile Existing Coverage and Column Types

Read and execute `templates/monitor-recommendations.sql` with `<database>` and `<schema>` replaced.

This query produces a combined profile per table+column:
- Column name, data type, nullability
- Whether a DMF is already attached for that column
- Table access frequency (queries in last 90 days from ACCESS_HISTORY)

Review the results to build a mental model of:
- Which tables have **zero** DMFs (highest priority)
- Which tables have **partial** coverage (missing key columns)
- Column types present: timestamps/dates, VARCHAR IDs, numeric amounts, email-like strings

---

### Step 3: Assess Pipeline Context (Upstream + Downstream)

For the top 10 highest-access tables with zero or partial DMF coverage, gather **both upstream and downstream** dependency signals plus table metadata. Read and execute `templates/pipeline-context.sql` once per candidate table, replacing `<database>`, `<schema>`, and `<table>`.

This uses `SNOWFLAKE.CORE.GET_LINEAGE` (object + data-movement lineage; no account admin) in both directions and returns, per table:

- `upstream_count` / `direct_upstream_count` — what the table is built from (its feeders). `upstream_count = 0` => the table is a **SOURCE / ingestion** point.
- `downstream_count` / `direct_downstream_count` — what depends on the table (its **blast radius**). High values => failures propagate widely.
- `pipeline_position` — `SOURCE`, `INTERMEDIATE`, `SINK`, or `ISOLATED`.
- `high_blast_radius` — TRUE when `downstream_count >= 5`.

> This step relies on `GET_LINEAGE` only. It deliberately does **not** query `ACCOUNT_USAGE.TABLES` for row-count/last-altered metadata: ACCOUNT_USAGE views can take several minutes to return on large accounts, and pipeline position + blast radius do not need them.

**Why both directions matter:**
- **Upstream** tells you where bad data *originates* and whether duplicates/nulls can be introduced by joins or CTAS (intermediate tables).
- **Downstream** tells you the *blast radius* — how many objects break if this table's quality slips.

> **Complementary signal (future enhancement):** lineage is not the only way to derive quality rules. Profiling the *existing data* (e.g. a column that is non-NULL in nearly all rows is a good candidate for a NULL-fraction expectation) can suggest rules directly, which is especially useful in migration scenarios. This is not yet wired into this workflow and is tracked as a follow-up.

**Fallback:** If `GET_LINEAGE` errors or returns no rows but the table should have dependencies, use the `OBJECT_DEPENDENCIES` fallback block at the bottom of `templates/pipeline-context.sql` (schema-wide upstream + downstream counts in one query; requires `IMPORTED PRIVILEGES` on `SNOWFLAKE`). If both are unavailable, skip this step and note that criticality is based on access frequency only.

---

### Step 4: Generate Ranked Recommendations

Using the column profile from Step 2 and criticality from Step 3, generate recommendations using this column-type mapping:

| Column Characteristic | Recommended DMF(s) | Rationale |
|---|---|---|
| Timestamp / DATE column | `SNOWFLAKE.CORE.FRESHNESS` + `SNOWFLAKE.CORE.FUTURE_TIMESTAMP_COUNT` | Detect stale data + future-dated records |
| `*_ID` / primary key column | `SNOWFLAKE.CORE.DUPLICATE_COUNT` + `SNOWFLAKE.CORE.UNIQUE_COUNT` | Detect PK violations |
| FK column (references another table) | `SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT` with `TABLE(ref_table(ref_col))` | Detect orphaned rows; replaces custom FK DMFs |
| Nullable VARCHAR (non-ID) | `SNOWFLAKE.CORE.NULL_COUNT` + `SNOWFLAKE.CORE.BLANK_COUNT` + `SNOWFLAKE.CORE.UNTRIMMED_STRING_COUNT` | Detect missing/empty/whitespace-padded values |
| VARCHAR (identifiers, codes) | `SNOWFLAKE.CORE.STRING_LENGTH_MIN` + `SNOWFLAKE.CORE.STRING_LENGTH_MAX` | Detect truncation or unexpected length changes |
| VARCHAR with known valid values (status, category, enum-like) | `SNOWFLAKE.CORE.ACCEPTED_VALUES` with lambda (e.g., `col -> col IN (...)`) | Detect invalid categorical values without a custom DMF |
| VARCHAR with JSON-like data | `SNOWFLAKE.CORE.INVALID_JSON_COUNT` | Detect malformed JSON in payload/config columns |
| VARCHAR with numeric-as-text data | `SNOWFLAKE.CORE.INVALID_NUMERIC_TYPE_CAST_COUNT` | Detect non-numeric values in columns expected to contain numbers |
| Numeric (amount, price, count) | `SNOWFLAKE.CORE.NULL_COUNT` + `SNOWFLAKE.CORE.ZERO_COUNT` + `SNOWFLAKE.CORE.NEGATIVE_COUNT` | Detect missing, zero, and negative values |
| Table level (all tables) | `SNOWFLAKE.CORE.ROW_COUNT` | Detect unexpected volume changes |
| VARCHAR with special characters | `SNOWFLAKE.CORE.SPECIAL_CHARACTER_COUNT` | Detect special characters in names, codes, or identifiers |
| VARCHAR with inconsistent casing | `SNOWFLAKE.CORE.CASE_FORMAT_VIOLATION_COUNT` | Detect mixed-case violations in columns expected to be uniform (e.g., status codes) |
| VARCHAR with email-like values | `SNOWFLAKE.CORE.ACCEPTED_VALUES` (e.g., `email -> email LIKE '%@%.%'`) or custom email format DMF | Detect format issues; use ACCEPTED_VALUES for simple patterns, custom DMF for strict regex |

> **Important:** Only recommend DMFs confirmed available in Step 1b. If a DMF does not appear in `SHOW DATA METRIC FUNCTIONS IN SNOWFLAKE.CORE`, omit it from recommendations.

#### Pipeline-signal layer (apply Step 3 results on top of the column-type mapping)

The column-type mapping above decides *which* DMFs are candidates. The pipeline signals from Step 3 then **add table/edge-level metrics** and **re-weight** the column-type candidates by the table's position in the pipeline:

| Pipeline signal (from Step 3) | Action | Rationale |
|---|---|---|
| `pipeline_position = 'SOURCE'` (no upstream / ingestion) | Prioritize `SNOWFLAKE.CORE.FRESHNESS` + `SNOWFLAKE.CORE.ROW_COUNT` (table level) | Entry points fail first on staleness/volume; there is no upstream to catch it earlier |
| `high_blast_radius = TRUE` (`downstream_count >= 5`) | Escalate the table to **CRITICAL**; always add `SNOWFLAKE.CORE.ROW_COUNT` + `SNOWFLAKE.CORE.FRESHNESS` | A quality slip here propagates to every dependent object |
| `upstream_count > 0` (INTERMEDIATE — built via join/CTAS) **and** an ID/grain column exists | Escalate `SNOWFLAKE.CORE.DUPLICATE_COUNT` / `SNOWFLAKE.CORE.UNIQUE_COUNT` on the grain column | Fan-out joins silently introduce duplicate keys in transformation outputs; a raw source with a naturally-unique key ranks lower |
| `high_blast_radius = TRUE` **and** a join/FK key column exists | Escalate `SNOWFLAKE.CORE.NULL_COUNT` on the join/FK key(s) | Nulls in join keys silently drop rows in every downstream object; NULL_COUNT on a leaf table's free-text column stays lower priority |
| Direct upstream table in the same schema referenced by an FK column | Recommend `SNOWFLAKE.CORE.REFERENTIAL_INTEGRITY_COUNT` with `TABLE(ref_table(ref_col))` on the FK edge | Catch orphaned rows at the dependency boundary using the system DMF |

> The pipeline layer never *removes* column-type recommendations — it only adds table/edge metrics and bumps priority. NULL_COUNT and DUPLICATE_COUNT still come from the column-type mapping; pipeline position decides how urgently to deploy them.

> **On the heuristics above:** the pipeline-signal actions and the priority tiers below are data-quality-skill heuristics curated by the team — they are practical defaults, not a hard Snowflake-defined standard. Treat the thresholds (e.g. `downstream_count >= 5`, top-20% access) as tunable starting points.

**Priority tiers (now factor in upstream + downstream, not just downstream):**
- **CRITICAL**: Zero coverage AND (`high_blast_radius = TRUE` (≥5 downstream) OR top 20% access frequency)
- **HIGH**: Zero coverage AND (<5 downstream) OR partial coverage on critical columns OR `pipeline_position = 'SOURCE'` missing FRESHNESS/ROW_COUNT OR `pipeline_position = 'INTERMEDIATE'` missing uniqueness on a grain column
- **MEDIUM**: Coverage present but missing timestamp/freshness checks OR missing uniqueness on ID columns
- **LOW**: Well-covered tables, or `ISOLATED`/`SINK` tables with no dependents, with optional additional checks

Present the ranked table:

```
## DMF Recommendations: <DATABASE.SCHEMA>

### Coverage Summary
- Tables in schema: X
- Tables with ≥1 DMF: Y (Z%)
- Columns with DMF coverage: N

### Recommendations by Priority

#### 🔴 CRITICAL (deploy immediately)
1. TABLE_NAME — 0 DMFs, 12 downstream objects, 450 queries/week
   - Add: FRESHNESS on (updated_at)
   - Add: DUPLICATE_COUNT on (customer_id)
   - Add: ROW_COUNT (table level)

#### 🟡 HIGH
2. TABLE_NAME2 — 1 DMF, partially covered
   ...

#### 🟢 MEDIUM
3. TABLE_NAME3 — missing freshness check
   ...
```

---

### Step 5: Generate Deployment DDL

After presenting the ranked recommendations, generate the complete DDL:

```sql
-- Deployment DDL for <DATABASE.SCHEMA>
-- Generated by Monitor Recommendations workflow

-- Set schedule for schema (run every hour, or on changes)
ALTER SCHEMA <database>.<schema>
  SET DATA_METRIC_SCHEDULE = 'TRIGGER_ON_CHANGES';

-- CRITICAL: <TABLE_NAME>
ALTER TABLE <database>.<schema>.<TABLE_NAME>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.FRESHNESS ON (<timestamp_column>),
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.DUPLICATE_COUNT ON (<id_column>),
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.ROW_COUNT ON ();

-- HIGH: <TABLE_NAME2>
ALTER TABLE <database>.<schema>.<TABLE_NAME2>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.NULL_COUNT ON (<nullable_column>),
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.BLANK_COUNT ON (<varchar_column>);
```

**⚠️ MANDATORY STOPPING POINT**: Present the full DDL plan and ask:

> "I've generated the DMF deployment plan above. This will attach **X monitors** to **Y tables** in `<DATABASE.SCHEMA>`.
>
> **Estimated cost:** Approximately X DMF executions per hour (serverless compute, billed per execution).
>
> Shall I execute this? (Yes / No / Modify — e.g., 'skip TABLE_X' or 'only deploy CRITICAL tier')"

**NEVER execute the DDL without explicit user confirmation.**

---

### Step 6: Execute (On Approval)

Execute each `ALTER TABLE` statement in priority order (CRITICAL first).

After execution:
> "DMFs attached. The first measurements will appear within 1–2 minutes (for `TRIGGER_ON_CHANGES`) or on the next scheduled run.
>
> Next steps:
> - Run a **health check** to see the first results: 'Show me the schema health for `<DATABASE.SCHEMA>`'
> - Set **SLA alerts** to be notified when quality drops: 'Set up quality alerts for `<DATABASE.SCHEMA>`'
> - Set **expectation thresholds** to define pass/fail criteria: 'Set DMF expectations for `<DATABASE.SCHEMA>`'"

---

### Step 7 (Optional): Custom DMF Recommendations

If columns with email, phone, UUID, or custom business-rule patterns are detected, offer:

> "I noticed columns that may benefit from **custom format validation DMFs** (e.g., email format, value ranges). Would you like me to create those too?"

If yes → Load `workflows/custom-dmf-patterns.md`.

---

## Output Format
- Coverage summary (tables total, monitored %, columns covered)
- Pipeline context per top table: position (SOURCE/INTERMEDIATE/SINK), upstream count, downstream blast radius
- Ranked recommendation table by priority tier (priority reflects pipeline position + blast radius)
- Column-type-to-DMF mapping rationale, plus pipeline-signal rationale (why a metric was escalated)
- Complete deployment DDL (ready to execute)
- Post-deployment next steps

## Stopping Points
- ✋ **Step 1**: Scope not provided — ask for DATABASE.SCHEMA
- ✋ **Step 1b**: Schema-level fast path — present the exact `ALTER SCHEMA` DDL and await explicit approval before execution
- ✋ **Step 5**: Before executing per-table DDL — show full plan and await explicit approval

## Error Handling
| Issue | Resolution |
|-------|-----------|
| `GET_LINEAGE` returns no rows / errors (Step 3) | Use the `OBJECT_DEPENDENCIES` fallback block in `templates/pipeline-context.sql` (schema-wide upstream + downstream counts) |
| `OBJECT_DEPENDENCIES` also unavailable | Skip pipeline-context criticality, base priority on access frequency only |
| ACCESS_HISTORY unavailable | Skip access frequency; base priority on column types, pipeline position, and table row counts |
| DMF already attached | Skip that column/metric combination in recommendations |
| Schema has no tables | "Schema is empty or doesn't exist. Verify the database and schema names." |
| ALTER TABLE fails (permissions) | Report which privilege is missing: `CREATE DATA METRIC FUNCTION` or `ATTACH DATA METRIC FUNCTION PRIVILEGE` |
| ALTER SCHEMA fails (permissions) | Schema-level DMF requires: OWNERSHIP on the schema, MANAGE DATA QUALITY on the account, EXECUTE DATA METRIC FUNCTION on the account, and SNOWFLAKE.DATA_METRIC_USER database role |
| FRESHNESS skips views/external tables | Expected behavior: FRESHNESS requires a column argument for views and external tables, so Snowflake automatically skips them in schema-level associations |

## Notes
- This workflow is **DMF-first by design** — it always recommends DMF setup, never ad-hoc assessment
- **Step 3 (pipeline context)** uses `SNOWFLAKE.CORE.GET_LINEAGE` in both directions (upstream + downstream) plus table metadata; it is the primary signal for prioritizing which DMFs to deploy, layered on top of column-type detection
- The pipeline-signal layer does not replace column-type DMFs — it adds table/edge metrics (FRESHNESS, ROW_COUNT, REFERENTIAL_INTEGRITY_COUNT) and escalates NULL_COUNT/DUPLICATE_COUNT based on pipeline position and blast radius
- **Schema-level fast path (Step 1b)** covers ROW_COUNT and FRESHNESS only — column-level DMFs (NULL_COUNT, DUPLICATE_COUNT, etc.) still require per-table `ALTER TABLE` statements
- FRESHNESS at the schema level automatically skips views and external tables (they require a column argument)
- For custom pattern validation DMFs, see `workflows/custom-dmf-patterns.md`
- For setting pass/fail thresholds on the attached DMFs, see `workflows/expectations-management.md`
- To check existing schema-level associations, use `DATA_METRIC_FUNCTION_REFERENCES` with `REF_ENTITY_DOMAIN => 'schema'`; the `LEVEL` and `EXCLUDE_TABLE_TYPES` columns identify schema-level vs table-level associations
