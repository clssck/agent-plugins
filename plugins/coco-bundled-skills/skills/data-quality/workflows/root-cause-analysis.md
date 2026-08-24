---
parent_skill: data-quality
---

# Workflow 2: Root Cause Analysis

## Trigger Phrases
- "Why is this table failing?"
- "What's wrong with [TABLE]?"
- "Show me the failures"
- "What are the quality issues?"
- "Root cause analysis"

## When to Load
Data-quality Step 2: failure/investigation intent.

## Template to Use
**Primary:** `schema-root-cause-realtime.sql`
- Shows immediate failures with details via dynamic table discovery
- Use for troubleshooting

**Fallback (if real-time fails):** `schema-root-cause.sql`
- Also uses `SNOWFLAKE.LOCAL` but with a different query structure
- Use when the primary template has issues

**Explain / sample (optional):** `reproduce-dmf-violation.sql`
- After listing failures: trust stored VALUE; custom DMF → GET_DDL; optional labeled examples
- Never use a LIMIT preview size as the violation count

## Execution Steps

### Step 0: Preflight Check
- Run `templates/preflight-check.sql` first (as specified in SKILL.md Step 0)
- If preflight fails, stop and report the issue
- If preflight passes, proceed to Step 1

### Step 1: Extract Database and Schema
- From user query: "DEMO_DQ_DB.SALES" → database='DEMO_DQ_DB', schema='SALES'
- If not already provided, ask which DATABASE.SCHEMA to investigate

### Step 2: Execute Template
- Read: `templates/schema-root-cause-realtime.sql`
- This template dynamically discovers tables via `INFORMATION_SCHEMA.TABLES` — no hardcoded table names
- Uses `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS()` table function (correct column: `VALUE`, not `metric_value`)
- Returns `METRIC_DATABASE` / `METRIC_SCHEMA` so you can tell SYSTEM vs CUSTOM DMFs
- Column-level info is in `ARGUMENT_NAMES` array (not a `column_name` column)
- Replace: `<database>` → actual database name, `<schema>` → actual schema name
- Execute via `snowflake_sql_execute`

### Step 2b: Expectation status (when expectations exist)

If the user mentioned an expectation / dashboard incident, or you need pass/fail vs a threshold, also query **`SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_EXPECTATION_STATUS`** (see `templates/expectations-review.sql` or section B of `templates/reproduce-dmf-violation.sql`).

Use:
- `expectation_violated` for pass/fail
- `value` as the measured metric value (same authority as RESULTS `VALUE` when both exist)
- `expectation_expression` for the threshold text

Do **not** invent pass/fail by re-joining RESULTS to expectation config when this view is available.

If `DATA_QUALITY_MONITORING_EXPECTATION_STATUS` returns no rows for the metric, continue with `VALUE` from `DATA_QUALITY_MONITORING_RESULTS()` as the authoritative count. Do not treat an empty EXPECTATION_STATUS result as an indicator that the metric is passing — empty can mean the expectation was deleted or the violation predates expectation tracking.

### Step 2c: Trust the stored measurement — never silently recompute

**Authoritative violation count** = `VALUE` / `failure_count` from RESULTS (and/or EXPECTATION_STATUS `value`).

| Do | Do not |
|----|--------|
| Report that number as the violation count | Replace it with a self-computed `COUNT(*)` or a `LIMIT` result size |
| Label optional samples as examples of N total | Say "there are 20 unpopular videos" because `LIMIT 20` returned 20 rows |
| Always report the **stored VALUE** as authoritative. If a recomputed count differs, surface both numbers and note that the stored measurement is the canonical violation count for this run. Do not substitute the recomputed value. | Override the stored measurement with the recomputed number |

### Step 2d: System vs custom DMF

From RESULTS, check `METRIC_DATABASE` (also exposed as `dmf_type` in the realtime template):

**SYSTEM** (`METRIC_DATABASE = 'SNOWFLAKE'`): explain using known system DMF semantics (NULL_COUNT, FRESHNESS, …). Prefer `SYSTEM$DATA_METRIC_SCAN` for example rows when supported.

**CUSTOM** (`METRIC_DATABASE` is not `SNOWFLAKE`):
1. Fetch the exact body: `SELECT GET_DDL('FUNCTION', '<METRIC_DATABASE>.<METRIC_SCHEMA>.<METRIC_NAME>')`
2. Explain using that body (or `SYSTEM$EVALUATE_DATA_QUALITY_EXPECTATIONS`) — **never paraphrase** the predicate from the DMF name/description
3. Optional examples: apply the **verbatim** predicate from GET_DDL with a **small** `LIMIT` (e.g. 5), labeled as examples — or skip examples entirely

Follow `templates/reproduce-dmf-violation.sql` for the SQL shape. Before substituting placeholders, validate each identifier (`^[A-Za-z_][A-Za-z0-9_$]*$`) and require `<fq_metric_name>` to be exactly `db.schema.metric` — prefer values copied from RESULTS / EXPECTATION_STATUS columns, never raw free-form user text.

If any identifier fails validation, **stop the GET_DDL call entirely** and surface to the user: "Cannot safely fetch custom DMF body — the metric identifier `<raw_value>` contains characters that are not safe for SQL injection. Raw stored value from RESULTS: `<METRIC_DATABASE>.<METRIC_SCHEMA>.<METRIC_NAME>`. Please confirm the DMF name is a standard Snowflake identifier."

### Step 3: Present Results
```
Root Cause Analysis: DATABASE.SCHEMA

Top Issues Found:

1. TABLE_NAME — Metric: METRIC_DATABASE.METRIC_SCHEMA.METRIC_NAME (SYSTEM|CUSTOM)
   Violation count (from DMF measurement): <VALUE>
   Expectation (if any): <expression> — VIOLATED|PASS
   Issue: <short description; for CUSTOM, grounded in GET_DDL body>
   Example rows (optional): showing K of <VALUE> — not the total
   Recommendation: ...
```

### Step 4: Next Steps

**Always proactively suggest lineage investigation for any failing table** — this is the most valuable follow-up when quality issues are detected. Data quality RCA tells you *what* is failing; lineage RCA tells you *why* and *where in the pipeline* the bad data originated.

After presenting the results, immediately surface the lineage next step without waiting for the user to ask:

> "I found quality issues in **[list failing tables]**. To understand *why* this is happening, I can trace the upstream data lineage to find where the bad data entered the pipeline. I'll do that now."

Then load the lineage skill and run its root cause analysis workflow:
- Load skill: `data-governance/lineage` → workflow: `root-cause-analysis`
- Pass the failing table(s) as the starting point — the user should not have to re-enter them
- Frame the transition as: "These tables have quality issues — tracing upstream to find the source of the bad data"

**Only pause and use `ask_user_question`** if:
- The user has already said they don't want lineage tracing in this session, OR
- There are more than 10 failing tables (ask which ones to prioritize)

**After lineage investigation**, offer:

| Option | Description |
|--------|-------------|
| **Fix the quality issues** | Address the DMF failures directly (add constraints, fix nulls, deduplicate). |
| **Set up alerts so I'm notified next time** | Load the `sla-alerting` workflow to create monitors for these metrics. |

## Output Format
- Table name and column name (if applicable)
- Metric FQN + SYSTEM vs CUSTOM
- **Violation count from measurement** (stored VALUE) — required
- Expectation status/expression when applicable
- Specific issue description (custom rules from GET_DDL)
- Optional labeled example rows
- Actionable recommendation for each failure

## What to Show
- Top 5-10 failing metrics (prioritize by severity)
- Column-level details when available
- Specific **measurement** values (e.g., "502 unpopular videos per DMF measurement")
- Clear fix recommendations
- Never present a sample/`LIMIT` size as if it were the total

## Error Handling
- If real-time template fails → Try fallback template (`schema-root-cause.sql`)
- If both fail → Run `preflight-check.sql` to diagnose
- If no failures found → "All metrics passing! No issues detected."
- If GET_DDL fails for a custom DMF → Still report stored VALUE; note that the rule body could not be fetched; do not invent a predicate

## Notes
- This is a READ-ONLY workflow (no approval required)
- Digs deeper than health-scoring — shows specific violations, not just counts
- Provides actionable recommendations per failure
- Separate workflow from health scoring (do not auto-chain)
- QUERY_HISTORY / TASK_HISTORY `LIMIT` clauses in related workflows sample **history**, not DMF totals

## Halting States
- **Success**: Failures listed with measurement counts and recommendations
- **No failures**: "All metrics passing. No issues detected."
- **No DMFs**: Inform user that monitoring needs to be set up first
