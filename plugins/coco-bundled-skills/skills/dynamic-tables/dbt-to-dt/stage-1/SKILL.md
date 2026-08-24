---
name: dbt-to-dt-stage-1
description: "Stage 1: Convert dbt table models to FULL refresh Dynamic Tables. Quick, safe, no INC classification needed."
parent_skill: dbt-to-dt
allowed-tools:
  - Task
  - Read
  - Write
  - Bash
  - ask_user_question
  - spawn_teammate
  - agent_output
  - kill_agent
---

# Stage 1 — CTAS → FULL DT

Convert all `materialized='table'` models to `materialized='dynamic_table'` with `refresh_mode='full'`, `scheduler='disable'`.

## RULES

1. **DO NOT enter plan mode.** This skill IS the plan. Follow the phases below in order.
2. **Dispatch workers via `spawn_teammate` for Phases 1-4.** You are the orchestrator — you print progress and dispatch.
3. **Batch cap: max 5 models per batch.**
4. **Never drop objects without user approval.**

## On load — execute IMMEDIATELY (no thinking, no exploring first):

### 1. Run setup-tasks.sh FIRST

```bash
bash <skill_dir>/stage-1/setup-tasks.sh
```

This registers your task tracker. Do this before reading any model files or asking questions.

### 2. Print state machine

```
Stage 1: CTAS → FULL DT — 5 Phases
=====================================
[1/5] Test Strategy     ← asking you now
[2/5] Inventory         ← worker
[3/5] Conversion Audit  ← worker
[4/5] Convert+Validate  ← worker (per batch, max 5 models)
[5/5] Report            ← worker

All models become FULL DT. No INC classification needed.
```

### 3. Phase 0: Test Strategy [you handle directly]

Ask the user 5 questions via ask_user_question:

1. "Where is testing happening? (a) dev schema (b) clone DB (c) parallel project (d) other"
2. "Role / Database / Schema / Warehouse for validation objects?"
3. "Warehouse for DT config? (the warehouse your converted DTs will reference)"
4. "Isolation approach? (a) in-place (b) parallel folder (c) other"
5. "Rollback plan? (a) leave as-is (b) revert model (c) revert batch"

After all 5 answers — validate:

```sql
SHOW WAREHOUSES LIKE '<test_warehouse>';
SHOW WAREHOUSES LIKE '<dt_warehouse>';
SHOW SCHEMAS IN DATABASE <test_db>;
```

After validation passes:
- `mkdir -p <dbt_project>/.dt-migration/stage-1/state`
- Write `stage-1/state/00-test-strategy.json`
- Mark step done: `cortex ctx step done -t <TASK> s-1`

Print:
```
✓ [SETUP] 1/5 Test strategy saved.
  Test target: <test_db>.<test_schema> via <test_wh>
  DT warehouse: <dt_wh>
```

## Phases 1-2, 4: Dispatch workers

For phases 1, 2, and 4:
1. Print: `→ [PHASE] N/5 <Name>: dispatching worker...`
2. Read phase prompt: `<skill_dir>/stage-1/phases/<NN>-<name>.md`
3. Spawn worker with phase content + context pack:
   ```
   Context pack:
   - dbt_project: <path>
   - test_strategy: db=<db>, schema=<schema>, test_wh=<wh>, dt_wh=<dt_wh>, role=<role>
   - skill_dir: <path to dbt-to-dt/ skill directory>
   - references_dir: <skill_dir>/references/
   - artifacts_dir: <dbt_project>/.dt-migration/stage-1/state/
   ```
4. Wait: `agent_output(wait=true)`
5. Print worker's summary (defined in each phase file)
6. Mark step done: `cortex ctx step done -t <TASK> s-<N>`

### Phase 3: Convert + Validate (all batches in parallel)

Read `stage-1/state/02-batch-plan.json`. It specifies `"dispatch": "all_parallel"` — dispatch ALL batches simultaneously. No waves, no layer ordering. Each model's validation samples from production parents independently.

1. Read `stage-1/state/02-batch-plan.json`.
2. Dispatch ALL batches at once (not in waves/layers):
   - Print: `→ [CONVERT] Dispatching <N> batches in parallel (<total> models). Results will print as each batch finishes.`
   - For each batch: spawn worker with `phases/03-convert-validate.md` + context pack + batch model list
3. **IMMEDIATELY print each batch result as it arrives** — do NOT wait for all batches before showing anything. After EACH `agent_output` returns, print that batch's result right away:
     ```
     ✓ Batch N/M done (X models):
       source(raw_orders) ──→ stg_orders [FULL DT ✓]
       source(raw_users)  ──→ stg_users [FULL DT ✓]
     ```
   The user MUST see progress after each batch, not a silent 10-minute wait.
4. After ALL batches complete — print consolidated summary:
     ```
     Convert + Validate complete (<N> batches, <total> models):
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
     source(raw_orders)    ──→ stg_orders            [FULL DT ✓]
     source(raw_customers) ──→ stg_customers         [FULL DT ✓]
     stg_orders + stg_products ──→ int_order_items   [FULL DT ✓]
     stg_customers + int_order_items ──→ fct_revenue [FULL DT ✗ reverted — validation mismatch]
     ...

     Summary: <N> PASS, <N> FAIL
     ```
   - Use `ask_user_question` to ask about cleanup. DO NOT drop anything until user responds:
     ```
     "Validation objects in <test_db>.<test_schema>: <N> val_* objects. Clean up now?"
     Options: (a) drop all (b) keep for inspection (c) skip
     ```
     If user says (a): drop. If (b) or (c): leave them.
   - Mark step done: `cortex ctx step done -t <TASK> s-4`

### Phase dispatch table

| Phase | Prompt file | Step | Dispatch |
|-------|------------|------|----------|
| 1 Inventory | `phases/01-inventory.md` | s-2 | single worker |
| 2 Conversion Audit | `phases/02-conversion-audit.md` | s-3 | single worker |
| 3 Convert + Validate | `phases/03-convert-validate.md` | s-4 | **per-batch** |
| 4 Report | `phases/04-report.md` | s-5 | single worker |

Each worker's phase file defines its own output format. The orchestrator prints whatever the worker returns — no reformatting.

---

## Done

```
Stage 1 complete. Artifacts in <dbt_project>/.dt-migration/stage-1/
```

Cleanup: `cortex ctx team delete team-dbt-dt-stage1`
