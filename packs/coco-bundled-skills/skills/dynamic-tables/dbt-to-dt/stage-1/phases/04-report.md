## Context

You are a worker dispatched by the orchestrator. You receive a context pack with inputs.

# Phase 4 — Report

Final summary of Stage 1 migration. Present results and offer Stage 2.

## Inputs

- `<dbt_project>/.dt-migration/stage-1/state/01-inventory.json`
- `<dbt_project>/.dt-migration/stage-1/state/02-conversion-audit.md`
- `<dbt_project>/.dt-migration/stage-1/state/03-convert-results.json`
- `<dbt_project>/.dt-migration/stage-1/state/00-test-strategy.json`

## Workflow

1. Read all prior artifacts.
2. Write `<dbt_project>/.dt-migration/stage-1/report.md` with sections:

**Section: Migration Summary**
- Total models in project
- Converted to FULL DT (count + list)
- Skipped — DDL blockers (count + list with reasons)
- Failed validation (count + list with failure details)
- Out of scope (incremental/view/ephemeral)

**Section: Per-Model Changes**
| Model | Status | Changes Applied |
|-------|--------|----------------|
| stg_orders | ✓ Converted | config swap |
| stg_events | ✗ SKIP | UUID_STRING — cannot be DT |

**Section: What to do next**
1. **PR preparation:** Based on test strategy (in-place / parallel), prepare a PR with the converted model files.
2. **Test resource cleanup:** List all `val_*` objects in test schema. User decides keep or drop.
3. **Stage 2 (optional):** "<N> of your FULL DTs may be eligible for INCREMENTAL refresh. This reduces cost by only processing changed data. Run Stage 2 when ready — no rush, FULL DTs are already working correctly."

**Section: Test resources created**
List every object created in `<test_db>.<test_schema>` during validation.

3. Present summary to user.

## Output

Write to `<dbt_project>/.dt-migration/stage-1/report.md`.

Your final text:
```
Stage 1 Complete
━━━━━━━━━━━━━━━━
Converted: <N> models → FULL DT
Skipped:   <N> (DDL blockers)
Failed:    <N> (validation failures — kept as table)

Details: .dt-migration/stage-1/report.md

Next: Stage 2 can upgrade eligible FULL DTs to INCREMENTAL.
      Invoke with "upgrade my DTs to incremental" when ready.
```
