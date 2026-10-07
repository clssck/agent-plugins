---
name: fine-tuning
description: "Fine-tune the arctic-extract model to improve AI_EXTRACT accuracy on domain-specific documents. Use when: AI_EXTRACT results are consistently poor on a specific document type, scale_factor 4.0 is insufficient, you have 20+ labeled examples. Triggers: fine-tune, fine-tuning, custom model, train arctic-extract, improve extraction accuracy, domain-specific extraction, better extraction results, FINETUNE, SNOWFLAKE.CORTEX.FINETUNE."
parent_skill: document-intelligence
---

# Fine-Tuning arctic-extract

Improve `AI_EXTRACT` accuracy on your document types by training a custom arctic-extract model.

## When to Use This Skill

- `AI_EXTRACT` results are consistently inaccurate on a specific document type
- `scale_factor` 4.0 has been tried and accuracy is still insufficient
- You process the same document layout repeatedly at scale (invoices, payslips, forms)
- You have at least 20 labeled document examples available

If you haven't tried `scale_factor` tuning yet, start with `../references/ai-extract.md` (scale_factor tuning) before fine-tuning.

---

## Workflow

### Step 1: Confirm Fine-Tuning Is the Right Approach [WAIT]

Ask the user:

```
Before fine-tuning, let's confirm this is the right approach:

1. Have you tried scale_factor tuning (1.5 → 4.0) with AI_EXTRACT?
2. Do you have at least 20 labeled document examples (document + expected extraction output)?
3. Is this a recurring document type you'll process regularly?

If yes to all three → fine-tuning is the right next step.
If no to #1 → start with scale_factor tuning first (cheaper and faster).
If no to #2 → gather more labeled examples before proceeding.
```

---

### Step 2: Check Prerequisites [WAIT]

Verify access control is in place. Run:

```sql
-- Check if CORTEX_USER role is granted
SHOW GRANTS TO ROLE <your_role>;
```

Required:
- `SNOWFLAKE.CORTEX_USER` database role granted to the user's role (by ACCOUNTADMIN)
- `CREATE MODEL` privilege on the target schema
- `READ` on the stage where documents are stored

If missing privileges, show the user what to request from their ACCOUNTADMIN. See `references/overview.md` for the full privilege list.

---

### Step 3: Prepare Training Data [WAIT]

Load `references/training-data.md` to guide the user through:

1. Creating a staging table with `FILE`, `Prompt`, `Response` columns
2. Inserting labeled rows using `TO_FILE()`
3. Creating a Snowflake Dataset object
4. Adding a versioned snapshot with `ALTER DATASET ADD VERSION`

Key questions to ask:
- Where are the document files? (Snowflake stage path)
- What fields do you want to extract? (becomes the `Prompt` schema)
- Do you have ground-truth answers for each document?

Wait for user to confirm dataset is ready before proceeding.

---

### Step 4: Submit Fine-Tuning Job

Once dataset is confirmed, submit the job:

```sql
SELECT SNOWFLAKE.CORTEX.FINETUNE(
    'CREATE',
    'db.schema.my_tuned_model',
    'arctic-extract',
    'snow://dataset/db.schema.my_dataset/versions/v1'
);
```

Save the returned job ID. Inform the user that training takes several minutes to complete.

---

### Step 5: Monitor Job Until Complete [WAIT]

Poll the job status with the user:

```sql
SELECT SNOWFLAKE.CORTEX.FINETUNE(
    'DESCRIBE',
    '<job_id>'
);
```

- `status = RUNNING` → continue waiting, check `progress` field
- `status = SUCCESS` → proceed to Step 6
- `status = FAILED` → load `references/job-management.md` troubleshooting section

---

### Step 6: Test the Fine-Tuned Model [WAIT]

Run a single-file test and compare against the base model. Load `references/inference.md` for the side-by-side comparison query.

Ask the user:
- **Accuracy improved** → proceed to Step 7 (batch / pipeline)
- **Not improved** → diagnose: Was training data varied enough? Were there enough examples? Consider retraining with more data.

---

### Step 7: Run at Scale [WAIT]

Load `references/inference.md` for batch processing patterns.

Offer post-processing options:
1. Done — I have the fine-tuned model, I'll use it manually
2. Run batch extraction now using the fine-tuned model
3. Set up a pipeline — load `../../ai-functions-pipeline-builder/references/pipeline.md` (Template A, using `model =>` parameter)

For the full extraction workflow with the fine-tuned model, see `../references/ai-extract.md`.

---

## Reference Files

| File | Use For |
|------|---------|
| `references/overview.md` | Prerequisites, limits, decision guide |
| `references/training-data.md` | Preparing the Dataset for training |
| `references/job-management.md` | Creating, monitoring, cancelling jobs |
| `references/inference.md` | Using the fine-tuned model in AI_EXTRACT |

---

## Stopping Points

| After Step | Wait For |
|------------|----------|
| Step 1 | Confirmation that fine-tuning is the right approach |
| Step 2 | Prerequisites confirmed |
| Step 3 | Training dataset ready |
| Step 5 | Job reaches SUCCESS or FAILED |
| Step 6 | Single-file test result evaluated |
| Step 7 | Post-processing choice |
