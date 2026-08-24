<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Snowsight Create Workflow

Requires `references/snowsight/core.md` to be loaded first.

## When to Load

Load this file when `environment == snowsight` at `create/SKILL.md` Step 8–9.

## Chat Confirmation and Deployment (Step 8–9)

**Supplements Steps 8 and 9 for Snowsight.** In Snowsight, the review block is shown in chat (not in a notebook cell). The notebook receives "Try It" cells only after the smoke test succeeds.

After generating prompts in Step 8 (either Direct or [research preview] Agent Research mode), present the review block in chat following the same format as `create/SKILL.md` Step 8 (function name, model, inputs, outputs, system prompt, user prompt template). Then use `ask_user_question` with options: **"Ready to deploy"** / **"Cancel"**.

**⚠️ Research mode gate (Snowsight).** Research mode here means you are about to pass a non-NULL `SQL_BODY` (param 8) to `CREATE_AI_FUNCTION`. Per `create/SKILL.md` Step 4, this is only permitted when the user EXPLICITLY asked for research mode, custom SQL, or SQL pre/post-processing. Before constructing `SQL_BODY`, re-read the chat and verify the user's explicit request — if you cannot quote it, fall back to Direct mode (param 8 = NULL).

**STOP**: Wait for confirmation. After the user confirms, proceed to Step 9 below.

## Step 9: Deploy via Stored Procedure

The review block was already presented in chat and the user confirmed via `ask_user_question`. This section covers deployment, smoke testing, and Try It cells.

After user confirms, deploy by running this CALL via `execute_sql`. All 9 positional parameters are required. Always set database/schema context first.

**Function signature** — verify your CALL matches these 9 types exactly before executing:

```
CREATE_AI_FUNCTION(
  VARCHAR,   -- 1. FUNCTION_NAME          e.g. 'DB.SCHEMA.MY_FUNC'
  VARCHAR,   -- 2. MODEL                  e.g. 'claude-sonnet-4-6'
  VARCHAR,   -- 3. SYSTEM_PROMPT          use $$ quoting
  VARCHAR,   -- 4. USER_PROMPT_TEMPLATE   use $$ quoting, MUST have {COL} placeholders
  VARIANT,   -- 5. INPUTS                 PARSE_JSON('[{"name":"COL","sql_type":"VARCHAR"}]')
  VARIANT,   -- 6. OUTPUTS                PARSE_JSON('[{"name":"field","json_type":"string","description":"..."}]')
  VARCHAR,   -- 7. FUNCTION_INTENTION     or NULL
  VARCHAR,   -- 8. SQL_BODY               NULL for Direct, full CREATE FUNCTION statement for Research (see below)
  VARCHAR    -- 9. STAGE_NAME             or NULL
)
```

### Direct mode:

```sql
USE {database}.{schema};

CALL SNOWFLAKE.CORTEX.CREATE_AI_FUNCTION(
    '{database}.{schema}.{function_name}',   -- 1. FUNCTION_NAME
    '{model}',                                -- 2. MODEL
    $${system_prompt}$$,                      -- 3. SYSTEM_PROMPT
    $${user_prompt_template}$$,               -- 4. USER_PROMPT_TEMPLATE — MUST contain {INPUT_NAME} placeholders
    PARSE_JSON('[{inputs_inner}]'),            -- 5. INPUTS — {inputs_inner} = comma-separated objects, e.g. {"name":"COL","sql_type":"VARCHAR"}
    PARSE_JSON('[{outputs_inner}]'),          -- 6. OUTPUTS — {outputs_inner} = comma-separated objects, e.g. {"name":"label","json_type":"string","description":"..."}
    '{function_intention}',                   -- 7. FUNCTION_INTENTION (or NULL)
    NULL,                                     -- 8. SQL_BODY (NULL for Direct)
    {stage_name_or_NULL}                      -- 9. STAGE_NAME (or NULL)
);
```

**Example:**

```sql
USE MY_DB.MY_SCHEMA;

CALL SNOWFLAKE.CORTEX.CREATE_AI_FUNCTION(
    'MY_DB.MY_SCHEMA.CLASSIFY_SENTIMENT',
    'claude-sonnet-4-6',
    $$You are a sentiment classifier. Classify the sentiment as positive, negative, or neutral.$$,
    $$Analyze this text: {TEXT}$$,
    PARSE_JSON('[{"name":"TEXT","sql_type":"VARCHAR"}]'),
    PARSE_JSON('[{"name":"label","json_type":"string","description":"positive, negative, or neutral"}]'),
    'Classify text sentiment',
    NULL,
    NULL
);
```

### Research mode:

**⚠️ Before generating this CALL, re-verify**: Did the user EXPLICITLY ask for research mode / custom SQL / pre or post-processing in this chat? If you cannot point to a specific user message that requested it, STOP and switch back to Direct mode — do not pass a non-NULL `SQL_BODY`.

```sql
USE {database}.{schema};

CALL SNOWFLAKE.CORTEX.CREATE_AI_FUNCTION(
    '{database}.{schema}.{function_name}',
    '', '', '',
    PARSE_JSON('[{inputs_inner}]'),
    PARSE_JSON('[{outputs_inner}]'),
    '{function_intention}',
    '{sql_body}',         -- 8. SQL_BODY (construct full CREATE FUNCTION DDL from Step 8 config — see "Constructing SQL_BODY" below; the DDL's COMMENT clause is what carries the `[CORTEX AI FUNC STUDIO]` prefix onto the deployed function)
    NULL
);
```

When `SQL_BODY` is set, `MODEL`, `SYSTEM_PROMPT`, and `USER_PROMPT_TEMPLATE` are ignored — pass empty strings.

#### Constructing SQL_BODY

The user confirmed a readable config (function name, inputs, return type, UDF logic) in Step 8. You must now wrap that into a complete `CREATE FUNCTION` DDL to pass as the `SQL_BODY` string parameter. Do NOT execute this DDL directly — it is only a string value for parameter 8.

**⚠️ MANDATORY COMMENT TAG**: The DDL **MUST** include a `COMMENT = '[CORTEX AI FUNC STUDIO] <short description>'` clause. This prefix (with trailing space) is required verbatim on every SQL body produced by this skill — it is how the studio identifies functions it created. No exceptions.

Build the DDL from the confirmed config:
```sql
CREATE OR REPLACE FUNCTION {database}.{schema}.{function_name}({param1} {type1}, {param2} {type2}, ...)
  RETURNS {return_type}
  LANGUAGE SQL
  COMMENT = '[CORTEX AI FUNC STUDIO] {short description of function intention}'
AS
$$
  {udf_logic_from_step8}
$$
```

Param 8 uses single quotes (not `$$`, since the DDL itself contains `$$` around the UDF logic). Double any single quotes inside the DDL body (`'` → `''`) — including the single quotes around the `COMMENT` value.

Before executing the `CALL`, verify the literal substring `[CORTEX AI FUNC STUDIO] ` appears inside the `SQL_BODY` string's `COMMENT` clause. If it is missing, fix the DDL first.

### Validation checklist — check BEFORE executing:

1. **Params 3–4 use `$$` quoting** — not single quotes. **Param 8 uses single quotes** (because the DDL contains `$$` internally) — double any `'` inside (`''`).
2. **Param 4 contains `{COLUMN_NAME}` for every input** — every `"name"` in Param 5 must appear as `{NAME}` in Param 4. Missing placeholders = function ignores input.
3. **Param 4 does NOT use `|| COLUMN_NAME`** — the SP expects `{COLUMN_NAME}` template syntax.
4. **Param 5 `INPUTS`**: JSON array of `{"name":"COL","sql_type":"VARCHAR"}` objects.
5. **Param 6 `OUTPUTS`**: JSON array of `{"name":"field","json_type":"string","description":"..."}` objects.
6. **Research mode only — Param 8 `SQL_BODY`** is non-NULL only if the user EXPLICITLY asked for research mode in the chat. If non-NULL, the DDL string must contain a `COMMENT = '[CORTEX AI FUNC STUDIO] ...'` clause. If either condition fails, do not execute.

## Smoke Test

After the CALL succeeds, test outside the notebook:

```sql
SELECT {function_name}({sample_input}) AS result;
```

**Return type awareness:**
- **Single-output** (one entry in `outputs`): returns the scalar type directly. Do NOT add `:field_name` accessor.
- **Multi-output** (multiple entries in `outputs`): returns VARIANT. Access fields with `:field_name::TYPE`.

## Try It Cells

After the smoke test passes, append cells to `{notebook_path}`:

1. **Markdown cell**: `# Try It: {function_name}`

2. **SQL cell** — prefer the user's source table (3–5 rows). Fallback: hardcoded CTE.

   From source table:
   ```sql
   SELECT {input_columns}, {database}.{schema}.{function_name}({input_columns}) AS result
   FROM {source_table} LIMIT 5;
   ```

   Hardcoded fallback:
   ```sql
   WITH sample_inputs AS (
       SELECT 'example input 1' AS INPUT_COL UNION ALL
       SELECT 'example input 2' AS INPUT_COL
   )
   SELECT INPUT_COL, {database}.{schema}.{function_name}(INPUT_COL) AS result
   FROM sample_inputs;
   ```

3. **Run the newly appended cells** with `notebook_action(action="run_notebook", ...)`.

After Try It runs, proceed to `create/SKILL.md` Step 10. The final tool call of this turn MUST be `ask_user_question` (Evaluate / Test / Done).
