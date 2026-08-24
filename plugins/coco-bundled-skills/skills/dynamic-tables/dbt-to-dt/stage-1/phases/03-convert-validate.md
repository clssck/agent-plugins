## Context

You are a worker dispatched by the orchestrator. You receive a context pack with inputs.
The orchestrator calls you once per batch — convert and validate only the models listed in your batch.

# Phase 3 — Convert + Validate

## CRITICAL: Process ONE model at a time

Do NOT convert all models first then validate. For each model in your batch, complete the FULL cycle before moving to the next:

```
FOR each model in batch:
  1. Convert the file
  2. dbt compile — verify Jinja renders correctly
  3. Validate (sample → baseline → DT → compare)
  4. Record PASS or revert + record FAIL
  THEN move to next model
```

## Inputs

- Batch model list (provided by orchestrator in the spawn prompt)
- `<dbt_project>/.dt-migration/stage-1/state/01-inventory.json` (full model list + refs — for parent lookup)
- `<dbt_project>/.dt-migration/stage-1/state/02-conversion-audit.md` (per-model changes)
- `<dbt_project>/.dt-migration/stage-1/state/00-test-strategy.json` (test_db, test_schema, test_wh, dt_wh)
- `../references/conversion-rules.md`

## CRITICAL: Config pattern — NEVER use target_lag

**Valid** — required params for this migration:
```jinja
{{ config(
    materialized='dynamic_table',
    snowflake_warehouse='<dt_wh from test-strategy>',
    scheduler='disable',
    refresh_mode='full',
    ... (other existing params like schema, tags, alias are fine to keep)
) }}
```

**Invalid** — will cause DDL failure:
```jinja
{{ config(
    materialized='dynamic_table',
    snowflake_warehouse='<dt_wh>',
    scheduler='disable',
    target_lag='downstream',   ← WRONG: mutually exclusive with scheduler='disable'
    refresh_mode='full'
) }}
```

`target_lag` and `scheduler='disable'` cannot coexist. Snowflake rejects DDL that has both. REMOVE `target_lag` if present in the source model.

## Per-Model Workflow

### 1. Apply conversion to model file

1. Read model file at path from inventory.
2. Apply Tier 1 — replace the config block with the exact pattern above:
   - `materialized='dynamic_table'`
   - `snowflake_warehouse='<dt_wh>'` (from `00-test-strategy.json`)
   - `scheduler='disable'`
   - `refresh_mode='full'`
   - **REMOVE** `target_lag` if present (any value)
   - **Preserve** `schema`, `database`, `tags`, `alias` if present
3. Apply Tier 2: convert post_hook scalar to list-form (if flagged in audit).
4. Write modified file back to disk.
5. **Post-write check:** grep the file for `target_lag`. If found, the conversion is wrong — fix it before proceeding.

### 2. dbt compile check

```bash
dbt compile --select <model_name> --profiles-dir <profiles_dir>
```

Verify the converted model compiles without errors (Jinja renders, macros resolve, refs valid).
If compile fails: revert the file, record FAIL with compile error, move to next model.

### 3. Lightweight validation

#### 3a. Sample parent data

For each direct parent (ref/source) of this model:
```sql
CREATE OR REPLACE TRANSIENT TABLE <test_db>.<test_schema>.val_<parent_name> AS
SELECT * FROM <parent_db>.<parent_schema>.<parent_table>
SAMPLE (1000 ROWS);
```

#### 3b. Run baseline CTAS (using the SAME sampled parents)

```sql
CREATE OR REPLACE TRANSIENT TABLE <test_db>.<test_schema>.val_baseline_<model> AS
<original_sql_with_refs_replaced_by_val_parents>;
```

#### 3c. Create transient DT (using the SAME sampled parents)

```sql
CREATE OR REPLACE TRANSIENT DYNAMIC TABLE <test_db>.<test_schema>.val_dt_<model>
  WAREHOUSE = '<test_wh>'
  REFRESH_MODE = 'FULL'
  INITIALIZE = 'ON_CREATE'
AS
<converted_sql_with_refs_replaced_by_val_parents>;
```

Wait for initial refresh to complete:
```sql
SELECT REFRESH_ACTION, STATE
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
  NAME => '<test_db>.<test_schema>.val_dt_<model>',
  DATA_TIMESTAMP_START => DATEADD('minute', -5, CURRENT_TIMESTAMP())
))
ORDER BY DATA_TIMESTAMP DESC LIMIT 1;
```

Poll until STATE = 'SUCCEEDED' (max 5 minutes, then FAIL).

#### 3d. Compare (baseline vs DT must be identical)

```sql
SELECT COUNT(*) AS diff_count FROM (
  SELECT * FROM <test_db>.<test_schema>.val_baseline_<model>
  EXCEPT
  SELECT * FROM <test_db>.<test_schema>.val_dt_<model>
);
```

Both directions must return `diff_count = 0`.

#### 3e. On PASS

Record PASS. Do NOT drop validation objects — the orchestrator handles cleanup after all batches with user approval.

#### 3f. On FAIL

1. Revert the model file to its pre-conversion state.
2. Record failure with diff details.
3. Do NOT drop validation objects — user may want to inspect them.

### 4. Record result

```json
{
  "model": "<name>",
  "status": "PASS | FAIL",
  "changes_applied": ["config_swap", "post_hook_list_form"],
  "failure_detail": null
}
```

## Loaded references

- `../references/conversion-rules.md` — Tier 1-2 transformation rules
- `../references/invariants.md` — DT behavioral constraints

## Output

Append results to `<dbt_project>/.dt-migration/stage-1/state/03-convert-results.json`.

Your final text (one line per model — orchestrator prints this to user):
```
<parent> ──→ <model_1> [FULL DT ✓]
<parent> ──→ <model_2> [FULL DT ✓]
<parent> ──→ <model_3> [FULL DT ✗ reverted — <reason>]
```
