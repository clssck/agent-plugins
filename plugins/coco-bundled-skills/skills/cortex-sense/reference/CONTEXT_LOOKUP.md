# Context lookup

Single contract for querying what a built Cortex Sense context knows about a use case. Used by `test/SKILL.md` (interactive lookup) and `refine/SKILL.md` (pre-correction diagnostic). Both sub-skills reference this file instead of duplicating call logic.

## Input

- `query` — natural-language question or concept name. Required unless `fully_qualified_names` is set.
- `fully_qualified_names` — list of `DATABASE.SCHEMA.TABLE` strings. Optional.

At least one of `query` or `fully_qualified_names` must be present. Do not issue an empty lookup.

## Dual-source parallel lookup

Every lookup triggers **two searches in parallel**:

1. **Business Ontology search** — `SYSTEM$GET_GLOSSARY_TERM_LIST` for term-name matching.
2. **Cortex Sense context lookup** — the existing MCP tool / SQL fallback path (see "Priority order" below).

Launch both at the same time. When both complete:

- **If ontology returned matching nodes:** render them first under a `From Business Ontology` heading (node name, domain, description, formula if present, synonyms). Then, if context lookup also returned documents, render them under `From Cortex Sense context` with the existing doc-type rendering rules.
- **If ontology returned nothing but context lookup did:** render context results under `From Cortex Sense context`.
- **If both returned nothing:** render the "no context found" block (see "When lookup returns nothing").

Always briefly state the source so the user knows where the answer came from.

### Ontology search — contract

```sql
SELECT SYSTEM$GET_GLOSSARY_TERM_LIST('', 'TERM')
```

Parse the JSON result, filter `terms[]` where `name` (case-insensitive) matches the query term or any of the term's `synonyms[]`. Also match partial/substring if the query is longer than one word. Return all matching entries across all domains.

> **Known limitation:** `SYSTEM$GET_GLOSSARY_TERM_LIST` returns all approved terms in the account; filtering happens client-side. This is fine for typical accounts (dozens to a few hundred terms), but is not designed for accounts with thousands of terms. There is no server-side search parameter available yet.

**Rendering ontology matches:**

```
From Business Ontology:

  <name> (<itemKind>) — <domain>
    <description>
    Formula: <formula if present>
    Synonyms: <synonyms comma-separated>
    Tags: <tags comma-separated>
```

If multiple domains define the same term, show all — the user should know about duplicates.

### Ontology availability — session-level flag

Business Ontology might not be enabled on the account. To avoid repeated failing calls:

- On the **first** ontology call in a session, if `SYSTEM$GET_GLOSSARY_TERM_LIST` returns a feature-gate error (or any error), set an in-memory session flag: `ontology_available = false`.
- For all subsequent lookups in the same session, **skip the ontology search entirely** — do not call it again. This prevents repeated 1–2s latency penalties on accounts without the feature.
- If the first call succeeds (even with 0 terms), set `ontology_available = true` and continue calling it for subsequent lookups.
- This flag is session-scoped — a new session always retries once.

> **Implementation note:** `ontology_available` is **agent-managed in-memory state**, not a Python variable or persisted value. The agent tracks it in the conversation context across tool calls within a session. It is reset implicitly when the session ends.

The same flag applies everywhere in the Cortex Sense skill that accesses ontology APIs (`SYSTEM$GET_GLOSSARY_SUMMARY` in setup discovery, `SYSTEM$GET_GLOSSARY_TERM_LIST` in lookup). If any ontology call fails with a feature-gate error, set the flag and skip all ontology calls for the rest of the session.

---

## Priority order (Cortex Sense context path)

Try each path in order; stop at the first that returns a usable response.

### 1. MCP tool — `cortex_sense`

Available only when the coding-agent MCP tool is registered (per-account gate, gated on `CORTEX_AGENT_ENABLE_CORTEX_SENSE`). When available, prefer it — it may return richer context types.

Parameters (exact):
- `query` (string) — optional only if `fully_qualified_names` is set.
- `fully_qualified_names` (string array) — omit when empty.
- `context_names` (string array) — filters results to specific registered contexts. Values must be the **full FQN** constructed as `<database_name>.<schema_name>.<name>` using the `database_name`, `schema_name`, and `name` fields from `list-contexts` output — all three segments are case-sensitive. Never guess, infer, or transform any segment. Always source values from a prior `list-contexts` call. Omit the parameter entirely when not filtering to a specific context.
- `max_results` (integer) — tune by caller context:
  - **Broad/all-contexts search** (`query/SKILL.md`): `5–10` to avoid response overflow.
  - **Scoped single lookup** (`test/SKILL.md` single spot-check): `5` — the account may have many rich contexts; the server default is uncapped and responses can be large.
  - **Eval per-question calls** (`eval/SKILL.md`): always `5` — eval fires one call per question; large per-call responses in sequence can cause context-limit errors.
  - **Generate seed lookup** (`eval/SKILL.md` generate verb, one broad call): `10`.
  - Also available for fine-grained control: `ontology_max_results`, `table_entity_max_results`, `qbe_max_results`, and `datamart_max_results` (set to `0` to suppress datamart documents entirely).

> **Cross-context contamination.** The MCP tool (`cortex_sense`) and the SQL function (`SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT`) return from the **account-wide shared index** — there is no per-domain filter parameter. If the account has multiple built contexts (e.g. a healthcare demo alongside the target sales context), returned documents may belong to any of them. After fetching, filter documents to those relevant to the active domain by checking `entity_key`, `database`, or `schema` against the manifest's scope patterns. Documents whose `entity_key` or `database.schema` clearly falls outside the domain's scope can be noted as cross-context results and de-prioritised, but do **not** silently discard them without checking — they may be genuinely shared reference content. When rendering to the builder, call out clearly if results appear to be from a different context (as seen in the session example above).

The tool returns `{ "documents": [...], "error": {...} }` directly.

> **Empty-response edge case (MCP path).** The `documents` field on the MCP tool's result struct carries `omitempty`, so a nil/empty slice is omitted from the JSON response (no `documents` key at all). Treat a missing `documents` key the same as `[]` — an empty result, not an error. Always guard with `result.documents ?? []` or equivalent before iterating.

**Wrong-account detection**

The MCP tool's inference connection is account-scoped and can silently point at a different Snowflake account than the SQL connection. This causes two distinct failure modes; treat both as account mismatch:

**Signal A — document database not in this account (on first successful MCP response):**

1. Extract the `database` field from the first returned document. If `database` is absent, try the leading dot-separated segment of `entity_key` — but only treat it as a candidate database name if it looks like a Snowflake identifier (no slashes, no `http`, no spaces). Skip Signal A entirely if no plausible database name can be extracted (e.g. the document is an ontology node referencing a KB article).
2. Run: `SELECT COUNT(*) AS n FROM INFORMATION_SCHEMA.DATABASES WHERE DATABASE_NAME = UPPER('<extracted_db>');`
3. **If `n = 0`**: database does not exist in this account → MCP is serving another account's index. Trigger mismatch (see "Mismatch action" below).
4. **If `n > 0`**: correct account. Set a confirmed-correct session flag; skip this check for the rest of the session.

Skip Signal A when: MCP response contains no documents, or the session flag (mismatch or confirmed-correct) is already set.

**Signal B — MCP returns `NotFound` for a context that exists (on any MCP call):**

A `NotFound` error from the MCP tool for a specific context (e.g. `TEMP.CORTEX_SENSE.sales`) is ambiguous: the context may have been deleted, or the MCP tool may be resolving the name against the wrong account's registry. To distinguish:

1. **In parallel**, call `list-contexts` and make an unscoped MCP call (no `context_names`, `max_results: 3`).
2. **If `list-contexts` shows the context exists AND the unscoped MCP call returns documents from a different account** (Signal A fires on those documents) → confirmed mismatch. Trigger mismatch (see below).
3. **If `list-contexts` shows the context does not exist** → the context was deleted or never registered. Surface: `"Domain '<name>' not found — it may have been deleted. Run 'set up cortex sense' to create a new one."` Do not trigger mismatch.
4. **If `list-contexts` shows it exists but the unscoped MCP call also returns nothing or errors** → ambiguous; trigger mismatch as a precaution.
5. **If `list-contexts` itself errors** → trigger mismatch as a precaution (cannot confirm whether the context exists; assume the inference connection is at fault).

**Mismatch action (same for Signal A and B):**

Surface exactly once per session (session-level flag `mcp_wrong_account = true`, never repeat):
> ⚠️ Your inference connection and SQL connection are on different accounts — context results are from the wrong account. Switch your inference account in `/settings` to match your SQL connection, then retry. Using the SQL fallback for this session.

Set `mcp_wrong_account = true`. Skip path 1 for all remaining lookups in this session.

> **Note on persistence.** The inference account setting in `/settings` does not always persist across sessions — it can revert silently. If this warning fires repeatedly at the start of sessions, that is the likely cause. The fix is always the same: realign the inference account in `/settings`.

**Fall through to path 2 if any of the following are true:**
- The MCP tool is not registered.
- The MCP tool returns a 404 or `"corpus is not enabled on this deployment"` error.
- The MCP tool returns a non-error response but `documents` is empty (or the `documents` key is absent) — an empty result from MCP does **not** mean there is no context; fall through to the SQL path and use whichever returns more documents.
- `mcp_wrong_account = true`.

### 2. SQL fallback — `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT`

Use when the MCP tool is not registered or returns the "not enabled" error above.


#### Key difference from the MCP tool

`context_names` (FQN strings like `"DB.SCHEMA.MY_CONTEXT"`) is an **MCP-only parameter** — `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT` does not accept it. The SQL function's equivalent for context filtering is `cortex_context_ids` (an array of int64 values). The MCP tool resolves `context_names` → int64 IDs internally via its dedicated service; when calling the SQL function directly, you must resolve them yourself (see "Scoped SQL call" below).

#### Required parameters

Only `query` is required (or `fully_qualified_names` when no query). The function resolves the account and deployment server-side — **do not** pass `account_url` or `deployment`, and do not construct them from `CURRENT_ACCOUNT()` / `CURRENT_REGION()` or the `CORTEX_SENSE_ACCOUNT_URL` / `CORTEX_SENSE_DEPLOYMENT` env vars. Those fields are obsolete for context lookup; passing a stale deployment key caused misleading context results in testing.

The SQL fallback is therefore always available when the function itself is callable — it does not depend on any env var being set.

#### Pre-call: warehouse

`SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT` (and any `sql_execute` / `snow sql` call) needs an active warehouse. If a call fails with `No active warehouse selected in the current session` (or similar), do **not** apologize or dead-end — recover, then retry the original statement:

1. If the domain manifest is loaded and has a `warehouse`, run `USE WAREHOUSE <manifest.warehouse>;` and retry.
2. Otherwise run `SELECT CURRENT_WAREHOUSE();`. If it returns a warehouse, retry as-is; if it is null, ask the builder once: `Which warehouse should I use to run this? (e.g. ANALYTICS_WH)`, then `USE WAREHOUSE <name>;` and retry.
3. Keep the copy matter-of-fact — a missing warehouse is a session setting, not a lookup failure.

#### Calling the function

The function takes a **single string argument** containing a JSON object. The JSON must have a top-level `request_structured` key whose value contains `query` (and optionally `fully_qualified_names` / `cortex_context_ids`).

Use `sql_execute` directly (preferred over bash/snow CLI):

```sql
SELECT SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT(
  '{"request_structured": {"query": "<query>"}}'
)
```

To include fully-qualified names, add a `fully_qualified_names` array to `request_structured`:

```sql
SELECT SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT(
  '{"request_structured": {"query": "<query>", "fully_qualified_names": ["DB.SCHEMA.TABLE"]}}'
)
```

#### Scoped SQL call — filtering to a specific context

To restrict results to one or more specific Cortex Sense contexts, pass `cortex_context_ids` (int64 array). The `list-contexts` output that was fetched at session start contains the `id` for every registered context — use it:

**Step 1 — resolve the int64 ID from `list-contexts` output:**

The `list-contexts` JSON result has one entry per context:

```json
{
  "id": 44143196,
  "name": "random_demo_store",
  "database_name": "TEMP",
  "schema_name": "CORTEX_SENSE",
  ...
}
```

Match by `database_name`, `schema_name`, and `name` (all case-sensitive) to find the entry, then extract `id` as an integer.

**Step 2 — include `cortex_context_ids` in the SQL call:**

```sql
SELECT SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT(
  '{"request_structured": {"query": "<query>", "cortex_context_ids": [44143196]}}'
)
```

For multiple contexts, pass multiple IDs: `"cortex_context_ids": [44143196, 44143164]`.

> **If `list-contexts` wasn't called yet** in this session (e.g. you jumped straight to the SQL path without the session-open step), run it now and parse the `id` field before constructing the call. Never guess or hardcode IDs — they are assigned by the Cortex Context dedicated service and can change across deployments.

> **Coverage caveat:** The same partial-filtering limitation that applies to the MCP tool also applies here. `cortex_context_ids` scopes `table_entity` and CAM documents reliably. `qbe` documents (from snowscope) are returned from the account-wide index regardless of the `cortex_context_ids` value — they are not filtered. Filter those out client-side if only in-context results are desired.

#### Common errors and what they mean

| Error message | Cause | Fix |
|---------------|-------|-----|
| `Expected valid JSON request` | Argument is not valid JSON | Ensure single string with proper JSON escaping |
| `request must set request_structured or request_json` | Missing top-level `request_structured` key | Wrap payload in `{"request_structured": {...}}` |
| `too many arguments for function` | Passed multiple arguments | Function takes exactly 1 string argument |

> **Do not add `account_url` or `deployment` to fix an error.** They are no longer required and are resolved server-side; adding a stale deployment key caused misleading context results in testing. If the call fails, check the JSON shape, not these fields.

#### Parsing the output

The function returns a single string column containing JSON. Parse as:

```json
{
  "response_structured": {
    "documents": [ ... ]
  },
  "response_json": "..."
}
```

Documents are at `response_structured.documents`. Use `response_structured` (already parsed object) rather than `response_json` (redundant stringified copy).

> **Empty-response edge case (SQL path).** `response_structured` may be absent or `response_structured.documents` may be missing when the response is empty. Guard with `response_structured?.documents ?? []` before iterating.

### 3. Dead-end — both unavailable

If neither path is available (MCP tool returns "not enabled" AND the SQL function itself errors), render once and stop:

```
Context lookup isn't available in this session.
(The MCP tool returned "corpus not enabled" and the SQL fallback failed.
 Try @cortex-sense resume <domain> and "refine" to record corrections
 directly — those land in the manifest and apply on the next build.)
```

Do not fall back to SQL against `INFORMATION_SCHEMA`, `ACCOUNT_USAGE`, or any other query source.

## Response — document shape

Both paths return the same document shape:

| Field | Notes |
|---|---|
| `doc_type` | Which context type this document is (see rendering table below) |
| `entity_key` | Stable identifier — table FQN, concept name, view name, etc. |
| `database` / `schema` / `table` | Populated for table-entity documents |
| `markdown` | Pre-formatted narrative content when present (often from snowscope). May be empty for CAM-only docs. |
| `cam_content` | Matching CAM record body when present (markdown for L1 `table_entity`; structured/protojson for some L2 docs). May be empty for snowscope-only docs. |
| `sources` | Contributing backends: `"snowscope"`, `"cam"`, or both |

> **Content contract.** Each document may carry content in either or both of `markdown` and `cam_content`. Read whichever is non-empty — both represent the same entity (`markdown` is a rendered narrative, `cam_content` is the CAM artifact) and may appear together when the entity is present in multiple sources. Do not assume one field is authoritative when the other is set; treat them as complementary views. Freshly built customer-data contexts are often CAM-only for L1 `table_entity`, so `markdown` can be empty while `cam_content` holds the body — skipping `cam_content` yields blank "Table — …" sections even though lookup succeeded.

## Dedup by entity_key (before rendering)

The index is partitioned by source backend (`snowscope`, `cam`). A single real-world entity (e.g. one table or one concept) can appear as multiple documents in the same response — one per partition — each carrying the same `entity_key` but different content fields.

**Before rendering, collapse duplicates:**

1. Group the raw document list by `entity_key`.
2. For each group with more than one document, merge into a single document:
   - `markdown`: take the first non-empty value across the group (prefer the document whose `sources` includes `"snowscope"`).
   - `cam_content`: take the first non-empty value across the group (prefer the document whose `sources` includes `"cam"`).
   - `doc_type`, `database`, `schema`, `table`: take from the document that has `markdown` set; fall back to the other.
   - `sources`: union all values (e.g. `["snowscope", "cam"]`).
3. The merged document now carries both `markdown` (narrative) and `cam_content` (structured artifact). Apply the content contract in "Response — document shape" to render it.
4. If all documents in a group have empty `markdown` **and** empty `cam_content`, discard the group — do not render a blank section.

The deduplicated list is what gets rendered. **Never render two sections for the same `entity_key`.**

## Rendering

Render one section per document. Choose the header from `doc_type`:

| `doc_type` | Header |
|---|---|
| `table_entity` (or table schema) | `### Table — <database>.<schema>.<table>` |
| Domain overview | `### Domain — <entity_key>` |
| Ontology context (entity / metric / policy) | `### Definition — <entity_key>` |
| Query pattern | `### Query pattern` |
| Semantic view | `### Semantic view — <entity_key>` |
| `ontology_edge` | skip — contains graph traversal metadata with no renderable content; discard silently |
| Any other unrecognised `doc_type` | `### Context — <entity_key>` — render `markdown` if non-empty, else summarise `cam_content` key fields; never dump raw JSON |

Under each header, render body content as follows:

1. If `markdown` is non-empty, render it as-is — it is already markdown. Do not re-wrap it in a code block and do not dump raw JSON.
2. If `markdown` is empty/missing but `cam_content` is non-empty, render `cam_content` instead. When it looks like markdown (typical for L1 `table_entity`), render as-is; when it is structured JSON/protojson, summarize the useful fields rather than dumping the raw blob.
3. If both are non-empty, render `markdown` as the primary body and use `cam_content` as a complementary view when it adds detail not already in `markdown` — do not silently drop either source.

Number duplicates within a type (`### Query pattern 1`, `### Query pattern 2`).

## Error handling

**MCP tool error object:** if the response carries an `error` object, read its `type`:
- Client error (auth / permission / invalid argument / not found) → relay the `message` plainly; if it looks like an input problem, ask the caller to refine the query or FQNs.
- Internal error → "the lookup failed — try again shortly".

**SQL non-zero exit with stderr matching "already exists"** → treat as success.
**SQL non-zero, other error** → surface the stderr/stdout trimmed; do not retry.
**`RESULT` is null** (SQL exits 0 but `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT` returned non-JSON) → treat as an internal error.

Either path: do **not** fall back to `INFORMATION_SCHEMA` or `ACCOUNT_USAGE`.

## When lookup returns nothing

```
I didn't find any context for "<query>".

This usually means:
  • The build hasn't finished yet — if you just ran setup, context for tables
    and query history can take a few hours to show up.
  • The tables or concepts aren't in scope for this domain.
  • The latest save hasn't been picked up yet — check back a bit later.
```

## Availability check (from doctor output)

`doctor` reports `lookup_sql_available: true` whenever the Snowflake connection works (`snow_cli == "ok"`) — the SQL fallback no longer depends on any env var. The flag is near-redundant now: sub-skills can skip reading it and just attempt the SQL call. Fall through to the dead-end only if the function call itself errors.
