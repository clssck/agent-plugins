# Summary format

Render this format whenever showing the current state of the domain context. Builder vocabulary, not internal source names. **Narrative summary, not a 9-row checklist.**

## When to render

- `setup/SKILL.md` — after discovery (the proposed draft) and after each builder edit.
- `setup/SKILL.md` — once more on confirm, immediately followed by the "build kicked off" message.
- `refine/SKILL.md` — on entry, and after each recorded change.
- `test/SKILL.md` — on entry, as a one-line "you're testing the <domain> context (last updated: …)".

## The scope box

The summary is a **single code block fence**. The entire box is one fence — no mixing of code and prose inside it.

```
─── <domain> · scope ────────────────────────────────  <state>

  ═══ SOURCES ══════════════════════════════════════════════════════
  Objects in your account, scoped by rules. Each rule re-runs on
  every refresh; the count on the right is what it matched now.

    INCLUDE — pulled into scope
      PATTERN                               │  DISCOVERED NOW
      ──────────────────────────────────────┼──────────────────────
      Tables                                │
        SALES.DATA.*                        │  ~80   ORDERS, ITEMS +78
      Semantic Views                        │
        SALES.DATA.PIPELINE_SV              │    1
        SALES.DATA.BOOKINGS_SV              │    1

    EXCLUDE — kept out of every answer, even on future refreshes
      PATTERN                               │  DISCOVERED NOW
      ──────────────────────────────────────┼──────────────────────
      Tables                                │
        SALES.STAGING.*                     │  12

  _(Still scanning your query history — type refresh to update)_

  ──────────────────────────────────────────────────────────────────
  Optional — I couldn't find these automatically
    dbt  e.g. @DB.SCHEMA.STAGE/target/manifest.json

──────────────────────────────────────────────────────────────────
  build · include <pattern> · exclude <pattern> · deeper
```

**Header line:** `─── <domain> · scope ────────────────────────────────  <state>` where `<state>` is one of:
- `proposed` — first render after discovery (no manifest saved yet)
- `edited` — a saved version exists but the builder has made unsaved changes in this session
- `updated <relative-time>` — a saved version exists, no unsaved changes (e.g. `updated 2 minutes ago`)

**SOURCES section:** always present, opened by `═══ SOURCES ═══…` with the two-line subtitle. Contains the **INCLUDE** block followed by the **EXCLUDE** block. Both blocks have the same two-column table structure (`PATTERN │ DISCOVERED NOW`).

**EXCLUDE block:** render only when at least one `excluded: true` rule exists; omit the block entirely otherwise. Uses the same two-column table structure as INCLUDE. Can cover any source type (`Tables`, `Semantic Views`, `Streamlit Apps`, etc.) — one indented sub-line per excluded rule; count column shows `est_tables` for `Tables` patterns or `—` for other source types.

**Status line** at the bottom of the SOURCES section:
- While waiting for the deep-pass result file: `_(Still scanning your query history — type **refresh** to update)_`
- Once the deep-pass results have been applied: `_(Scan complete)_`

**Optional section** (divider `──────…` + `Optional — I couldn't find these automatically` header + items). Render only when `pending_asks` is non-empty. One abbreviated line per pending ask. Omit section entirely — including the divider — when there are no pending asks.

**Footer bar** (always present, one line):
- While deep-pass is still pending: `build · include <pattern> · exclude <pattern> · deeper · refresh`
- Once deep-pass is complete: `build · include <pattern> · exclude <pattern> · deeper`

Omit `refresh` once discovery is complete. Free-form text is always accepted as a direct edit even when it doesn't match a keyword.

> **`help` card.** When the builder types `help`, render the improvement card **outside** the box as a separate prose block. Never render help card content inside the code fence. Do **not** re-render the scope box after the card — the builder reads the card and types their next action, which triggers the normal re-render.

## INCLUDE / EXCLUDE blocks — exact order

The SOURCES section contains two labeled blocks: **INCLUDE** and **EXCLUDE**. Each block has a two-column table header (`PATTERN` | `DISCOVERED NOW`) followed by one line per source or rule.

**INCLUDE block** — render sources in this order; skip any that have nothing:

1. `Tables` — one indented sub-line per included `pattern` rule
2. `Semantic Views` — one indented sub-line per `pattern` rule (the SV FQN), same structure as Tables; `all discovered` only when `rules: []` (builder explicitly requested all)
3. `Streamlit Apps` — `all discovered` or a specific filter
4. `External Tables` — one sub-line per Horizon-connected non-Snowflake DB
5. `External Dashboards` — one sub-line per Horizon-connected BI tool
6. `Tags` — tag name(s)
7. `Ontology` — domain name(s), each with four sub-lines (Nodes / Relationships / Associations / Source files)
8. `dbt` — stage path
9. `Files` — stage path(s)
10. `Definitions` — count inline (e.g. `2 recorded`)
11. `Instructions` — count inline

See "EXCLUDE block" in the scope box spec above for rendering rules — they apply in the same order as INCLUDE, skipping sources with no excluded rules.

**`DISCOVERED NOW` column rules:**
- `Tables` patterns: show `est_tables` count when known (e.g. `~80`); show top 1–2 table names + `+N more` when ≤ 5 total; show `—` when count not yet known.
- `Semantic Views`, `Streamlit Apps`, `Tags`, `External Tables`, `External Dashboards`: show the count returned by discovery; `—` when not yet scanned.
- `Ontology`: show four right-aligned sub-lines: `N  Nodes` / `N  Relationships` / `N  Associations` / `N  Source files`.
- `dbt`, `Files`, `Definitions`, `Instructions`: count is implicit (one line = one item); no separate count column needed.
- **`⚠️ too many`**: append ` ⚠️` to the count when a broad "all discovered" source (`Semantic Views`, `Streamlit Apps`, `External Tables`, `External Dashboards`) returns **> 20 objects**. Catalog pattern rules with explicit FQN globs are intentionally scoped — do not flag them.

**Forbidden:** any other section header, any sub-section like "Key table groups" / "Hot tables" / "Coverage" / "Recent activity".

**Empty row handling — two cases:**

| Case | What it means | How to render |
|---|---|---|
| **User-declared pattern, nothing found yet** | The builder explicitly asked to include a specific pattern (e.g. `"include all Streamlit apps in ANALYTICS.*"`, `"include semantic views matching SALES.*"`). A rule exists in the manifest. Discovery returned 0 results right now. | **Keep the row in the INCLUDE block.** Show the pattern. In the `DISCOVERED NOW` column show `0 _(none yet)_`. The rule stays active — matching objects will be picked up on the next build. |
| **Auto-scan, nothing found** | Discovery ran a broad scan (no explicit builder instruction) and found nothing. No manifest rule was written. | **Omit the row entirely** from the INCLUDE block. Instead, append a subtle one-liner *below* the fence (not inside it), grouping empty auto-scanned sources: `_(No Semantic Views / Streamlit Apps found — say "include <pattern>" to monitor them.)_` Omit sources that were never scanned at all. |

At build confirmation (§10 confirm block), render the full picture including any sources that were asked about but not yet added.

## Source-to-row reference

Each `sources[]` entry in `scope.yaml` maps to exactly one summary row. Use this as the single source of truth — do not invent additional rows.

| source name (`scope.yaml`) | type | INCLUDE label |
|---|---|---|
| `catalog_objects` | `snowflake_metadata` | `Tables` |
| `streamlit_apps_metadata` | `snowflake_metadata` | `Streamlit Apps` |
| `streamlit_apps` | `snowflake_content` | `Streamlit Apps` |
| `dbt_projects` | `snowflake_content` | `dbt` |
| `stage_files` | `snowflake_content` | `Files` |
| `semantic_views` | `snowflake_content` | `Semantic Views` |
| `tags` | `snowflake_metadata` | `Tags` |
| `business_ontology` | `business_ontology` | `Ontology` |
| `tableau`, `powerbi`, `sigma`, `looker` | `horizon_context` | `External Dashboards` |
| `databricks`, `redshift`, `sqlserver`, `postgres`, `dbt` | `horizon_context` | `External Tables` |
| `concepts`, `relationships`, `associations` | — | `Definitions` |
| `additional_instructions` | — | `Instructions` |

## Per-source content rules (INCLUDE block)

| Source label | What it shows in `PATTERN` column | `DISCOVERED NOW` column | Skipped if |
|---|---|---|---|
| `Tables` | One indented line per included `pattern` rule; ordered by recency-weighted activity where known. | `est_tables` count (~N); top 1–2 table names + `+N more` when ≤ 5. `—` if unknown. | No included pattern rules |
| `Semantic Views` | One indented sub-line per `pattern` rule (the SV's FQN), same as `Tables`. Use `all discovered` only when `rules: []` — i.e. builder explicitly asked for all SVs. Discovery-sourced SVs always have explicit pattern rules, never `rules: []`. | Count of SVs in scope. Append `⚠️` when > 20. Show top names up to 3 then `+N more`. When a user-declared pattern exists but discovery returned 0: show `0 _(none yet)_`. | No semantic views in scope **and** no user-declared pattern rule |
| `Streamlit Apps` | `all discovered` when no filter rule; filter expression (e.g. `ANALYTICS.*`) when the builder declared one. | Count of apps in scope. Append `⚠️` when > 20. When a user-declared pattern exists but discovery returned 0: show `0 _(none yet)_`. | No Streamlit apps found **and** no user-declared pattern rule |
| `External Tables` | One sub-line per platform: `Databricks (via Horizon Context)` etc. | N tables per platform. Append `⚠️` when > 20 per platform. When a user-declared platform rule exists but 0 returned: show `0 _(none yet)_`. | No external DB returned anything **and** no user-declared platform rule |
| `External Dashboards` | One sub-line per platform: `Tableau (via Horizon Context)` etc. | N objects per platform. Append `⚠️` when > 20. When a user-declared platform rule exists but 0 returned: show `0 _(none yet)_`. | No BI platform returned anything **and** no user-declared platform rule |
| `Tags` | Tag name(s), up to 6 | `N in scope` | No tags found |
| `Ontology` | Domain name | Four right-aligned sub-lines: `N  Nodes` / `N  Relationships` / `N  Associations` / `N  Source files`. | Ontology discovery matched nothing (or feature not enabled) |
| `dbt` | `@STAGE/path/to/manifest.json` (join `stage` + `path`, prefix `@`) | *(omit count column — one line = one file)* | No `dbt_projects` file rules |
| `Files` | `@STAGE/file_pattern`. Append `(Power BI models)` for `.pbit`/`.pbix`. | *(omit count column)* | No `stage_files` file rules |
| `Definitions` | `N recorded`; list names inline when total ≤ 3 | *(inline)* | All zero |
| `Instructions` | `N recorded` | *(inline)* | Zero |

*(See "EXCLUDE block" in the scope box spec for rendering rules — same format, applied to excluded rules only.)*

## Verbatim sample (with all three sections, pending asks present)

````
─── sales_ops · scope ───────────────────────────────  proposed

  ═══ SOURCES ══════════════════════════════════════════════════════
  Objects in your account, scoped by rules. Each rule re-runs on
  every refresh; the count on the right is what it matched now.

    INCLUDE — pulled into scope
      PATTERN                               │  DISCOVERED NOW
      ──────────────────────────────────────┼──────────────────────
      Tables                                │
        SALES.DATA.*                        │  ~80  ORDERS, ORDER_ITEMS +78
        SALES.ORDERS.*                      │  ~50
      Semantic Views                        │
        SALES.DATA.PIPELINE_SV              │    1
        SALES.DATA.BOOKINGS_SV              │    1
      Streamlit Apps  all discovered        │    4  SALES_DASH, FUNNEL +2
      External Tables                       │
        Databricks (via Horizon Context)    │   12
        Postgres (via Horizon Context)      │    3
      External Dashboards                   │
        Tableau (via Horizon Context)       │    2
      Tags            finance_certified     │   15  in scope
      Ontology        Finance               │   14  Nodes
                                            │   22  Relationships
                                            │   31  Associations
                                            │    1  Source file
      dbt             @ANALYTICS.DBT.ARTIFACTS/target/manifest.json
      Files           @MY_DB.DOCS.STAGE/metrics_spec.pdf
      Definitions     DAU, ARR  (2 recorded)
      Instructions    3 recorded

    EXCLUDE — kept out of every answer, even on future refreshes
      PATTERN                               │  DISCOVERED NOW
      ──────────────────────────────────────┼──────────────────────
      Tables                                │
        SALES.STAGING.*                     │  —
        SALES.DEV_*.*                       │  —

  _(Scan complete)_

  ──────────────────────────────────────────────────────────────────
  Optional — I couldn't find these automatically
    must-have tables  e.g. SALES.FACT_ORDERS

──────────────────────────────────────────────────────────────────
  build · include <pattern> · exclude <pattern> · deeper
````

## Verbatim sample (no pending asks, no excludes)

````
─── sales_ops · scope ───────────────────────────────  updated 2 minutes ago

  ═══ SOURCES ══════════════════════════════════════════════════════
  Objects in your account, scoped by rules. Each rule re-runs on
  every refresh; the count on the right is what it matched now.

    INCLUDE — pulled into scope
      PATTERN                               │  DISCOVERED NOW
      ──────────────────────────────────────┼──────────────────────
      Tables                                │
        SALES.DATA.*                        │  ~80  ORDERS, ORDER_ITEMS +78
        SALES.ORDERS.*                      │  ~50
      Streamlit Apps  all discovered        │    4  SALES_DASH, FUNNEL +2
      Definitions     DAU, ARR  (2 recorded)
      Instructions    3 recorded

  _(Scan complete)_

──────────────────────────────────────────────────────────────────
  build · include <pattern> · exclude <pattern> · deeper
````

## Before saving — prescribed phrase

Before running any save calls, output exactly this line (substituting the domain name):

```
Saving Cortex Sense scoping instructions for <domain>…
```

Do **not** improvise a different progress message. Then run the save calls. Then render the confirm block below.

## On confirm

The confirm block in `setup/SKILL.md` §10 is rendered after the save succeeds. Verbatim shape:

```
Saved. The build is now queued — it can take minutes or hours to complete depending on the scope.

  Build role:      <ROLE>  (fixed — recreate to change)
  Build warehouse: <WH>    (say "use warehouse <NAME>" to change it)
  Stored at:       <storage_location>

You don't need to wait. While it runs you can:
  • add more scope — just type here (e.g. "add FINANCE.REVENUE.*",
    "include dbt at @DB.SCHEMA.STAGE/target/manifest.json",
    "must-have tables: SALES.FACT_ORDERS")
  • reply here to add facts the build should know
    ("filter ds = max(ds) on snapshot tables",
    "ARR is in ANALYTICS.MARTS.FACT_ARR")
  • reply here with 5–10 questions you'd want to test the context
    against — I can help you build an eval set.
  • share this as an agent — ask me "set up an agent for <domain>"

When the build finishes, Cortex Sense for <domain> will be ready.

If CoCo restarts or you open a new session, type:
  @cortex-sense resume <domain>
```

Substitute `<ROLE>` and `<WH>` from the values resolved in §6. Substitute `<storage_location>` from the `storage_location` value resolved in §1 (the `<DB>.<SCHEMA>` where the manifest is saved). Substitute `<domain>` with the domain name. The role is locked at setup time — do not suggest `USE ROLE` as a way to change it; the only path is recreating this Cortex Sense.

### Rollout pointer (always render after the confirm block)

Always render this pointer after the confirm block (outside the code fence, as plain prose):

```
To put this context behind a shareable assistant, the cortex-agent skill can create a
Cortex Agent over your <domain> context. (Distributing that agent as a shareable link
is a product feature outside this skill — I can set up the agent, not the link.)
```

## What we never render

- `[✓] / [ ]` checkbox rows for internal sources.
- Internal source names (`streamlit_apps_metadata`, `cortex_agents_searches_threads`, `roles_users_grants`, `si_artifacts`, `access_history`).
- Sub-section headers ("Snowflake Metadata", "Connected Platforms", "Snowflake Content", "Key table groups", "Hot tables", "Coverage").
- `status: draft / active`.
- `version_id`. Stage paths are shown only in the `dbt` and `Files` INCLUDE rows and in the "stored at" confirm line — nowhere else.
- Empty rows or "—" placeholders. Omit instead.
- Layer 1, Layer 2, QBE, ontology, entity, graph.
- `help` card content inside the code fence. The card is always outside the box.
- The term "usage signal applied" or any other internal pipeline label.
- CoCo's own reasoning steps, internal tool traces, or intermediate SQL output.

## Expanded view (builder says "show details")

Expanded view keeps the INCLUDE/EXCLUDE structure but adds per-rule `user_prompt` lines and full stage paths. Header and footer stay the same as the normal view.

```
─── sales_ops · scope ───────────────────────────────  updated 2 minutes ago

  ═══ SOURCES ══════════════════════════════════════════════════════
  Objects in your account, scoped by rules. Each rule re-runs on
  every refresh; the count on the right is what it matched now.

    INCLUDE — pulled into scope
      Tables
        SALES.DATA.*       (~80)   "all of SALES.DATA"
        SALES.ORDERS.*     (~50)   "sales.orders ok"
      Streamlit Apps
        @PROD.TOOLS.APPS_STAGE/sales_dashboard.py
        @PROD.TOOLS.APPS_STAGE/funnel.py
      External Tables
        Databricks (via Horizon Context)
          analytics.gold.fact_orders
        Postgres (via Horizon Context)
          billing.public.invoices
      External Dashboards
        Tableau (via Horizon Context)
          Sales Pipeline FY27
      Definitions
        DAU   (metric)  COUNT(DISTINCT user_id)
        ARR   (metric)  ...
      Instructions
        1. filter ds = max(ds) on snapshot tables

    EXCLUDE — kept out of every answer, even on future refreshes
      Tables
        SALES.STAGING.*     "exclude staging and dev"

  _(Scan complete)_

  ──────────────────────────────────────────────────────────────────
  Optional — I couldn't find these automatically
    dbt  e.g. @DB.SCHEMA.STAGE/target/manifest.json

──────────────────────────────────────────────────────────────────
  build · include <pattern> · exclude <pattern> · deeper
```

If the builder explicitly asks for the YAML or wants to export it:

```bash
uv run --project <SKILL_DIR>/.. python <SKILL_DIR>/../scripts/persist_state.py preview \
    --from-file <WORKSPACE_DIR>/state.yaml
```
