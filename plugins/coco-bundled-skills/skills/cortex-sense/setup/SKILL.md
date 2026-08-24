---
name: cortex-sense-setup
description: "Set up Cortex Sense for a new use case. CoCo runs a background scan of the account the moment the use case is named, proposes a comprehensive draft domain context (tables, dashboards, semantic views, dbt, tags, hot tables from query history), accepts edits in plain English, surfaces a single batched turn of skippable asks for things it couldn't see, and persists the manifest the offline build consumes. Use when: starting a new use case, building cortex sense for a domain. Triggers: set up cortex sense, build cortex sense for <use case>, I want context for sales, set up <use case>."
parent_skill: cortex-sense
---

# Setup

## HARD RULES (read first — these override anything below on conflict)

- **NEVER save/persist the manifest until the builder explicitly confirms** by typing `build` / `ok` / `go` / `yes` (or an equivalent affirmation). Rendering the summary is **not** confirmation. The only path to save is the `build` branch in §9, which leads to §10.
- **Present scope only as the scope box** from `../reference/SUMMARY_FORMAT.md` — plain text inside a single code fence. Never a generic markdown table, never an `AskUserQuestion` / multiple-choice UI.
- **The interaction model is: summary box → builder types free-form text → echo + re-render.** Classify every edit per `../reference/INSTRUCTIONS.md`. Do not ask the builder to pick internal buckets or choose from menus.

## When to load

The user wants to set up Cortex Sense for a new domain. Routed from `SKILL.md`. If a manifest already exists for the domain, route to `refine/SKILL.md` instead.

## Setup (read once before mutating state)

- `../reference/USE_CASE_AND_CONTEXT.md` — vocabulary
- `../reference/DISCOVERY.md` — parallel discovery contract, exact SQL, fallbacks, render rules, "not yet supported" copy
- `../reference/ACCESS_PREFLIGHT.md` — the single source for the build-role access check (read-visibility preflight + grant remediation + save-time exact-source check); §7 and §10 route here
- `../reference/LOCAL_FILES.md` — uploading local files (dbt manifest, docs, SQL) and copying Workspace-backed Streamlit apps to a stage before scoping them
- `../reference/DASHBOARDS.md` — the unified dashboards concept (Streamlit + Horizon)
- `../reference/SCOPE_MANIFEST.md` — manifest shape (sources/rules with per-entry `user_prompt`, concepts/relationships/associations, pending_asks)
- `../reference/INSTRUCTIONS.md` — how to classify builder prose
- `../reference/SUMMARY_FORMAT.md` — narrative summary (exact rows, no extras)
- `../reference/NOT_YET_IMPLEMENTED.md` — exact user-facing placeholder lines

`<WORKSPACE_DIR>` and `<SKILL_DIR>` are placeholders the agent resolves.

**Flow sequence** (follow in order — do not skip steps):

```
§1 Entry checks (parallel) → §2 Open →
§3 Fast-pass + deep-pass background →
§4 Render initial draft → §5 Pass 2 (automatic) →
§6 Warehouse/role → §7 Access preflight → §8 Batched asks →
§9 Loop on edits → §10 Confirm and save
```

## 1. Entry checks (parallel)

Issue calls immediately on entry — **do not wait** for one to complete before starting the other.

### Branch A — Domain named in trigger

Fire **both** calls as parallel tool calls in the same turn:

1. **`doctor`** — `uv run --project <SKILL_DIR>/.. python <SKILL_DIR>/../scripts/persist_state.py doctor`
2. **`get-context`** — per `../reference/STORAGE.md` (checks whether a manifest already exists for this domain)

In the same turn: render the intro (§2) **and** issue both calls. The builder sees the intro immediately; results are surfaced as they arrive.

Surface results as they arrive:

- **doctor: `snow_cli == "missing"`** → stop and render once:
  > I need the Snowflake CLI (`snow`) to persist this. Install it from <https://docs.snowflake.com/developer-guide/snowflake-cli/installation/installation> and try again — I'll wait.

- **doctor: `needs_database_schema: true`** → ask once:
  > I couldn't set up the default storage location for the manifest. Tell me a database and schema I can write to (e.g. `MY_DB.CORTEX_SENSE`). This is a placeholder — the manifest will move to a native use-case object once available.

  Validate the `<DB>.<SCHEMA>` shape; after two failures, stop plainly. Set `CORTEX_SENSE_DB` / `CORTEX_SENSE_SCHEMA` env vars, re-run `doctor`. **Never** mention env-var names to the builder.

- **doctor: OK** → `storage_ready: true`; remember `storage_location` for §10's confirm block. Continue silently.

- **get-context: Context found** → a manifest already exists. Append the redirect line immediately after the intro (in place of the `▶` prompt) and stop — do not proceed to §3:
  > A Cortex Sense context for `<domain>` already exists — opening it for editing instead.
  Then route to `refine/SKILL.md`.

- **get-context: NotFound** → continue to §3 as normal. This is the expected fresh-start path.

- **get-context: Any other error** → log internally; continue to §3 (do not block setup).

### Branch B — No domain named in trigger

Fire only `doctor` immediately (in background). Proceed to §2 (intro) at once — the builder will name the domain in their first reply.

After the builder names the domain, fire `get-context` before proceeding to §3:
- Context found → route to `refine/SKILL.md` as above.
- NotFound → proceed to §3.

Skip `get-context` entirely on `@cortex-sense resume` — resume implies the context exists.

---

The user should never see `snow` tracebacks, "stage format" errors, raw tool traces, bash/python stack traces, validator error details, or internal step commentary. If a save or load fails with no recovery path, render a single plain-English sentence (per the error copy in `../reference/STORAGE.md`) and stop.

## 2. Open

**Always render the intro box** on a fresh start. The intro is skipped **only** on `@cortex-sense resume` or when `get-context` found an existing context (Branch A redirect).

- If the user named the domain in the trigger, capture it. Render the intro (while §1 checks run), then proceed **directly to §3** without re-asking for the name.
- If the user also pasted a doc / spec / schema list in the trigger, capture it as paste content and continue to §3 after the intro.
- If no domain was named, render the intro; the `▶` line at the bottom is the implicit ask — wait for the builder to name a domain before proceeding to §3.

On a **fresh start**, render this fixed intro **once**:

```
╭────────────────────────────────────────────────────────────────────╮
│         Cortex Sense — grounded context for CoCo & CoWork          │
╰────────────────────────────────────────────────────────────────────╯

  Curating context for agents by hand can't cover everything.
  Cortex Sense indexes the rest.

    your data estate today        with Cortex Sense
    ····················          ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒
    ·····█··············          ▒▒▒▒▒█▒▒▒▒▒▒▒▒▒▒▒▒▒▒
    ····················          ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒
    ··············█··█··    ──▶   ▒▒▒▒▒▒▒▒▒▒▒▒▒▒█▒▒█▒▒
    ··················█·          ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒█▒
    ····················          ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒
    mostly uncovered              every table grounded

    █ hand-curated context   · no context, agent guesses   ▒ grounded by Sense

  Agents answer well only when they have context — what your tables mean,
  how they join, how metrics are defined. Cortex Sense helps you create this
  layer from how your data is used today, starting from your queries,
  dashboards, semantic views, and dbt models. This layer is used to help
  Cortex Code, Cortex Agents, and CoWork answer questions across your
  warehouse with quality.

  How this works
    1. Scope it with me — about 10 minutes. Name a domain, I propose what
       to include, you adjust.
    2. I index it in the background — usually a few hours. It goes live
       when it's done; you don't have to wait around.
    3. We set up an eval together so you can measure it answers your real
       questions well.

  ▶ Name the domain or use case you want Sense for — eg: "sales pipeline",
    "finance reporting" — or paste a doc, spec, or schema list to start.
```

The intro is followed by **no** menu of modes, **no** "deep-dive vs paste" labels, **no** common starting points list, **no** "or if you'd like to test or refine an existing one" tail. The router in `SKILL.md` already handles re-entry.

When the builder responds (or if they named the domain in the trigger): if they paste a wall of text (typically > 200 chars, multiple lines, or contains FQNs, schema lists, definitions, etc.), treat it as paste content. If they just type a name, treat that as the domain and run discovery. If they do both ("sales — here's what I have: …"), treat the first short token as the name and the rest as paste content.

## 3. Discovery — parallel, aggressive, comprehensive on the first pass

The goal of this step is **one comprehensive draft scope**, not a thin starting point the builder has to push you to expand. Per `../reference/DISCOVERY.md`:

- At T=0, fire all of the following **at once** (they have no dependencies on each other):
  - **Fast-pass** (render draft immediately when these return, ~3–5s):
    - Four `snowflake_object_search` calls — one each for tables/external-tables, semantic views, Streamlit apps, and BI objects — seeded by the domain key question.
    - `cortex_sense(query="<domain key question>")` — existing context docs for this domain. If the tool fails or returns empty results, fall back to the `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT` SQL path per `../reference/CONTEXT_LOOKUP.md`.
    - Governance tags extracted from the tables search result.
    - **Ontology discovery** — sequential within this bullet, but the whole bullet fires at T=0: (1) `CALL SYSTEM$GET_GLOSSARY_SUMMARY()` to fetch the domain list, (2) match relevant domains, (3) `CALL SYSTEM$GET_GLOSSARY_GRAPH()` (Step 1b of `ONTOLOGY_DISCOVERY.md`) filtered by `domainId` to get per-domain relationship and association counts, and fetch registered sources. Failures skip silently; never blocks fast-pass rendering.
  - **Deep-pass** (already running at T=0 in the background): launch `discover_usage.py` per `../reference/DISCOVERY.md` "deep-pass" section as a **single background command via the Bash tool with `run_in_background=true`**, redirecting its stdout to a file:
    ```bash
    # Runs in CoCo bash sandbox (Linux) — launch with the Bash tool's run_in_background=true
    uv run --project <SKILL_DIR>/.. python <SKILL_DIR>/../scripts/discover_usage.py \
        --lookback-days 30 --connection <connection> \
        > <WORKSPACE_DIR>/deep_pass_results.json
    ```
    Poll with the Bash tool's background-output mechanism, and/or check for the result file on the next interaction (the file backs the `refresh` contract below). **Never** hand-roll a wrapper: do **not** `cat >` a `.sh` file, and do **not** use `nohup`, `&`, `disown`, or heredoc redirection to background it — use `run_in_background=true` on this one command. This both removes the scary script and avoids the shell-quoting bugs that come with hand-rolled backgrounding.
- **Render the draft the moment fast-pass calls return. Do not wait for the deep-pass.** The builder must see results in seconds, not minutes.

- **Before every re-render** (triggered by any builder input, including `refresh`): check whether `<WORKSPACE_DIR>/deep_pass_results.json` exists and has not yet been applied. If it does, read it, apply the usage signal to the scope, delete (or rename) the file so it is not applied again, and include `_(Scan complete — scope updated with usage data)_` in the status line of the next render. If the file does not exist yet, keep the status line as `_(Still scanning your query history — type **refresh** to update)_`.
- `SHOW STREAMLITS IN ACCOUNT` and `SHOW SEMANTIC VIEWS IN ACCOUNT` are **fallback only** — do not include them in the primary batch (see `DISCOVERY.md` "Streamlit and semantic view fallback").
- After the dashboards (Streamlit + any Horizon-reachable BI assets) come back, **enrich the catalog scope** with the tables those dashboards reference. This is the cross-source enrichment rule. The builder should not have to ask you to do this.

If a paste in §3 included scope hints, schema lists, definitions, or instructions, classify them per `../reference/INSTRUCTIONS.md` **before** rendering the draft. The discovery results then merge with the paste.

For each source, follow the per-source render rule in `DISCOVERY.md` ("what to render" table). When the search tool and the fallback both return non-empty, **render the results without any banner**. The "search not yet supported" line is reserved for cases where neither has anything.

## 4. Render the draft scope

Open with one plain-English line before the summary box:

```
Scan complete — here's the proposed scope for Cortex Sense for <domain>,
based on what your team actually queries.
```

Then render the scope box per `../reference/SUMMARY_FORMAT.md` (exact format, samples, and per-source rules are all there). Do not show `dbt` in the INCLUDE block — if no path was found, it belongs in section 2 (Optional). Omit section 2 entirely if no pending asks.

If ontology discovery (§3) matched at least one domain, include an `Ontology` row in the INCLUDE block per the `Ontology` row format in `../reference/SUMMARY_FORMAT.md` (four sub-lines: Nodes / Relationships / Associations / Source files). Use counts from `SYSTEM$GET_GLOSSARY_GRAPH()` filtered by `domainId` (Step 1b in `ONTOLOGY_DISCOVERY.md`) — this is the only function that returns per-domain relationship and association counts. `GET_GLOSSARY_SUMMARY` only provides `termCount` per domain and must not be used for Relationships or Associations sub-lines. Multiple matched domains: run one graph call and filter per domain. If no match, omit the row entirely.

**Output the scope box now** — do not wait for Pass 2 or the deep-pass before showing this first render. Then immediately proceed to §5 (Pass 2), §6 (warehouse/role), and §8 (batched asks) before the builder can interact. Do not skip §8.

After the scope fence:
- **Staging advisory**: Scan all `Tables` INCLUDE patterns for staging/dev conventions (`*.STG.*`, `*.STAGING.*`, `*_STG`, `*_DEV`, `*.RAW.*`, `*_TEMP`). For each match, append a one-liner advisory below the fence (never inside it), substituting the actual matched pattern: `⚠️ <MATCHED_PATTERN> looks like a staging schema — say "exclude" to remove it.` Skip patterns already in EXCLUDE.
- **Empty sources note**: Per `../reference/SUMMARY_FORMAT.md` "Empty row handling — two cases": keep user-declared pattern rules in the INCLUDE block even when discovery returns 0 (show `0 _(none yet)_`); for auto-scanned sources with nothing found and no manifest rule, omit the row and append a one-liner below the fence.

## 5. Pass 2 — automatic expansion

After §4 renders the initial fast-pass draft, **immediately** run Pass 2. This is not optional — do not wait for the builder to ask. The purpose is to derive richer searches from what Pass 1 already found.

**Tell the builder what's happening** — output this line before running any queries:

```
Expanding the search based on what I found — scanning related schemas,
harvesting vocabulary from table and column metadata, and looking for
related semantic views. One moment…
```

Then execute the full Pass 2 contract from `../reference/DISCOVERY.md` "Pass 2 — second wave" (steps a–f):

1. **Harvest grounded vocabulary** (step a): pull table/column comments from in-scope schemas via `INFORMATION_SCHEMA`. Mine semantic-view synonyms from `DESCRIBE SEMANTIC VIEW`. These yield concrete domain terms.
2. **Compute hot schemas + expand keywords** (steps b–c): identify the most-queried DBs/schemas from Pass 1. As an **orchestrator reasoning step** (never `CORTEX.COMPLETE`), expand the harvested vocabulary into ~10–15 related keywords.
3. **Show derived keywords** (step d / D6): render the keywords so the builder can see what was inferred and prune if needed.
4. **Re-search all sources** (step e): re-run the Pass 1 search calls with the expanded keywords. Also run schema-scoped `SHOW SEMANTIC VIEWS IN DATABASE <DB>` and `SHOW STREAMLITS IN DATABASE <DB>` for each hot DB.
5. **Fold in net-new candidates** (step f): deduplicate to schema level, skip anything already in scope, propose only net-new schemas.

**Also check the deep-pass background job.** Before re-rendering, check whether `<WORKSPACE_DIR>/deep_pass_results.json` exists. If it does, read and apply the usage signal (annotate tables with `distinct_users`, reorder schema groups by activity). If not yet available, keep the status line as `_(Still scanning your query history — type **refresh** to update)_`.

**Re-render the full summary** with all Pass 2 additions and any deep-pass data folded in. This is the second scope box — it supersedes the §4 draft. Both renders appear in the conversation: the §4 fast-pass draft first, then this updated version.

Apply the same post-fence checks as §4: staging advisory and empty-sources note (per `../reference/SUMMARY_FORMAT.md` "Empty row handling — two cases").

When the builder explicitly asks for related semantic views at any point, never skip the SV search silently (D2 — always report the outcome).

> **One** automatic expansion round. Further rounds happen only when the builder types `deeper`.

> ⚠️ **STOP** — by this point both the §4 draft and the §5 re-render have been output, along with the warehouse line (§6). Wait for the builder to respond before proceeding further.
>
> If any `⚠️` flags appear in the INCLUDE block (> 20 objects from a broad source), add one plain-prose line below the fence — once per initial render only: _"Heads up: some sources pulled in many objects automatically — say 'exclude' or 'only <schema>' to narrow."_

## 6. Confirm the build warehouse (required) and role

The manifest must record the warehouse the offline build runs on — the top-level `warehouse` field is **required**. The build also runs as your current role (which becomes the owning role, locked for the lifetime of this context). Surface both together, once, before the summary. Resolve them in one call:

```bash
uv run --project <SKILL_DIR>/.. snow sql --format json -q "SELECT CURRENT_WAREHOUSE() AS wh, CURRENT_ROLE() AS role;"
```

- **Warehouse non-empty** → set it as the top-level `warehouse` field and tell the builder once, in plain English (this same line confirms the build role):

  ```
  The build is configured to run as <ROLE> on warehouse <WH>.
  This role is fixed for the lifetime of this Cortex Sense — make sure it has read access to
  everything you add to scope (I'll flag any gaps). To build as a different role you'd need to
  recreate this Cortex Sense from scratch.

  Say "use warehouse <NAME>" to change the warehouse.
  ```

  If the schema `<DB>.<SCHEMA>` was created during this setup session (it did not exist before), append one additional line:
  ```
  Note: <DB>.<SCHEMA> was just created and is owned by <ROLE>. Other roles need explicit grants to resume this Cortex Sense (see reference/STORAGE.md "Schema ownership").
  ```

- **Warehouse empty / null** (the session has no active warehouse) → the field is required, so the builder must name one before the build can run. Ask once, and still confirm the role in the same turn:

  ```
  I couldn't find an active warehouse to run the build on. Which warehouse should I use? (e.g. ANALYTICS_WH)
  (The build will run as <ROLE> — this role is fixed for the lifetime of this Cortex Sense.)
  ```

  Do not proceed to save (§10) until a valid `warehouse` is set. If the builder names one, set it and continue.

If the builder later says "use warehouse X" at any point, update the top-level `warehouse` field per `../reference/INSTRUCTIONS.md`. The role is locked at setup time and is not a manifest field — it cannot be changed without recreating the Cortex Sense. Do not suggest `USE ROLE` as a way to change the build role. This announcement also covers the role for the access preflight (§7), which reuses `<ROLE>` and does not re-announce it.

## 7. Access preflight (before build)

Once the draft scope's in-scope databases are known, run the access preflight — the full contract (SQL, gap cross-check, grant remediation copy) lives in `../reference/ACCESS_PREFLIGHT.md` (steps 1–3). Do not restate its SQL here; just run it. It reuses the build role already surfaced in §6 (`<ROLE>` — do not re-announce), and renders any read-access gap **before** the build gate. No gaps → say nothing and continue.

This is a **warning, not a hard stop** — never block `build` on an access gap. The preflight also re-runs at save (§10).

## 8. One turn of batched asks

Cover the things you couldn't see automatically. Cap at **6** named, skippable items in **one** turn. Each line is one ask. Default is **skip all**.

Examples (only render the ones that apply):

```
Optional — I couldn't find these automatically. Add sources, or skip:

  [skip]  Streamlit          no apps found — list any you want included
  [skip]  Power BI           not connected via Horizon Context — enable: <link>
  [skip]  Tableau            not connected via Horizon Context — enable: <link>
  [skip]  dbt                stage path to manifest.json (e.g. @DB.SCHEMA.STAGE/target/manifest.json) — or a local repo path and I'll upload it
  [skip]  must-have tables   tables you know matter, e.g. FINANCE.REVENUE.BOOKINGS
  [skip]  business docs      e.g. @MY_DB.DOCS.STAGE/metrics_spec.pdf
  [skip]  query patterns     e.g. @MY_DB.DOCS.STAGE/revenue_queries.sql

Any local files you add (a doc, a SQL file, a dbt repo) I'll upload to
<DB>.<SCHEMA>.SENSE_SOURCES — tell me a different stage if you'd rather.
Reply with any to add it, or skip
```

Substitute `<DB>.<SCHEMA>` with the Cortex Sense storage database/schema from the doctor output (default `TEMP.CORTEX_SENSE`).

Sourcing rules:
- Render `Streamlit` **only** when discovery returned 0 Streamlit apps. If apps were found (they appear in the `Streamlit Apps` INCLUDE row), omit this ask.
- Render a BI platform row (Power BI, Tableau, Sigma, Looker) **only** when that specific platform returned 0 results in discovery. If it already appears in the `External Dashboards` INCLUDE row, do **not** ask about it again — it's already in scope. See Snowflake Horizon Context docs for available connectors.
- Render `dbt` **only** when no dbt manifest path was discovered. Do not show dbt in the main summary if no path is found — the ask here is sufficient.
- If the builder gives a **local** file path (dbt repo, doc, or SQL — anything not a `@stage` FQN), follow `../reference/LOCAL_FILES.md`: explain the build reads from stages, upload the file with `PUT` to the default `<DB>.<SCHEMA>.SENSE_SOURCES` stage (or a stage the builder names), and record the resulting stage FQN. Never record a local `file://` path, and never silently drop it.
- If an in-scope Streamlit app is **Workspace-backed** (`DESCRIBE STREAMLIT` returns a `snow://workspace/...` `source_location` instead of a stage `root_location`), the build can't read it directly. Follow `../reference/LOCAL_FILES.md` "Workspace-backed Streamlit apps → stage": ask for a target stage, copy the app's source there, and record it as a normal `streamlit_apps` `file` rule. Never copy silently, and never drop the app — offer the deploy-to-stage alternative if the builder prefers.
- **Streamlit readability gate** — When Streamlit apps were found (appear in the `Streamlit Apps` INCLUDE row), run the bulk readability check and render asks per `../reference/INSTRUCTIONS.md` "Streamlit content-path rule" → "Bulk inclusion".
- Render `must-have tables` whenever the catalog scope was inferred mostly from query history (because quiet but important tables are precisely what query history misses).
- Render `business docs` and `query patterns` only when the domain looks definition-heavy (multiple metrics in the draft) or workflow-heavy.
- Cap at 6 asks total. If all apply, prioritize: Streamlit → BI platforms → dbt → must-have tables → business docs → query patterns.

Whatever the builder fills in, classify and apply per `../reference/INSTRUCTIONS.md`. Items the builder skips are **not lost** — they go into the manifest as `pending_asks` entries with `provenance.state: needs-feedback` and `provenance.origin: inferred-shown-to-user`. When the builder revisits them in `refine/`, the ask is removed and the classified answer is added to the correct field with `provenance.state: approved`. See `../reference/SCOPE_MANIFEST.md` "Provenance".

After applying any answers, re-render the summary per §4.

## 9. Loop on edits, then confirm

The scope box always ends with the footer bar. Below the box (as plain prose, outside the fence), add once per initial render:

```
Next: reply with anything above to include more scope, or type "build" to start.
When you build, a background job turns this scope into the internal
knowledge CoCo uses to answer questions about your data. It can take minutes or hours
depending on the scope, and runs on your warehouse <WH>. You can narrow the scope anytime.
```

Substitute `<WH>` with the resolved warehouse from §6.

**Before every re-render**, check for `<WORKSPACE_DIR>/deep_pass_results.json` (see §3). Apply it silently if present.

**`refresh`**: Check for the deep-pass result file. If it exists, apply and re-render with `_(Scan complete)_` — and drop `refresh` from the footer bar (discovery is done). If not yet available, re-render with `_(Still scanning your query history — type **refresh** to update)_`. No other action.

**`clean up`** / **`deduplicate`** / **`remove low-quality sources`**: route to the `clean up` branch below.

**Free-form text** (anything other than `help`, `deeper`, `refresh`, `build`, `clean up`, `deduplicate`, `remove low-quality sources`): classify per `../reference/INSTRUCTIONS.md`. Update local state. Render the **echo line** for the change (single sentence, present tense). Then re-render the full scope box. Loop.

When an edit produces or changes a scope rule, store the builder's verbatim phrasing as the **`user_prompt`** field on that `sources[].rules[]` entry (or on the concept/relationship/association it produced). See `../reference/SCOPE_MANIFEST.md`.

### Branch: `help`

Analyse the current in-memory draft. Render a contextual improvement card **outside** the summary box (below it, as plain prose — not inside the code fence). Three categories:

- **Missing** — for each absent row (no items at all), one bullet with **two or more** plain-English examples of what can go there.
- **Can improve** — for rows that are present but thin, or common gaps; again **two or more** examples per bullet where applicable.
- **Advanced** — always include the `deeper` keyword hint, plus example **discovery/instruction phrases** the builder can type (not just `deeper`).

Example card (only render bullets that apply; cap at ~10 total across Missing + Can improve):

```
What you can add:

  Missing
    Tables              "add SALES.ORDERS.*" · "include ANALYTICS.MARTS.FACT_ARR" ·
                        "tables the revenue dashboard reads"
    Streamlit Apps      "add @ACCT.APP.SALES_PIPELINE" · "include the bookings Streamlit"
    External Tables     connect Databricks/Postgres via Horizon, then "include Databricks
                        catalog prod_analytics"
    External Dashboards enable Tableau or Power BI via Horizon · "include the Executive
                        Revenue workbook"
    Semantic Views      "add PIPELINE_SV and BOOKINGS_SV" · "include semantic views for sales"
    Tags                "include everything tagged finance_certified" ·
                        "find all tables tagged SALES_CRITICAL"
    Definitions         "DAU is COUNT(DISTINCT user_id)" · "define ARR as annualized bookings" ·
                        "ARR derives from bookings"
    Instructions        "filter ds = max(ds) on snapshot tables" · "default to ARR when someone
                        says revenue"
    Files               upload a spec or SQL workbook to a stage and paste the path —
                        "business doc at @MY_DB.DOCS.STAGE/sales_metrics.pdf" ·
                        "query patterns at @MY_DB.DOCS.STAGE/revenue_queries.sql"

  Can improve
    Tables              "exclude ANALYTICS.STAGING.*" · "only gold tables in SALES.DATA" ·
                        "dbt at @DB.SCHEMA.STAGE/target/manifest.json" (adds lineage)
    Streamlit Apps      "exclude @ACCT.APP.EXPERIMENT_*" · "drop the sandbox Streamlit apps"
    Tags                "only gold and finance_certified" · "scope by SALES_CRITICAL tag only"
    Definitions         "ARR lives in ANALYTICS.MARTS.FACT_ARR" · "churn rate means …"
    Instructions        tie-breaks, safe-answer rules, workflow notes ("explain the limitation
                        instead of inferring")
    Optional section    answer pending asks — dbt manifest path · stage path for docs or notebooks

  Advanced
    type: deeper        co-occurrence, Streamlit↔table, and lineage scans for net-new schemas
    you can also type   "find all tables tagged SALES_CRITICAL" ·
                        "include schemas that co-occur with SALES.DATA in queries" ·
                        "add upstream dependencies of FACT_ARR" ·
                        "search for anything related to churn or retention" ·
                        "add tables referenced in @MY_DB.DOCS.STAGE/revenue_spec.pdf"
```

Scoping rules:
- "Missing" bullets only for rows with zero items. Include **files** under Missing when the Optional section has a `business docs` or `query patterns` pending ask, or when definitions/instructions are empty and the domain looks definition- or workflow-heavy.
- "Can improve" only for thin rows or obvious gaps (e.g., large table set with no exclusion rules; domain name implies metrics but Definitions is absent; pending asks still in section 2).
- **Advanced** always includes the `deeper` keyword line **and** at least three example discovery/instruction phrases tailored to the draft (reuse tag names, schema prefixes, or table names already visible when possible).
- If everything looks complete, show "scope looks thorough" and the Advanced block only.

Do **not** re-render the summary box after the help card. The card stands on its own — the builder reads it and types their next action. The summary re-renders on the next edit, `deeper`, `refresh`, or `build`.

### Branch: `deeper`

Before running any queries, output exactly this message — no improvisation:

```
Running a deeper scan — this looks at query co-occurrence, dashboard-table
relationships, and object lineage across your account. It may take a couple
of minutes. I'll update the scope when it finishes.
```

Then kick off the second discovery pass using SQL from `../reference/DISCOVERY.md` "Deeper discovery". Run all four sub-steps before re-rendering:

1. **Query A — Co-occurrence** (`snow sql`): tables accessed in the same query sessions as in-scope pattern schemas. Uses `LIKE` conditions built from pattern rules. Skip gracefully if `ACCESS_HISTORY` is restricted.
2. **Query B — Dashboard ↔ table** (`snow sql`): bidirectional — which tables do in-scope Streamlits read, and which Streamlits query in-scope tables. Streamlit FQNs from fast-pass results are used as exact `IN` values; if fast-pass returned 0 Streamlit apps, skip the first half of Query B entirely (empty `IN ()` is invalid SQL) and run only the second half. Horizon BI objects not covered by this query.
3. **Query C — Object dependencies** (`snow sql`): upstream/downstream via `OBJECT_DEPENDENCIES`. Uses `LIKE` conditions from pattern rules. Skip gracefully if unavailable.
4. **Expanded keyword search**: re-run `snowflake_object_search` with 1–2 alternative phrasings of the domain question. Merge with existing results.

For each result, deduplicate to schema level and skip anything already covered by an existing pattern rule. Propose only net-new schemas. Render a brief echo before re-rendering the box:
- `_(Deeper scan complete — N new candidates added)_`
- `_(Deeper scan found nothing new)_`

After the echo, re-render the full scope box. The builder can type `deeper` again at any time.

### Branch: `clean up` / `deduplicate` / `remove low-quality sources`

Run two heuristics against the current in-scope `Tables` rules and surface findings as an advisory block outside the fence — never auto-remove:

1. **Staging names** — flag included patterns matching staging/dev conventions: `*.STG.*`, `*.STAGING.*`, `*_STG`, `*_DEV`, `*.RAW.*`, `*_TEMP`. Suggest excluding each, e.g. `"ANALYTICS.STAGING.* (~8 tables) — looks like a staging schema. Say 'exclude' to remove."` Skip rules already in EXCLUDE.
2. **Include/exclude overlap** — flag any included pattern that is a subset of an existing EXCLUDE rule (same DB prefix, narrower glob). Note the redundancy and offer to remove.

If neither heuristic finds anything: `Scope looks clean — no obvious staging or redundant patterns found.`

### Branch: `build` (or "ok" / "go" / "yes")

> ⚠️ **This is the ONLY path to saving.** Do **not** proceed to §10 unless the builder explicitly confirms.
> Valid triggers: `build`, `ok`, `go`, `yes`, or an equivalent affirmation.
> Presenting the summary is **NOT** confirmation. If the builder types anything else, treat it as an edit (§9) and re-render — do not save.

## 10. Confirm and save

1. Make sure every rule, concept, relationship, and association carries its verbatim `user_prompt`. Do **not** write a resolved FQN snapshot — the build re-derives scope from `sources[].rules` on each run and owns its own diff baseline (see `../reference/SCOPE_MANIFEST.md` "Scoping seeds; building discovers"). The top-level `warehouse` field is **required** and must be set (see §6); do not save without it.

   **Save-time access check:** before the save calls, run the access check per `../reference/ACCESS_PREFLIGHT.md` — re-run the visibility preflight (steps 1–3) if scope databases changed since §7, and run the final check on exact resolvable sources (step 5; wildcard/pattern rules, BI/external sources, and ontology are skipped there). Surface any gap once with the grant remediation from that file, then continue — a warning, not a blocker.

2. **Before running any save calls**, output exactly this line — do not improvise a different progress message:

   ```
   Saving Cortex Sense scoping instructions for <domain>…
   ```

3. **Save the manifest:** Assemble the manifest as YAML in-memory. Pipe it through `scripts/persist_state.py merge` (deduplicates `additional_instructions`, validates). Then run two SQL calls per `../reference/STORAGE.md` "Saving — two calls in sequence":
   - **create-context** → registers the domain context.
   - **put-stage-file** (path: `scope.yaml`, content: JSON-escaped manifest YAML, overwrite: true) → writes the manifest to the internal stage.

4. Treat "already exists" on `create-context` as success. On any other error, render the one-line warning from `../reference/STORAGE.md` and stop.

5. **Trigger a reprocess:** call `force-reprocess` per `../reference/STORAGE.md` "Force-reprocessing a context". This is non-blocking — if it fails, continue to step 6 without surfacing the error to the builder.

6. Render the confirm block **verbatim** from `../reference/SUMMARY_FORMAT.md` §"On confirm", substituting only `<domain>` (the domain name). The block is the canonical copy — do not rewrite or reorder its bullets here.

**Do not** offer "save as draft", "share for review", or "activate now". The builder confirmed once; the build runs.

**Do not** narrate internal steps to the builder. Never say "manifest", "state.yaml", "merge", "persist", or "save to stage" in builder-facing text. Never generate a progress message other than the prescribed `Saving Cortex Sense scoping instructions for <domain>…` line above. The confirm block from `SUMMARY_FORMAT.md` is the only builder-facing output after confirmation.

## What this skill never does

- Use `AskUserQuestion` / any multiple-choice or picker UI for scope decisions — the three-section summary box plus free-form text is the entire interaction model
- Open with a menu of scoping modes ("how much of your data should this context cover?")
- Offer hand-curated "common starting points" (`sales_ops`, `finance_reporting`, …)
- Render a 9-row checkbox grid of internal sources
- Use the word "Snowscope" or "snowscope" in any user-facing or agent-facing copy
- Surface `draft` / `active` / `version_id` to the builder
- Ask the builder to pick `concepts` vs `relationships` vs `additional_instructions`
- Add summary rows beyond the nine in `../reference/SUMMARY_FORMAT.md`
- Run discovery sequentially when it can run in parallel
- Filter `SHOW STREAMLITS` results with Python keyword matching (use search tool re-ranking — see `DISCOVERY.md`)
- Show raw tool traces, `snow sql` output, bash/python stack traces, or `persist_state.py` validator detail lines in the conversation
- Narrate internal retry attempts, pass-by-pass fallback logic, or connection debugging steps
- Surface messages about `INVALID_ARGUMENT`, `stage format` errors, or internal storage mechanics
- Show CoCo's own reasoning steps or intermediate tool results inline
- Use the term "usage signal applied" or other internal pipeline language in user-facing copy
