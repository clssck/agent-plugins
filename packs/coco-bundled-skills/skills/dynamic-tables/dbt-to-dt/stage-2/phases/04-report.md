## Context

You are a worker dispatched by the orchestrator.

# Phase 5 — Report

Present Layer N findings to the user. They review this before deciding which models to promote.

## Inputs

- `<dbt_project>/.dt-migration/stage-2/state/layer-N-candidates.json`
- `<dbt_project>/.dt-migration/stage-2/state/layer-N-validation.json`
- `<dbt_project>/.dt-migration/stage-2/state/01-pipeline-state.json`

## Workflow

1. Read all state files for this layer.
2. Synthesize findings.
3. Write `<dbt_project>/.dt-migration/stage-2/state/layer-N-report.json`:
   ```json
   {
     "layer": 0,
     "validated_inc": ["model_a", "model_b"],
     "blocked_operator": [{"model": "model_c", "reason": "COUNT(DISTINCT)"}],
     "blocked_ct": [{"model": "model_d", "reason": "DIM_EMPLOYEE CT=OFF"}],
     "blocked_validation": [{"model": "model_e", "reason": "091912 CURRENT_DATE in view"}]
   }
   ```
4. Write `<dbt_project>/.dt-migration/stage-2/report.md` (human-readable).

## Output

```
Layer <N> Report
━━━━━━━━━━━━━━━━
Validated INC:       <N> models (ready for shadow promotion)
Blocked (operator):  <N> models (annotated in model files)
Blocked (CT):        <N> models (need upstream team action)
Blocked (validation):<N> models (Snowflake rejected INC)

Ready for promotion:
  <model_1> — LEFT JOIN + GROUP BY, all CT ON
  <model_2> — simple WHERE, view chain OK

Blocked:
  <model_3> — COUNT(DISTINCT), suggest pre-aggregate
  <model_4> — DIM_EMPLOYEE CT=OFF (owned by IT_MODELING_RL)

Proceed with shadow promotion for validated models? [approve / select / skip]
```
