# Scope manifest

The durable shape of one domain's context. Persisted as JSON-escaped YAML via `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER put-stage-file`; each save creates a new versioned file (append-only). `scripts/persist_state.py` handles validation, dedup, and doctor pre-flight — it does **not** write to Snowflake directly.

The manifest holds the entire domain context: scope rules, dashboards, semantic views, dbt paths, declared definitions, the conceptual ontology, instructions, and any pending asks the builder skipped. The build consumes this file.

**Two conventions that run through the whole file:**

- **Every authored entry records the builder's verbatim phrasing in `user_prompt`.** This applies to each `sources[].rules[]` entry, each `concepts`/`relationships`/`associations` entry, and each instruction — the phrasing lives next to the structured entry it produced.
- **Three levels.** `concepts` + `relationships` are the conceptual ontology; `associations` bind concepts to physical/logical objects (schema mappings); `sources[].rules` are the logical/physical selection.

## Top-level keys

| Key | Purpose | User-facing? |
|---|---|---|
| `business_domain` | The domain identifier (legacy field name; previously called "use case"). Also the **default `domain`** for concepts/relationships/associations that omit one. | Internal name, user-facing value |
| `version_id`, `created_at`, `updated_at` | Internal versioning, set by the agent at save time. Do not hand-author. | No |
| `status` | `draft` \| `active`. Internal — always written as `active` once the builder confirms. | No |
| `warehouse` | **Required.** The Snowflake virtual warehouse the offline build uses for compute. A valid warehouse identifier (e.g. `ANALYTICS_WH`). Resolved from `CURRENT_WAREHOUSE()` during setup; the builder is told which one is used and can change it. | Yes — builder is told and can change it |
| `sources` | Scope rules per source (`pattern`, `tag`, `file`, …). The structured selection the build consumes. `catalog_objects` rules with `excluded: true` are applied both at ingest-time (tables not indexed) and serving-time (results filtered at query time). | Rendered as narrative summary |
| `concepts`, `relationships`, `associations` | The conceptual ontology + schema mappings. CoCo writes these automatically from the builder's natural language. | No (builder writes prose; classification is internal) |
| `additional_instructions` | Free-form instructions, **cold path** — shared with the offline build. | Rendered as "Instructions" |
| `in_account_instructions` | Free-form instructions applied at inference time — stay within this account, never shared outside it. Currently written to the same `scope.yaml` as `additional_instructions`; the separate `in_account_scope.yaml` storage split is not yet implemented (see `NOT_YET_IMPLEMENTED.md`). | No — single user-facing "Instructions" surface |
| `pending_asks` | Deferred items the builder skipped during the batched-asks turn. Each: `{ask, prompted_at?, provenance?}`. Every pending ask carries `provenance.state: needs-feedback`. When the builder responds, the ask is **removed** and the answer is classified into the appropriate field with `provenance.state: approved`. | Surfaced in expanded view |

## Full example

```yaml
business_domain: sales_ops
status: active
warehouse: <YOUR_WAREHOUSE>      # required — defaults to CURRENT_WAREHOUSE() during setup
created_at: 2026-06-10T20:00:00Z
updated_at: 2026-06-10T20:00:00Z
version_id: v-20260610-200000-abc123

sources:
  - name: catalog_objects
    type: snowflake_metadata
    enabled: true
    rules:
      - type: pattern
        pattern: SALES.DATA.*
        est_tables: 80
        user_prompt: "all of SALES.DATA"
      - type: pattern
        pattern: "SALES.STAGING.*"
        excluded: true
        user_prompt: "exclude staging"
      - type: pattern
        pattern: "*.*DEV*.*"
        excluded: true
        user_prompt: "exclude all dev schemas"
  # ... other sources ...

concepts:
  - name: ARR
    domain: finance
    type: metric
    description: "Recognized annual recurring revenue"
    formulas: ["..."]
    user_prompt: "finance ARR is recognized annual recurring revenue"

relationships:
  - source_concept: revenue
    relationship_type: same_as
    target_concept: GAAP_REVENUE
    target_domain: finance
    user_prompt: "revenue == GAAP_REVENUE in finance"

associations:
  - concept: ARR
    domain: finance
    source: catalog_objects
    fqn: ANALYTICS.MARTS.FACT_ARR
    association_type: primary_table
    user_prompt: "ARR is defined in ANALYTICS.MARTS.FACT_ARR"

additional_instructions:
  - user_prompt: "filter ds = max(ds) on snapshot tables"
    suggested_by: jane.doe

pending_asks:
  - ask: "dbt project — path on disk needs to be identified"
    prompted_at: "2026-06-10T19:55:00Z"
```

## Source-entry shape

Every source entry has only `name`, `type`, `enabled`, optional `rules`. Source `type`:

| `type` | Default | Where used |
|---|---|---|
| `snowflake_metadata` | enabled | Catalog, tags, access history, RBAC, SI, Cortex agents/searches/threads, Streamlit metadata |
| `horizon_context` | enabled | External metadata via Horizon Context connectors — Tableau, Power BI, Sigma, Looker (→ Dashboards row) and Databricks, Redshift, SQL Server, PostgreSQL, dbt (→ External tables row). The user-facing split is driven by `name`; see `DASHBOARDS.md`. |
| `snowflake_content` | enabled | Semantic views (`semantic_views`), Streamlit app source code (`streamlit_apps`), dbt project source (`dbt_projects`), and stage-hosted documents (`stage_files`). `semantic_views`, `streamlit_apps` and `dbt_projects` are enabled by default; `stage_files` requires explicit opt-in via `file` rules. See `DASHBOARDS.md`. |

**Conventions:**
- **Empty or omitted `rules` ⇒ include everything that source allows** (subject to `enabled`).
- **`enabled: false` keeps the entry** in the manifest for the audit trail rather than deleting it — the build skips disabled sources.
- A source's `name` is stable and identifies it; the user-facing presentation (e.g. the Dashboards vs External tables split for `horizon_context`) is driven by `name`, not `type`.

### Source name → build pipeline mapping

The `name` field is what the build pipeline routes on. The full mapping:

| `name` | Build pipeline | `type` | Notes |
|---|---|---|---|
| `catalog_objects` | `horizon_star` | `snowflake_metadata` | Tables, views, schemas |
| `semantic_views` | `semantic_view` | `snowflake_content` | Semantic views |
| `roles_users_grants` | `horizon_star` | `snowflake_metadata` | RBAC metadata |
| `tags` | `horizon_star` | `snowflake_metadata` | Object tags |
| `access_history` | `horizon_star` | `snowflake_metadata` | Query access history |
| `si_artifacts` | `horizon_star` | `snowflake_metadata` | Snowflake Intelligence artifacts |
| `cortex_agents_searches_threads` | `horizon_star` | `snowflake_metadata` | Cortex agents, search services, threads |
| `streamlit_apps_metadata` | `streamlit` | `snowflake_metadata` | Streamlit app registration & sharing metadata (no source code) |
| `streamlit_apps` | `streamlit` | `snowflake_content` | Streamlit app source code via stage file patterns |
| `dbt_projects` | `dbt` | `snowflake_content` | dbt manifest.json via file rule (stage + path) |
| `stage_files` | `kb`, `power_bi_stage` | `snowflake_content` | Stage-hosted documents and Power BI models. `.txt`/`.md` → `kb`; `.pbit`/`.pbix` → `power_bi_stage` (auto-routed by extension). |
| `business_ontology` | `kb` | `business_ontology` | Approved nodes, relationships, and stage sources from Business Ontology. Auto-discovered during setup fast-pass; uses `ontology_domain` rules — see `ONTOLOGY_DISCOVERY.md`. ⚠️ The source `name` field is `business_ontology` for manifest backward compatibility — do not rename. |
| `tableau` | `horizon_context` | `horizon_context` | Tableau workbooks via Horizon Context |
| `powerbi` | `horizon_context` | `horizon_context` | Power BI objects via Horizon Context |
| `sigma` | `horizon_context` | `horizon_context` | Sigma workbooks via Horizon Context |
| `looker` | `horizon_context` | `horizon_context` | Looker explores via Horizon Context |
| `databricks` | `horizon_context` | `horizon_context` | Databricks catalog tables via Horizon Context |
| `redshift` | `horizon_context` | `horizon_context` | Redshift tables via Horizon Context |
| `sqlserver` | `horizon_context` | `horizon_context` | SQL Server tables via Horizon Context |
| `postgres` | `horizon_context` | `horizon_context` | PostgreSQL tables via Horizon Context |
| `dbt` | `horizon_context` | `horizon_context` | dbt project catalog (databases/schemas/models) via Horizon Context — distinct from `dbt_projects` which is internal dbt source code on a stage |

### Snowflake-native metadata sources (`type: snowflake_metadata`)

Seven sources, all enabled by default. Scope each via its `rules` list only.

| `name` | What it adds | Rule types it accepts |
|---|---|---|
| `catalog_objects` | Tables, views, schemas | `pattern`, `tag`, `role`, `file` (non-empty `file_pattern`), `conversational` |
| `roles_users_grants` | RBAC | `pattern` |
| `tags` | Object tags | `pattern` |
| `access_history` | `ACCESS_HISTORY` | `lookback_days` (builder default **30** days when no rule) |
| `si_artifacts` | Snowflake Intelligence artifacts | `pattern` |
| `cortex_agents_searches_threads` | Cortex agents, search services, threads | `pattern` |
| `streamlit_apps_metadata` | Streamlit app registration & sharing metadata (no source code) | `pattern` |

### Snowflake-content sources (`type: snowflake_content`)

Four sources. `semantic_views`, `streamlit_apps`, and `dbt_projects` are enabled by default; `stage_files` requires explicit opt-in via `file` rules.

| `name` | What it adds | Rule types it accepts |
|---|---|---|
| `semantic_views` | Semantic views (full DESCRIBE, including verified queries and custom instructions) | `pattern` |
| `streamlit_apps` | Streamlit app source code | `file` (`file_pattern: ""` = all apps in stage; named pattern = specific app) |
| `dbt_projects` | dbt manifest.json on stage | `file` (`stage` + `path` pointing to `manifest.json`; `path` must end in `manifest.json`) |
| `stage_files` | Stage-hosted documents, query patterns, and Power BI models (.pbit/.pbix) | `file` (non-empty `file_pattern` pointing to the doc/SQL file, or empty for all files in stage) |

All `snowflake_content` file rules reference **stage** paths — the build never reads local files. When a builder supplies a local path (a dbt repo, a PDF, a SQL workbook), upload it to a stage first and record the resulting stage FQN; see `LOCAL_FILES.md`.

> **`streamlit_apps` pattern rules.** `pattern` is also accepted but restricted — apps without a `root_location` cannot be ingested by the pipeline. Only emit a `pattern` rule after batch `DESCRIBE STREAMLIT` confirms all matched apps are stage-backed. See `INSTRUCTIONS.md` "Streamlit content-path rule".

### Business Ontology source (`type: business_ontology`)

Auto-added during the setup fast-pass when ontology discovery finds relevant domains. Uses a `rules[]` list like all other sources, but the only valid rule type here is `ontology_domain`.

Each matched domain always produces **two rule sub-types** — a **source rule** and a **metadata rule**. They must never be merged into one.

**Source rule** — one per stage file registered to the domain (or zero if no stage files):

| Field | Required | Notes |
|---|---|---|
| `type` | yes | `"ontology_domain"` |
| `domain` | yes | Ontology domain name (e.g. `"Sales"`) |
| `stage` | yes | Three-part stage FQN `DB.SCHEMA.STAGE_NAME` |
| `file_pattern` | yes | Filename within the stage |
| `user_prompt` | yes | Verbatim builder phrase |

**Metadata rule** — exactly one per domain, holds display-only counts:

| Field | Required | Notes |
|---|---|---|
| `type` | yes | `"ontology_domain"` |
| `domain` | yes | Ontology domain name |
| `node_count` | no | Per-domain node count from `SYSTEM$GET_GLOSSARY_GRAPH()`. Does not affect the build. |
| `relationship_count` | no | Per-domain relationship count from `SYSTEM$GET_GLOSSARY_GRAPH()`. Display-only. |
| `association_count` | no | Per-domain association count from `SYSTEM$GET_GLOSSARY_GRAPH()`. Display-only. |
| `source_file_count` | no | Number of stage files for this domain at add time. Display-only. |
| `user_prompt` | no | Omit or set to an auto-generated label (e.g. `"<domain> ontology metadata"`). |

**Rule:** count fields (`node_count`, `relationship_count`, `association_count`, `source_file_count`) and source fields (`stage`, `file_pattern`) must never appear on the same rule — the validator rejects the mixed form.

If a domain has no registered stage files, emit only the metadata rule (no source rule). The build resolves approved nodes, relationships, and Semantic View associations from the live ontology at build time — they are not inlined in the manifest. See `ONTOLOGY_DISCOVERY.md` for the full discovery and fold-in contract.

### Horizon Context sources (`type: horizon_context`)

BI/DWH systems reached via Horizon Context connectors. Each appears as its own `sources[]` entry keyed by `name`. Accept `pattern` (incl. `excluded: true`) and `conversational` rules. See `DASHBOARDS.md` for the Dashboards vs External tables mapping and the connector list.

| `name` | Row | Typical filter shape |
|---|---|---|
| `tableau`, `powerbi`, `sigma`, `looker` | Dashboards | `pattern` with exact BI object name + optional `connector` and `path` |
| `databricks`, `redshift`, `sqlserver`, `postgres`, `dbt` | External tables | `pattern` on FQN globs (e.g. `db1.analytics.*`) + optional `connector` |

#### BI dashboard pattern rules — enriched fields

For BI dashboard sources (`tableau`, `powerbi`, `sigma`, `looker`), pattern rules carry additional fields from the SnowScope search response:

| Field | Required | Description |
|---|---|---|
| `pattern` | yes | **Exact BI object name** — no wildcards (`*`, `?`) allowed. Must match the object name as returned by SnowScope. |
| `connector` | no | The connector instance name (e.g. `"My Power BI"`, `"TABLEAU"`, `"Tableau Cloud Prod"`). Disambiguates when multiple connectors of the same platform exist. |
| `path` | no | Hierarchical folder path (e.g. `"My Power BI.Sales Dashboards"`). Wildcards (`*`) **are** allowed here for folder-level matching. |
| `excluded` | no | `true` to exclude this object from scope |
| `user_prompt` | yes | Verbatim builder phrasing |
| `description` | no | Optional human label |

**Wildcard rules for BI sources:**
- `pattern` (the object name): **NO wildcards** — must be the exact name returned by SnowScope search. This ensures the backend can reliably locate the specific object.
- `path` (the folder/project path): **Wildcards allowed** — use `*` to match across folders (e.g. `"TABLEAU.*"` to include objects from all projects on that connector).

**Why exact names?** BI objects frequently share names across connectors and folders (e.g. "Revenue Dashboard" may appear in 8 different locations). Only an exact name + connector + path combination uniquely identifies a specific object. The SnowScope `reference_id` (e.g. `da_6HXvx3BcD32FLptU7xbGRh`) provides a stable handle but is not stored in the manifest — the backend resolves it from the (name, connector, path) triple at build time.

```yaml
# Example: specific Power BI report in a known workspace
- type: pattern
  pattern: "Monthly Revenue Summary"
  connector: "My Power BI"
  path: "My Power BI.Finance Reports"
  user_prompt: "include the Monthly Revenue Summary report"

# Example: specific Tableau workbook
- type: pattern
  pattern: "Customer Retention Analysis"
  connector: "TABLEAU"
  path: "TABLEAU.Analytics Team"
  user_prompt: "include the Customer Retention workbook"

# Example: exclude a specific object
- type: pattern
  pattern: "Test Report Draft"
  connector: "My Power BI"
  path: "My Power BI.Finance Reports"
  excluded: true
  user_prompt: "exclude test report"
```

#### External catalog sources — connector field

For external catalog sources (`databricks`, `redshift`, `sqlserver`, `postgres`, `dbt`), pattern rules support an optional `connector` field to disambiguate when multiple connector instances of the same platform exist. Unlike BI sources, wildcards in `pattern` are still allowed (for FQN globs like `analytics.public.*`).

| Field | Required | Description |
|---|---|---|
| `pattern` | yes | Database/schema/table name or FQN glob (wildcards allowed, e.g. `analytics.*`) |
| `connector` | no | The connector instance name (e.g. `"Databricks Prod"`, `"dbt core"`, `"My Redshift"`). Disambiguates when the same database name appears on multiple connectors. |
| `excluded` | no | `true` to exclude |
| `user_prompt` | yes | Verbatim builder phrasing |

**`dbt` vs `dbt_projects`:** The `dbt` source (`horizon_context`) represents external dbt project catalogs discovered via a Horizon Context connector — databases, schemas, and models visible as catalog objects. The `dbt_projects` source (`snowflake_content`) is for internal dbt project source code (manifest.json, schema.yml) hosted on a Snowflake stage.

```yaml
# Example: dbt catalog via Horizon Context connector
- name: dbt
  type: horizon_context
  enabled: true
  rules:
    - type: pattern
      pattern: "ecommerce"
      connector: "dbt core"
      user_prompt: "include the ecommerce dbt project"

# Example: Databricks with specific connector instance
- name: databricks
  type: horizon_context
  enabled: true
  rules:
    - type: pattern
      pattern: "analytics.*"
      connector: "Databricks Prod"
      user_prompt: "include analytics schemas from Databricks"
```

## Rule types

| `type` | Fields | Notes |
|---|---|---|
| `pattern` | `pattern`, `user_prompt`; optional `excluded`, `description`, `est_tables`, `connector`, `path` | Globs for tables, semantic-view names, etc. For BI sources (`tableau`/`powerbi`/`sigma`/`looker`): `pattern` must be an exact name (no wildcards); `connector` and `path` provide disambiguation. `excluded: true` (exclusion) is valid **only** on `pattern` rules. |
| `tag` | `tag`, `user_prompt`; optional `values` (`[]` = all values) | Catalog scope by Snowflake tag |
| `role` | `role`, `user_prompt` | Catalog scope by role access |
| `file` | `stage`, `user_prompt`; one of `file_pattern` or `path` required; optional `est_tables` (non-dbt only) | See "The `file` rule" below. |
| `lookback_days` | `days`, `user_prompt` (positive integer) | Access history window. Omit the rule entirely ⇒ builder default of 30 days. |
| `conversational` | `user_prompt` only | Procedural / tie-break guidance that doesn't map to a glob |
| `ontology_domain` | Two sub-types — **source rule**: `domain`, `stage`, `file_pattern`, `user_prompt`; **metadata rule**: `domain`, optional count fields (`node_count`, `relationship_count`, `association_count`, `source_file_count`). Count fields and `stage`/`file_pattern` must never be on the same rule. Only valid inside a `business_ontology` source. |

Every rule includes **`user_prompt`** — the verbatim builder text that produced it. (`description` on a `pattern` rule is a separate, optional human label for the rule, distinct from `user_prompt`.) For which rule types each source accepts, see the per-source tables under "Source-entry shape" above.

### Pattern hygiene (validator-enforced)

The validator rejects patterns that are too broad or under-qualified — they make the build slow or ambiguous.

- **Include patterns: no database-level wildcards.** A bare `*` or a leading-wildcard database segment (`*.SCHEMA.*`) scans every database and is rejected. Scope to `DATABASE.SCHEMA.*` (schema-level) instead.
- **Exclude patterns (`excluded: true`): cross-database patterns are allowed.** Excludes are post-filters (no DB scan), so patterns like `*.*DEV*.*` (any schema containing "DEV") or `*.STAGING.*` (schema named exactly "STAGING") are valid. Only bare `*` is rejected (would exclude everything).
- **`semantic_views` patterns must carry the full database.** `DATABASE.SCHEMA.*` or `DATABASE.SCHEMA.OBJECT` — never a bare `SCHEMA.*`.
- **`file` / stage rules need the full 3-part stage FQN** (`DATABASE.SCHEMA.STAGE_NAME`); the `file_pattern` may wildcard.
- **dbt `path` must end in `manifest.json`** — the full path up to and including the file name.

### The `file` rule

`stage` is `DATABASE.SCHEMA.STAGE_NAME` (exactly three dot-separated parts). Two variants:

**Streamlit / stage_files / catalog_objects** — use `file_pattern`:

- **`file_pattern: ""`** (empty) ⇒ **all files in the stage**. Used for `streamlit_apps` when all apps in the stage should be included.
- **Non-empty `file_pattern`** ⇒ a single file name or subdirectory prefix on the stage. Used for catalog CSV lists (e.g. `sales_scope.csv`) or narrowing to a subfolder (e.g. `powerbi`).
- When the builder gives a full stage path like `@DB.SCHEMA.STAGE/app.py`, parse it into `stage: DB.SCHEMA.STAGE` + `file_pattern: app.py`.
- A **Workspace-backed Streamlit app** (source at a `snow://workspace/...` URI, which the build can't read) is copied out to a regular stage first and then recorded here as an ordinary `streamlit_apps` `file` rule — same shape as any other stage app, with `provenance.sources[].ref` pointing at the original `snow://workspace/...` path. See `LOCAL_FILES.md` "Workspace-backed Streamlit apps → stage".
- **Power BI models** (`.pbit`/`.pbix`): files placed in the stage are auto-discovered by the `power_bi_stage` pipeline. No special rule shape needed — use `file_pattern: ""` (all files in stage) or a subdirectory prefix (e.g. `file_pattern: "powerbi"`). The pipeline filters by extension: `.pbit`/`.pbix` → semantic model extraction; `.txt`/`.md` → `kb`.

**dbt_projects** — use `path` (the relative path to `manifest.json` within the stage):

- Each `file` rule points to exactly one `manifest.json`. Multiple manifests = multiple rules.
- When the builder gives `@DB.SCHEMA.STAGE/dbt/target/manifest.json`, parse into `stage: DB.SCHEMA.STAGE` + `path: dbt/target/manifest.json`.

```yaml
# all Streamlit app source code in the stage (empty file_pattern)
- type: file
  stage: PROD.TOOLS.APPS_STAGE
  file_pattern: ""
  user_prompt: "all Streamlit apps from PROD.TOOLS.APPS_STAGE"

# one staged CSV of FQNs (non-empty file_pattern, countable)
- type: file
  stage: GOVERNANCE.SCOPE.SCOPE_FILES
  file_pattern: sales_scope.csv
  est_tables: 87
  user_prompt: "tables listed in @GOVERNANCE.SCOPE.SCOPE_FILES/sales_scope.csv"

# Power BI models from a subdirectory on stage
- type: file
  stage: ANALYTICS.BI.MODELS_STAGE
  file_pattern: powerbi
  user_prompt: "Power BI models from @ANALYTICS.BI.MODELS_STAGE/powerbi"

# dbt manifest.json (uses path, not file_pattern)
- type: file
  stage: ANALYTICS.DBT.ARTIFACTS
  path: sales/target/manifest.json
  user_prompt: "dbt manifest at @ANALYTICS.DBT.ARTIFACTS/sales/target/manifest.json"
```

## Provenance

Every manifest entry (`sources[].rules[]`, `concepts[]`, `relationships[]`, `associations[]`, `additional_instructions[]`, `in_account_instructions[]`, and `pending_asks[]`) may carry an optional `provenance` sub-object. It is written and maintained by CoCo — the builder never authors it directly.

```yaml
provenance:                            # optional on any entry
  state: needs-feedback                # needs-feedback | approved
  origin: inferred-shown-to-user       # declared-by-user | inferred | inferred-shown-to-user
  recorded_at: "2026-06-18T17:00:00Z"  # optional — ISO-8601; when provenance was last updated
  initiated_by: jane.doe               # optional — who originated the entry
  approved_by: finance_lead            # optional — who gave the final OK
  sources:                             # optional — where the information came from
    - type: user_message
      ref: "DAU is COUNT(DISTINCT user_id)"
    - type: trajectory
      ref: "step-42"
    - type: source_code
      ref: "@PROD.TOOLS.APPS_STAGE/sales_dashboard.py"
```

### `state` — workflow status

| Value | Meaning |
|---|---|
| `needs-feedback` | Requires builder confirmation before acting on |
| `approved` | Builder confirmed or explicitly declared this; durable |

### `origin` — how the entry was produced

| Value | Meaning |
|---|---|
| `declared-by-user` | Builder stated this explicitly in conversation |
| `inferred` | System derived this without showing it to the builder |
| `inferred-shown-to-user` | System derived this and surfaced it; builder has seen it |

### `sources[].type` — open set

`user_message`, `trajectory`, `source_code`, `semantic_view`, `query_history`, `external_doc`

### `pending_asks` and the resolve-and-delete lifecycle

`pending_asks` is the "needs-feedback" queue. Every ask carries `provenance.state: needs-feedback`. When the builder responds, the ask is **removed from `pending_asks`** and the answer is classified into the correct field (`sources[].rules`, `concepts[]`, etc.) with `provenance.state: approved, recorded_at: <now>`. Pending asks are never promoted in place — they are resolved and deleted.

## Estimating table counts

`pattern` rules: one `COUNT(*)` against `INFORMATION_SCHEMA` when scoping catalog. `file` rules with a non-empty `file_pattern`: the row count from the staged list file when readable. Omit `est_tables` for `tag`, `role`, `path`, `lookback_days`, `conversational` (and for `pattern`/`file` when unknown — never write `est_tables: null`). Each rule gets at most one count; never enumerate individual tables in conversation.

## Business knowledge — concepts, relationships, associations

Declared definitions and links live in three top-level lists. CoCo writes these automatically by classifying the builder's natural language (the builder never picks the bucket — see `INSTRUCTIONS.md`). This is **not** a Snowflake Semantic Model; it is domain context the build consumes alongside `sources[].rules`. Names across these lists are **loosely coupled** — a `relationship` or `association` may reference a concept name that does not appear in `concepts[]`.

### Concept identity is `(domain, name)`

A concept's identity is the pair `(domain, name)`, so `ARR` in `finance` and `ARR` in `sales` are **two distinct concepts**. `domain` is optional and **defaults to the manifest's top-level `business_domain`** when omitted, so single-domain manifests stay terse.

**`concepts[]`** — named business terms.

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Concept name (e.g. `DAU`, `ARR`) |
| `domain` | no | Subject area; part of identity. Defaults to `business_domain`. |
| `type` | yes | `metric`, `dimension`, `entity`, `attribute`, … |
| `description` | no | Human-readable definition |
| `aliases` | no | List of alternate names |
| `formulas` | no | List of SQL/logical formulas |
| `user_prompt` | yes | Verbatim builder text |
| `extra` | no | Map of string → scalar for extension fields |

**`relationships[]`** — an edge between two concept names.

| Field | Required | Notes |
|---|---|---|
| `source_concept` | yes | Start of the edge |
| `source_domain` | no | Domain of `source_concept`; defaults to `business_domain` |
| `relationship_type` | yes | e.g. `same_as`, `derives_from`, `parent_of`, `feeds` |
| `target_concept` | yes | End of the edge |
| `target_domain` | no | Domain of `target_concept`; defaults to `business_domain` |
| `multiplicity` | no | `ManyToOne` \| `OneToOne` \| `ManyToMany` |
| `verbalizes` | no | Reading template, e.g. `"{A} earns {B}"` |
| `user_prompt` | yes | Verbatim builder text |
| `extra` | no | Extension map |

**`associations[]`** — bind a concept to a data source/object (a schema mapping).

| Field | Required | Notes |
|---|---|---|
| `concept` | yes | Concept name |
| `domain` | no | Which same-named concept this binds; defaults to `business_domain` |
| `source` | yes | A `sources[].name` (e.g. `catalog_objects`, `powerbi`) |
| `fqn` | yes | Object locator (table FQN, BI object id); use `""` when not applicable |
| `association_type` | yes | e.g. `primary_table`, `definition_source`, `lineage_from` |
| `user_prompt` | yes | Verbatim builder text |
| `extra` | no | Extension map |

**`additional_instructions[]` / `in_account_instructions[]`** — free-form hints, **`user_prompt` only** (plus optional `suggested_by`). Do not put typed concept payloads here. Pipe the assembled manifest through `persist_state.py merge` before calling `put-stage-file` — this runs `_merge_instructions()` in-process and may add `id` / `superseded_by` for the audit trail.

The two buckets serve different purposes:
- `additional_instructions` — consumed by the **offline build** (cold path); written to the main `scope.yaml` file, shared with the build.
- `in_account_instructions` — applied at **inference time** (hot path); intended to stay within this account. Currently written to the same `scope.yaml` as `additional_instructions` — the `in_account_scope.yaml` storage split is not yet implemented.

Today, route everything to `additional_instructions` unless the builder explicitly says it is for runtime/inference only (see `INSTRUCTIONS.md`).

> **The ontology layer is deliberately lightweight.** It carries enough structure to ground the build (`concepts`, `relationships`, `associations`, domain identity, optional `multiplicity`/`verbalizes`) but intentionally omits heavier conceptual machinery — entity/value typing, subtyping, constraint/derivation formulas, ternary+ relationships, and concept-centric grouping. Those are additive later; `type` carries the classification for now.

## Scoping seeds; building discovers

The build re-derives scope from `sources[].rules` on every run:

- The structured rules (`pattern` + `excluded` + per-rule `user_prompt`, plus `tag`/`role`/`file`/…) **are** the durable include/exclude spec.
- On each offline build, the build re-applies the rules to the account: an asset matching an include rule (by `pattern`, or for fuzzier cases the per-rule `user_prompt` phrasing) is auto-included; one matching an exclude rule is dropped; anything ambiguous becomes a `needs-feedback` / `pending_asks` item.
- The **diff baseline** ("what is new since the last build") is computed and owned by the build pipeline, not persisted in the authored manifest.

## Exclusion filtering (`catalog_objects` rules with `excluded: true`)

`catalog_objects` rules with `excluded: true` are applied at **both** ingest-time (excluded tables are not indexed) and **serving-time** (results matching exclude patterns are filtered from search results at query time). This means exclusions take effect immediately on save — no rebuild required for the serving-time filter.

```yaml
sources:
  - name: catalog_objects
    type: snowflake_metadata
    rules:
      - type: pattern
        pattern: "*.*DEV*.*"
        excluded: true
        user_prompt: "exclude all dev schemas"
      - type: pattern
        pattern: "*.*.TMP_*"
        excluded: true
        user_prompt: "exclude temporary tables"
```

**Semantics:**
- Glob syntax (`*`, `?`, `[...]`), case-insensitive, matched against the full `DB.SCHEMA.TABLE` name.
- Cross-database patterns like `*.*DEV*.*` are valid. Only bare `*` is rejected (would exclude everything).

**Non-table sources** (semantic views, streamlit, BI): use `excluded: true` on the respective source's rules. Those are ingest-time only.

## Status semantics — internal

`draft` and `active` are internal. The user-facing flow auto-saves with `status: active` once the builder confirms. The builder never sees, picks, or refers to status. If the manifest is later updated, the agent writes a new version with `status: active` via `put-stage-file`. Each save is a new immutable versioned file; the editing-head vs live-version mechanics are documented in `STORAGE.md`.

## Validation

Run `scripts/persist_state.py validate --from-file <state.yaml>` for a clean check. Use `merge` to deduplicate instructions before saving; use `preview` for a stripped human-readable view. (`save` and `set-status` no longer exist — storage goes through `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER put-stage-file` directly.)

## Persistence

The manifest is persisted via `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER put-stage-file` as JSON-escaped plain YAML. Before calling `put-stage-file`, pipe the manifest through `persist_state.py merge` to run validation and instruction dedup. See `STORAGE.md` for the full contract: location resolution, doctor pre-flight, and the persistence-layer registration call.
