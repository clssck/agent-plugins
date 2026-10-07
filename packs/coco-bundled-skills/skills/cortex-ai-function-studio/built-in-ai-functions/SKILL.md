---
name: built-in-ai-functions
description: "**[REQUIRED]** Use for ALL operations using Snowflake's built-in AI_* functions — including running functions, estimating token costs, and authoring batch SQL. Triggers: run AI_SENTIMENT, use AI_COMPLETE, use AI_CLASSIFY, use AI_SUMMARIZE_AGG, use AI_EXTRACT, use AI_FILTER, use AI_TRANSLATE, use AI_EMBED, use AI_PARSE_DOCUMENT, use AI_REDACT, use AI_TRANSCRIBE, use AI_SIMILARITY, estimate tokens, count tokens, AI function cost, how many tokens, token estimate, AI_COUNT_TOKENS, which AI functions can I use, AI function access/privileges, classify text, sentiment analysis, summarize, translate."
parent_skill: cortex-ai-function-studio
---
<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License.
     Refer to the LICENSE file in the root of this repository for full terms. -->

# Built-in AI Functions

Help users apply Snowflake's built-in Cortex AI Functions to their use cases. Draft the SQL they need, validate it, and offer the custom AI function workflow if the built-in result isn't sufficient.

## Rules

Read `../references/ai-function-rules.md`

- **Function access: don't surface a function the current role can't call.** Before listing **any** function (Step 0), run the batched `EXPLAIN_PRIVILEGES` access check in `../references/access_control.md` and filter the menu to what comes back `authorized`. Run it **once per session** and reuse the cached result on later turns (re-run only if the active role changes) — see the Caching section in that reference. The check is **best-effort, never a hard blocker** — if it errors (`EXPLAIN_PRIVILEGES` unavailable, the query fails), show the full list and move on. Do not infer access by executing every function in turn.
- **Estimate cost before large runs.** Before actually running (Step 4) a query that applies an AI function across a **table column** (batch over many rows) or has **multiple AI calls** in one statement, do a quick `AI_COUNT_TOKENS` estimate and surface it so the user can decide whether to proceed, sample, or narrow scope. Skip it for `only_compile` validation, single-literal/trial calls, and already-sampled or small runs. This is **advisory, never a blocker** — see `../references/cost_estimation.md`.

## Workflow

### Step 0: Determine Accessible Functions (EXPLAIN_PRIVILEGES Access Check)

**The first time this skill presents or uses a function in a session, your FIRST tool call MUST be the access-check query below** — before reading any other file, before naming or listing any function, before showing the Quick Reference. You have **not** completed Step 0 (and may not produce any function list) until this query has executed and returned **or** you have a cached result from earlier this session.

**Already ran it this session?** Reuse the cached function→`authorized` map — do **not** re-run the query. Re-run only if the active role changed (`USE ROLE` / `USE SECONDARY ROLES`), the user asks to re-check, or the user requests a function that came back unauthorized. Full caching rules: the Caching section in `../references/access_control.md`.

Run one batched query that calls `EXPLAIN_PRIVILEGES(..., missing_only => true)` (no `for_role`) on a dummy statement per function. It analyzes the **current session** without executing the functions — no credits, no model calls. (Full details + the model-bleed nuance + remediation: `../references/access_control.md`.)

```sql
SELECT
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_CLASSIFY('x',['a','b'])$$,                             missing_only => true) AS ai_classify,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_FILTER('positive', col) FROM (SELECT 'a' col)$$,       missing_only => true) AS ai_filter,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_EXTRACT(text => 'x', responseFormat => {'k':'q'})$$,   missing_only => true) AS ai_extract,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_COMPLETE('llama3.1-8b','x')$$,                         missing_only => true) AS ai_complete,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_PARSE_DOCUMENT(TO_FILE('@~/x.pdf'), {'mode':'OCR'})$$, missing_only => true) AS ai_parse_document,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_SUMMARIZE_AGG(col) FROM (SELECT 'x' col)$$,            missing_only => true) AS ai_summarize_agg,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_AGG('s', col) FROM (SELECT 'x' col)$$,                 missing_only => true) AS ai_agg,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_SENTIMENT('x')$$,                                      missing_only => true) AS ai_sentiment,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_TRANSLATE('hello','en','es')$$,                        missing_only => true) AS ai_translate,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_EMBED('e5-base-v2','x')$$,                             missing_only => true) AS ai_embed,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_REDACT('x')$$,                                         missing_only => true) AS ai_redact,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_TRANSCRIBE(TO_FILE('@~/x.mp3'))$$,                     missing_only => true) AS ai_transcribe,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_SIMILARITY('a','b')$$,                                 missing_only => true) AS ai_similarity;
```

Read each column: `{"authorized": true}` → the role **can** call that function (show it); anything else → **filter it out**.

Common failure modes — **do not** do these:

- ❌ Listing functions and adding a prose caveat like "…available if your role has access" **instead of** running the query. Run the query.
- ❌ Answering from the Quick Reference table or your own knowledge **before** the query returns.
- ❌ Probing access by actually calling functions one at a time (costs credits, conflates model RBAC).

Run the check **silently** — no narration on the happy path. Then continue, filtering every function list you present to the accessible set:

- **At least one column `authorized`** → show only those functions; drop the rest.
- **All columns denied (query succeeded)** → do not show the menu. Report that the current role lacks Cortex AI function access (with the remediation grant from `access_control.md`) and stop.
- **Query errored** (`EXPLAIN_PRIVILEGES` unavailable, the statement failed) → **do not hide anything** — present the full list and move on, optionally noting access wasn't verified.

### Step 1: Identify the Function

Match the user's task to the appropriate built-in function using the Quick Reference table below. **Only consider functions in the accessible set from Step 0.**

**If unclear which function:** Present the options — but **only after the Step 0 query has returned**, and **listing only the functions the current role can access** (drop any that failed the Step 0 check, and renumber accordingly). If you have not run the Step 0 query yet, run it now before rendering this menu:
```
Which built-in AI function fits your task?

1. AI_CLASSIFY — Categorize content into labels
2. AI_FILTER — Filter rows by natural language condition
3. AI_EXTRACT — Extract structured data from text or documents
4. AI_COMPLETE — General LLM task or image analysis
5. AI_PARSE_DOCUMENT — OCR and extract from PDFs/images
6. AI_SUMMARIZE_AGG — Summarize text across rows
7. AI_AGG — Custom aggregation across rows
8. AI_SENTIMENT — Sentiment scoring
9. AI_TRANSLATE — Language translation
10. AI_EMBED — Generate vector embeddings
11. AI_REDACT — Mask PII
12. AI_TRANSCRIBE — Audio/video to text
13. AI_SIMILARITY — Compare vector similarity

Or describe what you're trying to do and I'll recommend one.
```

If the user asks for, or describes a task that maps to, a function **not** in the accessible set, do not draft its SQL. Explain it isn't available to their role and show the remediation grant from `access_control.md`.

### Step 2: Look Up Documentation

**MANDATORY — do not skip.** Call `snowflake_product_docs` with a query like `"AI_CLASSIFY function syntax and examples"` to get the latest documentation for the identified function. Use `web_fetch` on the returned URL if more detail is needed.

**You MUST call `snowflake_product_docs` before drafting any SQL.** Answering from training-data memory is explicitly prohibited by `../references/ai-function-rules.md`. If `snowflake_product_docs` is unavailable, use `web_fetch` to the Snowflake docs URL for that function.

### Step 3: Draft SQL

Using the documentation results, help the user construct their query:

1. Understand the user's table/data structure
2. Draft the SQL using the correct function signature and patterns from the docs
3. Validate with `snowflake_sql_execute` (`only_compile: true`)
4. If validation fails, fix and re-validate before presenting to the user

### Step 4: Test and Iterate

**Before running a large or fan-out query, estimate cost first.** If the query applies the function across a table column (batch over many rows) or chains multiple AI calls:

1. **Use `AI_COUNT_TOKENS` — not character length, not row count alone.** Run the estimation query from `../references/cost_estimation.md`. Do NOT substitute `AVG(LENGTH(...))` or other character-based heuristics — `AI_COUNT_TOKENS` is the correct tool and counts the actual tokenizer input.
2. **Surface the projection as token counts only.** Format: `~N rows × ~T tokens/row ≈ X total input tokens`. **NEVER convert to dollar amounts or present USD figures (`$0.15`, `$2.00`, etc.) — this is prohibited even when the user asks "how much will this cost?".** Do NOT look up Snowflake pricing or the Service Consumption Table to convert tokens to dollars. Use token counts only.
3. **For generative functions (`AI_COMPLETE`, `AI_SUMMARIZE_AGG`, `AI_AGG`), explicitly state the floor caveat:** "`AI_COUNT_TOKENS` counts input tokens only — output tokens bill on top of this, so treat this number as a floor." Use the words "output tokens", "floor", or "input-only" in your response.
4. Let the user choose to proceed, sample, or narrow scope. Wait for their answer before running the full batch.

Skip cost estimation for `only_compile` validation, single-literal/trial calls, or already-sampled/small runs. It's advisory — if the estimate can't run, note it briefly and proceed.

Help the user run their query and iterate:
- If the user has labeled data, help them measure accuracy
- If the user wants to adjust parameters (model, task_description, few-shot examples), help them refine
- If the user is satisfied, the workflow is complete

### Step 5: Done

If the user is satisfied, the workflow is complete.

## Available Functions

AI_CLASSIFY, AI_FILTER, AI_EXTRACT, AI_COMPLETE, AI_PARSE_DOCUMENT, AI_SUMMARIZE_AGG, AI_AGG, AI_SENTIMENT, AI_TRANSLATE, AI_EMBED, AI_SIMILARITY, AI_REDACT, AI_TRANSCRIBE.

Do NOT use signatures from memory. Call `snowflake_product_docs` to get the correct syntax for whichever function the user needs.

## Notes

- All functions run in Snowflake — data never leaves the platform
- Functions work in SELECT, WHERE, and JOIN clauses
- Use batch processing (apply to table columns) for best throughput
- Access is gated by a Cortex database role (`SNOWFLAKE.CORTEX_USER` covers all functions, `AI_FUNCTIONS_USER` the scalar ones, `CORTEX_EMBED_USER` just `AI_EMBED`) plus the `USE AI FUNCTIONS` account privilege. Rather than mapping roles by hand, the Step 0 `EXPLAIN_PRIVILEGES` check resolves per-function access directly — filter the list to what it reports `authorized`. See `../references/access_control.md`.
