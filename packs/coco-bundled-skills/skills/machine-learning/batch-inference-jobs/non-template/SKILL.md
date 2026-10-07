---
name: batch-inference-non-template
description: "Batch inference on media files (images, audio, video) using InputSpec for explicit file-to-bytes conversion. Use for Whisper, ViT, and custom image/audio models."
parent_skill: batch-inference-jobs
---

# Batch Inference Jobs: Media Files

Run batch inference on images, audio, video, and other binary files stored in Snowflake stages. This approach uses `InputSpec` with `column_handling` to explicitly convert stage file paths to raw bytes.

## ⚠️ CRITICAL: Environment Guide Check

**Before proceeding, check if you already have the environment guide (from `machine-learning/SKILL.md` → Step 0) in memory.** If you do NOT have it or are unsure, go back and load it now. The guide contains essential surface-specific instructions for session setup, code execution, and package management that you must follow.

---

## When to Use

- Model expects raw bytes as input (not chat messages)
- Using models like Whisper, ViT, ResNet, CLIP, custom image/audio models
- You need explicit control over the file-to-bytes conversion
- Model was logged with a signature expecting binary input columns

## The Problem: Stage Paths vs Model Signatures

Your input DataFrame contains **string paths** pointing to files on a stage:

```
┌─────────────────────────────────────────┐
│ IMAGE_PATH (string)                     │
├─────────────────────────────────────────┤
│ @MY_DB.MY_SCHEMA.IMAGES/cat.jpg         │
│ @MY_DB.MY_SCHEMA.IMAGES/dog.jpg         │
└─────────────────────────────────────────┘
```

But models expect **actual file contents** (raw bytes, tensors, etc.)—not path strings.

## The Solution: InputSpec with column_handling

The `InputSpec` with `column_handling` tells batch inference how to convert each column from stage paths to the format the model expects:

```python
from snowflake.ml.model.batch import InputSpec, InputFormat, FileEncoding

input_spec = InputSpec(
    column_handling={
        "IMAGE_PATH": {
            "input_format": InputFormat.FULL_STAGE_PATH,
            "convert_to": FileEncoding.RAW_BYTES,
        }
    }
)
```

**What happens at runtime:**
```
Stage Path String          →  InputSpec Conversion  →  Model Input
"@DB.SCHEMA.STAGE/cat.jpg" →  Read file from stage  →  b'\xff\xd8\xff\xe0...' (raw bytes)
```

## Step 1: Check Model Signature

**⚠️ CRITICAL:** Before configuring `column_handling`, always check the model's function signature to understand what input columns and types the model expects.

```sql
-- First verify the model exists
SHOW MODELS LIKE '<MODEL_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>;

-- Then get version/signature details (only run after confirming model exists above — errors if model not found)
SHOW VERSIONS IN MODEL <DATABASE>.<SCHEMA>.<MODEL_NAME>;
```

Look at the `signatures` section in the `model_spec` output. Pay attention to:

1. **Input column names** - Must match your DataFrame column names OR be mapped via `column_handling`
2. **Input types** - Determines what `FileEncoding` to use:
   - `BYTES` → Use `FileEncoding.RAW_BYTES`

**Example signature analysis:**

```yaml
signatures:
  predict:
    inputs:
    - name: image
      type: BYTES      # Expects raw bytes
    - name: prompt
      type: STRING     # Regular string column
    outputs:
    - name: text
      type: STRING
```

**Column name mapping:**

If your DataFrame column name differs from the model's expected input name, the `column_handling` key should match your **DataFrame column name**, and the conversion will feed into the model's expected input:

```python
# DataFrame has "IMAGE_PATH", model expects "image" input

# First rename column to match model signature
input_df = input_df.with_column_renamed("IMAGE_PATH", "IMAGE")

# Use DataFrame column name in column_handling
input_spec = InputSpec(
    column_handling={
        "IMAGE": {  # Matches the renamed DataFrame column and model input name
            "input_format": InputFormat.FULL_STAGE_PATH,
            "convert_to": FileEncoding.RAW_BYTES,
        }
    }
)
```

**Checking for additional parameters:**

Also check if the signature has `params`:

```yaml
signatures:
  predict:
    inputs:
    - name: audio
      type: BYTES
    params:
    - name: language
      type: STRING
    - name: task
      type: STRING
```

If `params` is not empty, pass those via `InputSpec(params={...})`:

```python
input_spec = InputSpec(
    column_handling={
        "AUDIO": {
            "input_format": InputFormat.FULL_STAGE_PATH,
            "convert_to": FileEncoding.RAW_BYTES,
        }
    },
    params={"language": "en", "task": "transcribe"}
)
```

## FileEncoding Options

| FileEncoding | Output Type | Use For |
|--------------|-------------|---------|
| `RAW_BYTES` | `bytes` | Most models (images, audio, binary files) |
| `BASE64` | `str` (base64 encoded) | Models expecting base64 strings |
| `BASE64_DATA_URL` | `str` (data URL format) | Models expecting `data:image/jpeg;base64,...` |

## Complete Example: Image Classification

```python
from snowflake.snowpark import Session
from snowflake.ml.registry import Registry
from snowflake.ml.model.batch import (
    JobSpec, OutputSpec, SaveMode,
    InputSpec, InputFormat, FileEncoding,
)
from snowflake.ml.utils.stage_file import list_stage_files

session = Session.builder.config("connection_name", "<CONNECTION>").create()
reg = Registry(session=session)
mv = reg.get_model("<MODEL_NAME>").version("<VERSION>")

# List image files from stage
input_df = list_stage_files(
    session,
    "@<DATABASE>.<SCHEMA>.<STAGE>/images",
    pattern=".*\\.jpg", # for jpg files, adjust as needed
    column_name="IMAGES"
)

output_location = "@<DATABASE>.<SCHEMA>.<STAGE>/output/"

job = mv.run_batch(
    X=input_df,
    compute_pool="<COMPUTE_POOL>",
    output_spec=OutputSpec(
        stage_location=output_location,
        mode=SaveMode.OVERWRITE,
    ),
    input_spec=InputSpec(
        column_handling={
            "IMAGES": {
                "input_format": InputFormat.FULL_STAGE_PATH,
                "convert_to": FileEncoding.RAW_BYTES,
            }
        }
    ),
)

job.wait()

# Read results
results_df = session.read.option("pattern", ".*\\.parquet").parquet(output_location)
results_df.show()
```

## Complete Example: Audio Transcription (Whisper)

```python
from snowflake.ml.model.batch import (
    OutputSpec, SaveMode,
    InputSpec, InputFormat, FileEncoding,
)
from snowflake.ml.utils.stage_file import list_stage_files

# List audio files from stage
input_df = list_stage_files(
    session,
    "@<DATABASE>.<SCHEMA>.<STAGE>/audio",
    pattern=".*\\.wav",
    column_name="AUDIO"
)

output_location = "@<DATABASE>.<SCHEMA>.<STAGE>/output/"

job = mv.run_batch(
    X=input_df,
    compute_pool="<GPU_COMPUTE_POOL>",
    output_spec=OutputSpec(
        stage_location=output_location,
        mode=SaveMode.OVERWRITE,
    ),
    input_spec=InputSpec(
        column_handling={
            "AUDIO": {
                "input_format": InputFormat.FULL_STAGE_PATH,
                "convert_to": FileEncoding.RAW_BYTES,
            }
        }
    ),
)

job.wait()

# Read transcription results
results_df = session.read.option("pattern", ".*\\.parquet").parquet(output_location)
results_df.show()
# Output includes "outputs" column with {"text": "transcribed text..."}
```

## Multiple File Columns

If your model takes multiple file inputs (e.g., image + audio), configure each column:

```python
input_spec = InputSpec(
    column_handling={
        "IMAGE_PATH": {
            "input_format": InputFormat.FULL_STAGE_PATH,
            "convert_to": FileEncoding.RAW_BYTES,
        },
        "AUDIO_PATH": {
            "input_format": InputFormat.FULL_STAGE_PATH,
            "convert_to": FileEncoding.RAW_BYTES,
        }
    }
)
```

## Mixed Columns (Files + Tabular)

You can combine file columns with regular tabular columns. Only specify file columns in `column_handling`—other columns pass through unchanged:

```python
# DataFrame with both file paths and metadata
input_df = session.create_dataframe([
    ["@STAGE/img1.jpg", "outdoor", 0.8],
    ["@STAGE/img2.jpg", "indoor", 0.6],
], schema=["IMAGE_PATH", "CATEGORY", "CONFIDENCE"])

# Only configure the file column
input_spec = InputSpec(
    column_handling={
        "IMAGE_PATH": {
            "input_format": InputFormat.FULL_STAGE_PATH,
            "convert_to": FileEncoding.RAW_BYTES,
        }
        # CATEGORY and CONFIDENCE pass through as-is
    }
)
```

## External Stages (AWS S3)

Batch inference accepts file paths from **external stages** (Snowflake stages backed by Amazon S3) as input. The `column_handling` API is identical to internal stages — same path syntax (`@DATABASE.SCHEMA.STAGE/path/file.ext`), same `InputFormat.FULL_STAGE_PATH` setting. No user-code changes are needed when the input rows point at an external stage instead of an internal one.

> **Supported configurations for input:**
> - **Internal stages** — any encryption (`SNOWFLAKE_SSE` or client-side encryption)
> - **External stages** — AWS S3 only, must use server-side encryption (SSE). Azure Blob and Google Cloud Storage are not supported.

### Mixed external + internal stages in one job

Input rows can reference different stages in the same DataFrame — some external, some internal. Each path is resolved independently at read time.

```python
input_df = session.create_dataframe([
    ["@MY_DB.ML.EXTERNAL_S3_STAGE/cat.jpg"],   # External (S3-backed)
    ["@MY_DB.ML.IMAGES/dog.jpg"],              # Internal
    ["@MY_DB.ML.OTHER_INTERNAL/bird.jpg"],     # Different internal stage
], schema=["IMAGE_PATH"])
```

### Prerequisites

External stages require a one-time admin setup (S3 storage integration + IAM permissions for the bucket). See the Snowflake docs:
- [CREATE STAGE — external stage parameters](https://docs.snowflake.com/en/sql-reference/sql/create-stage#external-stage-parameters)
- [Bulk loading from Amazon S3](https://docs.snowflake.com/en/user-guide/data-load-s3)

The role used by the batch inference job must have `USAGE` on the external stage.

### Output is internal-only

`OutputSpec(stage_location=...)` for batch inference results must be an **internal** stage; either server-side (`SNOWFLAKE_SSE`) or client-side encryption is supported. External stages are not supported for output. Mixed-stage inputs are still allowed even when the output is on an internal stage.

## Verifying Your Setup

Before running a large batch job, test with a small sample:

```python
# Test with 2-3 files first
test_df = input_df.limit(3)

test_job = mv.run_batch(
    X=test_df,
    compute_pool="<COMPUTE_POOL>",
    output_spec=OutputSpec(
        stage_location="@<DATABASE>.<SCHEMA>.<STAGE>/test/",
        mode=SaveMode.OVERWRITE,
    ),
    input_spec=input_spec,
)
test_job.wait()

# Check results
results = session.read.option("pattern", ".*\\.parquet").parquet("@<DATABASE>.<SCHEMA>.<STAGE>/test/")
results.show()
```

## Common Mistakes

| Mistake | Error | Fix |
|---------|-------|-----|
| Missing `@` prefix | `File not found` | Use `@DB.SCHEMA.STAGE/file.ext` |
| Column name mismatch | `KeyError` or silent failure | Ensure `column_handling` key matches DataFrame column exactly |
| Wrong InputFormat | `Invalid path format` | Use `FULL_STAGE_PATH` for complete paths |
| Forgetting InputSpec | Model receives string instead of bytes | Always include `input_spec` for file columns |

## Troubleshooting

**Job fails with "file not found"**
- Verify the stage path is correct
- Ensure paths include the `@` prefix

**Model receives wrong data type**
- Check that `column_handling` column name matches your DataFrame column exactly
- Verify the model expects `RAW_BYTES` vs `BASE64`

**Empty or incorrect results**
- Test with a single file first
- Check model's expected input signature

## Stopping Points

- ✋ After test job completes, verify results before running full batch

## Output

- Batch inference job completed
- Parquet files with predictions (original input columns + model output columns)
