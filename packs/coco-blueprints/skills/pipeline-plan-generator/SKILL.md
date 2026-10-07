---
name: pipeline-plan-generator
description: "This skill should be used when a Pipeline Planner answers file exists and the user wants to generate an implementation plan. Triggers: generate plan from answers, run plan generator, investigate sources, create implementation plan, pipeline plan generator, I have my answers file ready."
---

# Pipeline Plan Generator

## Overview

Accepts a completed Pipeline Planner answers file, investigates the user's source data in Snowflake, generates a transformation topology (DAG), and produces a self-contained implementation plan document.

**Contract:** The answers file is the sole input. This skill never asks blueprint-style questions — requirements are already collected.

## Required Skills

This skill delegates lineage and data-quality work to two sibling skills. Both must be **active in your Cortex Code session** alongside this skill:

| Skill | Used in | Purpose |
|-------|---------|----------|
| `lineage` | Steps 2h, 2i, 4e | Source provenance, trust scoring, downstream impact, change detection |
| `data-quality` | Step 4e | DMF coverage discovery on source tables |

If either skill is not loaded, the corresponding steps are skipped and the plan document will note: `"[Lineage / Data-quality] enrichment unavailable — ensure the [lineage / data-quality] skill is active in this session."`

## When to Use

- User has completed the Pipeline Planner blueprint and has an answers file
- User says "generate a plan from my answers" or "run the plan generator"
- User has a YAML file with `selected_transform_technology`, `source_seed_reference`, and `transformation_intent` populated

**When NOT to use:**
- User hasn't collected requirements yet → direct them to the Pipeline Planner blueprint first
- User wants to change their technology selection → re-run the blueprint

## Input Contract

The answers file (YAML) must contain these keys:

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `selected_transform_technology` | string | Yes | Dynamic Tables, Streams & Tasks, Snowpark, dbt Projects on Snowflake, dbt Core, dbt + Dynamic Tables, Stored Procedures |
| `source_seed_reference` | string | Yes | Table FQN, schema, database, stage, or external description |
| `transformation_intent` | string | Yes | What the pipeline should produce |
| `data_freshness_requirement` | string | Yes | Batch, Near Real-Time, Real-Time |
| `downstream_consumers` | list | Yes | Who/what consumes the output |
| `pipeline_criticality` | string | Yes | Mission-critical, Important, Exploratory |
| `pipeline_trigger_model` | string | No | How the pipeline gets triggered |
| `pipeline_constraints` | list | No | Hard constraints |
| `work_context` | string | No | Build New or Extend Existing |
| `expand_target_project` | string | No | Expansion path only |
| `expansion_technology` | string | No | Expansion path only |

## Locating the Answers File

Answer files are produced by the Pipeline Planner blueprint and stored at:

```
projects/<project_name>/answers/pipeline-planner/answers_<timestamp>.yaml
```

**Projects directory resolution** (same as blueprint-builder):
1. `--projects-dir <path>` CLI flag (highest priority)
2. `BLUEPRINT_MANAGER_PROJECTS_DIR` environment variable
3. `<cwd>/projects` (default)

**Discovery flow when user doesn't provide an explicit path:**

```bash
# Find all pipeline-planner answer files across all projects
find projects/*/answers/pipeline-planner -name "*.yaml" -type f 2>/dev/null | sort -r
```

If multiple files exist, present the list (most recent first by timestamp) and ask the user to select one. If exactly one exists, use it automatically.

The `project_name` is derived from the answer file path: `projects/<project_name>/answers/...` — extract the directory name between `projects/` and `/answers/`.

## Execution

### Step 1: Load and Validate Answers

1. Locate the answers file (user provides path, or discover via the flow above)
2. Read and parse the YAML
3. Extract `project_name` from the file path
4. Verify required keys are populated:
   - `selected_transform_technology`
   - `source_seed_reference`
   - `transformation_intent`
   - `data_freshness_requirement`
   - `downstream_consumers`
   - `pipeline_criticality`

If any required key is missing or null, tell the user which keys are needed and stop. Direct them to re-run the Pipeline Planner blueprint to collect the missing answers.

### Step 2: Source Investigation (silent)

Execute against the user's connected Snowflake account. Do NOT display intermediate results unless errors occur.

**2a. Classify source type** — SQL cascade, stop at first success:

```sql
-- Attempt 1: Table?
DESCRIBE TABLE <source_seed_reference>;
-- Success → source_type = TABLE

-- Attempt 2: Schema?
SHOW TABLES IN SCHEMA <source_seed_reference>;
-- Success → source_type = SCHEMA

-- Attempt 3: Database?
SHOW SCHEMAS IN DATABASE <source_seed_reference>;
-- Success → source_type = DATABASE

-- Attempt 4: Stage?
LIST <source_seed_reference>;
-- Success → source_type = STAGE

-- All failed → source_type = EXTERNAL (ask user for schema)
```

**2b. Resolve to concrete objects:**

| source_type | Action |
|-------------|--------|
| TABLE | Use as-is |
| SCHEMA | Enumerate tables, filter by naming pattern (include RAW/SRC/STG/INGEST/LANDING/EVENT/LOG; exclude DIM/FACT/AGG/MART/RPT/SUMMARY/ARCHIVE). Auto-select ≤5; confirm 6-20; surface top 10 for 20+ |
| DATABASE | Enumerate schemas → tables, same filtering |
| STAGE | LIST files, sample payload (try Parquet → JSON → CSV) |
| EXTERNAL | Ask user for sample payload or column list |

**2c. Cortex availability probe:**

```sql
SELECT SNOWFLAKE.CORTEX.COMPLETE('snowflake-arctic', 'ping') AS cortex_probe;
```

Record `cortex_available = true/false`.

**2d. Describe sources:**

```sql
DESCRIBE TABLE <each_resolved_source_object>;
```

Record columns, types, nullability for each table.

**2e. Enrich (if Cortex available):**

```sql
-- Semantic descriptions
SELECT SNOWFLAKE.CORTEX.AI_GENERATE_TABLE_DESC(
  '<table_fqn>',
  OBJECT_CONSTRUCT('describe_columns', TRUE, 'use_table_data', TRUE)
) AS ai_description;

-- Relationship inference (2+ tables only)
SELECT SYSTEM$CORTEX_ANALYST_FAST_GENERATION(
  ARRAY_CONSTRUCT('<table_1>', '<table_2>', ...)
) AS fastgen_result;
```

Extract `structuredSuggestions.relationships` (left_table, right_table, left_column, right_column, cardinality, join_type).

**2f. Heuristic fallback (if Cortex unavailable, 2+ tables):**

Pattern-match columns ending in `_ID`, `_KEY`, `_CODE` across tables. Shared names → inferred relationship with `inferred_by: "heuristic"`.

**2g. Error handling:**

If any DESCRIBE or enrichment step fails, surface the specific error to the user and ask whether to remove the problematic table or fix permissions. Otherwise proceed silently.

**2h. Lineage enrichment (silent — delegate to the `lineage` skill):**

For each resolved source object, delegate to the sibling `lineage` skill — invoke it **by name** through the skill system — to obtain upstream/downstream lineage, trust scoring, and usage patterns. The `lineage` skill owns all API correctness, fallback logic, and error handling.

**Do not write GET_LINEAGE SQL directly.** Invoke the `lineage` skill and let its workflows execute their own templates. (Invoke by skill name, not by relative file path — the `lineage` and `data-quality` skills install under the `data-governance` category and their on-disk location varies; name-based invocation is layout-independent.)

**Invocation 1 — Provenance & trust (per source object):**

> Invoke the `lineage` skill. Run its **data-discovery / provenance-verification** workflow for `<source_fqn>`.
> Return structured results: upstream lineage path with trust tier, freshness status, and usage status per object. Do not present results to the user — record silently.

The `lineage` skill will: consult its `snowflake-apis` reference for correct GET_LINEAGE syntax; apply its `schema-patterns` trust-tier config; execute its provenance-verification template; handle its own fallback behavior (e.g., OBJECT_DEPENDENCIES) internally; and return `object_name, object_type, trust_tier, freshness_status, usage_status, level`.

**Invocation 2 — Downstream impact (per source object):**

> Invoke the `lineage` skill. Run its **impact-analysis** workflow for `<source_fqn>`.
> Return structured results: downstream objects with risk level, object type, query frequency, and unique users. Do not present results to the user — record silently.

Returns: `dependent_object, object_type, risk_level, queries_last_7_days, unique_users_7_days, distance`.

**Invocation 3 — Recent changes (per source object):**

> Invoke the `lineage` skill. Run its **root-cause-analysis / change-detection** workflow for `<source_fqn>` (last 7 days only).
> Return structured results: changed objects with change type, timestamp, and who changed it. Do not present results to the user — record silently.

Returns: `object_name, change_type, change_time, change_detail, changed_by, hours_ago`.

**Error handling:** If any lineage invocation returns "No lineage data available" or "Insufficient privileges", skip that invocation's results gracefully and note in the plan: "Lineage enrichment partially unavailable — [specific capability] based on schema naming patterns only."

**Record per source object (from combined `lineage` skill results):**
- `upstream_origin`: deepest upstream object from provenance (or "leaf — no upstream in Snowflake")
- `upstream_depth`: number of levels to origin
- `downstream_consumer_count`: count of objects from impact analysis
- `downstream_consumers_critical`: objects with `risk_level = 'CRITICAL'` from impact analysis
- `trust_tier`: from provenance verification `trust_tier` field
- `source_query_frequency`: from impact analysis `queries_last_7_days` on the source itself
- `source_unique_users`: from impact analysis `unique_users_7_days`
- `upstream_recently_changed`: objects from change detection with `hours_ago < 168`

**2i. Ecosystem risk assessment (silent):**

Using the structured results from the `lineage` skill invocations in 2h, assess whether the planned pipeline introduces risk to the existing data ecosystem. **No additional SQL execution required** — this is pure logic applied to results already collected.

**Derive `existing_dt_count`:** count objects from Invocation 2 where `object_type = 'DYNAMIC TABLE'`.

**Risk assessment logic:**

| Condition | Risk Flag | Severity |
|-----------|-----------|----------|
| `existing_dt_count > 3` | `REFRESH_CONTENTION` | Warning |
| `source_query_frequency > 200/day` | `HIGH_TRAFFIC_SOURCE` | Info |
| `trust_tier = UNTRUSTED` | `UNTRUSTED_SOURCE` | Warning |
| `upstream_recently_changed` is non-empty | `UPSTREAM_INSTABILITY` | Info |
| `downstream_consumers_critical > 0` and (`selected_transform_technology = 'Stored Procedures'` or pipeline output FQN matches an existing source object) | `CRITICAL_CONSUMER_RISK` | Critical |

> **Why only Stored Procedures trigger CRITICAL_CONSUMER_RISK:** Dynamic Tables, Streams & Tasks, Snowpark, and dbt all write to *new* output objects — they never modify the source tables they read from. Stored Procedures are the only technology in this skill's set that routinely issues DML (TRUNCATE, INSERT INTO, DELETE FROM, MERGE INTO) against existing tables, including sources. The FQN collision condition catches the edge case where the planned output object would overwrite an existing source regardless of technology.

**Threshold rationale (heuristics — calibrate to your environment):**
- `existing_dt_count > 3`: 3+ Dynamic Tables competing for the same source is a common warehouse slot contention point; lower this for XS/S warehouses or high-concurrency accounts. Override with `ecosystem_risk_thresholds.dt_count` in the answers file.
- `source_query_frequency > 200/day` (~8+ queries/hour): flags sources where adding a new consumer may introduce read contention or latency sensitivity. Adjust for your account's query baseline. Override with `ecosystem_risk_thresholds.query_frequency` in the answers file.

**Record:**
- `existing_dt_count`: Dynamic Tables already consuming this source
- `risk_flags`: list of triggered risk indicators with severity

### Step 3: Generate Topology (silent)

Generate a minimal DAG appropriate for the selected technology:

| Technology | Node type | Refresh mechanism |
|-----------|-----------|-------------------|
| Dynamic Tables | Dynamic Table | TARGET_LAG |
| Streams & Tasks | Task | Stream trigger or CRON |
| Snowpark | DataFrame step | Python orchestration |
| dbt | dbt model | staging → intermediate → mart |
| Stored Procedures | Procedure | Orchestration chain |

For each node, record:
- `name`: fully-qualified object name
- `object_type`: dynamic_table / stream / task / snowpark_procedure / dbt_model / stored_procedure
- `purpose`: one-sentence description
- `depends_on`: upstream object names
- `sql_body`: complete, executable SQL using real column names from DESCRIBE
- Technology-specific config: `target_lag`, `schedule`, `after`, `stream_trigger`, `file_path`

**Design principle:** Node count is determined entirely by the business requirements. Use as many nodes as needed — no more, no fewer. Simple pipelines may need one or two; complex ones may need many. Never cap the topology to fit a heuristic.

Write `topology_nodes` back to the answers file as structured YAML.

### Step 4: Generate Test Plan (silent)

Use `pipeline_criticality` from the answers file to determine test scope. Combine with column metadata from Step 2 to produce concrete, executable test SQL.

**4a. Test category selection (criticality tier is a starting default, not a prescription):**

The table below is a **default starting point** keyed off `pipeline_criticality` — it is not exhaustive or exclusionary. Choose the actual check set from the pipeline's context (transformation intent, downstream consumers, source characteristics, relationships inferred in Step 2e/2f, and `pipeline_constraints`), drawing on the **full Snowflake data-quality arsenal**. Delegate that selection to the `data-quality` skill, which knows the complete set of system DMFs (DUPLICATE_COUNT, UNIQUE_COUNT, FRESHNESS, SCHEMA_CHANGE_COUNT, ACCEPTED_VALUES, ROW_COUNT, BLANK_COUNT, statistics, etc.) and custom DMF patterns (e.g., a `referential_check` DMF spanning two tables). Any check can apply at any tier when context warrants — for example, referential integrity is essential whenever a foreign-key relationship was inferred, regardless of tier.

| Category | Default: Mission-critical | Default: Important | Default: Exploratory |
|----------|:---:|:---:|:---:|
| Primary key uniqueness | Yes | Yes | Yes |
| Non-null constraints (key columns) | Yes | Yes | Yes |
| Data completeness (expected time window present) | Yes | Yes | — |
| Row count stability (day-over-day variance) | Yes | Yes | — |
| Referential integrity | Yes | When FK inferred | When FK inferred |
| Statistical stability (distribution drift) | Yes | Context-dependent | — |
| Enum validity & conditional column gating | Yes | Context-dependent | — |
| Downstream compatibility | Yes | When critical consumers exist | — |
| Monitoring alerts (severity + recovery) | Yes | Basic | — |
| Retention & housekeeping validation | Yes | Yes | — |

Treat "—" as "not in the default set," not "forbidden" — include the check anyway when context indicates it matters.

**4b. For each applicable category, generate:**

- **Test name**: descriptive, prefixed with category (e.g., `pk_uniqueness__orders_daily`)
- **Test SQL**: from `data-quality` skill delegation — DMF attachment DDL when a built-in metric covers the check, or a SQL assertion returned by the `data-quality` skill when no built-in DMF applies
- **Severity**: `critical` (blocks deploy), `warning` (alerts but doesn't block), `info` (logged only)
- **Schedule**: how often to run (aligned with pipeline refresh cadence)
- **Recovery action**: what to do when the test fails (Mission-critical only)

**4c. Delegate test generation to the `data-quality` skill:**

For each applicable test category (from 4a), **invoke the `data-quality` skill** (invoke by name) with the output object FQN and the category name. The `data-quality` skill owns all test output — DMF attachment DDL where a built-in metric applies, SQL assertions where it doesn't, and deduplication against existing DMF coverage.

> Invoke the `data-quality` skill. For `<output_fqn>`, run its **test-generation** workflow for category: `<category_name>` (e.g., "primary key uniqueness", "non-null constraints", "row count stability").
> Return the test output: DMF attachment DDL + schedule, or SQL assertion, as appropriate.
> Record results silently.

For each category, record in the test plan:
- The test name, severity, and schedule
- What `data-quality` returned (DMF DDL or SQL assertion)
- Recovery action (Mission-critical only)

**4d. Monitoring alerts (Mission-critical and Important):**

| Tier | Alert triggers | Severity | Recovery |
|------|---------------|----------|----------|
| Mission-critical | Expected time window missing (no rows for current period), row count drop >30%, PK violation, null in required column, referential integrity failure | Critical | Documented per-alert (re-run, page oncall, pause downstream) |
| Important | Expected time window missing, row count drop >50% | Warning | Re-run pipeline; escalate if persists |

**4e. Lineage-informed tests (generated from Step 2h/2i signals):**

For each triggered category, **invoke the `data-quality` skill** (invoke by name) with the source FQN and the lineage context. The `data-quality` skill owns all test output for these categories too.

| Category | When Generated | Trigger Condition | Context to pass to `data-quality` |
|----------|---------------|-------------------|------------------------------------|
| Source freshness gate | Always (if source has upstream) | Source is not a leaf table | FQN + `"freshness check; data_freshness_requirement = <value>"` |
| Upstream schema stability | Mission-critical, Important | `upstream_recently_changed` non-empty | FQN + `"schema drift; upstream object <upstream_obj> recently altered"` |
| Downstream compatibility | Mission-critical | `downstream_consumers_critical > 0` | FQN + `"output contract; critical consumer = <consumer>, planned output = <output_fqn>"` |
| Refresh contention guard | When tech = Dynamic Tables | `existing_dt_count > 0` | FQN + `"DT refresh concurrency; existing_dt_count = <N>"` |
| Existing DMF reuse check | Always | Every source | FQN + `"preflight DMF coverage check"` |

> Invoke the `data-quality` skill. For `<source_fqn>` with context: `<context from table above>`.
> Return the test output: DMF attachment DDL + schedule, or SQL assertion, as appropriate.
> Record results silently — do not present to user.

For the **Existing DMF reuse check**, separately run the `data-quality` skill's **monitor-recommendations / preflight-check** workflow to discover DMFs already attached to the source. If existing DMFs overlap with tests being generated, note the duplication in the test plan — the `data-quality` skill handles this deduplication.

Write `test_plan` back to the answers file as structured YAML.

### Step 5: Present Plan (user-facing)

Display to the user:

1. **ASCII DAG** — box-drawing characters (NOT mermaid). Example style:
```
┌─────────────────┐    ┌─────────────────┐
│  source_table_1 │    │  source_table_2 │
└────────┬────────┘    └────────┬────────┘
         └──────────┬───────────┘
                    ▼
         ┌──────────────────┐
         │  stg_enriched    │
         └────────┬─────────┘
                  ▼
         ┌──────────────────┐
         │  final_output    │
         └──────────────────┘
```

2. **Node Walkthrough** — table: # | Name | Type | Operation | Why Separate
3. **Output Dataset** — name, grain, columns, satisfies intent
4. **Test & Monitoring Plan** — summary table: test name, category, severity, schedule
5. **Configuration Context** — technology, freshness, trigger, consumers, criticality tier
6. **Source Ecosystem Profile** — per source: trust tier, upstream origin, downstream consumer count, risk flags, existing DMF coverage
7. **Pre-Build Risk Assessment** — risk flags from Step 2i with mitigations

### Step 6: Approve Plan (user-facing)

Ask: **"Do you approve this transformation plan?"**

| Option | Action |
|--------|--------|
| Approved | Proceed to save |
| Adjust Intent | Re-ask intent, regenerate topology (loop to Step 3) |
| Add Source | Collect new source, re-investigate (loop to Step 2) |
| Change Node | Ask which node + what change, regenerate (loop to Step 3) |

Loop until "Approved".

### Step 7: Save Plan

Use `project_name` extracted in Step 1 and the original `answer_file_path` for all paths below.

**7a. Render SQL artifact:**

```bash
mkdir -p projects/<project_name>/output/iac/sql
.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/render_journey.py \
  projects/<project_name>/answers/pipeline-planner/<answers_file>.yaml \
  --blueprint pipeline-planner \
  --lang sql \
  --project <project_name>
```

**7b. Write plan document** to `projects/<project_name>/output/plans/<intent-slug>-plan.md`

Required sections:

1. **Executive Summary** — intent, technology choice, source → output, SQL artifact path
2. **Pipeline Topology** — ASCII DAG diagram
3. **Source Data Profile** — per table: FQN, columns, relationships, row estimates

   **3b. Source Ecosystem Profile** — per source object:
   - Trust tier and score (from schema pattern matching)
   - Upstream origin (deepest ancestor or "leaf")
   - Downstream consumers (count, with CRITICAL-tier objects named)
   - Access frequency (queries/day, unique users/week)
   - Existing DMF coverage (which metrics are already monitored)
   - Risk flags (from Step 2i assessment)

   **3c. Pre-Build Risk Assessment** — summary table of risk flags (flag + severity, affected object, mitigation recommendation, and whether the generated test plan addresses it). Example:

   | Risk Flag | Severity | Object | Mitigation | Test Coverage |
   |-----------|----------|--------|------------|---------------|
   | REFRESH_CONTENTION | Warning | RAW.ORDERS | Use dedicated warehouse for new DT | refresh_contention_guard test |
   | UPSTREAM_INSTABILITY | Info | RAW.INGEST.PRODUCTS | Schema drift test added | upstream_schema_stability test |
   | HIGH_TRAFFIC_SOURCE | Info | RAW.ORDERS | Consider clone for development | — (informational) |

4. **Node Specifications** — per node: purpose, input, output, transform logic, implementation SQL, dependencies, configuration
5. **Output Dataset Definition** — final table, grain, columns, consumers
6. **Test & Monitoring Plan** — per test: name, category, SQL, severity, schedule, recovery action (tier-appropriate)
7. **Implementation Sequence** — ordered DDL with prerequisites and validation queries
8. **Configuration Context** — technology, freshness, trigger, consumers, constraints, criticality tier
9. **Assumptions & Open Questions** — what to verify before executing

**Writing rules:**
- Use actual table/column names from investigation (never placeholders)
- SQL must be concrete and immediately executable
- Technical specification, not tutorial
- Target 200-600 lines depending on complexity and criticality tier

**7c. Confirm to user:**
- SQL artifact: `projects/<name>/output/iac/sql/<file>.sql`
- Plan document: `projects/<name>/output/plans/<intent-slug>-plan.md`

## Cross-Skill References

Read `references/cross-skill-delegation.md` for the full delegation table, pattern, key contract, and rationale for why delegation is used rather than embedding SQL directly.

## Additional Resources

### Reference Files

Load when needed during plan generation:

- **`references/cross-skill-delegation.md`** — Delegation table, pattern, key contract, and rationale for `lineage` and `data-quality` skill invocation

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Using mermaid for DAG diagrams | Use ASCII box-drawing characters — mermaid doesn't render in terminal |
| Placeholder SQL (`<your_warehouse>`) | Use real names from investigation; note assumptions in Section 8 |
| Generating topology without DESCRIBE data | Always complete investigation first — topology needs real column names |
| Skipping Cortex probe | Always probe — determines enrichment path (AI vs heuristic) |
| Presenting raw DESCRIBE output | Investigation is silent; only surface errors |
| Writing GET_LINEAGE, DMF, or other lineage/DQ SQL directly in this skill | Delegate to the `lineage` and `data-quality` skills — they own SQL syntax, argument forms (positional or named), output columns, and fallback behavior. This skill never hardcodes or validates their API details |
| Generating duplicate tests when DMFs already cover the metric | Delegate to `data-quality` skill for all test generation — it handles DMF discovery and deduplication |
| Treating the Step 4a tier matrix as exhaustive | It is a starting default — select the actual check set from context and the full DQ arsenal |
