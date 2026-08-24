# AC-track details (reference)

Reference for the **Answer Correctness (AC) track** of dataset curation. Skills (`dataset-scratch`, `dataset-production`, `dataset-expand`) link here for authoring rules, the Good/Bad table, quality checklists, and the long SQL templates. Step procedure (STOPs, ASK prompts, decision tables) lives in the skill bodies.

## When to read this

| You're in… | …and you need… | …read |
|---|---|---|
| `scratch` Step 2 | AC category mix | [§ AC question category guidance](#ac-question-category-guidance) |
| `scratch` Step 3 / `production` Step 5 / any AC drafting | universal AC ground-truth rule, Good/Bad table, AC quality checklist | [§ AC-track authoring](#ac-track-authoring) |
| `production` Step 2 / Step 4 | Pull `record_root.input` / `record_root.output` from the agent trace to drive AC `ground_truth_output` | [§ Trace projection from agent invocations](#trace-projection-from-agent-invocations) |
| `scratch` Step 4 | the long AC INSERT example with sample rows | [§ AC INSERT template (scratch)](#ac-insert-template-scratch) |

Step-executable SQL (production annotation DDL, `UPDATE`, projection) lives **inline in the calling skill** — not duplicated here.

`GROUND_TRUTH` JSON shape, field-absent semantics, `track` column: [`ground_truth_schema.md`](./ground_truth_schema.md).

---

## AC track definition

An **AC-track row** scores under `answer_correctness` (AC) and `logical_consistency` (LC) only. Shape:

- `INPUT_QUERY` — the question text.
- `GROUND_TRUTH` (VARIANT) — object whose **only** top-level key is `ground_truth_output` (canonical answer string). `ground_truth_invocations` is **omitted entirely** — not `[]`, not `null`. See [`ground_truth_schema.md` § trichotomy](./ground_truth_schema.md#the-ground_truth_invocations-trichotomy).
- `track = 'ac'`.
- `category` from the AC-only distribution.

AC-track rows do not participate in TSA / TEA scoring — those metrics surface "Missing ground truth" and exclude them from aggregates by design.

---

## AC question category guidance

Recommended AC-only distribution:

| Category | % | Purpose | Example |
|----------|---|---------|---------|
| Core use cases | 35% | Primary purpose | *"What was Q3 revenue?"* |
| Tool routing | 20% | Correct tool choice | "Show ML platform usage" vs general usage |
| Edge cases | 15% | Boundaries / invalid dates | *"Show revenue for Feb 30."* |
| Ambiguous queries | 10% | Clarification handling | *"Show recent activity."* |
| Data validation | 10% | Quality / incomplete periods | *"Why is the Dec total NULL?"* |
| Instruction compliance | 10% | Policy from agent instructions / orchestration | *"never do X"* / *"only do X if Y"* — verify refusal or conditional behavior |

**Instruction and orchestration compliance (mandatory):** Read response instructions, orchestration instructions, and any analyst- or persona-specific rules. Where the spec says things like "do not do X under any circumstance" or "only do X if Y", add explicit test questions whose expected answers verify compliance (refusals, deferrals, tone, tool gating). As an example, some users might specify "Do not answer unless you are confident you know how. Ask a follow-up question instead." If any such rule exists, include at least one dedicated compliance test case for it in the dataset.

**For each tool, include:**
- 1-2 clear routing questions (obviously maps to this tool)
- 1 negative routing question (similar but should NOT use this tool)
- 1 ambiguous question (could use multiple tools)

**Multi-tool flows:** Also include questions that should legitimately use **two or more tools** (sequential or combined in one answer). For each, document the expected tool sequence or combination in the notes column and when reviewing ground truth.

---

## AC-track authoring

### Universal AC ground-truth rule

`ground_truth_output` is the string `answer_correctness` compares the agent's actual answer against on every eval run. **It must contain real, literal, verifiable values — never placeholders, paraphrases, or made-up numbers.**

**Forbidden in `ground_truth_output`** — strictly banned:

- **Placeholder numerics** — *"the total revenue"*, *"$X.X M"*, *"~Y rows"*, *"the consume of all transactions"*, *"a few hundred"*.
- **Placeholder dates / periods** — *"the date of last order"*, *"the most recent quarter"*, *"the relevant period"*.
- **Placeholder identifiers / entities** — *"the top customer"*, *"the leading product"*, *"customer X"*, *"product Y"*.
- **Templated descriptions** — *"Returns the monthly aggregate of …"*, *"Verify the answer matches …"*, *"Check whether …"*, *"The answer should include …"*. These describe what the answer should look like instead of **being** the answer.
- **Made-up numbers** that did not come from a real source (agent trace, real SQL execution, or real semantic-model lookup).

**Required in every `ground_truth_output`** — the actual numeric value(s) (`$2,547,830.42`, `7.2%`), date(s) (`2025-10-12`, `Q3 2025 (Jul 1 – Sep 30)`), identifier(s) / entity name(s) (`ACME Corp`, `SKU-4471`, `acct_92831`). For qualitative answers (yes/no, classification, recommendation): the literal verdict **and** the literal supporting fact, e.g. *"Yes — January 2026 revenue ($812,440) exceeded December 2025 revenue ($774,219)."*

### Expected-answer Good/Bad table

Applies to **every** `ground_truth_output` string.

| | Good | Bad |
|---|---|---|
| Numeric | `"Total revenue for Q3 2025 was $2,547,830.42 across 1,284 transactions."` | `"Revenue is $X.X M."` / `"~$2.5M"` |
| Identifiers | `"The top customer was ACME Corp (acct_92831) with $412,008.17 in revenue."` | `"The top customer was the leading account."` |
| Dates | `"Last order was placed on 2025-10-12."` | `"The date of last order is the most recent transaction date."` |
| Qualitative | `"Yes — January 2026 revenue ($812,440) exceeded December 2025 revenue ($774,219)."` | `"Yes, January was higher than December."` |
| Multi-row | `"Top 3 products by Q3 2025 revenue: SKU-4471 ($188,402), SKU-2210 ($142,990), SKU-9183 ($120,415)."` | `"Top 3 products by revenue this period."` |
| Negative case | `"No transactions matched — the customer has no orders in Q3 2025."` | `"No relevant data found."` |

**Hard constraints (apply to every string):**

1. **No placeholder tokens** — no `<value>`, `<date>`, `<id>`, `<customer>`, `<product>`, `<amount>`.
2. **No vague quantifiers** — no `"some"`, `"a few"`, `"many"`, `"the most"`, `"~N"`, `"approximately X"`.
3. **No descriptive paraphrases** — no `"Returns …"`, `"Verify the answer …"`, `"The answer should …"`.
4. **No fabricated data** — every literal value must trace back to either (a) the agent's `record_root.output`, or (b) a real SQL / semantic-model / corpus lookup against the user's actual data.

> Why hard-enforced: loose ground truth is the #1 cause of useless `answer_correctness` scores. `"Revenue information"` scores randomly; `"Total revenue for Q3 2025 was $2,547,830.42 across 1,284 transactions."` produces tight grades.

### AC quality checklist

Run **before approving the AC-track table** (scratch Step 4 / production Step 6). A row failing any checkbox must be re-authored.

- [ ] `ground_truth_output` is a real answer string — not a description, placeholder, or template.
- [ ] No banned placeholder phrases (`$X.X M`, `<value>`, `~N`, `the date of …`, `the top customer`, `the consume of …`, `Verify the answer …`, `Returns the …`).
- [ ] Every numeric value is a literal number with appropriate units / precision.
- [ ] Every date is a literal date or date range.
- [ ] Every named entity / identifier is the actual name or ID.
- [ ] Qualitative questions carry literal verdict AND literal supporting fact(s).
- [ ] The answer reads like something the agent could plausibly say at runtime.

---

## AC drafting by methodology

- **`<METHODOLOGY> = 1` (build manually).** Hand-author each row's `ground_truth_output` from real-data lookups: write the canonical SQL / search query / `CALL` against the agent's semantic model or corpus, execute it, and paste the literal result into `ground_truth_output` as a real answer string. The [Universal AC ground-truth rule](#universal-ac-ground-truth-rule), [Expected-answer Good/Bad table](#expected-answer-goodbad-table), and [AC quality checklist](#ac-quality-checklist) apply identically — only the source of the answer differs.
- **`<METHODOLOGY> = 2` (invoke the user's agent).** The agent has already been invoked in scratch's Step 3 shared agent-invocation batch with `<batch_start>` fixed beforehand (see [`subagents.md` Step 4](./subagents.md#step-4-projection--trace-window-invariants)). **Do NOT re-invoke.** Execute **only** the [Answer-text projection (`record_root`)](./tea_details.md#query-1--record_ids--answers) via `snowflake_sql_execute` — this is the single SQL query AC-track needs. Do NOT run multi-tool detection or per-family projections for AC rows. Substitute the AC-track `INPUT_QUERY` list for `user_question IN (…)`, then apply [§ Apply the trace to ground truth (AC-track)](#apply-the-trace-to-ground-truth-ac-track) to copy `AGENT_RESPONSE` into `ground_truth_output`. AC-track questions in `<MISS_LIST>` (no `record_root` span found in the `<batch_start>` window) are dropped from `<AC_COUNT>` per the [Step 3 miss-rate report](./subagents.md#step-3-verification--miss-rate-report) — do not re-invoke or hand-author a substitute via methodology #1.

---

## Trace projection from agent invocations

Used by `dataset-production` Step 2 (mining production questions) and Step 4 (building the annotation table) for the **AC-track shape**: AC rows only need `record_root.input` (the user question) and `record_root.output` (the agent's actual answer) — `ground_truth_invocations` is **absent** for AC rows, so no per-tool-family attributes are needed. For TEA-shaped rows, use [`tea_details.md` § Trace projection from agent invocations](./tea_details.md#trace-projection-from-agent-invocations) instead, which adds the per-tool-family and universal-planning projections required to author `expected_tools_json`.

### AC-track production projection (`record_root` only)

Projection shape over `record_root.input` / `record_root.output`. Drives `USER_QUESTION` + `AGENT_RESPONSE` columns of the AC annotation table, and the seed list of unique questions for Step 3 filtering. The **calling skill** is responsible for collecting the production time range from the user and substituting it into the WHERE clause — this projection only declares the shape, not the window:

> Use `TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS('<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'))` to read observability events scoped to the agent.

```sql
SELECT
  RECORD_ATTRIBUTES:"ai.observability.record_root.input"::STRING  AS USER_QUESTION,
  RECORD_ATTRIBUTES:"ai.observability.record_root.output"::STRING AS AGENT_RESPONSE,
  RECORD_ATTRIBUTES:"ai.observability.record_id"::STRING          AS REQUEST_ID,
  TIMESTAMP                                                      AS RECORD_TS
FROM TABLE(
  SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>',
    '<SCHEMA>',
    '<AGENT_NAME>',
    'CORTEX AGENT'
  )
)
WHERE RECORD_ATTRIBUTES:"ai.observability.span_type"::STRING = 'record_root'
  AND RECORD_ATTRIBUTES:"ai.observability.record_root.input" IS NOT NULL
  -- Calling skill (e.g. dataset-production Step 2) appends here the
  -- user-supplied production time-window predicate and an optional sample cap:
  --     AND TIMESTAMP >= '<start_timestamp_utc>'
  --     AND TIMESTAMP <  '<end_timestamp_utc>'
  --   plus a tail   LIMIT <optional_sample_cap>   when the user supplies a cap.
QUALIFY ROW_NUMBER() OVER (PARTITION BY USER_QUESTION ORDER BY TIMESTAMP DESC) = 1
ORDER BY RECORD_TS DESC;
```

Use the same projection — wrapped as the inner `SELECT` — when the calling skill creates the AC annotation table; the outer DDL adds `row_id`, `expected_answer`, `is_correct`. AC rows do **not** require `expected_tools_json` (that's a TEA-shape concern); the AC annotation columns are listed inline in `dataset-production` Step 4.

### Apply the trace to ground truth (AC-track)

Copy `AGENT_RESPONSE` into the annotation table's `actual_answer` column **as-is** — this is the agent's literal production output that the annotator will compare against during Step 5. **Do not** auto-populate `expected_answer` from `actual_answer`; the annotator must independently verify the answer per the [Universal AC ground-truth rule](#universal-ac-ground-truth-rule) and [Expected-answer Good/Bad table](#expected-answer-goodbad-table).

---

## AC INSERT template (scratch)

> **Run silently — do NOT print anything to the user.** No progress messages, no "inserting AC rows" / "inserting TEA rows" / track labels / row counts. The calling skill already printed "Inserting rows..." — execute the SQL and move on without any user-facing output.

`dataset-scratch` Step 4 when `<METRIC_SCOPE>` ∈ {`both`, `ac`} and `<AC_COUNT> > 0`. **`GROUND_TRUTH` carries only `ground_truth_output`** — the `ground_truth_invocations` key is NOT present in the object. Do **NOT** write `'[]'`. Field-omission is the wire-format contract.

```sql
INSERT INTO <DATABASE>.<SCHEMA>.EVAL_DATASET_<AGENT_NAME>_<YYYYMMDD_HHMMSS> (INPUT_QUERY, GROUND_TRUTH, category, track, notes)
SELECT column1,
       TO_VARIANT(OBJECT_CONSTRUCT(
           'ground_truth_output', column2
           -- ground_truth_invocations is intentionally OMITTED on these rows.
       )),
       column3,
       'ac',
       column4
FROM VALUES
('What was the total revenue per product category for Q3 2025?',
 'Q3 2025 revenue: Services $1.6B, Hardware $0.7B, Subscriptions $0.2B; total ~$2.5B.',
 'core_use_case',
 'answer text only'),

('Show me the monthly revenue trend for 2025.',
 '2025 monthly revenue (millions): Jan $180.4, Feb $195.1, Mar $202.8, Apr $187.3, May $211.6, Jun $223.0, Jul $231.4, Aug $228.9, Sep $241.7, Oct $237.5, Nov $258.2, Dec $266.0; total ~$2.66B.',
 'core_use_case',
 'answer text only'),

('What is your name?',
 'I am a sales analytics assistant.',
 'instruction_compliance',
 'guardrail / persona compliance');
```

**Quick verification — run after the AC INSERT:**

```sql
SELECT INPUT_QUERY,
       GROUND_TRUTH:ground_truth_invocations IS NULL                                                AS field_absent,  -- expect TRUE
       ARRAY_SIZE(COALESCE(GROUND_TRUTH:ground_truth_invocations::ARRAY, ARRAY_CONSTRUCT()))         AS arr_size       -- expect 0
FROM <DATABASE>.<SCHEMA>.EVAL_DATASET_<AGENT_NAME>_<YYYYMMDD_HHMMSS>
WHERE track = 'ac';
```

If `field_absent = FALSE` on any row, the INSERT was authored with `PARSE_JSON('[]')` by mistake — re-run with the correct shape.

---

## Production / expand step content

The AC-only annotation-table DDL, the `UPDATE … SET expected_answer, is_correct` template, and the AC inner-SELECT of the projection all live inline in `dataset-production` Steps 4 / 5 / 6. They are not duplicated here. When authoring `expected_answer` values for those templates, apply the [Universal AC ground-truth rule](#universal-ac-ground-truth-rule) and [Expected-answer Good/Bad table](#expected-answer-goodbad-table).
