---
name: cortex-ai-function-studio-byom
summary: "Research-preview BYOM onboarding for CAIFS: shortlist verified Hugging Face models, validate GPU compute, deploy SPCS inference services, and compare BYOM against Cortex models."
description: "Use when the user asks to bring their own model, use a Hugging Face/open-source/task-specific model, deploy a model service, use SPCS inference with AI_COMPLETE, compare BYOM cost/quality, or add BYOM as a research-preview model-selection option in Cortex AI Function Studio."
---
<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Bring your own Model (BYOM) Service

Research-preview workflow for bringing task-specific models into Cortex AI Function Studio through Snowpark Container Services (SPCS) model inference.

## When to Load

Load after `cortex-ai-function-studio/SKILL.md` when the user selects or asks about BYOM, Hugging Face models, open-source models, SPCS model services, or using an existing model service as a CAIFS model candidate.

## Product Intent

Use Bring your own Model when the workload is cost-sensitive, task-specific, and does not require frontier reasoning. CAIFS should use its existing strengths — measurable quality, prompt/function optimization, and Pareto frontier comparison — to build trust in smaller open-source models.

The user experience is:

1. Collect normal CAIFS function context: business goal, function purpose, input shape, output shape, metric, and labeled data.
2. If the user selects a verified Bring your own Model (Hugging Face / open source) model during model selection, inspect available GPU compute capacity.
3. Shortlist verified Hugging Face models that match the task and available GPU pool.
4. Optimize prompts/function bodies across selected Bring your own Model and Cortex model candidates.
5. Present cost/quality Pareto frontier.
6. If the user chooses a Bring your own Model candidate, help provision/import/deploy it as an SPCS inference service and wire it into the AI function.

## Hard Rules

- Treat Bring your own Model as research preview; say so in user-facing review blocks.
- Do not invent model support, image names, SHA digests, instance-family mappings, or system functions. Use account metadata and verified model references.
- Do not skip CAIFS evaluation/optimization. Bring your own Model value is proven by measured quality and cost, not by model name.
- Do not deploy or create compute pools/services until the user approves a review block.
- Do not ask for secrets in chat. If a Hugging Face token is needed, instruct the user to configure it as a Snowflake secret/integration or through the approved account flow.
- If the model is not already in Snowflake Model Registry, include an import step before service deployment. The import may be async and can take 10–20 minutes depending on model size (faster when a Hugging Face token secret is provided).
- **Bring your own Model input scope:** CAIFS Bring your own Model over `AI_COMPLETE('<service>', ...)` supports **text input only** today. Some verified Bring your own Model families have Hugging Face task `image-text-to-text` and may be used for text-only prompts/outputs, but do not claim or route image/file input support through Bring your own Model `AI_COMPLETE` yet. For image/file inputs, use the standard Cortex-hosted multimodal flow instead of Bring your own Model.
- Prefer the `AI_COMPLETE(<model>, <text|prompt>, [, <model_parameters>, <response_format>])` service-overload path for generation models. The service/gateway name occupies the existing `model` argument; object resolution should determine whether it is a service or first-party model.
- Expect SPCS service behavior to differ from first-party Cortex models in some edge cases: model-parameter validation, token accounting, chat templating, context-window validation, multimodal support, and long-running request behavior may be service-specific.

## Long-Running Operations — STOP Protocol

Several Bring your own Model steps initiate operations that run asynchronously in Snowflake and take minutes to tens of minutes. The agent does not poll or wait. For each one, you MUST:

1. Tell the user the operation has been initiated and how long it typically takes.
2. Tell the user the **agent will stop working** at this point — these run inside Snowflake, not in the agent.
3. Remind the user they can return anytime and ask the agent to check status (e.g., "is the model import done?", "has the service finished provisioning?"). The agent will run the appropriate status check and continue from where it left off.
4. **Stop entirely.** Do not poll, do not loop, do not advance to the next step in the same turn.

Use this user-facing template verbatim (substitute placeholders):

> ⚠️ **Long-running operation: {operation}**
>
> {operation} has been started. This typically takes **{duration}**, runs asynchronously in Snowflake, and **the agent will stop working here.**
>
> Come back anytime and ask me to check status (for example, "is the {operation} done yet?") — I'll run the status check and pick up from where we left off.

Operations covered by this protocol:

| Step | Operation                                  | Typical duration                       | Status-check command                                                                         |
|------|--------------------------------------------|----------------------------------------|----------------------------------------------------------------------------------------------|
| 2    | `CREATE COMPUTE POOL`                      | a few minutes                          | `DESCRIBE COMPUTE POOL {name}` (wait for `IDLE`/`ACTIVE`)                                    |
| 4    | Model Registry import                      | **10–20 minutes** (faster with HF token) | `SHOW MODELS IN SCHEMA {db}.{schema}` / Models UI                                            |
| 5    | `OPTIMIZE_AI_FUNCTION` (non-`ultra-light` budget) | minutes–hours                          | See `../references/async_status.md`                                                          |
| 5    | `EVALUATE_AI_FUNCTION_ASYNC`               | minutes                                | See `../references/async_status.md`                                                          |
| 6    | `CREATE SERVICE`                           | several minutes (image pull + model load) | `DESCRIBE SERVICE {name}` / `SYSTEM$GET_SERVICE_STATUS('{name}')` (wait for `READY`)         |

## Workflow

### Step 0: Prerequisites

First complete the parent skill prerequisites in `../references/prerequisites.md`. Then complete the Bring your own Model prerequisites in `prerequisites.md` (this folder) — these cover privileges and account features that are only needed for the research-preview Bring your own Model path and are intentionally **not** in the main prerequisites doc.

Collect or confirm:

- Target `database` and `schema`
- Function task description
- Input columns and output schema
- Metric and labeled train/test data, if comparing quality
- Whether the user wants to use an existing SPCS service or onboard a new Hugging Face model

If in Snowsight, also follow `../references/snowsight/core.md` for notebook/display behavior. Stored procedure and SQL execution still happens through the execution tool, not notebook cells.

### Step 1: Choose Bring your own Model Path

Ask only if not already clear:

```
How do you want to use Bring your own Model?
1. Existing service - I already have an SPCS inference service callable by AI_COMPLETE
2. New model - Help me import/deploy a Hugging Face model as an SPCS service
3. Compare first - Shortlist Bring your own Model candidates and compare them before deploying
```

Store as `byom_path`.

### Step 2: Inspect GPU Compute

Run account inspection before recommending deployable models:

```sql
SHOW COMPUTE POOLS;
```

Look for GPU instance families and usable pools. If no usable GPU pool exists:

- Ask whether the user wants help creating one.
- If not, abort Bring your own Model onboarding and continue with normal Cortex model selection.
- If yes, collect `compute_pool_name`, cloud/provider constraints, instance family, min/max nodes, and warehouse/role requirements, then show a review block before any `CREATE COMPUTE POOL`.
- After the user approves and `CREATE COMPUTE POOL` is issued, **follow the Long-Running Operations STOP Protocol** above. The pool typically takes a few minutes to reach `IDLE`/`ACTIVE`. Stop entirely; do not advance to Step 3 in the same turn. The user can return and ask the agent to run `DESCRIBE COMPUTE POOL {name}` to check readiness, then continue.

Instance families vary by cloud/provider. Do not hard-code a universal family map; use verified account metadata or a Bring your own Model catalog reference.

### Step 3: Shortlist Models

Use a verified model catalog if available. Start with `../references/byom/model_catalog.md`.

**If the catalog is unpopulated** (only the placeholder banner / "_None yet._" under Verified Models), do **not** ask the user or owning team to dictate model names in chat — any answer would be unverified. Instead:

1. Tell the user, verbatim:

   > Bring your own Model is research preview, and the verified model list isn't published yet. I'm falling back to Cortex model selection — you can revisit Bring your own Model once the catalog ships.

2. Hand off to `../references/model_selection.md` and continue with the standard Cortex model options.
3. Skip the rest of the Bring your own Model workflow (Steps 4–8). Do not provision compute pools, import models, or create services.

**If the catalog is populated**, shortlist based on:

- Task type: classification, extraction, routing, redaction, summarization, transformation, etc.
- Bring your own Model text-input scope from Hard Rules above; reject or reroute image/file input requests away from Bring your own Model even when the candidate model's Hugging Face task is `image-text-to-text`.
- Input/output lengths and structured-output requirements
- Available GPU memory and target concurrency
- Latency and throughput targets
- Licensing/commercial constraints
- Whether the model is already imported into Snowflake Model Registry
- Whether AI Function support is needed for `AI_COMPLETE` generation or `AI_EMBED` embeddings; other AI SQL functions may not support service model selection.

Present 3–6 candidates with a Cortex baseline. Include estimated tradeoffs but label estimates clearly until measured.

### Step 4: Model Registry Import

**First, auto-detect an existing token secret.** Before asking anything, check whether a Hugging Face token secret already exists in the target schema so you can skip the question entirely:

```sql
SHOW SECRETS LIKE 'huggingface_token' IN SCHEMA {database}.{schema};
```

If a matching secret is found, do **not** show the choice dialog below — tell the user you found it (by name), confirm they want to use it (default yes), and proceed with it as `token_secret_object`. Only fall through to the choice dialog when no token secret exists, the lookup isn't permitted, or the user wants a different/new secret.

**Required pre-import choice (when no existing secret was auto-detected) — ask about a Hugging Face token secret before starting the import.** Snowflake imports from Hugging Face may be rate limited, so unauthenticated `SYSTEM$IMPORT_MODEL` jobs can take a long time or appear stalled. Authenticated Hugging Face downloads use higher rate limits and finish noticeably faster. The import **works without a token**, but it can be super slow. Before kicking off any import job, STOP and ask the user to choose exactly one option. This question is mandatory even when the verified catalog says `token_required: false`; `token_required` means the repository is not gated, but an HF token can still speed up downloads and avoid rate limits.

**If `environment == snowsight`:** use `ask_user_question` to show a three-option dialog before the import review block. Do not replace this with a chat-only sentence and do not proceed directly to "Ready to import" until the user answers.

1. **Yes, I already have an HF token secret in Snowflake** — ask them to provide the fully-qualified secret name, then verify the object/privilege if tooling permits and add it to the import YAML as `token_secret_object`.
2. **Create a new secret from my Hugging Face token** — for users who have a Hugging Face token but no Snowflake secret yet. Point them to `https://huggingface.co/settings/tokens` to obtain a token, then have them run the `CREATE SECRET` statement below **themselves** (in their own SQL session, worksheet, or the notebook SQL cell), substituting their own token. Do **not** ask for or accept the raw token value in chat. After they confirm it ran, verify the secret exists if tooling permits (for example `SHOW SECRETS LIKE 'huggingface_token' IN SCHEMA {database}.{schema}` or `DESCRIBE SECRET {database}.{schema}.huggingface_token`), then add it to the import YAML as `token_secret_object` — identical to option 1 from that point on.
3. **Proceed without an HF token** — confirm they accept the slower unauthenticated download path, then render the import YAML without `token_secret_object`.

Do not present the final import approval block or start `SYSTEM$IMPORT_MODEL` until the user has made this choice. Do not collect raw Hugging Face token values in chat.

**Option 2 — `CREATE SECRET` template.** When the user chooses to create a new secret (they have a token but no secret yet), tell them they can obtain a Hugging Face token from `https://huggingface.co/settings/tokens`, then instruct them to run this themselves (substituting their own token) in their own SQL session, worksheet, or the notebook SQL cell described below:

```sql
CREATE OR REPLACE SECRET {database}.{schema}.huggingface_token
  TYPE = GENERIC_STRING
  SECRET_STRING = 'your_huggingface_token';
```

After they confirm it ran, verify the secret exists if tooling permits, then reference the secret name as `token_secret_object` when configuring the import / external access integration. If the user chooses to proceed without a token, proceed with an unauthenticated import and clearly tell them it will be slower.

**One-step setup — auth + egress together.** Creating the secret only configures authentication. If the account does not already allow Hugging Face egress for the import job (no approved `ALLOW_ALL_EGRESS` and no Hugging Face external access integration), offer the network rule + external access integration SQL from the **Hugging Face Rate Limit / Stalled Import Help** section below in the *same* guided step — so the user sets up the token secret and the egress integration in one pass instead of discovering the egress gap only after a failed import. Ask the user to run both statements themselves (or hand them to an account admin if they lack `CREATE NETWORK RULE` / `CREATE EXTERNAL ACCESS INTEGRATION`). The agent still never collects the raw token in chat.

#### Hugging Face Rate Limit / Stalled Import Help

If the user asks for help because the import is slow, stalled, rate limited by Hugging Face, or they want help creating an HF token secret, explain that there are two mitigations: provide an HF token secret for the system import, or use the notebook local import fallback so the notebook service downloads the model and logs it to Snowflake directly. The notebook local import still needs Hugging Face egress through an External Access Integration (EAI). Open/create the function notebook and add exactly these helper cells before retrying the import:

1. A markdown cell that explains:
   - Snowflake may currently be rate limited by Hugging Face during unauthenticated model downloads.
   - A Hugging Face token is recommended to speed up imports.
   - The user can create or copy a token from `https://huggingface.co/settings/tokens`.
   - If the system import remains stalled, the notebook local import fallback can mitigate the rate limit by downloading in the notebook service and logging the model directly.
   - The notebook service must have Hugging Face network access through an EAI: use `ALLOW_ALL_EGRESS` if the customer already has and is allowed to use it; otherwise create a narrow Hugging Face EAI.
   - The agent will not ask for or collect the raw token in chat.
2. A SQL cell with this ready-to-edit template:

   ```sql
   CREATE OR REPLACE SECRET {database}.{schema}.huggingface_token
     TYPE = GENERIC_STRING
     SECRET_STRING = '<paste_huggingface_token_here>';
   ```

3. If the customer does not already have an approved `ALLOW_ALL_EGRESS` EAI, add a second SQL cell with this narrow Hugging Face egress template. Ask the user to run it only if they have privileges to create network rules and external access integrations, or to send it to their account admin:

   ```sql
   CREATE OR REPLACE NETWORK RULE huggingface_network_rule
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
     MODE = EGRESS
     COMMENT = 'Network Rule for Hugging Face external access';

   CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION huggingface_access_integration
     ALLOWED_NETWORK_RULES = (huggingface_network_rule)
     ENABLED = TRUE;
   ```

After creating those cells, STOP and ask whether the user has run the SQL cell to create the secret and whether the notebook service has Hugging Face EAI access (`ALLOW_ALL_EGRESS` or `huggingface_access_integration`). Do not proceed until the user confirms. Once the user says yes, verify the secret exists and verify the EAI if tooling permits, then recreate/retry the import job with `token_secret_object: "{database}.{schema}.huggingface_token"` in the import YAML if the previous import was stalled or unauthenticated. If the system import still fails or the user chooses the notebook local import path, attach the verified EAI to the notebook service before running the notebook fallback cell.

If the chosen Hugging Face model is not already imported:

1. Explain that Snowflake must import/download the model into Model Registry before SPCS serving.
2. Prefer the SQL-driven import path when the account has the preview system function. Before executing, present a review block and wait for approval. Include an estimated time line exactly in this form:

   > Estimated time: 10–20 minutes (usually faster when an HF token secret is provided).

   Then read `../references/byom/import_model_yaml_template.yml`, render every placeholder with verified values, and execute the rendered YAML as a single string argument:

   ```sql
   USE {database}.{schema};

   SELECT SYSTEM$IMPORT_MODEL('<rendered_import_yaml_text_with_single_quotes_escaped>');
   ```

   `SYSTEM$IMPORT_MODEL` accepts YAML text, not a staged file path. The import launches a model-logging Snowflake job.
3. If the user chose the HF token secret path, add `token_secret_object` to the import YAML only after the fully-qualified secret identifier is provided and verified. If the user chose the no-token path, omit `token_secret_object` and remind them the import may be significantly slower.
4. If `SYSTEM$IMPORT_MODEL` fails, is unavailable, or is blocked, use the notebook-based Model Registry import fallback as a **backup path only** — never as the first option. Before running the fallback, confirm the notebook service has Hugging Face egress through either the customer's approved `ALLOW_ALL_EGRESS` EAI or the narrow `huggingface_access_integration` from the stalled-import helper flow above, and attach that EAI to the notebook service if it is not already attached. Then open/create the function notebook, add a Python cell that downloads the Hugging Face model inside the notebook kernel and uploads/logs it directly to Snowflake Model Registry, and **run that cell for the customer**. Do not merely create the notebook and tell the user to run it themselves.

   ```python
   from snowflake.ml.model.models import huggingface
   from snowflake.ml.model import target_platform
   from snowflake.ml.registry import Registry
   from snowflake.snowpark.context import get_active_session

   session = get_active_session()

   model = huggingface.TransformersPipeline(
       task="<task_type>",
       model="<model_name>",
       compute_pool_for_log=None,
   )

   registry = Registry(
       session=session,
       database_name="<database>",
       schema_name="<schema>",
   )

   mv = registry.log_model(
       model=model,
       model_name="<model_name>",
       target_platforms=target_platform.SNOWPARK_CONTAINER_SERVICES_ONLY,
   )

   mv
   ```

   Replace `<task_type>` with the verified Hugging Face task for the selected model (for example, `image-text-to-text` only when that is the selected model's actual task), and replace `<model_name>`, `<database>`, and `<schema>` with verified values. Do not hard-code `image-text-to-text` for text-generation models. This fallback uses a notebook for execution by design; it is the only Bring your own Model import exception to the normal notebook display-only rule.

   **Run-and-continue requirement:** After adding the fallback Python cell, call `notebook_action(action="run_notebook", run_type="single", cell_id=<fallback_cell_id>)` or the equivalent Snowsight notebook run action to execute it. Wait for the cell result. If it succeeds and returns a `ModelVersion`/`mv` object or otherwise confirms `registry.log_model` completed, continue immediately to Step 6 (Provision Service) in the same workflow. If the cell is still running or the notebook tool reports an asynchronous run state, report the run status and ask the user to come back when it completes. If the cell fails, show the error and fix retryable notebook/EAI/Hugging Face issues; do not proceed to service deployment until the model is imported.
5. If both import paths fail with Hugging Face network errors such as `ConnectError: [Errno -2] Name or service not known`, report that the model-logging job/kernel cannot reach Hugging Face. Ask an account admin to enable model-build/model-logging egress (for example with the account's approved egress parameter or external access integration) before retrying. Do not claim the YAML or notebook code is invalid when the failure is a network/egress error.
6. Treat the system import as async/long-running — **follow the Long-Running Operations STOP Protocol** above. Tell the user the import typically takes **10–20 minutes (usually faster when an HF token secret is provided)**, can take longer without an HF token, and may be slower when Snowflake is rate limited by Hugging Face. Tell them the agent will stop working at this point and that they can return anytime and ask the agent to check import status (`SHOW MODELS IN SCHEMA {db}.{schema}` or the Models UI). Stop entirely for the system import path unless the user explicitly asks you to babysit the long-running job. **Exception:** for the notebook fallback path, the agent must run the notebook cell and, when it succeeds, continue to Step 6 instead of stopping after notebook creation.

### Step 5: Prompt/Function Optimization

Run normal CAIFS optimize flow with Bring your own Model candidates included as model candidates where supported.

- Load `../optimize/SKILL.md`.
- Include the current Cortex model and selected Bring your own Model candidates in the model comparison.
- If optimizing an existing function that already uses a Bring your own Model/SPCS service model, always include that existing Bring your own Model service in the optimizer `models` array. Hosted Cortex models may be added for comparison, but they must not replace or omit the Bring your own Model candidate unless the user explicitly asks to exclude Bring your own Model.
- Pass all selected models in one optimization call when using the CAIFS optimizer.
- Prefer `ultra-light` or `light` budget for first pass.
- For non-`ultra-light` budgets, optimize runs as an async Task (and `EVALUATE_AI_FUNCTION_ASYNC` runs evaluations as Tasks too) — **follow the Long-Running Operations STOP Protocol** above. Tell the user the agent will stop working here, and that they can return anytime and ask the agent to check the run status via `../references/async_status.md`. Stop entirely; do not advance in the same turn.
- Load `pricing/SKILL.md` before presenting Bring your own Model cost, relative cost, or Pareto frontier results. Bring your own Model is priced by measured SPCS throughput and compute-pool credit/hour rate, not Cortex-hosted token rates from `models.json`.
- Present Pareto frontier: quality metric, latency/throughput, estimated or measured cost, and operational complexity.
- Include service-capacity caveats: SPCS capacity, autoscaling behavior, and per-row request pacing can dominate latency/throughput results.
- When presenting Pareto frontier results that include Bring your own Model/SPCS service models, note that Bring your own Model `estimated_cost` is derived from measured SPCS throughput (see `pricing/SKILL.md`), not from Cortex-hosted token rates in `models.json`.

If Bring your own Model candidates cannot be passed directly to the optimizer yet, create a thin wrapper function/service candidate and evaluate it with `../evaluate/SKILL.md`; do not pretend it was optimized by unsupported machinery.

### Step 6: Provision Service

Enter this step immediately after either the system import is confirmed complete or the notebook fallback import cell succeeds. Do not ask the user to manually resume after a successful notebook fallback import.

Before provisioning, show a single review block and stop:

```
Ready to provision Bring your own Model service?

Research preview: Bring your own Model SPCS model service
Model: {hf_model_or_registry_model}
Service name: {database}.{schema}.{service_name}
Compute pool: {compute_pool}
Min/max instances: {min_instances}/{max_instances}
GPU/memory target: {gpu_count}, {memory}
Endpoint: /ai_complete through model inference proxy
External access/secret: {integration_or_secret_summary}
Autoscaling: {queue_fill_ratio_target}, {gpu_utilization_target}
Validation: smoke test with AI_COMPLETE, then CAIFS evaluate/optimize
```

Proceed only after approval.

Prefer SQL deployment from a staged manifest when `SYSTEM$DEPLOY_MODEL` is available. Read `../references/byom/deploy_model_yaml_template.yml`, render every placeholder with verified values, upload the rendered file to a stage, then execute:

```sql
USE {database}.{schema};
CREATE STAGE IF NOT EXISTS {deploy_stage};
CREATE IMAGE REPOSITORY IF NOT EXISTS {image_repository};

-- Upload rendered deploy_model.yml to @{deploy_stage}/spec/deploy_model.yml using PUT, SnowSQL, or Snowflake CLI.
CALL SYSTEM$DEPLOY_MODEL('@{deploy_stage}/spec/deploy_model.yml');
```

`SYSTEM$DEPLOY_MODEL` takes exactly one argument: the staged YAML manifest path. Do not call `SYSTEM$DEPLOY_MODEL()` with no args, separate positional args, or named params. If the call returns compute-pool errors such as `Insufficient GPU quota or a non-gpu Compute pool` or `incompatible compute pool type`, report the pool/type/quota issue and choose or provision a compatible GPU/model-serving pool before retrying.

Use `../references/byom/spcs_service_template.md` only when deploying a direct prebuilt model image with raw `CREATE SERVICE` rather than Model Registry deployment. Replace placeholders only with verified image digests, resource requests, and account values.

After `CREATE SERVICE` is issued, **follow the Long-Running Operations STOP Protocol** above. The service must pull the vLLM image, load the model into GPU memory, and pass its readiness probe — this typically takes **several minutes**. Stop entirely; do not run the smoke test in Step 7 in the same turn. The user can return and ask the agent to run `DESCRIBE SERVICE {database}.{schema}.{service_name}` or `SELECT SYSTEM$GET_SERVICE_STATUS('{database}.{schema}.{service_name}')` to check readiness, and the agent will continue with Step 7 once the service is `READY`.

### Step 7: Smoke Test

After service creation/resume succeeds, execute the required Bring your own Model/SPCS-in-AI-SQL session setup directly, then test. Do not precheck whether this session parameter is available; if the `ALTER SESSION` fails, stop and report the exact parameter/error. The service function resource keyword and model inference proxy container URL are bundled now and do not need to be set manually.

```sql
ALTER SESSION SET ENABLE_SPCS_SERVICE_FUNCTIONS_IN_AISQL = TRUE;

SELECT AI_COMPLETE(
  '{database}.{schema}.{service_name}',
  'Say hello in one short sentence.'
) AS response;
```

If the session parameter fails, stop and report the exact failed parameter/error. Tell the user they lack permission to alter this session parameter, or the account does not have the Bring your own Model/SPCS-in-AI-SQL preview enabled, and they should contact their account admin if they are interested in using Bring your own Model.

After the smoke test succeeds, continue to Step 8. Do not stop at the smoke test if the service is callable.

### Step 8: Wire Into CAIFS

Once smoke test passes:

- Use the service identifier as the model argument where `AI_COMPLETE` accepts SPCS services.
- Keep the function body close to normal CAIFS output: `AI_COMPLETE('{database}.{schema}.{service_name}', <prompt>, <model_parameters>, <response_format>)` where supported.
- Create or update the AI function using `../create/SKILL.md` if needed.
- Evaluate on labeled data using `../evaluate/SKILL.md`.
- Compare against Cortex candidates using `../optimize/SKILL.md` or evaluation tables.

After the Bring your own Model service is wired into the AI function or confirmed as the function's model, ask the user what they want to do next with `ask_user_question`: **Evaluate**, **Optimize**, or **Done**. If the user selects Evaluate, load `../evaluate/SKILL.md`; if Optimize, load `../optimize/SKILL.md` and ensure the Bring your own Model service model remains included in the optimization candidate list.

## Stopping Points

The agent stops entirely (does not poll) at every long-running operation. The user resumes by asking the agent to check status:

- ✋ Step 2: After `CREATE COMPUTE POOL`. Resume by asking the agent to check `DESCRIBE COMPUTE POOL {name}` for `IDLE`/`ACTIVE`.
- ✋ Step 4: After Model Registry import is initiated (10–20 min; usually faster with HF token). Resume by asking the agent to check `SHOW MODELS IN SCHEMA {db}.{schema}` / Models UI.
- ✋ Step 5: After a non-`ultra-light` optimize Task or `EVALUATE_AI_FUNCTION_ASYNC` Task is created. Resume via `../references/async_status.md`.
- ✋ Step 6: After `CREATE SERVICE`. Resume by asking the agent to check `DESCRIBE SERVICE {name}` or `SYSTEM$GET_SERVICE_STATUS('{name}')` for `READY`.
- ✋ Each review block (Step 2 compute-pool review, Step 6 service review) — agent waits for explicit user approval before issuing the create.

## Output

End with:

- Bring your own Model service identifier or import job status
- Smoke-test result status
- Evaluation/optimization status and Pareto recommendation
- Next action: evaluate, optimize, deploy winner, or continue with Cortex-only models
