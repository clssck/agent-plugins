## Context

You are a worker dispatched by the orchestrator. You receive a context pack with inputs.

# Phase 0 — Test Strategy

This phase is **conversational**. No autonomous work happens until the user has answered the questions below.

## Workflow

1. Ask the user 5 questions via `ask_user_question`:

   1. "Where is testing happening? (a) dev schema (b) clone DB (c) parallel project (d) other"
   2. "Role / Database / Schema / Warehouse for validation objects?"
   3. "Warehouse for DT config? (the warehouse your converted DTs will reference in their config)"
   4. "Isolation approach? (a) in-place (b) parallel folder (c) other"
   5. "Rollback plan? (a) leave as-is (b) revert model (c) revert batch"

2. Validate dbt readiness **(BLOCKING)**:

   Confirm `dbt` is callable and check the dbt-snowflake adapter version via `dbt --version`. Requirements:
   - **dbt is available** — record the path (needed for `dbt compile` in later phases)
   - **dbt-snowflake >= 1.11.5** — this is when `scheduler='disable'` support was added

   Read the version from the `Plugins:` → `snowflake:` line, NOT the Core line:
   ```
   Core:
     - installed: 1.11.9
   Plugins:
     - snowflake: 1.11.5      ← this is the version that matters
   ```
   Note: `dbt-adapters` and `dbt-common` are separate shared libraries on their own version tracks (their numbers look different and higher) — ignore those. Only the `snowflake:` plugin version gates this migration.

   If `dbt` is not found or the snowflake plugin is below 1.11.5: **STOP.** Tell the user:
   ```
   ⚠️ BLOCKING: dbt-snowflake >= 1.11.5 is required for this migration.

   scheduler='disable' was added in 1.11.5. On older versions, the scheduler
   field is silently ignored and target_lag resolves to 'None', causing
   Snowflake to reject the DDL with a compilation error.
   ```

   If version cannot be detected: ask user to confirm manually.

   **Key constraint to surface:**
   > `scheduler='disable'` and `target_lag` are **mutually exclusive**. Any existing `target_lag` in model configs will be REMOVED during conversion.

3. Validate environment:

   ```sql
   SHOW WAREHOUSES LIKE '<test_warehouse>';
   SHOW WAREHOUSES LIKE '<dt_warehouse>';
   SHOW SCHEMAS IN DATABASE <test_db>;
   ```

   If any fail, ask user to correct.

4. Write `<dbt_project>/.dt-migration/stage-1/state/00-test-strategy.json`:

```json
{
  "dbt_path": "<path to dbt binary>",
  "dbt_snowflake_version": "<detected version>",
  "test_db": "<db>",
  "test_schema": "<schema>",
  "test_wh": "<wh>",
  "dt_wh": "<dt_wh>",
  "role": "<role>",
  "isolation": "in-place | parallel-folder",
  "rollback": "leave-as-is | revert-model | revert-batch"
}
```

## Output

Return:
```
✓ Test strategy saved.
  dbt: <path> (dbt-snowflake <version> ✓)
  Target: <db>.<schema> via <wh>
  DT warehouse: <dt_wh>
  ⚠️ target_lag will be REMOVED from models during conversion (mutually exclusive with scheduler='disable')
```
