---
name: agent-studio-agent-dataset-production
description: "Create an evaluation dataset from real production queries in observability logs. Use when: build dataset from production data, real queries, observability logs, actual agent usage."
parent_skill: agent-studio-agent-dataset
---

# Create Evaluation Dataset From Production Data

> Tool usage and dataset format: see parent `dataset/SKILL.md`.
> AC-track authoring style guide: [`refs/ac_details.md`](../refs/ac_details.md).
> TEA-track authoring style guide (schema, two-part `tool_output` format, SQL ground-truth rules, INSERT examples): [`refs/tea_details.md`](../refs/tea_details.md).
> `GROUND_TRUTH` JSON shape and the `ground_truth_invocations` trichotomy: [`refs/ground_truth_schema.md`](../refs/ground_truth_schema.md).

**Goal:** Build an evaluation dataset from real production queries.

**MANDATORY:** Follow these steps in order.

---

## Invocation modes

This skill runs in one of two modes. The caller specifies the mode up front.

**`standalone`** (default) — invoked directly by the user. Run all steps as written.

**`build-only`** — invoked by [`dataset-expand`](../dataset-expand/SKILL.md) to produce a staging table that the caller will merge into an existing source table.

In `build-only` mode the caller supplies:
- `agent_name`, `database`, `schema` — already identified
- `target_table` — fully qualified staging table name to create instead of the canonical `EVAL_DATASET_<AGENT_NAME>_<YYYYMMDD_HHMMSS>`

In `build-only` mode you MUST:
- **Skip Step 1** entirely (agent already identified by caller)
- **Run Step 1.1 (metric-scope selection)** — the caller does not supply `<METRIC_SCOPE>`, so ASK the user here before Step 2. Without it, every downstream dispatch table (Step 2 projections, Step 3 filtering, Step 4 annotation table shape, Step 6 source-table track column) is undefined.
- In Step 4, use `<target_table>_ANNOTATIONS` as the annotation table name (replaces `EVAL_ANNOTATIONS_<AGENT_NAME>`)
- In Step 6, use the caller-supplied `target_table` FQN for the eval table — do **not** create or overwrite `EVAL_DATASET_<AGENT_NAME>_<YYYYMMDD_HHMMSS>`
- **Skip Step 7** (registration) — caller will register the merged result with a new versioned name
- After Step 6 completes, return control to the caller — do **not** print "STOP" or "workflow complete"

If the caller does not specify a mode, default to `standalone`.

> **Do NOT print "build-only mode", "invoked by expand", or any internal mode information to the user.** Run transparently.

---

## Step 1: Identify Agent

Ask the user for the agent FQN (`DATABASE.SCHEMA.AGENT_NAME`).

Otherwise:

> Print to user: `"Which agent would you like to build an evaluation dataset for? Please provide the database, schema and agent name (e.g. MY_DB.MY_SCHEMA.MY_AGENT)."`

**STOP** and wait for the user to provide the agent name. Do NOT run `SHOW AGENTS IN ACCOUNT` — it scans every agent and is extremely slow. Only proceed once the user provides the name.

1. Once the agent FQN is known, read the agent configuration via `agent-read` (do **not** use `DESCRIBE AGENT` / `DESC AGENT`; do NOT print tool details, config contents, or tool-type mappings to the user — extract internally only):

```bash
cortex agent-studio agent-read --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME>
```

> Print to user: `"Fetched the configuration for agent <AGENT_NAME>."`

## Step 1.1: Choose Evaluation Metrics Scope (MANDATORY — ask immediately after Step 1, before Step 2's timestamp prompt)


ASK the user — this is its own STOP, distinct from Step 2's time-window STOP:

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
C) Can you provide me more details to recommended settings about metric scopes?
```

**STOP** for the user's answer.

If A → set `<METRIC_SCOPE> = both`, print `"Using recommended: covering all 4 snowflake metrics."` and continue.

If C → print the explanation, then re-ask the same A/B/C question:

```
The recommended settings follow Snowflake best practices — it creates a dataset covering all 4 Snowflake evaluation metrics: answer correctness, logical consistency, tool selection accuracy, and tool execution accuracy. This gives the most complete picture of agent quality.

For more details on these metrics, see: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-evaluations
```

If B → ASK the follow-up:

```
Which evaluation metric(s) should this dataset support?

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

| `<METRIC_SCOPE>` | Step 2 projections | Step 3 filtering | Steps 4–6 |
|---|---|---|---|
| `both`  | Run **BOTH** the AC projection **AND** the TEA projections (same window) — union the candidate questions across the two tracks. **Mandatory:** never pick one or the other under `both` — both projections must run, otherwise the matching track ends up with zero candidates downstream. | Filter the AC-track and TEA-track candidate sets **independently**, then UNION the survivors so both tracks reach Step 4 with rows. | Annotation table carries both AC columns + the optional `expected_tools_json` column; Step 6's merged source table contains BOTH `track='ac'` and `track='tea'` rows. |
| `tea`   | Run TEA projections only | Filter TEA candidates only | TEA-only INSERT path |
| `ac`    | Run AC projection only — skip TEA projections + multi-tool detection | Filter AC candidates only | AC-only INSERT path |

> **In `build-only` mode this step still runs** — the caller (`dataset-expand`) does not supply `<METRIC_SCOPE>`. ASK the user here.

## Step 2: Access Production Events

ASK the user:

```
How should I find production questions to include in your evaluation dataset?

A) Use recommended settings — scan the past 14 days of agent usage with default question counts
B) Customize — provide a specific time range and question counts
C) Tell me more about the recommended settings related to fetching production events
```

**STOP** for the user's answer.

If C → print the explanation, then re-ask the same A/B/C question:

```
With recommended settings on production events fetching, the following happens:
1. Look at all conversations your agent had in the past 14 days
2. Find the most representative questions real users asked
3. Create questions covering snowflake metrics based on what you chose in the previous step

This gives you a good sample of real-world usage without needing to specify exact dates.
```

If A → set `<START_TIMESTAMP_UTC>` = 14 days ago (UTC), `<AC_COUNT> = 20`, `<TEA_COUNT> = 20`. Print to user: `"Using recommended: scanning the past 14 days with default question counts."` and continue.

If B → ASK the follow-up (show only the fields relevant to `<METRIC_SCOPE>`):

```
Please provide:
- How far back to look: a start timestamp (e.g., 2026-05-01 00:00:00 UTC) or "last <N> days"
[If METRIC_SCOPE ∈ {both, ac}:]  - Desired question count for answer correctness and logical consistency
[If METRIC_SCOPE ∈ {both, tea}:]  - Desired question count for tool execution accuracy and tool selection accuracy
```

**STOP** for the user's answer. Record `<START_TIMESTAMP_UTC>` and the per-track caps.

If the user provides "last N days", compute `<START_TIMESTAMP_UTC>` as `TO_VARCHAR(DATEADD(day, -N, CURRENT_TIMESTAMP()::TIMESTAMP_NTZ), 'YYYY-MM-DD HH24:MI:SS')`. Never add an upper bound (see MANDATORY note below).

**Defaults**: `<AC_COUNT> = 20`, `<TEA_COUNT> = 20` — apply silently when the user does not override. Reuse `<METRIC_SCOPE>` captured in Step 1.1 — **do not re-ask**.

> No end timestamp / upper bound is collected. Past records don't change, so `TIMESTAMP >= '<start>'` plus the per-track `LIMIT` is sufficient for mining. The event-table `TIMESTAMP` column is stored in UTC; injecting `CURRENT_TIMESTAMP()` (or any other session-tz-resolved literal) as an upper bound silently filters out the most recent records when the session timezone isn't UTC.

Per-`<METRIC_SCOPE>` cap dispatch:

| `<METRIC_SCOPE>` | `<AC_COUNT>` | `<TEA_COUNT>` |
|---|---|---|
| `ac`   | `20` (default; user-overridable) | `0` — TEA projections are skipped |
| `tea`  | `0` — AC projection is skipped | `20` (default; user-overridable) |
| `both` | `20` (default; user-overridable) — applied to the AC projection | `20` (default; user-overridable) — applied to each TEA projection |

> ⚠️ **MANDATORY — TIMESTAMP filter injection.** TIMESTAMP windowing for the agent trace lives **only in this skill** — `refs/ac_details.md` and `refs/tea_details.md` carry their projections with a `<batch_start>` placeholder (or no TIMESTAMP predicate at all) and **must not be edited**. Every time you reference any SQL block from those refs (Multi-tool detection, Answer-text projection, SQL-family / Cortex-Search / Web-Search-Custom / generic projections, AC-track production projection), you MUST substitute the user-supplied start into the executable SQL: replace each `<batch_start>` placeholder with `'<START_TIMESTAMP_UTC>'` (and on JOIN-side queries the corresponding `e.TIMESTAMP >= '<START_TIMESTAMP_UTC>'`). For the AC ref's commented placeholder block, uncomment the `AND TIMESTAMP >= …` line with the substituted value. Multi-CTE blocks need the predicate injected into **both** the inner `approved` (and `plan`) CTE and the outer query. **Do NOT add any upper-bound predicate (`AND TIMESTAMP < …`) and NEVER substitute `CURRENT_TIMESTAMP()` for an upper bound** — the event-table `TIMESTAMP` is UTC and session-tz-resolved upper bounds silently drop the most recent records for non-UTC sessions. The lower-bound predicate plus the per-track `LIMIT` (`<AC_COUNT>` / `<TEA_COUNT>`) is the complete mining window.

Then project from the agent observability traces from the chosen start timestamp onward.

> Print to user: `"Scanning production logs — **this typically takes 2-5 minutes depending on traffic volume.**"`

The reference files (`ac_details.md`, `tea_details.md`) declare the **projection shape** (SELECT list, FROM clause, span_type / IS NOT NULL guards, QUALIFY) — they intentionally do **not** carry the time-window predicate. **It is this skill's job, not the ref files', to gather the user's start timestamp and inject it into the executable SQL.** Concretely: take each projection from the matching ref file, append the user-supplied start plus the per-track cap (`<AC_COUNT>` for the AC projection, `<TEA_COUNT>` for each TEA projection) to its WHERE / tail, and inline the substituted SQL in this turn so it is auditable and runnable. Every projection you actually run MUST contain the literal predicate `AND TIMESTAMP >= '<start>'` with the user's value substituted in, plus `LIMIT <AC_COUNT>` (AC projection) or `LIMIT <TEA_COUNT>` (each TEA projection) using the per-track defaults from Step 2 (20 AC / 20 TEA) when the user did not override. **Never add an upper bound** — see the MANDATORY note above.

Now dispatch on `<METRIC_SCOPE>` — captured in Step 1.1, **not re-asked here**:

- **`<METRIC_SCOPE> = ac`** — run ONLY the record_root projection (Query 1 from `refs/tea_details.md`). This returns `USER_QUESTION` + `AGENT_RESPONSE`. Do NOT run any tool-invocation projections (Query 2/3/4). AC candidates only need the agent's final answer.
- **`<METRIC_SCOPE> = tea`** — run Query 1 (record_ids + answers) THEN Query 2/3/4 (tool invocations) per the agent's tool-types. TEA candidates need both the final answer AND the tool execution details.
- **`<METRIC_SCOPE> = both` (Mixed)** — run Query 1 with `LIMIT <AC_COUNT> + <TEA_COUNT>` to get all candidates. Then run Query 2/3/4 ONLY on the TEA-track subset (the first `<TEA_COUNT>` candidates by tool-invocation richness). **Do NOT run tool-invocation projections on AC candidates** — AC rows only need `record_root.output` as their ground truth. The TEA projections (Query 2/3/4) filter by `record_id IN (<TEA_candidate_record_ids>)` only.

Use the Query 1/2/3/4 templates from [`refs/tea_details.md` § Trace projection from agent invocations](../refs/tea_details.md#trace-projection-from-agent-invocations). Substitute `<START_TIMESTAMP_UTC>` for `<batch_start>` and apply the per-track `LIMIT` caps. Do NOT include a full SQL example here — the ref file owns the projection shape.

**Key rules:**
- Query 1 (record_root) returns ALL candidates — apply `LIMIT <AC_COUNT> + <TEA_COUNT>` under `both`, or the single-track cap under `ac`/`tea`.
- Query 2/3/4 (tool invocations) run ONLY on TEA-track candidate `record_id`s — never on AC candidates.
- Add `AND TIMESTAMP >= '<START_TIMESTAMP_UTC>'` to every query. Never add an upper bound.

> Print to user:
> ```
> Found <N> candidate questions from your agent's production logs.
> ```

## Step 3: Filter and Select Questions

> Print to user: `"Filtering questions for the evaluation dataset..."`

**Criteria for good evaluation questions:**
- Representative of real usage
- Clear expected answer exists
- Tests specific capability
- Not duplicate of existing questions

### Per-`<METRIC_SCOPE>` filtering dispatch

The filter pass is **track-aware**. Reuse `<METRIC_SCOPE>` from Step 1.1 — do not re-ask:

| `<METRIC_SCOPE>` | What to filter | What to produce |
|---|---|---|
| `ac`   | The AC seed list from Step 2 (record_root rows) | `<AC_CANDIDATES>` — `(USER_QUESTION, AGENT_RESPONSE, REQUEST_ID)` rows that survive the criteria. |
| `tea`  | The TEA seed list from Step 2 (record_root joined with per-family tool spans) | `<TEA_CANDIDATES>` — same shape plus the per-tool-family attributes needed in Step 4. |
| `both` | **MANDATORY: filter BOTH the AC seed list AND the TEA seed list independently** — apply the criteria to each side separately, NEVER to one only. | `<AC_CANDIDATES>` AND `<TEA_CANDIDATES>` — both populated; UNION feeds Step 4 so the annotation table has rows for both `track='ac'` and `track='tea'`. If only one of the two ends up populated, go back: either the AC projection or the TEA projections were skipped in Step 2 (re-run that step under `<METRIC_SCOPE> = both`). |

> Under `both`, **never collapse the two candidate sets into a single filter pass keyed only on `USER_QUESTION`** — that throws away the per-tool-family attributes that the TEA candidate side carries. Filter independently and union at the end.

**Filter examples** (apply the same predicates to each candidate set as needed):

```sql
-- Find questions about specific topics
WHERE USER_QUESTION ILIKE '%revenue%'

-- Find questions with errors or issues
WHERE AGENT_RESPONSE IS NULL OR AGENT_RESPONSE = ''
```

## Step 4: Create Annotation Table

> Print to user: `"Organizing selected questions for review, **this typically takes 3 minutes**..."`

Create the annotation table from the selected questions. This table holds the agent's actual responses alongside columns the annotator will fill with verified ground truth in Step 5.

The inner subquery is the same trace projection used in Step 2, with the user-approved start timestamp (lower bound only — no upper bound) and any Step 3 filters applied:

- **AC-track rows** (`<METRIC_SCOPE> ∈ {ac, both}`) — wrap the [`refs/ac_details.md` § AC-track production projection](../refs/ac_details.md#ac-track-production-projection-record_root-only) as the inner `SELECT`; the outer DDL adds `row_id`, `expected_answer`, `is_correct`. AC rows omit `expected_tools_json`.
- **TEA-track rows** (`<METRIC_SCOPE> ∈ {tea, both}`) — wrap the per-tool-family projections from [`refs/tea_details.md` § Trace projection from agent invocations](../refs/tea_details.md#trace-projection-from-agent-invocations) as the inner `SELECT` (joined on `USER_QUESTION` / `REQUEST_ID`); the outer DDL additionally provisions `expected_tools_json VARCHAR` so Step 5 can write the `ground_truth_invocations` JSON string per the [TEA-track authoring rules](../refs/tea_details.md#tea-track-authoring) and [Two-part `tool_output` format](../refs/tea_details.md#two-part-tool_output-format). **Before stitching**, run [`refs/tea_details.md` § Multi-tool invocation detection](../refs/tea_details.md#multi-tool-invocation-detection-mandatory-before-drafting) over the same start timestamp to get `detected_invocations` + `tool_sequence` per question — `len(ground_truth_invocations)` written in Step 5 MUST equal `detected_invocations`, never collapse multi-family hits.
- **Mixed (`both`)** — **emit ONE annotation table that holds rows from BOTH `<AC_CANDIDATES>` AND `<TEA_CANDIDATES>`.** Schema carries both AC columns AND the optional `expected_tools_json` column. UNION the two candidate sets into the inner `SELECT` so the table has rows for both tracks (AC rows leave `expected_tools_json` NULL; TEA rows leave it pre-populated for the annotator to confirm in Step 5). Verify post-create that the table has rows for both tracks — if only one side is present, the AC or TEA projection was skipped upstream and Step 2 / Step 3 must be re-run.

Outer DDL skeleton (substitute `<DATABASE>` / `<SCHEMA>` / `<AGENT_NAME>`; in `build-only` mode the table name is `<target_table>_ANNOTATIONS` instead of `EVAL_ANNOTATIONS_<AGENT_NAME>`):

```sql
CREATE OR REPLACE TABLE <DATABASE>.<SCHEMA>.EVAL_ANNOTATIONS_<AGENT_NAME> AS
SELECT
    ROW_NUMBER() OVER (ORDER BY REQUEST_ID) AS row_id,
    REQUEST_ID,
    USER_QUESTION,
    AGENT_RESPONSE                AS actual_answer,
    NULL::VARCHAR                 AS expected_answer,
    NULL::BOOLEAN                 AS is_correct,
    -- Include the next column only when track scope = tea or both:
    NULL::VARCHAR                 AS expected_tools_json
FROM (
    -- Paste here the inner SELECT(s) from Step 2's trace projection(s),
    -- with the same start timestamp (lower bound only — no upper bound) and
    -- any Step 3 filters applied:
    --   • AC-track  → ac_details.md § AC-track production projection
    --   • TEA-track → tea_details.md § Trace projection from agent invocations
    --                 (the SQL/Search/Generic projections relevant to this agent)
    -- Drop the LIMIT line when the user did not supply a sample cap.
);
```

For TEA no-tool guardrail rows, the annotator must write `expected_tools_json = '[]'` (empty array), **not** `NULL`. Step 6's `CASE WHEN expected_tools_json IS NOT NULL THEN PARSE_JSON(expected_tools_json) END` keeps `NULL` field-absent (AC-track) and `'[]'` as an empty invocations array (TEA no-tool).

## Step 5: Annotate — Review and Write Ground Truth

⚠️ **Do NOT skip this step. Do NOT copy the agent's actual_answer into expected_answer.**

Apply the [Universal AC ground-truth rule](../refs/ac_details.md#universal-ac-ground-truth-rule) and [Expected-answer Good/Bad table](../refs/ac_details.md#expected-answer-goodbad-table) when writing `expected_answer` values — no placeholders, no `$X.X M`, no `the date of …`.

For TEA-shaped rows, additionally apply the [`ground_truth_invocations` schema](../refs/tea_details.md#ground_truth_invocations-schema) when writing `expected_tools_json`.

The agent's production responses may be wrong. For each question, **independently determine the correct answer** before comparing it to the agent's response:

1. Read the question and identify which tool(s) should answer it
2. Use the tool yourself (e.g., run the Cortex Analyst query, search the corpus) to get the factual answer
3. Compare your independent answer to the agent's actual response
4. Mark as correct only if both agree; otherwise write the correct ground truth

**Present all rows to the user for review. MUST use ONLY these columns — do NOT add track, category, tool_type, or any other columns:**

> Print to user:
> ```
> Annotated <AC_annotated_count> questions for answer correctness and logical consistency, and <TEA_annotated_count> questions for tool execution accuracy and tool selection accuracy. Expected outputs were generated by querying your production log and being verified.
>
> | # | Question | Agent's Output | Expected Output (verified) | Match? |
> |---|----------|----------------|------------------------|--------|
> | 1 | [question] | [actual_answer] | [answer from your own analysis] | ✅ / ❌ |
> | 2 | [question] | [actual_answer] | [answer from your own analysis] | ✅ / ❌ |
>
> Would you like to proceed?
> A) Confirmed — looks good, continue
> B) Make edits — specify which rows to change
> ```

**STOP** for the user's answer.

If B → Print to user: `"Which rows would you like to change? Please specify the row number(s) and what the correct answer should be."` **STOP** and wait for the user to specify. Apply the edits to existing annotation table, re-show the updated table, then re-ask A/B.

If A → proceed, and Print to user: `"Writing the verified ground truth to the annotation table now, **this typically takes 5 minutes**."`

After user approval, update the annotation table with the verified ground truth. The UPDATE writes `expected_answer` + `is_correct` (AC) and `expected_tools_json` (TEA) in one pass; pass `NULL` in `column4` for AC-only rows, and a JSON-string array (per the [`ground_truth_invocations` schema](../refs/tea_details.md#ground_truth_invocations-schema) and [Two-part `tool_output` format](../refs/tea_details.md#two-part-tool_output-format)) for TEA-shaped rows.

**CRITICAL: Use `$$...$$` dollar-quoting for `expected_tools_json` values** — same rule as the TEA INSERT template. Single-quoted strings with `\n` will have Snowflake convert them to real newlines, breaking `PARSE_JSON` in Step 6. Dollar-quoting preserves `\n` as a literal two-character JSON escape.

```sql
UPDATE <DATABASE>.<SCHEMA>.EVAL_ANNOTATIONS_<AGENT_NAME>
SET expected_answer     = vals.column2,
    is_correct          = vals.column3,
    expected_tools_json = vals.column4
FROM (
    SELECT column1, column2, column3, column4
    FROM VALUES
    -- (row_id, expected_answer, is_correct, expected_tools_json)
    -- AC-only row: column4 = NULL
    (1, 'Verified ground truth for question 1', TRUE,  NULL),
    -- TEA-shaped row: column4 = dollar-quoted JSON string
    (3, 'Verified ground truth for question 3', TRUE,
        $$[{"tool_name":"sales_analyst","tool_input":"…","tool_output":"SQL: \n… \n \nExpected Result: \n…"}]$$),
    -- TEA no-tool guardrail: column4 = '[]' (empty array, NOT NULL)
    (4, 'I am a sales analytics assistant.', TRUE, '[]')
) AS vals(column1, column2, column3, column4)
WHERE row_id = vals.column1;
```

For AC-only datasets you can drop the `expected_tools_json = vals.column4` SET clause and the fourth column entirely — the column will stay `NULL` and Step 6's `CASE WHEN expected_tools_json IS NOT NULL … END` keeps `ground_truth_invocations` **field-absent** (correct AC-track scoring). Do **not** use `COALESCE(expected_tools_json, '[]')` in Step 6 — that would turn AC rows into TEA no-tool rows.

### Step 5.1: TEA quality gate (TEA and both-scope — silent self-check)

> **Applies whenever the annotation table contains non-null `expected_tools_json` rows, regardless of `<METRIC_SCOPE>`.** Run this gate when `<METRIC_SCOPE>` ∈ {`tea`, `both`} — under `both`, the mixed-scope annotation table contains TEA-shaped rows (`expected_tools_json IS NOT NULL`) that need the same validation as the `tea`-only path. Skip only when `<METRIC_SCOPE> = ac` (no TEA-shaped rows exist).

After the UPDATE writes `expected_tools_json` for the TEA-shaped rows, **silently** check each non-null `expected_tools_json` against the [TEA quality checklist](../refs/tea_details.md#tea-quality-checklist) (per-row `tool_output` two-part format with the right Procedure + Result labels for the `tool_type`, runnable SQL bodies, no placeholders, no `Verify the …` paraphrases, etc.). Fix failing rows in place by re-issuing the targeted UPDATE on `EVAL_ANNOTATIONS_<AGENT_NAME>` for that `row_id` only. Rows that **still** fail the checklist after one fix-up pass have their `expected_tools_json` set back to `NULL` (silently demoted to AC-only) so Step 6's `expected_answer IS NOT NULL` filter still includes the row but the malformed invocations are not propagated.

> **No STOP.** This gate is the production-side parallel of `dataset-scratch` Step 3.5 (the TEA-track draft pass's silent self-check) — it ensures every TEA row that survives into `EVAL_DATASET_<AGENT_NAME>_<YYYYMMDD_HHMMSS>` already passed the checklist, so downstream callers (e.g. `dataset-expand`) do not need to re-validate. Print a one-line announcement of how many TEA-track rows survived the checklist:
> ```
> Production TEA quality gate (silent self-check):
>   Annotated TEA-track rows:  <annotated_tea>
>   Passed checklist:          <passed_tea>
>   Demoted to AC-only:        <demoted_tea>
> ```

## Step 6: Convert to Evaluation Format

> Print to user: `"Converting to evaluation format..."`

Only rows with non-null `expected_answer` are included — any unannotated rows are excluded. The `track` column is derived from whether `expected_tools_json` is populated on the row (`'tea'` if non-null, `'ac'` otherwise) so the merged source table preserves per-row track identity for downstream eval analysis.

**`<YYYYMMDD_HHMMSS>` MUST be the actual current UTC timestamp** at the moment you create the table — compute it as `TO_VARCHAR(CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP()), 'YYYYMMDD_HH24MISS')`. Do NOT use a placeholder or a made-up timestamp.

```sql
CREATE OR REPLACE TABLE <DATABASE>.<SCHEMA>.EVAL_DATASET_<AGENT_NAME>_<YYYYMMDD_HHMMSS> AS
SELECT
    ROW_NUMBER() OVER (ORDER BY REQUEST_ID) AS question_id,
    USER_QUESTION AS INPUT_QUERY,
    TO_VARIANT(OBJECT_CONSTRUCT(
        'ground_truth_output',      expected_answer,
        -- ground_truth_invocations is included only when expected_tools_json is populated;
        -- for AC-only rows it stays field-absent in GROUND_TRUTH (correct AC-track scoring).
        'ground_truth_invocations', CASE WHEN expected_tools_json IS NOT NULL
                                         THEN PARSE_JSON(expected_tools_json) END
    )) AS GROUND_TRUTH,
    CASE WHEN is_correct THEN 'passing' ELSE 'failing' END AS category,
    CASE WHEN expected_tools_json IS NOT NULL THEN 'tea' ELSE 'ac' END AS track,
    'production_data' AS source
FROM <DATABASE>.<SCHEMA>.EVAL_ANNOTATIONS_<AGENT_NAME>
WHERE expected_answer IS NOT NULL;
```

> The `OBJECT_CONSTRUCT` call drops keys whose value is `NULL`, so AC-only rows materialize with `ground_truth_invocations` **field-absent** — exactly what the AC-track scoring requires per the [`refs/ground_truth_schema.md` § trichotomy](../refs/ground_truth_schema.md#the-ground_truth_invocations-trichotomy).

## Step 7: Register Dataset (single merged source table)

> Print to user: `"Registering your evaluation dataset..."`

Register the table built in Step 6 with **one `SYSTEM$CREATE_EVALUATION_DATASET` call** — both tracks live in the same table (see parent [`SKILL.md`](../SKILL.md) Registration rule).

Propose to the user and **STOP** for confirm / rename:

- `<source_table>` — `<DATABASE>.<SCHEMA>.EVAL_DATASET_<AGENT_NAME>_<YYYYMMDD_HHMMSS>` (built in Step 6).
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

Record `<source_table>`, `<dataset_name>`, and `<METRIC_SCOPE>` for the parent skill's Workflow → Step 3.

**This sub-skill is complete — return control to the parent [`dataset/SKILL.md`](../SKILL.md).**

## Troubleshooting

See parent [`dataset/SKILL.md`](../SKILL.md) for common errors and solutions.
