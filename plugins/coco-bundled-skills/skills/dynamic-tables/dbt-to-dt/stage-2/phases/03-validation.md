## Context

You are a worker dispatched by the orchestrator.
The orchestrator calls you once per batch (max 5 candidates).

# Phase 4 — Validation

Create a TRANSIENT INC DT for each candidate. Verify Snowflake keeps it as INCREMENTAL. Then DROP it.

This is a quick check — not a persistent deployment. We're proving "can this SQL run as INC?" before committing to shadow promotion.

## Inputs

- Batch candidate list (from orchestrator — confirmed candidates only)
- `<dbt_project>/.dt-migration/stage-2/state/layer-N-candidates.json`
- `<dbt_project>/.dt-migration/stage-2/state/00-test-strategy.json` (test_db, test_schema, test_wh)

## Per-Model Workflow

### 1. Get compiled SQL

Try `dbt compile --select <model_name>`. If compile fails (name collision), read the SQL body directly from the model file — strip `{{ config(...) }}` and replace refs/sources with fully qualified names from inventory.

### 2. Create TRANSIENT INC DT

This project uses `scheduler='disable'` — the required pattern.

```sql
CREATE OR REPLACE TRANSIENT DYNAMIC TABLE <test_db>.<test_schema>.val_inc_<model>
  WAREHOUSE = <test_wh>
  REFRESH_MODE = ADAPTIVE
  SCHEDULER = 'DISABLE'
AS
<compiled SQL>;
```

### 3. Trigger refresh and wait

```sql
ALTER DYNAMIC TABLE <test_db>.<test_schema>.val_inc_<model> REFRESH;
```

Poll until complete (max 5 minutes):
```sql
SELECT REFRESH_ACTION, STATE
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
  NAME => '<test_db>.<test_schema>.val_inc_<model>',
  DATA_TIMESTAMP_START => DATEADD('minute', -5, CURRENT_TIMESTAMP())
))
ORDER BY DATA_TIMESTAMP DESC LIMIT 1;
```

### 4. Check — does refresh_mode stay INCREMENTAL?

```sql
SHOW DYNAMIC TABLES LIKE 'val_inc_<model>' IN SCHEMA <test_db>.<test_schema>;
-- Check: refresh_mode = 'INCREMENTAL', refresh_mode_reason = NULL
```

**PASS:** refresh_mode = INCREMENTAL, reason = NULL
**FAIL:** downgraded to FULL, or reason is non-NULL

### 5. Drop the transient DT (always — this is validation, not deployment)

```sql
DROP DYNAMIC TABLE IF EXISTS <test_db>.<test_schema>.val_inc_<model>;
```

### 6. Record result

Append to `<dbt_project>/.dt-migration/stage-2/state/layer-N-validation.json`:
```json
[
  {
    "model": "<name>",
    "status": "PASS | FAIL",
    "refresh_mode": "INCREMENTAL | FULL",
    "refresh_mode_reason": null | "<reason>"
  }
]
```

If FAIL: write `-- DT-INC-BLOCKED: <refresh_mode_reason> (verified by validation)` in model file.

## Output

Your final text (one line per model):
```
<model_1> [INC ✓] — validated, transient dropped
<model_2> [FAIL] — reason: QUERY_NOT_SUPPORTED — annotated
```
