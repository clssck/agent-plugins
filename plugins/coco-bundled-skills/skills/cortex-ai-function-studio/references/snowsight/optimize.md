<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Snowsight Optimize Workflow

Requires `references/snowsight/core.md` to be loaded first.

## When to Load

Load this file when `environment == snowsight` at `optimize/SKILL.md` Step 4.5. This file covers the complete Snowsight optimize flow from execution through deployment and next steps (Steps 5–8). Once loaded, follow this file end-to-end — do not return to `optimize/SKILL.md`.

## MANDATORY: Pin Optimize Todos

**Immediately after loading this file**, call `system_todo_write` to pin the following steps. Mark Step 5 as `in_progress`. Do NOT skip any step — especially 6.2 and 6.3 (notebook cells).

```
1. Step 5: Run optimization SPROC (sync or async)
2. Step 6.1: Collect results from SPROC output or experiment
3. Step 6.2: Create notebook + add bar chart + Pareto frontier chart cells + run them
4. Step 6.3: ask_user_question — user selects model from Pareto results
5. Step 7: Deploy via CALL CREATE_AI_FUNCTION (NOT raw DDL) — show user for review first
6. Step 8: ask_user_question — next steps (Evaluate / Re-optimize / Done)
```

## Step 5: Running the Optimization (Snowsight)

**⚠️ ALL 18 positional parameters are required for OPTIMIZE_AI_FUNCTION.** Do NOT collapse parameters into a single JSON object. Do NOT skip or reorder parameters. **Always set database/schema context first.**

### Sync Path (`budget == ultra-light`)

When `auto_budget == ultra-light` (or its legacy alias `demo`), execute the CALL directly (no Task wrapper) using `execute_sql` with `timeout_seconds: 14400`:

```sql
USE {database}.{schema};

CALL SNOWFLAKE.CORTEX.OPTIMIZE_AI_FUNCTION(
    '{database}.{schema}.{function_name}',              -- 1. FUNCTION_NAME (VARCHAR)
    '{training_table}',                                  -- 2. TRAINING_TABLE (VARCHAR)
    '{label_column}',                                    -- 3. LABEL_COLUMN (VARCHAR)
    ARRAY_CONSTRUCT('{input_col1}', '{input_col2}'),     -- 4. INPUT_COLUMNS (ARRAY)
    '{metric_name}',                                     -- 5. METRIC_NAME (VARCHAR)
    ARRAY_CONSTRUCT('{model1}', '{model2}'),             -- 6. MODELS (ARRAY)
    '{reflection_model}',                                -- 7. REFLECTION_MODEL (VARCHAR)
    {test_table_or_NULL},                                -- 8. TEST_TABLE (VARCHAR or NULL)
    'ultra-light',                                       -- 9. AUTO_BUDGET (VARCHAR)
    {validation_fraction},                               -- 10. VALIDATION_FRACTION (FLOAT, must be >0.0 and <1.0)
    0.0,                                                 -- 11. TEMPERATURE (FLOAT)
    8192,                                                -- 12. MAX_TOKENS (INTEGER)
    {metric_options_or_NULL},                             -- 13. METRIC_OPTIONS (VARIANT or NULL)
    {custom_metric_udf_or_NULL},                          -- 14. CUSTOM_METRIC_UDF (VARCHAR or NULL)
    NULL,                                                -- 15. RUN_ID (NULL for sync)
    {aggregation_metric_or_NULL},                         -- 16. AGGREGATION_METRIC (VARCHAR or NULL)
    'body',                                              -- 17. OPTIMIZE_MODE (VARCHAR)
    '{experiment_name}'                                  -- 18. EXPERIMENT_NAME (VARCHAR)
);
```

The CALL returns a JSON result directly. Parse and proceed to Step 6.

### Async Path (any other budget)

Generate `run_id` as `ai_func_opt_{FUNC_SHORT_NAME}_{timestamp_ms}`. Before constructing the Task DDL, **resolve the warehouse name**:

1. Run `SELECT CURRENT_WAREHOUSE() AS WH;` via `execute_sql`.
2. If the result is non-NULL, use it as `{warehouse}`.
3. If the result is NULL, use `ask_user_question` to ask: `"No active warehouse detected. Which warehouse should I use for this optimization task?"` — use the user's response as `{warehouse}`.

Submit the optimization as an async Task by executing the following SQL via `execute_sql` tool.

```sql
USE {database}.{schema};

CREATE OR REPLACE TASK {database}.{schema}.{run_id}
    WAREHOUSE = {warehouse}
    USER_TASK_TIMEOUT_MS = 14400000
AS
    CALL SNOWFLAKE.CORTEX.OPTIMIZE_AI_FUNCTION(
        '{database}.{schema}.{function_name}',              -- 1. FUNCTION_NAME (VARCHAR)
        '{training_table}',                                  -- 2. TRAINING_TABLE (VARCHAR)
        '{label_column}',                                    -- 3. LABEL_COLUMN (VARCHAR)
        ARRAY_CONSTRUCT('{input_col1}', '{input_col2}'),     -- 4. INPUT_COLUMNS (ARRAY)
        '{metric_name}',                                     -- 5. METRIC_NAME (VARCHAR)
        ARRAY_CONSTRUCT('{model1}', '{model2}'),             -- 6. MODELS (ARRAY)
        '{reflection_model}',                                -- 7. REFLECTION_MODEL (VARCHAR)
        {test_table_or_NULL},                                -- 8. TEST_TABLE (VARCHAR or NULL)
        '{auto_budget}',                                     -- 9. AUTO_BUDGET (VARCHAR)
        {validation_fraction},                               -- 10. VALIDATION_FRACTION (FLOAT, must be >0.0 and <1.0)
        0.0,                                                 -- 11. TEMPERATURE (FLOAT)
        8192,                                                -- 12. MAX_TOKENS (INTEGER)
        {metric_options_or_NULL},                             -- 13. METRIC_OPTIONS (VARIANT or NULL)
        {custom_metric_udf_or_NULL},                          -- 14. CUSTOM_METRIC_UDF (VARCHAR or NULL)
        '{run_id}',                                           -- 15. RUN_ID (VARCHAR)
        {aggregation_metric_or_NULL},                         -- 16. AGGREGATION_METRIC (VARCHAR or NULL)
        'body',                                              -- 17. OPTIMIZE_MODE (VARCHAR)
        '{experiment_name}'                                  -- 18. EXPERIMENT_NAME (VARCHAR)
    );

EXECUTE TASK {database}.{schema}.{run_id};
```

### Parameter Notes

- **Param 4 `INPUT_COLUMNS`**: `ARRAY_CONSTRUCT(...)` — pass ALL input column names
- **Param 6 `MODELS`**: `ARRAY_CONSTRUCT(...)` — pass ALL selected models in a single call. If the function being optimized currently uses a Bring your own Model/SPCS service model, ensure that current Bring your own Model/service model is included alongside any selected Cortex-hosted models unless the user explicitly excluded it.
- **Param 7 `REFLECTION_MODEL`**: single string value
- **Param 15 `RUN_ID`**: required for async (needed for Task name and status checking); use `NULL` for sync
- **Param 18 `EXPERIMENT_NAME`**: required for async (the agent cannot read the CALL return from a Task)
- **Param 11 `TEMPERATURE`**: use `0.0` (matching current behavior for optimization)
- Pass `NULL` (not the string `'none'`) for all unused optional parameters

If the Task creation or execution fails, show the error and stop. Common failure: the current role lacks a direct USAGE grant on the warehouse — Snowflake Tasks require an explicit grant.

**⚠️ STOP after presenting the status summary (async path).** Do NOT proceed to Step 6 until the Task has reached `SUCCEEDED`. Query `TASK_HISTORY` at most **once per turn** — present the result and **end your turn with `ask_user_question`**. Never poll in a loop, never re-query automatically, never call `TASK_HISTORY` more than once per turn. The user will ask again when ready. The workflow resumes at Step 6 only when `STATE = 'SUCCEEDED'`.

### Status Checking (Async)

After submitting the optimization as an async Task, present the user with a summary and instructions using `ask_user_question`:

```
Optimization has been submitted as a background task.

**Task:** {run_id}
**Experiment:** {experiment_name}
**Models:** {models}
**Budget:** {auto_budget}

Optimization typically takes 5–30 minutes depending on budget and number of models. You can close this session and come back anytime — just ask me to "check optimization status" and provide the **Task** ID above.
```

Options: `["I'll come back later"]`

**Your turn MUST end with `ask_user_question` above.** Do NOT check status automatically. Do NOT call `TASK_HISTORY`. Do NOT proceed to Step 6. The `ask_user_question` call is a hard turn boundary — nothing runs after it.

### Checking Optimization Status

Only check status when the user **explicitly asks** in a new message (e.g., "check status of {run_id}"). Query `TASK_HISTORY` **once** — never more than one query per turn. Then:

- If `STATE = 'SUCCEEDED'`: proceed to Step 6 (collect results).
- If `STATE = 'FAILED'` or `'CANCELLED'`: report the error and stop.
- If `STATE` is `'SCHEDULED'`, `'EXECUTING'`, or not terminal: report the status and end your turn with `ask_user_question` (options: `["I'll check back later"]`). Do NOT re-query, do NOT poll again, do NOT offer to re-check automatically.

For full details on task states and result retrieval, load `references/async_status.md`.

## Step 6: Present Results (with Pareto Filtering)

**⚠️ MANDATORY — Re-read before resuming.** If this is a **new conversation** (e.g., the user is returning after an async optimization), you are resuming from memory without full skill context. **You MUST re-read this file (`references/snowsight/optimize.md`) before proceeding.** Do NOT jump directly to Step 6.3 or present results from memory — the instructions below contain required substeps, SQL templates, and notebook cell templates that you need.

**⚠️ MANDATORY**: You MUST complete ALL substeps below (6.1 through 6.3) **in order** before asking the user what to do next. Do NOT present results as a plain text table in the chat — results MUST be presented via notebook cells (bar chart + Pareto frontier graph in 6.2). The notebook is the primary deliverable, not chat text.

**Exception: single-model fast path** — if only one model was optimized, skip the Pareto frontier chart in step 6.2 (pareto filtering is pointless with a single model since there are no cost/quality tradeoffs to compare). You still MUST create the notebook with the bar chart showing seed vs optimized.

### Step 6.1: Collect Results

In Snowsight, the JSON return from the SPROC is not directly accessible for async runs (executed via Task). Use `SHOW RUN METRICS` and `SHOW RUN PARAMETERS` to retrieve results from the experiment. These are the **only** approved methods for retrieving optimization results in Snowsight.

**For sync runs** (`ultra-light` budget): the CALL returns a JSON result directly. Parse it — the `frontier_candidates` list contains the Pareto-filtered results with `model`, `score`, `test_score`, `estimated_cost`, and `prompt` for each candidate. Use these directly for Step 6.2.

**For async runs** (or when returning in a new session): query the experiment:

```sql
-- List all runs and their status
SHOW RUNS IN EXPERIMENT {experiment_name};

-- Per-candidate metrics (test_score / valset_score / estimated_cost /
-- is_frontier are stamped directly on the SEED and ITER runs)
SHOW RUN METRICS IN EXPERIMENT {experiment_name} RUN ITER_N;

-- Get estimated_cost and function_impl from ITER runs
SHOW RUN PARAMETERS IN EXPERIMENT {experiment_name} RUN ITER_N;

-- Get the seed score and aggregate stats
SHOW RUN METRICS IN EXPERIMENT {experiment_name} RUN SEED;
SHOW RUN PARAMETERS IN EXPERIMENT {experiment_name} RUN SEED;
```

Key fields:
- From ITER/SEED run metrics: `test_score` — the authoritative score for frontier candidates (a metric on the run itself; there is no separate `TEST_*` run)
- From ITER run parameters: `function_impl` (the optimized function body), `model`, `estimated_cost`
- From SEED run parameters: `total_candidates`, `elapsed_seconds`
- From SEED run metrics: `valset_score` (seed validation score), `test_score` (seed test score if test table was used)

**Score domain selection — derive from the data, not from memory:**

After fetching metrics for all `is_frontier` runs:
- **If ALL have `test_score != NULL`** → use `test_score` domain. Apply a test-Pareto prune: remove any candidate that is dominated by another on both `estimated_cost` and `test_score` (i.e., another candidate has lower-or-equal cost and strictly higher test score). Present only the surviving candidates.
- **If ANY is missing `test_score`** (NULL or absent) → use `valset_score` domain. Present the full written frontier (already validation-Pareto-optimal by construction).

Do NOT guess which domain applies from conversation history or from whether a test table was mentioned. Always derive it from the metric values returned by `SHOW RUN METRICS`. Do NOT present `valset_score` when `test_score` is available.

**⚠️ DO NOT** query internal experiment stage files (`candidates.json.gz`, `gepa_state.bin.gz`, `run_dir/`, etc.) via `snow://experiment/...` paths. These are internal artifacts and their format is not stable. Use ONLY `SHOW RUN METRICS` and `SHOW RUN PARAMETERS` to retrieve optimization results.

**⚠️ DO NOT** estimate or approximate scores by visually inspecting side-by-side results. Always use the official scores from `SHOW RUN METRICS`.

**⚠️ DO NOT re-run `OPTIMIZE_AI_FUNCTION` to retrieve results for a specific model.** All model results are already stored in the experiment — query them with `SHOW RUN METRICS` / `SHOW RUN PARAMETERS` as shown above.

**Run names are global across all models.** Candidates from every model share one monotonic sequence — `SEED` and `ITER_1`, `ITER_2`, …, `ITER_N` — and the producing model is a run PARAMETER (not part of the run name). Do NOT embed model names in run names.

If you are unsure which runs exist, start with `SHOW RUNS IN EXPERIMENT {experiment_name}` to list all runs, then query each relevant run's metrics individually.

**Failed models:** If `SHOW RUNS` returns a `{MODEL}_FAILED` run for a model, that model's optimization failed. Report the failure to the user (query `SHOW RUN PARAMETERS` on the FAILED run for the `error_message`) and proceed with whichever other models completed successfully.

**⚠️ Do NOT stop here.** You may present a brief summary of the raw results, but you MUST continue through Steps 6.2–6.3 (notebook charts, user selection) before asking what to do next.

### Step 6.2: Result Charts

**Append charts to the function's notebook** before asking for user selection. If the notebook doesn't exist yet, create `{function_name}.ipynb` first using the notebook skeleton from `references/snowsight/core.md` § Notebook Harness and set `notebook_path = "{function_name}.ipynb"`.

The chart data comes from the frontier candidates (Step 6.1). The agent must fill in the template values below from those sources — do NOT hardcode or guess values.

**⚠️ Do NOT use `matplotlib.use('Agg')` in chart cells.** Just `import matplotlib.pyplot as plt` and call `plt.show()` — Snowsight notebooks render inline.

Use a single `notebook_action(action="add_cells", ...)` call to append all of the following cells:

1. **Markdown** — section header + summary:
   ```markdown
   # Optimization Results: {function_name}
   **Metric:** {metric_name} | **Budget:** {auto_budget} | **Run ID:** {run_id}
   ```

2. **Python** — bar chart comparing seed vs optimized scores per model (all models, not just Pareto-optimal):
   ```python
   import matplotlib.pyplot as plt

   models = ["{model_1}", "{model_2}", ...]
   seed_scores = [{seed_test_score_1}, ...]
   best_scores = [{best_test_score_1}, ...]

   x = range(len(models))
   width = 0.35
   fig, ax = plt.subplots(figsize=(10, 6))
   ax.bar([i - width/2 for i in x], seed_scores, width, label='Seed (Before)', color='#B0BEC5')
   ax.bar([i + width/2 for i in x], best_scores, width, label='Optimized (After)', color='#29B5E8')
   ax.set_ylabel('{metric_name} Score')
   ax.set_title('Optimization Improvement by Model')
   ax.set_xticks(list(x))
   ax.set_xticklabels(models, rotation=45, ha='right')
   ax.legend()
   ax.set_ylim(0, 1.05)
   plt.tight_layout()
   plt.show()
   ```

3. **Python** — Pareto frontier graph (accuracy vs relative cost). Use only Pareto-optimal models from the frontier candidates:
   ```python
   import matplotlib.pyplot as plt

   pareto_models = ["{model_1}", "{model_2}", ...]       # from frontier_candidates
   pareto_scores = [{score_1}, {score_2}, ...]             # test_score or score from frontier_candidates
   pareto_costs = [{estimated_cost_1}, {estimated_cost_2}, ...]  # estimated_cost from frontier_candidates

   fig, ax = plt.subplots(figsize=(10, 6))
   ax.scatter(pareto_costs, pareto_scores, s=120, c='#29B5E8', edgecolors='#1A3E5C', linewidths=1.5, zorder=5)
   sorted_pairs = sorted(zip(pareto_costs, pareto_scores))
   ax.plot([p[0] for p in sorted_pairs], [p[1] for p in sorted_pairs], '--', color='#29B5E8', alpha=0.5, zorder=3)
   for model, cost, score in zip(pareto_models, pareto_costs, pareto_scores):
       ax.annotate(model, (cost, score), textcoords='offset points', xytext=(8, 8), fontsize=9)
   ax.axhline(y={seed_test_score}, color='#B0BEC5', linestyle=':', label=f'Seed score ({seed_test_score:.1%})')
   ax.set_xlabel('Relative Cost (1.0 = cheapest)')
   ax.set_ylabel('{metric_name} Score')
   ax.set_title('Pareto Frontier: Accuracy vs Cost')
   ax.legend()
   plt.tight_layout()
   plt.show()
   ```

Run the newly added cells (see `references/snowsight/core.md` § Appending cells — apply §7 view-mode to all three cells first; both chart Python cells are plot-only). Tell the user the notebook has been updated with optimization charts.

**⚠️ Checkpoint:** If you have not created a notebook and added chart cells by this point, STOP — go back to Step 6.1. Do NOT proceed to Step 6.3 without the notebook.

### Step 6.3: Get User Selection

Present the frontier candidates as a cost-quality summary (model name, score, relative cost) and use `ask_user_question` to let the user pick which optimized configuration to apply — one option per Pareto-optimal result (showing model name, score, and relative cost), plus a "Let me review the charts first" option.

## Step 7: Apply Optimized Function

Ask user:
```
Apply the optimized function?

1. Yes - Replace the original function
2. Save as new function - Create a new function with suffix (e.g., MY_FUNC_OPTIMIZED)
3. No - Keep original
```

### Snowsight Deployment

**⚠️ DO NOT execute raw `CREATE OR REPLACE FUNCTION` DDL directly — even if `best_ddl` is available in the results.** The optimizer returns a `best_ddl` field, but in Snowsight you must always re-deploy through `CALL SNOWFLAKE.CORTEX.CREATE_AI_FUNCTION(...)` to ensure consistent metadata, tagging, and registration. The steps below show how to construct the correct CALL.

**Step-by-step:**

1. **Retrieve the optimized function body** from the experiment:
   ```sql
   -- Query the winning ITER run for the optimized function body.
   -- Use the run with the highest test_score (test domain) or highest valset_score
   -- (validation domain) per the score domain determined in Step 6.1:
   SHOW RUN PARAMETERS IN EXPERIMENT {experiment_name} RUN ITER_N;  -- N = winning iteration
   ```
   Extract the `function_impl` value from the result. Also extract the `model` value.

2. **Parse the optimized `function_impl`** to extract prompt components:
   - **System prompt**: the string value in the `OBJECT_CONSTRUCT('role', 'system', 'content', '...')` block
   - **User prompt template**: the string value in the `OBJECT_CONSTRUCT('role', 'user', 'content', ...)` block (typically just `INPUT_TEXT` or `{INPUT_COL}`)
   - **Model**: from the `model=>'...'` parameter (or from the `model` run parameter)
   - **Has SQL wrapping or `response_format`**: check if `function_impl` contains `response_format=>` or any SQL logic beyond a bare `AI_COMPLETE(...)` call (e.g., string manipulation, CTEs, CASE expressions)

3. **Determine deployment mode** based on the `function_impl` structure:

   **If the optimized body is a simple AI_COMPLETE call** (no `response_format`, no SQL pre/post-processing around it — just `AI_COMPLETE(model=>..., messages=>...)` optionally with a trailing `::VARCHAR` or `:field::VARCHAR` accessor):
   - Use **Direct mode** — pass the extracted system_prompt, user_prompt_template, and model into params 2–4

   **If the optimized body has `response_format`, SQL wrapping, or pre/post-processing:**
   - Use **Research mode** — pass empty strings for params 2–4, and construct a full `CREATE FUNCTION` DDL string for param 8
   - This is the one place in the post-optimization flow where the structure of the optimized body itself forces research-mode deployment (the optimizer produced SQL the Direct-mode SP cannot represent). Use research-mode deployment **only** when the optimized body genuinely cannot be expressed as a Direct-mode call — never as a stylistic preference. The `[CORTEX AI FUNC STUDIO]` comment-prefix rule below still applies and is non-negotiable.

4. **Construct the CALL statement:**

   **Direct mode:**
   ```sql
   USE {database}.{schema};

   CALL SNOWFLAKE.CORTEX.CREATE_AI_FUNCTION(
       '{database}.{schema}.{function_name}',
       '{model}',
       $${optimized_system_prompt}$$,
       $${optimized_user_prompt_template}$$,
       PARSE_JSON('[{inputs_inner}]'),
       PARSE_JSON('[{outputs_inner}]'),
       '{function_intention}',
       NULL,
       NULL
   );
   ```

   **Research mode** (when `response_format` or SQL wrapping is present):
   ```sql
   USE {database}.{schema};

   CALL SNOWFLAKE.CORTEX.CREATE_AI_FUNCTION(
       '{database}.{schema}.{function_name}',
       '', '', '',
       PARSE_JSON('[{inputs_inner}]'),
       PARSE_JSON('[{outputs_inner}]'),
       '{function_intention}',
       '{sql_body}',
       NULL
   );
   ```

   Where `{sql_body}` is the full `CREATE FUNCTION` DDL as a string (with single quotes doubled). **The DDL MUST include a `COMMENT = '[CORTEX AI FUNC STUDIO] <description>'` clause** — this prefix (with trailing space) is required verbatim on every SQL body the studio produces:
   ```sql
   CREATE OR REPLACE FUNCTION {database}.{schema}.{function_name}({original_params})
     RETURNS {original_return_type}
     LANGUAGE SQL
     COMMENT = '[CORTEX AI FUNC STUDIO] {short description of function intention}'
   AS
   $$
     {function_impl}
   $$
   ```
   Remember: param 8 uses single quotes (not `$$`), so double any `'` inside the DDL body (`'` → `''`) — including the single quotes around the `COMMENT` value. Before executing the `CALL`, verify the literal substring `[CORTEX AI FUNC STUDIO] ` appears inside the `SQL_BODY` string's `COMMENT` clause; if missing, fix the DDL first.

   **Reuse the original `inputs`, `outputs`, and `function_intention`** from the function's creation context (preserved in conversation state or re-derived from the original function's comment/metadata). When reusing the original `function_intention`, strip any existing `[CORTEX AI FUNC STUDIO] ` prefix before re-applying it in the templates above so the prefix is not duplicated.

5. **Show the CALL statement to the user** for review before executing. Do NOT auto-execute.

6. **Execute via `execute_sql`** once the user confirms.

**⚠️ DO NOT** attempt to retrieve the function body from internal experiment stage files (`candidates.json.gz`, `gepa_state.bin.gz`, etc.). Always use `SHOW RUN PARAMETERS`.

### Save as New Function

If the user selects "Save as new function", ask for a new function suffix (e.g., V2, OPTIMIZED, PROD). Modify the function name in the CALL statement to use the new name (`{function_base}_{function_suffix}`) and show the modified CALL to the user for review. Once confirmed, execute it.

## Step 8: Next Steps

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

If the user selects 1 → Load `create/SKILL.md` with context:
- Preserve `{database}`, `{schema}`, `{function_name}`, `{inputs}`, `{outputs}`, `{model}`
- Pass the current seed function body and error analysis so the create workflow can inform approach selection
- Note: *"The customer is re-creating this function with a different approach. Skip to Step 4 (Select Creation Mode) — task description, clarifications, inputs, and outputs are already known. Follow `create/SKILL.md`'s mode-selection rules: default to Direct mode unless the customer has EXPLICITLY asked for research mode, custom SQL, or SQL pre/post-processing. Selecting 'change the initial function structure' here is NOT itself an explicit request for research mode — if you think research mode is warranted, briefly offer it and wait for the customer to confirm before switching."*

If the user selects 2 → Ask the customer for a new `auto_budget` and optionally new `models`. Then re-run optimization from Step 5 of this file with the updated settings.

If the user selects 3:
Try to run evaluation on the optimized version and see what the error types are. Then, critically reason through the following:
1. Can this be solved with different pre-/post-processing?
2. Inspect optimization progression to see whether it's in the correct direction. Would a different seed function body solve this problem?
3. Is the current model just not strong enough? Should we try a stronger or different type of model?
After doing this analysis, help user identify whether they should run optimization with different effort level or re-create function with different settings.
