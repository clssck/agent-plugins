---
name: create-ai-function
description: "Create a new custom AI function. Supports table-based or manual input specification, single or variant outputs. Direct AI_COMPLETE calls or additional pre- and post-processing."
parent_skill: cortex-ai-function-studio
---
<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Create AI Function

## When to Load

Load from main skill when user intent matches CREATE: "create", "build", "new" + ai/llm function.

## Information Model

Before starting the workflow, scan the user's message and conversation context for pre-provided information. Track what's collected and only prompt for missing required fields.

| Field | Required | Default | Confirm | Dependencies |
|-------|----------|---------|---------|--------------|
| `task_description` | Yes | - | No | - |
| `clarifications` | Yes | (gathered) | No | task_description |
| `input_source` | Yes | - | No | - |
| `source_table` | If from_table | - | No | input_source |
| `source_stage` | If multimodal | @{db}.{schema}.AI_FUNCTIONS | No | input_source |
| `inputs` | Yes | - | **Research only** | input_source |
| `outputs` | Yes | - | **Research only** | - |
| `creation_mode` | Yes (direct, research) | - | No | clarifications, inputs, outputs |
| `selected_approach` | If research | - | **Yes** | creation_mode |
| `system_prompt` | If direct | (generated) | **Yes** | task_description |
| `user_prompt_template` | If direct | (generated) | **Yes** | inputs |
| `database` | Yes | (from prerequisites) | No | - |
| `schema` | Yes | (from prerequisites) | No | - |
| `function_name` | Yes | (generated) | No | - |
| `model` | Yes | claude-sonnet-4-6 | No | - |
| `udf_body_sql` | If research | (generated) | **Yes** | selected_approach, inputs, outputs, model |

**Critical fields** (always confirm even if pre-provided): `selected_approach` + `udf_body_sql` (only if research mode), `system_prompt` + `user_prompt_template` (direct mode). In Direct mode, `inputs` and `outputs` are shown in the Step 8 review block and do not need separate confirmation.

**Simple fields** (accept silently if pre-provided): `creation_mode`, `input_source`, `source_table`, `database`, `schema`, `function_name`, `model`, `task_description`

## Pre-Collection

At workflow start, before prompting:

1. **Parse the user's initial message** for any pre-provided information:
   - Task description (e.g., "create a function that classifies sentiment...")
   - Creation mode hints (e.g., "simple function" → direct, "research the best approach" / "I want to add post-processing" → research)
   - Input/output definitions (e.g., "...takes a TEXT input and returns sentiment and confidence")
   - Target location (e.g., "...in MY_DB.MY_SCHEMA")
   - Function name (e.g., "...called CLASSIFY_SENTIMENT")
   - Model preference (e.g., "...using claude-sonnet-4-5")

2. **Check conversation context** for inherited values:
   - Database/schema from prerequisites
   - Function context if coming from another skill

3. **Mark collected fields** and note their source (user message, context, or default)

4. **Identify missing required fields** to determine which steps need prompting

---

## Workflow

### Step 0: Record create-flow start (telemetry probe)

At the very start of the create flow — before any prompting or SQL — fire the CLI
telemetry probe exactly once. It is best-effort: ignore the result and continue
even if it fails (do not block the flow or surface errors to the user):

```bash
cortex ai-function-studio create
```

This emits a single `coco.cli.ai_function_studio.execute` event
(`subcommand=create`) so we can measure how often the create flow is entered. If
the `cortex` CLI or the subcommand is unavailable, silently continue.

### Planning

#### Step 1: Gather Intention

**If `task_description` already collected** (user described what the function should do):
- Accept silently and proceed.

**If `task_description` not collected**, ask:
```
What should this AI function do? Describe the task in 1-2 sentences.

For example:
- "Classify customer support tickets into categories"
- "Extract named entities from legal documents"
- "Score product review quality on a 0-1 scale"
```

Then continue with Step 2 below.

#### Step 2: Clarifying Questions

**Skip this step unless the task is genuinely ambiguous** — i.e., you cannot generate a reasonable system prompt without more information. Most well-described tasks ("classify sentiment", "extract entities from contracts", "score review quality") do not need clarification. Any minor details (edge cases, formatting preferences) can be adjusted when the user reviews the generated prompt in Step 8.

If clarification is truly needed (e.g., the user said "process my data" with no specifics), ask at most 2-3 targeted questions batched together. Do not ask one at a time.

If you need to ask, wait for user answers before proceeding. Do not gate this as a mandatory stop — only pause if questions were actually asked.

#### Step 3: Define Inputs and Outputs

**If the user explicitly asks to process images, documents, or files from a stage**, load `references/multimodal_setup.md` and follow its workflow for multimodal input handling, model selection, and UDF generation. The default is text-only — do not suggest multimodal unprompted.

**Determine input source:**

**If `inputs` already collected** (user provided input definitions):
- Skip input source determination
- Show for confirmation

**If `source_table` already collected** (user mentioned a table):
- Input source is implicitly "from_table"
- Run `DESCRIBE TABLE <table_name>` and ask user to select input/output columns

**If neither collected**, ask:
```
How would you like to define your AI function inputs?

1. **From Table** - Extract schema from a Snowflake table
2. **Manual Spec** - Define inputs manually (names, types)
```

**If From Table:**
```sql
DESCRIBE TABLE <table_name>
```
Show columns and ask user to select which are **inputs** and what **outputs** the function should return.

**Detecting file inputs from table schema:** When running `DESCRIBE TABLE`, check each selected input column's data type:
- If type is **FILE** → use `sql_type: "FILE"` in the config. The function will accept FILE directly.
- If type is **VARCHAR** and sample values look like stage file paths (contain `/`, end with file extensions like `.jpg`, `.pdf`, etc.) → use `sql_type: "STAGE_FILE_PATH"`. The function will cast to FILE internally via `TO_FILE()`. Ask user for the stage name.
- Otherwise → regular text/scalar input.

The function signature must match the table's column types so `SELECT func(col) FROM table` works without any extra wrapping. Load `references/multimodal_setup.md` for full detection flow and model selection when file inputs are detected.

**If Manual Spec:** Collect input parameters and output fields:
```
Input 1:
  - Name: (e.g., customer_message)
  - SQL Type: [VARCHAR] (or NUMBER, FLOAT, BOOLEAN, VARIANT, FILE)

Output 1:
  - Name: (e.g., sentiment)
  - JSON Type: [string] (or number, boolean, array, object)
  - Description: (e.g., "The detected sentiment")
```

**Input type notes:** Semi-structured inputs (`ARRAY`, `VARIANT`, `OBJECT`) are surfaced into the prompt template as JSON strings — `ARRAY` via `ARRAY_TO_STRING(<col>, ', ')`, `VARIANT` and `OBJECT` via `TO_VARCHAR(<col>)`. The evaluate/optimize pipelines do the same conversion, so the prompt sees the JSON serialization rather than native structured data — that is functionally correct, just be aware of it when designing the prompt. Preserve the user's declared SQL types verbatim in the function signature: pass `sql_type: "ARRAY"`, `"VARIANT"`, or `"OBJECT"` to `create_udf.py` exactly as the user described the column; do not silently downcast to `VARCHAR`. For single-output functions, the return type maps from JSON type: `string` -> VARCHAR, `number` -> FLOAT, `integer` -> NUMBER, `boolean` -> BOOLEAN, `array`/`object` -> VARIANT. Multi-output functions always use `RETURNS VARIANT`.

**If creation mode will be Research** (user already indicated research, custom SQL, or pre/post-processing):
- **⚠️ STOP**: Confirm inputs/outputs before proceeding — research depends on accurate I/O definitions and changing them later wastes work.

**If creation mode will be Direct** (the common path):
- Do **not** stop here. Inputs/outputs will be shown in the Step 8 review block where the user confirms everything together. Proceed to Step 4.

#### Step 4: Select Creation Mode

**If any input has a multimodal type (`FILE` or `STAGE_FILE_PATH`)**, [research preview] Agent Research mode is NOT available — always use Direct mode. Do not offer or mention the research option. Skip to Step 7.

**Default to Direct mode.** [research preview] Agent Research mode (which generates a custom `--sql-body` UDF) may ONLY be used when the user has **EXPLICITLY** mentioned research mode, custom SQL, or SQL pre/post-processing in the current chat. Do not ask the user to choose a mode — infer it from what they have already said.

**⚠️ HARD RULE — Custom `--sql-body` / Research mode requires EXPLICIT user request.**
- Use [research preview] Agent Research mode (and therefore `create_udf.py --sql-body`) **only** if the user explicitly said one of: "research", "research mode", "explore approaches", "custom SQL", "SQL body", "pre-processing", "post-processing", or otherwise unambiguously asked for a custom SQL UDF body.
- Task complexity, multi-step logic, perceived need for validation, or your own preference are **NOT** sufficient justification. If the user did not explicitly ask, use Direct mode.
- **Before** selecting research mode, you MUST re-read the chat and verify there is an explicit mention from the user. If you cannot quote the exact user phrase that requested it, you do NOT have permission to use research mode — fall back to Direct mode.
- If you are considering research mode but the user has not explicitly asked, you must instead either (a) proceed with Direct mode silently, or (b) briefly offer research as an option and **wait** for the user to confirm before switching. Never enter research mode unilaterally.

Routing:
- User explicitly asked for research / custom SQL / pre or post-processing → [research preview] Agent Research mode. Continue to Step 5.
- Otherwise (the common case) → Direct mode. Skip to Create phase (Step 7).

If you are unsure and the task seems complex enough that research *might* help, you may briefly offer:
```
This looks like a straightforward task — I'll create a Direct AI_COMPLETE function.
If you'd prefer I research implementation approaches with SQL pre/post-processing,
let me know. (Note: Agent Research mode is [research preview, sandbox only].)
```
Then proceed with Direct mode without waiting for a response unless the user intervenes. **Do not** switch to research mode based on this offer alone — only switch if the user explicitly responds asking for it.

#### Step 5: Research and Present Approaches

With a clear understanding of the task, research how to best implement it as a Snowflake SQL UDF.

**Web search** — Search for state-of-the-art techniques relevant to the customer's specific task. Example queries:
   - "best approach for [task] with LLMs"
   - "[task] prompt engineering techniques"
   - "[task] structured output best practices"

   Focus on findings that translate to a SQL UDF implementation: prompting strategies, output structuring, validation techniques, and error handling. 
   A realistic combination would be SQL pre and post processings steps. Note, we cannot finetune or directly change model weights. Treat the model as a black box, but we can do Turing complete computation with SQL before and after calling AI_COMPLETE.

Synthesize web research and pre-built patterns to identify ~1-3 concrete approaches.

Present the approaches to the customer. Each approach must vary in **how the SQL UDF body is structured** — not just in prompt wording. For each approach, show:

1. **Name** and one-line description
2. **SQL UDF body sketch** — the complete `$$ ... $$` body showing where AI_COMPLETE sits relative to other SQL expressions
3. **Pros and cons** — quality, complexity, cost, latency, maintainability
4. **Best for** — when this approach is the right choice
5. **Recommended** - pick one of the approaches and tell the customer that this is the recommended approach

If there is high variance in solutions, order them from simplest to most complex.

**Always include a final option** after the researched approaches:
```
N+1. **Custom** — None of these fit? Describe your own pre- and post-processing strategy
     and I'll build the SQL UDF accordingly.
```

If the customer selects Custom, ask them to describe what they have in mind:
```
Describe the approach you'd like to take — what should happen before or after the
AI_COMPLETE call? I'll translate your idea into a concrete SQL UDF.
```

**⚠️ STOP**: Wait for customer to select an approach or describe their own. If they want modifications to any option, iterate.

#### Step 6: Confirm Approach

**[research preview] Agent Research mode only.** Direct mode skips this step.

Confirm the selected or described approach. Summarize what was chosen:
```
Selected approach: [name]

I'll build a SQL UDF that:
- [key structural characteristic]
- [key behavioral characteristic]

Proceeding to generate the full function.
```

---

### Create

#### Step 7: Select Target Location and Model

Use the target `database` and `schema` values that were already collected during prerequisites.

**If `function_name` already collected**, accept silently.

**If not collected**: Generate a name (SCREAMING_SNAKE_CASE) based on task description or outputs. Do not ask the user to confirm — the name will be shown in the Step 8 review block where they can edit it along with everything else.

**Do not treat the default model (`claude-sonnet-4-6`) as user-selected.** If the model is only the default, it is not considered collected for this step.

**If `model` was explicitly provided by the user or inherited from a prior workflow**, accept silently — unless the user explicitly asked to see model options (e.g., "show me available models"), in which case load `references/model_selection.md` and present the options.

**If no explicit/inherited model was collected**: It is MANDATORY to **load** `references/model_selection.md` and follow its full workflow. In create workflows, the final dialog option must be **"See all models"**, which lists verified Bring your own Model / Hugging Face models alongside the hosted families. If the user selects one of those models — or explicitly asks for a bring-your-own model, Hugging Face/open-source model, SPCS service, or an existing model service — route to `byom/SKILL.md`.

#### Step 8: Generate Prompts and Confirm

**If `environment == snowsight`:** Present the review below in chat (not in the notebook), then use `ask_user_question` with options **"Ready to deploy"** / **"Cancel"**. STOP and wait. After user confirms, follow `references/snowsight/create.md` Step 9 to deploy, then return here for Step 10.

**Direct mode:**

  Generate the system prompt and user prompt template from collected information.

  **If `system_prompt` not collected**, auto-generate from task description and clarifications:
  ```
  You are an expert [domain] assistant. Your task is to [task_description].

  Guidelines:
  - [specific instruction based on clarifications]
  - [edge case handling]
  - Always respond in the specified JSON format
  ```

  **If `user_prompt_template` not collected**, auto-generate from input parameter names:
  - Example for inputs `[TEXT, LANGUAGE]`:
    ```
    Analyze the following text:

    Text: {TEXT}
    Language: {LANGUAGE}
    ```

  **⚠️ STOP**: Present everything as a single review block. This is the only confirmation point for Direct mode:
  ```
  Here's the function configuration:

  Function: {database}.{schema}.{function_name}
  Model: {model}

  Inputs: {input_name} ({sql_type}), ...
  Outputs: {output_name} ({json_type}), ...
  Returns: {return_type}

  System prompt:
    "{system_prompt}"

  User prompt template:
    "{user_prompt_template}"

  Shall I proceed with this configuration?
  ```
  Wait for user to confirm or request edits before proceeding.

**[research preview] Agent Research mode:**

	Based on the confirmed approach, inputs, outputs, and model, compose the UDF logic (the SQL expression that goes inside `$$ ... $$`). Preserve the user's declared SQL types verbatim in the function signature — never silently convert semi-structured inputs (`ARRAY`, `VARIANT`, `OBJECT`) to `VARCHAR`.

	**The UDF logic is NOT limited to a single AI_COMPLETE call.** It should follow the structural pattern selected in the Planning phase, which may include:
	- SQL pre-processing on **scalar inputs only** (CASE WHEN, CONCAT, IFF, OBJECT_CONSTRUCT) — do NOT pre-process ARRAY or VARIANT inputs as they have indefinite length; pass them directly to AI_COMPLETE
	- AI_COMPLETE call (exactly one) — **always `AI_COMPLETE(...)`, never `SNOWFLAKE.CORTEX.COMPLETE(...)`** (legacy function, incompatible with evaluate/optimize pipelines)
	- SQL post-processing (TRY_PARSE_JSON, COALESCE, type casting, CASE WHEN)
	- Scalar subqueries for intermediate variables: `(SELECT expr FROM (SELECT AI_COMPLETE(...) AS r))`
	- REDUCE for iterative transformations on array results
	- Any other valid SQL expressions

	**Show the function config and UDF logic to the user in chat for review** (readable format, NOT raw DDL):
	```
	Function: DB.SCHEMA.FUNCTION_NAME
	Inputs: (inputs...)
	Returns: <return_type>

	UDF logic:
	    <the SQL expression body — AI_COMPLETE call, pre/post-processing, etc.>
	```

	**⚠️ STOP**: Always confirm before proceeding. The user may want to adjust the prompt, add edge case handling, change the SQL logic, etc. After confirmation, the agent constructs the full `CREATE FUNCTION` DDL internally at deployment time (Step 9) — do NOT show raw DDL to the user.

	**⚠️ MANDATORY COMMENT TAG**: Every `CREATE FUNCTION` DDL you generate for `--sql-body` MUST include a `COMMENT` clause whose value is **prefixed exactly** with `[CORTEX AI FUNC STUDIO] ` (note the trailing space) followed by a short human-readable description of the function's intention. This prefix is how the studio identifies functions it created and is non-negotiable — no exceptions, regardless of approach or model. Example: `COMMENT = '[CORTEX AI FUNC STUDIO] Classifies support tickets into priority buckets.'`. If the DDL you are about to pass to `--sql-body` does not contain this exact prefix, you MUST add it before calling `create_udf.py`.

#### Step 9: Deploy and Test

**If `environment == snowsight`:** Deploy via `CALL SNOWFLAKE.CORTEX.CREATE_AI_FUNCTION(...)` — a **9-parameter positional** stored procedure. Do NOT write raw `CREATE FUNCTION` DDL, do NOT use `LANGUAGE CORTEX_AI`, do NOT use named `=>` parameters. Read `references/snowsight/create.md` for the exact parameter template, smoke test, and Try It cell instructions. Return here for Step 10 after completion.

**If `environment == cli`:**

  **Direct mode:**

  **⚠️ Function body uses `AI_COMPLETE(...)` — NOT `SNOWFLAKE.CORTEX.COMPLETE(...)`**, which is a legacy function incompatible with the evaluate/optimize pipelines. If you are showing the DDL to the user instead of executing it, ensure the body contains `AI_COMPLETE(...)`.

  ```bash
  PYTHONPATH=<SKILL_DIRECTORY>/scripts uv run --project <SKILL_DIRECTORY> python <SKILL_DIRECTORY>/scripts/create_udf.py \
      --execute --connection <CONNECTION_NAME> --database <DATABASE> --schema <SCHEMA> \
      --function-name <FUNCTION_NAME> --function-intention '<FUNCTION_INTENTION>' \
      --model <MODEL> --system-prompt '<SYSTEM_PROMPT>' \
      --user-prompt-template '<USER_PROMPT_TEMPLATE>' \
      --inputs '<INPUTS_JSON_ARRAY>' --outputs '<OUTPUTS_JSON_ARRAY>'
  ```
  If any input uses `sql_type: "STAGE_FILE_PATH"`, also pass `--stage-name <STAGE_NAME>`.

  **[research preview] Agent Research mode:**

  **⚠️ Before constructing the DDL, re-verify**: Did the user EXPLICITLY ask for research mode / custom SQL / pre or post-processing in this chat? If you cannot point to a specific user message that requested it, STOP and switch back to Direct mode — do not use `--sql-body`.

  Construct the full `CREATE FUNCTION` DDL from the confirmed config (function name, inputs, return type, UDF logic from Step 8), then pass it as `--sql-body`. The DDL **MUST** include a `COMMENT` clause beginning with the exact prefix `[CORTEX AI FUNC STUDIO] ` — this is required for every SQL body and is how the studio identifies its functions. Example skeleton:
  ```sql
  CREATE OR REPLACE FUNCTION <DB>.<SCHEMA>.<FUNCTION_NAME>(<inputs>)
  RETURNS <return_type>
  LANGUAGE SQL
  COMMENT = '[CORTEX AI FUNC STUDIO] <short description of function intention>'
  AS
  $$
  <udf logic from Step 8>
  $$;
  ```
  Then deploy:
  ```bash
  PYTHONPATH=<SKILL_DIRECTORY>/scripts uv run --project <SKILL_DIRECTORY> python <SKILL_DIRECTORY>/scripts/create_udf.py \
      --execute --sql-body '<COMPLETE_CREATE_FUNCTION_DDL>' --connection <CONNECTION_NAME>
  ```
  If the DDL string you are about to pass does not contain the literal substring `[CORTEX AI FUNC STUDIO] ` inside a `COMMENT` clause, do NOT run the command — fix the DDL first.

  After creation, test: `SELECT <function_name>(<sample_input>) AS result;`

#### Step 10: Next Steps

Present to user:
```
Your AI function is ready!

**Recommended next step:** Evaluate your function against labeled test data to establish a performance baseline.

What would you like to do?
1. **Evaluate** (recommended) - Measure function performance against a labeled dataset
2. **Test** - Run a quick test with sample inputs via SQL
3. **Done** - Exit for now
```

If evaluate → Load `evaluate/SKILL.md` with context:
- Preserve function name, database, schema
- Note: *"You'll need a test table with input columns and expected outputs to evaluate."*

---

## Best Practices

**Research mode is opt-in only:** Custom SQL bodies (`create_udf.py --sql-body`) are reserved for [research preview] Agent Research mode, and Research mode is only available when the user **explicitly** asks for it ("research", "custom SQL", "SQL body", "pre/post-processing"). If there is no explicit request, use Direct mode — never reach for `--sql-body` because the task feels complex or you think a custom body would be cleaner. When in doubt, re-read the chat to confirm the user's request; if you cannot quote the request, do not use research mode.

**Mandatory comment prefix for SQL bodies:** Every `CREATE FUNCTION` DDL produced for `--sql-body` MUST include a `COMMENT = '[CORTEX AI FUNC STUDIO] <description>'` clause. The prefix `[CORTEX AI FUNC STUDIO] ` (with trailing space) is required verbatim — it is how the studio recognizes functions it created. Direct mode applies this prefix automatically via `_normalize_comment` in `create_udf.py`; in research mode you are constructing the DDL by hand, so you are responsible for including it. Verify the prefix is present in your DDL string before invoking `create_udf.py --sql-body`.

**SQL UDF Bodies:** Custom AI functions are `LANGUAGE SQL` UDFs. The body is a single SQL expression (not a statement block). Use scalar subqueries `(SELECT expr FROM (SELECT AI_COMPLETE(...) AS r))` when the AI_COMPLETE result is referenced multiple times. Inside UDF bodies, use `ARRAY_CONSTRUCT()` (not `[...]`), `OBJECT_CONSTRUCT()` (not `{...}`), and `PARSE_JSON('...')` for the response_format value. AI_COMPLETE is called exactly once per invocation. Do not apply input enrichment to ARRAY or VARIANT inputs — their indefinite length makes them unsuitable for SQL-level transformation; pass them directly to AI_COMPLETE. When the body uses `OBJECT_CONSTRUCT(...)` for multi-output, declare `RETURNS VARIANT` so the function is compatible with the evaluate/optimize pipelines. Do not use PostgreSQL `E'...'` escape string syntax; use regular `'\n'` or `CHAR(10)` for newlines.

**AI_COMPLETE calling convention:** Use the unqualified built-in `AI_COMPLETE(...)` — not the legacy `SNOWFLAKE.CORTEX.COMPLETE(...)`, which is a different (older) function and is not supported by the evaluate/optimize pipelines. Always use the named-parameter messages-array syntax; positional arguments are not supported for chat completions. The canonical pattern is:

```sql
AI_COMPLETE(
    model => 'claude-sonnet-4-6',
    messages => ARRAY_CONSTRUCT(
        OBJECT_CONSTRUCT('role', 'system', 'content', '<system prompt>'),
        OBJECT_CONSTRUCT('role', 'user', 'content', '<user message>')
    )
)::VARCHAR
```

Do NOT use the positional form `AI_COMPLETE('model', 'system', 'user')` — it will fail with `Invalid argument types` for chat-based models.

**System Prompts:** Be specific, define edge cases, use structure, add examples for complex tasks, keep focused.

**JSON Schema:** Use correct types (`string`, `number`, `boolean`, `array`, `object`), mark required fields, define `items` for arrays.

**Output Types:** For single-output functions, the return type maps from JSON type: `string` -> VARCHAR, `number` -> FLOAT, `integer` -> NUMBER, `boolean` -> BOOLEAN, `array`/`object` -> VARIANT. Multi-output functions always use `RETURNS VARIANT`. This applies to both Direct mode and [research preview] Agent Research mode — always use `RETURNS VARIANT` for multi-output so the function is compatible with the evaluate and optimize pipelines. Do not use `RETURNS OBJECT` — the evaluate/optimize SPROCs expect VARIANT.

**Testing:** Test typical inputs, edge cases (NULL, empty, long), verify types and structure.

**Performance:** Choose appropriate model, keep prompts concise, use structured output.

## Common Patterns

- **Classification:** Single string output (category)
- **Extraction:** Multiple fields (VARIANT)
- **Sentiment:** sentiment (string) + confidence (number)
- **Transformation:** Single string output (transformed text)
- **Validation:** is_valid (boolean) + errors (array)
- **Scoring:** Numeric output with range validation (Output Transformation pattern)
- **Conditional Processing:** Different prompts for different input types (Input Enrichment pattern)
- **Structured Extraction:** LLM extracts raw fields, SQL reshapes into precise output (Output Transformation - heavy)
- **Find-and-Replace:** LLM identifies items, SQL applies REPLACE iteratively (Iterative Transformation pattern)
