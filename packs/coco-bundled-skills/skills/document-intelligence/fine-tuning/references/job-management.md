# Fine-Tuning Job Management

Create, monitor, and cancel arctic-extract fine-tuning jobs using `SNOWFLAKE.CORTEX.FINETUNE`.

---

## Create a Fine-Tuning Job

```sql
SELECT SNOWFLAKE.CORTEX.FINETUNE(
    'CREATE',
    'db.schema.my_tuned_model',          -- fully qualified name for the output model
    'arctic-extract',                     -- base model to fine-tune
    'snow://dataset/db.schema.my_dataset/versions/v1'  -- training dataset
);
```

With an optional validation dataset:

```sql
SELECT SNOWFLAKE.CORTEX.FINETUNE(
    'CREATE',
    'db.schema.my_tuned_model',
    'arctic-extract',
    'snow://dataset/db.schema.training_ds/versions/v1',
    'snow://dataset/db.schema.validation_ds/versions/v1'
);
```

Returns a job ID string (e.g. `ft_6556e15c-8f12-4d94-8cb0-87e6f2fd2299`). Save this to track the job.

> **Note:** The `options` parameter is supported for arctic-extract fine-tuning. Epochs are auto-determined but can be set between 2 to 10.

---

## Check Job Status

### By job ID

```sql
SELECT SNOWFLAKE.CORTEX.FINETUNE(
    'DESCRIBE',
    'ft_6556e15c-8f12-4d94-8cb0-87e6f2fd2299'
);
```

### Example output (SUCCESS)

```json
{
  "base_model": "arctic-extract",
  "created_on": 1717004388348,
  "finished_on": 1717004691577,
  "id": "ft_6556e15c-8f12-4d94-8cb0-87e6f2fd2299",
  "model": "mydb.myschema.my_tuned_model",
  "progress": 1.0,
  "status": "SUCCESS",
  "training_data": "snow://dataset/training_ds/versions/v1",
  "trained_tokens": 2670734,
  "training_result": {
    "validation_loss": 1.0138969421386719,
    "training_loss": 0.6477728401547047
  },
  "validation_data": "snow://dataset/validation_ds/versions/v1"
}
```

### Output fields explained

| Field | Description |
|-------|-------------|
| `status` | Current job status (see lifecycle below) |
| `progress` | Float 0.0 → 1.0 |
| `model` | Fully qualified name of the fine-tuned model object |
| `trained_tokens` | Total tokens consumed during training |
| `training_result.training_loss` | Final training loss (lower = better fit) |
| `training_result.validation_loss` | Final validation loss (lower = better generalization) |
| `created_on` / `finished_on` | Unix timestamps in milliseconds |

---

## List All Jobs

```sql
SELECT SNOWFLAKE.CORTEX.FINETUNE('SHOW');
```

Returns an array of job objects. Filter by status to find running or failed jobs.

---

## Job Status Lifecycle

```
PENDING → RUNNING → SUCCESS
                  ↘ FAILED
```

| Status | Meaning |
|--------|---------|
| `PENDING` | Job queued, not yet started |
| `RUNNING` | Training in progress; check `progress` field |
| `SUCCESS` | Model ready for inference |
| `FAILED` | Training failed; see troubleshooting below |
| `ERROR` | Training job encountered error; see jon status for details |
| `CANCELLED` | Training job cancelled by the user |


There are also ERROR and CANCELLED statuses.
Poll every few minutes until `status = SUCCESS`:

```sql
-- Re-run this until progress = 1.0 and status = SUCCESS
SELECT SNOWFLAKE.CORTEX.FINETUNE(
    'DESCRIBE',
    '<your_job_id>'
);
```

---

## Cancel a Job

```sql
SELECT SNOWFLAKE.CORTEX.FINETUNE(
    'CANCEL',
    'ft_6556e15c-8f12-4d94-8cb0-87e6f2fd2299'
);
```

Only jobs in `PENDING` or `RUNNING` state can be cancelled.

---

## Troubleshooting FAILED Jobs

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Job fails immediately | Dataset missing required columns (`File`, `Prompt`, `Response`) | Validate dataset — see `training-data.md` |
| Job fails with privilege error | Missing `CREATE MODEL` or `SNOWFLAKE.CORTEX_USER` role | Check access control in `overview.md` |
| Job fails mid-training | questions × total pages > 50,000 | Reduce document count or number of questions |
| `validation_loss` much higher than `training_loss` | Overfitting — too few varied examples | Add more documents with layout variation |
| Model created but accuracy not improved | Training data too homogeneous or too few examples | Add diverse examples; aim for 50+ documents |

---

## Next Step

Once `status = SUCCESS` → proceed to `inference.md` to use the fine-tuned model.
