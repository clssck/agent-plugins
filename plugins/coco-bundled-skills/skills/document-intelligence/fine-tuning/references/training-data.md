# Training Data Preparation

Prepare a Snowflake Dataset with labeled document examples for fine-tuning arctic-extract.

---

## Dataset Column Schema

The Dataset must contain exactly three columns (case-insensitive, any order):

| Column | Type | Description |
|--------|------|-------------|
| `File` | STRING | Stage path to the document: `@db.schema.stage/file.pdf` |
| `Prompt` | JSON | Key/question pairs in any `responseFormat` format supported by `AI_EXTRACT` |
| `Response` | JSON | Key/answer pairs matching the keys in `Prompt` |

Additional columns are ignored.

---

## Prompt Formats

All three `AI_EXTRACT` responseFormat styles are supported:

### Format 1: Object (key → question)

```json
{"date": "What is the date?", "total": "What is the total amount?"}
```

### Format 2: Array of pairs

```json
[["invoice_number", "What is the invoice number?"], ["vendor", "What is the vendor name?"]]
```

### Format 3: JSON Schema (for table extraction)

```json
{
  "schema": {
    "type": "object",
    "properties": {
      "deductions": {
        "description": "Deductions",
        "type": "object",
        "properties": {
          "deductions_name": {"type": "array"},
          "current": {"type": "array"}
        }
      }
    }
  }
}
```

---

## Response Format

The `Response` column must contain a JSON object with keys matching the `Prompt`:

```json
{"date": "2024-06-30", "total": "82.50"}
```

**If the document does not contain an answer**, set the value to `None`:

```json
{"invoice_number": "543433434", "vendor": "None"}
```

---

## Example Dataset Rows

| File | Prompt | Response |
|------|--------|----------|
| `@db.schema.stage/file1.pdf` | `{"date": "What is the date?", "total": "What is the total?"}` | `{"date": "2024-06-30", "total": "82.50"}` |
| `@db.schema.stage/file2.pdf` | `[["invoice_number", "What is the invoice number?"], ["vendor", "What is the vendor?"]]` | `{"invoice_number": "543433434", "vendor": "Example Corp"}` |

---

## Creating the Dataset

Follow these steps exactly:

### Step 1: Create a staging table

```sql
CREATE OR REPLACE TABLE db.schema.my_data_table (
    f FILE,
    p VARCHAR,
    r VARCHAR
);
```

### Step 2: Insert training rows

Insert one row per document/question-set pair. Use `TO_FILE()` for the file column:

```sql
INSERT INTO db.schema.my_data_table (f, p, r)
SELECT
    TO_FILE('@db.schema.stage', 'invoice_001.pdf'),
    '{"invoice_number": "What is the invoice number?", "date": "What is the invoice date?", "total": "What is the total amount due?"}',
    '{"invoice_number": "INV-2024-001", "date": "2024-06-30", "total": "1250.00"}';
```

Repeat for each document. You can `INSERT` multiple rows in a single statement:

```sql
INSERT INTO db.schema.my_data_table (f, p, r) VALUES
    (TO_FILE('@db.schema.stage', 'inv_001.pdf'), '{"total": "What is the total?"}', '{"total": "1250.00"}'),
    (TO_FILE('@db.schema.stage', 'inv_002.pdf'), '{"total": "What is the total?"}', '{"total": "340.50"}'),
    (TO_FILE('@db.schema.stage', 'inv_003.pdf'), '{"total": "What is the total?"}', '{"total": "None"}');
```

### Step 3: Create the Dataset object

```sql
CREATE OR REPLACE DATASET db.schema.my_dataset;
```

### Step 4: Add a version with the training data

Use `FL_GET_STAGE` and `FL_GET_RELATIVE_PATH` to extract the stage and path from the FILE column:

```sql
ALTER DATASET db.schema.my_dataset ADD VERSION 'v1' FROM (
    SELECT
        FL_GET_STAGE(f) || '/' || FL_GET_RELATIVE_PATH(f) AS "file",
        p AS "prompt",
        r AS "response"
    FROM db.schema.my_data_table
);
```

The dataset is now referenceable as `snow://dataset/db.schema.my_dataset/versions/v1`.

---

## Validation Queries

Run these before submitting the fine-tuning job:

```sql
-- Check row count (recommend >= 20 documents)
SELECT COUNT(*) AS total_rows FROM db.schema.my_data_table;

-- Check for null or empty responses
SELECT * FROM db.schema.my_data_table
WHERE r IS NULL OR r = '' OR r = '{}';

-- Preview the dataset version
SELECT * FROM db.schema.my_dataset VERSIONS WHERE version = 'v1';
```

---

## Tips for Good Training Data

| Tip | Why |
|-----|-----|
| Include rows where the answer is `None` | Teaches the model when fields are absent |
| Include examples where the default answer is already correct | Confirms correct defaults; improves consistency |
| Cover variations in layout across the same document type | Prevents overfitting to a single layout |
| Use the same question wording as your inference `responseFormat` | Schema is derived from the union of all Prompt keys |
| Don't need to use the same questions for every document | Partial coverage per document is fine |

---

## Next Step

Once your Dataset is ready → proceed to `job-management.md` to submit the fine-tuning job.
