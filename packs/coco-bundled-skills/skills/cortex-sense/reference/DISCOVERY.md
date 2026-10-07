# Discovery

Discovery runs the moment the use case is named. It is **background work** — its purpose is to return one comprehensive draft scope, not to interview the builder. The builder should never have to push CoCo to "look at more sources" or "find more apps".

> **Orchestrator rule — fast-pass first, then deep-pass.** At T=0, launch the fast-pass calls (#1–#6) and `discover_usage.py` (#7) simultaneously — they have no dependency on each other. **As soon as the fast-pass calls return (~3–5s), render the draft summary immediately — do not wait for `discover_usage.py`.** The builder should see results within seconds, not minutes. When `discover_usage.py` finishes (30–120s later), silently re-render the Tables, External dashboards, Dashboards, and Semantic views rows with usage counts — no announcement to the builder. Do not run the fast-pass calls sequentially. Do not improvise SQL. Do not ask the builder which sources to check first.

## The discovery batch (all at T=0)

| # | Pass | Call | Purpose |
|---|---|---|---|
| 1 | 1 | `snowflake_object_search(search_query="<use case key question>", object_types=["table", "view", "external-table", "external-database", "database", "schema"], max_results=20)` | Top tables, schemas, databases, external tables, and external databases ranked by relevance |
| 2 | 1 | `snowflake_object_search(search_query="<use case key question>", object_types=["semantic-view"], max_results=10)` | Semantic views relevant to the use case |
| 3 | 1 | `snowflake_object_search(search_query="<use case key question>", object_types=["streamlit"], max_results=10)` | Streamlit apps relevant to the use case |
| 4 | 1 | `snowflake_object_search(search_query="<use case key question>", object_types=["bi-object"], max_results=10)` | BI objects relevant to the use case |
| 5 | 1 | `cortex_sense(query="<use case key question>")` | Existing registered context docs for this domain (definitions, rules, concepts already known) |
| 6 | 1 | Tag extraction from #1's results | Governance tags appearing on in-scope objects |
| 7 | 2 | `scripts/discover_usage.py` (launched at T=0, folds in silently) | Usage authority signal: hot tables, hot Streamlits, hot semantic views ranked by `distinct_users` |

> **Call #5 — `cortex_sense` tool.** If the tool is unavailable or returns empty results (error, empty `documents`, or absent `documents` key), fall back to the `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT` SQL path per `reference/CONTEXT_LOOKUP.md` and use whichever returns more documents. Any documents returned feed the Definitions row of the draft summary (pre-populate concepts/relationships/associations that are already known).

> **Call #7 — `discover_usage.py`.** This script has no dependency on the search results. Launch it at T=0 alongside the search calls. When it finishes, cross-reference its output with fast-pass results: annotate search hits that also appear in usage with `distinct_users`; add hot items not in search results; re-order the Tables row schema groups by `distinct_users` descending. Never block the fast-pass draft on deep-pass.

> **Do not call `SHOW STREAMLITS IN ACCOUNT` or `SHOW SEMANTIC VIEWS IN ACCOUNT` as part of the primary batch.** These are full-account scans that return unranked dumps. Use them only as a fallback when the corresponding search call returns nothing useful (see "Per-source fallback contract" below), or when the builder explicitly asks for a full scan.

> **`snowflake_object_search` is a CoCo MCP tool call, not a CLI command.** Call it as a function: `snowflake_object_search(search_query="...", object_types=[...], max_results=N)`. Do **not** run `cortex search object` as a bash command — that is a different interface with a plain-text output format that cannot be parsed as JSON.

> **Supported `object_types`:** `table`, `view`, `external-table`, `external-database`, `external-schema`, `database`, `schema`, `function`, `semantic-view`, `streamlit`, `bi-object`, `agent`. As with any type, an empty result just means nothing matched — fall through to the per-source fallback.

If any call fails, **do not give up on the draft**. Render what you have plus a one-line note for the source that failed (see "What to render"). Do not retry more than once.

## deep-pass — `discover_usage.py` (usage authority signal)

Launch at T=0 as a **single background command via the Bash tool's `run_in_background=true`**. Runs three `ACCOUNT_USAGE` queries in parallel — each fails independently without blocking the others.

```bash
# Launch with the Bash tool's run_in_background=true; redirect stdout to back the refresh contract.
uv run --project <SKILL_DIR>/.. python <SKILL_DIR>/../scripts/discover_usage.py \
    --lookback-days 30 \
    --connection <connection> \
    > <WORKSPACE_DIR>/deep_pass_results.json
```

Where `<connection>` is the active Snowflake connection name (same value used for all `snow sql` calls in this session).

> **Never hand-roll backgrounding.** Do not `cat >` a `.sh` wrapper, and do not use `nohup` / `&` / `disown` / heredoc redirection — use `run_in_background=true` on this one command. Hand-rolled backgrounding is where the scary script and the shell-quoting bugs come from. Poll via the Bash tool's background-output mechanism and/or the `deep_pass_results.json` file.

Output JSON shape:

```json
{
  "hot_tables":     [{"fqn": "...", "domain": "...", "access_count": N, "distinct_users": N, "last_accessed": "..."}],
  "hot_streamlits": [{"fqn": "...", "query_count": N, "distinct_users": N}],
  "hot_svs":        [{"fqn": "...", "access_count": N, "distinct_users": N, "last_accessed": "..."}],
  "fallbacks":      {"hot_tables": "no_access_history", ...}
}
```

`fallbacks` is present only when a query failed; a missing key means success. Noise filtering is applied internally: `TEMP.*` and `_PREVIEW__` items with `distinct_users < 5` are dropped.

**Hot tables** — `ACCESS_HISTORY` on `objectDomain IN ('Table', 'View')`, `LIMIT 200`. Starts at `--lookback-days`; auto-widens to 90 days if fewer than 3 distinct schemas are returned. Used two ways:
1. As candidate `pattern` rules for catalog scope (roll up by schema).
2. To order schema groups in the Tables summary row by `distinct_users` descending.

**Hot Streamlits** — `AGGREGATE_QUERY_HISTORY` `query_tag` parsing on `StreamlitName`, `LIMIT 100`. Fold in: annotate fast-pass search hits that also appear here with `distinct_users`; add usage-only apps so the agent can judge relevance.

**Hot semantic views** — `ACCESS_HISTORY` on `objectDomain = 'Semantic View'`, `LIMIT 50`. Same annotation pattern as hot Streamlits.

If `ACCESS_HISTORY` or `AGGREGATE_QUERY_HISTORY` is restricted in this account, the relevant key in `fallbacks` is set and the array is empty. Render `popularity unknown` for the affected row and continue — do not retry against `QUERY_HISTORY` text parsing.

## Streamlit and semantic view fallback — never Python keyword filtering

Search (call #3 for Streamlit, call #2 for semantic views) is always the first and preferred source. **Do not run `SHOW STREAMLITS IN ACCOUNT` or `SHOW SEMANTIC VIEWS IN ACCOUNT` unless search returned nothing useful.**

**Fallback rules (only when search returns 0 results or clearly irrelevant results):**

- **Streamlit:** Run `SHOW STREAMLITS IN ACCOUNT`. This may return hundreds to tens of thousands of apps — **do not filter with Python keyword matching**. Take the **top 15 by `last_altered_on` descending** as the candidate set and surface this as: *"Showing 15 most recently modified Streamlit apps (no search results for this use case)."*
- **Semantic views:** Run `SHOW SEMANTIC VIEWS IN ACCOUNT`. The total count is typically small — include all results without filtering.

**Full-scan mode:** If the builder explicitly asks to "show all Streamlit apps" or "scan everything", then and only then run the `SHOW` commands unconditionally and surface the full (or recency-ranked) list.

The same principle applies to any future source with large unranked dumps: search first, `SHOW` only on fallback or explicit request.

> **Streamlit content resolution.** Discovery returns a Streamlit app's FQN and metadata; resolving where its *source code* lives is a separate step owned by `INSTRUCTIONS.md` "Streamlit content-path rule". Run `DESCRIBE STREAMLIT <fqn>` and branch on the location column: `root_location` (`@DB.SCHEMA.STAGE`) is read directly; `source_location` (`snow://workspace/...`) means the app is **Workspace-backed** — the build can't read it in place, so copy it to a stage per `LOCAL_FILES.md` "Workspace-backed Streamlit apps → stage". Never silently drop a workspace app.
>
> **Bulk inclusion readability gate.** When discovery finds multiple Streamlit apps in a schema, batch `DESCRIBE STREAMLIT` to check `root_location` before proposing content sources. Annotate the Streamlit summary row with the readability split (e.g. "M stage-backed, N not stage-backed"). See `INSTRUCTIONS.md` "Streamlit content-path rule" → "Bulk inclusion" for the limit and rule-emission details.

## Cross-source enrichment

After the dashboards (Streamlit + Horizon-reachable BI assets) and external tables (Horizon-reachable non-Snowflake DBs) come back:

1. For each dashboard, extract the tables it references (table name in `query_text`, dataset reference, etc.).
2. For each external table, treat its FQN as a candidate already in scope; if it joins (in any visible query history) to Snowflake tables, those Snowflake tables are also candidates.
3. Roll those tables up by schema.
4. Add the top schemas as candidate `pattern` rules in the catalog scope, **with a `description: "referenced by <dashboard>"` or `description: "joins to <external table>"`** so the builder sees why.

The builder should not have to coach CoCo into doing this. If the discovery draft has dashboards or external tables but no catalog rules derived from them, the draft is incomplete.

Same rule for semantic views: if a semantic view references tables that aren't already in the catalog scope, add them as candidates.

## What to render — banner rules

For each source after the parallel batch returns:

| search tool | fallback | What to render |
|---|---|---|
| ✓ returned N | — | Just show the N results. **No banner.** |
| 0 | ✓ returned N | Just show the N results. **No banner.** |
| 0 | 0 | `no <source> found` |
| 0 | not implemented today | `<source> not yet supported — coming soon` (link to `DASHBOARDS.md` "see also" tip when applicable) |
| failed once and we already retried | (any) | `<source> unavailable right now — continuing without it` |

The phrase **"search not yet supported — fallback returned N results"** is **deprecated**. Do not emit it. If the fallback worked, just render the results.

## Per-source fallback contract

If multiple sources need a fallback, run those fallbacks in **parallel** — same rule as the primary batch.

| Source | Primary (search) | Fallback (only if search returns nothing useful) | If both fail |
|---|---|---|---|
| Tables / schemas | call #1 — `object_types` includes `table`, `view`, `database`, `schema` | `INFORMATION_SCHEMA.TABLES` count grouped by schema (top 50) | `no tables found` |
| External tables (Databricks / SQL Server / PostgreSQL / Redshift / dbt) | call #1 — `object_types` includes `external-table`, `external-database` | n/a (search is the only path) | `no external tables found` |
| Semantic views | call #2 — `object_types=["semantic-view"]` | `SHOW SEMANTIC VIEWS IN ACCOUNT` (full list, small N) | `no semantic views found` |
| Streamlit apps | call #3 — `object_types=["streamlit"]` | `SHOW STREAMLITS IN ACCOUNT` top 15 by `last_altered_on` desc — **no keyword filter** | `no Streamlit apps found` |
| BI objects (Tableau / Power BI / Sigma / Looker) | call #4 — `object_types=["bi-object"]` | n/a (search is the only path) | `no BI objects found` |
| Tags | metadata `tags` field on call #1's results | `SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES` count grouped by tag | `no tags found` |
| Hot tables (popularity) | n/a | deep-pass `discover_usage.py` `hot_tables` output | `popularity unknown` |
| `dbt` (source: `dbt_projects`) | builder names a stage path to `manifest.json`; auto-detection not supported | n/a | Render as a pending ask in the Optional section: `dbt  e.g. @DB.SCHEMA.STAGE/target/manifest.json` |
| `Files` (source: `stage_files`) | builder adds a stage file (doc, CSV, Power BI model); auto-detection not supported | n/a | Omit from section 1; surface in Optional if the builder mentioned documents but hasn't given a path yet |

> **Discovery vs content.** BI objects and external tables are **discoverable** via search, just like Streamlit apps — discovery returns their metadata. Searching the *content* of these assets (a dashboard's internal queries/fields/definitions, an external table's row data) is **not yet supported**. A platform only appears in results if it is connected to the account via a Horizon Context connector; see `DASHBOARDS.md` for the connector "see also" tip when a platform is plausibly relevant but not connected.

## Feeding the summary rows

The whole point of discovery is a **comprehensive draft**, so the rendered summary (`SUMMARY_FORMAT.md`) should be rich, not a single line. Every discovery output maps onto a specific summary row — populate **every** row you have data for; omit a row only when there is genuinely nothing for it.

| `SUMMARY_FORMAT.md` row | Fed by |
|---|---|
| `Tables` | call #1 table/view hits **plus** deep-pass `hot_tables`. Group by schema and render **one `pattern` rule per in-scope schema**, ordered by `distinct_users` descending once deep-pass lands — do **not** collapse to a single schema when several are active. Append the excluded-patterns sub-line for any `excluded: true` rules. |
| `Dashboards` | Streamlit hits (call #3) annotated with `distinct_users` from deep-pass `hot_streamlits` |
| `External tables` | external-table and external-database hits from call #1 — one sub-line per non-Snowflake DB/connector (includes `dbt` via Horizon Context, Databricks, Redshift, PostgreSQL, SQL Server). Store `connector` from the search result to disambiguate. |
| `External dashboards` | BI-object hits (call #4) — one sub-line per platform (`Tableau`, `Power BI`, `Sigma`, `Looker`) |
| `Semantic views` | call #2 hits annotated with `distinct_users` from deep-pass `hot_svs` (fallback: `SHOW SEMANTIC VIEWS IN ACCOUNT`). **The `semantic_views` source must always have at least one explicit `pattern` rule** — neither a missing `rules` key nor `rules: []` is valid (both scope to every SV in the account and the validator rejects them). Write one rule per discovered SV using its full FQN (`DATABASE.SCHEMA.SV_NAME`). If specific FQNs are not yet resolved, fall back to a database-scoped wildcard (`DATABASE.SCHEMA.*`) — but always include the database name at minimum. |
| `Tags` | tag metadata on call #1's results (fallback: `TAG_REFERENCES`) |
| `dbt` | source name: `dbt_projects` (`snowflake_content`). Populated only when the builder has named a stage path to `manifest.json`. Discovery does not auto-detect dbt manifests — if none named, surface as a pending ask in the Optional section. |
| `Files` | source name: `stage_files` (`snowflake_content`). Populated only when the builder has explicitly added a stage file (business doc, CSV, Power BI model). Not auto-detected during discovery. |
| `Definitions` / `Instructions` | call #5 `cortex_sense` documents (pre-existing context for this domain) + builder declarations classified per `INSTRUCTIONS.md` |

**Under-run check:** if the draft renders only a single `Tables` line and nothing else, discovery under-ran. Before rendering, re-check the hot-tables rollup (it should yield several schema groups) and the per-type search results (#2–#4 populate Dashboards / Semantic views / External tables). A healthy first draft for a real account typically shows multiple table groups plus at least one of Dashboards / Semantic views / Tags.

## Builder hints

The builder may already know which schemas matter — they are not helpless without discovery. If they named schemas in the trigger ("set up sales context, focus on `SALES.DATA.*`") or pasted a doc with FQNs, fold those in **before** the parallel batch finishes. Discovery then either confirms the choice or surfaces additional candidates.

## Don't over-research

fast-pass (calls #1–#6) should return in single-digit seconds — render the draft immediately when those finish. deep-pass (`discover_usage.py`) streams in later. If deep-pass is taking too long and the builder is waiting, render the draft from fast-pass alone and let deep-pass fold in when it arrives. Never block the conversation on a slow ACCOUNT_USAGE query.

## Do not drop already included sources

When iterating on the draft per the user's request, keep the existing sources as-is unless the user explicitly asks to drop them. Adding new ones is additive — never silently remove sources the builder previously confirmed.

---

## Pass 2 — second wave (automatic, runs once)

The point of the second wave is to **derive a richer set of searches from what Pass 1 already found**, then re-search all sources. It runs **once, automatically**, right after the fast-pass draft renders — the builder should never have to push CoCo to "look harder". Further rounds happen only when the builder types `deeper` (which reuses the heavier machinery below).

```
Pass 1 (fast-pass)  →  render draft immediately
      │
      ▼
Pass 2 — second wave (automatic, once)
  a. Harvest grounded vocabulary from pass-1 objects   (SQL/SHOW — deterministic, cheap)
  b. Compute hot DB/schema names                       (frequency over pass-1 tables + hot_tables)
  c. Expand into related keywords                      (ORCHESTRATOR reasoning — NO CORTEX.COMPLETE)
  d. Show derived keywords to the builder; let them prune  (transparency, D6)
  e. Re-search ALL sources with the new keywords + schema-scoped SHOWs
  f. Drop anything already in scope; propose only net-new; fold into the draft
```

**Why no `CORTEX.COMPLETE` for keyword expansion.** The orchestrator is already an LLM. A `CORTEX.COMPLETE` call would be an LLM calling an LLM — redundant, and it drags in model-availability/region fragility (e.g. `claude-3-5-sonnet` may be unavailable in-region), extra cost/latency, and fenced-JSON parsing. Keyword expansion is a pure reasoning step over SQL-harvested vocabulary — do it in-context.

### a. Grounded vocabulary harvest

Pull real, account-specific terms from the objects Pass 1 already found (deterministic SQL — no model call):

```sql
-- table-level domain vocabulary
SELECT table_name, comment
FROM <DB>.INFORMATION_SCHEMA.TABLES
WHERE table_schema = '<SCHEMA>' AND comment IS NOT NULL;

-- column-level vocabulary
SELECT column_name, comment
FROM <DB>.INFORMATION_SCHEMA.COLUMNS
WHERE table_schema = '<SCHEMA>' AND comment IS NOT NULL;
```

Also mine semantic-view synonyms from `DESCRIBE SEMANTIC VIEW <sv_fqn>` (e.g. `GMV → ["revenue", "gross merchandise value"]`). Together these yield concrete terms like *freight value, delivery status, review score, business segment* that seed better searches.

### b–c. Hot schemas + keyword expansion

Compute the hot DB/schema names by frequency over the Pass-1 tables plus deep-pass `hot_tables`. Then, **as an orchestrator reasoning step**, expand the harvested vocabulary + the use-case domain into ~10–15 related keywords (dedup). No `CORTEX.COMPLETE`.

### d. Transparency (D6)

Show the derived keywords to the builder and let them prune, on the draft render:

```
_(I found these by keyword-searching your catalog and by scanning the schemas your
tables live in, then expanding into related terms: <k1>, <k2>, … — tell me anything I missed.)_
```

### e. Schema-keyed re-search

Re-run the Pass-1 search calls with the expanded keywords, **and** run these schema-scoped lookups for each hot DB:

```sql
-- Semantic views DEFINED in a hot DB
SHOW SEMANTIC VIEWS IN DATABASE <DB>;

-- Streamlit apps in a hot DB (surfaces apps an account-wide dump buries)
SHOW STREAMLITS IN DATABASE <DB>;
```

**Semantic views whose PHYSICAL tables live in a hot DB (D1 / D5):** `OBJECT_DEPENDENCIES` does **not** capture semantic views, so DESCRIBE each SV candidate and keep the ones whose base tables are in the hot DB. Cap the loop at **≤25** candidates.

```sql
DESCRIBE SEMANTIC VIEW <sv_fqn>;
-- keep rows where BASE_TABLE_DATABASE_NAME = '<DB>'
```

> **DB-scoped `SHOW … IN DATABASE` is allowed here** — it is cheap and returns exactly the scoped objects. This is **distinct** from the account-wide `SHOW STREAMLITS IN ACCOUNT` / `SHOW SEMANTIC VIEWS IN ACCOUNT` that the primary batch forbids (those return unranked full-account dumps). Use the DB-scoped form freely in Pass 2; still avoid the account-wide form except as the documented fallback.

### D2 — never silently skip related semantic views

When the builder **explicitly asks for related semantic views**, run both the account/DB-scoped SV search **and** the DESCRIBE base-table match, then report the outcome explicitly — *"found N"* or *"found none"*. Never drop the SV search silently.

### Guardrails

- **One** automatic expansion round. Further rounds only via `deeper`.
- Cap the keyword set at ~10–15 after dedup; cap net-new searches.
- Deduplicate candidates against existing pattern rules; propose only net-new (schema-level).
- Keep the "do not drop already-included sources" rule.

---

## Deeper discovery (triggered by builder typing `deeper`)

A second pass that finds adjacent tables and dashboards not caught by keyword search. Run all four sub-steps via `snow sql`, then re-render the summary. See `setup/SKILL.md` §9 Branch: `deeper` for orchestration.

### Pattern substitution

`catalog_objects` scope is pattern-based, not FQN-based. Convert each `pattern` rule to a `LIKE` condition before substituting into SQL:

- `DB.SCHEMA.*` → `LIKE 'DB.SCHEMA.%'`
- `*.SCHEMA.*` → `LIKE '%.SCHEMA.%'`
- `SCHEMA.*` → `LIKE 'SCHEMA.%'`

Combine with `OR`. If more than 10 patterns exist, use the top 10 by `distinct_users` from the deep-pass `hot_tables` output (most active schemas first).

### Query A — Co-occurrence: tables accessed alongside in-scope tables

Finds tables that users query in the same sessions as in-scope tables — strong signal for data belonging to the same domain.

```sql
SELECT
  other_obj.value:"objectName"::STRING AS adjacent_fqn,
  COUNT(*) AS co_access_count,
  COUNT(DISTINCT user_name) AS distinct_users
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY,
     LATERAL FLATTEN(input => direct_objects_accessed) known_obj,
     LATERAL FLATTEN(input => direct_objects_accessed) other_obj
WHERE query_start_time > CURRENT_TIMESTAMP - INTERVAL '30 days'
  AND (
    known_obj.value:"objectName"::STRING LIKE '<pattern_1>'
    OR known_obj.value:"objectName"::STRING LIKE '<pattern_2>'
    -- one OR clause per pattern rule
  )
  AND NOT (
    other_obj.value:"objectName"::STRING LIKE '<pattern_1>'
    OR other_obj.value:"objectName"::STRING LIKE '<pattern_2>'
  )
  AND other_obj.value:"objectDomain"::STRING IN ('Table', 'View')
GROUP BY 1
HAVING distinct_users >= 2
ORDER BY co_access_count DESC
LIMIT 50;
```

Skip gracefully if `ACCESS_HISTORY` is restricted. Propose results as net-new `pattern` rule candidates with echo: *"also queried alongside your tables"*.

### Query B — Dashboard ↔ table cross-reference (Streamlit)

Bidirectional link between Streamlit dashboards and tables via `ACCESS_HISTORY` + `QUERY_HISTORY` `query_tag`.

**Tables read by in-scope Streamlit dashboards** — surfaces tables the dashboard uses that may not yet be in scope.

> **Guard:** only run this query if at least one Streamlit FQN was returned by the fast-pass `snowflake_object_search` call #3. If fast-pass found 0 Streamlit apps, skip this direction entirely.

```sql
SELECT
  TRY_PARSE_JSON(qh.query_tag):"StreamlitName"::STRING AS streamlit_fqn,
  ah_flat.value:"objectName"::STRING AS table_fqn,
  COUNT(*) AS access_count
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah
JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY qh ON ah.query_id = qh.query_id
, LATERAL FLATTEN(input => ah.direct_objects_accessed) ah_flat
WHERE ah.query_start_time > CURRENT_TIMESTAMP - INTERVAL '30 days'
  AND qh.query_tag LIKE '%StreamlitName%'
  AND ah_flat.value:"objectDomain"::STRING IN ('Table', 'View')
  AND TRY_PARSE_JSON(qh.query_tag):"StreamlitName"::STRING
      IN (<Streamlit FQNs from fast-pass call #3 — exact string values>)
GROUP BY 1, 2
ORDER BY 1, 3 DESC;
```

Propose `table_fqn` results as `catalog_objects` candidates with echo: *"referenced by `<streamlit_fqn>`"*.

**Streamlit dashboards that query in-scope tables** — surfaces dashboards not yet in the Dashboards row:

```sql
SELECT
  TRY_PARSE_JSON(qh.query_tag):"StreamlitName"::STRING AS streamlit_fqn,
  COUNT(DISTINCT qh.query_id) AS query_count
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah
JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY qh ON ah.query_id = qh.query_id
, LATERAL FLATTEN(input => ah.direct_objects_accessed) ah_flat
WHERE ah.query_start_time > CURRENT_TIMESTAMP - INTERVAL '30 days'
  AND qh.query_tag LIKE '%StreamlitName%'
  AND (
    ah_flat.value:"objectName"::STRING LIKE '<pattern_1>'
    OR ah_flat.value:"objectName"::STRING LIKE '<pattern_2>'
  )
GROUP BY 1
HAVING streamlit_fqn IS NOT NULL
ORDER BY 2 DESC
LIMIT 20;
```

Propose `streamlit_fqn` results as candidates for the Dashboards row with echo: *"queries your tables"*.

> Horizon BI objects (Tableau, Power BI) do not produce `StreamlitName` query tags — their queries run through the BI tool's own connection. Use Query C for Horizon object lineage.

### Query C — Object dependencies: semantic lineage

Finds views, tasks, and other objects that directly reference or are referenced by in-scope schemas via Snowflake's built-in lineage graph.

```sql
SELECT DISTINCT
  CASE WHEN (
    referencing_object_name LIKE '<pattern_1>'
    OR referencing_object_name LIKE '<pattern_2>'
  ) THEN referenced_object_name
    ELSE referencing_object_name END AS adjacent_fqn,
  CASE WHEN (
    referencing_object_name LIKE '<pattern_1>'
    OR referencing_object_name LIKE '<pattern_2>'
  ) THEN 'downstream' ELSE 'upstream' END AS direction,
  referencing_object_type
FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES
WHERE referencing_object_name LIKE '<pattern_1>'
   OR referencing_object_name LIKE '<pattern_2>'
   OR referenced_object_name  LIKE '<pattern_1>'
   OR referenced_object_name  LIKE '<pattern_2>'
LIMIT 100;
```

Skip gracefully if `OBJECT_DEPENDENCIES` is unavailable. Upstream results are candidates for `catalog_objects` with echo: *"upstream dependency"*. Downstream results are context only — do not automatically add to scope.

### Using results

- Deduplicate to **schema level** — propose `DB.NEW_SCHEMA.*` not individual table FQNs.
- Skip anything already covered by an existing pattern rule.
- Render net-new additions in the Skipped → resolved items flow (remove from Skipped, add to the appropriate summary row).
- Echo before re-rendering the box: `_(Deeper scan complete — N new candidates added)_` or `_(Deeper scan found nothing new)_`.
