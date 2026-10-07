---
name: evaluate-ai-function
description: "Evaluate an AI function's performance against a labeled dataset using a Python stored procedure."
parent_skill: cortex-ai-function-studio
---
<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Evaluate AI Function

## When to Load

Load from main skill when user intent matches EVALUATE: "evaluate", "test", "measure", "score".

## Critical: Snowsight Stored Procedure

**In Snowsight, evaluation MUST use `CALL SNOWFLAKE.CORTEX.EVALUATE_AI_FUNCTION(...)` with exactly 12 positional parameters.** The procedure name is `EVALUATE_AI_FUNCTION` — not `AI_FUNC_EVALUATE`, not `AI_FUNCTION_EVALUATE`, not named `=>` parameters. See Step 4 "Running the Evaluation" for the exact template.

## Information Model

| Field | Required | Default | Confirm | Dependencies |
|-------|----------|---------|---------|--------------|
| `function_name` | Yes | - | No | - |
| `function_model` | Yes | (extracted) | No | function_name |
| `test_table` | Yes | - | No | - |
| `input_columns` | Yes | - | **Yes** | test_table |
| `label_column` | Yes | - | **Yes** | test_table |
| `sample_size` | No | all | No | - |
| `metric_name` | Yes | - | **Yes** | - |
| `experiment_name` | No | `{run_id}` | No | - |

**Critical fields** (always confirm even if pre-provided): `input_columns`, `label_column`, `metric_name`

**Simple fields** (accept silently if pre-provided): `function_name`, `test_table`, `sample_size`, `experiment_name`

## Pre-Collection

Before prompting, scan the user's initial message and any prior context for already-provided information:

1. **Function name**: Look for fully qualified names like `DB.SCHEMA.FUNCTION_NAME`
2. **Test table**: Look for table references like `DB.SCHEMA.TABLE`
3. **Column mappings**: Look for phrases like "input column X", "label column Y", "map X to Y"
4. **Metric**: Look for evaluation metrics like "exact_match" or "llm_judge". Note these are not the only names, and users can build custom evaluation metrics. If you aren't sure, ask the user. 

For each piece found:
- **Simple fields**: Accept silently, proceed without re-asking
- **Critical fields**: Present for confirmation even if pre-provided ("I see you want to use columns X, Y — confirm?")

## Workflow

### Step 1: Get AI Function

**If `function_name` already collected** (user provided function name upfront):
- Skip the prompt — proceed directly to validation
- Acknowledge: "I'll evaluate `{function_name}`"

**If not collected**, ask user:
```
What AI function would you like to evaluate?

Provide the fully qualified function name (e.g., DB.SCHEMA.FUNCTION_NAME)
```

Validate function exists:
```sql
DESCRIBE FUNCTION <function_name>;
```

If not found confirm name or redirect to `create/SKILL.md` first.

**Extract the model from the function's definition** for use in evaluation tracking. `DESCRIBE FUNCTION` returns a `body` property with the function's SQL body (and needs only USAGE on the function, unlike `GET_DDL` which requires ownership):
```sql
DESCRIBE FUNCTION <function_name>(<param_types>);
```

Read the `body` property to find the model name hardcoded in the function body. The model appears as a string literal in the AI_COMPLETE call:
```
model=>'model-name'
```

Store this as `{function_model}` for use when calling EVALUATE_AI_FUNCTION.

### Step 2: Get Test Data Table

**If `test_table` already collected** (user provided table name upfront):
- Skip to table validation, acknowledge: "I'll use `{test_table}` for evaluation"

**If coming from optimize workflow:** Pre-populate with the test table used during optimization:
```
The optimize workflow used test table: {test_table_from_optimize}
For consistent results, we recommend using the same test data.
Confirm this table? (y/n) If no, provide a different table name.
```

**If returning from synthetic data generation or pseudo-label generation:** After data has been created, you MUST confirm which table to use:
```
Data generation complete.

Which table would you like to use for evaluation?
1. **Use the generated table** - {generated_table_name}
2. **Specify a different table** - I have another table to use
```

**Otherwise**, ask:
```
How would you like to get evaluation data?
1. **Existing table** — I have a labeled test table
2. **Generate test data** — Create synthetic examples with AI
3. **Generate labels** — I have inputs but no expected outputs
```

- If **Existing table**: ask for the table name, then proceed to table validation below.
- If **Generate test data** or **Generate labels**: **Load** `synthetic-data/SKILL.md`. Keep function context from Step 1.
- If the user needs help splitting or mapping an existing table: **Load** `references/data_preparation.md` with context `workflow: "evaluate"`.

After data preparation completes, validate the table:
```sql
DESCRIBE TABLE <table_name>;
SELECT COUNT(*) AS row_count FROM <table_name>;
```
Store the column list from the DESCRIBE output — you will need it for column mapping validation below.

**If `input_columns` and `label_column` already collected** (user provided column mappings upfront):
- Present for confirmation (critical fields): "I'll use input columns `{input_columns}` and label column `{label_column}` — confirm?"

**Otherwise:** Follow column mapping in `references/data_preparation.md` Step 4.

**⚠️ STOP**: Always confirm column mapping before proceeding (critical fields).

After confirmation, **Load** `references/data_preparation.md` Step 5 to validate that all mapped columns exist in the relevant tables. Do NOT proceed if columns don't match.

**⚠️ Column mismatch handling**: If any mapped column does not exist in the test table, you MUST present the mismatch to the user via `ask_user_question` (not prose text). Include the mismatched column names, the actual table columns, and remediation options. Do NOT silently remap or proceed — always surface the mismatch through `ask_user_question` so the user can decide.

**Multi-key output handling:** If the user's test table has multiple truth columns that correspond to keys in a multi-key function output (e.g., separate `SENTIMENT`, `CONFIDENCE` columns instead of a single VARIANT), help them combine these into a single VARIANT `label_column` using `OBJECT_CONSTRUCT` in a view before evaluation. See `references/data_preparation.md` "Multi-Column Truth Aggregation" for the SQL pattern.

### Step 3: Configure Evaluation

**If `sample_size` already collected**, skip this step. Use defaults for any not provided: sample_size=all.

**If not collected**, ask user:
```
Evaluation configuration:

- Sample size: [all] - Number of rows to evaluate (or 'all')
```

**Experiment Convention:** Per-row evaluation details are persisted as `eval_detail.json` in a per-evaluation **Snowflake Experiment**. By default the experiment is named after the auto-generated `run_id` (e.g., `ai_func_eval_MY_FUNC_1739919133000`); each evaluation produces its own experiment. The single run inside is named `EVAL`, so the queryable artifact is always at `snow://experiment/{experiment_name}/versions/EVAL/eval_detail.json`. Reading these files requires the server-side parameter `ENABLE_EXPERIMENT_SNOWURL_READ_PATH_RESOLUTION` to be enabled.

**Querying eval_detail.json — required pattern:** Always create a named JSON file format first (the inline `(FILE_FORMAT => (TYPE => JSON))` syntax is **not** supported on SnowURL paths). Use a `TEMPORARY` file format so it auto-cleans at session end:

```sql
CREATE OR REPLACE TEMPORARY FILE FORMAT eval_detail_json_fmt
  TYPE = JSON
  STRIP_OUTER_ARRAY = TRUE;
```

Then reference it from `SELECT ... FROM 'snow://...'` (string literal, no `@` prefix):
```sql
SELECT $1:row_id::INT AS ROW_ID, $1:metric_score::FLOAT AS SCORE
FROM 'snow://experiment/{experiment_name}/versions/EVAL/eval_detail.json'
(FILE_FORMAT => eval_detail_json_fmt);
```

Note: The metric is selected at runtime when calling the SPROC, not at creation time.

### Step 4: Run Evaluation

**Load** `references/metrics.md` and present the metric selection prompt.

**⚠️ In Snowsight, you MUST use `ask_user_question` with the exact options from `references/metrics.md`.** Do NOT infer the metric from the task type or prior context — always present the full 6-option menu and let the user choose. Do NOT skip this step even if the task seems obvious (e.g., do NOT auto-select "semantic_similarity", "bertscore", or any metric not in the list).

**If user chooses "Create custom metric" (option 6):**
**Load** `references/custom_metrics.md` with context:
- Preserve function name: `{function_name}`
- Preserve test table: `{test_table}`
- Preserve column mappings: `{input_columns}`, `{label_column}`
- Note: *"After creating your custom metric, we'll return here to run the evaluation."*

After custom metric creation completes, return to this step with the new metric name.

**Custom Metric Loading:** Custom metrics are implemented as Python UDFs in Snowflake. Pass the fully qualified UDF name as the `CUSTOM_METRIC_UDF` parameter. The SPROC calls the UDF directly via SQL.

**Otherwise**, execute with the selected metric:

#### Execution Mode

**Default to sync execution.** Use `timeout_seconds: 14400` (4 hours) to prevent the query from timing out. Async execution is available for large datasets (500+ rows) or complex metrics — only use it if the user explicitly requests it.

**Sync execution** (default): Calls the stored procedure directly and returns results inline.

**Async execution** (only when explicitly requested): Wraps the stored procedure call in a Snowflake Task for background execution. If the user requests async, ask about timeout (default: 240 minutes).

#### Running the Evaluation

**If `environment == snowsight`:**

Call the first-party stored procedure directly. Execute via `execute_sql` tool with `timeout_seconds: 14400`.

**Sync execution (Snowsight):**

**⚠️ ALL 12 positional parameters are required.** Do NOT collapse parameters into a single JSON object. Do NOT skip or reorder parameters. **Always set database/schema context first** to avoid session errors. Follow this exact template:

```sql
USE {database}.{schema};

CALL SNOWFLAKE.CORTEX.EVALUATE_AI_FUNCTION(
    '{database}.{schema}.{function_name}',   -- 1. FUNCTION_NAME (VARCHAR)
    '{test_table}',                           -- 2. TEST_TABLE (VARCHAR)
    ARRAY_CONSTRUCT('{input_col1}', '{input_col2}'),  -- 3. INPUT_COLUMNS (ARRAY)
    '{label_column}',                         -- 4. LABEL_COLUMN (VARCHAR)
    '{metric_name}',                          -- 5. METRIC_NAME (VARCHAR)
    '{function_model}',                       -- 6. MODEL_NAME (VARCHAR)
    {sample_size_or_NULL},                    -- 7. SAMPLE_SIZE (INTEGER or NULL)
    {experiment_name_or_NULL},                -- 8. EXPERIMENT_NAME (VARCHAR or NULL)
    {metric_options_or_NULL},                 -- 9. METRIC_OPTIONS (VARIANT or NULL)
    500,                                      -- 10. MAX_LENGTH (INTEGER)
    {custom_metric_udf_or_NULL},              -- 11. CUSTOM_METRIC_UDF (VARCHAR or NULL)
    {run_id_or_NULL}                          -- 12. RUN_ID (VARCHAR or NULL)
);
```

**Concrete example** — evaluating with exact_match:

```sql
USE MY_DB.MY_SCHEMA;

CALL SNOWFLAKE.CORTEX.EVALUATE_AI_FUNCTION(
    'MY_DB.MY_SCHEMA.CLASSIFY_SENTIMENT',
    'MY_DB.MY_SCHEMA.TEST_DATA',
    ARRAY_CONSTRUCT('TEXT'),
    'EXPECTED',
    'exact_match',
    'claude-sonnet-4-6',
    NULL,
    NULL,
    NULL,
    500,
    NULL,
    NULL
);
```

Parameter notes:
- **Param 3 `INPUT_COLUMNS`**: `ARRAY_CONSTRUCT(...)` with one string per column name — e.g., `ARRAY_CONSTRUCT('TEXT', 'CATEGORY')`
- **Param 5 `METRIC_NAME`**: one of `'exact_match'`, `'fuzzy_match'`, `'contains_match'`, `'redaction_match'`, `'llm_judge'`
- **Param 6 `MODEL_NAME`**: the model used by the function (for metadata tracking); also used as the judge model for `llm_judge`
- **Param 9 `METRIC_OPTIONS`**: `PARSE_JSON('{"threshold": 0.85}')` for fuzzy_match, `PARSE_JSON('{"task_description": "..."}')` for llm_judge. Pass `NULL` when not needed.
- **Param 11 `CUSTOM_METRIC_UDF`**: pass as a string — e.g., `'DB.SCHEMA.MY_METRIC'`
- Pass `NULL` (not the string `'none'`) for all unused optional parameters

Returns `VARIANT` — `{"score": <float 0.0-1.0>, ...}`. Extract `score` from the result.

**Async execution (Snowsight) — only when explicitly requested:**

Generate `run_id` as `ai_func_eval_{FUNC_SHORT_NAME}_{timestamp_ms}`. Default `experiment_name` = `run_id`.

Before constructing the Task DDL, **resolve the warehouse name**: run `SELECT CURRENT_WAREHOUSE() AS WH;` via `execute_sql`. If NULL, use `ask_user_question` to ask: `"No active warehouse detected. Which warehouse should I use for this evaluation task?"` — use the user's response as `{warehouse}`.

```sql
USE {database}.{schema};

CREATE OR REPLACE TASK {database}.{schema}.{run_id}
    WAREHOUSE = {warehouse}
    USER_TASK_TIMEOUT_MS = 14400000
AS
    CALL SNOWFLAKE.CORTEX.EVALUATE_AI_FUNCTION(
        '{database}.{schema}.{function_name}',
        '{test_table}',
        ARRAY_CONSTRUCT('{input_col1}', '{input_col2}'),
        '{label_column}',
        '{metric_name}',
        '{function_model}',
        {sample_size_or_NULL},
        '{experiment_name}',
        {metric_options_or_NULL},
        500,
        {custom_metric_udf_or_NULL},
        '{run_id}'
    );

EXECUTE TASK {database}.{schema}.{run_id};
```

For async, `EXPERIMENT_NAME` and `RUN_ID` are required (the agent cannot read the CALL return from a Task).

**If `environment == cli`:**

Run the evaluation script. It generates a `CALL EVALUATE_AI_FUNCTION(...)` stored procedure (anonymous SPROC) and executes it in a single Snowpark session. When showing SQL to users, always reference this `EVALUATE_AI_FUNCTION` SPROC name — do NOT invent manual SQL or alternative evaluation approaches. **Always pass every flag** — use `none` for unused optional parameters. For sync execution, use `timeout_seconds: 14400` (4 hours) to prevent the query from timing out.

```bash
PYTHONPATH=<SKILL_DIRECTORY>/scripts uv run --project <SKILL_DIRECTORY> python <SKILL_DIRECTORY>/scripts/run.py evaluate \
    --database {database} \
    --schema {schema} \
    --connection <CONNECTION_NAME> \
    --function-name {database}.{schema}.{function_name} \
    --test-table {test_table} \
    --input-columns {input_col1} {input_col2} \
    --label-column {label_column} \
    --metric-name {metric_name} \
    --model-name {function_model} \
    --sample-size none \
    --experiment-name none \
    --metric-options none \
    --max-length 500 \
    --custom-metric-udf none \
    --run-id none
    # For async execution, also append:
    #   --async --warehouse {warehouse} --timeout-minutes {timeout_minutes}
```

`--experiment-name none` lets the server auto-generate the experiment from `run_id`. Pass an explicit name only if you want to reuse an existing experiment.

Run `run.py evaluate --help` to see all flags and their descriptions.

#### Sync Output

**Snowsight:** The CALL returns `VARIANT` — `{"score": <float 0.0-1.0>, ...}`. Extract the `score` and `experiment_name` directly from the CALL return value. This is the **only** result you need to present. Do NOT search for results tables, stages, or other storage — the score is in the return value.

**⚠️ Always report the official score from the CALL return or `SHOW RUN METRICS`.** Do NOT estimate, approximate, or visually inspect results to guess a score.

**⚠️ DO NOT** call non-existent procedures (e.g., `GET_EVALUATION_RESULTS`), query tables named `*_EVAL_RESULTS`, or `LIST` internal stages to find per-row results. Per-row details are **only** available via SnowURL (see Step 5) and may not be accessible if the server-side parameter is not enabled. If SnowURL queries fail, present just the aggregate score and move on.

**CLI:** The script prints a JSON result to stdout:
```json
{
  "status": "success",
  "score": 0.85,
  "metric": "exact_match",
  "function": "DB.SCHEMA.MY_FUNC",
  "run_id": "ai_func_eval_MY_FUNC_1739919133000",
  "experiment_name": "ai_func_eval_MY_FUNC_1739919133000",
  "snowurl": "snow://experiment/ai_func_eval_MY_FUNC_1739919133000/versions/EVAL/eval_detail.json",
  "num_examples": 50
}
```

#### Async Output

**Snowsight:** The Task is created and executed. The agent must track the `run_id` and `experiment_name` that were passed to the CALL (since the Task return is not directly accessible).

**CLI:** The script creates a Snowflake Task whose body is the anonymous SPROC (with inlined Python) + CALL. No named procedures are created.
```json
{
  "status": "submitted",
  "run_id": "ai_func_eval_MY_FUNC_1739919133000",
  "task": "DB.SCHEMA.ai_func_eval_MY_FUNC_1739919133000",
  "experiment_name": "ai_func_eval_MY_FUNC_1739919133000",
  "snowurl": "snow://experiment/ai_func_eval_MY_FUNC_1739919133000/versions/EVAL/eval_detail.json"
}
```

**⚠️ WAREHOUSE NOTE**: If the Task creation fails or the script returns `{"status": "error", ...}`, it likely means the current role lacks a direct USAGE grant on the target warehouse. Snowflake Tasks require an explicit grant — session-level access via role hierarchy is not sufficient. Display the error to the user with the `GRANT` command needed and instructions for finding usable warehouses.

**⚠️ IMPORTANT**: Display the run_id and SnowURL prominently to the user:

```
Evaluation started in background!

RUN_ID: {run_id}
EXPERIMENT: {experiment_name}

Save these to track your evaluation.

Check status:  See references/async_status.md
View results:
  CREATE OR REPLACE TEMPORARY FILE FORMAT eval_detail_json_fmt
    TYPE = JSON STRIP_OUTER_ARRAY = TRUE;
  SELECT $1
  FROM 'snow://experiment/{experiment_name}/versions/EVAL/eval_detail.json'
  (FILE_FORMAT => eval_detail_json_fmt);
```

**Load** `references/async_status.md` if user wants to check status.

**Cleanup after async completes:** Follow `references/async_status.md` § Cleanup for task verification and cleanup SQL. The Snowflake Experiment persists across Task cleanup so users can keep querying `eval_detail.json`.

**Eval Detail Artifact:**

The SPROC creates a per-evaluation Snowflake Experiment (default name = `run_id`) with a single run named `EVAL`. Per-row evaluation details are uploaded as `eval_detail.json` to the run's nested stage at `snow://experiment/{experiment_name}/versions/EVAL/eval_detail.json`. Each JSON record carries:

| Key | Type | Description |
|-----|------|-------------|
| `row_id` | INTEGER | Row number from test data |
| `input_text` | STRING | Input values summary |
| `expected` | STRING | Expected output |
| `predicted` | STRING | Model's prediction |
| `metric_score` | FLOAT | Score for this row (0.0-1.0) |
| `metric_feedback` | STRING | Metric feedback explaining the score |
| `error_message` | STRING | Error message if evaluation failed |
| `metric_name` | STRING | Name of the metric used |
| `model_name` | STRING | Model name used |
| `split` | STRING | Always `"test"` for standalone EVALUATE |

The aggregate score, function name, model, sample size, and elapsed time are stored as run metrics/parameters and queryable via `SHOW RUN METRICS / SHOW RUN PARAMETERS IN EXPERIMENT {experiment_name} RUN EVAL`.

**Note on VARIANT data:** `expected` and `predicted` are stringified. When the function returns VARIANT (multi-output) or the label column is VARIANT (e.g., from synthetic data), values are serialized to JSON strings. To access fields in result queries, use `PARSE_JSON($1:expected):key` or `PARSE_JSON($1:predicted):key` after selecting from the SnowURL.

**Metric Optional Parameters via `metric_options`:**

| Metric | Option | Type | Default | Description |
|--------|--------|------|---------|-------------|
| fuzzy_match | threshold | FLOAT | 0.85 | Minimum similarity score |
| llm_judge | task_description | VARCHAR | '' | Task context for the judge |

### Step 5: Present Results

**If `environment == snowsight`:** Present the aggregate score from the CALL return value. Then load `references/snowsight/evaluate.md` and follow its **"Results Notebook (Step 5)"** section to append results to the notebook. Do NOT dump results as chat-only output — the notebook is required for result display in Snowsight.

Display the returned score:
```
Evaluation Results
==================

Function: {function_name}
Metric: {metric_name}
Test Size: {n} examples
Eval ID: {run_id}

Average Score: {score:.1%}
```

This is the primary result. Present it immediately — do NOT delay showing the score while searching for per-row details.

**Per-row details (optional — may not be available):**

Per-row evaluation details are stored in the experiment as `eval_detail.json` via SnowURL. These require the server-side parameter `ENABLE_EXPERIMENT_SNOWURL_READ_PATH_RESOLUTION` to be enabled. **If SnowURL queries fail with a parse or resolution error, skip per-row details and present only the aggregate score. Do NOT search for results in tables, stages, or non-existent stored procedures.**

If SnowURL is available, use the same query pattern from Step 3 (create `eval_detail_json_fmt`, then `SELECT $1:row_id, $1:input_text, $1:expected, $1:predicted, $1:metric_score, $1:metric_feedback FROM 'snow://experiment/{experiment_name}/versions/EVAL/eval_detail.json'`). Add `WHERE $1:metric_score::FLOAT < 1 ORDER BY SCORE` for failure analysis.

**If `environment == cli`:**

Display the returned score (same format as above).

**Detailed results:**
```
Detailed results saved to experiment: {experiment_name}
Evaluation ID: {run_id}
SnowURL: snow://experiment/{experiment_name}/versions/EVAL/eval_detail.json

Compare evaluation runs (each run is its own experiment):
  SHOW EXPERIMENTS LIKE 'ai_func_eval_{FUNCTION_NAME}_%' IN SCHEMA {database}.{schema};
  SHOW RUN PARAMETERS IN EXPERIMENT {database}.{schema}.{experiment_name} RUN EVAL;
  SHOW RUN METRICS    IN EXPERIMENT {database}.{schema}.{experiment_name} RUN EVAL;
```

### Step 6: Next Steps

Present to user:
```
Evaluation complete!

**Recommended next step:** Optimize your function to improve its performance. The optimizer will automatically tune the entire function body -- prompts, model references, and SQL pre/post-processing -- and help you find the best model for your cost/quality tradeoffs.

What would you like to do?
1. **Optimize** (recommended) - Improve the function through function body optimization and model selection
2. **Done** - Exit for now
```

If optimize → Load `optimize/SKILL.md` with context:
- Preserve function name and column mappings
- Pass the test table used: `{test_table}`
- Note: *"For consistent comparison, use this same test table as your held-out test set in the optimize workflow."*

## Stopping Points

Critical confirmations (always stop, even if pre-provided):
- ✋ Step 2: Confirm column mapping (input_columns, label_column)

Optional confirmations:
- ✋ Step 5: After presenting results

## Output

- Average score returned (float between 0.0 and 1.0)
- Detailed results table (optional) for debugging
- No persistent artifacts — Python code is inlined into the anonymous SPROC
