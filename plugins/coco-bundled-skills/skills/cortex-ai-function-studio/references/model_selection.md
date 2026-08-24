<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Model Selection Reference

## When to Load

**Always load this reference when model selection is needed.** This is the standard workflow for choosing a model — it dynamically queries the account's available models and presents smart recommendations.

Triggers: model selection step in any workflow, "see more models", "list models", "available models", "which models", "recommend a model".

**Bring your own Model (research preview):** Verified Hugging Face / open-source models from `../references/byom/model_catalog.md` are listed under **"See all models"** (Step 4) as their own section, next to the Cortex-hosted families — they're normal selectable options, with no separate gateway. Selecting one (or an explicit ask for a Hugging Face/open-source model, an SPCS service, or an existing model service) loads `../byom/SKILL.md`; such a model isn't directly callable until onboarded, so it skips the Step 5 test.

## Workflow

### Fast Path

**If a model has already been provided** (user specified it, or it was inherited from context like the function's baked-in model), skip the full selection workflow. Do **not** count workflow defaults such as `claude-sonnet-4-6` as "already provided" unless the user explicitly chose them:
1. Verify the model is available (Step 5)
2. If verification passes, use it immediately — no need to present options
3. If verification fails, fall back to the full selection flow below

If the user explicitly asks to see available models, do not take the Fast Path — run the full Step 1 → Step 4 workflow regardless of any default already collected.

### Step 1: Check Account Allowlist

```sql
SHOW PARAMETERS LIKE 'cortex_models_allowlist' IN ACCOUNT
```

**Based on the `value` column:**

- **`ALL`**: Proceed to Step 2 to query all available models
- **Comma-separated list** (e.g., `claude-haiku-4-5, claude-sonnet-4-5`): Parse and use only those specific models as the available set
- **`NONE`**: Inform user: "No Cortex models are available for this account. Please contact your administrator to enable model access." Then exit the Cortex AI Function Studio.

### Step 2: Query Available Models

```sql
SHOW MODELS IN SNOWFLAKE.MODELS
```

Intersect the results with the models defined in `src/models.json`. Only models that appear in **both** the `SHOW MODELS` output **and** `models.json` are considered available.

**IF `SHOW MODELS` fails or returns empty:**

1. In fallback mode, treat **all models in `src/models.json`** as potentially available
2. Present the 6 default models from Step 3 as-is (no substitution needed since we can't verify availability)
3. Continue to Step 4 with these 6 options

⚠️ **SAY THIS TO THE USER** (do not paraphrase):
> The `SNOWFLAKE.MODELS` registry doesn't exist in this account. I'll show you the standard model families. An ACCOUNTADMIN can run `CALL SNOWFLAKE.MODELS.CORTEX_BASE_MODELS_REFRESH();` to populate the full model list.

**IF user asks** "where is model X?" or "why can't I see certain models?":

⚠️ **SAY THIS TO THE USER** (do not paraphrase):
> An ACCOUNTADMIN can run `CALL SNOWFLAKE.MODELS.CORTEX_BASE_MODELS_REFRESH();` to populate the model registry with the latest available Cortex models.

### Step 3: Check Default Models Against Available Set

Build a curated default list of 6 hosted Cortex models ordered by cost (cheapest first). These cover a range of price/quality tradeoffs:

| # | Model | Tier |
|---|-------|------|
| 1 | `openai-gpt-5-nano` | Ultra-budget |
| 2 | `gemini-2.5-flash` | Budget |
| 3 | `claude-haiku-4-6` | Mid-range |
| 4 | `openai-gpt-5` | Premium |
| 5 | `claude-sonnet-4-6` | Premium |
| 6 | `claude-opus-4-7` | High-end |

**Including the current/inherited model:** If the calling workflow has a current model (e.g., the model baked into the function being evaluated or optimized) and it is NOT already in the default 6, insert it into the list at its appropriate cost position and remove the default model from the same tier to keep the list at 6 options. Mark it as "(current)" in the presentation.

For each default model, check whether it appears in the available set (from Step 2). If a model is **not** available:

1. Find the closest substitute by cost from `src/models.json` that **is** available (not necessarily the same family — pick by nearest input/output cost)
2. Use the substitute in the presented list
3. Inform the user of each substitution made (e.g., "`gemini-2.5-flash` is not available in your account; substituting `openai-gpt-5-mini` (similar cost tier).")

**Note:** If the calling workflow specifies that a strong/high-quality model is preferred (e.g., for synthetic data generation or reflection models), default to suggesting `claude-opus-4-7` and bias toward the most capable models when presenting options.

### Step 4: Present Options

Present using `ask_user_question`. The dialog UI may cap visible choices and add its own `Other...` choice, so the **final** explicit option must always be **"See all models"**.

**Format each option as:** `model-name` with a brief cost-tier note (e.g., "Ultra-budget", "Mid-range", "High-end").

**Hard guard:** never present a create/optimize model dialog that omits **"See all models"**. If the curated hosted list is too long to fit alongside it, trim hosted options (keep a cost/quality spread) — but always keep **"See all models"**.

Final option for create/optimize: **"See all models"** — "View the full list: Cortex-hosted models by family, plus verified Bring your own Model (Hugging Face / open source) models."

**After presenting options, inform the user:**

> Not all models may be available in every region or cloud provider. I'll run a quick test after you choose to make sure the model works in your account.

#### If user selects "See all models":

Present two labeled sections so the source is unambiguous:

1. **Cortex-hosted models** — all available models from `src/models.json`, grouped by family, each with a short size/speed/quality note.
2. **Bring your own Model — Hugging Face / open source (research preview)** — the verified models from `../references/byom/model_catalog.md`, grouped by its size tiers (Sub-2B, 4–9B, 20–35B, 70B+), each showing the `hf_handle` and whether a Hugging Face token is required.

All entries are directly selectable. If the user picks a Bring your own Model entry, load `../byom/SKILL.md` (it's onboarded, not called directly). If the catalog is empty/gated (`_None yet._`), show the section header and note the verified list isn't published yet.

### Step 5: Verify Model Availability

After the user selects a model (from Step 4, "See all models", or free-text input), run a lightweight test call to confirm the model is actually callable in this account's region and cloud provider:

**Bring your own Model / Hugging Face picks skip this check** — they aren't callable until onboarded. If the selection came from the Bring your own Model section (or an explicit BYOM/HF/SPCS ask), load `../byom/SKILL.md` instead; the smoke test runs there (Step 7) once the service is `READY`.

```sql
SELECT AI_COMPLETE('<selected_model>', 'test') AS test_response
```

**IF the call succeeds:** The model is confirmed available. Proceed with the selected model.

**IF the call fails** (e.g., model not deployed in this region, permission error, unsupported cloud provider):

⚠️ **SAY THIS TO THE USER** (do not paraphrase):
> The model `<selected_model>` is not available in your account's region or cloud provider. Let's pick a different model.

Then return to **Step 4** and re-present the model options, **excluding the failed model** from the list. Continue this loop until the user selects a model that passes verification.

**Note:** Keep a running list of failed models for the duration of the selection workflow so they are excluded from all subsequent presentations (Steps 3, 4, and "See all models").

## Model Validation & Auto-Correction

When user provides a model name (including via "Something else" free-text input):

1. **Validate**: Check if the model exists in the available models list (case-insensitive match)
2. **Auto-correct** common issues:
   - Case normalization: `LLAMA3.1-70B` → `llama3.1-70b`
   - Hyphen variations: `claude-3.5-sonnet` → `claude-3-5-sonnet`
   - Close matches: Suggest the closest valid model if user input is similar
3. **Confirm**: Show the user the resolved model name and get confirmation before proceeding
