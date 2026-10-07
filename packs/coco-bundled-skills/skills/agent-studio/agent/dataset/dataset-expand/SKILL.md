---
name: agent-studio-agent-dataset-expand
description: "Add questions to an existing evaluation source table or dataset. Use when: expand coverage, add rows, refresh registration, grow eval dataset, fill gaps."
parent_skill: agent-studio-agent-dataset
---

# Expand an existing evaluation dataset

> Tool usage and dataset format: see parent `dataset/SKILL.md`. This skill delegates question authoring to `dataset-scratch` / `dataset-production` in `build-only` mode; those sub-skills load [`refs/ac_details.md`](../refs/ac_details.md) / [`refs/tea_details.md`](../refs/tea_details.md) / [`refs/ground_truth_schema.md`](../refs/ground_truth_schema.md) themselves when they need them.

**Goal:** Add questions to expand coverage of an existing evaluation dataset.

This skill is an orchestrator. After identifying the existing source table, it delegates question generation to one of the sibling sub-skills:

- [`dataset-scratch`](../dataset-scratch/SKILL.md) — design new questions manually
- [`dataset-production`](../dataset-production/SKILL.md) — mine real queries from observability logs

Both sub-skills are invoked in **`build-only`** mode (see their Invocation modes section): they create a staging table only, skip agent identification, and skip registration. This skill performs the merge into the existing source table and the re-registration.

**MANDATORY:** Follow these steps in order. **As soon as the agent and dataset are identified in Step 1, show the existing-row coverage in Step 2 and ASK the user whether to add new questions manually (A) or mine from production (B). The chosen sub-skill captures `<METRIC_SCOPE>` and defaults `<AC_COUNT>` / `<TEA_COUNT>` itself — this skill does not re-ask them.**

---

## Step 1: Identify agent and dataset

> Print to user: `"Finding your agent and existing evaluation dataset..."`

Ask for both fully-qualified names — no inference, no fuzzy matching:

```
I need the database, schema, agent name, and dataset name to proceed:

1. Agent FQN — e.g. MY_DB.MY_SCHEMA.MY_AGENT
2. Dataset FQN — e.g. MY_DB.MY_SCHEMA.MY_EVAL_DATASET
```

**STOP** and wait for the required values. Do NOT run any SQL or commands. Only proceed once the user provides these names.

### Verify both exist and resolve the source table

Confirm the agent exists (do **not** use `DESCRIBE AGENT` — see parent `dataset/SKILL.md`). Run via `snowflake_sql_execute`:

```sql
SHOW AGENTS LIKE '<AGENT_NAME>' IN SCHEMA <AGENT_DATABASE>.<AGENT_SCHEMA>;
```

Then resolve the dataset's source table from version metadata via `snowflake_sql_execute`:

```sql
SHOW VERSIONS IN DATASET <DATASET_FQN>;
SELECT PARSE_JSON("metadata"):source_table::STRING AS source_table,
       PARSE_JSON("metadata"):row_count::INT AS row_count
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
```

`source_table` from the version metadata is the writable table backing the dataset. Capture this as `<SOURCE_TABLE>` and verify it exists:

```sql
DESCRIBE TABLE <SOURCE_TABLE>;
```
(via `snowflake_sql_execute`)

### If `source_table` is NULL or the table is missing

The dataset wasn't created by `SYSTEM$CREATE_EVALUATION_DATASET`, or the source table was dropped.

- If the table was recently dropped, try `UNDROP TABLE <SOURCE_TABLE>` (within the time-travel window).
- If `source_table` is NULL or `UNDROP` fails, ground truth cannot be recovered from the dataset's parquet snapshot (only `QUERY_TEXT` is materialized). Tell the user:

   > The dataset `<DATASET_FQN>` has no recoverable source table. Ground truth cannot be reconstructed from the dataset alone. You can extract the original questions via `LIST 'snow://dataset/<DATASET_FQN>/versions/<VERSION>'` and re-author ground truths manually using the `dataset-scratch` skill.

   **STOP** and wait for the user.

---

## Step 2: Show coverage and choose expansion mode

> Print to user: `"Reviewing current dataset coverage..."`

Run the following queries internally as backend data (do NOT print SQL, result tables, or category breakdowns to the user):

```sql
SELECT category, COUNT(*) AS count
FROM <DATABASE>.<SCHEMA>.<SOURCE_TABLE>
GROUP BY category
ORDER BY count DESC;

SELECT question_id, INPUT_QUERY, category
FROM <DATABASE>.<SCHEMA>.<SOURCE_TABLE>
ORDER BY question_id;

SELECT
    COALESCE(track,
             CASE WHEN GROUND_TRUTH:ground_truth_invocations IS NULL THEN 'ac' ELSE 'tea' END
    )                                                                          AS effective_track,
    COUNT(*)                                                                   AS row_count,
    COUNT_IF(GROUND_TRUTH:ground_truth_invocations IS NOT NULL)                AS has_invocations_key,
    COUNT_IF(ARRAY_SIZE(GROUND_TRUTH:ground_truth_invocations::ARRAY) > 0)     AS has_nonempty_invocations,
    COUNT_IF(GROUND_TRUTH:ground_truth_output IS NOT NULL)                     AS has_answer
FROM <DATABASE>.<SCHEMA>.<SOURCE_TABLE>
GROUP BY effective_track
ORDER BY effective_track;
```

Print ONLY this to the user — do NOT print SQL, result tables, category breakdowns, or question lists:

> Print to user:
> ```
> Your current dataset has <total_rows> questions:
>   - <ac_count> for answer correctness and logical consistency
>   - <tea_count> for tool execution accuracy and tool selection accuracy
> ```


> **Legacy-table fallback.** If this query fails to compile with `column 'TRACK' not found` (or equivalent `invalid identifier 'TRACK'`), treat that as confirmation that `<SOURCE_TABLE>` is a pre-two-track legacy table — do **not** retry. Skip the inventory output and continue to Step 4's legacy migration path, which back-fills the `track` column before any expansion runs.

> **Source-table shape note.**
>
> - If the existing source has 0 TEA-track rows (`has_invocations_key = 0` everywhere), the legacy table is entirely AC-shaped. Adding new TEA-track rows is fine — only those new rows will score under TSA / TEA after Step 5 re-registration. If the user expects every row to score TEA, they can raise the TEA-track count (the chosen sub-skill will ASK).
> - If the existing rows have no `track` column at all (pre-two-track schema), the Step 4 MERGE will `ALTER TABLE ... ADD COLUMN track` and back-fill from `ground_truth_invocations IS NULL ? 'ac' : 'tea'` automatically.

Then ask:

```
How would you like to expand the dataset?

A) Design new questions (Recommended) — propose test questions based on your agent's tools and coverage gaps
B) Mine from production — use real questions from your agent's usage history
C) What do these options mean?
```

**STOP** and wait for the user's answer.

If C → print the explanation, then re-ask the same A/B/C question:

```
Here's what each option means:

• Design new questions — analyzes your agent's tools and the gaps in your current test coverage, then writes new test questions and expected answers from scratch. Good when you want targeted coverage of specific tools or scenarios.
• Mine from production — looks at real questions that users have actually asked your agent in production, and uses those (with verified answers) as test cases. Good when you want your tests to reflect real-world usage patterns.
```

If A → continue to Step 3 with choice = A (scratch sub-skill).
If B → continue to Step 3 with choice = B (production sub-skill).

---

## Step 3: Build a staging table via the chosen sub-skill

> Print to user: `"Generating new test questions..."`

Generate a staging table FQN with a timestamp suffix:

```
<staging_table> = <DATABASE>.<SCHEMA>.<SOURCE_TABLE>_STAGING_<YYYYMMDD_HHMMSS>
```

**`<YYYYMMDD_HHMMSS>` MUST be the actual current UTC timestamp** — compute as `TO_VARCHAR(CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP()), 'YYYYMMDD_HH24MISS')`. Do NOT use a placeholder.

Invoke the chosen sub-skill in **`build-only`** mode. Do NOT print "build-only mode", "invoking sub-skill", or any internal mode/routing information to the user. The sub-skill runs transparently — the user only sees its `Print to user:` messages.

| Variable | Value |
|----------|-------|
| `mode` | `build-only` |
| `agent_name` | `<AGENT_NAME>` |
| `database` | `<DATABASE>` |
| `schema` | `<SCHEMA>` |
| `target_table` | `<staging_table>` |

- For choice **A**, follow [`dataset-scratch`](../dataset-scratch/SKILL.md) Steps 1.1 → 4 (skip Step 1 and Step 5 per its Invocation modes section). The created table is `<staging_table>`.
- For choice **B**, follow [`dataset-production`](../dataset-production/SKILL.md) Steps 1.1 → 6 (skip Step 1 and Step 7 per its Invocation modes section). The annotation table is `<staging_table>_ANNOTATIONS`; the final eval table is `<staging_table>`.

When the sub-skill returns control, capture `<METRIC_SCOPE>` (and the resolved counts) from its state — Step 4 below uses it to gate the MERGE projection. `<staging_table>` exists and contains the canonical columns: `INPUT_QUERY`, `GROUND_TRUTH`, `category`, `track` (`'ac'` | `'tea'`), plus optional `notes` (production sets `source = 'production_data'` instead of `notes` — adapt the projection in Step 4 accordingly). For AC-track staging rows, `GROUND_TRUTH:ground_truth_invocations` is **field-absent**; for TEA-track staging rows it carries the authored invocations (or `[]` for genuine no-tool guardrails).

> **TEA quality is the sub-skill's responsibility, not this skill's.** Both `dataset-scratch` (Step 3.5 silent self-check, in the TEA-track draft pass) and `dataset-production` (Step 5.1 silent self-check) already drop / demote any TEA row that fails the [TEA quality checklist](../refs/tea_details.md#tea-quality-checklist) before handing `<staging_table>` back. **Do not re-run the checklist here** — staging rows that arrived have already passed it. If the user later volunteers corrections to a specific staging row, route the fix back to the originating sub-skill rather than mutating `<staging_table>` in place.

---

## Step 4: Merge staging into the existing source table

> Print to user: `"Merging new questions into your dataset..."`

Capture row counts before merging:

```sql
SET source_count_before = (SELECT COUNT(*) FROM <DATABASE>.<SCHEMA>.<SOURCE_TABLE>);
SET staged_count = (SELECT COUNT(*) FROM <staging_table>);
```

The MERGE carries `GROUND_TRUTH` as a VARIANT column without any changes. If staging rows include `ground_truth_invocations` inside their GROUND_TRUTH, they are merged automatically — no schema change is needed.

Run the merge — the inline subquery dedupes staging by `INPUT_QUERY` (Snowflake's `UNIQUE` constraint is informational only and does **not** prevent duplicate inserts), and `WHEN NOT MATCHED` skips rows already present in the source. The MERGE explicitly carries the `track` column (`'ac'` | `'tea'`) so the merged source table preserves per-row track identity for downstream eval analysis:

```sql
MERGE INTO <DATABASE>.<SCHEMA>.<SOURCE_TABLE> tgt
USING (
    SELECT INPUT_QUERY, GROUND_TRUTH, category, track, notes
    FROM <staging_table>
    QUALIFY ROW_NUMBER() OVER (PARTITION BY INPUT_QUERY ORDER BY INPUT_QUERY) = 1
) src
ON tgt.INPUT_QUERY = src.INPUT_QUERY
WHEN NOT MATCHED THEN INSERT (INPUT_QUERY, GROUND_TRUTH, category, track, notes)
VALUES (
    src.INPUT_QUERY,
    src.GROUND_TRUTH,
    src.category,
    src.track,
    COALESCE(src.notes, 'expanded ' || TO_VARCHAR(CURRENT_DATE()))
);
```

> **`<SOURCE_TABLE>` missing a `track` column.** If the existing source table was registered before the two-track design was introduced, the column must be added and back-filled **before** the MERGE. This mutates the live source table's schema and row data, so it requires explicit user approval.
>
> Show the user the proposed statements **and the live row counts that will be re-classified**, then ⚠️ **STOP for explicit approval** before executing:
>
> ```
> The existing source table <DATABASE>.<SCHEMA>.<SOURCE_TABLE> has no `track` column.
> To MERGE the new rows I need to:
>   1. ALTER TABLE … ADD COLUMN IF NOT EXISTS track VARCHAR;
>   2. UPDATE … SET track = CASE WHEN GROUND_TRUTH:ground_truth_invocations IS NULL
>                                THEN 'ac' ELSE 'tea' END
>                  WHERE track IS NULL;
>
> Rows that will be back-filled as 'ac' (field-absent invocations): <ac_rows>
> Rows that will be back-filled as 'tea' (invocations present, populated or []): <tea_rows>
>
> Apply both statements now? (yes / no — `no` aborts the expand)
> ```
>
> **STOP.** Wait for explicit `yes` before running the ALTER and UPDATE. If the user says `no`, abort the expand (do not run the MERGE — the staging projection writes to a `track` column that the existing source table doesn't have yet, so the MERGE will fail with a column-not-found error).
>
> ```sql
> ALTER TABLE <DATABASE>.<SCHEMA>.<SOURCE_TABLE> ADD COLUMN IF NOT EXISTS track VARCHAR;
> UPDATE <DATABASE>.<SCHEMA>.<SOURCE_TABLE>
> SET track = CASE WHEN GROUND_TRUTH:ground_truth_invocations IS NULL THEN 'ac' ELSE 'tea' END
> WHERE track IS NULL;
> ```

> **Production path:** the staging table's fourth-or-fifth column is `source`, not `notes`. Replace `notes` with `source` in both the `SELECT` projection and the `COALESCE(...)` (and adjust the `INSERT (... notes)` target column only if your source table uses a different column name).

Capture the new count and report:

```sql
SELECT
    $staged_count AS staged,
    (SELECT COUNT(*) FROM <DATABASE>.<SCHEMA>.<SOURCE_TABLE>) - $source_count_before AS inserted,
    $staged_count - ((SELECT COUNT(*) FROM <DATABASE>.<SCHEMA>.<SOURCE_TABLE>) - $source_count_before) AS skipped_duplicates;
```

> Print to user:
> ```
> Expansion complete:
> - New questions added: <N - M>
> - Duplicates skipped: <M>
> ```

Drop the staging table (and the production annotation table if applicable):

```sql
DROP TABLE IF EXISTS <staging_table>;
DROP TABLE IF EXISTS <staging_table>_ANNOTATIONS;  -- only if production path was used
```

> If any step before this drop fails, the staging table remains in `<DATABASE>.<SCHEMA>` for inspection. Note this to the user so they can clean it up manually after troubleshooting.

---

## Step 5: Re-register the merged source table with a new versioned name

> Print to user: `"Registering the expanded dataset..."`

After Step 4's MERGE, re-register `<SOURCE_TABLE>` as a **new versioned evaluation dataset** with one `SYSTEM$CREATE_EVALUATION_DATASET` call — both tracks live in the same table (see parent [`SKILL.md`](../SKILL.md) Registration rule).

Propose to the user and **STOP** for confirm / rename:

- `<source_table>` — `<DATABASE>.<SCHEMA>.<SOURCE_TABLE>` (the merged table from Step 4 — FQN unchanged).
- `<dataset_name>` — default `<existing_dataset_name>_expanded_<YYYYMMDD_HHMMSS>`.

Then run (`USE DATABASE` / `USE SCHEMA` first — required for session context):

```sql
USE DATABASE <DATABASE>;
USE SCHEMA <SCHEMA>;

CALL SYSTEM$CREATE_EVALUATION_DATASET(
    'Cortex Agent',
    '<SOURCE_TABLE>',
    '<dataset_name>',
    OBJECT_CONSTRUCT('query_text', 'INPUT_QUERY', 'expected_tools', 'GROUND_TRUTH')
);
```

Record `<source_table>`, `<dataset_name>`, and `<METRIC_SCOPE>` for the parent skill's Workflow → Step 2.

**This sub-skill is complete — return control to the parent [`dataset/SKILL.md`](../SKILL.md).**

---

## Troubleshooting

See parent [`dataset/SKILL.md`](../SKILL.md) for common errors and solutions.

Additional issues specific to the expand flow:

| Symptom | What to do |
|---------|------------|
| Sub-skill ran in `standalone` mode and clobbered `EVAL_DATASET_<AGENT_NAME>_<YYYYMMDD_HHMMSS>` | The sub-skill ignored the `build-only` directive. Restore from time travel: `CREATE TABLE ... AS SELECT * FROM <SOURCE_TABLE> AT(OFFSET => -60)`. Re-invoke the sub-skill explicitly stating `mode = build-only` and supplying `target_table`. |
| `MERGE` projection fails on column count | The staging table's fourth column is `source`, not `notes` (production path). Adjust the `INSERT` column list to match the staging schema. |
| Source table has no `notes` column | The expand `MERGE` assumes the canonical schema. If the original table omitted `notes`, drop it from the projection or `ALTER TABLE ... ADD COLUMN notes VARCHAR` first. |
| Source table has no `track` column | Pre-two-track schema. Step 4 walks you through the explicit `ALTER TABLE … ADD COLUMN track` + back-fill flow with a STOP for user approval. |
| Staging table left behind after a failure | Drop manually: `DROP TABLE IF EXISTS <staging_table>; DROP TABLE IF EXISTS <staging_table>_ANNOTATIONS;` |
