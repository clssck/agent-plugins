---
name: model-registry-hugging-face-models
description: "Deploy Hugging Face models to Snowflake Model Registry. Use when: Logging Hugging Face models. Triggers: log model, model to snowflake, hugging face, huggingface, transformers pipeline."
parent_skill: model-registry
---

# Logging Hugging Face Models

The Model Registry has built-in support for any Hugging Face model loadable via `transformers.Pipeline`. There are two approaches to log a HF model, and the behavior is controlled by the `compute_pool_for_log` parameter on `TransformersPipeline`.

## ⚠️ CRITICAL: Environment Guide Check

**Before proceeding, check if you already have the environment guide (from `machine-learning/SKILL.md` → Step 0) in memory.** If you do NOT have it or are unsure, go back and load it now. The guide contains essential surface-specific instructions for session setup, code execution, and package management that you must follow.

## When to Use

- Deploying Hugging Face Transformers models to Snowflake
- User mentions: "log HuggingFace model", "deploy transformers", "ProsusAI/finbert", model IDs with forward slashes
- Working with `transformers.Pipeline` compatible models
- Need to choose between remote vs local model logging strategies for hugging face models

### Logging Modes

| Mode | `compute_pool_for_log` value | What happens | When to use |
|------|------------------------------|--------------|-------------|
| **Remote** (default) | A compute pool name string (defaults to system CPU pool) | Model metadata (ID, task, revision) is captured; actual weights are downloaded server-side via `SYSTEM$IMPORT_MODEL` during `log_model()` | Standard path — no local download needed, works without `huggingface_hub` installed |
| **Local (snapshot download)** | `None` | Model artifacts are downloaded locally via `huggingface_hub.snapshot_download()` then uploaded to registry | When you need to pre-filter files (`allow_patterns`/`ignore_patterns`), work offline, or avoid server-side download |

### Approach 1: Using `TransformersPipeline` (recommended)

Create a `TransformersPipeline` wrapper — the model is NOT loaded into memory. Only metadata is captured.

**Remote logging (default):**

```python
from snowflake.ml.model.models import huggingface
from snowflake.ml.registry import Registry

session = <SESSION_SETUP>
reg = Registry(session=session, database_name="<DATABASE>", schema_name="<SCHEMA>")

model = huggingface.TransformersPipeline(
    task="text-classification",
    model="ProsusAI/finbert",
)

mv = reg.log_model(
    model,
    model_name="<MODEL_NAME>",
    version_name="<VERSION>",
)
```

The default CPU compute pool is used to download the model server-side. To specify a different compute pool:

```python
model = huggingface.TransformersPipeline(
    task="text-classification",
    model="ProsusAI/finbert",
    compute_pool_for_log="MY_COMPUTE_POOL",
)
```

**Local logging (snapshot download):**

Pass `compute_pool_for_log=None` to download model files locally before uploading. Requires `huggingface_hub` to be installed.

**⚠️** For `text-generation` models logged locally, you must provide `signatures` — see [OpenAI Signatures for Text Generation](#openai-signatures-for-text-generation).

```python
from snowflake.ml.model.models import huggingface
from snowflake.ml.registry import Registry

session = <SESSION_SETUP>
reg = Registry(session=session, database_name="<DATABASE>", schema_name="<SCHEMA>")

model = huggingface.TransformersPipeline(
    task="text-classification",
    model="ProsusAI/finbert",
    compute_pool_for_log=None,
    allow_patterns=["*.safetensors", "*.json", "*.txt"],  # optional: filter downloaded files
    ignore_patterns=["*.bin", "*.msgpack"],                # optional: exclude files
)

mv = reg.log_model(
    model,
    model_name="<MODEL_NAME>",
    version_name="<VERSION>",
)
```

### Approach 2: Using `transformers.pipeline()` directly

Load the model fully into memory, then log it. The model artifacts are uploaded from local memory.

**⚠️** For `text-generation` models, you must provide `signatures` — see [OpenAI Signatures for Text Generation](#openai-signatures-for-text-generation).

```python
import transformers
from snowflake.ml.model.openai_signatures import OPENAI_CHAT_WITH_PARAMS_SIGNATURE
from snowflake.ml.registry import Registry

session = <SESSION_SETUP>
reg = Registry(session=session, database_name="<DATABASE>", schema_name="<SCHEMA>")

model = transformers.pipeline(
    task="text-generation",
    model="bigscience/bloom-560m",
    token="<HF_TOKEN>",
    return_full_text=False,
    max_new_tokens=100,
)

mv = reg.log_model(
    model,
    model_name="<MODEL_NAME>",
    version_name="<VERSION>",
    signatures=OPENAI_CHAT_WITH_PARAMS_SIGNATURE,
)
```

### `TransformersPipeline` Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `task` | Pipeline task (e.g., `"text-classification"`, `"text-generation"`, `"summarization"`). Inferred from model if `None`. | `None` |
| `model` | HuggingFace model identifier (e.g., `"ProsusAI/finbert"`). | `None` |
| `revision` | Branch, tag, or commit ID for the model version. | `None` |
| `token_or_secret` | HF token string or a fully qualified Snowflake secret name (e.g., `"DB.SCHEMA.MY_HF_SECRET"`). | `None` |
| `trust_remote_code` | Allow custom code from the HF Hub. Only set `True` for trusted repos. | `None` |
| `model_kwargs` | Extra keyword arguments passed to the model's `from_pretrained()`. | `None` |
| `compute_pool_for_log` | Compute pool name for remote logging. Set to `None` for local snapshot download. | Default CPU pool |
| `allow_patterns` | File patterns to include when downloading (local mode only). | `None` |
| `ignore_patterns` | File patterns to exclude when downloading (local mode only). | `None` |

### HF-specific `log_model()` Options

When calling `reg.log_model()` with a HF model, the `options` dict supports:

| Option key | Description | Default |
|------------|-------------|---------|
| `target_methods` | List of methods on the model. HF models use `__call__` by default. | `["__call__"]` |
| `cuda_version` | CUDA runtime version for GPU deployment. Set to `None` to disable GPU. | `"12.4"` |

The registry auto-infers `signatures` for most tasks (`fill-mask`, `question-answering`, `summarization`, `table-question-answering`, `text2text-generation`, `text-classification`, `sentiment-analysis`, `text-generation`, `token-classification`, `ner`, `translation`, `translation_xx_to_yy`, `zero-shot-classification`). For other tasks, provide `signatures` or `sample_input_data` explicitly.

**⚠️ `text-generation` and local logging:** When logging a HF model with task `text-generation` **locally** (via `compute_pool_for_log=None` or `transformers.pipeline()`), you **must** provide an OpenAI-compatible signature explicitly. Remote logging applies the signature automatically. See [OpenAI Signatures for Text Generation](#openai-signatures-for-text-generation).

`sample_input_data` is ignored for HF models — use `signatures` if the task is not in the auto-inferred list.

### OpenAI Signatures for Text Generation

The `snowflake.ml.model.openai_signatures` module provides pre-built signatures that emulate OpenAI chat completion behavior. These are **required** when logging `text-generation` HF models locally and **automatically applied** when logging remotely.

**Available signatures:**

| Signature | Description |
|-----------|-------------|
| `OPENAI_CHAT_SIGNATURE` | Default — content as structured parts (text, image, video, audio) |
| `OPENAI_CHAT_SIGNATURE_WITH_CONTENT_FORMAT_STRING` | Content as a plain string (most models support this) |
| `OPENAI_CHAT_WITH_PARAMS_SIGNATURE` | Default + inference params (`temperature`, `top_p`, etc.) as `ParamSpec` |
| `OPENAI_CHAT_WITH_PARAMS_SIGNATURE_WITH_CONTENT_FORMAT_STRING` | String content + inference params as `ParamSpec` |

**When to provide signatures:**

| Logging mode | Task `text-generation` | Other tasks |
|--------------|----------------------|-------------|
| **Remote** (`compute_pool_for_log` = compute pool name) | Auto-applied (uses `OPENAI_CHAT_WITH_PARAMS_SIGNATURE`) | Auto-inferred |
| **Local** (`compute_pool_for_log=None` or `transformers.pipeline()`) | **Must provide explicitly** | Auto-inferred |

**Example — local logging with OpenAI signature:**

```python
from snowflake.ml.model.models import huggingface
from snowflake.ml.model.openai_signatures import OPENAI_CHAT_WITH_PARAMS_SIGNATURE
from snowflake.ml.registry import Registry

session = <SESSION_SETUP>
reg = Registry(session=session, database_name="<DATABASE>", schema_name="<SCHEMA>")

model = huggingface.TransformersPipeline(
    task="text-generation",
    model="meta-llama/Llama-2-7b-chat-hf",
    compute_pool_for_log=None,
    token_or_secret="MY_DB.MY_SCHEMA.HF_TOKEN_SECRET", # required for gated models
)

mv = reg.log_model(
    model,
    model_name="<MODEL_NAME>",
    version_name="<VERSION>",
    signatures=OPENAI_CHAT_WITH_PARAMS_SIGNATURE,
)
```

### Authentication for Private/Gated Models

**Using a HF token directly for local download:**

```python
model = huggingface.TransformersPipeline(
    task="text-generation",
    model="meta-llama/Llama-2-7b-chat-hf",
    token_or_secret="hf_xxxYOUR_TOKEN_HERExxxx",
)
```

**Using a Snowflake secret (recommended for production):**

```python
model = huggingface.TransformersPipeline(
    task="text-generation",
    model="meta-llama/Llama-2-7b-chat-hf",
    token_or_secret="MY_DB.MY_SCHEMA.HF_TOKEN_SECRET",
)
```

### External Access for Snowflake Notebooks

When downloading HF models from a Snowflake Notebook, attach an external access integration allowing egress to HuggingFace hosts:

```sql
CREATE NETWORK RULE huggingface_network_rule
TYPE = HOST_PORT
VALUE_LIST = (
    'huggingface.co',
    'hub-ci.huggingface.co',
    'cdn-lfs-us-1.hf.co',
    'cdn-lfs-eu-1.hf.co',
    'cdn-lfs.hf.co',
    'transfer.xethub.hf.co',
    'cas-server.xethub.hf.co',
    'cas-bridge.xethub.hf.co'
)
MODE = EGRESS;

CREATE EXTERNAL ACCESS INTEGRATION huggingface_access_integration
ALLOWED_NETWORK_RULES = (huggingface_network_rule)
ENABLED = true;
```

Attach this integration to your Notebook before running model download code.

## Troubleshooting

- Many HF models are large — use a Snowpark-optimized warehouse.
- Snowflake warehouses do not have GPUs. Use CPU-optimized models for warehouse inference, or deploy via SPCS for GPU support.
- Task names are **case-sensitive** (e.g., `"text-classification"`, not `"Text-Classification"`).

## Stopping Points

- Before `log_model()` - confirm model name, version, and logging mode with user
- If gated model detected (e.g., Llama) - verify authentication is configured
- After logging - wait before proceeding to inference unless user explicitly requests it

## Output

- Model logged to Snowflake Model Registry
- Model version object (`ModelVersion`) ready for deployment
- Model accessible via `reg.get_model("<MODEL_NAME>").version("<VERSION>")`
