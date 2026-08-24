<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Bring your own Model Verified Model Catalog

> **Status: populated (`text-generation` and text-only use of `image-text-to-text`).** Last synced from the `VERIFIED_MODELS_CATALOG` source-of-truth on **2026-05-20**.
>
> CAIFS Bring your own Model input scope is centralized in `../../byom/SKILL.md` Hard Rules: Bring your own Model over `AI_COMPLETE('<service>', ...)` supports text input only today. This catalog may include `image-text-to-text` model families, but they are allowed only for text-only prompts/outputs. Entries for other task types in the source catalog (`summarization`, `text-classification`, `token-classification`, `fill-mask`, `table-question-answering`, `audio-text-to-text`) are **not** surfaced through this workflow until Bring your own Model expands beyond generation-style models.
>
> Re-sync this file from `VERIFIED_MODELS_CATALOG` whenever the source catalog changes. Do not edit individual entries in isolation; mirror the source.

Reference for the verified Hugging Face model list used by CAIFS Bring your own Model shortlisting (Step 3 of `../../byom/SKILL.md`).

## Usage

Load this file during Bring your own Model shortlisting. If the **Verified Models** section below is empty or only shows `_None yet._`, treat the catalog as **unpopulated** and follow the unpopulated-catalog fallback in `../../byom/SKILL.md` Step 3 (tell the user, fall back to Cortex model selection, skip the rest of Bring your own Model). Do not ask the user or owning team to dictate models in chat — that produces unverified recommendations.

These Verified Models are also listed in the standard model picker: `../model_selection.md` shows them as a separate **Bring your own Model — Hugging Face / open source (research preview)** section under "See all models", alongside the hosted families (no separate gateway). Selecting one enters the onboarding flow in `../../byom/SKILL.md` rather than being called directly.

## Catalog Fields (source-of-truth shape)

Each entry mirrors `VERIFIED_MODELS_CATALOG`:

- `hf_handle`: Hugging Face repo identifier; passed to Model Registry import and used as the served model name.
- `tasks`: Hugging Face task tags. CAIFS Bring your own Model surfaces entries that include `text-generation` or `image-text-to-text`, subject to the centralized Bring your own Model text-input scope in `../../byom/SKILL.md`.
- `token_required`: `true` if the Hugging Face repo is gated and requires a HF access token (configured by the user as a Snowflake secret per `../../byom/SKILL.md` Step 4).
- `trust_remote_code`: `true` if the model needs `--trust-remote-code` at vLLM startup. **All current text-generation entries: `false`.**
- `additional_pip_requirements`: extra Python deps for vLLM startup. **All current text-generation entries: `[]`.**
- `max_batch_rows`: per-call row batch cap. All current text-generation entries: `50`.
- `vllm_engine_args`: per-GPU-class vLLM startup flags. Always includes `default`. May also include `GPU_NV_S` (small), `GPU_NV_M` (medium), and/or `GPU_NV_L` (large) overrides. Use the override that matches the user's compute pool instance family; fall back to `default` if no class-specific entry exists.

## Selection Guidance

Match a candidate to the user's GPU compute pool and task shape:

- Use the size tiers below to align model parameter count with pool instance class.
- Prefer entries with a `vllm_engine_args` override for the user's exact GPU class — `default` works but is conservative on `--max-model-len`.
- If `token_required: true`, confirm the user has (or is willing to configure) a Hugging Face token as a Snowflake secret before proposing the model.
- Prefer **Instruct** variants for general task work; **Base** variants are for users who explicitly want pre-instruction-tuning behavior.
- `image-text-to-text` models such as Gemma 4, Qwen3-VL, and Kimi-K2.5 may be proposed only under the centralized Bring your own Model text-input scope in `../../byom/SKILL.md`.
- If no catalog entry clearly matches, continue with Cortex models or ask for human review. Do not recommend arbitrary Hugging Face models as verified — the catalog above is the only source of "verified" status.

## Verified Models

### Sub-2B (fits `GPU_NV_S`)

| `hf_handle` | Token required | `default` max_model_len | GPU class overrides |
|---|---|---|---|
| `baidu/ERNIE-4.5-0.3B-PT` | no | 4096 | — |
| `google/gemma-3-1b-it` | **yes** | 4096 | `GPU_NV_S`: 2048 |
| `Qwen/Qwen3-1.7B` | no | 4096 | — |
| `microsoft/Phi-4-mini-instruct` | no | 4096 | `GPU_NV_S`: 2048 |

### 4–9B (fits typical default GPU; some have `GPU_NV_S`/`GPU_NV_L` tuning)

| `hf_handle` | Token required | `default` max_model_len | GPU class overrides |
|---|---|---|---|
| `google/gemma-3-4b-it` | **yes** | 4096 | `GPU_NV_S`: 2048 |
| `Qwen/Qwen3-4B-Instruct-2507` | no | 4096 | — |
| `mistralai/Mistral-7B-Instruct-v0.3` | no | 4096 | `GPU_NV_S`: 2048; `GPU_NV_L`: 8192 + chunked prefill |
| `humain-ai/ALLaM-7B-Instruct-preview` | no | 4096 | — |
| `meta-llama/Llama-3.1-8B-Instruct` | **yes** | 4096 | `GPU_NV_S`: 2048; `GPU_NV_L`: 8192 + chunked prefill |
| `deepseek-ai/DeepSeek-R1-Distill-Llama-8B` | no | 4096 | `GPU_NV_S`: 2048; `GPU_NV_L`: 8192 + chunked prefill |
| `Qwen/Qwen3-8B` | no | 4096 | `GPU_NV_S`: 2048; `GPU_NV_L`: 8192 + chunked prefill |
| `Qwen/Qwen3-8B-Base` | no | 4096 | — |
| `swiss-ai/Apertus-8B-Instruct-2509` | no | 4096 | — |
| `nvidia/NVIDIA-Nemotron-Nano-9B-v2` | no | 4096 | — |

### 20–35B (recommend `GPU_NV_M` or larger)

| `hf_handle` | Token required | `default` max_model_len | GPU class overrides |
|---|---|---|---|
| `openai/gpt-oss-20b` | no | 8192 | `GPU_NV_M`: 4096; `GPU_NV_L`: 16384 + chunked prefill |
| `baidu/ERNIE-4.5-21B-A3B-Thinking` | no | 8192 | — |
| `Qwen/Qwen3-30B-A3B-Instruct-2507` | no | 8192 | — |
| `Qwen/Qwen3-32B` | no | 8192 | `GPU_NV_M`: 4096; `GPU_NV_L`: 16384 + chunked prefill |

### 70B+ (recommend `GPU_NV_L`)

| `hf_handle` | Token required | `default` max_model_len | GPU class overrides |
|---|---|---|---|
| `meta-llama/Llama-3.3-70B-Instruct` | **yes** | 8192 | `GPU_NV_M`: 4096; `GPU_NV_L`: 16384 + chunked prefill |
| `openai/gpt-oss-120b` | no | 8192 | `GPU_NV_L`: 16384 + chunked prefill |
| `Qwen/Qwen3-235B-A22B-Instruct-2507` | no | 8192 | `GPU_NV_L`: 16384 + chunked prefill |
| `deepseek-ai/DeepSeek-V3.1` | no | 8192 | `GPU_NV_L`: 16384 + chunked prefill |
| `deepseek-ai/DeepSeek-V3.1-Base` | no | 8192 | `GPU_NV_L`: 16384 + chunked prefill |
| `moonshotai/Kimi-K2-Thinking` | no | 8192 | `GPU_NV_L`: 16384 + chunked prefill |

### Image-text-to-text models usable for text-only Bring your own Model

Use these models only for text prompts/text outputs in CAIFS Bring your own Model. The model task may be `image-text-to-text`, but the image-input capability is out of scope for this workflow today.

| Model/family | HF task | Token required | Text-only Bring your own Model guidance |
|---|---|---|---|
| Gemma 4 family, including `gemma-4-E4B` | `image-text-to-text` | verify per repo | Allowed for text-only prompts; do not reject solely because the task is `image-text-to-text`. |
| Qwen3-VL family | `image-text-to-text` | verify per repo | Allowed for text-only prompts; do not use image inputs through CAIFS Bring your own Model. |
| Kimi-K2.5 family | `image-text-to-text` | verify per repo | Allowed for text-only prompts; do not use image inputs through CAIFS Bring your own Model. |

## Out of Scope

The source-of-truth catalog also lists models/tasks CAIFS Bring your own Model does **not** currently surface — `audio-text-to-text` (Qwen2-Audio), `summarization` (BART-CNN), `text-classification`, `token-classification`, `fill-mask`, and `table-question-answering`. For `image-text-to-text`, only the image-input portion is out of scope; text-only usage is allowed as described above. Do not recommend unsupported task families through this workflow.
