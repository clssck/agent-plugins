---
name: data-quality
description: "Monitor, analyze, and enforce data quality using Snowflake DMFs. Schema-level and per-table DMF attachment, health scoring, incident investigation, circuit breakers, table comparison, dataset popularity, ad-hoc assessment, prompt quality scoring, and per-group monitoring via WITHIN GROUP clause."
---

# Data Quality

Monitor, analyze, and enforce data quality across Snowflake schemas using Data Metric Functions (DMFs). Compare tables for migration validation, regression testing, and data reconciliation. Analyze dataset popularity and usage patterns to prioritize governance.

## When to Use

Activate this skill when the user mentions any of:

- **Health/trust keywords**: "schema health", "data quality score", "can I trust my data", "quality check"
- **DMF keywords**: "data metric function", "DMF", "DMF results", "metrics failing"
- **Issue investigation**: "why is this table failing", "what's wrong with my data", "root cause", "quality issues"
- **Change detection**: "quality regression", "what changed", "what broke", "did quality get worse"
- **Trend keywords**: "quality trends", "is quality improving", "quality over time"
- **Alerting keywords**: "quality alerts", "SLA monitoring", "alert me on quality drops", "enforce DQ SLAs"
- **Table comparison keywords**: "compare tables", "data diff", "table diff", "validate migration", "dev vs prod data", "find differences", "data reconciliation"
- **Popularity/usage keywords**: "popular tables", "most used tables", "least used", "unused tables", "stale data", "dataset usage", "table popularity", "who uses this table", "is this table used"
- **Ad-hoc / no-DMF keywords**: "check data quality without DMFs", "one-time quality check", "quick quality scan", "assess columns", "check for nulls", "check freshness", "check completeness"
- **Listing quality keywords**: "listing quality", "listing health", "listing freshness", "provider data quality", "consumer data quality", "data product quality", "check my listing"
- **Accepted values / categorical keywords**: "accepted values", "ACCEPTED_VALUES", "value in set", "allowed values", "validate column values", "categorical validation", "column must be in list"
- **Referential integrity keywords**: "referential integrity", "REFERENTIAL_INTEGRITY_COUNT", "orphaned rows", "foreign key check", "FK validation", "cross-table integrity check", "orphan rows"
- **Schema-level DMF keywords**: "add DMF to schema", "monitor whole schema", "schema-level DMF", "ALTER SCHEMA ADD DATA METRIC FUNCTION", "bulk attach DMF", "schema anomaly detection", "monitor all tables", "schema monitoring", "schema data quality"
- **Pipeline-context keywords**: "recommend monitors based on my pipeline", "use lineage dependencies to pick DMFs", "which dependency is most critical to monitor", "monitor my source/ingestion tables", "prioritize monitoring for high blast-radius tables", "recommend quality for my data pipeline", "monitor by upstream/downstream criticality"
- **Prompt quality keywords**: "score my prompt", "prompt quality", "prompt linter", "improve my prompt", "rewrite prompt", "prompt engineering", "prompt score"
- **Prompt comparison keywords**: "compare prompts", "prompt regression", "before and after prompt", "prompt iteration"
- **Prompt execution keywords**: "execute prompt", "run both prompts", "test my prompt"
- **Within group / grouped DMF keywords**: "within group", "group by DMF", "per-group metrics", "grouped monitoring", "GROUP LIMIT", "broken down by", "separately for each", "metrics per group"

**Do NOT use** for: non-quality-related schema operations or data access control.

**Cross-skill:** After identifying quality issues (e.g. NULLs, failing DMFs, wrong values), proactively use the **lineage** skill to trace upstream and find where the bad data originated—do not wait for the user to ask. This gives a complete root-cause answer (what is wrong + where it came from).

## Workflow Decision Tree

```
User request
  |
  v
Step 0: Check intent BEFORE preflight
  |
  ├── "recommend monitors" / "what should I monitor" / "set up DMFs" /
  |   "attach DMFs for the first time" / "which DMFs should I add" /
  |   "recommend monitors based on my pipeline / lineage" /
  |   "use lineage dependencies to pick DMFs" /
  |   "which dependency is most critical to monitor" /
  |   "monitor my source/ingestion tables" /
  |   "prioritize monitoring for high blast-radius tables" /
  |   "recommend quality for my data pipeline"
  |         └──> Load workflows/monitor-recommendations.md
  |              (DMF-first: profiles columns AND upstream/downstream lineage,
  |               ranks by pipeline position + blast radius, generates DDL)
  |
  ├── "coverage gaps" / "unmonitored tables" / "monitoring health" /
  |   "what % of tables are monitored" / "noisy monitors" / "silent monitors" /
  |   "DMF cost" / "monitoring coverage report"
  |         └──> Load workflows/coverage-gaps.md
  |
  ├── "investigate DQ incident" / "why did freshness drop" / "why did row count drop" /
  |   "correlate violation" / "DQ incident root cause" / "why did my pipeline fail quality"
  |         └──> Load workflows/dq-incident-investigation.md
  |              (orchestrates: DMF violations → lineage skill → data-governance skill)
  |
  ├── "circuit breaker" / "pause pipeline on violation" / "halt bad data" /
  |   "stop downstream when quality fails"
  |         └──> Load workflows/circuit-breaker.md
  |
  ├── "accepted values" / "ACCEPTED_VALUES" / "value in set" / "allowed values" /
  |   "categorical validation" / "validate column values"
  |         └──> Load workflows/custom-dmf-patterns.md
  |              (Step 1: Prefer ACCEPTED_VALUES; escalate to custom DMF only when needed)
  |
  ├── "add DMF to schema" / "schema-level DMF" / "monitor whole schema" /
  |   "ALTER SCHEMA ADD DATA METRIC FUNCTION" / "bulk attach DMF" /
  |   "schema anomaly detection" / "monitor all tables in schema"
  |         └──> Load workflows/monitor-recommendations.md
  |              (Step 1b: Schema-level fast path for ROW_COUNT + FRESHNESS)
  |
  ├── "referential integrity" / "REFERENTIAL_INTEGRITY_COUNT" / "orphaned rows" /
  |   "FK check" / "foreign key validation" / "cross-table integrity"
  |         └──> Load workflows/monitor-recommendations.md
  |              (Prefer system DMF REFERENTIAL_INTEGRITY_COUNT over custom DMF)
  |
  ├── "within group" / "group by" / "per-group metrics" / "grouped monitoring" /
  |   "monitor by region" / "monitor by category" / "null count per" /
  |   "duplicates by" / "GROUP LIMIT" / "quality by segment" /
  |   "broken down by" / "separately for each" / "per region" / "per category" /
  |   "for each <column> separately" / "which <groups> have the worst" /
  |   "metrics per" / "quality per" / "track <metric> for each <group>"
  |         └──> Load workflows/within-group-dmf.md
  |              (Per-group DMF metrics via WITHIN GROUP clause.
  |               IMPORTANT: If the user wants a DMF metric computed separately
  |               for each value of a column — e.g. "nulls per region",
  |               "quality broken down by category", "which departments have
  |               the worst data" — this is a WITHIN GROUP use case.
  |               Do NOT create dynamic tables, manual GROUP BY queries,
  |               or separate DMF associations per group value.)
  |
  ├── "custom DMF" / "format validation" / "email format check" / "value range check" /
  |   "cross-column validation DMF"
  |         └──> Load workflows/custom-dmf-patterns.md
  |
  ├── "DMF expectations" / "set threshold" / "tune DMF threshold" /
  |   "review expectations" / "expectation management"
  |         └──> Load workflows/expectations-management.md
  |
  ├── Listing quality / ad-hoc check / "without DMFs" / "one-time check"
  |         └──> Load workflows/adhoc-assessment.md
  |              (no DMFs required; works for listings too)
  |
  ├── "score my prompt" / "prompt quality" / "prompt linter" / "prompt score"
  |         └──> Load workflows/prompt-quality.md
  |              (Score via Cortex Complete — no DMFs, no schema needed)
  |
  ├── "improve prompt" / "rewrite prompt" / "prompt engineering" /
  |   "make my prompt better"
  |         └──> Load workflows/prompt-improve.md
  |              (Score + rewrite via Cortex + re-score + before/after)
  |
  ├── "compare prompts" / "prompt regression" / "execute both prompts" /
  |   "test my prompt" / "run both prompts"
  |         └──> Load workflows/prompt-execute-compare.md
  |              (Execute original + improved via Cortex Complete, compare outputs)
  |
  └── None of the above — proceed to Step 1 preflight check
        |
        v
    Step 1 preflight: total_dmfs_attached = 0?
        |
        ├── YES — offer 3 options to user:
        |     1. Set up DMFs (continuous monitoring) ──> Load workflows/monitor-recommendations.md
        |     2. Run ad-hoc one-time assessment ──────> Load workflows/adhoc-assessment.md
        |     3. None / skip
        |
        └── NO (DMFs present) — Step 2: Identify intent
              |
              ├── Health/trust/score ----------> Load workflows/health-scoring.md
              |
              ├── Failures/root cause ---------> Load workflows/root-cause-analysis.md
              |
              ├── Regression/what changed -----> Load workflows/regression-detection.md
              |
              ├── Trends/over time ------------> Load workflows/trend-analysis.md
              |
              ├── Alerts/SLA/notify -----------> Load workflows/sla-alerting.md
              |
              ├── Compare tables/diff/migrate -> Load workflows/compare-tables.md
              |                                    (has its own sub-workflows)
              |
              └── Popularity/usage/unused -----> Load workflows/popularity.md
```

## Critical: Correct Snowflake View/Function Locations

Before executing any query, be aware of the correct data sources:

| Data | Correct Location | Notes |
|---|---|---|
| DMF metric results (values) | `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS()` | **Table function**, not a view. Takes `REF_ENTITY_NAME` and `REF_ENTITY_DOMAIN` params. |
| **Expectation pass/fail status** | `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_EXPECTATION_STATUS` | **View or table function.** Use this for "which expectations are passing/failing" and for violation counts. Has `expectation_violated`, `value`, `expectation_expression`, `measurement_time`. Do not derive pass/fail by joining RESULTS + DATA_METRIC_FUNCTION_EXPECTATIONS. |
| DMF references (config) | `INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES()` | **Table function** per-table or per-schema. Use `REF_ENTITY_DOMAIN => 'table'` for table-level; use `REF_ENTITY_DOMAIN => 'schema'` to see schema-level associations (lowercase enum values). Includes new columns: `LEVEL` (`'TABLE'` or `'SCHEMA'`, uppercase) and `EXCLUDE_TABLE_TYPES`. Also available as `SNOWFLAKE.ACCOUNT_USAGE.DATA_METRIC_FUNCTION_REFERENCES` view (same new columns). |
| DMF expectations (config only) | `SNOWFLAKE.ACCOUNT_USAGE.DATA_METRIC_FUNCTION_EXPECTATIONS` | View with expectation definitions (name, expression). For **status** (pass/fail) use DATA_QUALITY_MONITORING_EXPECTATION_STATUS instead. |
| DMF credit/usage | `SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_USAGE_HISTORY` | View for cost tracking, NOT metric values |

**`SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_RESULTS` does NOT exist.** Never query it. Always use `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS()`.

**Investigate / RCA — trust stored measurements (SNOW-3777068):** When reporting a DMF or expectation violation count, always use `VALUE` from `DATA_QUALITY_MONITORING_RESULTS()` and/or `value` + `expectation_violated` from `DATA_QUALITY_MONITORING_EXPECTATION_STATUS`. Never replace that number with a self-computed recount or a `LIMIT`-capped preview size. For custom DMFs (`METRIC_DATABASE` ≠ `SNOWFLAKE`), fetch the body with `GET_DDL('FUNCTION', …)` before explaining or sampling — do not paraphrase the predicate. See `workflows/root-cause-analysis.md` Steps 2b–2d and `templates/reproduce-dmf-violation.sql`.

**Schema-level DMF associations:** When ROW_COUNT or FRESHNESS is added at the schema level via `ALTER SCHEMA ... ADD DATA METRIC FUNCTION`, Snowflake automatically creates object-level associations for all supported table-like objects in the schema (unless excluded). To check which DMFs were added at the schema level, call `INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES()` with `REF_ENTITY_DOMAIN => 'schema'`. Individual object-level references created via schema-level association show `LEVEL = 'SCHEMA'` in the `DATA_METRIC_FUNCTION_REFERENCES` view/function. Use `EXCLUDE_TABLE_TYPES` to see which object types were excluded.

**Correct column names for `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS()`:**
`MEASUREMENT_TIME`, `TABLE_NAME`, `TABLE_SCHEMA`, `TABLE_DATABASE`, `METRIC_NAME`, `METRIC_SCHEMA`, `METRIC_DATABASE`, `VALUE`, `REFERENCE_ID`, `ARGUMENT_NAMES`, `ARGUMENT_TYPES`, `ARGUMENT_IDS`

**Grouped DMF (WITHIN GROUP) results:** When a DMF is attached with `WITHIN GROUP`, `DATA_QUALITY_MONITORING_RESULTS()` includes a `GROUP_BY_INFO` column (VARIANT) containing per-group column IDs and values. `SYSTEM$EVALUATE_DATA_QUALITY_EXPECTATIONS` returns one row per (expectation, group_value) combination with a `GROUP_BY_VALUES` column. Use `SYSTEM$DATA_METRIC_SCAN` with `WITHIN_GROUP_VALUES` parameter to filter results by specific group value.

**Correct column names for `ACCOUNT_USAGE.DATA_METRIC_FUNCTION_REFERENCES`:**
`REF_DATABASE_NAME`, `REF_SCHEMA_NAME`, `REF_ENTITY_NAME`, `REF_ENTITY_DOMAIN`, `METRIC_NAME`, `SCHEDULE`, `SCHEDULE_STATUS`, `LEVEL` (new: `TABLE` or `SCHEMA`), `EXCLUDE_TABLE_TYPES` (new: list of excluded object types for schema-level associations)

## Workflow

### Step 0: Preflight Check (REQUIRED for DMF workflows)

**Goal:** Validate the environment before running any DMF-based workflow. Skip for: compare-tables, popularity, adhoc-assessment, monitor-recommendations, coverage-gaps, circuit-breaker, custom-dmf-patterns, and expectations-management workflows (each of those handles its own setup validation internally).

**Actions:**

1. Extract `DATABASE.SCHEMA` from the user's message. If only a schema name is provided, ask which database it belongs to.
2. Read and execute `templates/preflight-check.sql` with placeholders replaced.
3. Evaluate results:
   - **table_count = 0** → Stop. "Schema is empty or doesn't exist."
   - **total_dmfs_attached = 0** → DMFs are not configured. **Do not stop.** Instead, ask the user:

     > "I didn't find any Data Metric Functions (DMFs) attached to the tables in `<DATABASE>.<SCHEMA>`.
     > DMFs enable continuous, scheduled quality monitoring. How would you like to proceed?
     >
     > **1. Set up DMFs for continuous monitoring** — I'll analyze your tables and recommend the right DMFs to attach. You'll get trend history, regression detection, and SLA alerts.
     >
     > **2. Run a one-time ad-hoc assessment** — I'll check your data quality right now using inline Snowflake system functions, with no setup required. Works for any table, schema, or Marketplace listing.
     >
     > **3. Skip for now** — Continue without a quality check."

     - If user chooses **1**: Load `workflows/monitor-recommendations.md` and proceed.
     - If user chooses **2**: Load `workflows/adhoc-assessment.md` and proceed with the ad-hoc flow.
     - If user chooses **3**: Stop gracefully.

   - **readiness_status = 'NO_RESULTS'** → Stop. "DMFs haven't run yet. Wait 1-2 minutes and retry."
   - **readiness_status = 'LIMITED'** → Proceed, but warn that regression/trend queries may not work.
   - **readiness_status = 'READY'** → Proceed to Step 1.

### Step 1: Route to Workflow

**Goal:** Determine which workflow matches the user's intent and load it.

| User Intent | Workflow to Load |
|---|---|
| Health check, trust, quality score | **Load** `workflows/health-scoring.md` |
| Why failing, what's wrong, root cause (DMF-based) | **Load** `workflows/root-cause-analysis.md` |
| DQ incident investigation, correlate violation, why did freshness/volume drop | **Load** `workflows/dq-incident-investigation.md` |
| What changed, regression, what broke | **Load** `workflows/regression-detection.md` |
| Quality trends, improving, over time | **Load** `workflows/trend-analysis.md` |
| Set up alerts, SLA, notify on drops | **Load** `workflows/sla-alerting.md` |
| Compare tables, data diff, validate migration, dev vs prod | **Load** `workflows/compare-tables.md` |
| Popular tables, most/least used, unused data, who uses this | **Load** `workflows/popularity.md` |
| Ad-hoc check, no DMFs, one-time, listing quality | **Load** `workflows/adhoc-assessment.md` |
| Recommend monitors, set up DMFs, which DMFs to attach, monitor by pipeline/upstream/downstream criticality, monitor source/ingestion or high blast-radius tables | **Load** `workflows/monitor-recommendations.md` |
| Coverage gaps, unmonitored tables, noisy/silent monitors, DMF cost | **Load** `workflows/coverage-gaps.md` |
| Circuit breaker, pause pipeline on violation | **Load** `workflows/circuit-breaker.md` |
| Referential integrity, orphaned rows, FK validation, cross-table integrity | **Load** `workflows/monitor-recommendations.md` (use REFERENTIAL_INTEGRITY_COUNT system DMF) |
| Schema-level DMF: add/modify/suspend ROW_COUNT or FRESHNESS on a schema, check schema-level associations | **Load** `workflows/monitor-recommendations.md` (Step 1b: schema-level fast path) |
| Within group / grouped DMF: per-group metrics, broken down by, monitor by region/category, GROUP LIMIT | **Load** `workflows/within-group-dmf.md` |
| Custom DMF, format validation, value range, cross-column validation | **Load** `workflows/custom-dmf-patterns.md` |
| Accepted values, value in set, categorical validation, allowed values | **Load** `workflows/custom-dmf-patterns.md` (Step 1: ACCEPTED_VALUES first) |
| DMF expectations, set threshold, tune threshold | **Load** `workflows/expectations-management.md` |
| Score prompt, prompt quality, prompt linter | **Load** `workflows/prompt-quality.md` |
| Improve prompt, rewrite prompt, prompt engineering | **Load** `workflows/prompt-improve.md` |
| Execute prompts, compare outputs, test prompt, prompt regression | **Load** `workflows/prompt-execute-compare.md` |

If the intent is ambiguous, ask the user which workflow they want.

### Step 2: Execute Template from Workflow

**Goal:** Run the SQL template specified by the loaded workflow.

**Actions:**

1. Read the SQL template specified in the workflow file (from `templates/` directory)
2. Replace all placeholders:
   - `<database>` with the actual database name
   - `<schema>` with the actual schema name
3. Execute using `snowflake_sql_execute`
4. If the primary template fails, try the fallback template specified in the workflow

**Note:** The compare-tables and popularity workflows have their own step-by-step execution flows — follow the loaded workflow directly when those routes are selected.

**Error handling:**
- If template fails and fallback also fails: run `templates/preflight-check.sql` to diagnose
- If no DMFs found: inform user that DMFs need to be attached first
- If no data yet: inform user that DMFs haven't run — wait 1-2 minutes
- Maximum 2 fallback attempts before reporting the error to the user

### Step 3: Present Results

**Goal:** Format and present results per the workflow's output guidelines.

Follow the output format specified in the loaded workflow file. Suggest logical next steps (e.g., root cause analysis after health check).

## Tools

### snowflake_sql_execute

**Description:** Executes SQL queries against the user's Snowflake account.

**When to use:** All template executions — health checks, root cause analysis, regression detection, trend analysis, and alert creation.

**Usage pattern:**
1. Read the appropriate SQL template from `templates/`
2. Replace `<database>` and `<schema>` placeholders with actual values
3. Execute the resulting SQL via `snowflake_sql_execute`

**Templates available (DMF workflows):**

| Template | Purpose | Type |
|---|---|---|
| `preflight-check.sql` | Validate environment before any workflow | Read |
| `check-dmf-status.sql` | Verify DMF setup per table | Read |
| `check-dq-monitoring-enabled.sql` | Check DMF result availability | Read |
| `schema-health-snapshot-realtime.sql` | Current health (primary) | Read |
| `schema-health-snapshot.sql` | Current health (fallback) | Read |
| `schema-root-cause-realtime.sql` | Current failures (primary); includes METRIC_DATABASE for SYSTEM vs CUSTOM | Read |
| `schema-root-cause.sql` | Current failures (fallback) | Read |
| `reproduce-dmf-violation.sql` | Trust stored VALUE / EXPECTATION_STATUS; custom GET_DDL; optional labeled examples | Read |
| `schema-regression-detection.sql` | Compare runs over time | Read |
| `schema-quality-trends.sql` | Time-series analysis | Read |
| `schema-sla-alert.sql` | Create automated alert | **Write** |
| `adhoc-column-quality.sql` | SNOWFLAKE.CORE.* inline DMF patterns for ad-hoc assessment | Read |
| `monitor-recommendations.sql` | Profile columns + rank DMF recommendations by criticality | Read |
| `pipeline-context.sql` | Upstream + downstream lineage (GET_LINEAGE) per table; drives pipeline-aware DMF prioritization | Read |
| `coverage-gaps-summary.sql` | Coverage % + critical unmonitored tables | Read |
| `monitor-effectiveness.sql` | Noisy/silent monitor analysis (uses DATA_QUALITY_MONITORING_EXPECTATION_STATUS) | Read |
| `circuit-breaker-setup.sql` | Create ALERT + TASK suspension; trigger uses DATA_QUALITY_MONITORING_EXPECTATION_STATUS + expectation_violated | **Write** |
| `custom-dmf-create.sql` | Custom DMF templates for format/range/FK validation | **Write** |
| `expectations-review.sql` | Review DMF expectations and pass/fail status (uses DATA_QUALITY_MONITORING_EXPECTATION_STATUS) | Read |
| `prompt-cortex-complete.sql` | Score, rewrite, or execute a prompt via Cortex Complete | Read + LLM credits |

All DMF monitoring templates use `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS()` for raw metric values — never `SNOWFLAKE.ACCOUNT_USAGE`. For **expectation pass/fail** and **violation counts**, use `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_EXPECTATION_STATUS` (view or table function); the templates `expectations-review.sql`, `monitor-effectiveness.sql`, and `circuit-breaker-setup.sql` use it.
The `adhoc-column-quality.sql` template uses `SNOWFLAKE.CORE.*` functions called inline and requires no pre-attached DMFs.

For compare-tables tools (`data_diff` CLI, SQL templates), see `workflows/compare-tables.md`.

## Stopping Points

- ✋ **Before SLA alert creation**: The `sla-alerting` workflow creates Snowflake ALERT objects and a log table — present the full configuration and get explicit user approval before executing any CREATE statements
- ✋ **Before materializing diff results**: The compare-tables workflow can write diff results to a new table — confirm table name and location with user first
- ✋ **After health check with failures**: Present results and ask if user wants root cause analysis (do not auto-chain workflows)
- ✋ **When DMFs are absent (Step 0)**: Present the three-option menu (DMF recommendations / ad-hoc assessment / skip) — do not auto-select on behalf of the user
- ✋ **Before executing DMF recommendations DDL**: `monitor-recommendations` must show the ranked DDL plan and await explicit approval
- ✋ **Before creating custom DMFs**: `custom-dmf-patterns` must show generated DDL and await approval
- ✋ **Before activating circuit breaker**: `circuit-breaker` must present the ALERT + task modification plan and get explicit approval
- ✋ **Before rewriting a prompt**: Present detected quality gaps and confirm user wants Cortex to rewrite (costs LLM credits, may alter intent)
- ✋ **Before executing both prompts**: Confirm user wants to run original + improved prompts through Cortex Complete (costs LLM credits)

**Resume rule:** Upon user approval, proceed directly to the next step without re-asking.

## Cross-Skill Delegation Rules

Data quality investigation often requires capabilities owned by other skills. **Never re-implement what other skills already do.** Delegate explicitly:

| Capability Needed | Delegate To | How |
|---|---|---|
| Upstream lineage tracing | `lineage` skill | Say "Loading lineage skill for upstream root cause" → load `lineage/workflows/root-cause-analysis.md` |
| DDL change detection on upstream tables | `lineage` skill | Say "Checking upstream change history" → load `lineage` and use `change-detection.sql` |
| QUERY_HISTORY analysis for failed queries | `data-governance` skill | Say "Loading data-governance skill for query history" → load `data-governance/workflows/horizon-catalog.md` |
| TASK_HISTORY for failed task runs | `data-governance` skill | Same delegation as above |
| Data masking policy after quality finding | `data-governance` skill | Load `data-governance/workflows/data-policy.md` |
| PII detection after quality profiling | `data-governance` skill | Load `data-governance/workflows/sensitive-data-classification.md` |

## Output

Each workflow produces structured output:

- **Health Scoring**: Overall health percentage, passing/failing metric counts, tables monitored
- **Root Cause Analysis**: Failing metrics by table/column, issue descriptions, fix recommendations
- **DQ Incident Investigation**: Multi-dimensional root-cause report with timeline, primary cause, contributing factors, remediation steps
- **Regression Detection**: Health delta (previous vs current), new failures, resolved issues
- **Trend Analysis**: Time-series health scores, persistent vs transient issues, trend direction
- **SLA Alerting**: Alert configuration summary, activation status, monitoring instructions
- **Compare Tables**: Row counts, added/removed/modified rows, schema differences, validation report (see `workflows/compare-tables.md` for details)
- **Dataset Popularity**: Popularity-ranked tables, unused/stale object list, storage cost estimates, usage trends, top consumers
- **Monitor Recommendations**: Pipeline context (upstream/downstream position + blast radius from lineage), ranked DMF recommendations by criticality, column-type mappings, deployment DDL
- **Coverage Gaps**: Coverage % by schema, critical unmonitored tables, noisy/silent monitor list, cost optimization suggestions
- **Circuit Breaker**: Circuit breaker configuration, ALERT DDL, resume workflow
- **Custom DMF Patterns**: Generated `CREATE DATA METRIC FUNCTION` DDL for format/range/FK checks
- **Expectations Management**: Current expectation inventory with pass/fail status, threshold tuning suggestions
- **Prompt Quality**: Overall 1-10 score, 9 dimension scores with detail, strengths vs gaps, improvement suggestions
- **Prompt Improve**: Before vs after scores, per-dimension delta table, improved prompt text
- **Prompt Execute Compare**: Side-by-side LLM outputs for original vs improved prompt

## Error Handling

| Error | Action |
|---|---|
| Primary template fails | Try fallback template from the same workflow |
| Fallback also fails | Run `preflight-check.sql` to diagnose environment |
| No DMFs found | Present 3-option menu: continuous monitoring setup / ad-hoc one-time assessment / skip |
| No data available | Inform user: "DMFs haven't run yet. Wait 1-2 minutes and retry." |
| Insufficient history | Inform user: "Need at least 2 measurements for comparison." |
| SQL compilation error | Report the error clearly — do not hide failures or fabricate results |
| `ACCOUNT_USAGE.DATA_QUALITY_MONITORING_RESULTS` referenced | This view does NOT exist. Use `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS()` instead |

## Reference

For detailed DMF concepts, **Load** `reference/dmf-concepts.md` when the user asks about DMF setup, concepts, or best practices.

For detailed prompt scoring dimensions (sub-criteria, scoring rules), **Load** `reference/prompt-scoring-dimensions.md` when the user asks about how prompt dimensions are scored.
