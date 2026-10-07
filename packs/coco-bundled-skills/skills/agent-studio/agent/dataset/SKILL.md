---
name: agent-studio-agent-dataset
description: "Create and manage evaluation datasets for Cortex Agents. Use when user wants to: create eval dataset, build evaluation data, curate dataset, add questions to dataset, create dataset from production data, make test questions for agent, evaluation dataset, ground truth data, prepare evaluation questions."
parent_skill: agent-studio-agent
---

# Dataset Curation for Cortex Agent Evaluation

Create and manage evaluation datasets for Cortex Agents. Use with the sibling `eval/SKILL.md` skill to score the registered dataset.

> Tool usage: see parent `agent/SKILL.md`. Additional:
> - **REQUIRED:** `snowflake_sql_execute` for table creation, data insertion, dataset registration, and observability queries
> - **REQUIRED:** `cortex agent-studio agent-read` for reading agent configuration (tools, instructions, persona)
> - **FORBIDDEN:** `DESC AGENT` or `DESCRIBE AGENT` SQL for spec extraction — use `agent-read` instead

## Output rules

**ONLY PRINT to the user what is explicitly marked as `Print to user:` in the sub-skill steps.** Do NOT print step numbers (e.g. "Step 1", "Step 3.4"), step titles, internal procedure details, SQL queries, JSON schemas, technical variable names (e.g. `<METRIC_SCOPE>`, `<AC_COUNT>`, `<TEA_COUNT>`, `<METHODOLOGY>`, `<batch_start>`, `record_id`), or implementation logic to the user. **NEVER show internal step numbers or variable names to the user — they are for internal navigation only.** The user should only see: concise status messages, selection prompts, confirmation tables, and final results.

**Selection prompts MUST always include ALL options exactly as written in the sub-skill** — including the "Can you provide me more details?" / "What do these mean?" option. Never drop or abbreviate any option from the prompt. Every selection presented to the user must be complete, regardless of whether the skill is running in `standalone` or `build-only` mode.

## Prerequisites

- Snowflake connection with permission to create tables in the target schema
- For production workflows: access to AI Observability events for the agent

## Dataset Format

Snowflake Agent Evaluations require an `INPUT_QUERY` (`VARCHAR`) + `GROUND_TRUTH` (`VARIANT`) source-table shape. The `GROUND_TRUTH` VARIANT carries a JSON object whose `ground_truth_invocations` field can be **populated** (TEA-track), **`[]`** (TEA-track no-tool guardrail), or **absent** (AC-track) — the three states drive which metrics score each row.

Canonical schema rules — column types, the `TO_VARIANT(OBJECT_CONSTRUCT(...))` build pattern, AC/TEA/`[]` row examples, element-level rules (`tool_name`, `tool_type`, `tool_input` / `tool_output`), the trichotomy, field-absent evaluation semantics, and sanity-check SQL — live in [`refs/ground_truth_schema.md`](refs/ground_truth_schema.md). **Do not duplicate those rules in this file or in sub-skill bodies — link out.**

### Tool-type scope declaration (MANDATORY first step)

Before authoring any ground-truth invocations, the agent **must declare** which tool-type category each of the agent's registered tools falls into. This selects the right authoring template, context-gathering query, and TEA judge prompt.

#### The four categories

| Category | Maps to `tool_type` | Tools fall here when … |
|----------|---------------------|-------------------------|
| **SQL** (text-to-SQL / Cortex Analyst) | `cortex_analyst_text_to_sql`, `system_execute_sql` | The tool is a Cortex Analyst service, a semantic-model-backed text-to-SQL endpoint, or a tool that runs SQL the model wrote. |
| **Search** (Cortex Search / Web Search) | `cortex_search`, `web_search` | The tool is a Cortex Search Service over a corpus, or web_search. Note: `tool_name` for web search is always the literal `"web_search"`. |
| **Custom** (generic procedure / function) | `generic` | Any user-defined Snowflake stored procedure, UDF, external function, or HTTP/REST tool registered with the agent. |
| **Mixed** | combination of SQL / Search / Custom | The agent has tools spanning two or more of the above categories. |

#### How to determine the scope

Infer from `agent-read` output (or ask the user) which category their agent's tools fall into. Declare the scope explicitly in the response before authoring ground truth. The declaration block looks like:

```
Tool-type scope: Mixed
- revenue_lookup        → SQL    (cortex_analyst_text_to_sql)
- customer_search       → Search (cortex_search)
- industry_news_search  → Search (web_search)
- order_tracker         → Custom (generic procedure)
```

This declaration is **required output** and is verified by the eval suite — the dataset must subsequently contain at least one ground-truth invocation matching each declared category. If, after inspection, **every** discovered tool maps to a single category (e.g. all `cortex_analyst_text_to_sql`), record that single category instead of `Mixed`; the coverage requirement degenerates to one category in that case.

#### Coverage requirement

When scope is **Mixed**, the final dataset must include at least one ground-truth invocation per declared category. The eval suite checks this with per-category procedure-label assertions (`SQL:`, `Search Query:`, `Procedure Call:`, plus `tool_name="web_search"` when applicable).

### TEA-aligned authoring rules

Detailed authoring rules for `ground_truth_invocations` — schema, two-part `tool_output` format (Procedure label + `Expected Result:`), `tool_input` rules per `tool_type`, SQL ground-truth requirements (runnable SQL + executed result, no `Verify …` paraphrases), and the TEA quality checklist — live in [`refs/tea_details.md` § TEA-track authoring](refs/tea_details.md#tea-track-authoring); concrete JSON examples are in [`refs/tea_details.md` § TEA INSERT template (scratch)](refs/tea_details.md#tea-insert-template-scratch). Sub-skills deep-link to that ref where they reach the authoring step — do not re-state the rules in the sub-skill body.

### Registration rule (parent-owned)

**Confirm the registered dataset name with the user before calling `SYSTEM$CREATE_EVALUATION_DATASET`.** Every sub-skill must propose a full `<database>.<schema>.<dataset_name>` (with the `YYYYMMDD_HHMMSS` suffix) and STOP for the user to confirm or rename before running the registration SQL. Applies to first-time registration (`scratch` Step 5, `production` Step 7) and re-registration (`expand` Step 5). All three sub-skills produce a `<DATASET_NAME>` the parent picks up in **Workflow → Step 2** for the optional eval step.

---

## Where details live (refs/)

The three sub-skills (`dataset-scratch` / `dataset-production` / `dataset-expand`) keep their bodies **compact** — only the mandatory STOPs, user-facing prompts, step orchestration, and the high-level "what does this step do" framing live in each `SKILL.md`. All **procedural details, SQL templates, quality checklists, worked examples, and decision matrices** live in shared reference files under [`refs/`](refs/). The sub-skills link to refs when they reach the detail; the refs do not orchestrate or STOP, they just supply the content.

| Ref file | Owns |
|---|---|
| [`refs/ground_truth_schema.md`](refs/ground_truth_schema.md) | Canonical `GROUND_TRUTH` VARIANT shape; the `ground_truth_invocations` trichotomy (populated vs `[]` vs absent); field-absent semantics for evaluation; sanity-check SQL patterns. **One canonical statement of the schema rules — do NOT duplicate in skill bodies.** |
| [`refs/ac_details.md`](refs/ac_details.md) | AC-track authoring **style guide** — track definition, category guidance, the universal AC ground-truth rule (forbidden / required content), Expected-answer Good/Bad table, AC quality checklist, AC INSERT example (scratch Step 4). Step-executable SQL (annotation DDL, `UPDATE`, projection) lives inline in the calling skill. |
| [`refs/tea_details.md`](refs/tea_details.md) | TEA-track authoring **style guide** — track definition, category + tool-type guidance, `ground_truth_invocations` schema, two-part `tool_output` format, SQL ground-truth requirements, TEA quality checklist, TEA INSERT template with worked examples (scratch Step 4), trace projection from agent invocations (methodology #2). Step-executable SQL (annotation DDL, `UPDATE`, staging fix-up) lives inline in the calling skill. |
| [`refs/subagents.md`](refs/subagents.md) | Methodology choice (`<METHODOLOGY>` = have the agent generate ground truth vs. invoke the user's agent) and the bounded parallel-invocation playbook (Python `ThreadPoolExecutor`). Used by `dataset-scratch` (and transitively by `dataset-expand`'s `build-only` sub-call); does NOT apply to `dataset-production`. |

Mandatory user-facing STOPs and ASK prompts **always** live in the sub-skill body. The refs supply the *content* of each prompt's branches (decision criteria, budget numbers, SQL templates), not the prompts themselves.

## Routing

> Print to user (when the skill is first loaded and the user hasn't specified a clear sub-skill):
> ```
> Cortex Agent evaluations let you test your agent's quality before rolling it out to users. Snowflake uses the GPA framework to evaluate your agent — its thinking process across the goals it defines, the plans it makes, and the actions it takes to achieve those goals. This is done using 4 metrics: tool selection accuracy (goal to plan), tool execution accuracy (plan to action), answer correctness (action to goal), and logical consistency (wholistic across the GPA thinking cycle).
>
> I can help you build a golden dataset based on your agent's configuration — a set of test questions with verified expected answers that you can run against your agent to measure its performance.
>
> Here's how I can help create an evaluation dataset for you:
> • Design the dataset from scratch — I'll analyze your agent's tools, write test questions covering different scenarios, and generate expected answers. Best for new agents or when you want targeted coverage.
> • Build the dataset from production data — I'll scan your agent's real usage logs, find representative questions users actually asked, and build expected answers from observed behavior. Best when your agent has been running in production.
> • Expand existing dataset — I'll add new questions to a dataset you've already built, filling coverage gaps. Best when you have a dataset but want broader test coverage.
>
> Which would you like to do?
> A) Design the dataset from scratch
> B) Build the dataset from production data
> C) Expand an existing dataset
> ```

**STOP** and wait for the user's answer. Do not guess.

## Workflow (parent owns: route → sub-skill → eval)

The parent skill orchestrates the full dataset lifecycle in three steps. The three sub-skills (`dataset-scratch` / `dataset-production` / `dataset-expand`) handle only their respective table work — building, expanding the writable source table — and **return control to this skill** when their table is registered (or, for expand, re-registered). Running the optional evaluation is **owned by this parent skill only**. Do **not** run an evaluation from inside another sub-skill — it happens here in Step 3.

### Step 1: Route to the right sub-skill

1. If the user's message clearly signals a sub-skill (e.g. "from production", "from scratch", "expand my dataset"), route directly without asking.
2. Otherwise, print the intro + A/B/C prompt from the Routing section above and **STOP**.

| User choice | Sub-skill to load |
|-------------|-------------------|
| A) Design from scratch | [`dataset-scratch/SKILL.md`](dataset-scratch/SKILL.md) |
| B) Build from production | [`dataset-production/SKILL.md`](dataset-production/SKILL.md) |
| C) Expand existing | [`dataset-expand/SKILL.md`](dataset-expand/SKILL.md) |

Record `<SUB_SKILL>` ∈ {`scratch`, `production`, `expand`} and continue.

### Step 2: Run the chosen sub-skill end-to-end

Load the corresponding sub-skill file and follow it step-by-step to completion. Each sub-skill is self-contained for **table work only** — it builds (or merges) and then registers (or re-registers) a single merged source table. No sub-skill runs an evaluation itself.

When the sub-skill returns control, capture this state for the rest of the workflow:

| Variable | Value source |
|----------|--------------|
| `<AGENT_FQN>` | `<DATABASE>.<SCHEMA>.<AGENT_NAME>` — from the sub-skill's Step 1 (scratch / production) or Step 1 (expand, captured as Agent FQN) |
| `<SOURCE_TABLE>` | FQN of the writable source table that backs the dataset (scratch / production → `EVAL_DATASET_<AGENT_NAME>_<YYYYMMDD_HHMMSS>`; expand → the existing source table merged in Step 4) |
| `<DATASET_NAME>` | The registered dataset name from the sub-skill's registration step — scratch Step 5, production Step 7, expand Step 5 (re-register). **All three sub-skills produce a `<DATASET_NAME>`** — there is no on-the-fly registration branch. |
| `<METRIC_SCOPE>` | One of `ac` / `tea` / `both`, captured by the sub-skill: scratch Step 1.1, production Step 1.1; for expand, the invoked sub-skill's Step 1.1. |

Then continue to Step 3.

### Step 3: Run Evaluation Now? (optional)

ASK the user:

```
The dataset `<DATASET_NAME>` is ready. Do you want to run an evaluation against it right now?

Metrics that will run (driven by `<METRIC_SCOPE>` captured in Step 2):
- ac    → answer_correctness, logical_consistency
- tea   → answer_correctness, logical_consistency, tool_selection_accuracy, tool_execution_accuracy
- both  → answer_correctness, logical_consistency, tool_selection_accuracy, tool_execution_accuracy

Reply:
  Y / yes   → kick off the evaluation now
  N / no    → skip the eval; we're done
```

**STOP** and wait.

#### Step 3.1 — If the user says no

End the workflow. Surface a short summary:

- `<SOURCE_TABLE>` — the writable source table
- `<DATASET_NAME>` — the registered evaluation dataset (most recent version, after any expand re-register that ran)

The user can always run the sibling `eval/SKILL.md` skill later against `<DATASET_NAME>`.

**This workflow is complete. STOP.**

#### Step 3.2 — If the user says yes — invoke the sibling `eval` skill

Load [`../eval/SKILL.md`](../eval/SKILL.md) in **called-from-parent mode** and pre-fill all of the following so the sibling does **not** re-ASK the user:

| `eval` input | Value to pass |
|--------------|---------------|
| `<AGENT_FQN>` | `<AGENT_FQN>` captured in Step 2 |
| `<DATASET_NAME>` | `<DATASET_NAME>` captured in Step 2 — the dataset is already registered by the sub-skill, so the `eval` skill references it directly via `evaluation.dataset_fqn` (no top-level `dataset:` block, no read of the underlying source table). |
| `<METRIC_SCOPE>` | `<METRIC_SCOPE>` captured in Step 2 (one of `ac` / `tea` / `both`). The `eval` skill maps this to the metric list deterministically — do not pass a metric list. |
| `<RUN_NAME>` | `<agent_name>_eval_<YYYYMMDD_HHMMSS>`. |

Do **not** pass `<SOURCE_TABLE>` to the `eval` skill — it does not accept it and reads only the registered dataset object. If you need a per-record results table named after `<SOURCE_TABLE>`, materialize it on this side after the sub-skill returns.

The `eval` skill owns the eval cycle from here:

- Resolves the built-in metric list from `<METRIC_SCOPE>`, then pauses to ask whether the user wants to add a custom metric (one STOP).
- Uses the pre-filled `<DATASET_NAME>` and skips its dataset prompt.
- Builds and uploads the YAML, kicks off `EXECUTE_AI_EVALUATION` with `<RUN_NAME>`.
- Surfaces `<SNOWSIGHT_URL>` and returns control.

When the `eval` skill returns control, surface a short summary to the user:

| Variable | Value source |
|----------|--------------|
| `<RUN_NAME>` | The eval run that just completed. |
| `<SNOWSIGHT_URL>` | The Snowsight evaluation URL printed by the `eval` skill. |

**This workflow is complete. STOP.**

---

## Reference: Best practices

### Question design

**Do:** realistic phrasing, variations, boundary and negative cases, tool-routing scenarios.
**Don't:** overly formal-only wording, all-easy questions, skipping edge cases.

### Expected answers

**Do:** specific numbers and formatting, context (e.g. period), define "close enough."
**Don't:** vague expectations, exact match on long prose, ignore date-format differences.

### Maintenance

- Version registered dataset names with a **`YYYYMMDD_HHMMSS`** suffix
- Document changes between versions; keep the source table and re-register after edits

---

## Troubleshooting

| Symptom | What to do |
|---------|------------|
| `Insufficient privileges to operate on dataset` | **→ Route to `../permission/SKILL.md`** |
| `Insufficient privileges on database` | **→ Route to `../permission/SKILL.md`** |
| `Insufficient privileges on agent` | **→ Route to `../permission/SKILL.md`** |
| `Insufficient privileges on usage` | **→ Route to `../permission/SKILL.md`** |
| `GROUND_TRUTH` type mismatch | Column must be `VARIANT` (not `OBJECT` or `VARCHAR`). Build values with `TO_VARIANT(OBJECT_CONSTRUCT(...))`, `OBJECT_CONSTRUCT(...)::VARIANT`, or `PARSE_JSON()` — not bare `OBJECT_CONSTRUCT()`. |
| `SQL compilation error` inserting with function calls in `VALUES` | Use `INSERT ... SELECT ... FROM VALUES` with the construction in the **SELECT** list |
| Dataset not found after registration | Confirm database/schema; `SHOW DATASETS IN SCHEMA <DB>.<SCHEMA>;` |
| `SYSTEM$CREATE_EVALUATION_DATASET` error | Column names in the table must match the mapping object exactly |
| `The DB is not set for the current session` on `SYSTEM$CREATE_EVALUATION_DATASET` | Run `USE DATABASE` / `USE SCHEMA` before the call |
| `Duplicate query_text` on registration | Duplicate `INPUT_QUERY` rows in the source table. Snowflake's `UNIQUE` constraint is informational only and does **not** prevent inserts, so dedupe explicitly: `DELETE FROM <SOURCE_TABLE> WHERE question_id IN (SELECT question_id FROM (SELECT question_id, ROW_NUMBER() OVER (PARTITION BY INPUT_QUERY ORDER BY question_id) AS rn FROM <SOURCE_TABLE>) WHERE rn > 1);` then re-register. Prefer dedupe-on-write (e.g. `MERGE` with `QUALIFY ROW_NUMBER() = 1` over staging) to avoid this in the first place. |
| Agent invocation returns HTTP 401 / 403 | The role needs: (1) `GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <role>;` (or `SNOWFLAKE.CORTEX_AGENT_USER`), AND (2) `GRANT USAGE ON DATABASE <db> TO ROLE <role>; GRANT USAGE ON SCHEMA <db>.<schema> TO ROLE <role>; GRANT USAGE ON AGENT <db>.<schema>.<agent> TO ROLE <role>;`.|
| TSA/TEA score is `0.0` with "Missing ground truth" | `ground_truth_invocations` field is absent from `GROUND_TRUTH`. Add `[]` for no-tool questions or a populated array for tool-using questions. |
| TSA score `0.0` with "Expected no tools but N invoked" | `ground_truth_invocations` is `[]` but the agent called tools. Either the question routing is wrong or the expected array is missing entries. |

---

## Integration

- **`test/SKILL.md`:** try questions interactively before locking into the dataset
- **`eval/SKILL.md`:** run evaluations against the registered dataset
