## Context

You are a worker dispatched by the orchestrator. User has deployed the PR and wants to clean up.

# Phase 7 — Cleanup + Next Steps

Drop shadow DTs after user confirms production deploy succeeded. Provide recommendations for next steps.

## Inputs

- `<dbt_project>/.dt-migration/stage-2/state/layer-N-shadows.json`
- `<dbt_project>/.dt-migration/stage-2/state/00-test-strategy.json`

## Workflow

### 1. List shadow DTs

```sql
SHOW DYNAMIC TABLES LIKE '%_inc_shadow' IN SCHEMA <test_db>.<test_schema>;
```

### 2. Confirm with user via ask_user_question

```
Shadow DTs in <test_db>.<test_schema>:
  <model_1>_inc_shadow
  <model_2>_inc_shadow

Have you deployed the PR and confirmed production works? Drop all shadows? [approve / keep]
```

### 3. If approved: drop

```sql
DROP DYNAMIC TABLE IF EXISTS <test_db>.<test_schema>.<model>_inc_shadow;
```

### 4. Present next steps

```
Layer <N> complete.

Recommendations:
1. Audit promoted models in production:
   - Run: SHOW DYNAMIC TABLES LIKE '<model>' — verify refresh_mode=INCREMENTAL
   - Check refresh history after a few runs to confirm NO_DATA behavior
2. Monitor for silent downgrades (refresh_mode_reason becomes non-NULL)
3. When ready for Layer <N+1>: invoke Stage 2 again

Blocked models that could become INC with changes:
  <model> — needs COUNT(DISTINCT) → pre-aggregate rewrite
  <model> — needs DIM_EMPLOYEE CT enabled (coordinate with IT team)
```

## Output

```
Layer <N> cleanup complete.
Shadows dropped: <list>

Next: Layer <N+1> has <M> FULL DTs.
Invoke Stage 2 again when ready.
```
