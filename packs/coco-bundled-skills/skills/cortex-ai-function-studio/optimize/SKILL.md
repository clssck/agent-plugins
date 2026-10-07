---
name: optimize-ai-function
description: "Optimize an AI function through automated function body optimization, including prompts, model references, and SQL pre/post-processing."
parent_skill: cortex-ai-function-studio
---
<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Optimize AI Function

Automatically improves AI functions through iterative function body optimization with Pareto frontier selection. The optimizer can modify the entire SQL function body -- prompts, model references, SQL pre/post-processing -- not just the system prompt.

## Prerequisites

**The target function must be created via `create/SKILL.md`** (or have compatible structure). The optimizer reverse-parses the function DDL to extract the full function body as the seed for optimization, then creates temporary functions with candidate body variations during optimization. The function body must contain at least one `AI_COMPLETE` call. The optimizer can modify the entire body -- prompts, model references, SQL pre/post-processing -- while preserving the function signature.

**ARRAY-typed parameters are supported.** The optimizer detects ARRAY parameters from the function DDL and automatically handles type casting when passing training data (stored as VARCHAR) to candidate functions. No manual type conversion is needed. For best results, ensure synthetic training data was generated with `--function-name` so that ARRAY inputs are stored as JSON arrays (e.g., `["NAME", "EMAIL"]`) rather than comma-separated strings.

**Supported multimodal patterns:**
- **VARCHAR file paths**: function takes VARCHAR inputs with `TO_FILE()` in the body — auto-detected from DDL.
- **FILE data type**: function takes FILE parameters directly — auto-detected from DDL signature. `stage_name` **must** be provided in metric options.

For FILE-type functions, ask the user for `stage_name` during data collection. The optimizer validates stage access and file existence automatically before starting — see `references/multimodal_setup.md` "Validating File Access".

If the function was not created with the expected structure, the optimization will fail. Direct the user to recreate the function using the create workflow.

## When to Load

Load from main skill when user intent matches OPTIMIZE: "optimize", "tune", "improve".

## Information Model

| Field | Required | Default | Confirm | Dependencies |
|-------|----------|---------|---------|--------------|
| `function_name` | Yes | - | No | - |
| `function_structure_confirmed` | Yes | - | **Yes** | function_name |
| `training_table` | Yes | - | No | - |
| `test_table` | No | training_table | No | - |
| `input_columns` | Yes | - | **Yes** | training_table |
| `label_column` | Yes | - | **Yes** | training_table |
| `metric` | Yes | - | **Yes** | - |
| `auto_budget` | Yes | light | No | - |
| `models` | Yes | [function's model] | **Yes** | - |
| `reflection_model` | Yes | claude-sonnet-4-6 | No | - |
| `experiment_name` | No | (generated) | No | function_name |
| `aggregation_metric` | No | accuracy | No | metric |
| `optimize_mode` | No | body | No | - |

**Critical fields** (always confirm even if pre-provided): `function_structure_confirmed`, `input_columns`, `label_column`, `metric`, `models`

**Simple fields** (accept silently if pre-provided): `function_name`, `training_table`, `test_table`, `auto_budget`, `reflection_model`, `experiment_name`, `aggregation_metric`, `optimize_mode`

## Pre-Collection

Before prompting, scan the user's initial message and any prior context for already-provided information:

1. **Function name**: Look for fully qualified names like `DB.SCHEMA.FUNCTION_NAME`
2. **Tables**: Look for table references like `DB.SCHEMA.TABLE`, mentions of "training table", "test table"
3. **Column mappings**: Look for phrases like "input column X", "label column Y", "expected column Z"
4. **Metric**: Look for evaluation metrics like "exact_match" or "llm_judge". Note these are not the only names, and users can build custom evaluation metrics. If you aren't sure, ask the user.
5. **Budget**: Look for "ultra-light" (formerly "demo"; still accepted), "light", "medium", "heavy" or phrases like "quickest", "quick test", "E2E", "demo walkthrough", "quick optimization", "thorough search"
   - Treat "quickest", "quickest safe", "quick test", "small test", "E2E", "end-to-end test", and "demo walkthrough" as `auto_budget=ultra-light` unless the user explicitly names a larger budget.
6. **Models**: Look for model names like "claude-sonnet-4-5", "claude-haiku-4-5", "claude-opus-4-5"

For each piece found:
- **Simple fields**: Accept silently, proceed without re-asking
- **Critical fields**: Present for confirmation even if pre-provided

## Workflow

### Step 1: Get AI Function

**If `function_name` already collected** (user provided function name upfront):
- Skip the prompt — proceed directly to validation
- Acknowledge: "I'll optimize `{function_name}`"

**If not collected**, ask the user what function they would like to optimize. Validate function exists and get its DDL.

**Always use the fully qualified name** (`DB.SCHEMA.FUNCTION_NAME`). If the user provides an unqualified name, resolve it using the `{database}` and `{schema}` from prerequisites. All downstream references (review block, script flags, DDL) must use the fully qualified name.

### Step 2: Verify Function Structure (Background)

The optimizer reverse-parses the function DDL to extract the **full function body** (the SQL expression inside the `AS $$ ... $$` block). This becomes the seed body for optimization. The body must contain at least one `AI_COMPLETE` call.

If extraction fails (function DDL cannot be parsed or body doesn't contain `AI_COMPLETE`), inform user they need to recreate the function using `create/SKILL.md`.

### Step 3: Get Training & Test Data Tables

**If `training_table` already collected** (user provided table name upfront):
- Skip to table validation, acknowledge: "I'll use `{training_table}` for training"

**If coming from evaluate workflow with split data:** Pre-populate:
```
Using data splits from evaluation:
- Training: {train_table_from_evaluate}
- Test: {test_table_from_evaluate}

Confirm these tables? (y/n) If no, provide different table names.
```

**Otherwise:** **Load** `references/data_preparation.md` with context:
- `workflow`: "optimize"
- Keep function context from Step 1 for synthetic or pseudo-label routes.

**Note on optimize training data:** The optimizer internally splits training into train/dev sets automatically. Use `0.5` validation by default; if the training table has more than 200 rows, use `0.2` validation instead. **Never set validation fraction to 0.0 or 1.0** — 0.0 produces an empty validation set (optimizer hangs); 1.0 leaves no data for reflection.

**Test table defaults to training table.** Do not ask the user for a separate test table unless they explicitly provide one or request a split. If no test table is provided, silently use the training table for final evaluation. If the user provides a separate test table (or one was carried over from an evaluate workflow), use it.

When routing to synthetic data generation from this workflow, pass function context and **infer task description automatically** from the function COMMENT (or system prompt fallback). If unsure, you can ask for a quick confirmation/edit, not for a brand-new intention prompt.

Validate training table (and test table if provided):
```sql
DESCRIBE TABLE <training_table>;
SELECT COUNT(*) FROM <training_table>;
```

If test table provided:
```sql
DESCRIBE TABLE <test_table>;
SELECT COUNT(*) FROM <test_table>;
```

Store the column lists from both DESCRIBE outputs — you will need them for column mapping validation below.

**If `input_columns` and `label_column` already collected:**
- Present for confirmation (critical fields): "I'll use input columns `{input_columns}` and label column `{label_column}` — confirm?"

**Otherwise:** Follow column mapping in `references/data_preparation.md` Step 4.

**⚠️ STOP**: Always confirm column mapping before proceeding (critical fields).

After confirmation, **Load** `references/data_preparation.md` Step 5 to validate that all mapped columns exist in the relevant tables. Do NOT proceed if columns don't match.

**⚠️ Column mismatch handling**: If any mapped column does not exist in the training or test table, you MUST present the mismatch to the user via `ask_user_question` (not prose text). Include the mismatched column names, the actual table columns, and remediation options. Do NOT silently remap or proceed — always surface the mismatch through `ask_user_question` so the user can decide.

**Multi-key output handling:** If the user's training/test table has multiple truth columns that correspond to keys in a multi-key function output (e.g., separate `SENTIMENT`, `CONFIDENCE` columns instead of a single VARIANT), help them combine these into a single VARIANT `label_column` using `OBJECT_CONSTRUCT` in a view before optimization. See `references/data_preparation.md` "Multi-Column Truth Aggregation" for the SQL pattern.

### Step 4: Configure Optimization

#### Step 4.1: Select Metric

**Load** `references/metrics.md` and present the metric selection prompt.

**If user chooses "Create custom metric" (option 6):**
**Load** `references/custom_metrics.md` with context:
- Preserve function name: `{function_name}`
- Preserve training table: `{training_table}`
- Preserve column mappings: `{input_columns}`, `{label_column}`
- Note: *"After creating your custom metric, we'll return here to continue optimization setup."*

After custom metric creation completes, return to this step with the new metric name.

Store as `metric_name`.

#### Step 4.1b: Select Aggregation Metric (Classification Tasks Only)

**If `aggregation_metric` already collected**, skip. Otherwise:

**Only ask this if the task/problem appears classification-based (e.g., predicting categories, classes, or labels).** For non-classification tasks, skip and leave `aggregation_metric` as NULL.

```
The optimizer will use batch-level accuracy as the aggregation metric and report
precision, recall, F1, and accuracy as diagnostics for each candidate.

Would you like to change the aggregation metric?

1. **accuracy** (default) - Optimize for overall accuracy
2. **f1-score** - Optimize for F1 score (recommended for imbalanced classes)
```

Store as `aggregation_metric`. Default: `'accuracy'`

When `aggregation_metric` is set, the optimizer computes precision, recall, F1, and accuracy across each evaluation batch. All four are reported as diagnostics; the selected metric is used to score and rank candidates.

#### Step 4.2: Select Budget

**If `auto_budget` already collected**, skip. Otherwise:

```
How thorough should the optimization search be?

1. ultra-light - ~2 iterations (quickest, safest for E2E/headless testing, ~5 minutes)
2. light - ~6 iterations (recommended for real optimization, ~5-10 minutes)
3. medium - ~12 iterations (balanced, ~10-20 minutes)
4. heavy - ~18 iterations (thorough search, ~20-30 minutes)
```

**Snowsight `ask_user_question` options** — use these exact labels (do NOT paraphrase):
- `"ultra-light: ~2 iterations, ~5 min (quickest)"`
- `"light: ~6 iterations, ~5-10 min (recommended)"`
- `"medium: ~12 iterations, ~10-20 min (balanced)"`
- `"heavy: ~18 iterations, ~20-30 min (thorough)"`

Store as `auto_budget`. Default: `light` for normal customer optimization.

**Quick/E2E override:** If the user asks for the "quickest", "quickest safe", "quick test", "small test", "E2E", "end-to-end test", or "demo walkthrough" setting, store `auto_budget=ultra-light`. Do not silently choose `light` for these phrases.

#### Step 4.3: Select Models to Optimize

**If `models` already collected**, skip. Otherwise:

Follow the model selection workflow in `references/model_selection.md` (Steps 1-4) to determine the available models. Present the hosted models plus `See all models` to the user as a **multi-select** list; the user must select which models to optimize for — do not silently pick for them. Verified Bring your own Model / Hugging Face models are listed under `See all models` (no separate gateway). If the user selects one of those (or explicitly asks for a Hugging Face/open-source model, an SPCS service, or an existing model service), load `byom/SKILL.md` first, then return to optimization.

**Always include the function's current model** (from Step 2) in the list. If it is not already one of the 6 defaults, append it to the list marked as "(current)". The current model must always be visible so users can include it in the optimization comparison.

**Bring your own Model inclusion rule:** If the function's current model is a Bring your own Model/SPCS service model (for example a fully-qualified service name used in `AI_COMPLETE`, an imported Model Registry service, or any existing Bring your own Model selected earlier in the workflow), it must be included in `models` even when the user also selects Cortex-hosted models. Do not replace Bring your own Model with only Cortex-hosted candidates. The optimization should compare the existing Bring your own Model candidate against the selected hosted models unless the user explicitly says to exclude Bring your own Model.

**⚠️ STOP**: Show the model list and wait for the user's selection before proceeding. **In Snowsight, you MUST use `ask_user_question` with `multiSelect: true`.** Do NOT auto-select models or skip this menu — even in long sessions where earlier steps provided context.

```
Which models would you like to optimize for? You can select one or more. The current Bring your own Model/service model will be included automatically unless you explicitly exclude it.

Your function currently uses: {current_model}

Recommended models (ordered by cost):
  1. openai-gpt-5-nano  — Ultra-budget
  2. claude-sonnet-4-6  — Premium / recommended
  {if current_model not in list above:}
  replace the closest hosted option above with {current_model} — (current)

  n-1. See all models (Cortex-hosted models + verified Bring your own Model / Hugging Face models)

Tip: Selecting models across different cost tiers helps find the best
cost/quality tradeoff via Pareto analysis.

Enter model names (comma-separated), or just press enter to use: {current_model}
```

If the user selects "See all models", display all available models from `src/models.json` grouped by family — plus the `Bring your own Model — Hugging Face / open source (research preview)` group from `references/byom/model_catalog.md` (see `references/model_selection.md`) — and let them pick.

If the user selects a Bring your own Model / Hugging Face model (from `See all models`) or explicitly asks for a bring-your-own model, Hugging Face/open-source model, SPCS service, or an existing model service, load `byom/SKILL.md` first; the selected/onboarded service model is then included in the optimization candidate list.

Store as `models` (array). Default: `[<model from function DDL>]`. Before storing, ensure the current Bring your own Model/SPCS service model from the function DDL is present in the array. If it is missing and the user did not explicitly exclude it, append it and tell the user it will be included for comparison.

#### Step 4.4: Select Reflection Model

**If `reflection_model` already collected**, skip. Otherwise:

Default to `claude-sonnet-4-6` (or the strongest available model). Do not ask — accept silently.

Store as `reflection_model`. Default: `claude-sonnet-4-6`

#### Step 4.5: Review All Settings

**⚠️ STOP**: Present all optimization settings together as a single review block:

- **Experiment name**: Snowflake Experiment to persist optimization results (per-iteration runs, parameters, metrics) AND per-row eval details — every run (SEED, each accepted/rejected `ITER_N`, and the winner) uploads its own `eval_detail.json` to its nested stage (`versions/<run_name>/eval_detail.json`). Default: `{FUNCTION_NAME}_OPT_EXP`
- **Validation fraction**: Fraction of training data for validation vs reflection. Recommended default from the Step 3 training row count: `0.5`; if the training table has more than 200 rows, use `0.2`. Must be strictly between 0.0 and 1.0 (exclusive) — never use 0.0 or 1.0
- **Execution mode**: `sync` if `auto_budget == ultra-light` (or its legacy alias `demo`) (fast enough to wait); `async` otherwise (runs in background). The user can override this choice only after you explain that non-`ultra-light` sync runs can block for a long time.

```
Here's what I'll optimize:

Function: {database}.{schema}.{function_name}
Training table: {training_table} ({row_count} rows)
Test table: {test_table}
Input columns: {input_columns}
Label column: {label_column}
Metric: {metric_name}
Model: {models}
Reflection model: {reflection_model}
Budget: {auto_budget}
Execution mode: {execution_mode} (sync for ultra-light budget, async otherwise)
Experiment: {experiment_name}

Confirm or edit?
```

**In Snowsight, you MUST use `ask_user_question`** to confirm — do NOT auto-proceed or silently accept defaults. Present the review block in chat first (long content pattern), then call `ask_user_question` with options like `"Confirm and proceed"` / `"I want to edit"`.

**If `environment == snowsight`:** Load `references/snowsight/optimize.md` and follow it from Step 5 through Step 8. That file contains the complete Snowsight optimize flow — execution, result collection, charting, deployment, and next steps. **Do not return to this file.**

#### Step 4.6: Experiment Conflict Check

Immediately after the user confirms settings in Step 4.5, check whether the target experiment already has optimization results. `experiment_name` is always set at this point — it defaults to `{FUNCTION_NAME}_OPT_EXP` and was confirmed (or edited) by the user in the review block.

```sql
SHOW RUNS IN EXPERIMENT {experiment_name};
```

**If no runs exist** (empty result): proceed normally to Step 5.

**If the query fails with a SQL error** (experiment does not exist yet): treat as no runs and proceed normally to Step 5.

**If runs exist**, inform the user and present their options — leading with the safe choice:

> Experiment `{experiment_name}` already has optimization results from a prior run.
>
> Re-optimizing into the same experiment is not supported. You have two options:
>
> **Option A (recommended): Use a different experiment name** — provide a new name to start fresh while keeping the existing results.
>
> **Option B: Delete the existing experiment** — permanently removes all prior results and cannot be undone.

**⚠️ MANDATORY CHECKPOINT — DATA LOSS:** Wait for explicit user confirmation before executing the DROP. Do NOT proceed automatically.

**If the user chooses a different experiment name (Option A):** Ask them to provide a new `experiment_name`. Update `experiment_name` and return to Step 4 to re-confirm settings with the new name.

**If the user explicitly confirms deletion (Option B):**
```sql
DROP EXPERIMENT IF EXISTS {experiment_name};
```
Then proceed to Step 5.

---

*The remainder of this file (Steps 5–8) is for CLI environments only.*

### Step 5: Run Optimization

**Always pass `timeout_seconds: 14400` (4 hours / 240 minutes) on every `OPTIMIZE_AI_FUNCTION` SQL call.** The SPROC routinely runs for 10+ minutes; the default 180s statement timeout will kill it mid-run. The `run.py optimize` script sets this for you; if you invoke the SQL tool directly, you must pass it explicitly.

Explain to the user what the procedure does:
```
OPTIMIZE_AI_FUNCTION iteratively improves your function by:
1. Scoring function body variations against training examples
2. Keeping Pareto-optimal performers (best quality/cost tradeoffs)
3. Generating new variations — modifying prompts, model references, and SQL pre/post-processing
```

Pass all selected models in a single SPROC call. The SPROC runs all models **concurrently** internally using parallel threads, so there is no need to call it once per model. Results from all models will be compared in Step 6 to find pareto-optimal options.

#### Execution Mode

Use the execution mode confirmed in Step 4.5: `sync` if `auto_budget == ultra-light` (or its legacy alias `demo`) (fast enough to wait), `async` otherwise.

**Do not run non-`ultra-light` budgets synchronously by default.** For `light`, `medium`, or `heavy`, use async execution and stop after submission with the run ID, status command, and resume instructions. Only run a non-`ultra-light` budget synchronously if the user explicitly confirms they understand it may block for 10+ minutes.

**Async unavailable fallback:** If async execution is unavailable because the role lacks Task or warehouse privileges, do not automatically fall back to sync for `light`, `medium`, or `heavy`. Offer to either:
1. switch to `ultra-light` and run sync now, or
2. get the required Task/warehouse grant and keep the selected non-`ultra-light` budget async.

For E2E/headless/customer walkthroughs, recommend option 1 (`ultra-light` sync).

**Sync execution** (`budget == ultra-light`, or its legacy alias `demo`): Runs the CALL directly and returns results inline.

**Async execution** (any other budget): Runs in background. Append `--async --warehouse {warehouse}` to `run.py optimize`.

#### Running the Optimization

Run the optimization script. It renders the anonymous SPROC, appends the CALL, and executes everything in a single Snowpark session. **Always pass every flag** — use `none` for unused optional parameters.

**Resolving `<SKILL_DIRECTORY>`**: this is the absolute path to the installed `cortex-ai-function-studio` skill package. Find it with:
```bash
# Runs in CoCo bash sandbox (Linux) — safe on any host OS
find /custom-skills /workspace /home -name "presentation.py" -path "*/cortex-ai-function-studio/*" 2>/dev/null | head -1 | xargs dirname | xargs dirname
```
Use the path it prints as `<SKILL_DIRECTORY>` in all commands below.

Choose the command form from the confirmed execution mode:

- For `ultra-light`, run the sync command without `--async`.
- For `light`, `medium`, or `heavy`, run the async command by appending `--async --warehouse {warehouse} --timeout-minutes 240` (4 hours; matches the `timeout_seconds: 14400` used for direct SQL calls).
- If a warehouse has not been collected for async mode, ask for it before running.

```bash
PYTHONPATH=<SKILL_DIRECTORY>/scripts uv run --project <SKILL_DIRECTORY> python <SKILL_DIRECTORY>/scripts/run.py optimize \
    --database {database} --schema {schema} --connection <CONNECTION_NAME> \
    --function-name {database}.{schema}.{function_name} --training-table {training_table} \
    --label-column {label_column} --input-columns {input_col1} {input_col2} \
    --metric-name {metric_name} --models {model1} {model2} --reflection-model {reflection_model} \
    --test-table {test_table or none} --auto-budget {auto_budget} \
    --experiment-name {experiment_name or none} \
    --validation-fraction {validation_fraction} --temperature 0.7 --max-tokens 8192 \
    --metric-options none --custom-metric-udf none \
    --run-id none --aggregation-metric {aggregation_metric or none} \
    --engine default
    # For async budgets only: append --async --warehouse {warehouse} --timeout-minutes 240
```

Run `run.py optimize --help` to see all flags and their descriptions.

**Important: SQL timeout** — For sync execution, the optimization SPROC can run for 10+ minutes. Use `timeout_seconds: 14400` (4 hours) to prevent the query from timing out before completion. If you call `CALL OPTIMIZE_AI_FUNCTION(...)` via the SQL tool directly (instead of `run.py`), pass `timeout_seconds=14400`.

#### Sync Output

The script prints a JSON result to stdout:
```json
{"status": "success", "result": {"run_id": "...", "best_body": "...", "best_ddl": "...", "seed_body": "...", ...}, "function": "DB.SCHEMA.MY_FUNC"}
```

Collect and store results from each model run for comparison in Step 6.
The single call returns results for all models. Each model gets the same budget and runs independently in parallel.

**Timeout self-correction:** If the script fails due to a SQL timeout, the query was killed (client-side cancellation), not completed. Inform the user, then check the experiment for partial results (`SHOW RUN METRICS IN EXPERIMENT {experiment_name}`). Offer to **skip the timed-out model** or **reduce budget** (e.g., `medium` → `light`). Do NOT silently move on or conflate partial results from different models.

#### Async Output

The script prints a JSON result to stdout with the generated `run_id`:
```json
{"status": "submitted", "run_id": "ai_func_opt_MY_FUNC_1739919133000", "task": "DB.SCHEMA.ai_func_opt_MY_FUNC_1739919133000"}
```

**⚠️ WAREHOUSE NOTE**: If the Task creation fails or the script returns `{"status": "error", ...}`, it likely means the current role lacks a direct USAGE grant on the target warehouse. Snowflake Tasks require an explicit grant — session-level access via role hierarchy is not sufficient. Display the error to the user with the `GRANT` command needed and instructions for finding usable warehouses.

**⚠️ IMPORTANT**: Display the run_id prominently to the user:

```
Optimization started in background!

RUN_ID: {run_id}

Save this run_id to track your optimization.

Check status:  See references/async_status.md
View results:  SHOW RUN METRICS IN EXPERIMENT {experiment_name}
```

**⚠️ IMPORTANT**: For async optimization, `EXPERIMENT_NAME` is required since the return value isn't directly accessible. Results are persisted as experiment runs.

**Load** `references/async_status.md` if user wants to check status.

**Cleanup after async completes:** See `references/async_status.md` Cleanup section for task status verification and cleanup SQL (drop the Task after it reaches `SUCCEEDED`, `FAILED`, or `CANCELLED`).

### Step 6: Present Results (with Pareto Filtering)

**⚠️ MANDATORY — Re-read before resuming.** If this is a **new conversation** (e.g., the user is returning after an async optimization), you are resuming from memory without full skill context. **You MUST re-read this file (`optimize/SKILL.md`) before proceeding.** Do NOT jump directly to Step 6.3 or present results from memory — the instructions below contain required substeps and SQL templates that you need.

**⚠️ MANDATORY**: You MUST complete ALL substeps below (6.1 through 6.3) before presenting any results to the user or asking what to do next. **Exception: single-model fast path** — if only one model was optimized, skip step 6.2 (pareto filtering is pointless with a single model since there are no cost/quality tradeoffs to compare). Go directly from 6.1 to 6.3, presenting the single model's best result.

**6.1. Collect results:**

Always use `presentation.py` to produce cost values — the script applies correct relative-cost scaling from `models.json` and the formula `cost = input_cost × prompt_chars + output_cost × avg_output_chars`. Do NOT compute costs manually, use Python REPL, or read from `models.json` by hand; manual calculations produce wrong units (dollars instead of relative multipliers).

Choose the path based on how results were provided:

**Path A — User provided model/score results as a table in chat** (no Snowflake experiment needed):

Locate the skill directory, then run `presentation.py` with `--json`:

```bash
# Runs in CoCo bash sandbox (Linux) — safe on any host OS
SKILL_DIR=$(find /custom-skills /workspace /home -name "presentation.py" -path "*/cortex-ai-function-studio/*" 2>/dev/null | head -1 | xargs dirname | xargs dirname)

uv run --project "$SKILL_DIR" python "$SKILL_DIR/scripts/presentation.py" \
    --json '[{"model": "model-name", "score": 0.XX}, {"model": "model-name-2", "score": 0.YY}]' \
    --prompt-chars {system_prompt_chars} --avg-output-chars {avg_output_chars} \
    --seed-score {original_score} --format table
```

`--prompt-chars` = system prompt template character count **ONLY** (do NOT add user input characters); `--avg-output-chars` = average output character count; `--seed-score` = original function score (optional). Both `--prompt-chars` and `--avg-output-chars` are required without `--experiment`.

**Path B — Results stored in a Snowflake experiment** (after running the optimizer):

The SPROC flags Pareto-optimal candidates with `is_frontier`; these runs carry `function_impl`, `model`, `estimated_cost`, `valset_score`, and `test_score` (when test-evaluated). `presentation.py` reads these runs and renders the cost-quality table:

```bash
PYTHONPATH=<SKILL_DIRECTORY>/scripts uv run --project <SKILL_DIRECTORY> python <SKILL_DIRECTORY>/scripts/presentation.py \
    --experiment {experiment_name} --connection {connection} --format table
```

This prints the Pareto table directly (see 6.2). It never mixes score domains: when every frontier candidate was test-evaluated it shows test scores (pruned to the test-Pareto subset); otherwise it shows validation scores for the full frontier. Use `--format json` to get the same rows programmatically (e.g. to drive `ask_user_question`).

Sync and async runs persist to the experiment identically, so collection and presentation are **the same for both paths**: read the `is_frontier` runs from the experiment with `presentation.py`. (Sync `run.py` stdout additionally returns the same data under `result` for convenience — including `best_ddl` for body mode — but the experiment is the source of truth.)

The experiment name follows the pattern `{FUNCTION_NAME}_OPT_EXP` unless the user specified a custom name. Run names form one global sequence — `SEED` for the seed candidate and `ITER_1`, `ITER_2`, …, `ITER_N` for each candidate across ALL models (accepted and rejected). The producing model is a run PARAMETER, not part of the run name; do NOT embed model names in run names.

**Failed models:** If `SHOW RUNS` returns a `{MODEL}_FAILED` run for a model, that model's optimization failed. Report the failure to the user (query `SHOW RUN PARAMETERS` on the FAILED run for the `error_message`) and proceed with whichever other models completed successfully.

**Per-row test-set evaluation details** (optional):

For per-row test-set evaluation details (uploaded by the optimizer to the winning ITER run's nested stage), create a named JSON file format and query the artifacts via SnowURL string-literal paths:

```sql
CREATE OR REPLACE TEMPORARY FILE FORMAT eval_detail_json_fmt
  TYPE = JSON
  STRIP_OUTER_ARRAY = TRUE;

-- Per-row details for the SEED candidate's test eval (on the SEED run)
SELECT $1:row_id::INT AS ROW_ID, $1:expected::STRING AS EXPECTED,
       $1:predicted::STRING AS PREDICTED, $1:metric_score::FLOAT AS SCORE,
       $1:metric_feedback::STRING AS FEEDBACK
FROM 'snow://experiment/{experiment_name}/versions/SEED/eval_detail.json'
(FILE_FORMAT => eval_detail_json_fmt)
ORDER BY ROW_ID;

-- Per-row details for the winning optimized candidate's test eval
-- (on the winning ITER run; substitute its run name, e.g. ITER_7)
SELECT $1:row_id::INT AS ROW_ID, $1:expected::STRING AS EXPECTED,
       $1:predicted::STRING AS PREDICTED, $1:metric_score::FLOAT AS SCORE,
       $1:metric_feedback::STRING AS FEEDBACK
FROM 'snow://experiment/{experiment_name}/versions/ITER_N/eval_detail.json'
(FILE_FORMAT => eval_detail_json_fmt)
ORDER BY ROW_ID;
```

> **Every run has its own detail file.** Every persisted run — the `SEED`,
> each accepted and rejected `ITER_N`, and the winner — uploads an
> `eval_detail.json` to its own nested stage
> (`versions/<run_name>/eval_detail.json`), so any run can be recovered by
> reading its JSON. Rejected runs carry only the minibatch rows they were
> scored on (`split = "val_subsample"`).

> **⚠️ SnowURL scope**: These `snow://experiment/...` paths are ONLY for per-row eval detail files — each run's own `eval_detail.json` (e.g. `versions/SEED/eval_detail.json`, `versions/ITER_3/eval_detail.json`). Do NOT use SnowURL paths to retrieve function bodies, candidates, or optimization state — use `SHOW RUN PARAMETERS` for function body retrieval.

> Querying `'snow://experiment/...'` requires the server-side parameter `ENABLE_EXPERIMENT_SNOWURL_READ_PATH_RESOLUTION` to be enabled. The path is a **string literal**, not a `@stage` reference, and the FILE FORMAT must be a named object — inline `(TYPE => JSON)` is not supported on SnowURL.

**6.2. Present Pareto-optimal results as a cost-quality table:**

Present the table produced by `presentation.py` (step 6.1). Its columns are: `#`, `Run`, `Model`, `Test Score` and/or `Val Score`, `Improvement`, `Est. Credits/1K calls`.

- **Run**: the SEED/ITER run name (flagged `is_frontier`) — use it in Step 7 to fetch the selected candidate's `function_impl`.
- **Test Score / Val Score**: never mixed — `Test Score` (left) plus `Val Score` appear when a test table was used; only `Val Score` otherwise.
- **Improvement**: difference from the seed candidate's score in the same domain (computed by the script).
- **Est. Credits/1K calls**: per-1,000-call cost in Snowflake credits derived from each run's `estimated_cost`, with a `(cheapest)` / `(N.Nx)` relative marker.

The table is already the Pareto set (hypervolume-selected by the SPROC, test-Pareto-pruned for display when test scores exist). Present all rows — do NOT re-filter.

**6.3. Get user selection:**

**⚠️ STOP**: Use `ask_user_question` to let user select the result to apply. Each option should show the model name, score, and cost. For the selected row, fetch its optimized function body from the SEED/ITER run's `function_impl` parameter (`SHOW RUN PARAMETERS IN EXPERIMENT {experiment_name} RUN {selected_run}`); this is what gets deployed in Step 7. (Sync body-mode runs also expose `best_ddl` directly in the `run.py` output for the overall winner.)

### Step 7: Apply Optimized Function

Ask user:
```
Apply the optimized function?

1. Yes - Replace the original function
2. Save as new function - Create a new function with suffix (e.g., MY_FUNC_OPTIMIZED)
3. No - Keep original
```

The optimizer returns `best_ddl`, a complete `CREATE FUNCTION` DDL statement with the optimized body. It is built by `reconstruct_ddl()`, which only replaces the `$$...$$` body and preserves everything else from the original DDL — including (or omitting) the `COMMENT` clause.

**⚠️ MANDATORY COMMENT TAG CHECK**: Before showing or executing `best_ddl`, verify it contains a `COMMENT` clause whose value begins with the exact prefix `[CORTEX AI FUNC STUDIO] `. If the original function was created by the studio the prefix carries through automatically; if it was created outside the studio (or by an older flow) the prefix may be missing. If missing, you MUST inject a `COMMENT = '[CORTEX AI FUNC STUDIO] <short description>'` clause into the DDL before deployment — this prefix is required for every `CREATE FUNCTION` DDL produced by this skill and is how the studio identifies its functions. Do not deploy a SQL body without it.

**⚠️ STOP**: Show the (verified/fixed) `best_ddl` to the user for review. Once confirmed, execute the DDL directly:

```sql
{best_ddl}
```

**If "Save as new function":**

Ask the user for a new function suffix (e.g., V2, OPTIMIZED, PROD). Modify the function name in the DDL to use the new function name (`{function_base}_{function_suffix}`) and show the modified DDL to the user for review. Apply the same `[CORTEX AI FUNC STUDIO] ` comment-prefix check described above before executing. Once confirmed, execute it.

### Step 8: Next Steps

Ask user:
```
Optimization complete. What would you like to do?

1. **Evaluate** - Test optimized function on held-out data
2. **Re-optimize** - Run again with different settings
3. **Done** - Exit
```

If evaluate → Load `evaluate/SKILL.md` with context:
- Preserve function name
- Pass the test table used: `{test_table}`
- Note: *"The evaluate workflow will use your test table: {test_table} for consistent results."*

If the customer wants to re-optimize or is unsatisfied with the current improvement:
**⚠️ STOP**: Use `ask_user_question` to let the user select the result to apply.

Ask the user:
```
Do you want to change the initial function structure (prompts, pre/post-processing, model)?
Most of the cases, changing in abstraction can give significantly different results.

1. Yes - Go back to recreate new function with different initial structure.
2. No - Re-optimize with different optimization effort level.
3. Analyze errors and help me decide.
```

If the user selects 1 -> Load `create/SKILL.md` with context:
- Preserve `{database}`, `{schema}`, `{function_name}`, `{inputs}`, `{outputs}`, `{model}`
- Pass the current seed function body and error analysis so the create workflow can inform approach selection
- Note: *"The customer is re-creating this function with a different approach. Skip to Step 4 (Select Creation Mode) — task description, clarifications, inputs, and outputs are already known. Follow `create/SKILL.md`'s mode-selection rules: default to Direct mode unless the customer has EXPLICITLY asked for research mode, custom SQL, or SQL pre/post-processing. Selecting 'change the initial function structure' here is NOT itself an explicit request for research mode — if you think research mode is warranted, briefly offer it and wait for the customer to confirm before switching."*

If the user selects 2 -> Ask the customer for a new `auto_budget` and optionally new `models`. Then re-run optimization from Step 5 (Run Optimization) with the updated settings.

If the user selects 3:
Try to run evaluation on the optimized version and see what the error types are. Then, critically reason through the following:
1. Can this be solved with different pre-/post-processing?
2. Inspect optimization progression to see whether it's in the correct direction. Would a different seed function body solve this problem?
3. Is the current model just not strong enough? Should we try a stronger or different type of model?
After doing this analysis, help user identify whether they should run optimization with different effort level or re-create function with different settings.

## Stopping Points

Critical confirmations (always stop, even if pre-provided):
- ✋ Step 3: Confirm column mapping (input_columns, label_column)
- ✋ Step 4.3: Show available models and wait for user selection

Optional confirmations:
- ✋ Step 6: After presenting pareto-optimal results (get user selection)
- ✋ Step 7: Before applying changes

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Function not found` | Use fully qualified name: `DB.SCHEMA.MY_FUNC`. Verify: `SHOW FUNCTIONS LIKE 'MY_FUNC' IN SCHEMA DB.SCHEMA;` |
| `Could not extract function body from DDL` | Function DDL could not be parsed. Recreate via `create/SKILL.md`. |
| `Could not extract model name from DDL` | Function body does not contain `model=>'...'`. Recreate via `create/SKILL.md`. |
| Statement timeout / `Statement reached its statement_timeout_in_seconds` while running `OPTIMIZE_AI_FUNCTION` | Always pass `timeout_seconds: 14400` (4 hours / 240 minutes) on the SQL call. The default 180s timeout will kill the SPROC mid-run. |
| Optimization hangs after creating experiment (no temp functions created) | `validation_fraction` is 0.0, producing an empty validation set. The optimizer cannot score candidates and loops indefinitely. Set `validation_fraction` to a value above 0.0 (recommended: 0.2–0.5). |

## Output

- VARIANT result from the SPROC (JSON object) with best function body and DDL per model — the `run.py` script parses this and prints it as a JSON string to stdout
- Experiment object with optimization history (runs, metrics, parameters)
- Updated AI function with optimized body (if applied)
- No persistent artifacts — Python code is inlined into the anonymous SPROC

## Quick Reference — Presenting Cost Tables from Inline Results

For inline results (user provides model/score table in chat), load `references/presentation_quick_ref.md`.
