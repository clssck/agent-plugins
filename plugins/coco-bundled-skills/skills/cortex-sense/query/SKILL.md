---
name: cortex-sense-query
description: "Query Cortex Sense contexts with natural language. Searches across all contexts or filters to specific use case(s). Automatically matches your query to the most relevant contexts by examining manifest metadata. Use when: asking questions across multiple use cases, exploring what contexts exist, searching for data without knowing which context to use, querying a specific use case without the full test or eval workflow. Triggers: query about <X>, search contexts for <X>, search across contexts for <X>, what does cortex sense know about <X>, which of my contexts know about <X>, @cortex-sense query <use-case> about <X>."
parent_skill: cortex-sense
---

# Query

## What you're searching

A Cortex Sense context is a pre-built, scoped knowledge base for one domain — curated table schemas, business definitions, query patterns, and semantic-view metadata assembled ahead of time by a builder. Querying searches that curated knowledge; it does not execute SQL or return live data values. If the user actually wants current numbers, row counts, or a computed result, this isn't the right tool — say so rather than guessing an answer from context documents.

## Two modes

1. **All-contexts mode**: User types "query about X" or "search contexts for X" — searches across all available contexts, ranks by relevance.
2. **Scoped mode**: User types "@cortex-sense query <use-case> about X" — filters to specific context only.

## List-only path (no query)

When the intent is purely to enumerate existing domains — "list cortex sense", "show all domains", "what cortex sense do I have", "list all contexts", "what domains exist", or any equivalent — **skip all input-parse and lookup steps** and go straight here:

1. Call `list-contexts` (see the SQL block in the section below).
2. Render:
   ```
   Your Cortex Sense domains (<N> found):

     • <domain_name_1>  (<DB_1>.<SCHEMA_1>)
     • <domain_name_2>  (<DB_2>.<SCHEMA_2>)
     …

   To resume one: @cortex-sense resume <domain>
   To check its build: @cortex-sense resume <domain> check build
   ```
3. If no contexts exist:
   ```
   No Cortex Sense domains found. To create one: set up cortex sense
   ```
4. Stop. Do not proceed to the query flow.

> **Important:** Registered domains live in `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER`. They are **not** in a stage, not in `SHOW STREAMLITS`, and not in `INFORMATION_SCHEMA`. Always call `list-contexts` — never infer the list from stage contents or file listings.

---

## On entry: check prerequisites, then list contexts

**Do not run `uv run doctor` for query — the subprocess startup cost is significant and the checks are cheaper done directly.** Perform the equivalent inline instead, and cache the results for the session so subsequent queries skip this entirely.

**Inline prerequisite check (once per session):**

1. `which snow` — if missing, show the install line (same copy as `../setup/SKILL.md` §0) and stop.
2. Read env vars directly:
   - `database` = `$CORTEX_SENSE_DB`
   - `schema` = `$CORTEX_SENSE_SCHEMA`
3. If `snow` is present, continue silently. Only ask the user for a database and schema if `$CORTEX_SENSE_DB` / `$CORTEX_SENSE_SCHEMA` are unset **and** the list-contexts call below subsequently fails — don't ask preemptively.

The SQL fallback (`SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT`) is available whenever `snow` works — it resolves account/deployment server-side and needs no env vars (see `../reference/CONTEXT_LOOKUP.md`). Full doctor contract is in `../reference/STORAGE.md` — consult it only if a SQL call fails with a configuration or auth error and you need to diagnose.

Then list all available contexts:

```bash
uv run --project <SKILL_DIR>/.. snow sql --format json -q "
  SELECT SYSTEM\$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER(
    '{\"action\":\"list-contexts\"}'
  ) AS result;
"
```

Parse the response to extract the list of contexts with their `name`, `database_name`, and `schema_name`.

`<WORKSPACE_DIR>` and `<SKILL_DIR>` are placeholders the agent resolves.

## Open the session

Render once, on entry:

```
Querying Cortex Sense contexts.

(Found <N> context(s) in your account.)
```

If no contexts exist, stop and suggest:

```
No Cortex Sense contexts found. To create one, type: set up cortex sense
```

## Parse the input

Extract from the user's request:

- **`domain`** — if "@cortex-sense query <name> about X" pattern, extract `<name>`
- **`query`** — the natural language question (everything after "about" or the full input if no domain specified)

**Smart domain matching (all-contexts mode only):** After extracting the text after "about", check whether it matches an available context name, then branch on **match quality** — this is what decides confirm-first vs switch-silently:

- **Clean match** — an exact context name, or a *single* context whose name contains the text as a case-insensitive prefix/substring: switch to scoped mode **without a confirmation round-trip**. Treat the matched context as `domain`, and note the switch in one line ("Scoped to the `<domain>` context — say *all contexts* to broaden.") so the builder can cheaply correct it. Text after the matched name becomes the `query`; if there's none, ask "What would you like to know about the `<domain>` context?"
- **Fuzzy or ambiguous match** — an approximate/typo match with no clean substring, or *two or more* contexts that match equally well: do **not** switch silently. Show a "Did you mean?" confirmation naming the candidate(s) before scoping.
- **No name match**: stay in all-contexts mode and rank contexts by relevance (next section).

For example:
- "query about product_data_science" → single substring match `product_data_science_mini` → switch to scoped mode, note "Scoped to the `product_data_science_mini` context."
- "query about strimlit" → approximate/typo match to `streamlit_open_source_analytics`, no clean substring → confirm: "Did you mean the `streamlit_open_source_analytics` context?"
- "query about revenue" → no context named like "revenue" → stay in all-contexts mode, rank by relevance

If neither a domain nor query text is present, ask once:

```
What would you like to query?
  • For all contexts: "query about <your question>"
  • For specific context: "@cortex-sense query <use-case> about <your question>"
```

## Match contexts (all-contexts mode only)

If a domain is specified (scoped mode), validate it exists in the contexts list. If not found, report:

```
Domain "<domain>" not found.

Available contexts: <list context names>

To query a different context, type: @cortex-sense query <name> about <query>
```

If no domain specified (all-contexts mode), rank contexts by relevance. Loading a manifest costs one `get-stage-file` SQL round-trip per context, issued serially — so **pre-filter cheaply before loading any manifest** rather than fetching all of them (an account with 20+ contexts must not trigger 20+ round-trips just to rank):

0. **Cheap name pre-filter (no SQL).** Score every context on its `list-contexts` metadata alone — context `name`, `database_name`, `schema_name` — against the query keywords. Advance to manifest loading only the contexts that survive, capped at **10 candidates**:
   - If the account has ≤10 contexts, skip the pre-filter and load all of them.
   - If more than 10 survive, keep the 10 whose names/schemas best match the query; if the query is topical and matches no names at all, take the first 10.
   - Whenever the cap drops contexts, say so once so the builder can narrow — "Ranked the 10 closest contexts by name; name a context to search it directly." Never silently discard contexts.

1. Load each **candidate's** manifest using `get-stage-file` per `../reference/STORAGE.md` "Loading — one call":

```bash
uv run --project <SKILL_DIR>/.. snow sql --format json -q "
  WITH raw AS (
    SELECT TRY_PARSE_JSON(
      SYSTEM\$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER(
        '{\"action\":\"get-stage-file\",\"parameters\":{\"name\":\"<domain>\",
          \"database_name\":\"<DB>\",\"schema_name\":\"<SCHEMA>\",
          \"path\":\"scope.yaml\"}}'
      )
    ):response_structured:content::STRING AS content_str
  )
  SELECT
    CASE
      WHEN content_str REGEXP '^[A-Za-z0-9+/\\n]+=*\$'
        THEN BASE64_DECODE_STRING(content_str)
      ELSE content_str
    END AS scope_yaml
  FROM raw;
"
```

2. For each loaded manifest, count keyword matches:
   - Match against `business_domain` (case-insensitive)
   - Match against `sources[].rules[].user_prompt` (case-insensitive substring)
   - Match against `sources[].rules[].description` when present (case-insensitive substring) — only `pattern`-type rules carry this field; other rule types simply contribute no match here
   - Match against `concepts[].name` (case-insensitive)
   - Match against `concepts[].description` (case-insensitive substring)

3. Rank candidates by match count. Take top 3-5 (or all if match scores are tied).

If no contexts match and query is specific, inform user:

```
No contexts found matching "<query>".

All available contexts:
  • <context-1>
  • <context-2>
  ...

Try a different query, or specify a context: @cortex-sense query <name> about <query>
```

## Execute lookup

**Follow the full lookup contract in `../reference/CONTEXT_LOOKUP.md`:**

1. Try the `cortex_sense` MCP tool first (coding-agent, per-account gate).
   - After the first MCP response, run **Signal A** of the wrong-account detection check from `../reference/CONTEXT_LOOKUP.md` "Wrong-account detection". If it triggers (`mcp_wrong_account = true`), switch to path 2 for the rest of the session.
2. If the tool is not registered, fall back to the SQL system function (`SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT`) — available whenever `snow` works (no env vars required).
3. If both are unavailable (the SQL function itself errors), render the dead-end and stop.

This section covers what's specific to query mode: how to shape step 1's call, and how to handle a flaky one. Everything else — call shapes, response parsing, rendering table, error handling — comes verbatim from the contract; do not duplicate it here.

### Shape the call

Pass the extracted `query` (see "Parse the input") as one complete natural-language string — the caller's actual question, not a keyword fragment. One call already returns a broad set of relevant matches; issuing several calls with slightly reworded or keyword-only versions of the same question does not surface more results, it just multiplies latency. Target exactly **one `cortex_sense` call per mode**, and always set `datamart_max_results: 0` — this skill does not surface datamart documents:

- **Scoped mode**: one call, `context_names: ["<DB>.<SCHEMA>.<use-case>"]`, `datamart_max_results: 0`.
- **All-contexts mode**: one call, `context_names` holding *every* matched context from the ranking step (`["<DB1>.<SCHEMA1>.<name1>", "<DB2>.<SCHEMA2>.<name2>", ...]`), `datamart_max_results: 0` — never loop the tool call once per matched context.

If the user's request also names specific tables, pass them as `fully_qualified_names` in the *same* call rather than a follow-up call.

> **Note:** `context_names` filters results, but coverage is partial by doc type: `table_entity` results are reliably scoped to the named context(s); `ontology_node` results are scoped inconsistently; `qbe` results are not scoped at all. Either may still include documents from contexts you didn't name — don't assume `context_names` fully isolates results across every doc type.

**Writing a good query:** ask in business language — a definition, a formula, a table's purpose, a metric, a recurring pattern — rather than a single keyword or SQL-shaped text. "What tables define ARR" surfaces more than "ARR". When the user already named a table or view, pass it via `fully_qualified_names` instead of describing it in prose — that's a more precise signal than working it into the `query` string.

### Resilience

A `cortex_sense` call can fail transiently (timeout, 5xx, connection reset) for reasons that have nothing to do with the tool being unavailable. If the first attempt fails with one of those signals, retry the exact same call once before falling through to step 2 above. Do not retry on a permanent signal (the tool not being registered, or a "not enabled" response) — fall through immediately, per the contract. Never retry with a narrower or reworded query as a workaround; retry the identical call.

## Render results

Group results by source context. For each document returned:

1. Determine which context it came from (if available in document metadata, otherwise infer from sources)
2. Render a header showing the source context:

```
### From: <context-name>
```

3. Render the document using the standard rendering from `../reference/CONTEXT_LOOKUP.md` (by doc_type: table_entity, ontology_node, etc.)

Treat every `doc_type` in the response as complementary, not competing — a `table_entity` document and an `ontology_node` document about the same concept both matter; render both instead of stopping at the first match. If the same `entity_key` shows up under more than one context with materially different content, render both under their own context headers rather than silently picking one — the discrepancy itself is useful information for the builder.

After all results:

```
type another query, specify a context, or: **done**
```

## When lookup is unavailable

If neither the MCP tool nor the SQL fallback is available, render the dead-end copy from `../reference/CONTEXT_LOOKUP.md` "Dead-end — both unavailable", then stop.

## When the lookup returns nothing

Use the verbatim copy from `../reference/CONTEXT_LOOKUP.md` "When lookup returns nothing", then:

```
Try a different query, or: **done**
```

## What this skill never does

- Edit or refine contexts — route to `../refine/SKILL.md` for corrections
- Set up new contexts — route to `../setup/SKILL.md` for that
- Run structured evals — route to `../eval/SKILL.md` for answer correctness scoring
