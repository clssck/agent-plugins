<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Snowsight Core Rules

Loaded when `environment == snowsight`. Adds notebook-based visual surfaces to the studio. **CLI behavior is unchanged — everything below is gated on `environment == snowsight`.**

Per-workflow notebook recipes are in separate files under `references/snowsight/`. This file contains universal rules that apply to ALL Snowsight workflows.

## ⚠️ TL;DR — Snowsight Hard Rules

These survive context compaction by being short and at the top:

0. **Snowsight Workspace notebooks are NOT standard Jupyter.** Kernel name, cell types, and `notebook_action` shapes are Snowflake-specific — copy snippets from § "Notebook Harness" verbatim, do not pull from training data. Telltale hallucinations: `"python3"`, `"streamlit"`, `cell_type: "code"`, `language_info`.
1. **Never deploy without chat confirmation.** Create flow: generate prompts → present review block in chat → `ask_user_question("Ready to deploy")` → deploy via `CALL SNOWFLAKE.CORTEX.CREATE_AI_FUNCTION(...)` through `execute_sql`.
2. **All user input goes through `ask_user_question`** — never a plain-text question or numbered menu. Validation: 2–6 options, no `"Other"`/`"Custom"` (auto-added), use `type: "text"` + `defaultValue` for free-form names.
3. **Pin workflow steps with `system_todo_write`** right after reading this file (see next section).
4. **Try It cells run only after smoke test succeeds.**
5. **Hand off Step 10 with `ask_user_question`** (Evaluate / Test / Done).
6. **After `add_cells`, set markdown cells and plot-only Python cells to `results_only`** via `notebook_action set_cell_view_mode` — default `code_and_results` shows raw markdown / matplotlib source. Editable cells (DDL, metric code, progress Python, preview SQL) stay default. See §7.
7. **Async tasks: ONE status query per user message.** Query `TASK_HISTORY` once, present the status, end turn with `ask_user_question`. Never poll in a loop, never re-query automatically, never call `TASK_HISTORY` more than once per turn.

If a tool call fails, fix the payload using harness snippets and retry once or twice; after that, chat-based confirmation is an acceptable fallback — graceful degradation beats a stalled workflow.

## Mandatory Notebook Mode

When `environment == snowsight`, the notebook is the **strongly preferred** surface for Create, Evaluate, Optimize, Synthetic Data, and Custom Metric workflows. It's the primary visual surface for example calls ("Try It"), evaluation results, synthetic data previews, and optimization result charts — use it whenever the Snowsight Workspace tools work.

If the notebook can't be created, appended to, or run after one or two harness-aligned retries, tell the user the notebook tooling failed and fall back to a chat-based confirmation flow. Do not loop indefinitely on a broken notebook — graceful degradation is better than a stalled workflow.

**⚠️ Notebook is for DISPLAY ONLY — not for execution.** All stored procedure calls must be executed via the `execute_sql` tool in the agent's own execution context. The notebook is only for: Try It example calls (Create), result queries and charts (Evaluate), result charts and Pareto filtering (Optimize), data previews (Synthetic Data), and Bring your own Model Hugging Face token-secret helper cells. The only execution exception is the Bring your own Model notebook-based Model Registry import fallback documented in `byom/SKILL.md` Step 4, and only after `SYSTEM$IMPORT_MODEL` fails. Do NOT write to existing `.sql` files or Snowsight SQL worksheets either — always use a `.ipynb` notebook.

## Pin the workflow with `system_todo_write` (MANDATORY first action)

Skill files get edited out of context as the conversation progresses; tool-call results are not durable. `system_todo_write` is the only mechanism that reliably survives context compaction — its state is re-rendered every turn.

**Immediately after reading this file and the relevant sub-skill, call `system_todo_write` to pin the workflow steps as todos.** Mark the first `in_progress`. Update statuses as you go — but **never** mark a step `completed` if you skipped a sub-step (e.g., do NOT mark "Deploy" complete without the chat confirmation + Ready to deploy).

**Example — Create workflow:**

```
1. Create notebook from intent (in_progress)
2. Collect inputs/outputs, mode, model, function name
3. Present review block in chat, ask_user_question("Ready to deploy" / "Cancel") — STOP
4. Deploy via CALL SNOWFLAKE.CORTEX.CREATE_AI_FUNCTION(...) (references/snowsight/create.md) + smoke test
5. Append Try It cells (3-5 rows from source table) to notebook + run them
6. ask_user_question("Next step": Evaluate / Test / Done)
```

Apply the same pattern to Evaluate and Optimize workflows — pin each step from the sub-skill as a todo before starting.

## Notebook Harness (anti-hallucination — copy snippets verbatim)

> Past Claude sessions have invented `"python3"`/`"streamlit"` kernel names, `cell_type: "code"`, and `language_info` blocks here — all valid in standard Jupyter, all **wrong in Snowsight Workspace notebooks**. Wrong kernel name → opaque `"notebook is taking longer than expected to load"` error → stalled workflow. Copy the snippets below verbatim; do not paraphrase or "improve" them.

### 1. Notebook skeleton — pass to `write` verbatim

Path: `{notebook_path}` (e.g., `customer_sentiment.ipynb`)

```json
{
  "metadata": {
    "kernelspec": {
      "display_name": "Jupyter Notebook",
      "name": "jupyter"
    }
  },
  "nbformat": 4,
  "nbformat_minor": 5,
  "cells": []
}
```

**Do NOT add** `language_info`, `language`, `codemirror_mode`, `mimetype`, `file_extension`, `nbconvert_exporter`, or `pygments_lexer`. Those keys all appear in standard Jupyter `.ipynb` files; none are valid here and adding them prevents the kernel from loading.

### 2. `notebook_action add_cells` — markdown cell

```json
{
  "action": "add_cells",
  "params": "{\"notebook_path\": \"{notebook_path}\", \"cells\": [{\"cell_type\": \"markdown\", \"source\": \"# Try It: {function_name}\\n\\nRun these example calls to smoke-test the function with representative inputs.\"}]}"
}
```

### 3. `notebook_action add_cells` — SQL cell (REQUIRES `result_variable_name`)

```json
{
  "action": "add_cells",
  "params": "{\"notebook_path\": \"{notebook_path}\", \"cells\": [{\"cell_type\": \"sql\", \"result_variable_name\": \"result_{function_name}\", \"source\": \"<SQL here>\"}]}"
}
```

`result_variable_name` is **required** for every SQL cell, even one whose result you never read. Omitting it fails validation.

### 4. `notebook_action add_cells` — Python cell

```json
{
  "action": "add_cells",
  "params": "{\"notebook_path\": \"{notebook_path}\", \"cells\": [{\"cell_type\": \"python\", \"source\": \"import pandas as pd\\nprint('hello')\"}]}"
}
```

**⚠️ Workspace cells share no implicit globals.** `session`, `pd`, `plt`, etc. are not auto-injected — include every `import` explicitly. Prefer precomputing values via `snowflake_sql_execute` and inlining as Python literals; if you need a live query, prepend `from snowflake.snowpark.context import get_active_session` + `session = get_active_session()`.

**⚠️ Do NOT use `matplotlib.use('Agg')` in notebook cells.** The `Agg` backend is for headless servers and renders to file buffers, not inline displays. Snowsight notebooks render charts inline via `plt.show()` — just `import matplotlib.pyplot as plt` and call `plt.show()` directly.

### 5. `notebook_action run_notebook` — run a single cell

```json
{
  "action": "run_notebook",
  "params": "{\"notebook_path\": \"{notebook_path}\", \"run_type\": \"single\", \"cell_id\": \"<cell_id_from_add_cells_response>\"}"
}
```

For "run this cell and everything after it" (used after appending a new section): `"run_type": "after"`.

### 6. `notebook_action get_cell_source_codes` — re-read a cell after user edits

```json
{
  "action": "get_cell_source_codes",
  "params": "{\"notebook_path\": \"{notebook_path}\", \"cell_ids\": [\"<cell_id>\"]}"
}
```

### 7. `notebook_action set_cell_view_mode` — hide source for markdown / plot-only cells

```json
{
  "action": "set_cell_view_mode",
  "params": "{\"notebook_path\": \"{function_name}.ipynb\", \"cell_id\": \"<cell_id_from_add_cells_response>\", \"view_mode\": \"results_only\"}"
}
```

Valid `view_mode` values: `code_and_results` (default), `code_only`, `results_only`, `collapsed`. Anything else is invalid — do not guess. Our workflows only ever switch to `results_only`; the others are listed for completeness.

- **Apply to:** every markdown cell; every Python cell whose only purpose is `plt.show()` / chart rendering.
- **Leave default:** DDL preview SQL, custom metric Python, Try It / data preview / eval result SQL, progress-bar Python.

Sequence: `add_cells` → `set_cell_view_mode` (per cell ID) → `run_notebook`. Calling after `run_notebook` works too but briefly flashes source.

### 8. Common hallucinations and their fixes

If you're about to write any **Hallucinated** value, STOP and use the **Correct** one. (See also §4 callout for `session` / import gotchas, §9 for runtime errors.)

| Field / call | Hallucinated (from training data) | Correct (Snowsight) |
|---|---|---|
| `kernelspec.name` | `"python3"`, `"streamlit"`, `"sql"`, `"snowflake"` | `"jupyter"` |
| `kernelspec.display_name` | `"Python 3"`, `"Streamlit Notebook"` | `"Jupyter Notebook"` |
| Top-level metadata key | `"language_info": {...}` | (omit entirely) |
| `cell_type` for SQL | `"code"` + `"language": "sql"` | `"sql"` (no `language` field) |
| `cell_type` for Python | `"code"` | `"python"` |
| SQL cell required field | (omitted) | `"result_variable_name": "<name>"` |
| `notebook_action` file param | `"file_path"` | `"notebook_path"` |
| `notebook_action` insert position | `"position": 0` | `"insert_at_index": 0` |
| `notebook_action` cell IDs param | `"cell_id": [...]` (singular) for `get_cell_source_codes` | `"cell_ids": [...]` (plural) |
| `add_cells` cells field | `"cells": "<JSON string>"` | `"cells": [<array of objects>]` (object, not stringified) |
| Editing `.ipynb` files | `edit` tool with `old_string`/`new_string` | `notebook_action` only — `edit` corrupts notebook JSON |
| `set_cell_view_mode` value | `"hidden"`, `"results"`, `"output_only"`, `"none"` | `"results_only"` or default `"code_and_results"` (§7) |
| matplotlib backend | `matplotlib.use('Agg')` | (omit entirely) — just `import matplotlib.pyplot as plt` + `plt.show()` |

### 9. Recovery: what each error message actually means

| Error message | Real cause | Fix |
|---|---|---|
| `notebook is taking longer than expected to load` | Invalid `kernelspec.name` (e.g. `"python3"`, `"streamlit"`) — the loader can't start the kernel and times out | Rewrite the `.ipynb` with the skeleton in §1, then retry `add_cells` once. Do not retry against the original broken file — it will time out forever. If the rewrite still fails, chat fallback is fine. |
| `[WARNING] Invalid cell_type 'code'` | You used Jupyter's `"code"` for a SQL or Python cell | Re-send `add_cells` with `cell_type: "sql"` (and `result_variable_name`) or `cell_type: "python"` |
| `result_variable_name is required for SQL cells` | Missing required field | Add `"result_variable_name": "<snake_case_name>"` to the SQL cell object |
| `Invalid action 'X'` | You guessed an action name | Only use: `add_cells`, `run_notebook`, `get_cell_source_codes`, `get_notebook_state`, `edit_cells`, `delete_cells` (others exist for service/kernel mgmt — see `notebooks-in-workspaces` skill) |
| `NameError: name 'session' is not defined` | Workspace notebooks (jupyter kernel) do not auto-inject `session`; you wrote `session.sql(...)` in a Python cell without importing it | Use `notebook_action edit_cells` to prepend `from snowflake.snowpark.context import get_active_session\nsession = get_active_session()` to the cell, OR rewrite the cell to inline pre-computed values from a `snowflake_sql_execute` call (see §4) |
| `NameError: name 'pd' is not defined` (or `plt`, `np`, etc.) | Same root cause — no implicit imports in Workspace cells | Add the missing `import` line at the top of the cell |
| Markdown / chart source still visible after run | You skipped `set_cell_view_mode` (§7) after `add_cells` | Call it now with `view_mode: "results_only"` for each markdown / plot cell ID, then re-run |

**Recovery rule**: When `notebook_action` errors, the fix is in the table above ~95% of the time — fix the payload and retry. If a second harness-aligned retry still fails, fall back to chat-based confirmation; that's a legitimate last resort.

## Notebook Skill (consult on demand)

The Notebook Harness above covers the notebook operations needed for AI Function Studio workflows. Read `workspaces/notebooks-in-workspaces/SKILL.md` only when:

- You hit a `notebook_action` error not explained by the Harness's recovery table (§9), OR
- You need an action not listed there (kernel/service management, schedules, migration, etc.).

**Do not load `snowflake-notebooks`** — different skill, ships a wrong kernelspec for Snowsight Workspace notebooks.

## Required Snowsight tools

This skill depends on the following Snowsight-specific tools:

**Required skill/tooling:** `notebooks-in-workspaces` skill, `write` (for creating .ipynb files), `notebook_action` (for `add_cells`, `get_cell_source_codes`, `get_notebook_state`, etc.), `bash` (for shell commands like `ls`), `read_active_pane`, `ask_user_question`

**Do not invoke `notebook_manager.py` in Snowsight.** This workflow currently uses Snowsight Workspace tools directly (`write` and `notebook_action`). `notebook_manager.py` is not part of the active Snowsight notebook flow yet.

**If a required tool is entirely missing** (not registered, distinct from a tool that errored), tell the user the notebook preview is unavailable and continue in chat-based confirmation for the rest of the session. **If a tool errored mid-flow**, that's the §8 recovery table — fix the payload and retry, don't escalate to "tool unavailable" until you've tried the harness fix.

## Required Notebook Structure

Each AI function gets **one notebook**. The notebook is required, not optional. It is the function's living document — each workflow stage (Create, Evaluate, Optimize) **appends** a markdown section header followed by its content cells. The result is a chronological record of the function's lifecycle, all in one place.

**Notebook path convention:** Derive a short `snake_case` notebook filename from the task description or function name and store it as the state variable `notebook_path` (e.g., `notebook_path = "customer_sentiment.ipynb"`). The notebook name does NOT need to match the final function name. If no meaningful name can be derived, use `custom_ai_function.ipynb` (append a number if it already exists). Use this `notebook_path` value in every `notebook_action` call for the rest of the session.

### Creating the notebook

Create the notebook when it is first needed (e.g., before appending Try It cells or evaluation results). Use the `write` tool with the skeleton from the **Notebook Harness** above (§1) — copy verbatim, do not hand-craft.

If the notebook already exists from a previous session, **do not try to reuse it**. Write a fresh `.ipynb` file (it will overwrite). This avoids "notebook has not been loaded yet" errors from trying to open stale files.

For non-Create-first workflows (e.g., user jumps straight to Evaluate or Optimize), create the notebook using `{function_name}.ipynb` when the function name is known, and set `notebook_path` to that value.

### First cell: set database and schema context

When the notebook is created, add a **SQL cell** as the very first cell that sets the notebook's database and schema context:

```sql
USE {database}.{schema};
```

Where `{database}` and `{schema}` come from the user's chat context or from the values collected during prerequisites (Step 0). If the database and schema are already known (e.g., from session defaults or prerequisites), include this cell at creation time. If not yet known, create the notebook skeleton first and add the `USE` cell later, before appending any SQL cells that need schema context.

**Run this cell before any other SQL cell.** Use `notebook_action(action="run_notebook", run_type="single", cell_id=<use_cell_id>)` to execute it. This ensures all subsequent SQL cells in the notebook (result queries, data previews) execute in the correct schema context.

### Appending cells (all stages)

Each workflow stage adds cells to the notebook using `notebook_action(action="add_cells", ...)`. New cells are always appended at the end. **Always start each stage with a markdown cell** as a section divider (e.g., `# 📋 Create`, `# 📊 Evaluation`, `# 🔧 Optimization`).

**After `add_cells`, before `run_notebook`:** call `set_cell_view_mode` (§7) on each markdown cell and each plot-only Python cell ID returned. Skip otherwise.

**After adding cells, run them** (unless the stage is preview-only — see Create Workflow below). The `add_cells` response returns the cell IDs of the newly created cells. Use the **first** new cell's ID with `run_type: "after"` to run it and everything after it:

```
notebook_action(action="run_notebook", params='{"notebook_path": "{notebook_path}", "run_type": "after", "cell_id": "<first_new_cell_id>"}')
```

SQL/Python cells must be run to produce results and charts. Markdown renders automatically once view-mode is set (§7), so no explicit run is needed for markdown. Running from the first new cell avoids re-executing earlier sections.

After running, **tell the user** the notebook has been created or updated. When a new notebook is created and cells are added, Snowsight should automatically switch the user's view to that notebook; on subsequent stages, say it was updated.

**⚠️ `notebook_action` parameter naming:** The notebook file parameter is always `notebook_path` (not `file_path`). Example:
```
notebook_action(action="add_cells", params='{"notebook_path": "{notebook_path}", "cells": [...]}')
```

## UX: Use `read_active_pane` for context

Before asking the user for context (function name, table name, database/schema), call **`read_active_pane`** first. It returns the content currently visible in the user's active Snowsight pane — typically a SQL worksheet, query results, or object explorer. If the active pane contains relevant SQL, table references, or query results, use that context instead of prompting. This avoids redundant questions when the answer is already on screen.

## UX: Use `ask_user_question` for ALL user input (MANDATORY)

Every time you need user input — picking options, confirming a config, providing a name, yes/no — the **final tool call of the turn must be `ask_user_question`**. Never end a turn with a plain-text question or numbered menu. If a sub-skill shows a chat-style prompt, translate it into `ask_user_question`.

### Tool shape

```json
{
  "questions": [
    {
      "header": "Short title",
      "question": "Your question text",
      "type": "options",
      "options": [
        {"label": "Option A", "description": "optional detail"},
        {"label": "Option B", "description": "optional detail"}
      ]
    }
  ]
}
```

- 1–4 questions per call. `header` is a max-12-char chip (e.g., `"Next step"`, `"Database"`).
- **`type: "options"`** — 2–6 options required, each with `label` (1–5 words) + `description`. Do **NOT** add `"Other"`/`"Custom"`/`"Specify"` options — `"Something else"` is auto-appended by the UI.
- **`type: "text"`** — free-form input; always provide `defaultValue`. Use for names, FQNs, identifiers; combine multiple text questions in one call for forms (e.g., database + schema).

If validation fails (e.g., 1 option, missing `defaultValue`, `"Other"` present), fix the payload and retry — don't rephrase as plain-text chat.

### Long content pattern

The `ask_user_question` UI does not render long text well. When a stopping point involves presenting detailed content (configuration summaries, column lists, JSON schemas, research approaches, multi-line explanations, etc.), **do not put the full content into the `question` field**. Instead:

1. **Print the content first** in a chat message, using the best formatting for the content type:
   - **Code block** (` ``` `) for JSON configs, SQL, or structured data
   - **Bold** key values and labels in prose summaries (e.g., **Function:** `DB.SCHEMA.MY_FUNC`)
   - **Tables** for column mappings, model comparisons, or parameter lists
   - **Numbered lists** with **bold headers** for multi-option presentations (e.g., research approaches)

2. **Then call `ask_user_question`** with a short question that references the printed content. Examples:
   - `"Does the above configuration look good?"` → options: `"Yes, proceed"` / `"I want to edit"` / `"Cancel"`
   - `"Which option above would you like?"` → one short label per option
   - `"Confirm the settings above?"` → `"Yes"` / `"Edit"` options

**Rule of thumb:** If the question text or any option description would exceed ~2 short sentences, print the detail in chat first and keep the `ask_user_question` call concise.

### Stopping-point checklist (every entry below MUST end the turn with `ask_user_question`)

- **prerequisites.md Target DB/Schema**: Use session defaults as options if set; otherwise two `type: "text"` questions for database + schema.
- **SKILL.md Step 1-2**: Workflow selection (Create / Evaluate / Optimize / Check Status / Demo)
- **create/SKILL.md Step 3**: Input/output source (From Table / Manual Spec)
- **create/SKILL.md Step 4**: Creation mode (Direct / [research preview] Agent Research)
- **create/SKILL.md Step 5**: Research approach selection (one option per approach + Custom)
- **create/SKILL.md Step 8** (Snowsight): "Ready to deploy" after chat review block — use 2-option `"Ready to deploy"` / `"Cancel"` (do NOT send a 1-option call)
- **create/SKILL.md Step 10**: Next steps (Evaluate / Test / Done) — final tool call after Try It runs; one-line chat confirmation is fine, but the turn MUST end with this call
- **evaluate/SKILL.md Step 2**: Test table source (generate data / use existing table)
- **evaluate/SKILL.md Step 4**: Metric selection (exact_match / fuzzy_match / llm_judge / custom)
- **custom_metrics.md Step 2–5**: Custom metric creation review (Ready to create metric)
- **evaluate/SKILL.md Step 4**: Execution mode (Sync / Async)
- **evaluate/SKILL.md Step 6**: Next steps (Optimize / Done)
- **optimize/SKILL.md Step 4.1**: Metric selection
- **optimize/SKILL.md Step 4.2**: Budget (light / medium / heavy)
- **optimize/SKILL.md Step 4.3**: Model selection — use `multiSelect: true`
- **optimize/SKILL.md Step 5**: Execution mode (Sync / Async)
- **optimize/SKILL.md Step 8**: Next steps (Evaluate / Re-optimize / Manage versions / Done)
- **demos/SKILL.md Step 1**: Demo selection
- **references/data_preparation.md Step 1**: Data situation (tables ready / need split / synthetic / pseudo-labels)

This list is illustrative, not exhaustive — the **MANDATORY** rule above applies to *any* user input not on this list as well.

## Setup: Verify Snowsight Context

Check whether you are running in the Snowflake Snowsight environment by inspecting the `environment` variable. If `environment == snowsight`, proceed — the Snowsight Workspace tools are available.

If you are in Snowsight but not yet in a workspace, help the user navigate with `snowsight_navigate` to open Workspaces page. All workflows require the user to be in a workspace before continuing.
