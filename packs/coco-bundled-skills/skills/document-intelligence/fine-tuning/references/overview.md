# Fine-Tuning arctic-extract — Overview

Fine-tune the `arctic-extract` model to improve `AI_EXTRACT` accuracy on your specific document types and layouts.

**Docs**: [docs.snowflake.com/en/user-guide/snowflake-cortex/arctic-extract-finetuning](https://docs.snowflake.com/en/user-guide/snowflake-cortex/arctic-extract-finetuning)

---

## When to Fine-Tune arctic-extract vs. When to Keep Prompt-tuning

| Situation | Recommended Action |
|-----------|-------------------|
| Occasional OCR issues (garbled characters, null values) | Try `scale_factor` first (1.5 → 4.0) |
| Wrong fields extracted, bad descriptions | Refine `responseFormat` questions |
| `scale_factor` 4.0 still unsatisfactory on a specific doc type | **Fine-tune** |
| Same document layout used repeatedly at scale (invoices, payslips, forms) | **Fine-tune** |
| You have 20+ labeled document examples | **Fine-tune** |
| One-off extraction from varied, unpredictable documents | Stick with prompt engineering |

Fine-tuning produces a custom model stored as a Snowflake object. It does not change the base `arctic-extract` model.

---

## Prerequisites

### Role & Privileges

| Privilege | Object |
|-----------|--------|
| `USAGE` or `OWNERSHIP` | Database containing the Dataset |
| `USAGE` or `OWNERSHIP` | Schema containing the Dataset |
| `READ` or `OWNERSHIP` | Stage where document files are stored |
| `USAGE` or `OWNERSHIP` | Schema where the fine-tuned model will be stored |
| `CREATE MODEL` | Schema where the fine-tuned model will be stored |

Additionally, the `ACCOUNTADMIN` role must grant the `SNOWFLAKE.CORTEX_USER` database role to the user calling `FINETUNE`.

```sql
-- Run as ACCOUNTADMIN
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <your_role>;
```

---

## Supported File Formats

| Format | Supported |
|--------|-----------|
| PDF | Yes |
| PNG | Yes |
| JPG, JPEG | Yes |
| TIFF, TIF | Yes |

---

## Key Limits

| Limit | Value |
|-------|-------|
| Minimum documents (recommended) | 20 |
| Maximum unique document files in Dataset | 1,000 |
| Max pages per document (AWS US West 2 / Europe Central 1) | 64 |
| Max pages per document (AWS US East 1 / Azure East US 2) | 125 |
| Questions × total pages across all documents | ≤ 50,000 |
| Training epochs | Auto-determined, can be set optionally between values 2 and 10 |
| `options` parameter | supported for arctic-extract |

**Valid combinations for the 50,000 limit:**

| Questions | Pages per doc | Doc files |
|-----------|---------------|-----------|
| 10 | 1 | 5,000 |
| 100 | 1 | 500 |
| 10 | 10 | 500 |
| 25 | 10 | 200 |

> **Note:** The same document file can be referenced multiple times in the Dataset.

---

## Fine-Tuning Workflow (High Level)

```
1. Prepare labeled documents (File + Prompt + Response)
      ↓
2. Create a Snowflake Dataset object with your training data
      ↓
3. Submit a FINETUNE('CREATE') job
      ↓
4. Monitor with FINETUNE('DESCRIBE') until status = SUCCESS
      ↓
5. Use AI_EXTRACT(model => 'db.schema.my_tuned_model', ...)
```

**Reference files:**
- Training data preparation → `training-data.md`
- Job creation and monitoring → `job-management.md`
- Running inference with the fine-tuned model → `inference.md`
