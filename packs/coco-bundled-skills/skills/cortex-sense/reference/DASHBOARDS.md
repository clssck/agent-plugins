# Dashboards & external metadata via Horizon

The builder thinks of four user-facing rows; CoCo reads from several internal sources.

| User-facing row | What goes here | Internal sources |
|---|---|---|
| **Dashboards** | Streamlit apps and other native Snowflake dashboards | Streamlit metadata (`snowflake_object_search` type: `streamlit`) |
| **External tables** | Non-Snowflake tables and catalogs reachable via Horizon Context | Databricks / SQL Server / PostgreSQL / Redshift / dbt (`snowflake_object_search` types: `external-table`, `external-database`) |
| **External dashboards** | BI tools reachable via Horizon Context | Tableau / Power BI / Sigma / Looker (`snowflake_object_search` type: `bi-object`) |

Connector list: see Snowflake Horizon Context connector docs.

## Why three rows

- **Dashboards** (native): Streamlit and similar Snowflake-hosted assets. No connector needed.
- **External tables**: Non-Snowflake databases — source data the build needs to know exists.
- **External dashboards**: BI tools (Tableau, Power BI, Sigma, Looker) connected via Horizon. A workbook is a question someone has already asked — useful for understanding business intent, separate from raw data.

Keeping BI workbooks separate from native dashboards avoids conflating Snowflake-hosted assets with external ones, and separating both from external tables avoids conflating "what people use" with "what data is available".

## Display rule

**Show only what discovery actually returned.** No checkboxes for platforms that returned nothing. Silent absence.

If discovery returned 4 Streamlit apps, 2 Tableau workbooks, and 12 Databricks tables, the summary shows:

```
Dashboards
  Streamlit       4 apps

External tables
  Databricks     12 tables (via Horizon)

External dashboards
  Tableau         2 workbooks (via Horizon)
```

Nothing else. No "Power BI: not connected", no "Postgres: disabled".

## "Could be there but isn't" tip

The exception: when discovery clearly returned **zero** assets for a Horizon-eligible platform that the builder asked about, or when CoCo has reason to believe the platform is in the customer's stack (mentioned, referenced in a query) but is not reachable, render **one** "see also" line per platform:

> Power BI not connected via Horizon Context — to include it, enable the Power BI connector (see Snowflake Horizon Context docs)

> Alternatively, Power BI semantic models can be onboarded by placing `.pbit` or `.pbix` files in a Snowflake stage — add them as `stage_files` (not `powerbi`). The `power_bi_stage` pipeline auto-discovers and extracts these files.

> Databricks not connected via Horizon Context — to include it, enable the Databricks connector (see Snowflake Horizon Context docs)

Single line. Not a configuration prompt. Not a knob.

## YAML mapping

The manifest uses `type: horizon_context` for everything reachable via Horizon Context (regardless of whether it ends up in the Dashboards row or the External tables row). Streamlit metadata stays under `type: snowflake_metadata` since it lives in Snowflake itself. The user-facing split is presentation-only and driven by the `name` field.

```yaml
sources:
  # Optional metadata source. The guaranteed record is the streamlit_apps CONTENT
  # source (snowflake_content) — see INSTRUCTIONS.md "Streamlit content-path rule".
  - name: streamlit_apps_metadata
    type: snowflake_metadata
    enabled: true
    rules: [...]

  - name: tableau          # → External dashboards row
    type: horizon_context
    enabled: true
    rules:
      - type: pattern
        pattern: "Weekly Sales Overview"
        connector: "TABLEAU"
        path: "TABLEAU.Sales Team"
        user_prompt: "include the Weekly Sales Overview workbook"
      - type: pattern
        pattern: "Customer Segmentation"
        connector: "Tableau Cloud Prod"
        path: "Tableau Cloud Prod.Marketing"
        user_prompt: "include the Customer Segmentation data source"

  - name: powerbi          # → External dashboards row
    type: horizon_context
    enabled: true
    rules:
      - type: pattern
        pattern: "Monthly Revenue Summary"
        connector: "My Power BI"
        path: "My Power BI.Finance Reports"
        user_prompt: "include the Monthly Revenue Summary report"

  - name: databricks       # → External tables row
    type: horizon_context
    enabled: true
    rules: [...]

  - name: postgres         # → External tables row
    type: horizon_context
    enabled: true
    rules: [...]

  - name: streamlit_apps
    type: snowflake_content
    enabled: true
    rules: [...]             # file rules with stage + file_pattern

  - name: stage_files
    type: snowflake_content
    enabled: false           # disabled by default; builder opts a file in
    rules: [...]
```

Render mapping (for SUMMARY_FORMAT):

| `name` | Row |
|---|---|
| `streamlit_apps_metadata` | Dashboards |
| `tableau`, `powerbi`, `sigma`, `looker` | External dashboards |
| `databricks`, `sqlserver`, `postgres`, `redshift`, `dbt` | External tables |
| `streamlit_apps`, `stage_files` (any `snowflake_content`) | *not rendered* — scope-only; affects what the build reads, not what the summary shows |

Internal source-name disambiguation is for the build, not the builder.

## Streamlit source code — `snowflake_content`

Streamlit `.py` source is the `streamlit_apps` (`snowflake_content`) source. The rule for it — always create it when an app is added, resolve its stage via `DESCRIBE STREAMLIT`, keep `streamlit_apps_metadata` optional, copy Workspace-backed apps (`snow://workspace/...`) to a stage, and handle Git-backed/unresolvable stages — lives in `INSTRUCTIONS.md` "Streamlit content-path rule" (the single source; don't restate it here). For the summary, `streamlit_apps` is scope-only — not rendered (see the render mapping above).

Other stage-hosted content (`stage_files` — docs, SQL workbooks) is opt-in: the builder points at a specific file.

## Discovery hooks

See `DISCOVERY.md` for the search contract. Today:

- **Streamlit**: `snowflake_object_search` with `object_types=["streamlit"]` (see `DISCOVERY.md`) + `SHOW STREAMLITS IN ACCOUNT` as fallback only. What is **not yet supported** is searching the *content* of these apps — discovery returns the app metadata only.
- **Tableau / Power BI / Sigma / Looker (Dashboards)**: discoverable via `snowflake_object_search` with `object_types=["bi-object"]`, the same way Streamlit apps are discovered. Each result carries a **name**, **connector**, **path**, and **reference_id**. When adding to scope, store the exact name in `pattern`, and populate `connector` and `path` from the search result to enable the backend to locate the specific object. What is **not yet supported** is searching the *content* of these assets (their internal queries, fields, and definitions) — discovery returns the asset metadata only.
- **Databricks / SQL Server / PostgreSQL / Redshift / dbt (External tables)**: discoverable via `snowflake_object_search` with `object_types=["external-table", "external-database"]`. Each result carries a **name**, **connector** (type + instance), and **reference_id**. When adding to scope, store the database/schema/table name in `pattern` and populate `connector` from the search result. The `dbt` connector exposes dbt project catalogs as external databases and schemas (not BI objects).
