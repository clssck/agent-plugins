<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Cortex AI Function Access Check (EXPLAIN_PRIVILEGES)

> **Focus: a fast, best-effort access check** that resolves per-function access in **one batched query, run once per session.** Use it to avoid surfacing AI functions the current role can't call. It is a **filter on the happy path, never a hard blocker** — if the check can't run, show everything.

## When to Load

Load this reference any time the session is about to **surface or author** SQL that calls a built-in AI function — regardless of which skill or intent path led here:

- **Built-in** — before presenting the list of built-in AI functions (built-in skill Step 0).
- **Explore** — before recommending built-in vs. custom, so you don't steer a user toward functions their role can't call.
- **SQL authoring (tasks, sql-author, or any path that writes AI function SQL)** — before drafting the AI_* SQL, as required by `ai-function-rules.md`.

Source of truth: [Privileges and model access for Cortex AI Functions](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-privileges-and-access) and [EXPLAIN_PRIVILEGES](https://docs.snowflake.com/en/sql-reference/functions/explain_privileges).

## TL;DR

1. Run **one** batched query: call `EXPLAIN_PRIVILEGES(statement => '<dummy call>', missing_only => true)` for each function, all in a single `SELECT`.
2. A function is **accessible** when its cell is `{"authorized": true}`. Anything else means the current role can't call it — filter it out of the menu.
3. **If the whole check errors** (the function isn't available on the account, the query fails, etc.) → **move on and do not hide any functions.** Show the full list.
4. Run it **silently** — no "checking access…" preamble. Only speak up when something is filtered out or the user asks.
5. Run it **at most once per session.** Cache the result and reuse it on later turns; re-run only when the active role changes (see [Caching](#caching-run-once-per-session)).

This replaces the older `IS_DATABASE_ROLE_IN_SESSION` approach. `EXPLAIN_PRIVILEGES` asks the real question ("can *this session* run this exact statement?") per function, so it captures the `USE AI FUNCTIONS` account privilege **and** per-function `USAGE` **without** any `SHOW GRANTS` walk (which can time out on large accounts).

## The check

`EXPLAIN_PRIVILEGES` with `missing_only => true` and **no** `for_role` evaluates the **current session** (primary + secondary roles, inherited roles, and `PUBLIC`). Pass `for_role` only if you specifically want to analyze a different role — it does **not** reflect database-role grants, so leave it off here.

The statement argument must **type-check** (parse + resolve signatures), but it is **not executed** — no credits, no model invocation. Use the dummy calls below verbatim.

```sql
SELECT
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_CLASSIFY('x',['a','b'])$$,                                  missing_only => true) AS ai_classify,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_FILTER('positive', col) FROM (SELECT 'a' col)$$,            missing_only => true) AS ai_filter,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_EXTRACT(text => 'x', responseFormat => {'k':'q'})$$,        missing_only => true) AS ai_extract,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_COMPLETE('llama3.1-8b','x')$$,                              missing_only => true) AS ai_complete,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_PARSE_DOCUMENT(TO_FILE('@~/x.pdf'), {'mode':'OCR'})$$,      missing_only => true) AS ai_parse_document,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_SUMMARIZE_AGG(col) FROM (SELECT 'x' col)$$,                 missing_only => true) AS ai_summarize_agg,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_AGG('s', col) FROM (SELECT 'x' col)$$,                      missing_only => true) AS ai_agg,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_SENTIMENT('x')$$,                                           missing_only => true) AS ai_sentiment,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_TRANSLATE('hello','en','es')$$,                             missing_only => true) AS ai_translate,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_EMBED('e5-base-v2','x')$$,                                  missing_only => true) AS ai_embed,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_REDACT('x')$$,                                              missing_only => true) AS ai_redact,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_TRANSCRIBE(TO_FILE('@~/x.mp3'))$$,                          missing_only => true) AS ai_transcribe,
  EXPLAIN_PRIVILEGES(statement => $$SELECT AI_SIMILARITY('a','b')$$,                                      missing_only => true) AS ai_similarity;
```

These dummy calls only need to *compile*, not return good results — the literal args are placeholders. The `@~/` user stage in the FILE-based calls always resolves, so they type-check on any account.

## Reading the result

Each column is a JSON string:

- **`{"authorized": true}`** → the role can call the function. **Show it.**
- **Anything else** (an `allOf` / `oneOf` tree of missing privileges) → the role is missing something. **Filter it out** of the menu.

### Graceful degradation

- **At least one column `authorized`** → show those functions; filter out the rest.
- **All columns denied (query succeeded)** → the role has no Cortex AI access. Don't show an empty menu — report it and give the remediation grant (below), then stop.
- **Query errored / `EXPLAIN_PRIVILEGES` unavailable / `SNOWFLAKE` unreachable** → **do not filter.** Show the full list and proceed; optionally add one line noting access wasn't verified. Never hard-block on a failed check.

## Caching: run once per session

The batched check returns the access status for **every** function at once, so it's a single per-session lookup — **not** a per-function or per-turn probe. Running it on every turn is wasteful; running it per function defeats the batching.

- **Run once.** The first time this session needs to present or author an AI function, run the batched query and remember the resulting function→`authorized` map.
- **Reuse thereafter.** On later turns, reuse that cached map. Do **not** re-run the query.
- **Cache in working context, not in Snowflake.** The result already lives in the earlier turn's output — reuse it from there. Don't rely on a Snowflake session variable or temp table: connections aren't guaranteed to persist across turns, so that state can silently vanish.
- **Key the cache on the active role(s).** The authorized set is a function of the current primary + secondary roles, so the cache is valid only while those hold.

Re-run the check **only** when:

- No cached result exists yet this session (first use), **or**
- The active role context changed — you issued or observed a `USE ROLE` / `USE SECONDARY ROLES`, **or**
- The user explicitly asks to re-check access, **or**
- The user asks for a function that previously came back **unauthorized** (one re-verify, in case grants changed).

**Per-function top-up.** If the user asks about a function that wasn't in the cached batch (e.g. a brand-new function not in the stub list), probe just that one function with a single `EXPLAIN_PRIVILEGES` call and add it to the cached map — don't re-run the whole batch.

## Dummy-query reference

Use these exact stubs (they compile without executing). If a brand-new function appears that isn't listed, confirm its signature from docs (`snowflake_product_docs`) before adding a stub.

| Function | Kind | Dummy statement |
|----------|------|-----------------|
| `AI_CLASSIFY` | scalar | `SELECT AI_CLASSIFY('x',['label1','label2'])` |
| `AI_FILTER` | scalar | `SELECT AI_FILTER('positive', col) FROM (SELECT 'a' col)` |
| `AI_EXTRACT` | scalar | `SELECT AI_EXTRACT(text => 'x', responseFormat => {'k':'q'})` |
| `AI_COMPLETE` | scalar | `SELECT AI_COMPLETE('llama3.1-8b','x')` |
| `AI_PARSE_DOCUMENT` | scalar | `SELECT AI_PARSE_DOCUMENT(TO_FILE('@~/x.pdf'), {'mode':'OCR'})` |
| `AI_SUMMARIZE_AGG` | aggregate | `SELECT AI_SUMMARIZE_AGG(col) FROM (SELECT 'x' col)` |
| `AI_AGG` | aggregate | `SELECT AI_AGG('s', col) FROM (SELECT 'x' col)` |
| `AI_SENTIMENT` | scalar | `SELECT AI_SENTIMENT('x')` |
| `AI_TRANSLATE` | scalar | `SELECT AI_TRANSLATE('hello','en','es')` |
| `AI_EMBED` | scalar | `SELECT AI_EMBED('e5-base-v2','x')` |
| `AI_REDACT` | scalar | `SELECT AI_REDACT('x')` |
| `AI_TRANSCRIBE` | scalar | `SELECT AI_TRANSCRIBE(TO_FILE('@~/x.mp3'))` |
| `AI_SIMILARITY` | scalar | `SELECT AI_SIMILARITY('a','b')` |

By default `CORTEX_USER` is granted to `PUBLIC`, so on an untouched account every function comes back `authorized`. Filtering matters once an admin has revoked that default or granted access selectively.

## Reporting missing access

When a function is filtered out and the user asks why (or when nothing is accessible), surface the remediation without dumping the raw JSON tree:

```
{FUNCTION} isn't available to your current role ({role}).

To enable Cortex AI functions, an ACCOUNTADMIN can grant a Cortex database role:
  GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE {role};
```

If the missing privilege the tree reports is specifically `USE AI FUNCTIONS` on the account, that grant is also a valid remediation path (`GRANT USE AI FUNCTIONS ON ACCOUNT TO ROLE {role};`), but the database role above is the standard route.

## Pitfalls

- **Never hard-block on a failed check.** If `EXPLAIN_PRIVILEGES` errors or isn't available, show all functions — do not hide anything or stop the workflow.
- **Don't pass `for_role`.** It does not reflect database-role grants (it will report `USE AI FUNCTIONS` missing even when the session is authorized). Session mode — `missing_only => true`, no `for_role` — is the correct, accurate form.
- **Statements must type-check.** Use the dummy stubs verbatim; wrong signatures fail at compile time and the check won't run for that function.
- **Secondary roles are included.** Session mode reflects everything active, including secondary roles — correct for "what can I call *right now*." If the user is asking what *this primary role* allows, suggest re-checking under `USE SECONDARY ROLES NONE`.
- **Don't probe by executing functions.** A real call conflates *function* RBAC with *model* RBAC and costs credits. `EXPLAIN_PRIVILEGES` analyzes without executing.
- **Don't narrate on success.** No "checking access…" preamble when everything passes. Only speak up when filtering or failing.
