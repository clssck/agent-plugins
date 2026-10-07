---
name: synthetic-data
description: "Generate synthetic data or pseudo-label input-only tables for AI function evaluation and optimization. Triggers: generate data, synthetic data, test data, create test cases, make training data, pseudo label, label my input-only table."
parent_skill: cortex-ai-function-studio
---
<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Synthetic Data Generation for AI Functions

Generate realistic data for evaluating and optimizing AI functions.

## Automated Generation (Recommended)

Use the `GENERATE_SYNTHETIC_DATA` stored procedure for server-side data generation using Cortex LLM.

### When to Use

Load this sub-skill when user intent involves: "generate data", "synthetic data", "test data", "create test cases", "make training data", "pseudo label", or "label my input-only table".

### Workflow

Follow these steps sequentially when generating synthetic data.

#### Step 1: Infer Task Description (Preferred)

**IMPORTANT**: The GENERATE_SYNTHETIC_DATA procedure requires a **task description** string, NOT a function name.

When an AI function is already known in context (for example from optimize/evaluate workflows, or when the user named the function in their initial message), **do not ask the user to retype intention**. Infer `task_description` in this order:

1. Function `COMMENT` (intention text)
2. System prompt from function DDL (fallback)

If the user named the function up front and inference succeeds, announce the inferred description and proceed without stopping for confirmation. Otherwise (interactive setup with no function context), present a brief confirmation prompt:

```
I inferred this task description from your function metadata:
{inferred_task_description}

Use this task description? (y/n) If no, provide an updated description.
```

Only if inference fails (no comment and no usable prompt), ask the user for a task description:
```
Describe the task your AI function performs. This guides synthetic test-case generation.

Example: "Classify customer support tickets into categories: billing, technical, account, general. Return the category and priority level."
```

Store the final value as `task_description`.

#### Step 2: Collect Input Columns & Output Schema

Ask the user:
```
What are the input columns (in function argument order)?
What is the output schema for the function? Provide either:
  - An OUTPUT_SCHEMA (JSON object with "properties"), or
  - A FUNCTION_NAME of an existing structured AI function (schema will be inferred from its response_format)

Example:
- Input columns: CLAIM, DOCUMENTS
- Output schema: {"properties": {"VERDICT": {"type": "string"}, "RATIONALE": {"type": "string"}, "EVIDENCE": {"type": "string"}, "CONFIDENCE": {"type": "number"}}}
```

Store `input_columns`. For the SQL call, format as comma-separated, single-quoted values:
`input_columns_csv = 'CLAIM', 'DOCUMENTS'`.
Store `output_schema` as a JSON object, or `function_name` if inferring from an existing function.

**Pass `--function-name` whenever the target function already exists or any input column is semi-structured (`ARRAY`, `VARIANT`, `OBJECT`).** Do not rely on `--output-schema` alone in those cases — only the function DDL exposes per-parameter types, which the generator needs in order to emit valid JSON values for each semi-structured input (e.g. a JSON array like `["billing","tech"]` for `ARRAY`, a JSON object like `{"author":"...","date":"..."}` for `OBJECT`) instead of degenerate comma-separated strings. Skipping `--function-name` will silently produce malformed data that fails downstream evaluate/optimize.

#### Step 3: Collect Output Table

Ask the user:
```
What is the fully qualified table name where synthetic data should be stored?

Example: MY_DB.MY_SCHEMA.SYNTHETIC_DATA
```

Store as `output_table`.

#### Step 4: Collect Model

**Load** `references/model_selection.md` and follow its full workflow, biasing toward the strongest available model since synthetic data quality depends heavily on model capability.

Store as `model`. Default: `claude-opus-4-7`

#### Step 5: Execute Generation

**If `environment == snowsight`:**

Call the first-party stored procedure directly. Execute via `execute_sql` tool with `timeout_seconds: 14400`.

**⚠️ ALL 9 positional parameters are required.** Do NOT collapse parameters into a single JSON object. Do NOT skip or reorder parameters. **Always set database/schema context first.**

```sql
USE {database}.{schema};

CALL SNOWFLAKE.CORTEX.GENERATE_SYNTHETIC_DATA(
    '{task_description}',                    -- 1. TASK_DESCRIPTION (VARCHAR)
    '{output_table}',                        -- 2. OUTPUT_TABLE (VARCHAR)
    ARRAY_CONSTRUCT('{col1}', '{col2}'),     -- 3. INPUT_COLUMNS (ARRAY)
    '{model}',                               -- 4. MODEL (VARCHAR or NULL)
    {num_examples},                          -- 5. NUM_EXAMPLES (INTEGER)
    NULL,                                    -- 6. SOURCE_TABLE (NULL for synthetic mode)
    {function_name_or_NULL},                 -- 7. FUNCTION_NAME (VARCHAR or NULL)
    {PARSE_JSON_output_schema_or_NULL},      -- 8. OUTPUT_SCHEMA (VARIANT or NULL)
    NULL                                     -- 9. MAX_SOURCE_ROWS (NULL for synthetic mode)
);
```

**Concrete example:**

```sql
USE MY_DB.MY_SCHEMA;

CALL SNOWFLAKE.CORTEX.GENERATE_SYNTHETIC_DATA(
    'Classify customer support tickets into categories like billing, technical, or general',
    'MY_DB.MY_SCHEMA.SYNTHETIC_TICKETS',
    ARRAY_CONSTRUCT('TICKET_TEXT'),
    'claude-opus-4-7',
    50,
    NULL,
    NULL,
    PARSE_JSON('{"type":"object","properties":{"CATEGORY":{"type":"string","description":"billing, technical, or general"}}}'),
    NULL
);
```

Parameter notes:
- **Param 3 `INPUT_COLUMNS`**: `ARRAY_CONSTRUCT(...)` with column names in function argument order
- **Param 4 `MODEL`**: required for synthetic mode (e.g., `'claude-opus-4-7'`). For pseudo-label mode, pass `NULL` to default to `claude-opus-4-7`.
- **Param 8 `OUTPUT_SCHEMA`**: `PARSE_JSON('{"type":"object","properties":{"LABEL":{"type":"string","description":"..."}}}')`. Do NOT pass as a plain string — must use `PARSE_JSON()`.
- **Param 7 `FUNCTION_NAME`**: pass as a string — e.g., `'DB.SCHEMA.CLASSIFY_TICKETS'`
- Pass `NULL` (not the string `'none'`) for all unused optional parameters
- At least one of `FUNCTION_NAME` or `OUTPUT_SCHEMA` must be non-NULL

Returns `VARIANT` — `{"success": true, "mode": ..., "total_generated": ..., ...}`. Extract `total_generated`, `output_table`, `expected_keys`, `model_used` from the result.

**If `environment == cli`:**

Run the generation script directly. It renders the anonymous SPROC, appends the CALL, and executes everything in a single Snowpark session. **Always pass every flag** — use `none` for unused optional parameters:

```bash
PYTHONPATH=<SKILL_DIRECTORY>/scripts uv run --project <SKILL_DIRECTORY> python <SKILL_DIRECTORY>/scripts/run.py synthetic \
    --database {database} \
    --schema {schema} \
    --connection {connection} \
    --task-description "{task_description}" \
    --output-table {output_table} \
    --input-columns {input_columns...} \
    --model {model} \
    --num-examples 50 \
    --source-table none \
    --function-name {function_name or none} \
    --output-schema {output_schema_json or none} \
    --max-source-rows none
```

| Flag                  | Description                                                                                       |
|-----------------------|---------------------------------------------------------------------------------------------------|
| `--database`          | Database for the anonymous SPROC context                                                          |
| `--schema`            | Schema for the anonymous SPROC context                                                            |
| `--connection`        | Snowflake connection name from `connections.toml`                                                 |
| `--task-description`  | Description of the AI function task (NOT a function name). Guides generation.                     |
| `--output-table`      | Fully qualified table name for generated data (e.g., `DB.SCHEMA.SYNTHETIC_DATA`)                 |
| `--input-columns`     | Space-separated input column names in argument order                                              |
| `--model`             | Cortex model for generation, or `none` to use default (`claude-opus-4-7`)                        |
| `--num-examples`      | Total number of examples to generate (default: 50)                                                |
| `--source-table`      | Existing input-only table for pseudo-label mode, or `none` for synthetic generation               |
| `--function-name`     | Existing function to infer output schema from, or `none`                                          |
| `--output-schema`     | JSON output schema string (e.g., `'{"properties":{"LABEL":{"type":"string"}}}'`), or `none`      |
| `--max-source-rows`   | Row cap for pseudo-label preview, or `none` to process all rows                                   |

The script prints a JSON result to stdout:
```json
{"status": "success", "result": {...}, "output_table": "DB.SCHEMA.SYNTHETIC_DATA"}
```

**Note**: `--input-columns` is required. Output shape must be provided via `--output-schema` or `--function-name` (at least one must not be `none`).
**Note**: Outputs are generated under an `outputs` key (JSON object) with keys matching the schema properties.

#### Step 6: Show Results

**If `environment == snowsight`:** Do not stop after printing the output table or preview SQL. Load `references/snowsight/synthetic_data.md` and follow its **"Preview Notebook (Step 6)"** section immediately after generation succeeds. Use the collected `output_schema` (or the schema inferred from `function_name`) and the script result fields (`output_table`, plus `result.total_generated`, `result.model_used`, and `result.expected_keys`) to append and run a notebook preview with:
- a markdown summary cell
- a SQL data preview cell
- a Python `matplotlib` visualization cell

The Python visualization cell is required. If the supporting aggregation query returns no rows, still add the chart cell with an empty literal so the notebook shows the friendly empty state instead of silently omitting the graph.

**If `environment == cli`:**
Display the results to the user, including the row count and output table name so they know the workflow finished:

```
Synthetic data generation complete! Created {total_generated} examples in {output_table}.

Output table: {output_table}
Total examples generated: {total_generated}

You can view your data with:
  SELECT * FROM {output_table} LIMIT 10;

The table has the following columns:
  - ID: Auto-incrementing identifier
  - Input columns: One VARCHAR column per input specified by `INPUT_COLUMNS`
  - EXPECTED: VARIANT column containing JSON object with keys from the output schema

Note: The EXPECTED column is VARIANT (JSON object), not VARCHAR. The evaluate and optimize
pipelines handle this automatically — they convert both EXPECTED and PREDICTED to strings
internally. No manual casting is needed when passing this table to evaluate/optimize.

To access individual expected values:
  SELECT EXPECTED:key_name FROM {output_table};
```

If there were batch errors, report them but note that partial data may still be usable.

#### Step 7: Continue

Ask the user what they want to do next:

```
What would you like to do next?

1. **View the data** - Preview the generated examples
2. **Evaluate** - Run your AI function against this data
3. **Optimize** - Use this data to optimize your AI function's prompt
4. **Generate more** - Create additional synthetic data
5. **Done** - Finished with data generation
```

Route based on selection:
- View: Execute `SELECT * FROM {output_table} LIMIT 10;`
- Evaluate: Load `evaluate/SKILL.md`
- Optimize: Load `optimize/SKILL.md`
- Generate more: Return to Step 1
- Done: End workflow

---

## Pseudo-Label Input-Only Tables

Use this flow when the user already has input rows but no expected labels.

### When to Use

- Evaluate or optimize workflows require labeled data, but source table is input-only.
- User wants labels generated and reviewed before full run, with optional model override.

### Requirements

- No pre-existing function is required.
- Define output shape via `OUTPUT_SCHEMA` (JSON object with `properties`) or `FUNCTION_NAME` (infers schema from an existing structured function's `response_format`).

### Pseudo-Label Workflow

1. Confirm source table and input columns.
2. Confirm task description for expected-label generation.
3. Define output shape (`OUTPUT_SCHEMA` or `FUNCTION_NAME`).
4. Choose destination labeled table (same customer schema).
5. Choose pseudo-label model (default `claude-opus-4-7`; allow user override).
6. Run a preview with a small row cap.
7. Show preview (`INPUT_*`, `EXPECTED`) and allow revise/regenerate.
8. On approval, run full labeling (all rows) and overwrite destination table.
9. Continue to evaluate/optimize with:
   - `label_column` = `EXPECTED`
   - `input_columns` unchanged

### Preview Call (sample rows)

**If `environment == snowsight`:**

```sql
USE {database}.{schema};

CALL SNOWFLAKE.CORTEX.GENERATE_SYNTHETIC_DATA(
    '{task_description}',
    '{output_table}',
    ARRAY_CONSTRUCT('{col1}', '{col2}'),
    NULL,
    50,
    '{source_table}',
    {function_name_or_NULL},
    {PARSE_JSON_output_schema_or_NULL},
    20
);
```

Execute via `execute_sql` tool with `timeout_seconds: 14400`.

**If `environment == cli`:**

Run the same script with `--source-table` and `--max-source-rows` to cap the preview:

```bash
PYTHONPATH=<SKILL_DIRECTORY>/scripts uv run --project <SKILL_DIRECTORY> python <SKILL_DIRECTORY>/scripts/run.py synthetic \
    --database {database} \
    --schema {schema} \
    --connection {connection} \
    --task-description "{task_description}" \
    --output-table {output_table} \
    --input-columns {input_columns...} \
    --model none \
    --num-examples 50 \
    --source-table {source_table} \
    --function-name {function_name or none} \
    --output-schema {output_schema_json or none} \
    --max-source-rows 20
```

### Full Run Call (all rows, overwrite table)

**If `environment == snowsight`:**

Same as preview call but with `MAX_SOURCE_ROWS = NULL` to process all rows:

```sql
USE {database}.{schema};

CALL SNOWFLAKE.CORTEX.GENERATE_SYNTHETIC_DATA(
    '{task_description}',
    '{output_table}',
    ARRAY_CONSTRUCT('{col1}', '{col2}'),
    {model_or_NULL},
    50,
    '{source_table}',
    {function_name_or_NULL},
    {PARSE_JSON_output_schema_or_NULL},
    NULL
);
```

Execute via `execute_sql` tool with `timeout_seconds: 14400`.

**If `environment == cli`:**

```bash
PYTHONPATH=<SKILL_DIRECTORY>/scripts uv run --project <SKILL_DIRECTORY> python <SKILL_DIRECTORY>/scripts/run.py synthetic \
    --database {database} \
    --schema {schema} \
    --connection {connection} \
    --task-description "{task_description}" \
    --output-table {output_table} \
    --input-columns {input_columns...} \
    --model {model or none} \
    --num-examples 50 \
    --source-table {source_table} \
    --function-name {function_name or none} \
    --output-schema {output_schema_json or none} \
    --max-source-rows none
```

**Output table shape (same as synthetic mode):**
- Input columns (`VARCHAR`)
- `EXPECTED` (`VARIANT`, typed JSON object)

---

### Parameters Reference

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| TASK_DESCRIPTION | VARCHAR | required | Description of the AI function task (NOT a function name) |
| OUTPUT_TABLE | VARCHAR | required | Fully qualified table name for output |
| INPUT_COLUMNS | ARRAY | required | Required input column names in argument order |
| MODEL | VARCHAR | NULL | Synthetic mode: required. Pseudo-label mode: optional (defaults to `claude-opus-4-7` if omitted). |
| NUM_EXAMPLES | INTEGER | 50 | Total number of examples to generate |
| SOURCE_TABLE | VARCHAR | NULL | If set, enables pseudo-label mode from existing input rows |
| FUNCTION_NAME | VARCHAR | NULL | Optional: infer schema from an existing structured function |
| OUTPUT_SCHEMA | VARIANT | NULL | Optional explicit output schema override |
| MAX_SOURCE_ROWS | INTEGER | NULL | Optional row cap for pseudo-label preview |

### Output Table Schema

The SPROC creates a table with the following columns:

| Column | Type | Description |
|--------|------|-------------|
| ID | INT | Auto-incrementing ID |
| Input columns | VARCHAR | One column per input specified by `INPUT_COLUMNS` |
| EXPECTED | VARIANT | JSON object containing all output keys from the output schema |

**Input type handling:** All input columns are stored as VARCHAR. When the function has ARRAY-typed parameters and `--function-name` is provided, the generator automatically produces JSON array values (e.g., `["NAME", "EMAIL"]`) instead of plain comma-separated strings. These JSON array strings are correctly detected and parsed by the optimizer and evaluator during downstream workflows.

**Accessing output values**: Use Snowflake's VARIANT syntax to access individual output keys:
```sql
SELECT EXPECTED:verdict, EXPECTED:rationale FROM {output_table};
-- Or cast to string: EXPECTED:verdict::STRING
```

### Return Value

```json
{
    "success": true,
    "output_table": "MY_DB.MY_SCHEMA.SYNTHETIC_DATA",
    "total_generated": 50,
    "input_columns": ["CLAIM", "DOCUMENTS"],
    "expected_keys": ["VERDICT", "RATIONALE"],
    "batch_errors": null
}
```

### Information Checklist

Before calling `GENERATE_SYNTHETIC_DATA`, ensure you have collected:

| Field | Description | Required | Default |
|-------|-------------|----------|---------|
| `task_description` | Description of the AI function task (or expected-label task in pseudo-label mode) | Yes | - |
| `output_table` | Fully qualified output table name | Yes | - |
| `input_columns` | Input column names in argument order (become separate VARCHAR columns) | Yes | - |
| `output_schema` or `function_name` | Output schema (one is required). Provide `output_schema` as a JSON object with `properties`, or `function_name` to infer from an existing function. | Yes (one of) | - |
| `model` | Cortex model (`required` in synthetic mode; optional in pseudo-label mode) | Conditionally | pseudo-label default: claude-opus-4-7 |
| `num_examples` | Number of examples to generate | No | 50 |
| `source_table` | Existing input-only source table (pseudo-label mode) | No | NULL |
| `max_source_rows` | Preview cap for pseudo-label mode | No | NULL |

---

## Stopping Points

- ✋ Step 1: After inferring/collecting task description — skip when the user named the function up front and inference succeeded
- ✋ Step 4: After model selection
- ✋ Step 6: After showing results
- ✋ Step 7: After presenting next steps
- ✋ Pseudo-Label Step 7: After showing preview for approval

## Output

- Snowflake table with synthetic or pseudo-labeled data
- Columns: ID, input columns (VARCHAR), EXPECTED (VARIANT)
