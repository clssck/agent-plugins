# AI_EXTRACT

Extract structured fields from text or documents into JSON output.

**Docs**: [docs.snowflake.com/en/sql-reference/functions/ai_extract](https://docs.snowflake.com/en/sql-reference/functions/ai_extract) — full syntax, parameters, response formats, constraints, scale_factor details, and supported file types.

## Scope

`AI_EXTRACT` pulls **pre-existing facts** out of text or documents — field values that are present in the source.

**Do not use for:**
- **Classification** (assigning a document to one of several categories) → use `AI_CLASSIFY`. Passing a list of categories as a field description (`'doc_type': 'invoice|contract|receipt|...'`) is a common misuse and gives unreliable results.
- **Generated output** (insights, narratives, summaries, recommended actions) → use `AI_COMPLETE`. If the value must be *reasoned about or created* rather than *read from the document*, it belongs in `AI_COMPLETE` or `AI_CLASSIFY`.

---

## ⚠️ CRITICAL: Always Display Pricing Before Execution

**Before AI_EXTRACT calls, warn the user to check current rates at the link below before proceeding.**

> ⚠️ Check current rates before running: [AI Functions Costs](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-cost)

---

## TO_FILE Path Handling (READ THIS FIRST)

**This is the most common source of errors.** Follow these rules exactly:

### Rule 1: Stage path and filename are SEPARATE arguments

```sql
-- CORRECT: Two separate arguments
TO_FILE('@db.schema.mystage', 'invoice.pdf')

-- WRONG: Concatenated path
TO_FILE('@db.schema.mystage/invoice.pdf')
```

### Rule 2: Use the FILENAME only, not the path from LIST/DIRECTORY

When you run LIST or DIRECTORY, the output shows paths like `folder/invoice.pdf`. **Do NOT use this full path as the filename argument.** Extract just the filename.

**Example scenario:**
- User provides stage: `@mydb.myschema.docs`
- User wants file: `report.pdf`
- LIST shows: `files/report.pdf` (includes folder prefix)

```sql
-- WRONG: Using the path from LIST output
TO_FILE('@mydb.myschema.docs', 'files/report.pdf')

-- CORRECT: Using just the filename
TO_FILE('@mydb.myschema.docs', 'report.pdf')
```

### Rule 3: For batch processing, strip the folder prefix from relative_path

When processing files via DIRECTORY(), the `relative_path` column may include folder prefixes. Strip them:

```sql
-- If relative_path is 'files/report.pdf', extract just 'report.pdf'
SELECT 
    relative_path,
    AI_EXTRACT(
        file => TO_FILE('@mydb.myschema.docs', 
                        SPLIT_PART(relative_path, '/', -1)),  -- Gets just filename
        responseFormat => ['invoice_number', 'total']
    ):response AS result
FROM DIRECTORY(@mydb.myschema.docs)
WHERE relative_path ILIKE '%.pdf';
```

**Alternative:** If files are at root level of stage, `relative_path` can be used directly:

```sql
-- Only when relative_path equals filename (no folder prefix)
TO_FILE('@stage', relative_path)
```

### Rule 4: DDL commands do NOT use @ prefix

The `@` symbol is only used when **referencing** a stage in queries. DDL commands (ALTER, CREATE, DROP) use the stage name directly:

```sql
-- WRONG: Using @ in DDL
ALTER STAGE @mydb.myschema.mystage SET DIRECTORY = (ENABLE = TRUE);

-- CORRECT: No @ prefix for DDL
ALTER STAGE mydb.myschema.mystage SET DIRECTORY = (ENABLE = TRUE);
```

| Command Type | Use `@`? | Example |
|--------------|----------|---------|
| LIST | Yes | `LIST @db.schema.stage` |
| DIRECTORY() | Yes | `FROM DIRECTORY(@db.schema.stage)` |
| TO_FILE() | Yes | `TO_FILE('@db.schema.stage', 'file.pdf')` |
| ALTER STAGE | **No** | `ALTER STAGE db.schema.stage ...` |
| CREATE STAGE | **No** | `CREATE STAGE db.schema.stage ...` |
| DROP STAGE | **No** | `DROP STAGE db.schema.stage` |

---

## Accessing Results

```sql
AI_EXTRACT(...):response:field_name::STRING
```

---

## Usage Patterns
### Pattern 1: Text Extraction

```sql
SELECT AI_EXTRACT(
    text => 'Jan Kowalski lives in Warsaw and works for Snowflake',
    responseFormat => ['person', 'location', 'organization']
):response AS result;
-- {"person": "Jan Kowalski", "location": "Warsaw", "organization": "Snowflake"}
```

### Pattern 2: Single File Extraction

**Given:** Stage `@mydb.myschema.invoices` and file `invoice1.pdf`

```sql
SELECT AI_EXTRACT(
    file => TO_FILE('@mydb.myschema.invoices', 'invoice1.pdf'),
    responseFormat => {
        'invoice_number': 'What is the invoice number?',
        'total': 'What is the total amount?'
    }
):response AS result;
```
### Pattern 3: Batch Processing (All Files in Stage)

**Given:** Stage `@mydb.myschema.invoices` containing files in subfolders

```sql
-- Enable directory table (NOTE: DDL commands do NOT use @ prefix)
ALTER STAGE mydb.myschema.invoices SET DIRECTORY = (ENABLE = TRUE);
ALTER STAGE mydb.myschema.invoices REFRESH;

-- Process all PDFs - use SPLIT_PART to get filename only
SELECT 
    relative_path,
    SPLIT_PART(relative_path, '/', -1) AS filename,
    AI_EXTRACT(
        file => TO_FILE('@mydb.myschema.invoices', SPLIT_PART(relative_path, '/', -1)),
        responseFormat => {
            'invoice_number': 'What is the invoice number?',
            'total': 'What is the total amount?'
        }
    ):response AS result
FROM DIRECTORY(@mydb.myschema.invoices)
WHERE relative_path ILIKE '%.pdf';
```

### Pattern 4: Table Extraction (Line Items)

```sql
SELECT AI_EXTRACT(
    file => TO_FILE('@mydb.myschema.invoices', 'invoice1.pdf'),
    responseFormat => {
        'schema': {
            'type': 'object',
            'properties': {
                'invoice_number': {
                    'type': 'string',
                    'description': 'Invoice number'
                },
                'line_items': {
                    'type': 'object',
                    'description': 'Line items from the invoice',
                    'column_ordering': ['description', 'quantity', 'unit_price', 'amount'],
                    'properties': {
                        'description': { 'description': 'Item description', 'type': 'array' },
                        'quantity': { 'description': 'Quantity', 'type': 'array' },
                        'unit_price': { 'description': 'Unit price', 'type': 'array' },
                        'amount': { 'description': 'Total amount', 'type': 'array' }
                    }
                }
            }
        }
    }
):response AS result;
```

### Pattern 5: Mixed Extraction (Fields + Table)

```sql
SELECT AI_EXTRACT(
    file => TO_FILE('@stage', 'report.pdf'),
    responseFormat => {
        'schema': {
            'type': 'object',
            'properties': {
                'title': { 'type': 'string', 'description': 'Document title' },
                'authors': { 'type': 'array', 'description': 'List of authors' },
                'data_table': {
                    'type': 'object',
                    'description': 'Monthly revenue data',
                    'column_ordering': ['month', 'revenue'],
                    'properties': {
                        'month': { 'description': 'Month', 'type': 'array' },
                        'revenue': { 'description': 'Revenue amount', 'type': 'array' }
                    }
                }
            }
        }
    }
):response AS result;
```

### Pattern 6: Batch Processing with Scale Factor

When a scale_factor was determined during testing, carry it into the batch query:

```sql
SELECT 
    SPLIT_PART(relative_path, '/', -1) AS filename,
    AI_EXTRACT(
        file => TO_FILE('@mydb.myschema.invoices', SPLIT_PART(relative_path, '/', -1)),
        responseFormat => {
            'invoice_number': 'What is the invoice number?',
            'total': 'What is the total amount?'
        },
        config => { 'scale_factor': 1.5 }
    ):response AS result
FROM DIRECTORY(@mydb.myschema.invoices)
WHERE relative_path ILIKE '%.pdf';
```

---

## Real-World Example: Invoice Processing

**Scenario:** User has stage `@acme.finance.billing_docs` with invoice PDFs

**Step 1: List files**
```sql
LIST @acme.finance.billing_docs;
-- Shows: documents/inv_001.pdf, documents/inv_002.pdf, etc.
```

**Step 2: Single file test (use filename only, NOT the path from LIST)**
```sql
SELECT AI_EXTRACT(
    file => TO_FILE('@acme.finance.billing_docs', 'inv_001.pdf'),
    responseFormat => {
        'invoice_number': 'What is the invoice number?',
        'date': 'Invoice date in YYYY-MM-DD format',
        'total': 'Total amount due'
    }
):response AS result;
```

**Step 3: Batch all files**
```sql
SELECT 
    SPLIT_PART(relative_path, '/', -1) AS filename,
    AI_EXTRACT(
        file => TO_FILE('@acme.finance.billing_docs', SPLIT_PART(relative_path, '/', -1)),
        responseFormat => {
            'invoice_number': 'What is the invoice number?',
            'date': 'Invoice date in YYYY-MM-DD format',
            'total': 'Total amount due'
        }
    ):response AS result
FROM DIRECTORY(@acme.finance.billing_docs)
WHERE relative_path ILIKE '%.pdf';
```

---

## Prompt Engineering Tips

| Problem | Solution |
|---------|----------|
| Wrong field extracted | Add "NOT the [other field]" to question |
| Wrong format | Specify: "Return as YYYY-MM-DD", "number only" |
| Missing field | Add "If not found, return null" |
| Ambiguous | Describe location: "at the top", "in the header" |
| OCR typos / garbled characters | Use `config => { 'scale_factor': 1.5 }`, increase incrementally up to 4.0 |
| Missing values from dense/small text | Use `config => { 'scale_factor': 1.5 }`, increase incrementally |
| Large page format (bigger than A4) | Use `scale_factor` 1.5 or 2.0 |
| Systematic poor accuracy on a specific document type even at scale_factor 4.0 | Fine-tune arctic-extract — see `../fine-tuning/SKILL.md` |

**Good questions:**
```sql
'invoice_number': 'What is the invoice number? Usually labeled "Invoice #". NOT the PO number.'
'date': 'What is the invoice date? Return in YYYY-MM-DD format. NOT the due date.'
'total': 'What is the total amount due? Return as number without currency symbol.'
```

---

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| File not found | Wrong path in TO_FILE | Use filename only, not full path from LIST |
| `invalid array format` | Malformed responseFormat | Check syntax — see [docs](https://docs.snowflake.com/en/sql-reference/functions/ai_extract) 
| | `too many questions` | >100 entities or >10 tables | Split into multiple calls |
| OCR typos or garbled text | Small text, dense layout, or large pages | Use `config => { 'scale_factor': 1.5 }`, increase up to 4.0 |
| Null/missing values that exist in doc | Text too small for default OCR | Use `config => { 'scale_factor': 1.5 }`, increase up to 4.0 |

For the full list of error conditions, see [AI_EXTRACT docs](https://docs.snowflake.com/en/sql-reference/functions/ai_extract#error-conditions).

## Large Documents (>125 pages)

AI_EXTRACT limit is 125 pages (less with scale_factor). Options:
1. Split PDF into chunks before processing
2. Use AI_PARSE_DOCUMENT (2000 page limit) + AI_COMPLETE

## Stage Restrictions

**Works with:** Named internal stages, external stages (S3, Azure, GCS)

**Does NOT work with:** User stages (`@~`), table stages, encrypted external stages
