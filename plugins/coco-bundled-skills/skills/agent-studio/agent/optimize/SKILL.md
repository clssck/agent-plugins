---
name: agent-studio-agent-optimize
description: "Optimize a Cortex Agent for production readiness: baseline eval, failure-pattern analysis, instruction improvements, overfitting check, generalization, and re-eval. Use when the user wants to optimize an agent, improve agent accuracy, prepare an agent for production, fix systematic wrong answers, detect overfitting in instructions, or run the evaluate-improve-generalize loop. Trigger phrases: optimize my agent, improve my agent, make my agent production-ready, agent accuracy is low, systematically improve agent instructions, generalize agent instructions, overfitting in agent instructions. Do NOT use for semantic-view agentic optimization (that is semantic-view/agentic_optimization) or a one-shot eval with no improvement loop (that is eval/SKILL.md)."
parent_skill: agent-studio-agent
---

# Optimize Cortex Agent

Guided loop: discover → dataset → baseline eval → instruction improvements → overfitting check → generalize → re-eval.

> Tool usage: see parent `agent/SKILL.md`.
> - **REQUIRED:** `cortex agent-studio` for spec and eval (`agent-read` / `agent-write` / `agent-save` / `agent-deploy` / `eval-write` / `eval-deploy`)
> - **REQUIRED:** `snowflake_sql_execute` for `SHOW AGENTS`, `SHOW VERSIONS`, eval status, and observability
> - **FORBIDDEN:** legacy `cortex-agent` Python scripts, Streamlit, `run_evaluation.py`, hand-written `CREATE AGENT` / `ALTER AGENT ... SET SPECIFICATION`
> - **Permission errors** during dataset or eval → load `../permission/SKILL.md`. Do not suggest GRANTs or workarounds.

This skill **coordinates**. It does not reimplement dataset authoring or eval deploy. Load those siblings and return here.

## When to Use

| Use this skill | Use something else |
|----------------|--------------------|
| Improve an existing agent against a dataset, then ship | One-shot eval → `../eval/SKILL.md` |
| Production-readiness / systematic accuracy work | Config health check → `../audit/SKILL.md` |
| Instruction overfitting / generalization | One wrong request → `../../debug/SKILL.md` |
| Agent-level evaluate → improve → generalize | Automated SV job → `../../semantic-view/agentic_optimization/SKILL.md` |

## Scoring

Native evals return 0–1 floats. Bucket `answer_correctness` as:

| Bucket | Score | Treat as |
|--------|-------|----------|
| Pass | `>= 0.80` | Correct |
| Partial | `0.40`–`0.79` | Partial |
| Fail | `< 0.40` | Incorrect |

Primary metric is **mean `answer_correctness`**. Targets: `> 0.70` after Phase 4, `> 0.80` after Phase 6, zero critical overfitting, zero regressions (a Pass must not become a Fail).

## Resume

If `<WORKSPACE_DIR>/state.json` exists, read it first and continue from `current_phase`. Do not restart completed phases.

Default `<WORKSPACE_DIR>` to `./agent-optimize-<AGENT_NAME>` unless the user names one.

---

## Phase 1: Discovery

**Goal:** Identify the working agent, snapshot the spec, initialize the workspace.

1. Call `get_page_context` silently if available (see parent). Otherwise ask for `DATABASE.SCHEMA.AGENT_NAME`. If only a name is given:
   ```sql
   SHOW AGENTS LIKE '%<AGENT_NAME>%' IN ACCOUNT;
   ```
2. Ask whether this agent is **in production**. If yes, do not edit it in place:
   - Ask for a clone FQN (suggest `<DATABASE>.<SCHEMA>.<AGENT_NAME>_OPT`).
   - Snapshot, then deploy the clone (commands below). All later phases use `<WORKING_FQN>` = clone.
   - If not production, `<WORKING_FQN>` = the original.
3. Snapshot:
   ```bash
   cortex agent-studio agent-read --fqn <SOURCE_FQN>
   ```
   Write the YAML to `/tmp/agent_spec.yaml`, then:
   ```bash
   cortex agent-studio agent-write --yaml-content "$(cat /tmp/agent_spec.yaml)" --source-object <WORKING_FQN>
   ```
   For a clone, also deploy (this creates the object):
   ```bash
   cortex agent-studio agent-deploy --file-path <CLONE_AGENT_NAME>.agent.yaml --fqn <WORKING_FQN>
   ```
4. Present: purpose (from instructions), instruction character counts (`response` / `orchestration` / `system`), tool names and types. Ask about known issues.
5. Create `<WORKSPACE_DIR>`, then write `state.json` and `optimization_log.md` (templates in [references/workspace.md](references/workspace.md)).

**Gate:** User confirms agent identity and workspace.
**State:** `1_discovery → passed`. Record `source_fqn`, `working_fqn`, `clone_fqn`.

---

## Phase 2: Dataset

**Goal:** A registered native eval dataset (about 15–20 diverse questions).

1. Ask whether a **registered** evaluation dataset already exists (`DATABASE.SCHEMA.DATASET_NAME`).
2. **If yes:** confirm the name (`SHOW DATASETS LIKE '<NAME>' IN SCHEMA <DB>.<SCHEMA>;`). Infer `<METRIC_SCOPE>` from the source table (`tea` / `both` if any row has `ground_truth_invocations`; else `ac`) or ask. Record `<DATASET_NAME>` and `<SOURCE_TABLE>` if known.
3. **If no:** load [`../dataset/SKILL.md`](../dataset/SKILL.md). When it finishes table work, **skip its Step 3 optional eval** — Phase 3 owns baseline. Capture `<AGENT_FQN>`, `<DATASET_NAME>`, `<SOURCE_TABLE>`, `<METRIC_SCOPE>`.
4. Spot-check coverage: tool-routing questions (~25%), diversity, specific expected answers. If thin, offer `dataset-expand` before continuing.

**Gate:** User confirms the dataset is good enough to baseline.
**State:** `2_dataset → passed`. Record `dataset_name`, `metric_scope`, `eval_source`.

---

## Phase 3: Baseline

**Goal:** Measure current accuracy and group failures by root cause.

**Load:** [references/eval-results.md](references/eval-results.md), [references/failure-analysis.md](references/failure-analysis.md), [references/best-practices.md](references/best-practices.md).

1. Load [`../eval/SKILL.md`](../eval/SKILL.md) in **called-from-parent** mode:

   | Input | Value |
   |-------|-------|
   | `<AGENT_FQN>` | `<WORKING_FQN>` |
   | `<AGENT_VERSION>` | `LIVE` |
   | `<DATASET_NAME>` | from Phase 2 |
   | `<METRIC_SCOPE>` | from Phase 2 |
   | `<RUN_NAME>` | `opt_baseline_<YYYYMMDD_HHMMSS>` |

2. When eval returns, poll to `COMPLETED` and pull per-record scores (eval-results.md). Do **not** load `monitor/SKILL.md` (it stops for exploratory ASKs).
3. Present mean AC / LC (and TSA / TEA if in scope) plus Pass / Partial / Fail counts.
4. Analyze each Fail and Partial. Discover patterns from the data — do not force preset buckets. Split **Category A** (agent instructions) vs **Category B** (semantic view / generated SQL).
5. Recommend a fix order.

**Gate:** User confirms the categorization and priorities.
**State:** `3_baseline → passed`. Record `runs.baseline` and `agent_versions.baseline`.

---

## Phase 4: Instruction improvements

**Goal:** Fix Category A patterns in instructions; hand off Category B.

**Load:** [references/failure-analysis.md](references/failure-analysis.md), [references/improvement-examples.md](references/improvement-examples.md).

1. **Category B:** For each semantic-view failure, either load `../../semantic-view/SKILL.md` (same team) or write a short handoff (view FQN, question, expected vs actual SQL, suggested fix) and pause until those fixes land.
2. **Category A:** For each pattern, draft a specific instruction section, show how it handles the failed questions, and iterate wording with the user. Do not apply the first draft.
3. After the user approves the combined instructions, apply them with [Apply instruction edit](#apply-instruction-edit). Record the new `VERSION$N` from `SHOW VERSIONS`.
4. Re-eval — same dataset and `<METRIC_SCOPE>`, `<RUN_NAME>` = `opt_after_improvements_<YYYYMMDD_HHMMSS>`, `<AGENT_VERSION>` = the version just saved (not `DEFAULT`, so a prod original is not required to publish mid-loop).
5. Compare vs baseline (eval-results.md). List fixes, regressions, remaining failures.
6. If mean AC `< 0.70`, analyze remaining failures and repeat this phase.

**Gate:** User approves the instruction changes before the apply step, and reviews the comparison before leaving the phase.
**State:** `4_improvements → passed`. Record `runs.after_improvements` and `agent_versions.after_improvements`.

---

## Phase 5: Overfitting

**Goal:** Find instruction text that will fail off the eval set.

**Load:** [references/overfitting.md](references/overfitting.md).

1. Read the current working spec (`agent-read --fqn <WORKING_FQN>`).
2. Flag eval-specific dates, entity names, numeric thresholds, fixed result counts, and absolute ranges. For each issue: production risk + suggested generalization. Priority: Critical / Medium / Low.
3. Present the list. Do not ask whether an issue "is overfitting" — explain the risk and ask which ones to fix.

**Gate:** User confirms which issues to generalize.
**State:** `5_overfitting → passed`.

---

## Phase 6: Generalize and validate

**Goal:** Production-ready instructions; confirm no regressions.

**Load:** [references/overfitting.md](references/overfitting.md), [references/workspace.md](references/workspace.md).

1. For each approved issue, show before → after with rationale. Present the full generalized instructions.
2. Apply with [Apply instruction edit](#apply-instruction-edit). Record the new version.
3. Final eval: `<RUN_NAME>` = `opt_generalized_<YYYYMMDD_HHMMSS>`, `<AGENT_VERSION>` = the generalized version, same dataset.
4. Three-way comparison: baseline → after improvements → generalized. Generalization must not turn a prior Pass into a Fail. If it does, tighten the wording and re-eval.
5. Write `DEPLOYMENT_SUMMARY.md` (template in workspace.md). Walk the success checklist with the user.
6. If work was on a clone and the user wants it on the original: `agent-read` the clone, `agent-write` / `agent-save` to `<SOURCE_FQN>`, then `agent-publish` only after an explicit yes.

**Gate:** User approves production deployment (and any clone → original publish).
**State:** `6_generalization → passed`.

---

## Apply instruction edit

Use this for Phase 4 and Phase 6. Do **not** load `../edit/SKILL.md` (comment review and test handoff break the loop).

1. `cortex agent-studio agent-read --fqn <WORKING_FQN>` — keep the **complete** YAML.
2. Change only `instructions.*`. Never drop `tools`, `tool_resources`, `mcp_servers`, `skills`, `models`, `orchestration`, or `experimental`.
3. Confirm the diff with the user. Wait for an explicit yes.
4. Write via a temp file (same pattern as `edit/SKILL.md`):
   ```bash
   cat > /tmp/agent_spec.yaml << 'YAML_EOF'
   <COMPLETE_MODIFIED_YAML>
   YAML_EOF
   cortex agent-studio agent-write --yaml-content "$(cat /tmp/agent_spec.yaml)" --source-object <WORKING_FQN>
   cortex agent-studio agent-save --file-path <AGENT_NAME>.agent.yaml --fqn <WORKING_FQN>
   ```
5. Re-read the live spec. If `tools` is missing or the tool names changed, **stop** — do not re-eval. Restore from the last good `agent-read` and retry.
6. Record the new version:
   ```sql
   SHOW VERSIONS IN AGENT <WORKING_FQN>;
   ```
   Use that `VERSION$N` as `<AGENT_VERSION>` on the next eval. Do not `agent-publish` during the loop.

---

## Running an eval from this skill

Always load `../eval/SKILL.md` in called-from-parent mode with the table in Phase 3. After it returns `<RUN_NAME>` and the Snowsight URL, stay here: poll and score with [references/eval-results.md](references/eval-results.md).

Keep the same `<DATASET_NAME>` and `<METRIC_SCOPE>` for baseline, after-improvements, and generalized runs so comparisons are valid.

---

## References

| File | When |
|------|------|
| [references/eval-results.md](references/eval-results.md) | Poll, per-record scores, comparison tables |
| [references/failure-analysis.md](references/failure-analysis.md) | Phases 3–4 |
| [references/improvement-examples.md](references/improvement-examples.md) | Phase 4 |
| [references/overfitting.md](references/overfitting.md) | Phases 5–6 |
| [references/best-practices.md](references/best-practices.md) | All phases |
| [references/workspace.md](references/workspace.md) | `state.json`, log, deployment summary |
