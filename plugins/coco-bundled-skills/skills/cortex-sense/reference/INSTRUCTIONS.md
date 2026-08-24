# Instructions — natural language in, classified storage out

The builder writes plain English. CoCo classifies internally and shows a one-line evidence echo of where it was recorded. **The builder never picks `concepts` vs `relationships` vs `associations` vs `additional_instructions`.**

This file is a CoCo-facing classification appendix, not a routing menu the user sees.

## Routing rules (internal)

Apply in order. First match wins.

| Builder phrasing | Internal slot | Echo to builder |
|---|---|---|
| Defines a metric/dimension/term: "DAU is …", "define ARR as …", "<term> means <formula>", aliases | `concepts[]` | "Recorded: <name> defined as <formula\|definition> (<type>)." |
| Connects two terms: "X is the same as Y", "X derives from Y", "X feeds Y" | `relationships[]` | "Recorded: <X> <relationship_type> <Y>." |
| Links a term to a table or BI object: "ARR is in `ANALYTICS.MARTS.FACT_ARR`", "revenue comes from Power BI dataset D" | `associations[]` | "Recorded: <concept> lives in <fqn>." |
| Scope include (tables): "add `SALES.ORDERS.*`", "include only sales tables" | `catalog_objects` source rule (no `excluded` flag). Database-level wildcards rejected — scope to `DATABASE.SCHEMA.*`. | "Updated scope: including `<pattern>`." |
| Scope exclude (tables): "exclude `ANALYTICS.STAGING.*`", "ignore dev tables", "hide anything with DEV in it" | `catalog_objects` source rule with `excluded: true`. Cross-database patterns like `*.*DEV*.*` are valid (only bare `*` rejected). | "Updated scope: excluding `<pattern>`." |
| Scope edit (non-table): "exclude semantic view X", "disable Power BI", "ignore streamlit Y" | `sources[].rules` on the matching source with `excluded: true` | "Updated scope: <human description>." |
| Settings edit: "7 day access history", "dbt at @DB.SCHEMA.STAGE/target/manifest.json" | `sources[].rules` (matching source) | "Updated <source>: <description>." |
| Warehouse edit: "use warehouse `ANALYTICS_WH`", "run the build on `BUILD_WH`", "set the compute warehouse to X" | top-level `warehouse` field | "Set the build warehouse to `<warehouse>`." |
| Stage file or business doc: "notes at @MY_DB.DOCS.STAGE/metrics_spec.txt", "runbook at @MY_DB.DOCS.STAGE/onboarding.md", "add @DB.SCHEMA.STAGE/file.ext", "Power BI models from @STAGE/powerbi" | `sources[]` with `name: stage_files`, `type: snowflake_content`, `file` rule (`.pbit`/`.pbix` auto-route to `power_bi_stage` by extension; kb pipeline accepts `.txt`/`.md` only) | "Added stage file: `@<stage>/<file>`." |
| Streamlit app: "include Streamlit @DB.APP.STAGE", "add the sales Streamlit", any Streamlit path | `streamlit_apps` content source (resolve stage via `DESCRIBE STREAMLIT`); metadata optional — see **Streamlit content-path rule** below | "Added Streamlit: <app>." |
| dbt project: "dbt manifest at @DB.SCHEMA.STAGE/target/manifest.json", "add dbt project", "include dbt" | `sources[]` with `name: dbt_projects`, `type: snowflake_content`, `file` rule (`stage` + `path` to manifest.json) | "Added dbt manifest: `@<stage>/<path>`." |
| Procedural / tie-break / safe-answer / hint: "treat house campaigns as non-client-serving", "default to ARR when someone says revenue", "explain the limitation instead of inferring" | `additional_instructions[]` (`user_prompt` only) | "Recorded as an instruction." |
| Anything that doesn't fit cleanly above | `additional_instructions[]` | "Recorded as an instruction." |

### Source-name rules

- Stage paths (`@DB.SCHEMA.STAGE/file.ext`) for business documents or query-pattern files → `name: stage_files`, `type: snowflake_content`.
- Stage paths to Power BI models (`@DB.SCHEMA.STAGE/model.pbit` or `.pbix`) → same as above: `name: stage_files`, `type: snowflake_content`. Do **not** route to `powerbi` (which is for Horizon Context connected dashboards, not file-based models).
- Streamlit apps (by name, URL, or `@STAGE` path) → always create the `streamlit_apps` content source (resolve its stage via `DESCRIBE STREAMLIT`); `streamlit_apps_metadata` is optional. See below.
- dbt manifest paths (`@DB.SCHEMA.STAGE/path/to/manifest.json`) → `name: dbt_projects`, `type: snowflake_content`. Local repo paths → upload first per `LOCAL_FILES.md`.

**Semantic views — always write explicit pattern rules.** The `semantic_views` source must always have at least one `pattern` rule when enabled — neither a missing `rules` key nor `rules: []` is allowed; both scope to every SV in the account. Rule of thumb:
- **Specific SVs found** → one `pattern` rule per SV using the full FQN (`DATABASE.SCHEMA.SV_NAME`).
- **SVs found but FQNs not fully resolved** → one `pattern` rule per in-scope database/schema using a wildcard (`DATABASE.SCHEMA.*`).
- **Builder says "include all SVs in DB1"** → one rule: `pattern: DB1.*`.

**Pattern hygiene** (the validator enforces these on **source rules** — construct rules accordingly): `semantic_views` patterns must carry the full database; `file`/stage rules need the 3-part `DATABASE.SCHEMA.STAGE`; dbt `path` must end in `manifest.json`. For `catalog_objects` **include** rules, database-level wildcards (`*`, `*.SCHEMA.*`) are rejected — scope to `DATABASE.SCHEMA.*`. For `catalog_objects` **exclude** rules (`excluded: true`), cross-database patterns like `*.*DEV*.*` are valid (they post-filter, no DB scan); only bare `*` is rejected. See `SCOPE_MANIFEST.md` "Pattern hygiene".

### Streamlit content-path rule

Streamlit has two source paths: **content** (`streamlit_apps`, `type: snowflake_content` — the app source code) and **metadata** (`streamlit_apps_metadata`, `type: snowflake_metadata` — registration/sharing metadata). When a builder adds a Streamlit app:

- **Always create the `streamlit_apps` content source** and do our best to resolve where the code lives. Content is the guaranteed record.
- **`streamlit_apps_metadata` is optional for now** — create it only when the builder specifically wants app metadata (e.g. "include the Streamlit registration/sharing metadata"). Do **not** auto-create it by default.

**Resolve the staging location** with `DESCRIBE STREAMLIT <DB.SCHEMA.APP>`, which returns either `root_location` (the stage path where the code lives) or `source_location` (a `snow://workspace/...` URI for Workspace-authored apps), plus `main_file`. The populated location column is the discriminator:

- **`root_location` is a plain internal stage** (`@DB.SCHEMA.STAGE[/...]`) → build the `file` rule: `stage: DB.SCHEMA.STAGE`, `file_pattern: <main_file>` (or `""` for all apps when adding a whole schema of apps).
- **`source_location` starts with `snow://workspace/`** (a Workspace-backed app, no usable `root_location`) → the build can't read Workspace files directly. Copy the app's source to a regular stage per `LOCAL_FILES.md` "Workspace-backed Streamlit apps → stage", then record the resulting stage as a normal `streamlit_apps` `file` rule. Ask for the target stage first — never copy silently.
- **`root_location` is Git-backed, empty, or not a resolvable internal stage** → best-effort: still record the app in the Dashboards row (metadata is fine), mark content resolution uncertain, and ask **once**:
  > "`<app>` looks Git-backed — I can include its metadata, but I may not be able to read its source for the build. Want me to include it anyway, or point me at a stage copy?"
- **`DESCRIBE STREAMLIT` fails or can't be parsed** → ask **once** for the stage path (fold into the batched asks) and record best-effort.
- **Never silently drop the app** in any branch.

> Validate the exact `DESCRIBE STREAMLIT` column names (`root_location`, `main_file`) against a live call before relying on them; adjust parsing if the API differs.

Snowflake Streamlit apps are first-class objects identified by a three-part FQN (`DATABASE.SCHEMA.APP_NAME`) — that FQN is what discovery returns and what `streamlit_apps_metadata` uses when the builder opts into metadata.

```yaml
sources:
  - name: streamlit_apps            # always created (content)
    type: snowflake_content
    enabled: true
    rules:
      - type: file
        stage: PROD.TOOLS.APPS_STAGE          # from DESCRIBE STREAMLIT root_location
        file_pattern: "sales_dashboard.py"    # from main_file ("" = all apps in stage)
        user_prompt: "add the sales Streamlit"
  # streamlit_apps_metadata is OPTIONAL — add only when the builder wants metadata:
  # - name: streamlit_apps_metadata
  #   type: snowflake_metadata
  #   enabled: true
  #   rules:
  #     - type: pattern
  #       pattern: "PROD.TOOLS.SALES_DASHBOARD"
  #       user_prompt: "add the sales Streamlit"
```

If the builder explicitly says "metadata only" (e.g. "just the Streamlit metadata, not the code"), omit the `streamlit_apps` entry and create only `streamlit_apps_metadata`.

**Bulk inclusion (all apps in a schema):** When multiple Streamlit apps are in scope for inclusion — whether discovered automatically or because the builder explicitly asked for all apps in a schema — batch `DESCRIBE STREAMLIT` on them (up to 50; if more, sample and extrapolate) and apply the per-app rules above to each result. Then aggregate into file rules:

- Stage-backed apps sharing a stage → one `file` rule with an appropriate `file_pattern`.
- Stage-backed apps on distinct stages → one `file` rule per stage.
- Workspace-backed apps (`source_location` = `snow://workspace/...`) → add a `pending_ask` offering to copy them to a stage. Ask template:
  ```
  [skip]  Streamlit staging   N of M apps in <SCHEMA> are workspace-backed (no stage path).
                              I can copy them to a stage for ingestion.
                              Target stage? (default @<DB>.<SCHEMA>.SENSE_SOURCES)
  ```
- Git-backed or unresolvable apps (no usable `root_location` and not workspace-backed) → add a `pending_ask` noting the builder must upload or accept metadata-only. Ask template:
  ```
  [skip]  Streamlit upload    N of M apps in <SCHEMA> are git-backed or unresolvable.
                              I can't read their source directly. Upload to a stage
                              and tell me the path, or I'll include metadata only.
  ```
- `DESCRIBE STREAMLIT` fails for some apps → treat as unresolvable (fold into the git-backed/unresolvable ask above).
- If **no** apps are stage-backed, also skip the `streamlit_apps` source and emit `streamlit_apps_metadata` with a `pattern` rule instead.

If both workspace-backed and git-backed apps are present, render both asks. If only one type exists, render only that one.

**Never use a `pattern` rule for `streamlit_apps`** unless you have confirmed (via batch DESCRIBE) that all matched apps are stage-backed.

### Scope-of-removal rules

When the builder says "remove X", the scope of removal is **exactly the category the builder named** and nothing else.

| Builder says | What is removed | What is NOT removed |
|---|---|---|
| "remove the Streamlit apps" | All `streamlit_apps` / `streamlit_apps_metadata` rules | `catalog_objects` rules, `dbt_projects`, `stage_files`, any other source |
| "remove staging tables" / "exclude ANALYTICS.STAGING.*" | The matching `catalog_objects` pattern rule | Dashboard sources, dbt, stage files, other catalog patterns |
| "remove stage files" | `stage_files` rules | Everything else |
| "remove all except tables" | All sources **except** `catalog_objects` | `catalog_objects` rules are untouched |
| "disable Power BI" | `powerbi` source set to `enabled: false` | All other sources |

**Never silently drop sources outside the named category.** If the builder says "remove Streamlit" and you're about to remove a `catalog_objects` rule because it looks related, do not — only touch the `streamlit_apps` / `streamlit_apps_metadata` entries. If unsure whether the removal is cross-source, echo what you plan to remove and confirm before acting.

Always include the verbatim text in `user_prompt`. The structured fields (`name`, `type`, `formula`, …) are best-effort extractions.

## What the builder sees vs. what gets stored

> Builder: *"DAU is COUNT(DISTINCT user_id)"*

Internal:
```yaml
concepts:
  - name: DAU
    type: metric
    formulas: ["COUNT(DISTINCT user_id)"]
    user_prompt: "DAU is COUNT(DISTINCT user_id)"
```
Echo: *"Recorded: DAU defined as `COUNT(DISTINCT user_id)` (metric)."*

> Builder: *"exclude staging and dev in ANALYTICS"*

Internal:
```yaml
sources:
  - name: catalog_objects
    rules:
      - type: pattern
        pattern: "ANALYTICS.STAGING.*"
        excluded: true
        user_prompt: "exclude staging and dev in ANALYTICS"
      - type: pattern
        pattern: "ANALYTICS.DEV_*.*"
        excluded: true
        user_prompt: "exclude staging and dev in ANALYTICS"
```
Echo: *"Updated scope: excluding `ANALYTICS.STAGING.*` and `ANALYTICS.DEV_*.*`."*

> Builder: *"treat house campaigns as non-client-serving"*

Internal:
```yaml
additional_instructions:
  - user_prompt: "treat house campaigns as non-client-serving"
```
Echo: *"Recorded as an instruction."*

## The two `additional_*` buckets

The manifest has two free-form buckets internally:

- `additional_instructions` — feeds the next build (cold path).
- `in_account_instructions` — applied at inference time; intended to stay within this account. Currently written to the same `scope.yaml` (the `in_account_scope.yaml` storage split is not yet implemented).

**Today, route everything to `additional_instructions`** unless the builder explicitly says "this is for runtime only" or similar. The user-facing surface shows one bucket called "Instructions". The split is invisible to the builder and may collapse entirely once feedback storage lands.

## Conflict handling

If a new instruction contradicts an existing one (same `name` for a `concept` with a different `formula`; same exclusion pattern that overlaps with an inclusion), don't silently overwrite. Surface the conflict and ask:

> Builder said earlier: "DAU is `COUNT(DISTINCT user_id)`". Now: "DAU is `COUNT(*)`". Which is canonical?

When the builder picks one, mark the older entry `superseded_by` the new one (audit trail, internal). Pipe the manifest through `persist_state.py merge` before calling `put-stage-file` — it runs `_merge_instructions()` in-process to handle dedup and supersession.

## Propagation — placeholder

When a correction looks like it could apply elsewhere ("DAU is COUNT(DISTINCT user_id)" probably also applies to `weekly_active_users`, `monthly_active_users`, …), the proposal calls for CoCo to propose propagation with confirmation. **Not yet implemented.** Today, record the single fact and append the user-facing "(propagation across similar metrics is not yet implemented)" line.
