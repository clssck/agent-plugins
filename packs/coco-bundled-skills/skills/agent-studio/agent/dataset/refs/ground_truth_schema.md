# Ground-truth schema (reference)

This is a reference file for the **`GROUND_TRUTH` JSON shape**, the **`ground_truth_invocations` trichotomy** (populated vs `[]` vs absent), and the **`track` column convention** used in all dataset tables. It is **not** a skill — every dataset-curation skill (`scratch`, `production`, `expand`) and the evaluator (`evaluate-cortex-agent`) link here when they touch the ground-truth structure.

The goal of this file is **one canonical statement of the schema rules**, so the same rule is not duplicated across 5+ skill files.

## When to read this

| You're in… | …and you reach… | …read this section |
|---|---|---|
| Any dataset-curation skill | "the `GROUND_TRUTH` column" | [`GROUND_TRUTH` VARIANT shape](#ground_truth-variant-shape) |
| `dataset-scratch` Step 4 / `production` Step 6 / `expand` Step 4 | "should this row include `ground_truth_invocations`?" | [The `ground_truth_invocations` trichotomy](#the-ground_truth_invocations-trichotomy) |
| Any dataset-curation skill | "what is the `track` column?" | [The `track` column convention](#the-track-column-convention) |
| `evaluate-cortex-agent` Step 2 | "how does field-absent affect which metrics score this row?" | [Field-absent semantics for evaluation](#field-absent-semantics-for-evaluation) |

For AC-specific INSERT/UPDATE/projection templates, see [`ac_details.md`](./ac_details.md).
For TEA-specific INSERT/UPDATE/projection templates and the `ground_truth_invocations` JSON internals, see [`tea_details.md`](./tea_details.md).

---

## `GROUND_TRUTH` VARIANT shape

`GROUND_TRUTH` is a Snowflake `VARIANT` column on every dataset table. The VARIANT carries a JSON object with **up to two** top-level keys:

| Key | Required? | Type | Meaning |
|---|---|---|---|
| `ground_truth_output` | **Always present** on every row, both tracks. | String | The canonical answer the agent should produce for `INPUT_QUERY`. Graded by `answer_correctness` (AC) and `logical_consistency` (LC). |
| `ground_truth_invocations` | **Conditionally present** — see [The `ground_truth_invocations` trichotomy](#the-ground_truth_invocations-trichotomy). | JSON array of `{tool_name, tool_input, tool_output}` objects | The expected tool calls the agent should make, in order. Graded by `tool_selection_accuracy` (TSA) and `tool_execution_accuracy` (TEA). |

### Source-table column types

Snowflake Agent Evaluations require the source table to expose at least these two columns:

| Column | Type | Description |
|--------|------|-------------|
| `INPUT_QUERY` | `VARCHAR` | The question to ask the agent. |
| `GROUND_TRUTH` | `VARIANT` | The JSON object documented above. |

> **Important — use `VARIANT`, not `OBJECT`.** Build values with a function that returns a true `VARIANT` — `TO_VARIANT(OBJECT_CONSTRUCT(...))` is the recommended pattern (equivalent: `OBJECT_CONSTRUCT(...)::VARIANT` or `PARSE_JSON(...)`). Bare `OBJECT_CONSTRUCT(...)` returns a non-`VARIANT` value and can cause ground truth to be serialized as a string at evaluation time.

### `ground_truth_invocations` element-level rules

Each element of the `ground_truth_invocations` array is an object with these fields:

- **`tool_name`** — exact registered name from observability traces. Case-insensitive at eval time. For Cortex Analyst you may also use the semantic-model path (e.g. `@DB.SCHEMA.STAGE/model.yaml`). For web search the name is always the literal `"web_search"` (not configurable).
- **`tool_type`** — **do not include** in the row. The evaluator reads it from the trace at runtime.
- **`tool_input`** / **`tool_output`** — **required, non-empty** free-form strings on every invocation element. Empty strings silently disable TEA scoring for that element. Full per-`tool_type` authoring rules (two-part `tool_output` format, SQL ground-truth requirements, worked examples) → [`tea_details.md`](./tea_details.md).

### AC-track row shape (`ground_truth_invocations` omitted)

```json
{
  "ground_truth_output": "Total revenue for Q3 2025 was $2,547,830.42 across 1,284 transactions."
}
```

The `ground_truth_invocations` key is **not present at all** in the JSON object — not as `null`, not as `[]`. The VARIANT object has exactly one key.

### TEA-track row shape (`ground_truth_invocations` populated)

```json
{
  "ground_truth_output": "Total revenue for Q3 2025 was $2,547,830.42 across 1,284 transactions.",
  "ground_truth_invocations": [
    {
      "tool_name": "sales_analyst",
      "tool_input": "total revenue per product category for Q3 2025",
      "tool_output": "SQL:\nSELECT product_category, SUM(net_amount) AS total_revenue FROM SALES_DB.PUBLIC.SALES_TRANSACTIONS WHERE order_date BETWEEN '2025-07-01' AND '2025-09-30' GROUP BY product_category\n\nExpected Result:\nServices $1.6B, Hardware $0.7B, Subscriptions $0.2B"
    }
  ]
}
```

### TEA-track no-tool guardrail row shape (`ground_truth_invocations` = `[]`)

```json
{
  "ground_truth_output": "I am a sales analytics assistant.",
  "ground_truth_invocations": []
}
```

The `ground_truth_invocations` key **is present**, but the array is empty. This is **only** for guardrail / persona / refusal rows where the agent must invoke **no** tool.

For the full `tool_output` two-part format (Procedure label + Result label), see [`tea_details.md` § Two-part `tool_output` format](./tea_details.md#two-part-tool_output-format).

---

## The `ground_truth_invocations` trichotomy

A row's `ground_truth_invocations` field can be in **exactly one** of three states. The state is load-bearing — it determines which evaluation metrics will score the row.

| State | Wire-format shape | Track | Meaning | Used for |
|---|---|---|---|---|
| **Populated** | `[{tool_name, tool_input, tool_output}, …]` | TEA | The agent **should** invoke these exact tools, in this order, with these arguments. | Normal TEA-track rows. TSA matches `tool_name` sequence; TEA matches `tool_input` / `tool_output` per element. |
| **`[]` (empty array)** | `[]` | TEA | The agent must invoke **NO** tools. TSA scores 1.0 if zero invocations, 0.0 if any. | TEA-track no-tool guardrail rows — persona / refusal / instruction-compliance questions where calling any tool is wrong. |
| **Absent (field omitted)** | (key not present in the object) | AC | TSA / TEA do **not** score this row. AC and LC still score it. | AC-track rows — questions where tool-routing is not under test, only answer correctness. |

### Critical: `[]` is NOT a substitute for "I don't care about tool routing"

This is the single most common authoring mistake.

- **Use `[]` only** when "the agent must call no tool" is the correct answer (guardrails, persona responses, refusals).
- **Use field-absent** when tool-routing simply isn't being graded on this row (AC-track design choice).

If you write `[]` on an AC-track row by mistake, **every** agent run that legitimately invokes a tool to answer the question will fail TSA. The aggregate TSA score will collapse meaningfully. The fix: re-author the row with the `ground_truth_invocations` key **omitted** from `OBJECT_CONSTRUCT` (see [`ac_details.md` § AC INSERT template](./ac_details.md#ac-insert-template-scratch) and its inline quick-verification `SELECT`).

---

## The `track` column convention

Every dataset table created by the dataset-curation skills has a `track VARCHAR NOT NULL` column. Valid values are exactly `'ac'` and `'tea'` (lowercase, no other values). The column is **load-bearing** — every later step (eval, expand merges, parent-skill orchestration) relies on it to distinguish track-by-track behaviour without re-inspecting the `GROUND_TRUTH` VARIANT.

| `track` value | `ground_truth_invocations` rule | Metrics scored at eval | Sub-skill that authored it |
|---|---|---|---|
| `'ac'` | Field **must be absent** (omitted from `GROUND_TRUTH`). | AC + LC | scratch AC-track INSERT / production AC-track UPDATE. |
| `'tea'` | Field **must be present**, either **populated** or `[]`. | AC + LC + TSA + TEA | scratch TEA-track INSERT / production TEA-track UPDATE. |

### The `track` column and `ground_truth_invocations` shape are redundant by design

The track is recoverable from `GROUND_TRUTH:ground_truth_invocations IS NULL` (AC-track) vs `IS NOT NULL` (TEA-track), but the `track` column makes it explicit and indexable. **All scratch / production / expand SQL uses `WHERE track = '…'` rather than parsing the VARIANT** — it's cheaper, more readable, and resilient to legacy rows that may have inconsistent VARIANT shapes.

### Legacy tables (no `track` column)

Tables created before the two-track design lack a `track` column. The expand skill detects this and back-fills:

```sql
ALTER TABLE <DATABASE>.<SCHEMA>.<SOURCE_TABLE> ADD COLUMN IF NOT EXISTS track VARCHAR;
UPDATE <DATABASE>.<SCHEMA>.<SOURCE_TABLE>
SET track = CASE WHEN GROUND_TRUTH:ground_truth_invocations IS NULL THEN 'ac' ELSE 'tea' END
WHERE track IS NULL;
```

The back-fill is one-shot: legacy AC-track rows have field-absent `ground_truth_invocations` so they backfill to `'ac'`; legacy TEA-track rows have it populated (or `[]` for guardrails) so they backfill to `'tea'`. The legacy table is then conformant for all downstream skills.

---

## Field-absent semantics for evaluation

When `evaluate-cortex-agent` runs against the dataset:

| Row state | AC | LC | TSA | TEA |
|---|---|---|---|---|
| `track = 'ac'`, `ground_truth_invocations` field absent | Scored | Scored | **Not scored** ("Missing ground truth") | **Not scored** ("Missing ground truth") |
| `track = 'tea'`, `ground_truth_invocations` populated | Scored | Scored | Scored | Scored |
| `track = 'tea'`, `ground_truth_invocations = []` (no-tool guardrail) | Scored | Scored | Scored (1.0 if agent called no tool, 0.0 if any) | Scored (vacuous — no invocations to compare) |

### Per-row "Missing ground truth" is excluded from the aggregate mean

When TSA / TEA report "Missing ground truth" on a row, that row is **excluded** from the metric's numerator and denominator in the aggregate mean — it does **not** count as a 0. This is the explicit design rationale for using field-absent on AC-track rows instead of `[]`:

- **Field-absent → row excluded from TSA / TEA aggregate.** The agent's TSA / TEA scores reflect only the rows where tool-routing was actually under test.
- **`[]` → row included in TSA aggregate, requiring zero invocations.** If the row was AC-track (tool-routing not under test) but mistakenly carried `[]`, every legitimate agent invocation drops the aggregate TSA score. Wrong signal.

See `evaluate-cortex-agent` Step 5.2 for the mean-score computation that implements this exclusion.

---

## Sanity-check SQL patterns

Used by any skill that needs to verify an existing dataset table is well-formed **before** modifying or appending to it.

### 1. Confirm `GROUND_TRUTH` is a `VARIANT` with the expected keys

```sql
SELECT
    COUNT(*)                                                                                                AS total_rows,
    COUNT_IF(GROUND_TRUTH:ground_truth_output IS NOT NULL)                                                  AS rows_with_answer,           -- expect total_rows on every row
    COUNT_IF(GROUND_TRUTH:ground_truth_invocations IS NOT NULL)                                             AS rows_with_invocations_key,  -- expect TEA-track count
    COUNT_IF(GROUND_TRUTH:ground_truth_invocations IS NULL)                                                 AS rows_field_absent,          -- expect AC-track count
    COUNT_IF(ARRAY_SIZE(GROUND_TRUTH:ground_truth_invocations::ARRAY) = 0)                                  AS rows_empty_invocations      -- expect TEA-track guardrail count
FROM <DATABASE>.<SCHEMA>.<SOURCE_TABLE>;
```

If `rows_with_answer < total_rows`, some rows have no `ground_truth_output` — they will fail AC at eval time. Fix before iterating.

### 2. Confirm `track` column is populated and consistent with the VARIANT shape

```sql
-- Detect track/shape inconsistencies. Every track='ac' row must have field-absent
-- invocations, and every track='tea' row must have the field present (populated or []).
SELECT INPUT_QUERY,
       track,
       GROUND_TRUTH:ground_truth_invocations IS NULL AS field_absent,
       CASE
           WHEN track = 'ac'  AND GROUND_TRUTH:ground_truth_invocations IS NOT NULL THEN 'ac row has invocations key (should be omitted)'
           WHEN track = 'tea' AND GROUND_TRUTH:ground_truth_invocations IS NULL     THEN 'tea row has no invocations key (should be populated or [])'
           WHEN track IS NULL                                                       THEN 'track column not set (legacy row — run back-fill)'
           WHEN track NOT IN ('ac', 'tea')                                          THEN 'invalid track value (must be ac or tea)'
           ELSE NULL
       END AS inconsistency
FROM <DATABASE>.<SCHEMA>.<SOURCE_TABLE>
WHERE
    track IS NULL
    OR track NOT IN ('ac', 'tea')
    OR (track = 'ac'  AND GROUND_TRUTH:ground_truth_invocations IS NOT NULL)
    OR (track = 'tea' AND GROUND_TRUTH:ground_truth_invocations IS NULL);
```

If this query returns rows, fix the inconsistencies before iterating. The `track` column is the canonical truth — when in doubt, align the VARIANT to match `track` rather than the other way around (the eval framework reads `track` indirectly via the per-row `GROUND_TRUTH` shape, so they must agree).

### 3. Confirm legacy tables have been back-filled (no NULL `track`)

```sql
SELECT COUNT(*) AS legacy_rows_missing_track
FROM <DATABASE>.<SCHEMA>.<SOURCE_TABLE>
WHERE track IS NULL;
```

If this returns `> 0`, run the legacy back-fill SQL from [The `track` column convention](#the-track-column-convention) above before proceeding.
