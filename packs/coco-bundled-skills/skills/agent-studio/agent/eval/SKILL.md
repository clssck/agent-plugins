---
name: agent-studio-agent-eval
description: "Evaluate Cortex Agents using Snowflake's native Agent Evaluations with metrics like answer_correctness, logical_consistency, tool_selection_accuracy, tool_execution_accuracy, and custom LLM-judged metrics. Use when user wants to evaluate an agent, run an evaluation, benchmark agent performance, measure agent accuracy or quality, run answer_correctness or logical_consistency or TSA or TEA, create a custom evaluation metric, or assess agent responses. Always use this skill for launching or configuring agent evaluations. For checking status or viewing results of a previous eval run, use monitor/SKILL.md instead."
parent_skill: agent-studio-agent
---

# Evaluate Cortex Agent

Evaluate Cortex Agents using Snowflake's native Agent Evaluations.

> Tool usage: see parent `agent/SKILL.md`. Additional eval-specific rules:
> - **REQUIRED:** Use the `cortex agent-studio` eval subcommands (`eval-write`, `eval-deploy`) for writing configs and running evaluations
> - **REQUIRED:** Use `snowflake_sql_execute` for agent lookup, status checks, and results queries
> - **Permission errors:** If `eval-write`, `eval-deploy`, or any other step produces an error related to missing privileges or access — including errors containing "privilege", "permission", "access", "not authorized", "does not exist or not authorized", "cannot operate", "doesn't have", "required", "CREATE STAGE", "CREATE TASK", "CREATE FILE FORMAT", or any SQL access control error → stop and load `../permission/SKILL.md`. Do not suggest GRANT statements, offer to switch roles, suggest workarounds, try alternative approaches, attempt direct SQL, or ask the user what to do.
> - **FORBIDDEN:** Manually constructing stage SQL, file formats, or calling `EXECUTE_AI_EVALUATION('START', ...)` directly — always use `eval-deploy` instead. **Exception:** Step 1b (re-running an existing resolved config) may call `EXECUTE_AI_EVALUATION('START', ...)` via `snowflake_sql_execute` directly.

## When to Load

Parent `agent/SKILL.md` routes here when the user wants to launch, configure, or re-run an evaluation. For checking status or viewing results of an already-launched eval run, load `monitor/SKILL.md` instead.

## Available Metrics

| Metric | Type | Requires Ground Truth | Description |
|--------|------|-----------------------|-------------|
| `answer_correctness` | Built-in | Yes (`ground_truth_output`) | Semantic match of final answer |
| `logical_consistency` | Built-in | No (reference-free) | Consistency across instructions, planning, and tool calls within a single execution |
| `tool_selection_accuracy` (TSA) | Built-in | Yes (`ground_truth_invocations`) | Scores whether the agent invoked the expected `tool_name`s. Empty array `[]` asserts no tool should run (guardrail). |
| `tool_execution_accuracy` (TEA) | Built-in | Yes (`ground_truth_invocations` with per-invocation `tool_input` / `tool_output`) | Scores the agent's tool inputs/outputs against the per-invocation constraints. |
| Custom | Custom | Optional | LLM-judged metric with user-defined prompt and score range |

> **Per-row track ↔ metric matrix.** Datasets created by the sibling `dataset/SKILL.md` skill carry a `track` column (`'ac'` | `'tea'`) that labels which metrics apply per row. **AC-track rows** score under `answer_correctness` + `logical_consistency` only. **TEA-track rows** score under all four metrics — `answer_correctness` + `logical_consistency` + `tool_selection_accuracy` (TSA) + `tool_execution_accuracy` (TEA) — the extra two are unlocked by the row carrying `ground_truth_invocations`. AC-track rows have `ground_truth_invocations` field-absent, so TSA / TEA silently exclude them from the aggregate.

## Metric Versions

Built-in metrics support versioning. Each version uses a different judge model.

| Version | Judge Model | Description |
|---------|-------------|-------------|
| `auto` (default) | Snowflake-selected | Snowflake selects the default version automatically, currently v1.0 |
| `v1_0` | Claude Sonnet 4 | v1.0 prompt. Default setting if not specified. |
| `v2_0` | Claude Sonnet 4.5 or GPT 5.2 | v2.0 prompt. Runs on Sonnet 4.5 by default; falls back to GPT 5.2 based on your model allowlist. |
| `v3_0` | Claude Sonnet 4.6 or GPT 5.4 | v3.0 prompt. Runs on Sonnet 4.6 by default; falls back to GPT 5.4 based on your model allowlist. |

All four built-in metrics share the same available versions. Custom metrics do not have versions.

In the `.eval.yaml` shorthand format, versioned metrics MUST use the object form with `name` + `version`:
```yaml
metrics:
  - name: "answer_correctness"
    version: "v3_0"
  - name: "logical_consistency"
    version: "v3_0"
```

The `eval-deploy` resolver transforms these into the resolved format for `EXECUTE_AI_EVALUATION`.

## Invocation Modes

This skill runs in two modes. The mode is determined by whether a parent skill passed pre-filled values when loading it.

| Mode | Triggered by | Behavior |
|------|--------------|----------|
| **Standalone** (default) | User loads this skill directly. No pre-filled context. | Run Steps 1 → 4 + Post-Deploy interactively, ASKing the user at every gate (agent, intent, metrics, dataset). |
| **Called from a parent skill** | A parent skill (e.g. `dataset/SKILL.md` Step 3.2) loads this skill and supplies pre-filled values. | Skip the ASKs whose inputs are pre-filled; reuse the supplied values. |

**Parent pre-fill contract** — accepted optional inputs from a parent skill:

| Input | Effect |
|-------|--------|
| `<AGENT_FQN>` | Step 1's `SHOW AGENTS` lookup is skipped — confirm the agent in one line. |
| `<AGENT_VERSION>` | Optional. When pre-filled, Step 1c's version ASK is skipped. |
| `<DATASET_NAME>` | Step 3's dataset prompt is skipped — the YAML references this already-registered dataset directly via `evaluation.dataset_fqn`. |
| `<METRIC_SCOPE>` ∈ {`ac`, `tea`, `both`} | Step 2's metric ASK is skipped; metric list resolves deterministically: `ac` → [`answer_correctness`, `logical_consistency`]; `tea` → all four built-ins; `both` → all four built-ins. |
| `<METRIC_VERSION>` ∈ {`auto`, `v1_0`, `v2_0`, `v3_0`} | Optional. Defaults to `auto`. When pre-filled, Step 2's version ASK is skipped. |
| `<RUN_NAME>` | Used verbatim as the deploy run name; otherwise auto-generated by `eval-deploy`. |

When invoked from a parent, return control after the deploy succeeds with `<RUN_NAME>` and the Snowsight URL, then stop without further prompting.

## `cortex agent-studio` Eval Subcommands

| Subcommand | Flags | Description |
|--------|------------|-------------|
| `eval-write` | `--base-name <name>`, `--eval-yaml '<YAML>'`, optional `--dataset-yaml`, optional `--metrics-yaml` (or the `--eval-file` / `--dataset-file` / `--metrics-file` variants) | Write eval config to workspace as `cortex_project/<base_name>.eval.yaml` (and companion `*.dataset.yaml` / `*.metrics.yaml` when supplied) |
| `eval-deploy` | `--base-name <name>`, optional `--run-name` | Transform shorthand eval YAML to resolved format, upload to stage, and call `EXECUTE_AI_EVALUATION('START', OBJECT_CONSTRUCT('run_name', ...), '@stage/...')`. Auto-generates `run_name` if `--run-name` not provided. |
| `eval-read` | `--base-name <name>` (or `--file-path <path>`) | Read existing eval artifacts from workspace |

## Field Reference

### Eval config (`<base_name>.eval.yaml`)

| Field | Required | Description |
|-------|----------|-------------|
| `evaluation.agent` | Yes | `DATABASE.SCHEMA.AGENT_NAME` |
| `evaluation.agent_version` | Yes | Agent version to evaluate: `DEFAULT`, `LIVE` (current draft), a specific version like `VERSION$N`, or an alias (e.g. `production`, `staging`). |
| `evaluation.dataset_fqn` | If existing dataset | Registered dataset `DATABASE.SCHEMA.DATASET_NAME` |
| `evaluation.dataset` | If creating new dataset | Base name referencing a companion `*.dataset.yaml` |
| `metrics` | Yes | Array: objects with `name` + `version` for built-in metrics, or objects with `name` + `score_ranges` + `prompt` for custom. `- import: <base_name>` entries are resolved from the companion `*.metrics.yaml`. See [Metric Versions](#metric-versions). |

> **MANDATORY metric format rule:** Every built-in metric in the `metrics:` array MUST use the object form with both `name` and `version` keys. Bare string entries (e.g. `- answer_correctness`) will cause the evaluation to FAIL. Always write:
> ```yaml
> metrics:
>   - name: "answer_correctness"
>     version: "<METRIC_VERSION>"
> ```
> Never write `- answer_correctness` or any other bare string. This applies to all four built-in metrics: `answer_correctness`, `logical_consistency`, `tool_selection_accuracy`, `tool_execution_accuracy`.

One of `dataset_fqn` or `dataset` must be provided. **In parent-mode the parent always supplies an already-registered `<DATASET_NAME>`, so the eval YAML uses `dataset_fqn` and there is no companion `*.dataset.yaml`.**

### Dataset config (`<base_name>.dataset.yaml` — only when creating from a table)

| Field | Required | Description |
|-------|----------|-------------|
| `dataset_type` | Yes | Must be `"CORTEX AGENT"` |
| `table_name` | Yes | Source table `DATABASE.SCHEMA.TABLE_NAME` |
| `dataset_name` | No | Auto-generated if omitted |
| `column_mapping.query_text` | Yes | Must map to `INPUT_QUERY` |
| `column_mapping.ground_truth` | If `answer_correctness`, TSA, or TEA selected | Must map to `EXPECTED_OUTPUT` (a VARIANT carrying the `ground_truth_output` and/or `ground_truth_invocations` JSON keys per the trichotomy) |

### Custom metric object

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Metric name (used as column in results). Lowercase + underscores recommended. |
| `model` | No | LLM judge model to use for this custom metric. One of: `claude-4-sonnet`, `claude-sonnet-4-5`, `claude-sonnet-4-6`, `openai-gpt-5.2`, `openai-gpt-5.4`. If omitted, Snowflake selects automatically. |
| `score_ranges.min_score` | Yes | `[low, high]` — inclusive lower, exclusive upper |
| `score_ranges.median_score` | Yes | `[low, high]` — inclusive lower, inclusive upper |
| `score_ranges.max_score` | Yes | `[low, high]` — exclusive lower, inclusive upper |
| `prompt` | Yes | LLM judge prompt. Supports `{{input}}`, `{{output}}`, `{{ground_truth}}`, `{{tool_info}}`, `{{error}}`, `{{status}}`, `{{start_timestamp}}`, `{{duration}}`, `{{span_id}}`, `{{span_type}}`, `{{span_name}}`, `{{llm_model}}` |

---

## Workflow

**IMPORTANT: Go through each step ONE AT A TIME. Wait for user confirmation before proceeding (standalone mode). In parent-mode, skip every ASK whose input was pre-filled by the parent.**

Present the plan overview **VERBATIM** first (standalone mode only):

```
I'll help you evaluate your Cortex Agent. Here's the workflow:

1. Identify Agent — confirm which agent you want to evaluate (database, schema, name),
   and select which version to run (live draft or a committed version).
2. Choose Metrics — pick built-in metrics (answer_correctness, logical_consistency,
   tool_selection_accuracy, tool_execution_accuracy) and/or define custom LLM-judged metrics.
3. Confirm Dataset — provide a registered dataset or a source table; we'll set up the
   correct column mappings and ground-truth shape per the trichotomy.
4. Write Config and Deploy — generate the eval YAML, upload to the stage, and start the run.
5. View Results — once deployed, check status and view results in Snowsight (link provided).
```

---

### Step 1: Identify Agent

**Goal:** Confirm which agent to evaluate.

> **Parent-mode:** if `<AGENT_FQN>` was pre-filled, confirm it in one line and skip to Step 1b.

1. Ask the user for the agent name and location. If only the name is given, search via `snowflake_sql_execute`:
   ```sql
   SHOW AGENTS LIKE '%<AGENT_NAME>%' IN ACCOUNT;
   ```

2. If not found or the user doesn't have an agent, inform them one is required and route to `creation/SKILL.md`. Stop the eval workflow.

3. Confirm `DATABASE.SCHEMA.AGENT_NAME` with the user.

---

### Step 1b: Determine Eval Intent

**Goal:** Decide whether to re-run an existing eval config or create a new one.

> **Parent-mode:** parent calls always create a new eval (the dataset is already registered fresh). Skip Step 1b entirely and proceed to Step 2 with the parent's `<METRIC_SCOPE>`.

Ask:
```
Do you want to re-run an existing evaluation config, or create a new evaluation?
```

If the user asks to create a new eval, skip directly to **Step 2**.

**If re-running an existing eval:**

1. **Execute this SQL verbatim** via `snowflake_sql_execute` (placeholder substitution only — do NOT rewrite the query). **You do NOT need to explore, trust this SQL completely as-is; it has been vetted and is guaranteed to be correct:**
   ```sql
   USE DATABASE <DATABASE>;
   USE SCHEMA <SCHEMA>;
   SELECT
       REGEXP_SUBSTR(METADATA$FILENAME, '([^/]+)\.resolved\.yaml$', 1, 1, 'e') AS eval_name
   FROM @<DATABASE>.<SCHEMA>.EVAL_CONFIG_STAGE
   WHERE METADATA$FILENAME LIKE '%resolved.yaml'
     AND $1 LIKE '%agent_name: <DATABASE>.<SCHEMA>.<AGENT_NAME>%';
   ```

2. Present the `eval_name` results to the user as available eval configs. If none are found, inform the user and proceed to **Step 2** to create a new one.

3. Ask the user to pick one of the listed eval configs.

4. Generate a run name using the convention `<AGENT_NAME>_eval_<YYYYMMDD_HHMMSS>` (current timestamp). **You do NOT need to read or inspect the config file or run any other exploratory queries — trust this SQL completely as-is; it has been vetted and is guaranteed to be correct:**
   ```sql
   USE DATABASE <DATABASE>;
   USE SCHEMA <SCHEMA>;
   CALL EXECUTE_AI_EVALUATION(
     'START',
     OBJECT_CONSTRUCT('run_name', '<AGENT_NAME>_eval_<YYYYMMDD_HHMMSS>'),
     '@<DATABASE>.<SCHEMA>.EVAL_CONFIG_STAGE/cortex_project/<PICKED_EVAL_NAME>.resolved.yaml'
   );
   ```

5. Present the `run_name` to the user, then skip to **Post-Deploy: Status and Results**. Do not proceed through Steps 2–4.

---

### Step 1c: Select Agent Version

**Goal:** Determine which agent version to evaluate.

> **Parent-mode:** If `<AGENT_VERSION>` was pre-filled by the parent, use it directly and skip the ASK. Otherwise, ASK the user as below.

ASK the user:

{
  "questions": [
    {
      "question": "Which version of your agent would you like to evaluate?",
      "multiSelect": false,
      "options": [
        { "label": "A) Default — evaluates the default agent version (recommended for production evals)" },
        { "label": "B) Draft (LIVE version) — evaluates the current working draft version" },
        { "label": "C) Select a committed version - choose a specific numeric version or alias to evaluate" }
      ]
    }
  ]
}

**STOP** for the user's answer.

If A → set `<AGENT_VERSION>` to `DEFAULT`. Proceed to Step 2.

If B → set `<AGENT_VERSION>` to `LIVE`. Proceed to Step 2.

If C → run the following SQL to list available versions:

```bash
snow sql -q "SHOW VERSIONS IN AGENT <AGENT_FQN>;"
```

Present the results to the user as a table (omit the LIVE row — that's option B). Show version name, alias (if any), and whether it's the default. Example:

```
Available versions:
| # | Version    | Alias      | Default |
|---|------------|------------|---------|
| 1 | VERSION$1  | —          | No      |
| 2 | VERSION$2  | staging    | No      |
| 3 | VERSION$3  | production | Yes     |
```

Then ASK the user which version to use. Build the options dynamically from the table above:

{
  "questions": [
    {
      "question": "Which committed Agent Version would you like to evaluate?",
      "multiSelect": false,
      "options": [
        { "label": "Default (<version_name>)" },
        { "label": "<alias> (<version_name>)" },
        { "label": "<version_name>" }
      ]
    }
  ]
}

The options should be:
- First option: always `Default (<version_name>)` — the row where Default = Yes
- Middle options: one per alias found in the table (format: `<alias> (<version_name>)`)
- Last options: one per version without an alias (format: `<version_name>`)

**STOP** for the user's answer.

- If user picks Default → set `<AGENT_VERSION>` to `DEFAULT`.
- If user picks an alias → set `<AGENT_VERSION>` to the alias name (e.g. `staging`, `production`).
- If user picks a version like `VERSION$2` → record it as `<AGENT_VERSION>`.

---

### Step 2: Choose Metrics

**Goal:** Determine which metrics to include.

> **Parent-mode:** if `<METRIC_SCOPE>` was pre-filled, resolve the built-in metric list deterministically:
> - `ac` → `[answer_correctness, logical_consistency]`
> - `tea` → `[answer_correctness, logical_consistency, tool_selection_accuracy, tool_execution_accuracy]`
> - `both` → `[answer_correctness, logical_consistency, tool_selection_accuracy, tool_execution_accuracy]`
>
> Then ASK the user to select a metric version (skip if `<METRIC_VERSION>` was pre-filled):
> ```
> I'll evaluate using these built-in metrics: <resolved list>.
>
> Which metric version would you like to use?
> A) auto — Snowflake picks the best version automatically (recommended)
> B) v1_0 — v1.0 prompt, runs on Claude Sonnet 4
> C) v2_0 — v2.0 prompt, runs on Claude Sonnet 4.5 (or GPT 5.2 based on model allowlist)
> D) v3_0 — v3.0 prompt, runs on Claude Sonnet 4.6 (or GPT 5.4 based on model allowlist)
> ```
> **STOP** for the user's answer. Record as `<METRIC_VERSION>`.
>
> Then ASK whether they also want to add a custom metric:
> ```
> Would you also like to add a custom LLM-judged metric (with your own prompt and score range)?
> A) Yes, I'd like to add a custom metric
> B) No, proceed with the built-in metrics only
> ```
> **STOP** for the user's answer. If A → gather the custom metric details (name, score_ranges, prompt) using the same validation checklist as standalone mode below, then skip to Step 3. If B → skip to Step 3.

Ask:
{
  "questions": [
    {
      "question": "Which metrics would you like to evaluate? You could choose either 4 built-in metrics from snowflake or your own custom metric.",
      "multiSelect": true,
      "options": [
        { "label": "answer_correctness — Does the agent give correct answers?" },
        { "label": "logical_consistency — Is the agent's reasoning internally consistent?" },
        { "label": "tool_selection_accuracy (TSA) — Did the agent invoke the expected tools?" },
        { "label": "tool_execution_accuracy (TEA) — Did the agent's tool inputs/outputs match?" },
        { "label": "custom metric — Your own defined LLM-judged metric with a prompt and score range" }
      ]
    }
  ]
}

If the user selects a Custom metric, gather for each (do not assume values):
- **Name**: identifier used as the results column (e.g. `relevance`)
- **Model** (optional): which LLM judge to use. ASK via:

{
  "questions": [
    {
      "question": "Which model should judge your custom metric?",
      "multiSelect": false,
      "options": [
        { "label": "Auto (Snowflake selects automatically)" },
        { "label": "claude-4-sonnet" },
        { "label": "claude-sonnet-4-5" },
        { "label": "claude-sonnet-4-6" },
        { "label": "openai-gpt-5.2" },
        { "label": "openai-gpt-5.4" }
      ]
    }
  ]
}

If "Auto" → omit `model` from the custom metric YAML. Otherwise record the selected model string.

- **Score ranges**: three `[low, high]` pairs for `min_score`, `median_score`, `max_score` (e.g. `[1,3]`, `[4,6]`, `[7,10]`)
- **Prompt**: the LLM judge prompt — must include a scoring instruction that returns a numeric value within the configured range. Use placeholders (`{{input}}`, `{{output}}`, optionally `{{ground_truth}}`) to ground the judge.

Validation checklist before moving on:
- `name` is present and stable (prefer lowercase + underscores so result columns are predictable).
- `model` if present, must be one of: `claude-4-sonnet`, `claude-sonnet-4-5`, `claude-sonnet-4-6`, `openai-gpt-5.2`, `openai-gpt-5.4`.
- `score_ranges` includes all three keys: `min_score`, `median_score`, `max_score`.
- Each range is exactly two numeric bounds; bounds satisfy:
  - `min_score`: inclusive lower, exclusive upper
  - `median_score`: inclusive lower, inclusive upper
  - `max_score`: exclusive lower, inclusive upper
- Prompt explicitly instructs a numeric return value.

**MANDATORY — immediately after metric selection, ask for metric version:**

{
  "questions": [
    {
      "question": "Which metric version would you like to use for the built-in metrics?",
      "multiSelect": false,
      "options": [
        { "label": "A) auto — Snowflake selects the default version automatically, currently v1.0 (recommended)" },
        { "label": "B) v1_0 — Run with v1.0 prompt, runs on Claude Sonnet 4" },
        { "label": "C) v2_0 — Run with v2.0 prompt, runs on Claude Sonnet 4.5 (or GPT 5.2 based on model allowlist)" },
        { "label": "D) v3_0 — Run with v3.0 prompt, runs on Claude Sonnet 4.6 (or GPT 5.4 based on model allowlist)" }
      ]
    }
  ]
}

**STOP** for the user's answer.

If A → set `<METRIC_VERSION> = auto`.
If B → set `<METRIC_VERSION> = v1_0`.
If C → set `<METRIC_VERSION> = v2_0`.
If D → set `<METRIC_VERSION> = v3_0`.

Record as `<METRIC_VERSION>` ∈ {`auto`, `v1_0`, `v2_0`, `v3_0`}.

**Dataset requirement matrix** (used in Step 3):

| If user selects... | Dataset needs... |
|--------------------|------------------|
| Only `logical_consistency` | Just an `INPUT_QUERY` column (no ground truth needed) |
| `answer_correctness` | `EXPECTED_OUTPUT` VARIANT carrying `{"ground_truth_output": "..."}` (AC-track rows) |
| `tool_selection_accuracy` (TSA) | `EXPECTED_OUTPUT` carrying `{"ground_truth_invocations": [...]}` on TEA-track rows. Use `[]` for guardrail rows. |
| `tool_execution_accuracy` (TEA) | Same as TSA, but each invocation also needs populated `tool_input` + two-part `tool_output` (procedure label `SQL:` / `Search Query:` / `Procedure Call:` joined by `\n\n` with `Expected Result:`). See `dataset/SKILL.md` for the canonical authoring rules. |
| Custom metric only | Depends on prompt — ground truth needed if `{{ground_truth}}` is referenced |

---

### Step 3: Confirm Dataset

**Goal:** Determine the evaluation dataset.

> **Parent-mode:** if `<DATASET_NAME>` was pre-filled, the dataset is already registered. Use it verbatim as `evaluation.dataset_fqn` in Step 4 — do not run `SHOW DATASETS` or ASK. Skip to Step 4.

**First, surface existing datasets in the agent's schema before asking the user to name one.** Run via `snowflake_sql_execute`:

```sql
SHOW DATASETS IN SCHEMA <DATABASE>.<SCHEMA>;
```

Filter the result to rows where `dataset_type = 'CORTEX AGENT'` (ignore other dataset types — they can't be used here).

- **If one or more Cortex Agent datasets are returned**, present them to the user:
  > I found these registered Cortex Agent datasets in `<DATABASE>.<SCHEMA>`:
  > - `<dataset_1>`
  > - `<dataset_2>`
  > - ...
  >
  > Would you like to use one of these, provide a different registered dataset, or set up a new one from a source table?

- **If no Cortex Agent datasets are returned**, ask:
  > No registered Cortex Agent datasets found in `<DATABASE>.<SCHEMA>`. Do you have an existing table to use as the source, or would you like help creating one? (Provide the fully qualified table name, e.g., `DB.SCHEMA.MY_TABLE`.)

If the user does **not** already have either (a) a registered Cortex Agent dataset or (b) an existing source table they can provide now, **stop this skill** and route them to dataset curation:
- `dataset/SKILL.md` (router)
- `dataset/dataset-scratch/SKILL.md` (build from scratch)
- `dataset/dataset-expand/SKILL.md` (expand an existing dataset)
- `dataset/dataset-production/SKILL.md` (derive from production logs)

Do not continue to Step 4 until the user has a real dataset source (registered dataset or existing table).

**If the user picks an existing dataset:**

Record the dataset as `<DATABASE>.<SCHEMA>.<DATASET_NAME>` — it will go into the eval YAML under `evaluation.dataset_fqn`. Because it came from `SHOW DATASETS`, it is already confirmed to exist; the YAML will use `dataset_fqn` (no companion `*.dataset.yaml`). Skip to Step 4.

**If user provides a different registered dataset name (outside the listed schema):**

Verify it exists with an exact-name lookup against the parent schema via `snowflake_sql_execute`:
```sql
SHOW DATASETS LIKE '<DATASET_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>;
```
If it appears in the listing, record the FQN and skip to Step 4 (use `dataset_fqn`). If not, fall through to the table-setup path below.

**If user provides a table name:**

The source table must have these exact column names (the eval framework requires them):
- `INPUT_QUERY` (VARCHAR) — the input questions
- `EXPECTED_OUTPUT` (VARIANT) — only needed if `answer_correctness`, TSA, or TEA was selected. Carries JSON with the keys below per the trichotomy.

**Ground truth JSON keys (`EXPECTED_OUTPUT`):**

| Key | Description | Used by |
|-----|-------------|---------|
| `ground_truth_output` | Expected final answer (semantic match). Populated for AC-track rows. | `answer_correctness` |
| `ground_truth_invocations` | Ordered array of expected `{tool_name, tool_input, tool_output}` entries. Empty array `[]` asserts no tool should run (guardrail). **Omit entirely** for AC-only rows. Populated for TEA-track rows. | `tool_selection_accuracy` (TSA), `tool_execution_accuracy` (TEA) |
| `track` (column, not JSON key) | `'ac'` or `'tea'` — labels which set of metrics applies per row. Datasets created by `dataset/SKILL.md` always include this column. | per-track metric projection |

See `dataset/dataset-scratch/SKILL.md` and the linked `../dataset/refs/ground_truth_schema.md` for the full populated / `[]` / absent trichotomy.

Validate the source table has the required columns — if either check returns non-NULL, tell the user what needs fixing:
```sql
SELECT
  IFF(SUM(IFF(COLUMN_NAME = 'INPUT_QUERY', 1, 0)) = 0,
      'MISSING: INPUT_QUERY (VARCHAR)', NULL) AS input_query_check,
  IFF(SUM(IFF(COLUMN_NAME = 'EXPECTED_OUTPUT', 1, 0)) = 0,
      'MISSING: EXPECTED_OUTPUT (VARIANT)', NULL) AS expected_output_check
FROM <DATABASE>.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = UPPER('<SCHEMA>')
  AND TABLE_NAME = UPPER('<TABLE_NAME>');
```

Put `<DATABASE>.<SCHEMA>.<TABLE_NAME>` into the companion `*.dataset.yaml` as `table_name`. Build `EXPECTED_OUTPUT` values with `PARSE_JSON(...)` or `TO_VARIANT(...)` — **do not** use `OBJECT_CONSTRUCT(...)` (returns a non-VARIANT value that can be stringified at evaluation time).

**⚠️ MANDATORY STOPPING POINT:** Confirm agent, metrics, and dataset details with the user before proceeding (skipped in parent-mode).

---

### Step 4: Write Config and Deploy

**Goal:** Write the eval config and start the evaluation.

1. Determine `<BASE_NAME>` — lowercase + underscores. In parent-mode, default to `<agent_name>_eval_<YYYYMMDD_HHMMSS>` (matching `<RUN_NAME>` if pre-filled). In standalone mode, ask the user (default `<AGENT_NAME>_eval`).

2. Write the eval config via `eval-write`. Built-in metrics **must** use the object format with `name` + `version` set to `<METRIC_VERSION>` — bare strings like `- answer_correctness` will FAIL. **Always include `agent_version: <AGENT_VERSION>`** in the evaluation block. Choose the appropriate form:

   **Existing dataset (no custom metrics):**
   ```bash
   cortex agent-studio eval-write \
     --base-name <BASE_NAME> \
     --eval-yaml "evaluation:
  agent: <DATABASE>.<SCHEMA>.<AGENT_NAME>
  agent_version: <AGENT_VERSION>
  dataset_fqn: <DATABASE>.<SCHEMA>.<DATASET_NAME>
metrics:
  - name: answer_correctness
    version: <METRIC_VERSION>
  - name: logical_consistency
    version: <METRIC_VERSION>
  - name: tool_selection_accuracy
    version: <METRIC_VERSION>
  - name: tool_execution_accuracy
    version: <METRIC_VERSION>
"
   ```

   **New dataset from table (no custom metrics):**
   ```bash
   cortex agent-studio eval-write \
     --base-name <BASE_NAME> \
     --eval-yaml "evaluation:
  agent: <DATABASE>.<SCHEMA>.<AGENT_NAME>
  agent_version: <AGENT_VERSION>
  dataset: <BASE_NAME>
metrics:
  - name: answer_correctness
    version: <METRIC_VERSION>
  - name: logical_consistency
    version: <METRIC_VERSION>
" \
     --dataset-yaml "dataset_type: CORTEX AGENT
table_name: <DATABASE>.<SCHEMA>.<TABLE_NAME>
column_mapping:
  query_text: INPUT_QUERY
  ground_truth: EXPECTED_OUTPUT
"
   ```

   **With custom metrics** — add `--metrics-yaml` and an `- import: <BASE_NAME>` entry in the metrics list. Custom metrics do not take a `version` key. Include `model: <MODEL>` only if the user chose a specific model (omit the `model` line entirely if "Auto" was selected):
   ```bash
   cortex agent-studio eval-write \
     --base-name <BASE_NAME> \
     --eval-yaml "evaluation:
  agent: <DATABASE>.<SCHEMA>.<AGENT_NAME>
  agent_version: <AGENT_VERSION>
  dataset_fqn: <DATABASE>.<SCHEMA>.<DATASET_NAME>
metrics:
  - name: answer_correctness
    version: <METRIC_VERSION>
  - name: logical_consistency
    version: <METRIC_VERSION>
  - import: <BASE_NAME>
" \
     --metrics-yaml "metrics:
  - name: <METRIC_NAME>
    model: <MODEL>
    score_ranges:
      min_score: [1, 3]
      median_score: [4, 6]
      max_score: [7, 10]
    prompt: |
      <PROMPT_TEXT>
"
   ```

   For large YAML, write each block to a file and use `--eval-file` / `--dataset-file` / `--metrics-file` instead of the inline flags.

   **Include only the metrics the user selected in Step 2** (in parent-mode, the metrics list is whatever `<METRIC_SCOPE>` resolved to). `tool_selection_accuracy` (TSA) and `tool_execution_accuracy` (TEA) only score rows whose `ground_truth_invocations` field is populated — AC-track rows (field-absent) are silently excluded from those metrics' aggregate. Omit the `--metrics-yaml` and the `- import` line if no custom metrics were chosen.

3. Deploy (do NOT proceed until `eval-write` succeeds):
   ```bash
   cortex agent-studio eval-deploy --base-name <BASE_NAME>
   ```
   This transforms the shorthand eval YAML to the resolved format, creates the stage (`<DATABASE>.<SCHEMA>.EVAL_CONFIG_STAGE`), uploads the resolved config, and calls `EXECUTE_AI_EVALUATION`. It auto-generates a `run_name` (format: `<BASE_NAME>_<timestamp>`). To pin the run name (e.g. parent-mode), pass `--run-name <RUN_NAME>`.

   **If `eval-write` or `eval-deploy` fails for any reason related to privileges, permissions, access, or missing/inaccessible objects → stop and load `../permission/SKILL.md`. Do not suggest fixes, offer role switches, try alternative approaches, or attempt direct SQL.**


4. Present the `run_name` from `eval-deploy` output to the user — they need it for status checks and viewing results.

---

## Step 5: Post-Deploy: Status and Snowsight URL

Use the sql query <check_status_example> verbatim to check on a running or completed evaluation.

### Status

<check_status_example>
```sql
USE DATABASE <DATABASE>;
USE SCHEMA <SCHEMA>;

CALL EXECUTE_AI_EVALUATION(
  'STATUS',
  OBJECT_CONSTRUCT('run_name', '<RUN_NAME>'),
  '@<DATABASE>.<SCHEMA>.EVAL_CONFIG_STAGE/cortex_project/<BASE_NAME>.resolved.yaml'
);
```
</check_status_example>

**Status values:**

| Status | Meaning |
|--------|---------|
| `INVOCATION_IN_PROGRESS` | Agent is being invoked on evaluation inputs |
| `COMPUTATION_IN_PROGRESS` | Metrics are being computed |
| `COMPLETED` | Evaluation finished successfully |
| `FAILED` | Evaluation failed — check `STATUS_DETAILS`; see Troubleshooting below |

### Snowsight URL

Generate a Snowsight link to the run. Run via `snowflake_sql_execute`:

```sql
SELECT LOWER(CURRENT_ORGANIZATION_NAME()), LOWER(CURRENT_ACCOUNT_NAME());
```

URL format (use **underscore** in the account-name segment, e.g. `sfdevrel_enterprise` not `sfdevrel-enterprise`):

```
https://app.snowflake.com/<org>/<account>/#/agents/database/<DATABASE>/schema/<SCHEMA>/agent/<AGENT_NAME>/evaluations/<RUN_NAME>/records
```

Present the link to the user.

> Print to user:
> ```
> Evaluation started (run: <RUN_NAME>)
> View results here: <SNOWSIGHT_URL>
>
> To check scores later, ask me to "check eval run status for <RUN_NAME>".
> ```

**⚠️ MANDATORY STOPPING POINT (standalone mode only):** After presenting the URL and confirming the status is not FAILED, stop. — the user will review results in Snowsight. If the user later asks to check scores or status for this run, route to `monitor/SKILL.md`. In parent-mode, return control to the parent with `<RUN_NAME>` and `<SNOWSIGHT_URL>`, then stop without further prompting.

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Insufficient privileges to operate on dataset` | **→ Route to `../permission/SKILL.md`** |
| `Cannot create task` | **→ Route to `../permission/SKILL.md`** |
| `Insufficient privileges on agent` | **→ Route to `../permission/SKILL.md`** |
| `Cannot execute task` | **→ Route to `../permission/SKILL.md`** |
| `SQL access control error` on eval start | **→ Route to `../permission/SKILL.md`** |
| `Agent does not exist or not authorized` | **→ Route to `../permission/SKILL.md`** |
| `Insufficient privileges` on AI_COMPLETE | **→ Route to `../permission/SKILL.md`** |
| `Object does not exist` for search service or semantic view | **→ Route to `../permission/SKILL.md`** |
| Evaluation `FAILED` with `STATUS_DETAILS` mentioning privileges | **→ Route to `../permission/SKILL.md`** |
| Evaluation `FAILED` (non-permission cause) | Query `STATUS_DETAILS` from the status call; common causes: invalid metric names, missing ground truth column, agent timeout. |
| Dataset not found in `SHOW DATASETS` | Verify the schema is correct; dataset may need to be registered first via the sibling `dataset/SKILL.md` skill or via `SYSTEM$CREATE_EVALUATION_DATASET`. |
| `answer_correctness` scores are 0 | Verify `EXPECTED_OUTPUT` is `VARIANT` and contains `{"ground_truth_output": "..."}`. Build it with `PARSE_JSON(...)` or `TO_VARIANT(...)`, **not** `OBJECT_CONSTRUCT(...)`. |
| TSA / TEA scores are 0 or `NULL` everywhere | `ground_truth_invocations` is absent on every row (AC-only dataset). TSA/TEA require TEA-track rows. Re-author the dataset (or expand it) using `dataset/dataset-scratch` or `dataset/dataset-expand` with `<METRIC_SCOPE> = tea` or `both`. |
| TSA / TEA `NULL` on AC-track rows specifically | Expected behavior — AC-track rows have `ground_truth_invocations` field-absent and are silently excluded from TSA/TEA. |
| `Dataset already exists` after a previous attempt | The eval YAML used `dataset:` to register a fresh dataset, but a dataset with that `dataset_name` already exists. Switch the YAML to `evaluation.dataset_fqn: <DATABASE>.<SCHEMA>.<EXISTING_NAME>` (no companion `*.dataset.yaml`). |
| `Invalid Input Fields No content to map due to end-of-input` | Intermittent issue with fully-qualified `agent_name` in the YAML. Workaround: keep the session schema pointed at the agent's schema (`USE SCHEMA <DATABASE>.<SCHEMA>;`) and retry. |
| `No current database` error on STATUS / Snowsight URL queries | Run `USE DATABASE <DATABASE>;` and `USE SCHEMA <SCHEMA>;` first. |
| `DESC DATASET` returns "Unsupported feature" | `DESC DATASET` is not currently supported. Use `SHOW DATASETS LIKE '<NAME>' IN SCHEMA <DB>.<SCHEMA>` instead. |

## Integration

- **`../permission/SKILL.md`** — diagnose and fix missing permissions. Route here for any privilege-related error.
- **`dataset/SKILL.md`** — author / expand evaluation datasets (Step 3.2 of the parent workflow can call into this skill in **parent-mode** with `<AGENT_FQN>` / `<DATASET_NAME>` / `<METRIC_SCOPE>` pre-filled).
- **`test/SKILL.md`** — try questions interactively before locking into a dataset.
- **`creation/SKILL.md`** — create the agent if the user doesn't have one.
- **`monitor/SKILL.md`** — check status and view per-metric scores of a completed or in-progress eval run.
