---
name: batch-inference-template
description: "Batch inference with multimodal LLMs using OpenAI chat message format. Stage paths in messages are auto-resolved. Use for Qwen-VL, TinyLlama, and other vLLM-based chat models."
parent_skill: batch-inference-jobs
---

# Batch Inference Jobs: Chat Models

Run batch inference on multimodal LLMs using OpenAI-style chat messages. This approach uses a `MESSAGES` column with structured conversation data, and stage paths embedded in messages are automatically resolved.

## ⚠️ CRITICAL: Environment Guide Check

**Before proceeding, check if you already have the environment guide (from `machine-learning/SKILL.md` → Step 0) in memory.** If you do NOT have it or are unsure, go back and load it now. The guide contains essential surface-specific instructions for session setup, code execution, and package management that you must follow.

---

## When to Use

- Model uses OpenAI chat completion signature
- Using vLLM-based multimodal LLMs (Qwen-VL, LLaVA, TinyLlama, MedGemma)
- Input is structured as conversation messages
- You want automatic resolution of stage paths in message content

## Key Advantage: Auto Stage Path Resolution

When using the OpenAI message format, stage paths inside `image_url.url`, `video_url.url`, or `input_audio.data` fields are **automatically detected and resolved**—no `column_handling` configuration needed. This works for internal stages (any encryption) and external stages (AWS S3 with SSE only); see `../non-template/SKILL.md` → External Stages for the supported configurations.

## Step 1: Check Model Signature

**⚠️ CRITICAL:** Before building the input DataFrame, always check the model's function signature to determine how parameters should be passed.

```sql
-- First verify the model exists
SHOW MODELS LIKE '<MODEL_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>;

-- Then get version/signature details (only run after confirming model exists above — errors if model not found)
SHOW VERSIONS IN MODEL <DATABASE>.<SCHEMA>.<MODEL_NAME>;
```

Look at the `signatures` section in the `model_spec` output. Pay attention to:

1. **`inputs`** - These are DataFrame columns (e.g., `messages`, `temperature`, `max_completion_tokens`)
2. **`params`** - These are passed via `InputSpec(params={...})`

**Example signature analysis:**

```yaml
signatures:
  __call__:
    inputs:
    - name: messages
      ...
    - name: temperature
      type: DOUBLE
    - name: max_completion_tokens
      type: INT64
    ...
    params: []  # Empty = no InputSpec params
```

**Decision logic:**

| Signature | How to Pass Parameters |
|-----------|----------------------|
| Parameters in `inputs`, `params: []` empty | Add as DataFrame columns |
| Parameters in `params` list | Use `InputSpec(params={...})` |


## Message Format

Messages follow the OpenAI chat completion format:

```python
messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What is the capital of France?"},
]
```

For multimodal content, use the structured content format:

```python
messages = [
    {"role": "system", "content": [{"type": "text", "text": "You are an image analyzer."}]},
    {
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe this image."},
            {
                "type": "image_url",
                "image_url": {
                    "url": "@DB.SCHEMA.STAGE/image.jpg", 
                },
            },
        ],
    },
]
```

## Complete Example: Text-Only Chat

```python
import json
from snowflake.snowpark import Session
from snowflake.ml.registry import Registry
from snowflake.ml.model.batch import JobSpec, OutputSpec, SaveMode, InputSpec

session = Session.builder.config("connection_name", "<CONNECTION>").create()
reg = Registry(session=session)
mv = reg.get_model("<MODEL_NAME>").version("<VERSION>")

# Create messages for text-only chat
messages_list = [
    [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is the capital of France?"},
    ],
    [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain quantum computing in simple terms."},
    ],
]

# Create DataFrame with MESSAGES column (JSON-encoded)
data = [json.dumps(m) for m in messages_list]
input_df = session.create_dataframe(data, schema=["MESSAGES"])

job = mv.run_batch(
    X=input_df,
    compute_pool="<GPU_COMPUTE_POOL>",
    output_spec=OutputSpec(
        stage_location="@<DATABASE>.<SCHEMA>.<STAGE>/output/",
        mode=SaveMode.OVERWRITE,
    ),
    input_spec=InputSpec(params={"temperature": 0.7, "max_completion_tokens": 256}),
    job_spec=JobSpec(gpu_requests="1"),
)

job.wait()
```

## Complete Example: Multimodal Chat (Images)

For vision-language models, include image references in the messages.

```python
import json
from snowflake.ml.model.batch import JobSpec, OutputSpec, SaveMode, InputSpec
from snowflake.ml.model.inference_engine import InferenceEngine

# Stage path to your image
image_stage_path = "@<DATABASE>.<SCHEMA>.<STAGE>/images/cat.jpg"

messages_list = [
    [
        {"role": "system", "content": [{"type": "text", "text": "You are an expert image analyzer."}]},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image in 20 words or less."},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_stage_path,
                    },
                },
            ],
        },
    ],
]

data = [json.dumps(m) for m in messages_list]
input_df = session.create_dataframe(data, schema=["MESSAGES"])

job = mv.run_batch(
    X=input_df,
    compute_pool="<GPU_COMPUTE_POOL>",
    output_spec=OutputSpec(
        stage_location="@<DATABASE>.<SCHEMA>.<STAGE>/output/",
        mode=SaveMode.OVERWRITE,
    ),
    input_spec=InputSpec(params={"temperature": 0.0}),
    job_spec=JobSpec(gpu_requests="1"),
    inference_engine_options={
        "engine": InferenceEngine.VLLM,
        "engine_args_override": [
            "--max-model-len=7048",
            "--gpu-memory-utilization=0.9",
        ]
    }
)

job.wait()
```

## Processing Multiple Images

If the user provides image URLs or local images, upload them to a stage as the input for the batch inference jobs.

To process multiple images with the same prompt:

```python
import json
from snowflake.ml.utils.stage_file import list_stage_files

# Get list of image paths
image_files_df = list_stage_files(
    session,
    "@<DATABASE>.<SCHEMA>.<STAGE>/images",
    pattern=".*\\.jpg", # for jpg files, adjust as needed
    column_name="IMAGE_PATH"
)
image_paths = [row["IMAGE_PATH"] for row in image_files_df.collect()]

# Create messages for each image
messages_list = []
for image_path in image_paths:
    messages = [
        {"role": "system", "content": [{"type": "text", "text": "You are an expert image analyzer."}]},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image."},
                {"type": "image_url", "image_url": {"url": image_path}},
            ],
        },
    ]
    messages_list.append(messages)

data = [json.dumps(m) for m in messages_list]
input_df = session.create_dataframe(data, schema=["MESSAGES"])
```

## Inference Parameters

Pass model inference parameters via `InputSpec.params`:

```python
input_spec = InputSpec(
    params={
        "temperature": 0.7,
        "max_completion_tokens": 256,
        "top_p": 0.9,
    }
)
```

Common parameters for chat models:
- `temperature` - Sampling temperature (0.0 = deterministic)
- `max_completion_tokens` - Maximum tokens in response
- `top_p` - Nucleus sampling threshold
- `frequency_penalty` - Penalize repeated tokens
- `presence_penalty` - Penalize tokens already present

## vLLM Engine Options

For multimodal models, you may need to configure vLLM:

```python
from snowflake.ml.model.inference_engine import InferenceEngine

inference_engine_options = {
    "engine": InferenceEngine.VLLM,
    "engine_args_override": [
        "--max-model-len=7048",      # Context length
        "--gpu-memory-utilization=0.9",  # GPU memory usage
    ]
}
```

## Reading Output

Chat models return responses in OpenAI chat completion format:

```python
output_location = "@<DATABASE>.<SCHEMA>.<STAGE>/output/"
results_df = session.read.option("pattern", ".*\\.parquet").parquet(output_location)
results_df.show(1, max_width=200)

# Output columns: "MESSAGES", "id", "object", "created", "model", "choices", "usage"
#
# The "choices" column contains the assistant's response:
# [{"index": 0, "message": {"content": "...", "role": "assistant"}, "finish_reason": "stop"}]
```

To extract the response text:

```python
from snowflake.snowpark.functions import col, get

results_df.select(
    col('"MESSAGES"'),
    get(get(col('"choices"'), 0), "message")["content"].alias("response")
).show()
```

## Supported Content Types

The OpenAI message format supports:

| Content Type | Field | Example |
|--------------|-------|---------|
| Text | `type: "text"` | `{"type": "text", "text": "Hello"}` |
| Image | `type: "image_url"` | `{"type": "image_url", "image_url": {"url": "@STAGE/img.jpg"}}` |
| Video | `type: "video_url"` | `{"type": "video_url", "video_url": {"url": "@STAGE/vid.mp4"}}` |
| Audio | `type: "input_audio"` | `{"type": "input_audio", "input_audio": {"data": "@STAGE/audio.wav"}}` |

## Troubleshooting

**Model doesn't understand the image**
- Verify the model supports vision (e.g., Qwen-VL, LLaVA)
- Check that the stage path is correct and file exists
- Ensure the message format matches OpenAI's multimodal format

**Out of memory errors**
- Reduce `--max-model-len` in engine_args_override
- Increase `--gpu-memory-utilization` carefully
- Use a compute pool with more GPU memory

**Slow inference**
- Increase replicas in JobSpec for parallelism
- Use `JobSpec(replicas=N, gpu_requests="1")`

**JSON parsing errors**
- Ensure messages are properly JSON-encoded with `json.dumps()`
- Verify the message structure matches OpenAI format

## Output

- Batch inference job completed
- Parquet files with OpenAI chat completion format responses
- Output columns: `MESSAGES`, `id`, `object`, `created`, `model`, `choices`, `usage`
