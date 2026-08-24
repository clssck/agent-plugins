---
name: agent-studio-agent-dataset-scratch
description: "Create a new evaluation dataset from scratch for a Cortex Agent. Use when: new agent needs eval dataset, build evaluation data from scratch, design test questions, no existing dataset."
parent_skill: agent-studio-agent-dataset
---

# Create Evaluation Dataset from Scratch

> Tool usage and dataset format: see parent `dataset/SKILL.md`.
> AC-track authoring style guide: [`refs/ac_details.md`](../refs/ac_details.md).
> TEA-track authoring style guide: [`refs/tea_details.md`](../refs/tea_details.md).
> `GROUND_TRUTH` JSON shape and the `ground_truth_invocations` trichotomy: [`refs/ground_truth_schema.md`](../refs/ground_truth_schema.md).

**Goal:** Design and build an evaluation dataset for a new or lightly tested agent.

**MANDATORY:** Follow these steps in order. **As soon as the agent is identified in Step 1, you MUST ask the user for the evaluation metric scope (Step 1.1 — AC / TEA / Both). Step 1.2 (per-track counts) is defaulted from the agent's tool count — NO user prompt. Do not run any other step, query, or tool-discovery action until the Step 1.1 metric-scope answer is captured.**

---

## Invocation modes

| Mode | Trigger | Behavior |
|---|---|---|
| `standalone` (default) | Invoked directly by the user. | Run **all** steps as written. |
| `build-only` | Invoked by [`dataset-expand`](../dataset-expand/SKILL.md) to produce a staging table the caller will merge. | Skip Step 1 (caller already identified the agent) and Step 5 (caller will register the merged table). Run Step 1.1 and Step 1.2 normally — ASK the user for `<METRIC_SCOPE>` and default `<AC_COUNT>` / `<TEA_COUNT>` here; the caller does **not** supply them. In Step 4 write into the caller-supplied `target_table` FQN, not `EVAL_DATASET_<AGENT_NAME>_<YYYYMMDD_HHMMSS>`. After Step 4 return control to the caller without printing "STOP" or "workflow complete". |

In `build-only` mode the caller supplies: `agent_name`, `database`, `schema`, `target_table`. `<METRIC_SCOPE>`, `<AC_COUNT>`, and `<TEA_COUNT>` are captured **here** in Step 1.1 / 1.2 and surfaced back to the caller when control returns.

> **Do NOT print "build-only mode", "invoked by expand", or any internal mode information to the user.** Run transparently.

---

## Step 1: Identify Agent and Understand Capabilities

Ask the user for the agent FQN (`DATABASE.SCHEMA.AGENT_NAME`).

Otherwise:

> Print to user: `"Which agent would you like to build an evaluation dataset for? Please provide the database, schema and agent name (e.g. MY_DB.MY_SCHEMA.MY_AGENT)."`

**STOP** and wait for the user to provide the agent name. Do NOT run `SHOW AGENTS IN ACCOUNT` — it scans every agent and is extremely slow. Only proceed once the user provides the name.

1. Once the agent FQN is known, read the agent configuration via `agent-read` (do **not** use `DESCRIBE AGENT` / `DESC AGENT`; do NOT print tool details, config contents, or tool-type mappings to the user — extract internally only):

```bash
cortex agent-studio agent-read --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME>
```

2. From the returned spec, extract internally (do NOT print these details to the user):
   - What tools are available (Cortex Analyst, Cortex Search, Web Search, generic procs, etc.)
   - What questions each tool can answer
   - The boundaries between tools

3. Examine `instructions`, response instructions, and orchestration sections internally for:
   - **Guardrails**: Does the agent refuse certain question types?
   - **Persona**: Is it customer-facing? Analytics-focused?
   - **Sample questions**: What questions is it designed to answer?

   **Common pitfall**: Creating analytics questions for a customer-service agent that's programmed to deflect data queries.

4. **Print only this to the user:**

> Print to user: `"Fetched the configuration for agent <AGENT_NAME>."`

## Step 1.1: Choose Evaluation Metrics Scope (MANDATORY — ask immediately after Step 1, before any other step)


ASK the user:

```
Snowflake has developed a methodology to evaluate an agent's performance across its thinking process of Goals, Plans, and Actions — we call it your agent's GPA.

To measure it, we rely on 4 main metrics:
• Tool Selection Accuracy — did the agent choose the right tools for the user's goal?
• Tool Execution Accuracy — evaluates Plans to Actions: did each tool receive the right input and produce the right output?
• Answer Correctness —  does the final answer match what the user expected?
• Logical Consistency —  is the agent's reasoning coherent across instructions, planning, and tool calls?

We believe this provides a solid starting point for understanding your agent's performance, and when combined with your own custom LLM judges, gives a robust picture of quality.

For more information, see:
  • https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-evaluations
  • https://www.snowflake.com/en/developers/guides/best-practices-for-evaluating-cortex-agents/

Would you like to:
A) Use recommended settings — create a dataset covering all 4 snowflake metrics
B) Customize — choose which metrics to include
C) Can you provide me more details to recommended settings?
```

**STOP** for the user's answer.

If A → set `<METRIC_SCOPE> = both`, print `"Using recommended: covering all 4 snowflake metrics."` and continue to Step 1.2.

If C → print the explanation, then re-ask the same A/B/C question:

```
The recommended settings follow Snowflake best practices — it creates a dataset covering all 4 Snowflake evaluation metrics: answer correctness, logical consistency, tool selection accuracy, and tool execution accuracy. This gives the most complete picture of agent quality.

For more details on these metrics, see: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-evaluations
```

If B → ASK the follow-up:

```
Which evaluation metrics should this dataset support?

A) All Snowflake metrics (recommended) — covers answer correctness, logical consistency, tool selection accuracy, and tool execution accuracy.
B) Tool metrics only — covers tool execution accuracy and tool selection accuracy.
C) Correctness metrics only — covers answer correctness and logical consistency.
D) What do these options mean?
```

If D → print the following explanation, then re-ask this A/B/C/D question:

```
Here's what each option means:

• All Snowflake metrics (recommended) — creates a dataset covering all 4 Snowflake evaluation metrics: answer correctness, logical consistency, tool selection accuracy, and tool execution accuracy. This gives the most complete picture of agent quality.
• Tool metrics only — tests whether the agent picks the right tools and runs the right queries. Covers tool selection accuracy and tool execution accuracy metrics.
• Correctness metrics only — tests whether the agent gives factually correct final answers. Covers answer correctness and logical consistency metrics.

For more details on these metrics, see: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-evaluations
```

If A → `<METRIC_SCOPE> = both`.
If B → `<METRIC_SCOPE> = tea`.
If C → `<METRIC_SCOPE> = ac`.

**STOP** for the user's answer. Record as `<METRIC_SCOPE>` ∈ {`both`, `tea`, `ac`}.

### Effect on every later step in this skill

The dataset is built and registered as **one merged table** (no `_AC` / `_TEA` split). Schema details: [`refs/ground_truth_schema.md`](../refs/ground_truth_schema.md).

| `<METRIC_SCOPE>` | Step 1.2 defaults to | Steps 1.3 / 1.4 / 1.5 (TEA prereqs) | Step 4 INSERTs |
|---|---|---|---|
| `both` | `<AC_COUNT> = 10` **and** `<TEA_COUNT> = 20 / 30 / 40` (by tool count) — NO user prompt | Run (for the TEA-track only) | **Both** AC and TEA INSERTs into the same table |
| `tea`  | `<TEA_COUNT> = 20 / 30 / 40` (by tool count); `<AC_COUNT> = 0` auto — NO user prompt | Run | TEA INSERT only |
| `ac`   | `<AC_COUNT> = 20`; `<TEA_COUNT> = 0` auto — NO user prompt | **Skip entirely** — jump directly from Step 1.2 to Step 2 | AC INSERT only |

The optional eval kick-off lives in the parent [`dataset/SKILL.md`](../SKILL.md) **Workflow → Step 3**, not in this skill.

> **In `build-only` mode this step still runs** — the caller does not supply `<METRIC_SCOPE>`. ASK the user here.

---

## Step 1.2: Default AC / TEA question counts (NO user prompt)

> Print to user: `"Calculating the right number of test questions for your agent..."`

Compute `<TOOL_COUNT>` from the agent spec's `tools` array, **excluding** any entry whose `tool_spec.type` is `system_agentic_semantic_context` (internal planning step, not evaluatable). Then resolve counts:

| `<METRIC_SCOPE>` | `<AC_COUNT>` | `<TEA_COUNT>` |
|---|---|---|
| `both` | `10` | `20` if `<TOOL_COUNT> ≤ 15`; `30` if `15 < <TOOL_COUNT> ≤ 30`; `40` if `<TOOL_COUNT> > 30` |
| `tea`  | `0`  | same TEA tier as above |
| `ac`   | `20` | `0` |

> Print to user:
> ```
> I'll create <AC_COUNT + TEA_COUNT> test questions total:
>   - <AC_COUNT> to test answer correctness and logical consistency
>   - <TEA_COUNT> to test tool execution accuracy and tool selection accuracy
> ```

The user may override the defaults explicitly (e.g. *"use 20 AC and 60 TEA"*); otherwise the defaults stand and execution continues immediately. **No STOP.** In `build-only` mode this step still runs (caller does not supply the counts).

---

## Step 1.3: Tool-Type Discovery (TEA-only — skip if `<METRIC_SCOPE> = ac`)

> Run silently — do NOT print anything to the user for this step.

> **Gate:** Run only when `<METRIC_SCOPE>` ∈ {`both`, `tea`}. Skip entirely under `ac`.

Derive `tool_type` for each entry in the agent spec's `tools` array (no observability data needed yet). Skip tools with type `system_agentic_semantic_context` — internal planning step, not evaluatable.

| `tool_spec.type` in spec | `tool_type` (eval runtime) | `tool_name` rule |
|---------------------------|----------------------------|------------------|
| `CortexAnalystTool` | `cortex_analyst_text_to_sql` | value from spec |
| `CortexSearchTool` | `cortex_search` | value from spec |
| `WebSearchTool` | `web_search` | always `"web_search"` (fixed) |
| anything else | `generic` | value from spec |

The authoring template for each `tool_type`'s `tool_output` (Procedure label + `Expected Result:` block) is owned by [`refs/tea_details.md` § Two-part `tool_output` format](../refs/tea_details.md#two-part-tool_output-format) (with concrete JSON in the [TEA INSERT template](../refs/tea_details.md#tea-insert-template-scratch)) — do **not** restate it here; Steps 3–4 link to those sections when they reach the authoring step.

---

## Step 1.4: Gather Tool Context for Ground Truth (TEA-only — skip if `<METRIC_SCOPE> = ac`)

> Run silently — do NOT print anything to the user for this step.

> **Gate:** Run only when `<METRIC_SCOPE>` ∈ {`both`, `tea`}. Skip entirely under `ac`.

For each tool found in Step 1.3, run the matching context-gathering block from [`refs/tea_details.md` § TEA prereqs: per-tool context gathering](../refs/tea_details.md#tea-prereqs-per-tool-context-gathering) — the per-`tool_type` SQL (semantic model, search corpus, generic procedure / function) and the consolidated context-table format both live there. Apply the queries to the tools enumerated in Step 1.3. Do NOT print query results or tool details to the user.

---

## Step 1.5: Declare Tool-Type Scope (TEA-only — skip if `<METRIC_SCOPE> = ac`) — default to Mixed (NO user prompt)

> Run silently — do NOT print anything to the user for this step.

**Default to `Mixed`.** Do **not** ask the user — the dataset curation defaults pre-pick `Mixed` for speed. Declare the scope explicitly so the per-category coverage requirement (parent [`SKILL.md`](../SKILL.md#tool-type-scope-declaration-mandatory-first-step)) is on record. The three canonical tool-type categories (SQL / Search / Custom) and the coverage assertion are owned by [`refs/tea_details.md` § Tool-type coverage rule](../refs/tea_details.md#tool-type-coverage-rule-mandatory) — do not restate the definitions here. Build the per-tool mapping from Step 1.3's `tool_spec.type` → category translation. No user-facing print for this step — proceed silently.

If, after Step 1.3, **every** discovered tool maps to a single category (e.g. all `cortex_analyst_text_to_sql`), record that single category instead of `Mixed` internally (still no STOP, still no user print).

---

## Step 2: Design question categories

> Print to user: `"Designing test questions for your agent..."`

Pick the distribution(s) that apply for `<METRIC_SCOPE>` and design questions against them. Each question carries a `track` ∈ {`ac`, `tea`} label that follows it through Step 3 / Step 4.

> **Under `<METRIC_SCOPE> = both`, design BOTH question sets in this single step** — the `<AC_COUNT>` AC-track questions AND the `<TEA_COUNT>` TEA-track questions, independently. The two sets are **not alternatives**; both must be authored here so that Step 3 (per-track drafting passes) and Step 4 (per-track INSERTs) have both pools available.

| `<METRIC_SCOPE>` | Distribution(s) to apply |
|---|---|
| `both` | Run both distributions in this single Step 2. Apply the [AC-only distribution](../refs/ac_details.md#ac-question-category-guidance) to author the `<AC_COUNT>` AC-track questions and the [TEA-aware distribution](../refs/tea_details.md#tea-category-guidance) to author the `<TEA_COUNT>` TEA-track questions. The per-tool checklist + multi-tool flows requirement apply only to the TEA-track subset. |
| `tea`  | [TEA-aware distribution](../refs/tea_details.md#tea-category-guidance) for the `<TEA_COUNT>` TEA-track questions. |
| `ac`   | [AC-only distribution](../refs/ac_details.md#ac-question-category-guidance) for the `<AC_COUNT>` AC-track questions. Skip the *Tool routing* category, per-tool routing checklist, and *Multi-tool flows* requirement — those exist to exercise TEA. |

**Instruction and orchestration compliance is mandatory in every scope / both tracks.** Apply [`refs/ac_details.md` § AC question category guidance — Instruction and orchestration compliance](../refs/ac_details.md#ac-question-category-guidance) to author at least one dedicated compliance test case per persona / orchestration / response-instruction rule. Place each compliance row in whichever track(s) you want graded (AC, TEA, or both).

## Step 3: Draft Questions with Expected Answers

> Print to user: `"Drafting questions and expected answers..."`

The two tracks are drafted **independently** — independent counts (`<AC_COUNT>` and `<TEA_COUNT>` defaulted in Step 1.2), independent category distributions (Step 2), and a per-question `track` label that follows each row to Step 4. The **methodology** below is **shared** across both tracks — defaulted to `1` (invoke the user's agent) for both, no user prompt.

| `<METRIC_SCOPE>` | What runs in Step 3 |
|---|---|
| `both` | Shared methodology → (if `<METHODOLOGY> = 2`) shared agent-invocation batch → AC-track pass → TEA-track pass. |
| `tea`  | Shared methodology → (if `<METHODOLOGY> = 2`) shared agent-invocation batch → TEA-track pass only. Skip the AC-track subsection. |
| `ac`   | Shared methodology → (if `<METHODOLOGY> = 2`) shared agent-invocation batch → AC-track pass only. Skip the TEA-track subsection. |

Sizing was already resolved inline in Step 1.2 (`<AC_COUNT>` / `<TEA_COUNT>`). The user's override rule from Step 1.2 applies — if they ask for custom counts here, honor that.

**Auto-draft questions — no per-category STOP.** Generate the full set of proposed questions for every category, per track, in **one pass**. Print to user as a single merged table (both tracks together) and proceed immediately to the methodology subsection below.

> Print to user: `"Here's the question table I drafted for you: "`
>```
>Proposed test questions:
>| # | Question | Test Category | Expected Tool |
>|---|----------|---------------|---------------|
>| 1 | [tea question] | Core Use Case (Tool Execution Accuracy and Tool Selection Accuracy) | [tool] |
>| 2 | [tea question] | Multi Tool (Tool Execution Accuracy and Tool Selection Accuracy) | [tool1 → tool2] |
>| 3 | [ac question] | Core Use Case (Answer Correctness and Logical Consistency) | — |
>| 4 | [ac question] | Instruction Compliance (Answer Correctness and Logical Consistency) | — |
>```

**MANDATORY Test Category format:** Every row's `Test Category` column MUST use the format `<Category Name> (<Full Metric Name>)`. The metric name is always one of: `Answer Correctness and Logical Consistency`, `Tool Execution Accuracy and Tool Selection Accuracy`. Never abbreviate to AC/TEA/TSA. Never use underscores. Examples: `Core Use Case (Tool Execution Accuracy and Tool Selection Accuracy)`, `Edge Case (Answer Correctness and Logical Consistency)`, `Multi Tool (Tool Execution Accuracy and Tool Selection Accuracy)`, `Instruction Compliance (Answer Correctness and Logical Consistency)`.

> The user may still volunteer corrections in their next message. If they do, REDO the affected rows here in `dataset-scratch`. Otherwise, **No STOP** — proceed immediately.

For each question, gather: (1) exact question text, (2) expected answer (specific, verifiable), (3) which tool should handle it — **TEA-track only; AC-track rows skip this**, (4) any edge case notes, (5) track label (`'ac'` or `'tea'`).

### Step 3.1: Shared methodology — **STOP and ask the user**


ASK the user:

```
How should the correct answers for these questions be obtained?

A) Build manually (Recommended) — look up the answers by querying your data directly
B) Run the agent — invoke the agent on all questions and record what it does
C) What do these options mean?
```

**STOP** for the user's answer.

If A) → set `<METHODOLOGY> = 1`.
If B) → set `<METHODOLOGY> = 2`.
If C) → print the explanation, then re-ask the same A/B/C question:

```
Here's what each option means:

• Build manually (Recommended) — write and run SQL queries or search queries directly against your data to figure out the correct answers independently of the agent. This takes longer but gives answers that don't depend on the agent's current behavior.
• Run the agent  — send each test question to your agent, record the tools it uses and answers it gives, and use those as the expected behavior. This is faster and reflects how the agent actually works today.
```



Record `<METHODOLOGY>`. The answer_correctness and tool_execution_accuracy track subsections below both branch off this value — do not re-ask.

### Step 3.2: Shared agent-invocation batch (applies whenever `<METHODOLOGY> = 2`, all scopes) — Run the agent across the question batch

> Print to user: `"Running your agent on all test questions to record its behavior..."`

> **Gate:** Run this subsection whenever `<METHODOLOGY> = 2`. Skip entirely when `<METHODOLOGY> = 1`.

Under methodology #2, every question in the in-scope track(s) needs to be run through the user's agent. Unify the invocation phase **before** any per-track drafting — one trace window, one batch — so that under `both` scope the AC-track `ground_truth_output` and the TEA-track `Expected Result:` text come from the **same agent run** (no cross-track drift). The AC-track and TEA-track subsections downstream **read** from this batch via their respective projection queries; they do **not** invoke the agent themselves.

**Batch question list `<ALL_QUESTIONS>`:** under `both` → de-duplicated union of `<AC_COUNT>` AC-track + `<TEA_COUNT>` TEA-track `INPUT_QUERY` strings; under `tea` → TEA-track only (`<TEA_COUNT>`); under `ac` → AC-track only (`<AC_COUNT>`). Set `N = len(<ALL_QUESTIONS>)` and echo to the user once (e.g. `"Combined batch: <N> questions (<AC_COUNT> Answer Correctness + <TEA_COUNT> Tool Execution Accuracy)"` for `both`).

Record `<batch_start>` (timestamp **just before** the first invocation runs) once. Every downstream observability query is scoped to this window, so AC-track and TEA-track projections read the same agent run.

**Then run the agent across `<ALL_QUESTIONS>` using the bounded-parallel Python invoker in [`refs/subagents.md`](../refs/subagents.md) — do NOT invoke the agent one question at a time in-thread.** Specifically:

1. Read [`refs/subagents.md` § Step 2 — Bounded-parallel agent invocation](../refs/subagents.md#step-2-bounded-parallel-agent-invocation-python-threadpoolexecutor) and follow it verbatim — run the single Python script (`≤ 8` concurrent calls via `ThreadPoolExecutor`, 300 s per-call hard timeout) against the agent's REST `:run` endpoint. Substitute `<AGENT_FQN>`, `<CONNECTION>`, and the full `<ALL_QUESTIONS>` list (with per-question `track` labels). The script only triggers runs and records OK/FAIL/TIMEOUT plus `<batch_start>` / `<batch_end>` into `batch_meta.json`; it does NOT project traces or write to `EVAL_DATASET_*`.
2. After the script exits, run [`refs/subagents.md` § Step 3 — Verification + miss-rate report](../refs/subagents.md#step-3-verification--miss-rate-report) once: read `batch_meta.json`, build `<MISS_LIST>` (timeouts + HTTP errors + silent missing spans), decrement `<AC_COUNT>` / `<TEA_COUNT>` per missed question's track label, and print the miss-rate report.
3. Honor [`refs/subagents.md` § Step 4 — Projection + trace-window invariants](../refs/subagents.md#step-4-projection--trace-window-invariants): `<batch_start>` is fixed once, both per-track projections read the same window, and the agent is never re-invoked inside Step 3.4 / Step 3.5.

> Print to user:
> ```
> Running your agent on <N> test questions now.
> **This will take approximately 5 minutes.** I'll let you know when it's done.
> ```

After all invocations complete and the miss-rate report has been printed, the AC-track and TEA-track subsections below project per-track ground truth from this batch — do not invoke the agent again. **Source of truth:** project only from `TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(...))` rows in the `<batch_start>` window per [`refs/tea_details.md` § Source of truth](../refs/tea_details.md#source-of-truth-observability-table-function-only); do not parse the SSE / trace JSON response payload for ground truth.

### Step 3.3: Per-track drafting dispatch


This dispatch table picks which of the two per-track drafting passes below (Step 3.4 AC, Step 3.5 TEA) runs based on `<METRIC_SCOPE>` and `<METHODOLOGY>`:

| `<METRIC_SCOPE>` | `<METHODOLOGY> = 2` order | `<METHODOLOGY> = 1` order |
|---|---|---|
| `both` | Step 3.4 (AC) first, then Step 3.5 (TEA) | **Step 3.5 (TEA) first**, then Step 3.4 (AC) — TEA executes queries; AC reuses results |
| `ac`   | Step 3.4 only | Step 3.4 only |
| `tea`  | Step 3.5 only | Step 3.5 only |

### Step 3.4: AC-track draft pass (run when `<METRIC_SCOPE>` ∈ {`both`, `ac`})

> Print to user: `"Extracting answer correctness and logical consistency data — **this typically takes 1-2 minutes.**"`
> **Do NOT print "AC-track", "TEA-track", or any track label in user-facing output. These are internal labels only.**

> **Gate:** Run when `<METRIC_SCOPE>` ∈ {`both`, `ac`} **and** `<AC_COUNT> > 0`. Reuse `<METHODOLOGY>` from Step 3.1 — do not re-ask.

Apply [`refs/ac_details.md` § AC-track authoring](../refs/ac_details.md#ac-track-authoring). Under `<METHODOLOGY> = 2`, execute **only** [Query 1](../refs/tea_details.md#query-1--record_ids--answers) via `snowflake_sql_execute` (substitute `<batch_start>`, `<batch_end>`, AC-track `INPUT_QUERY` list). Returns `record_id`, `user_question`, `agent_answer` — use `agent_answer` as `ground_truth_output`. Save `<APPROVED>` for TEA reuse. Do NOT run Query 2/3/4 for AC.

Under `<METHODOLOGY> = 1`, for each AC-track question:

**If ANY query fails (SQL error, auth error, timeout, empty result), immediately DROP that question. Do NOT troubleshoot or retry.**

When `<METRIC_SCOPE> = both` (Step 3.5 TEA already ran first):
1. **Reuse the executed query results from Step 3.5** — do NOT re-execute
2. Write `ground_truth_output` based on those results

When `<METRIC_SCOPE> = ac` (no TEA results to reuse):
1. First run `DESCRIBE SEMANTIC VIEW <view>` for each relevant semantic view to understand tables/columns (cache results — do NOT re-describe per question)
2. Build the correct SQL query using the semantic view structure
3. Execute via `snowflake_sql_execute` — if it errors or returns empty, **drop this question and move on**
4. For multi-tool questions: execute the first tool first, use its results for the second tool's input
5. Write `ground_truth_output` as a real answer string with literal values from the results

Print the draft when `<METRIC_SCOPE>` ∈ {`ac`} (no STOP):

```
answer correctness track draft (auto-approved):
| # | Question | Test Category | Expected Output |
|---|----------|---------------|---------------------|
| 1 | [question] | Core Use Case (Answer Correctness and Logical Consistency) | [verifiable answer] |
```

> **No STOP.** Rows failing the checklist are dropped from `<AC_COUNT>`; print a one-line survivor count. Under `<METRIC_SCOPE> = both`, run the TEA pass below next — DO NOT proceed to Step 4 yet; under `ac`, go to Step 4. If the user volunteers corrections later, REDO the affected row(s) here.

### Step 3.5: TEA-track draft pass (run when `<METRIC_SCOPE>` ∈ {`both`, `tea`})

> Print to user: `"Extracting tool execution accuracy and tool selection accuracy data — **this typically takes 3 minutes.**"`
> **Do NOT print "AC-track", "TEA-track", or any track label in user-facing output. These are internal labels only.**

> **Gate:** Run when `<METRIC_SCOPE>` ∈ {`both`, `tea`} **and** `<TEA_COUNT> > 0`. Reuse `<METHODOLOGY>` from Step 3.1 — do not re-ask. Under `both` and `<METHODOLOGY> = 2`, run **after** the AC pass above.

Apply [`refs/tea_details.md` § TEA-track authoring](../refs/tea_details.md#tea-track-authoring). Under `<METHODOLOGY> = 2`, execute via `snowflake_sql_execute` in this exact order (see [Projection routing](../refs/tea_details.md#projection-routing-by-track)):

1. [Query 1](../refs/tea_details.md#query-1--record_ids--answers) — already run in Step 3.4; reuse `<APPROVED>` results
2. [Query 2 — SQL full](../refs/tea_details.md#query-2--sql-full) — skip if no `cortex_analyst` tools
3. [Query 3 — Search full](../refs/tea_details.md#query-3--search-full) — skip if no `cortex_search` tools
4. [Query 4 — Generic full](../refs/tea_details.md#query-4--generic-full) — skip if no `web_search`/`generic` tools
5. [Stitch + multi-tool detection](../refs/tea_details.md#stitching--multi-tool-detection) — join via `record_id`, sort by `event_ts`, build `ground_truth_invocations`

Substitute `<batch_start>`, `<batch_end>`, and `<approved_record_ids>` (from Query 1) into each query. Each row's `ground_truth_invocations` array MUST have exactly `detected_invocations` entries in `event_ts` order — drop the row if you cannot reconstruct all.

Under `<METHODOLOGY> = 1`, for each TEA-track question:

**If ANY query fails (SQL error, auth error, timeout, empty result), immediately DROP that question and move to the next one. Do NOT troubleshoot, retry, or debug.**

**Before writing SQL:** Run `DESCRIBE SEMANTIC VIEW <DB>.<SCHEMA>.<VIEW_NAME>` once per semantic view tool to understand tables, columns, and relationships. Cache the results — do NOT re-describe for every question.

1. Determine which tool(s) should answer it — set `tool_name` for each invocation
2. Using the semantic view structure, build the correct SQL query — this becomes `tool_output` (the "SQL:" part). For Cortex Search tools, build the search query instead.
3. Write `tool_input` as a natural-language paraphrase of what the agent would pass to the tool
4. Execute the SQL/search query via `snowflake_sql_execute` — if it errors or returns empty, **drop this question and move on**
5. For multi-tool questions: execute tools in sequence — the first tool's result informs the second tool's `tool_input`
6. Based on the question and all executed results, write `ground_truth_output` as the final answer string
7. When `<METRIC_SCOPE> = both`, **Save all queries, results, and `ground_truth_output`** — Step 3.4 reuses them directly

Print the draft (no STOP — proceed immediately to Step 4). When `<METRIC_SCOPE> = both`, print the **full combined dataset** (both tracks together):

> Print to user:
> ```
> Built <AC_COUNT + TEA_COUNT> questions for your evaluation dataset.
> Here's the evaluation dataset generated from scratch for quick review:
>
> | # | Question | Expected Output | Test Category | Expected Tool |
> |---|----------|---------------------|---------------|---------------|
> | 1 | [question] | [answer] | Core Use Case (Tool Execution Accuracy and Tool Selection Accuracy) | [tool] |
> | 2 | [question] | [answer] | Multi Tool (Tool Execution Accuracy and Tool Selection Accuracy) | [tool1 → tool2] |
> | 3 | [question] | [answer] | Core Use Case (Answer Correctness and Logical Consistency) | — |
> | 4 | [question] | [answer] | Instruction Compliance (Answer Correctness and Logical Consistency) | — |
> ```

> **No STOP.** Rows failing the [TEA quality checklist](../refs/tea_details.md#tea-quality-checklist) (e.g. SQL didn't execute cleanly, `tool_input` reads as SQL, missing Procedure label) are dropped silently from `<TEA_COUNT>`; print a one-line survivor count. If the user volunteers corrections later, REDO the affected row(s) here.

> **Step 3 completion check** — before Step 4, verify drafts match `<METRIC_SCOPE>`: `both` → both AC + TEA drafts above; `ac` → AC only; `tea` → TEA only. If a required draft is missing, run the missing pass before moving on.

## Step 4: Create Dataset Table

> Print to user: `"Saving the evaluation dataset to Snowflake — **this typically takes 5 minutes.**"`

> ⚠️ **USER-FACING OUTPUT RULE FOR ALL OF STEP 4:** After the print above, run ALL sub-steps (4.1, 4.2, 4.3, and the completion check) **completely silently**. Do NOT print progress updates, row counts, track names, INSERT descriptions, or any intermediate status. The next user-facing output is "Inserting rows..." followed by the sanity-check result. The section headers below (e.g. "AC-track INSERT", "TEA-track INSERT") are internal navigation labels — NEVER echo them to the user.

⚠️ **Do NOT create the table until you reach this step.** The required schema is below —
do not invent your own column names or types. INPUT_QUERY (VARCHAR) and GROUND_TRUTH (VARIANT)
are mandatory column names for SYSTEM$CREATE_EVALUATION_DATASET registration. The added `track` column is required by the two-track design — it lets every later step (eval result analysis, expand merges) distinguish rows in the same merged table.

**`<YYYYMMDD_HHMMSS>` MUST be the actual current UTC timestamp** at the moment you create the table — compute it as `TO_VARCHAR(CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP()), 'YYYYMMDD_HH24MISS')`. Do NOT use a placeholder or a made-up timestamp.

```sql
CREATE OR REPLACE TABLE <DATABASE>.<SCHEMA>.EVAL_DATASET_<AGENT_NAME>_<YYYYMMDD_HHMMSS> (
    question_id INT AUTOINCREMENT,
    INPUT_QUERY VARCHAR NOT NULL UNIQUE,
    GROUND_TRUTH VARIANT NOT NULL,
    category VARCHAR,
    track VARCHAR NOT NULL,                     -- 'ac' | 'tea' (matches the GROUND_TRUTH shape on this row)
    author VARCHAR DEFAULT CURRENT_USER(),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
    notes VARCHAR
);
```

> Print to user: `"Inserting rows..."`
> **CRITICAL: Do NOT mention "AC-track", "TEA-track", "AC rows", "TEA rows", or any track distinction in user-facing output for the entirety of Step 4. These are internal implementation details. The user should only see "Inserting rows..." at the start and the sanity-check result at the end. Do NOT print separate messages per track.**

### Step 4.1: Per-track INSERT dispatch

> Run silently — do NOT print anything to the user for Steps 4.1, 4.2, or 4.3. No progress messages, no track labels, no row counts per track, no "inserting X rows", no echoing of section headers. The only user-facing output for all of Step 4 is `"Inserting rows..."` (already printed above) and the sanity-check result at the end.

This dispatch table picks which of the two INSERT templates below (Step 4.2 AC, Step 4.3 TEA) runs based on `<METRIC_SCOPE>`. Under `<METRIC_SCOPE> = both`, **both** INSERTs run into the same `EVAL_DATASET_<AGENT_NAME>_<YYYYMMDD_HHMMSS>` table (order arbitrary; they write disjoint rows). Under `ac` or `tea`, only the matching INSERT runs.

| `<METRIC_SCOPE>` | AC-track INSERT (Step 4.2) | TEA-track INSERT (Step 4.3) |
|------------------|----------------------------|------------------------------|
| `both`           | Run — writes the `<AC_COUNT>` AC-track rows | Run — writes the `<TEA_COUNT>` TEA-track rows |
| `ac`             | Run — writes the `<AC_COUNT>` AC-track rows | Skip (`<TEA_COUNT> = 0`) |
| `tea`            | Skip (`<AC_COUNT> = 0`)                     | Run — writes the `<TEA_COUNT>` TEA-track rows |

Both INSERT templates follow the canonical [`refs/ground_truth_schema.md` § `GROUND_TRUTH` VARIANT shape](../refs/ground_truth_schema.md#ground_truth-variant-shape) — `VARIANT` wrapping, `column_mapping.expected_tools → GROUND_TRUTH` registration key, `INSERT … SELECT … FROM VALUES` pattern, and the `INPUT_QUERY UNIQUE`-is-informational caveat.

Under `both` scope, run **both** statements in sequence into the same `EVAL_DATASET_<AGENT_NAME>_<YYYYMMDD_HHMMSS>` table. The two INSERTs do not interact — they write disjoint rows and Snowflake's `UNIQUE` constraint on `INPUT_QUERY` will fire if the same `INPUT_QUERY` text appears in both tracks (rare; rename one if it does).

### Step 4.2: AC-track INSERT (run when `<METRIC_SCOPE>` ∈ {`both`, `ac`})

> Run silently — do NOT print anything to the user. Do NOT echo this section header or describe what you are inserting.

Run the AC-track INSERT template from [`refs/ac_details.md` § AC INSERT template (scratch)](../refs/ac_details.md#ac-insert-template-scratch) — and run the quick-verification `SELECT` immediately after, confirming `field_absent = TRUE` on every row.

> **If `<METRIC_SCOPE> = both`, this INSERT is now complete — DO NOT proceed to Step 5 yet. Run the next INSERT below.** If `<METRIC_SCOPE> = ac`, proceed to Step 5.

### Step 4.3: TEA-track INSERT (run when `<METRIC_SCOPE>` ∈ {`both`, `tea`})

> Run silently — do NOT print anything to the user. Do NOT echo this section header or describe what you are inserting.

Run the TEA-track INSERT template from [`refs/tea_details.md` § TEA INSERT template (scratch)](../refs/tea_details.md#tea-insert-template-scratch).

> **Step 4 completion check** — before proceeding to Step 5, verify the row count in `EVAL_DATASET_<AGENT_NAME>_<YYYYMMDD_HHMMSS>` matches the per-scope expectation: `both` → `<AC_COUNT> + <TEA_COUNT>` rows split `track = 'ac'` / `track = 'tea'`; `ac` → `<AC_COUNT>` rows all `track = 'ac'`; `tea` → `<TEA_COUNT>` rows all `track = 'tea'`. Under `both`, if only one track is present in the table, **go back and run the missing INSERT** before moving on.

## Step 5: Register Dataset (single merged source table)

> Print to user: `"Registering your evaluation dataset..."`

Register the table built in Step 4 with **one `SYSTEM$CREATE_EVALUATION_DATASET` call** — both tracks live in the same table (see parent [`SKILL.md`](../SKILL.md) Registration rule).

Propose to the user and **STOP** for confirm / rename:

- `<source_table>` — `<DATABASE>.<SCHEMA>.EVAL_DATASET_<AGENT_NAME>_<YYYYMMDD_HHMMSS>` (built in Step 4).
- `<dataset_name>` — default `<agent_name>_eval_<YYYYMMDD_HHMMSS>`.

Then run (`USE DATABASE` / `USE SCHEMA` first — required for session context):

```sql
USE DATABASE <DATABASE>;
USE SCHEMA <SCHEMA>;

CALL SYSTEM$CREATE_EVALUATION_DATASET(
    'Cortex Agent',
    '<source_table>',
    '<dataset_name>',
    OBJECT_CONSTRUCT('query_text', 'INPUT_QUERY', 'expected_tools', 'GROUND_TRUTH')
);
```

Record `<source_table>` and `<dataset_name>` for the parent skill's Workflow → Step 3.

**This sub-skill is complete — return control to the parent [`dataset/SKILL.md`](../SKILL.md).**

## Troubleshooting

See parent [`dataset/SKILL.md`](../SKILL.md).
