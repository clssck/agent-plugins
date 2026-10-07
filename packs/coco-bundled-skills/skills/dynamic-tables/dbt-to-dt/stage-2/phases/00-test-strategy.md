## Context

You are a worker dispatched by the orchestrator.

# Phase 1 — Test Strategy (Stage 2)

## Workflow

1. Check if Stage 1 already ran: look for `<dbt_project>/.dt-migration/stage-1/state/00-test-strategy.json`
2. If exists: read and confirm with user via `ask_user_question`:
   ```
   Stage 1 used: <db>.<schema> via <wh>, DT warehouse: <dt_wh>
   Continue with same environment? [yes / update]
   ```
3. If "yes": reuse. Write `<dbt_project>/.dt-migration/stage-2/state/00-test-strategy.json` with Stage 1 config + Stage 2 additions below.
4. If "update" or no Stage 1 artifacts: ask the same 5 questions as Stage 1 Phase 0.

## Stage 2 naming conventions (written into test-strategy)

These naming conventions prevent collisions when testing in parallel with existing models:

- **Shadow DTs:** `<model>_inc_shadow` in test schema (e.g., `<test_db>.<test_schema>.stg_orders_inc_shadow`)
- **Test schema:** same as Stage 1 test target
- **No model file renames during testing.** Shadow DTs are created via DDL in the test schema — they are NOT dbt models. No name collision with existing dbt models.
- **Promotion:** When user decides to promote, the original model file gets `refresh_mode='full'` → `refresh_mode='adaptive'`. Shadow is dropped after production deploy. No suffix in production.

## Output

Write `<dbt_project>/.dt-migration/stage-2/state/00-test-strategy.json`:
```json
{
  "stage": 2,
  "reuses_stage_1": true,
  "test_target": {"db": "<db>", "schema": "<schema>", "warehouse": "<wh>"},
  "dt_warehouse": "<dt_wh>",
  "role": "<role>",
  "conventions": {
    "shadow_suffix": "_inc_shadow",
    "shadow_schema": "<test_schema>",
    "compile_fallback": "use model SQL directly if name collision occurs"
  }
}
```

Return: `✓ Test strategy confirmed. Target: <db>.<schema> via <wh>. Shadow suffix: _inc_shadow`
