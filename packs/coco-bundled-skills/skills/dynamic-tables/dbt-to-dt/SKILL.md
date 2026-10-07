---
name: dbt-to-dt
description: "Convert dbt table models to Snowflake Dynamic Tables. Two stages: Stage 1 converts to FULL DT (quick, safe). Stage 2 upgrades eligible FULL DTs to INCREMENTAL (iterative, per-layer). Use when: migrate dbt to DT, convert dbt models to dynamic tables, dbt materialized dynamic_table, table to DT migration, make models incremental."
parent_skill: dynamic-tables
---

# dbt-to-dt — Router

Detects user intent and routes to the appropriate sub-skill.

## Applicability check

This skill is for **dbt projects** being migrated to Dynamic Tables. If there is no dbt project in the user's working directory (no `dbt_project.yml`), this skill does not apply — fall back to the parent `dynamic-tables` skill's OPTIMIZE intent instead.

## Routing

| User intent | Route to |
|-------------|----------|
| "Convert my dbt models to DTs" / "migrate to dynamic tables" / first-time migration | `stage-1/SKILL.md` |
| "Can this model be a DT?" / pastes single SQL / "classify this model" | `advisor/SKILL.md` |
| "Upgrade FULL DTs to INC" / "check shadow results" / "next INC layer" / "optimize my DTs" | `stage-2/SKILL.md` |
| "What's the status of my migration?" | Check `<dbt_project>/.dt-migration/` artifacts and report current state |

## Key Concept: Two-Stage Migration

**Stage 1 — CTAS → FULL DT (quick win):**
- Converts `materialized='table'` to `materialized='dynamic_table'` with `refresh_mode='full'`
- No change tracking needed, no cascade analysis, no operator classification
- Only DDL blockers matter (UUID_STRING, RANDOM, WITH RECURSIVE, UNPIVOT, SAMPLE)
- Lightweight validation: sample-and-compare per model

**Stage 2 — FULL DT → INC upgrade (iterative):**
- Upgrades individual FULL DTs to `refresh_mode='adaptive'` where safe
- One topological layer at a time (upstream first)
- Shadow + Observe + Promote pattern (create INC shadow, wait N days, compare, promote via dbt)
- User invokes repeatedly — each run handles one layer

## Architecture: scheduler='disable'

All converted DTs use `scheduler='disable'`. dbt remains the orchestrator — refreshes happen on each `dbt run` via `ALTER DYNAMIC TABLE ... REFRESH`. No TARGET_LAG.

## References

Shared knowledge loaded by both stages:
- `references/conversion-rules.md` — risk-tiered conversion rules
- `references/invariants.md` — DT behavioral constraints
- `references/runtime-failures.md` — error catalog

Stage 2 additionally loads:
- `references/classification-rules.md` — operator matching for INC eligibility
- `references/incremental-operators.md` (parent: `../../references/incremental-operators.md`)
- `references/validation-playbook.md` — INC validation checks + data equivalence
- `references/cascade-rules.md` — cascade logic for INC upgrade decisions
