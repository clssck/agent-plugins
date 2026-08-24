## Context

You are a worker dispatched by the orchestrator. User has approved shadow promotion for specific models.

# Phase 6 — Shadow Promotion

Create persistent `_inc_shadow` DTs for user-approved models. These run alongside production FULL DTs for observation.

## Inputs

- User's approval list (which models to promote to shadow)
- `<dbt_project>/.dt-migration/stage-2/state/layer-N-report.json`
- `<dbt_project>/.dt-migration/stage-2/state/00-test-strategy.json` (test_db, test_schema, test_wh)

## Per-Model Workflow

### 1. Get compiled SQL

Same as Phase 4 validation — try `dbt compile`, fall back to direct SQL extraction.

### 2. Create persistent shadow DT

```sql
CREATE DYNAMIC TABLE <test_db>.<test_schema>.<model>_inc_shadow
  WAREHOUSE = <test_wh>
  REFRESH_MODE = ADAPTIVE
  SCHEDULER = 'DISABLE'
AS
<compiled SQL>;
```

### 3. Trigger initial refresh

```sql
ALTER DYNAMIC TABLE <test_db>.<test_schema>.<model>_inc_shadow REFRESH;
```

Wait for completion.

### 4. Verify (same check as validation — should pass since Phase 4 proved it)

```sql
SHOW DYNAMIC TABLES LIKE '<model>_inc_shadow' IN SCHEMA <test_db>.<test_schema>;
```

### 5. Record result

Write `<dbt_project>/.dt-migration/stage-2/state/layer-N-shadows.json`:
```json
{
  "layer": 0,
  "created_at": "<timestamp>",
  "shadows": [
    {"model": "<name>", "shadow_fqn": "<test_db>.<test_schema>.<model>_inc_shadow", "status": "active"}
  ]
}
```

## Output

```
Shadow DTs created (<N> models):
  <model_1>_inc_shadow [active] — ready for observation
  <model_2>_inc_shadow [active] — ready for observation

These run alongside your production FULL DTs.
When ready to compare performance, invoke Stage 2 again.
To deploy to production: change refresh_mode='full' → 'adaptive' in model file + dbt run --full-refresh.
After deploy succeeds: invoke Stage 2 again to clean up shadows.
```
