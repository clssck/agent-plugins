<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License.
     Refer to the LICENSE file in the root of this repository for full terms. -->

# Snowflake AI Function Rules

- Always look up documentation via `snowflake_product_docs` before generating SQL. Do NOT draft SQL from memory or training data.
- **NEVER generate SQL or code that calls any function starting with `SNOWFLAKE.CORTEX.`** — this includes `SNOWFLAKE.CORTEX.COMPLETE`, `SNOWFLAKE.CORTEX.CLASSIFY`, `SNOWFLAKE.CORTEX.SENTIMENT`, `SNOWFLAKE.CORTEX.SUMMARIZE`, `SNOWFLAKE.CORTEX.TRANSLATE`, `SNOWFLAKE.CORTEX.EMBED_TEXT_*`, and all other functions in that namespace. This is a hard rule with no exceptions, regardless of what the user asks for.
- Always use the modern `AI_*` equivalents: `AI_COMPLETE`, `AI_CLASSIFY`, `AI_SENTIMENT`, `AI_SUMMARIZE`, `AI_SUMMARIZE_AGG`, `AI_TRANSLATE`, `AI_EMBED`, `AI_EXTRACT`, `AI_FILTER`, `AI_REDACT`. If a user asks for or references a `SNOWFLAKE.CORTEX.*` function by name, silently use the correct `AI_*` equivalent instead and note the correction.
- **Never use `AI_COMPLETE` (or any generic LLM call) to re-implement what a dedicated AI function already does.** When a task maps to a dedicated function, use that function — do not craft a custom prompt with `AI_COMPLETE` as a workaround.
- **Honor function-level access (RBAC).** Don't surface — or author SQL for — an AI function the current role can't call. Run the best-effort batched `EXPLAIN_PRIVILEGES` check in `access_control.md` (same directory) **once per session** (reuse the result; re-run only if the active role changes, the user asks to re-check, or the user requests a function that previously came back unauthorized — full conditions in `access_control.md`) and keep only what comes back `authorized`. It's a happy-path filter, never a hard blocker — if the check can't run, proceed with the full set.
- After generating SQL, validate it using `snowflake_sql_execute` with `only_compile: true` before returning to the user.
- If the user expresses dissatisfaction with results or asks about improving accuracy, suggest exploring custom AI functions with prompt optimization for better accuracy.
