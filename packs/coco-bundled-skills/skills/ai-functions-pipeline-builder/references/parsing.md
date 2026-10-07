# Parsing Workflow

Full text extraction using AI_PARSE_DOCUMENT.

## Use When

- User wants full text from documents
- User wants layout/structure preserved (tables, headers)
- User needs OCR from scanned documents

## Constraints

| Constraint | Limit |
|------------|-------|
| Max file size | 100 MB |
| Max pages | 2000 per call |

## Pricing

> ⚠️ Check current rates before running: [Snowflake Service Consumption Table](https://docs.snowflake.com/en/user-guide/cost-understanding-overall#service-type). LAYOUT mode costs more than OCR mode. Don't quote hardcoded credit numbers — they drift; the docs are the source of truth.

**Full pricing details:** See [ai-parse-doc.md](functions/ai-parse-doc.md)

> **Read `functions/ai-parse-doc.md` before writing any SQL** — do not use `AI_PARSE_DOCUMENT` syntax from memory (`TO_FILE()` wrapper and result path accessor must come from that file).

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

### 2. Choose Parsing Mode [WAIT]

Ask: **LAYOUT** (structure-preserving: tables/headings/lists, costs more — best for reports/forms) or **OCR** (plain text, cheaper — best for scanned docs).

### 3. List Files

Show available files in the stage. Inform user you'll test on one file first.

### 4. Cost Estimate

Display estimated cost for the test file, then proceed to test.

### 5. Single File Test [WAIT]

Parse ONE file only. Display first ~1500 characters of results. (`AI_PARSE_DOCUMENT` — no `SNOWFLAKE.CORTEX` prefix.)

Ask if satisfied:
- Yes → proceed to batch
- No → try the other mode, return to Step 4

### 6. Batch Process

Display batch cost for all files, then execute batch parsing.

### 7. Post-Processing [WAIT]

Offer options:
1. Done - I have what I need
2. Store results in a Snowflake table
3. Set up a pipeline for continuous processing

**Option 2 — Store results:**

```sql
CREATE TABLE IF NOT EXISTS db.schema.parsed_documents (
  doc_id INT AUTOINCREMENT,
  file_name STRING,
  content TEXT,
  parsed_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

INSERT INTO db.schema.parsed_documents (file_name, content)
SELECT 
  SPLIT_PART(relative_path, '/', -1),
  AI_PARSE_DOCUMENT(TO_FILE('@stage_name', relative_path), {'mode': 'LAYOUT'}):content::STRING
FROM DIRECTORY(@stage_name)
WHERE relative_path LIKE '%.pdf';
```

After storing, always suggest pipeline setup.

**Option 3 — Pipeline:** Load `references/pipeline.md` (Template B).

---

## Stopping Points

| After Step | Wait For |
|------------|----------|
| 1 | File location (and upload destination if local) |
| 2 | Parsing mode selection |
| 5 | Single file result confirmation |
| 7 | Post-processing choice |
