# Workspace Files

Lightweight tracking for the optimize loop. No local `versions/` tree and no per-question JSON dumps — Snowflake agent versions and eval run names are the source of truth.

```
<WORKSPACE_DIR>/
├── state.json
├── optimization_log.md
└── DEPLOYMENT_SUMMARY.md    # Phase 6
```

Write these with a shell heredoc. Do not add `.py` helpers.

## state.json

Create in Phase 1. Update `current_phase` and the matching `phases_completed` entry as soon as a phase passes — do not batch writes.

```json
{
  "source_fqn": "DATABASE.SCHEMA.AGENT",
  "working_fqn": "DATABASE.SCHEMA.AGENT_OPT",
  "clone_fqn": "DATABASE.SCHEMA.AGENT_OPT",
  "workspace_dir": "./agent-optimize-AGENT",
  "dataset_name": null,
  "metric_scope": null,
  "eval_source": null,
  "current_phase": 1,
  "runs": {
    "baseline": null,
    "after_improvements": null,
    "generalized": null
  },
  "agent_versions": {
    "baseline": null,
    "after_improvements": null,
    "generalized": null
  },
  "phases_completed": {
    "1_discovery": { "status": "pending" },
    "2_dataset": { "status": "pending" },
    "3_baseline": { "status": "pending" },
    "4_improvements": { "status": "pending" },
    "5_overfitting": { "status": "pending" },
    "6_generalization": { "status": "pending" }
  }
}
```

`clone_fqn` is `null` when the user is not on a production clone. `working_fqn` is always the agent this loop mutates.

## optimization_log.md

Append after each phase. Keep it short.

```markdown
# Optimization log: <WORKING_FQN>

## Phase 1 — Discovery
- Source: <SOURCE_FQN>
- Working: <WORKING_FQN>
- Tools: …
- Known issues: …

## Phase 2 — Dataset
- Dataset: <DATASET_NAME>
- Scope: ac | tea | both

## Phase 3 — Baseline
- Run: <RUN_NAME>
- Mean AC: …
- Patterns: …

## Phase 4 — Improvements
- Version saved: VERSION$N
- Run: <RUN_NAME>
- Comparison: …

## Phase 5 — Overfitting
- Critical / medium / low: …

## Phase 6 — Generalization
- Version saved: VERSION$N
- Run: <RUN_NAME>
- Three-way: …
```

## Success criteria

| Check | Target |
|-------|--------|
| Mean `answer_correctness` | `> 0.80` on the final run |
| Critical overfitting | 0 |
| Regressions vs baseline (Pass → Fail) | 0 |
| Domain-expert approval | Yes |

Instruction size is informational (character count of `instructions.*`). There is no hard cap.

## DEPLOYMENT_SUMMARY.md

```markdown
# Deployment summary: <AGENT_NAME>

## Accuracy
- Baseline: mean AC … (pass/partial/fail)
- After improvements: …
- Generalized: …
- Delta vs baseline: …

## Changes
1. …

## Instruction size
- Baseline: N chars
- Final: N chars

## Readiness
- [ ] Accuracy target met
- [ ] No critical overfitting
- [ ] Generalized beyond the eval set
- [ ] Domain expert approved
- [ ] Clone published to original (if applicable)

## Follow-up
- Collect production misses into the next dataset expand
- Re-eval when tools or data change
```
