# Document Classification Workflow

Classify and categorize documents into user-defined categories using AI_CLASSIFY.

## Use When

- User wants to sort/categorize/triage documents by type (e.g., invoice, contract, receipt)
- User wants to route documents to different processing workflows
- User wants to identify document types in a mixed stage

## Constraints

| Constraint | Limit |
|------------|-------|
| Categories | 2-500 (>20 may reduce accuracy) |
| Image formats (direct) | JPG, JPEG, PNG, WEBP, GIF |
| Document formats (parse first) | PDF, DOCX, PPTX, HTML, TXT |
| Output modes | Single-label (default), multi-label |

Requires `SNOWFLAKE.CORTEX_USER` database role.

## Supported Format Strategies

| Format | Strategy |
|--------|----------|
| JPG, PNG, WEBP, GIF | Direct image classification via `AI_CLASSIFY(TO_FILE(...), categories)` |
| PDF, DOCX, PPTX, HTML, TXT | Parse first page (LAYOUT mode) via `AI_PARSE_DOCUMENT`, then classify extracted text |

## Pricing

> ⚠️ Check current rates before running — don't quote hardcoded credit numbers; they drift, and the docs are the source of truth:
> - `AI_CLASSIFY` (billed on input tokens) → [AI Functions Costs](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-cost)
> - `AI_PARSE_DOCUMENT` (added when text extraction is needed for PDF/DOCX/etc.) → [Snowflake Service Consumption Table](https://docs.snowflake.com/en/user-guide/cost-understanding-overall#service-type)

Parsing only the first page keeps the parse cost minimal.

**Full pricing details:** See [ai-classify.md](functions/ai-classify.md)

## Reference
Read `functions/ai-classify.md` to get the correct AI_CLASSIFY syntax. This prevents errors from incorrect function signatures.

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

### 2. Define Categories [WAIT]

Ask for: label names (e.g. "invoice", "contract"), optional per-label descriptions (≤25 words each), single- or multi-label mode, optional `task_description` (≤50 words), and optional few-shot examples. Confirm back to user before proceeding.

### 3. List Files & Determine Strategy

Show available files. Strategy: images (JPG, PNG, WEBP, GIF) → direct `AI_CLASSIFY`; PDFs/DOCX/PPTX/HTML/TXT → parse first page (`LAYOUT`, `page_filter: [{'start': 0, 'end': 1}]`) then classify. Mixed → apply both arms. Inform user you'll test one file first.

### 4. Cost Estimate

Display estimated cost for the test file (images: AI_CLASSIFY only; documents: AI_PARSE_DOCUMENT 1 page + AI_CLASSIFY), then proceed.

### 5. Single File Test [WAIT]

Classify ONE file only. Display results clearly. (`AI_CLASSIFY` — no `SNOWFLAKE.CORTEX` prefix.)

**For image files:**
```sql
SELECT AI_CLASSIFY(
    TO_FILE('@stage', 'photo.jpg'),
    ['invoice', 'contract', 'receipt', 'tax_form'],
    {'task_description': 'Classify business documents by their document type'}
):labels AS classification;
```

**For document files (parse first page, then classify):**
```sql
SELECT AI_CLASSIFY(
    AI_PARSE_DOCUMENT(
        TO_FILE('@stage', 'doc.pdf'),
        {'mode': 'LAYOUT', 'page_filter': [{'start': 0, 'end': 1}]}
    ):pages[0]:content::VARCHAR,
    ['invoice', 'contract', 'receipt', 'tax_form'],
    {'task_description': 'Classify business documents by their document type'}
):labels AS classification;
```

Ask if satisfied:
- **Yes, classification is correct** → proceed to Step 6 (batch)
- **No, wrong category assigned** → return to Step 2 to refine labels, descriptions, task_description, or add few-shot examples
- **No, classification seems uncertain or off** (may need more document context) → proceed to Step 5a (Page Context Tuning)

**Category vs context:** if the label makes no sense for the doc type → refine categories (Step 2); if the label is plausible but the first page lacked enough content (cover pages, generic headers) → try Step 5a.

### 5a. Page Context Tuning [WAIT]

Iteratively increase pages parsed (docs only, not images). Show the cost impact (table below) before each retry.

1. **Try first 3 pages.** Re-run with `{'mode': 'LAYOUT', 'page_filter': [{'start': 0, 'end': 3}]}`. With `page_filter`, access content via `:pages[0]:content` (not `:content`). Good → Step 6. Better but not done → try 5 pages. No improvement → Step 2 (refine labels).
2. **Try all pages.** Omit `page_filter`; access via `:content`. Still not satisfactory → refine labels/descriptions (Step 2), add few-shot examples, or add a task_description.

**Cost impact reference (display at each iteration):**

| Pages parsed | AI_PARSE_DOCUMENT cost per file | Notes |
|---|---|---|
| First page only | 1× per-page rate | Default, cheapest |
| First 3 pages | ~3× per-page rate | 3x cost |
| First 5 pages | ~5× per-page rate | 5x cost |
| All pages | num_pages × per-page rate | Highest cost, most context |

**Important:** Always display the cost impact before each retry. Never silently increase page count.

### 6. Batch Process

Display batch cost (AI_PARSE_DOCUMENT per page if applicable + AI_CLASSIFY, using page count from Step 5a if adjusted). Execute batch classification:

**For image files:**
```sql
SELECT
    SPLIT_PART(relative_path, '/', -1) AS filename,
    AI_CLASSIFY(
        TO_FILE('@stage', SPLIT_PART(relative_path, '/', -1)),
        ['invoice', 'contract', 'receipt', 'tax_form'],
        {'task_description': 'Classify business documents by their document type'}
    ):labels[0]::VARCHAR AS category
FROM DIRECTORY(@stage)
WHERE relative_path ILIKE '%.jpg'
   OR relative_path ILIKE '%.png';
```

**For document files:**
```sql
SELECT
    SPLIT_PART(relative_path, '/', -1) AS filename,
    AI_CLASSIFY(
        AI_PARSE_DOCUMENT(
            TO_FILE('@stage', SPLIT_PART(relative_path, '/', -1)),
            {'mode': 'LAYOUT', 'page_filter': [{'start': 0, 'end': 1}]}
        ):pages[0]:content::VARCHAR,
        ['invoice', 'contract', 'receipt', 'tax_form'],
        {'task_description': 'Classify business documents by their document type'}
    ):labels[0]::VARCHAR AS category
FROM DIRECTORY(@stage)
WHERE relative_path ILIKE '%.pdf';
```

Show category counts per label after batch completes.

### 7. Post-Processing [WAIT]

Ask: process a specific category, store results, set up a pipeline, or done.

**Option 1 — Chain to another workflow:**

Ask which category to process and what to do with it. Route to the appropriate sub-skill with a WHERE clause filtering by category:

| User wants | Route to |
|---|---|
| Extract fields from a category (e.g., all invoices) | `references/extraction.md` |
| Parse full text from a category | `references/parsing.md` |
| Analyze charts/visuals from a category | `references/visual-analysis.md` |

The chained workflow handles its own post-processing from there.

**Option 2 — Store results:**

```sql
CREATE TABLE IF NOT EXISTS db.schema.classification_results (
    result_id INT AUTOINCREMENT,
    file_path STRING,
    file_name STRING,
    category STRING,
    labels_raw VARIANT,
    classified_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

INSERT INTO db.schema.classification_results (file_path, file_name, category, labels_raw)
SELECT
    relative_path,
    SPLIT_PART(relative_path, '/', -1),
    AI_CLASSIFY(...):labels
FROM DIRECTORY(@stage)
WHERE relative_path ILIKE '%.pdf';
```

After storing, always suggest pipeline setup.

**Option 3 — Pipeline:**

- If the user **only classified** (did not chain to another workflow via Option 1): Load `references/pipeline.md` **Template D** (classification-only pipeline).
- If the user **chained to another workflow** via Option 1 (e.g., classify → extract, or classify → extract → summarize): Load `references/pipeline.md` **Template E** (multi-step pipeline). This creates an N-step pipeline with a root classification task and child tasks for each subsequent operation, linked via `AFTER`.

**Option 4 — Done:** End workflow.

---

## Stopping Points

| After Step | Wait For |
|------------|----------|
| 1 | File location (and upload destination if local) |
| 2 | Category definitions confirmed |
| 5 | Single file classification result confirmation |
| 5a | Page context tuning result (at each iteration) |
| 7 | Post-processing choice |
