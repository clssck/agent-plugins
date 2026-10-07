## Context

You are a worker dispatched by the orchestrator. You receive a context pack with inputs.

# Phase 2 — Conversion Audit

Apply conversion-rules.md to each convertible model. Identify what changes are needed per model.

## Inputs

- `<dbt_project>/.dt-migration/stage-1/state/01-inventory.json` (convertible models list)
- `../references/conversion-rules.md`
- `../references/invariants.md`

## Workflow

1. Load references.
2. For each model with classification = CONVERTIBLE:

   a. Read the `{{ config(...) }}` block from the model SQL file.
   b. Read the SQL body.
   c. Apply each tier from `conversion-rules.md`:

   **Tier 1 (config swap — always apply):**
   - `materialized='table'` → `materialized='dynamic_table'`
   - Add: `snowflake_warehouse='<dt_wh>'` (from test-strategy), `scheduler='disable'`, `refresh_mode='full'`
   - Remove: `target_lag` (if present)
   - Stays: `schema`, `database`, `tags`, `alias`

   **Tier 2 (SQL fixes — scan and flag):**
   - post_hook scalar → flag for list-form conversion

   **Tier 3 (user review — escalate):**
   - `on_schema_change`, `unique_key`, `incremental_strategy` → flag
   - post_hook/pre_hook with complex macros → flag
   - Unknown parameters → flag

3. Write `<dbt_project>/.dt-migration/stage-1/state/02-conversion-audit.md`

4. Compute batch plan from DAG (read `ref()` dependencies from `01-inventory.json`):
   - Layer 0: models with no `ref()` to other convertible models
   - Layer 1: models that `ref()` Layer 0 models
   - Layer N: models that `ref()` Layer N-1 models
   - Split layers with >5 models into sub-batches of 5

   Write `<dbt_project>/.dt-migration/stage-1/state/02-batch-plan.json`:
   ```json
   {
     "validation_strategy": "sample_and_compare",
     "validation_details": "Per model: SAMPLE 1000 rows from each production parent into transient tables in test schema, CTAS baseline vs transient DT, EXCEPT comparison. Each model validates independently — no dependency on other models being converted first.",
     "dispatch": "all_parallel",
     "dispatch_details": "ALL batches dispatch simultaneously. FULL DT validation samples from production parents — converting model A has zero effect on model B's validation. No wave/layer ordering needed.",
     "batches": [
       {"batch": 1, "models": ["stg_orders", "stg_customers", "stg_products"]},
       {"batch": 2, "models": ["stg_events", "stg_sessions"]},
       {"batch": 3, "models": ["int_order_items", "fct_revenue"]}
     ]
   }
   ```

5. Present checkpoint:
   ```
   CHECKPOINT — Conversion Audit
   ═══════════════════════════════
   <N> models ready for conversion in <B> batches.
   <M> have Tier 2 auto-fixes (post_hook list-form).
   <K> need your review (hooks, unknown params).

   Batch plan:
     Batch 1: <models> (Layer 0)
     Batch 2: <models> (Layer 0)
     Batch 3: <models> (Layer 1)
     ...

   Approve? [yes / review details / abort]
   ```

## Output

Your final text:

```
┌─────────────────────────┬───────┬────────┐
│ Finding                 │ Count │ Action │
├─────────────────────────┼───────┼────────┤
│ Config swap (Tier 1)    │ <N>   │ auto   │
│ Hook review needed      │ <N>   │ user   │
└─────────────────────────┴───────┴────────┘
Escalations: <N> (requires user decision)
Details: .dt-migration/stage-1/state/02-conversion-audit.md
```
