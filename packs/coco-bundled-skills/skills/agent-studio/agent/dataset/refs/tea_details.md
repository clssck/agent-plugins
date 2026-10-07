# TEA-track details (reference)

Reference for the **Tool Execution Accuracy (TEA) track** of dataset curation. Skills (`dataset-scratch`, `dataset-production`, `dataset-expand`) link here for authoring rules and the long SQL templates. Step procedure (STOPs, ASK prompts, mapping tables, decision tables) lives in the skill bodies.

## When to read this

| You're trying to … | …read |
|---|---|
| Pick the TEA-track question mix and confirm per-tool-type coverage | [§ TEA category guidance](#tea-category-guidance) |
| Author a `ground_truth_invocations` array (schema, two-part `tool_output` format, SQL ground-truth rules, quality checklist) | [§ TEA-track authoring](#tea-track-authoring) |
| Decide methodology for a TEA-track row (#1 build manually vs #2 trace projection  ) | [§ TEA drafting by methodology](#tea-drafting-by-methodology) |
| Pull `record_root.*` and per-tool-family attributes from the agent trace after invoking the agent for ground truth (methodology #2) | [§ Trace projection from agent invocations](#trace-projection-from-agent-invocations) |
| Populate a TEA-track source table with sample rows | [§ TEA INSERT template (scratch)](#tea-insert-template-scratch) |

The sub-skills (`dataset-scratch` / `dataset-production` / `dataset-expand`) each carry a header pointer to this file, and the parent [`dataset/SKILL.md`](../SKILL.md) deep-links to `§ TEA-track authoring` from its TEA-aligned authoring rules. When a sub-skill step reaches one of the intents above, follow the link in the matching row — **do not** re-state these rules in the sub-skill body.

Step-executable SQL (production annotation DDL, `UPDATE`, projection, expand staging fix-up) lives **inline in the calling skill** — not duplicated here.

`GROUND_TRUTH` JSON shape, field-absent semantics: [`ground_truth_schema.md`](./ground_truth_schema.md).

---

## TEA track definition

A **TEA-track row** scores under AC + LC + TSA + TEA. It carries `INPUT_QUERY`, `GROUND_TRUTH` (VARIANT with **both** `ground_truth_output` and `ground_truth_invocations`), `track = 'tea'`, and a `category`. `ground_truth_invocations` may be `[]` for no-tool guardrails; never absent (absence is the AC-track shape — see [`ac_details.md`](./ac_details.md)).

---

## TEA category guidance

> **Internal reference only.** Use this section to design questions internally. Do NOT print tool-type tables, coverage rules, or category distributions to the user.

TEA-track categorization is **tool-type-centric**, not question-purpose-centric. Each row belongs to the `tool_type` of the tool the agent should invoke for it — `sql`, `search`, or `custom`. (Don't reuse AC's *Core / Edge / Ambiguous / Data validation / Instruction compliance* dimensions; those describe the **answer string**, which is AC's concern. TEA grades the **invocation**, so the natural axis is the tool family being invoked.)

### Tool-type coverage rule (mandatory)

A TEA-track plan **must include every tool-type that appears in the agent config**. Read the agent spec, enumerate the set of `tool_type` values across all tools, and assert that the final dataset has at least one row per type. The three canonical tool-types are:

| `tool_type` | What it does | Typical Cortex tools | When to include |
|---|---|---|---|
| `sql` | Natural-language → SQL → tabular result over a Snowflake table or semantic view | Cortex Analyst, custom SQL data agents | **Mandatory whenever any `sql` tool exists in the agent config.** SQL is the most popular Cortex Agent tool family; production agents almost always have one. |
| `search` | Semantic retrieval over an indexed corpus | Cortex Search Service | **Mandatory whenever any `search` tool exists in the agent config.** The second-most popular family; most multi-modal agents pair an Analyst with a Search service. |
| `custom` | Arbitrary user-defined tool — external function, generic tool, custom UDF, third-party API wrapper | Custom generic tools, external functions, custom data agents | **Mandatory whenever any `custom` tool exists in the agent config.** Often a one-off (workflow trigger, write-back, third-party lookup); easy to forget — explicitly enumerate the agent config before approving the plan. |

> **Coverage assertion before approving the plan:** for every tool-type `T` present in the agent config, the dataset has `≥ 1` TEA row whose `ground_truth_invocations[].tool_name` resolves to a tool of type `T`. If the agent config has all three (`sql` + `search` + `custom`), all three tool-types must be represented — even if `custom` is rarely used in production.

### Default distribution (tool-type-weighted, popularity-first)

Allocate TEA-track rows in proportion to **how heavily each tool-type is used in the agent's production traffic** (read from the prior production query if available, otherwise from the agent spec's stated purpose). When the popularity split is unknown, fall back to this default that biases toward the most popular families while still guaranteeing coverage of the least popular ones:

| `tool_type` | Default share of TEA-track rows | Reasoning |
|---|---|---|
| `sql` | **50%** | Most popular; analytical / quantitative questions dominate real workloads. Use at least one row per distinct SQL tool (most agents register one Analyst per semantic view). |
| `search` | **35%** | Second-most popular; covers semantic / retrieval / KB-style questions. Use at least one row per distinct Search service. |
| `custom` | **10%** | Least popular but **must not be 0%** if any custom tool exists. One row per custom tool is the floor; add more only if production traffic shows heavy custom-tool use. |
| Multi-tool flows | **5%** | Reserved slice for questions that legitimately invoke `≥ 2` tools (any combination of types). See [§ Multi-tool flow rule](#multi-tool-flow-rule) below. |

When the agent config is missing a tool-type (e.g. a SQL-only agent with no Search and no Custom tools), **redistribute that tool-type's share** proportionally across the present types — never include a row for a tool-type the agent doesn't have.

### Per-tool checklist (mandatory)

Within each tool-type's share, for **each individual tool** of that type include:

- **1–2 clear routing questions** — the question maps unambiguously to this tool (lets TEA grade tool selection + invocation on the happy path).
- **1 negative-routing question** — superficially similar but should **not** invoke this tool (the agent should pick a sibling tool or decline).
- **1 ambiguous-routing question** — could plausibly route here or to a sibling of the same type or of a different type; the agent should clarify before invoking.

### Multi-tool flow rule

Reserve **at least one row per agent** (more when popularity warrants) for questions that legitimately invoke **two or more tools** in a specific sequence or combination. Document the expected tool sequence in the row's `notes` (e.g. `Expected flow: finance_analyst (sql) → support_search (search)`) and reflect it in `ground_truth_invocations` as a two-or-more-element array in trace order. Multi-tool flows are the only category that can mix tool-types within a single row, and they are essential for catching orchestration bugs that single-tool rows miss.

---

## TEA prereqs: per-tool context gathering

Before authoring TEA-track ground truth (`tool_output` payloads), the calling skill must gather per-tool context. Without this context, `tool_output` is just placeholders and TEA will not score above noise. For each tool the agent has, run the matching block:

**`cortex_analyst_text_to_sql`** — load the semantic model used by the tool. Find the model path in `agent_config.json` (each Cortex Analyst tool entry has `semantic_model_file` / `semantic_view` / `semantic_view_id`). Then read it:

```sql
-- Stage-based semantic model
SELECT $1 FROM @<DB>.<SCHEMA>.<STAGE>/<model.yaml>;

-- OR semantic view (preferred when present)
DESCRIBE SEMANTIC VIEW <DB>.<SCHEMA>.<VIEW_NAME>;
SELECT * FROM SEMANTIC_VIEW(<DB>.<SCHEMA>.<VIEW_NAME> DIMENSIONS *) LIMIT 1;
```

Extract: **table/view names**, **dimension columns**, **measure columns**, **time/date columns**, and any **filters** the model exposes. These are the identifiers the SQL judge will look for.

**`cortex_search`** — sample the indexed corpus so you know what phrases actually appear in retrieved documents:

```sql
SHOW CORTEX SEARCH SERVICES LIKE '<service_name>' IN SCHEMA <DB>.<SCHEMA>;
DESCRIBE CORTEX SEARCH SERVICE <DB>.<SCHEMA>.<SERVICE_NAME>;

SELECT * FROM TABLE(
    CORTEX_SEARCH_DATA_SCAN(SERVICE_NAME => '<DB>.<SCHEMA>.<SERVICE_NAME>')
) LIMIT 10;
```

Note 3–5 short phrases that occur in the corpus — these become your `tool_output` substring expectations.

**`web_search`** — no corpus query needed; note the *kind* of source you expect (official docs, news article, vendor site).

**`generic`** — read the tool's resource spec from `agent_config.json` (`tool_resources.<tool_name>` has `execution_environment`, `identifier`, and a parameter list). For SQL-callable tools, also:

```sql
DESCRIBE PROCEDURE <DB>.<SCHEMA>.<PROC_NAME>(<arg_types>);
DESCRIBE FUNCTION  <DB>.<SCHEMA>.<FUNC_NAME>(<arg_types>);
```

Capture: **parameter names + types** (used to author `tool_input` JSON), and **return shape / output column names** (used to author `tool_output` verification criteria).

Consolidate the findings into a context table the calling skill can announce to the user:

```
| tool_name | tool_type | Tables / corpus / proc identifiers | Key columns / params / output keys |
|-----------|-----------|------------------------------------|------------------------------------|
| …         | …         | …                                  | …                                  |
```

---

## TEA-track authoring

### `ground_truth_invocations` schema

JSON array of expected tool calls, in execution order. Each element: `{"tool_name": "...", "tool_input": "...", "tool_output": "..."}` (all three keys required).

States — populated (normal), `[]` (no-tool guardrail; TSA scores 1.0 iff agent invokes nothing), absent (AC-track only — invalid for TEA). See [`ground_truth_schema.md` § trichotomy](./ground_truth_schema.md#the-ground_truth_invocations-trichotomy).

`tool_input` rules:

- First / only call → paraphrase `INPUT_QUERY` in the form the tool receives (NL sentence for analyst/search, JSON object for generic).
- Nth call (chained) → state the dependency on the prior tool's output explicitly.
- For `cortex_search` / `web_search` / `generic`, `tool_input` MUST read as **natural language** — no `SELECT … FROM …`. The structured query goes in `tool_output`'s `Search Query:` / `Procedure Call:` part instead.

### Two-part `tool_output` format

Every populated `tool_output` is a string with **two parts joined by a blank line**:

```
<Procedure-label>:
<runnable SQL / canonical Search Query / real Procedure Call>

<Result-label>:
<literal rows / corpus phrase / proc output — must be consistent with ground_truth_output>
```

Labels per `tool_type` (mandatory — used by the judge):

| tool_type | Procedure label | Result label |
|-----------|-----------------|--------------|
| `cortex_analyst_text_to_sql`, `system_execute_sql` | `SQL:` | `Expected Result:` |
| `cortex_search`, `web_search` | `Search Query:` | `Expected Result:` |
| `generic` | `Procedure Call:` | `Expected Result:` |

`Verify the SQL …` / `Verify the result …` / `Check if …` paraphrases are **NOT** allowed in either part for any row. For concrete JSON examples per `tool_type`, see [§ TEA INSERT template (scratch)](#tea-insert-template-scratch).

### SQL ground-truth requirements

SQL-tool rows must use **runnable SQL** AND a **real executed result**:

1. **`SQL:` body is runnable SQL, never a paraphrase.** Real Snowflake SQL using identifiers from the agent's semantic model. NL descriptions are not acceptable.
2. **Execute the SQL and paste the actual result into `Expected Result:`.** Literal rows / values / numbers / identifiers. `Verify the result …` paraphrases are not acceptable.
3. **When invoking the agent for ground truth, copy SQL and result from the trace verbatim** — see [§ Trace projection from agent invocations](#trace-projection-from-agent-invocations) for the projection SQL across all tool families.

If the SQL errors or returns nothing, fix the identifiers and re-run — do not relax to `Verify …` mode. Rows whose SQL has not been executed must not be inserted.

For `cortex_search` / `web_search` / `generic`, the procedure body and `Expected Result:` are likewise concrete (real corpus phrase / real proc output), and `tool_input` reads as natural language.

### TEA quality checklist

Run before approving the TEA-track table (scratch Step 4 / production Step 6). A row failing any per-row checkbox must be re-authored; a coverage failure means add the missing rows before approving.

**Per-row checks:**

- [ ] `tool_output` follows the [Two-part format](#two-part-tool_output-format) with the right Procedure + Result labels for the tool_type.
- [ ] `Expected Result:` is consistent with `ground_truth_output` (same numbers, identifiers, claims); no placeholders anywhere.
- [ ] `SQL:` body is literal runnable SQL that was executed against real data, per [SQL ground-truth requirements](#sql-ground-truth-requirements). Non-SQL `tool_input` reads as natural language.
- [ ] Multi-step chains have one array entry per invocation in trace order, with chained `tool_input` referencing the prior tool's output. **`len(ground_truth_invocations)` MUST equal `detected_invocations`** from the [Multi-tool invocation detection](#multi-tool-invocation-detection-mandatory-before-drafting) query for the same `user_question` — never collapse multi-family hits (e.g. `cortex_search → cortex_analyst`) into a single entry.
- [ ] No-tool questions use `[]`, not an omitted field. `tool_name` for web search is exactly `"web_search"`.
- [ ] `ground_truth_output` follows the [AC-track Good/Bad rules](./ac_details.md#expected-answer-goodbad-table).

**Per-table coverage checks** (see [§ TEA category guidance](#tea-category-guidance)):

- [ ] Every `tool_type` in the agent config is represented (≥ 1 row), and no row invokes a tool-type absent from the config — [Tool-type coverage rule](#tool-type-coverage-rule-mandatory).
- [ ] Popularity split (≈50 % `sql` / 35 % `search` / 10 % `custom` / 5 % multi-tool) is approximated or a deliberate alternative is justified — [Default distribution](#default-distribution-tool-type-weighted-popularity-first).
- [ ] Per-tool routing mix is present (1–2 clear + 1 negative + 1 ambiguous per tool) — [Per-tool checklist](#per-tool-checklist-mandatory).
- [ ] At least one [multi-tool flow row](#multi-tool-flow-rule) is present.
- [ ] Methodology #2 rows reuse the trace verbatim (exact `observed_sql` / search query / `CALL` signature, exact agent result) — see [§ TEA drafting by methodology](#tea-drafting-by-methodology).

---

## TEA drafting by methodology

- **`<METHODOLOGY> = 1` (build manually).** Hand-author each row's `tool_output` against the agent's semantic model or corpus: write the canonical SQL / search query / `CALL` signature, execute it (or sample the corpus), and paste the literal result into `Expected Result:`. The [SQL ground-truth requirements](#sql-ground-truth-requirements) and [Two-part format](#two-part-tool_output-format) apply identically — only the source of the call differs.
- **`<METHODOLOGY> = 2` (invoke the user's agent).** The agent has already been invoked in scratch's Step 3 shared agent-invocation batch with `<batch_start>` fixed beforehand (see [`subagents.md` Step 4](./subagents.md#step-4-projection--trace-window-invariants)). **Do NOT re-invoke.** Project the TEA-track `INPUT_QUERY` subset from the same `<batch_start>` window using the per-family SQL in [§ Trace projection from agent invocations](#trace-projection-from-agent-invocations), then apply [§ Apply the trace to ground truth](#apply-the-trace-to-ground-truth) to copy verbatim into `tool_output` and re-run for `Expected Result:`. TEA-track questions in `<MISS_LIST>` (no trace found in the `<batch_start>` window) are dropped from `<TEA_COUNT>` per the [Step 3 miss-rate report](./subagents.md#step-3-verification--miss-rate-report) — do not re-invoke or hand-author a substitute via methodology #1.


---

## Trace projection from agent invocations

> **All content in this section is internal implementation detail. Do NOT print tool-type scope, tool mappings, namespace tables, exclusion rules, or query structure to the user.** Execute the queries silently and use results internally only.

Used by `dataset-scratch` Step 3 when the user picks **methodology #2 — invoke the agent for ground truth** (skip under methodology #1). Record the timestamp just before the first invocation as `<batch_start>`, run the agent across every approved question, then project from the same window: `record_root.*` drives `ground_truth_output`; per-tool-family `agent.tool.<family>.*` drives `tool_output` for TEA-shaped rows. Universal planning attributes (`agent.planning.tool_execution.*`) are JSON arrays — one element per tool call in that turn — and serve as the fallback for any tool family without a dedicated namespace.

### Source of truth (observability table function only)

All ground truth comes from `TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS('<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'))`. Do NOT parse SSE traces or local files. Every query uses `WHERE TIMESTAMP >= '<batch_start>' AND TIMESTAMP < '<batch_end>'` (both values from `batch_meta.json`) to cap the scan window tightly.

### Projection routing by track

| Track | What to execute (in order) |
|-------|---------------------------|
| **AC** | 1. [Query 1 (record_ids + answers)](#query-1--record_ids--answers) — returns `record_id`, `user_question`, `agent_answer`. **Nothing else.** |
| **TEA** | 1. [Query 1 (record_ids + answers)](#query-1--record_ids--answers) |
| | 2. [Query 2 — SQL full](#query-2--sql-full) — skip if no `cortex_analyst` tools |
| | 3. [Query 3 — Search full](#query-3--search-full) — skip if no `cortex_search` tools |
| | 4. [Query 4 — Generic full](#query-4--generic-full) — skip if no `web_search` or `generic` tools |
| | 5. [Stitch + multi-tool detection](#stitching--multi-tool-detection) — join via `record_id`, order by `event_ts`, build `ground_truth_invocations` |

### Exclusion rules (mandatory)

Every per-family query below MUST exclude these — they are infrastructure, not ground truth:

1. **Memory-tool services.** Any `cortex_search` service whose FQN matches `*.MEMORY.MEMORY_*`. The agent preloads memory on every turn — never a ground-truth invocation.
2. **Planning / system / server tool types.** The SKIP set for Query 4's `tool_execution.type` filter: `system_execute_sql`, `system_agentic_semantic_context`, `cortex_analyst_text_to_sql`, `cortex_search`, `server_skill`, `server_mcp`, `code_interpreter`, `data_to_chart`, `system_literal_retriever`, `bash`, `upload_asset`, `schedule_snowflake_task`.

---

### Query 1 — record_ids + answers

Returns `record_id` → `user_question` mapping AND `agent_answer` (drives `ground_truth_output` for both AC and TEA). AC-track stops here.

```sql
SELECT
    RECORD_ATTRIBUTES:"ai.observability.record_id"::STRING         AS record_id,
    RECORD_ATTRIBUTES:"ai.observability.record_root.input"::STRING AS user_question,
    RECORD_ATTRIBUTES:"ai.observability.record_root.output"::STRING AS agent_answer
FROM TABLE(
  SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
  )
)
WHERE TIMESTAMP >= '<batch_start>' AND TIMESTAMP < '<batch_end>'
  AND RECORD_ATTRIBUTES:"ai.observability.span_type"::STRING = 'record_root'
  AND RECORD_ATTRIBUTES:"ai.observability.record_root.input"::STRING IN (<list of approved INPUT_QUERY values>)
QUALIFY ROW_NUMBER() OVER (PARTITION BY user_question ORDER BY TIMESTAMP DESC) = 1;
```

Save results as `<APPROVED>`. Use `record_id` values as `<approved_record_ids>` in subsequent queries.

---

### Query 2 — SQL full

Skip if agent has no `cortex_analyst` tools. Returns detection columns + full payload for `tool_output` authoring.

```sql
SELECT
    RECORD_ATTRIBUTES:"ai.observability.record_id"::STRING AS record_id,
    TIMESTAMP AS event_ts,
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.sql_execution.analyst_tool_name"::STRING AS tool_name,
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.cortex_analyst.semantic_model"::STRING   AS semantic_model,
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.sql_execution.query"::STRING             AS observed_sql,
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.sql_execution.final_sql"::STRING         AS final_sql,
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.sql_execution.result"::STRING            AS result_json,
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.sql_execution.execution_status"::STRING  AS exec_status
FROM TABLE(
  SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
  )
)
WHERE TIMESTAMP >= '<batch_start>' AND TIMESTAMP < '<batch_end>'
  AND RECORD_ATTRIBUTES:"ai.observability.record_id"::STRING IN (<approved_record_ids>)
  AND RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.sql_execution.query" IS NOT NULL
ORDER BY TIMESTAMP;
```

---

### Query 3 — Search full

Skip if agent has no `cortex_search` tools. Returns detection columns + full payload.

```sql
SELECT
    RECORD_ATTRIBUTES:"ai.observability.record_id"::STRING AS record_id,
    TIMESTAMP AS event_ts,
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.cortex_search.name"::STRING    AS service_fqn,
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.cortex_search.query"::STRING   AS search_query,
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.cortex_search.filter"::STRING  AS filter_expr,
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.cortex_search.results"::STRING AS results_json,
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.cortex_search.columns"::STRING AS columns_json
FROM TABLE(
  SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
  )
)
WHERE TIMESTAMP >= '<batch_start>' AND TIMESTAMP < '<batch_end>'
  AND RECORD_ATTRIBUTES:"ai.observability.record_id"::STRING IN (<approved_record_ids>)
  AND RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.cortex_search.query" IS NOT NULL
  AND RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.cortex_search.name"::STRING NOT ILIKE '%.MEMORY.MEMORY_%'
ORDER BY TIMESTAMP;
```

---

### Query 4 — Generic full

Skip if agent has no `web_search` or `generic`/`custom` tools. Returns detection columns + full payload via LATERAL FLATTEN on planning arrays.

```sql
WITH plan_events AS (
    SELECT
        RECORD_ATTRIBUTES:"ai.observability.record_id"::STRING AS record_id,
        TIMESTAMP AS event_ts,
        TRY_PARSE_JSON(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.tool_execution.name"::STRING)           AS names_arr,
        TRY_PARSE_JSON(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.tool_execution.type"::STRING)           AS types_arr,
        TRY_PARSE_JSON(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.tool_execution.argument.name"::STRING)  AS arg_names_arr,
        TRY_PARSE_JSON(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.tool_execution.argument.value"::STRING) AS arg_values_arr,
        TRY_PARSE_JSON(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.tool_execution.results"::STRING)        AS results_arr
    FROM TABLE(
      SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
        '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
      )
    )
    WHERE TIMESTAMP >= '<batch_start>' AND TIMESTAMP < '<batch_end>'
      AND RECORD_ATTRIBUTES:"ai.observability.record_id"::STRING IN (<approved_record_ids>)
      AND RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.tool_execution.name" IS NOT NULL
)
SELECT
    p.record_id,
    p.event_ts,
    f.index           AS invocation_idx,
    f.value::STRING   AS tool_name,
    p.types_arr[f.index]::STRING   AS tool_type,
    p.arg_names_arr[f.index]       AS arg_names,
    p.arg_values_arr[f.index]      AS arg_values,
    p.results_arr[f.index]         AS results
FROM plan_events p, LATERAL FLATTEN(input => p.names_arr) f
WHERE p.types_arr[f.index]::STRING NOT IN (
    'system_execute_sql', 'system_agentic_semantic_context', 'cortex_analyst_text_to_sql',
    'cortex_search', 'server_skill', 'server_mcp', 'code_interpreter',
    'data_to_chart', 'system_literal_retriever', 'bash', 'upload_asset',
    'schedule_snowflake_task'
)
ORDER BY p.event_ts, f.index;
```

---

### Stitching + multi-tool detection

After Query 2 + 3 + 4 complete, stitch in-memory:

1. **Join** all result rows to `<APPROVED>` via `record_id` → `user_question`.
2. **Union** rows from Query 2 (family=`sql`, tool_name=`tool_name`), Query 3 (family=`cortex_search`, tool_name=`service_fqn`), Query 4 (family=`generic`, tool_name=`tool_name`).
3. **Sort** all invocations for each `user_question` by `event_ts` ascending — this is the canonical `tool_sequence` order.
4. **Count** per `user_question` → `detected_invocations`. Any question with invocations from 2+ families or 2+ distinct tools is a **multi-tool flow**.
5. **Build `ground_truth_invocations`** array in `tool_sequence` order. Each element uses the full payload from the same row:
   - SQL rows → `tool_output` = `"SQL: \n <final_sql> \n \n Expected Result: \n <result_json parsed>"`
   - Search rows → `tool_output` = `"Search Query: \n <search_query> \n \n Expected Result: \n <results_json snippet>"`
   - Generic rows → `tool_output` = `"Procedure Call: \n CALL <tool_name>(<arg_names> => <arg_values>) \n \n Expected Result: \n <results>"`
6. The row's `ground_truth_invocations` array MUST have exactly `detected_invocations` entries in the `event_ts`-sorted order. Drop the row if you cannot reconstruct all of them.

> **After stitching.** Every TEA-shaped row's `ground_truth_invocations` MUST conform to [§ `ground_truth_invocations` schema](#ground_truth_invocations-schema) and the [Two-part `tool_output` format](#two-part-tool_output-format) — same field names, same array shape, same labels per `tool_type`. No-tool guardrails use `[]` (not an omitted field, not JSON `null`).

For each tool execution, copy **verbatim** into `tool_output`: `final_sql` → `SQL:`, `search_query` → `Search Query:`, reconstructed `CALL <tool_name>(<arg_name> => <arg_value>, …)` → `Procedure Call:`. Then **re-run** the exact SQL / query / call and paste the literal result into `Expected Result:` (per the [SQL ground-truth requirements](#sql-ground-truth-requirements)). Do not paraphrase the trace.

---

## TEA INSERT template (scratch)

> **Run silently — do NOT print anything to the user.** No progress messages, no "inserting TEA rows" / "inserting AC rows" / track labels / row counts. The calling skill already printed "Inserting rows..." — execute the SQL and move on without any user-facing output.

`dataset-scratch` Step 4 when `<METRIC_SCOPE>` ∈ {`both`, `tea`} and `<TEA_COUNT> > 0`. `column3` is the JSON string for `ground_truth_invocations` (`'[]'` for no-tool guardrails).

**Use `$$...$$` (dollar-quoting) for `column3`** — this disables Snowflake's backslash escape processing so `\n` stays as a literal two-character JSON escape. Do NOT use single quotes for JSON strings containing `\n`. Single quotes inside the JSON need no escaping with dollar-quoting.

In `tool_output`, use `\n` (not a real newline) to separate lines. Format: `"SQL: \n <sql> \n \n Expected Result: \n <result>"` — note the spaces around `\n` for readability in the stored JSON.

```sql
INSERT INTO <DATABASE>.<SCHEMA>.EVAL_DATASET_<AGENT_NAME>_<YYYYMMDD_HHMMSS> (INPUT_QUERY, GROUND_TRUTH, category, track, notes)
SELECT column1,
       TO_VARIANT(OBJECT_CONSTRUCT(
           'ground_truth_output',      column2,
           'ground_truth_invocations', PARSE_JSON(column3)
       )),
       column4,
       'tea',
       column5
FROM VALUES
-- 1) cortex_analyst — TWO-PART: SQL: + Expected Result:
('What was the total revenue per product category for Q3 2025?',
 'Q3 2025 revenue: Services $1.6B, Hardware $0.7B, Subscriptions $0.2B; total ~$2.5M.',
 $$[{"tool_name":"sales_analyst","tool_input":"total revenue per product category for Q3 2025","tool_output":"SQL: \nSELECT product_category, SUM(net_amount) AS total_revenue FROM SALES_DB.PUBLIC.SALES_TRANSACTIONS WHERE order_date BETWEEN '2025-07-01' AND '2025-09-30' GROUP BY product_category \n \nExpected Result: \nServices $1.6B, Hardware $0.7B, Subscriptions $0.2B"}]$$,
 'core_use_case',
 'analyst — literal SQL + literal result'),

-- 2) cortex_search — TWO-PART: Search Query: + Expected Result:
('What are the most common billing complaints?',
 'Customers most commonly report failed payment and incorrect charge issues.',
 $$[{"tool_name":"support_search","tool_input":"billing problems and payment issues","tool_output":"Search Query: \nbilling problems and payment issues \n \nExpected Result: \nRetrieved chunks contain the phrase 'failed payment' and reference billing"}]$$,
 'core_use_case',
 'search — query + corpus phrase'),

-- 3) multi-step chain (search → generic) — chained tool_input; demonstrates Procedure Call:
('List the open orders for Acme Corporation.',
 'Acme Corporation (customer_id C-1024) has two open orders: ORD-981 (shipped) and ORD-994 (processing).',
 $$[{"tool_name":"customer_search","tool_input":"find customer named Acme Corporation","tool_output":"Search Query: \nAcme Corporation \n \nExpected Result: \ncustomer_id = 'C-1024'"},{"tool_name":"order_tracker","tool_input":"Using customer_id C-1024 from customer_search above, list open orders","tool_output":"Procedure Call: \nCALL list_open_orders(customer_id => 'C-1024') \n \nExpected Result: \nORD-981 (shipped) and ORD-994 (processing)"}]$$,
 'multi_tool',
 'chained — search → proc, chained tool_input'),

-- 4) no-tool guardrail — ground_truth_invocations MUST be []
('What is your name?',
 'I am a sales analytics assistant.',
 '[]',
 'instruction_compliance',
 'no-tool guardrail test');
```

Source-table column types and the `TO_VARIANT(OBJECT_CONSTRUCT(...))` build pattern apply identically to AC and TEA INSERTs — see [`ground_truth_schema.md` § Source-table column types](./ground_truth_schema.md#source-table-column-types).

---

## Production / expand step content

Annotation-table DDL, `UPDATE … SET expected_tools_json`, and `OBJECT_INSERT(...)` staging fix-ups live inline in `dataset-production` Steps 4 / 5 / 6 and `dataset-expand` Step 3. When authoring `expected_tools_json` values, apply the [Two-part `tool_output` format](#two-part-tool_output-format), the [SQL ground-truth requirements](#sql-ground-truth-requirements), and the [TEA INSERT examples](#tea-insert-template-scratch).
