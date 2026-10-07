<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Bring your own Model Prerequisites

Bring your own Model prerequisites for the research-preview path in Cortex AI Function Studio. These are intentionally **not** in `../references/prerequisites.md` — most CAIFS users will never hit this path, and surfacing SPCS/compute-pool checks for every session would add noise.

## When to Load

Load from `byom/SKILL.md` Step 0, after the parent `../references/prerequisites.md` has been completed. Also load when the user asks "what do I need for BYOM", "BYOM setup", "BYOM permissions", or hits a privilege/feature error during the Bring your own Model workflow.

## Scope

This doc covers what's needed to:

- Inspect / create a GPU compute pool
- Import a Hugging Face model into Snowflake Model Registry
- Create an SPCS inference service
- Call the service through `AI_COMPLETE('<db>.<schema>.<service>', …)`

If any check fails, **stop the Bring your own Model workflow** and report the missing item to the user. Do not work around missing privileges or feature flags.

## Required

### Silent Bring your own Model Prerequisite Checks

**Quiet on success**: run the checks below in a **single parallel batch**. Do NOT narrate beforehand. If everything passes, do NOT display individual results — only mention Bring your own Model prerequisites if something **fails**.

Run these in parallel (single tool-call batch), except where a check depends on the selected Bring your own Model path:

1. **GPU compute pool visibility**:
   ```sql
   SHOW COMPUTE POOLS;
   ```
   The role from `CURRENT_ROLE()` must see at least one pool with a GPU instance family. If none exist, the workflow may need `CREATE COMPUTE POOL ON ACCOUNT` to create one — capture this so Step 2 of `byom/SKILL.md` can offer to create one (with user approval).

2. **SPCS service privilege posture**:
   Do **not** run `SHOW GRANTS TO ROLE` as a prerequisite. Grant introspection can be slow in large accounts and is not required to proceed.

   Instead, use an execute-first posture:
   - Continue to the non-mutating feature checks below.
   - For mutating Bring your own Model operations (`CREATE COMPUTE POOL`, Model Registry import, `CREATE SERVICE`), show the normal review block and then run the statement only after user approval.
   - If Snowflake returns an insufficient-privilege error, stop and report the exact failed operation and privilege implied by the error.

   Expected privileges, validated by the operation that needs them:
   - `CREATE SERVICE` on `{database}.{schema}` for service creation
   - `USAGE` on the chosen compute pool, or `CREATE COMPUTE POOL` on the account if creating one
   - `BIND SERVICE ENDPOINT` on the account for the service's inference endpoint

3. **AI SQL service-overload session setup**:
   Do **not** precheck whether this session parameter exists. Attempt to set the required Bring your own Model/SPCS-in-AI-SQL session parameter directly:

   ```sql
   ALTER SESSION SET ENABLE_SPCS_SERVICE_FUNCTIONS_IN_AISQL = TRUE;
   ```
   The service function resource keyword and model inference proxy container URL are bundled now and do not need to be set manually. If the statement fails with `Invalid parameter` or a permission error, stop and report the exact failed parameter/error. Tell the user they lack permission to alter this session parameter, or the account does not have the Bring your own Model/SPCS-in-AI-SQL preview enabled, and they should contact their account admin if they are interested in using Bring your own Model. Do not attempt to work around it.

4. **Model Registry availability** (only if the user plans to import a Hugging Face model — i.e. `byom_path` is `New model` or `Compare first`):
   ```sql
   SHOW MODELS IN SCHEMA {database}.{schema};
   ```
   The query should succeed (an empty result is fine). A `feature not enabled` error indicates Model Registry is not available in the account/region — stop and report it.

5. **Verified model catalog populated** (only if `byom_path` is `New model` or `Compare first`):
   - Read `../references/byom/model_catalog.md`.
   - If the file shows the "not yet populated" banner and `_None yet._` under Verified Models, the catalog is gated. Follow the unpopulated-catalog fallback in `byom/SKILL.md` Step 3 (tell the user, fall back to Cortex model selection, skip the rest of Bring your own Model). Do not proceed to Steps 4–8.

**If any check fails**, stop and report only the failure:

- No GPU compute pool visible AND no `CREATE COMPUTE POOL` privilege → user needs an account admin to create or grant access to a GPU pool.
- Mutating operation returns an insufficient-privilege error, such as missing `CREATE SERVICE`, compute pool `USAGE`, `CREATE COMPUTE POOL`, or `BIND SERVICE ENDPOINT` → user needs an account admin to grant the privilege from the Snowflake error.
- Bring your own Model/SPCS-in-AI-SQL session parameter setup fails → report the exact failed parameter/error; tell the user they lack permission to alter the session parameter or the preview is not enabled, and they should contact their account admin if they are interested in using Bring your own Model.
- Model Registry not available → Bring your own Model `New model` path is not supported in this region; offer the existing-service path or fall back to Cortex models.
- Catalog unpopulated → fall back to Cortex models (do not attempt Bring your own Model).

## Optional but Recommended

- **Hugging Face token as a Snowflake secret** — speeds up Model Registry imports. Configured by the user (not the agent) per `byom/SKILL.md` Step 4, which offers a "Create a new secret from my Hugging Face token" option that walks the user through creating the secret themselves. If absent, imports still work but are slower.
- **External Access Integration** for the Hugging Face hub and approved container image registries — required if the account does not allow unauthenticated egress to those hosts. Configured by an account admin; reference its name in Step 4 / Step 6 review blocks.

## Privileges Summary

| Privilege | Scope | Used in |
|---|---|---|
| `USAGE` on compute pool | GPU compute pool | Step 2, Step 6 |
| `CREATE COMPUTE POOL` | Account | Step 2 (only if creating a new pool) |
| `CREATE SERVICE` | `{database}.{schema}` | Step 6 |
| `BIND SERVICE ENDPOINT` | Account | Step 6 |
| `USAGE` on `EXTERNAL ACCESS INTEGRATION` | Account | Step 4, Step 6 (if egress restricted) |
| `READ` on `SECRET` (HF token) | `{database}.{schema}` | Step 4 (optional speedup) |
| Model Registry read/write | `{database}.{schema}` | Step 4 (only on `New model` path) |
| `SNOWFLAKE.CORTEX_USER` (or equivalent) | Database role | Step 7, Step 8 (`AI_COMPLETE` service overload) |

## Output

The Bring your own Model workflow may proceed only when **all required checks pass**. If any required check fails, the workflow stops at Step 0 and reports the failure — it does not advance to Step 1 in the same turn.
