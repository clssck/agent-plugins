---
name: dbt-to-dt-stage-2
description: "Stage 2: Upgrade FULL DTs to INCREMENTAL where safe. Iterative, one topological layer at a time. Shadow + Observe + Promote."
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

# Stage 2 — FULL DT → INC Upgrade

Upgrade eligible FULL DTs to `refresh_mode='adaptive'`. One topological layer at a time.

## RULES

1. **DO NOT enter plan mode.** This skill IS the plan. Follow the phases below.
2. **Dispatch workers via `spawn_teammate` for Phases 1-5.** You are the orchestrator.
3. **One layer per invocation.** After a layer completes, use `ask_user_question` to ask if user wants next layer.
4. **Never drop objects without user approval.** Use `ask_user_question` and wait for response before any DROP.

## On load — execute IMMEDIATELY (no reading, no exploring first):

### 1. Run setup-tasks.sh FIRST

```bash
bash <skill_dir>/stage-2/setup-tasks.sh
```

This registers your task tracker. Do this before reading any model files or analyzing anything.

### 2. Print state machine

```
Stage 2: FULL → INC Upgrade — 7 Phases
=========================================
[1/7] Test Strategy       ← confirm/reuse from Stage 1
[2/7] Pipeline Inventory  ← read DAG, identify layers
[3/7] Candidate Assessment ← classify operators + check CT (analysis only)
[4/7] Validation          ← transient INC DT, verify it stays INC, drop it
[5/7] Report              ← present findings: passed, blocked, recommendations
[6/7] Shadow Promotion    ← user approves, create persistent _inc_shadow DTs
[7/7] Cleanup + Next Steps ← after deploy: drop shadows, recommend next layer

This is iterative — each invocation handles one layer.
Layer N+1 starts after Layer N is resolved.
```

### 3. Detect current state

Read `<dbt_project>/.dt-migration/stage-2/state/` to determine:
- Which layer we're on
- Whether shadows exist (resume at Phase 5) or need creation (Phase 3-4)
- Whether this is a fresh start (Phase 1-2)

Detection logic:
- No `stage-2/state/` dir → fresh start (Phase 1)
- Has `01-pipeline-state.json` but no `layer-N-candidates.json` → Phase 3
- Has `layer-N-candidates.json` but no `layer-N-validation.json` → Phase 4
- Has `layer-N-validation.json` but no `layer-N-report.json` → Phase 5
- Has `layer-N-report.json` but no `layer-N-shadows.json` → Phase 6 (user approved promotion)
- Has `layer-N-shadows.json` → Phase 7 (cleanup after deploy)
- Layer fully complete (report + no shadows) → ask user if ready for next layer

### 4. Route to appropriate phase

Based on detected state, dispatch the right phase worker.

## Phase dispatch

For each phase, dispatch workers:
1. Print: `→ [PHASE] N/7 <Name>: dispatching worker...`
2. Read phase prompt: `<skill_dir>/stage-2/phases/<NN>-<name>.md`
3. Spawn worker with phase content + context pack
4. Wait: `agent_output(wait=true)`
5. Print worker's summary
6. Mark step done: `cortex ctx step done -t <TASK> s-<N>`

### Phases 3 and 4: per-batch if >5 models

If the current layer has more than 5 models, split into batches of 5 for:
- Phase 3 (candidate assessment): one worker per batch, print per-model results
- Phase 4 (shadow validation): one worker per batch, print per-model results

Same pattern as Stage 1 Phase 3. User sees progress after each batch of 5.

### Phase dispatch table

| Phase | Prompt file | Step | When |
|-------|------------|------|------|
| 1 Test Strategy | `phases/00-test-strategy.md` | s-1 | Fresh start only |
| 2 Pipeline Inventory | `phases/01-pipeline-inventory.md` | s-2 | Always first |
| 3 Candidate Assessment | `phases/02-candidate-assessment.md` | s-3 | If no candidates.json for current layer |
| 4 Validation | `phases/03-validation.md` | s-4 | If candidates exist but no validation.json |
| 5 Report | `phases/04-report.md` | s-5 | After validation done |
| 6 Shadow Promotion | `phases/05-shadow-promotion.md` | s-6 | After user reviews report and approves |
| 7 Cleanup + Next Steps | `phases/06-cleanup.md` | s-7 | After user deploys PR |

## Context pack (passed to each worker)

```
- dbt_project: <path>
- test_strategy: db=<db>, schema=<schema>, test_wh=<wh>, dt_wh=<dt_wh>, role=<role>
- skill_dir: <path to dbt-to-dt/ skill directory>
- references_dir: <skill_dir>/references/
- artifacts_dir: <dbt_project>/.dt-migration/stage-2/state/
- current_layer: <N>
```

## References

Load in addition to shared references:
- `../references/classification-rules.md` — operator matching for INC eligibility
- `../../references/incremental-operators.md` — the operator lookup table
- `../references/validation-playbook.md` — INC validation checks
- `../references/cascade-rules.md` — cascade logic

---

## Done (per layer)

```
Layer <N> complete. <promoted> promoted to INC, <dropped> kept as FULL.
```

Use `ask_user_question`: "Ready to start Layer <N+1>? [yes / not now]"

Cleanup: `cortex ctx team delete team-dbt-dt-stage2`
