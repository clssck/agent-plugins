# Inference with a Fine-Tuned arctic-extract Model

Use your fine-tuned model with `AI_EXTRACT` by passing the model name via the `model` parameter.

---

## Required Privileges

Before running inference, ensure the role has these privileges on the fine-tuned model object:

| Privilege | Object |
|-----------|--------|
| `OWNERSHIP` or `USAGE` | Fine-tuned model |
| `READ` | Fine-tuned model |

---

## Basic Inference

```sql
SELECT AI_EXTRACT(
    model => 'db.schema.my_tuned_model',
    file  => TO_FILE('@db.schema.stage', 'document.pdf')
);
```

The fine-tuned model uses the questions baked in during training — no `responseFormat` needed.

Access the result:

```sql
SELECT AI_EXTRACT(
    model => 'db.schema.my_tuned_model',
    file  => TO_FILE('@db.schema.stage', 'invoice.pdf')
):response AS extracted_fields;

-- Access individual fields
SELECT
    AI_EXTRACT(
        model => 'db.schema.my_tuned_model',
        file  => TO_FILE('@db.schema.stage', 'invoice.pdf')
    ):response:invoice_number::STRING AS invoice_number,
    AI_EXTRACT(
        model => 'db.schema.my_tuned_model',
        file  => TO_FILE('@db.schema.stage', 'invoice.pdf')
    ):response:total::STRING AS total;
```

---

## Overriding Questions with `responseFormat`

Pass `responseFormat` to extend or override the trained questions:

```sql
SELECT AI_EXTRACT(
    model        => 'db.schema.my_tuned_model',
    file         => TO_FILE('@db.schema.stage', 'document.pdf'),
    responseFormat => [
        ['name', 'What is the first name of the employee?'],
        ['city', 'Where does the employee live?']
    ]
);
```

> Use this to add new fields not covered in training, or to refine question wording for edge cases.

---

## Single File Test — Compare Fine-Tuned vs. Base Model

Run this before batch processing to validate improvement:

```sql
-- Fine-tuned model
SELECT
    'fine-tuned' AS model_type,
    AI_EXTRACT(
        model => 'db.schema.my_tuned_model',
        file  => TO_FILE('@db.schema.stage', 'test_doc.pdf')
    ):response AS result

UNION ALL

-- Base model (no model parameter = uses arctic-extract default)
SELECT
    'base' AS model_type,
    AI_EXTRACT(
        file          => TO_FILE('@db.schema.stage', 'test_doc.pdf'),
        responseFormat => {'invoice_number': 'What is the invoice number?', 'total': 'What is the total?'}
    ):response AS result;
```

---

## Batch Processing

```sql
-- Enable directory table
ALTER STAGE db.schema.stage REFRESH;

-- Batch extract with fine-tuned model
SELECT
    SPLIT_PART(relative_path, '/', -1) AS filename,
    AI_EXTRACT(
        model => 'db.schema.my_tuned_model',
        file  => TO_FILE('@db.schema.stage', SPLIT_PART(relative_path, '/', -1))
    ):response AS result
FROM DIRECTORY(@db.schema.stage)
WHERE relative_path ILIKE '%.pdf';
```

To persist results, wrap the batch query in `CREATE TABLE AS SELECT`. To keep the fine-tuned model running on new files as they land, build a pipeline — see `../../../ai-functions-pipeline-builder/references/pipeline.md`.

---

## Copying the Model

The fine-tuned model is a first-class Snowflake object and can be copied between databases, schemas, or accounts:

```sql
-- Copy to another schema in the same account
CREATE MODEL db2.schema2.my_tuned_model
    FROM MODEL db.schema.my_tuned_model;
```

For cross-account copying, use data sharing or replication — see [Snowflake docs](https://docs.snowflake.com/en/user-guide/snowflake-cortex/arctic-extract-finetuning).

---

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Model not found` | Wrong fully qualified name | Verify with `SHOW MODELS IN SCHEMA db.schema` |
| `Insufficient privileges` | Missing `USAGE` or `READ` on model | Grant privileges to the role |
| Worse results than base model | Overfitting or insufficient training data | Add more varied examples, retrain |
| `File not found` | TO_FILE path issue | See TO_FILE path rules in `../../references/ai-extract.md` |
