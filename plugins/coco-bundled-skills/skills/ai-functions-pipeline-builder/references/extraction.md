# Extraction Workflow

Structured field and table extraction using AI_EXTRACT.

## Use When

- User wants specific fields (names, dates, amounts, IDs)
- User wants tables with defined columns (line items, transactions)

## Constraints & Pricing

See [AI_EXTRACT docs](https://docs.snowflake.com/en/sql-reference/functions/ai_extract) for constraints (max file size, pages, questions per call).

> ⚠️ Check current rates before running: [AI Functions Costs](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-cost). With `scale_factor`, cost scales by the factor value. Don't quote hardcoded credit numbers — they drift; the docs are the source of truth.

## Reference
Read `functions/ai-extract.md` for TO_FILE path handling rules and batch processing patterns. See [AI_EXTRACT docs](https://docs.snowflake.com/en/sql-reference/functions/ai_extract) for full syntax and parameters.

---

## Confidence scores (opt-in)

`AI_EXTRACT` can return a per-field certainty score (0–1) for every value it pulls — useful to route
low-confidence documents for review, flag specific shaky fields, gate auto-approval, or expose a
data-quality metric. Scoring must be enabled **at extract time** (it can't be added downstream): pass
`scores => TRUE`. The response then carries a `scoring` object beside `response`; read a field's score at
`RAW_EXTRACT:scoring:scores:<field>:score` (a 0–1 float) and derive whatever flag you need:

```sql
-- in the AI_EXTRACT(...) call:  scores => TRUE
-- then in the projection:
  TRY_CAST(RAW_EXTRACT:scoring:scores:<field>:score::STRING AS FLOAT) AS <FIELD>_CONF,
  IFF(TRY_CAST(RAW_EXTRACT:scoring:scores:<field>:score::STRING AS FLOAT) < <threshold>, TRUE, FALSE) AS LOW_CONFIDENCE
```

Scoring is **preview** and adds no cost, but only scalar fields get per-field scores — list/table fields
return a single aggregate score, not per-cell — so verify the access path against current docs before
relying on it.

---

## Workflow

### 1. Get File Location [WAIT]

**If files are on Snowflake stage:** Get full stage path, proceed to Step 2.

**If files are local:** You must get the upload destination from the user. Do not create any stages or run any SQL until the user provides this information.

Ask: "Which database, schema, and stage name should I use? (e.g., MY_DB.MY_SCHEMA.MY_STAGE)"

Use the exact stage name the user provides. After user responds, create stage with server-side encryption:
```sql
CREATE STAGE IF NOT EXISTS db.schema.user_provided_stage_name 
DIRECTORY = (ENABLE = TRUE) 
ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');
```

Then upload the files.

### 2. Define Extraction Fields [WAIT]

Ask what fields to extract. For each field, get:
- Field name
- Description of what to extract
- Type: single value, list, or table

Confirm fields back to user before proceeding.

### 3. List Files

Show available files in the stage. Inform user you'll test on one file first.

### 4. Cost Estimate

Display estimated cost for the test file, then proceed to test.

### 5. Single File Test [WAIT]

Extract from ONE file only. Display results clearly. (`AI_EXTRACT` — no `SNOWFLAKE.CORTEX` prefix.)

Ask if satisfied:
- **Yes** → Step 6 (batch)
- **No, wrong fields extracted** → Step 2 (refine descriptions)
- **No, OCR quality issues** (garbled characters, null fields that visibly exist) → Step 5a (Scale Factor Tuning)

### 5a. Scale Factor Tuning [WAIT]

Iteratively increase `scale_factor` (sequence: **1.5 → 2.0 → 2.5 → 3.0 → 4.0**). Always show cost impact before each retry (cost = `scale_factor × default`; page limit = `floor(125 / scale_factor)`).

1. Re-run with `config => { 'scale_factor': 1.5 }`. Good → lock in, go to Step 6. Better but not done → try next value. No improvement / worse → likely not OCR — go back to Step 2 or switch to AI_PARSE_DOCUMENT + AI_COMPLETE.
2. **If 4.0 still unsatisfactory:** suggest refining field descriptions (Step 2), using AI_PARSE_DOCUMENT+AI_COMPLETE, improving source doc quality, or fine-tuning (`../../fine-tuning/SKILL.md`).

### 6. Batch Process

Display batch cost (if `scale_factor > 1.0`, show both default and scaled costs). Execute batch extraction with `config => { 'scale_factor': <value> }` if one was chosen.

### 7. Post-Processing [WAIT]

Offer options:
1. Done - I have what I need
2. Store results in a Snowflake table
3. Set up a pipeline for continuous processing

**Option 2 — Store results:**

```sql
CREATE TABLE IF NOT EXISTS db.schema.extraction_results (
  result_id INT AUTOINCREMENT,
  file_name STRING,
  extracted_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
  -- Add user's extraction fields here
  field1 STRING,
  field2 STRING,
  raw_response VARIANT
);

INSERT INTO db.schema.extraction_results (file_name, field1, field2, raw_response)
SELECT 
  SPLIT_PART(relative_path, '/', -1),
  result:field1::STRING,
  result:field2::STRING,
  result
FROM DIRECTORY(@stage_name),
LATERAL (
  SELECT AI_EXTRACT(
    file => TO_FILE('@stage_name', relative_path),
    responseFormat => {'field1': 'description', 'field2': 'description'}
  ) AS result
)
WHERE relative_path LIKE '%.pdf';
```

After storing, always suggest pipeline setup.

**Option 3 — Pipeline:** Load `references/pipeline.md` (Template A, or Template A2 if page optimization was used in Step 5a).

---

## Stopping Points

| After Step | Wait For |
|------------|----------|
| 1 | File location (and upload destination if local) |
| 2 | Field definitions confirmed |
| 5 | Single file result confirmation |
| 5a | Scale factor tuning result (at each iteration) |
| 7 | Post-processing choice |
