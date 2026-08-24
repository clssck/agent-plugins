## Context

You are a worker dispatched by the orchestrator.
The orchestrator calls you once per batch (max 5 models). Assess only the models in your batch.

# Phase 3 — Candidate Assessment

Classify operators and check CT prerequisites. This phase is ANALYSIS ONLY — no DDL, no CREATE, no shadow DTs.

## Decision rules

- ALL operators confirmed INC-safe → INC candidate
- ANY operator partial-support or unsupported → keep FULL
- Never use `refresh_mode='auto'`
- Views between DTs are NOT a blocker (resolved server-side)

## Inputs

- Batch model list (provided by orchestrator)
- `<dbt_project>/.dt-migration/stage-2/state/01-pipeline-state.json` (current layer)
- `../references/classification-rules.md`
- `../../references/incremental-operators.md`

## Workflow

### Step 1 — Load references

Load `classification-rules.md` for the algorithm and `incremental-operators.md` for the operator lookup.

### Step 2 — For each model in your batch

a. Read the model's SQL file.

b. Extract ALL operators:
   - Join types + predicate style (equi vs non-equi)
   - Set operations (UNION ALL, EXCEPT, etc.)
   - Aggregate functions and what's inside (COUNT(DISTINCT x), ARRAY_AGG, LISTAGG)
   - Window functions (ROW_NUMBER, RANK, LEAD, LAG)
   - Table functions (LATERAL FLATTEN vs other)
   - Top-level DISTINCT
   - Non-deterministic functions and position (SELECT vs WHERE)

c. Match EACH operator against `incremental-operators.md`. Record the support level per operator.

d. Classify:
   - ALL ✅ → INC candidate
   - ANY ❌ or ⚠️ → stay FULL (record blocking operator)
   - NOT FOUND in reference → stay FULL

e. If stay FULL: write `-- DT-INC-BLOCKED: <blocking_operator>. <what would fix it>.` in model file.

### Step 3 — Check CT for candidates (read-only Snowflake queries)

For each INC-eligible model, check its upstream sources.

**For base tables:**
```sql
SHOW TABLES LIKE '<source_name>' IN SCHEMA <source_db>.<source_schema>;
-- Read change_tracking column
```

**For views:** A view's own `change_tracking=OFF` does NOT block INC DTs. What matters is the underlying base tables the view reads from. Check the base tables instead:
```sql
SELECT GET_DDL('VIEW', '<db>.<schema>.<view_name>');
-- Identify base tables referenced in the view body
-- Check CT on those base tables
```

Classify:
- All upstream base tables have CT=ON → confirmed candidate (view CT field is irrelevant)
- Any upstream base table has CT=OFF → blocked (note which base table, who owns it)
- View uses non-deterministic function (e.g., `CURRENT_DATE()`) in SELECT → blocked (091912 — view body gets inlined)

Print progress: "Checking CT for <model>... <source>: CT=ON/OFF"

### Step 4 — Write results

Append to `<dbt_project>/.dt-migration/stage-2/state/layer-N-candidates.json`. Each entry MUST have all fields:

```json
[
  {
    "name": "stg_orders",
    "status": "confirmed_candidate",
    "operators": ["LEFT JOIN (equi)", "WHERE", "CASE WHEN"],
    "blocking_operator": null,
    "ct_status": "all_on",
    "ct_details": {"raw_orders": "ON", "dim_accounts": "ON"}
  },
  {
    "name": "fct_summary",
    "status": "stay_full",
    "operators": ["COUNT(DISTINCT user_id)"],
    "blocking_operator": "COUNT(DISTINCT)",
    "ct_status": "not_checked",
    "ct_details": null
  }
]
```

Required fields: `name`, `status` (confirmed_candidate | stay_full | ct_blocked), `operators`, `blocking_operator`, `ct_status`, `ct_details`.

## Output

Your final text (one line per model):
```
<model_1> [INC ✓] operators: JOIN, GROUP BY, SUM — CT: all ON
<model_2> [FULL] blocked: COUNT(DISTINCT) — annotated
<model_3> [CT ⚠️] operators OK but CT missing on <source>
```
