# General dbt Guide

Sanofi dbt guidance derived from the OneMesh "dbt - how to guide" Confluence hub, its first-level sections, the split model-development subpages, and reusable patterns from other Sanofi dbt standards pages. Routing index first, then rules for structure, naming, layers, YAML, packages, development practice, tags, snapshots, seeds, sources, exposures. Project names, schemas, models, tables, domains, ticket IDs, and dates in examples are placeholders unless identified as a Sanofi convention; adapt to the target repository and current platform guidance.

## Source of Truth

**Precedence on conflict, high → low:** (1) target repository's documented contract, incl. documented local exceptions; (2) applicable, approved, current team standard; (3) cross-space standards as supporting evidence; (4) Draft/WIP material, advisory only. NEVER use a lower rank to override a higher contract. Applicability, approval status, currency, or conflict resolution unclear ⇒ ask before proceeding.

Core references, base `https://sanofi.atlassian.net/wiki/spaces/OneMesh/pages/`:

| Page | ID |
|---|---|
| `dbt - how to guide` | 66171471965 |
| `I. Getting Started` | 66274656737 |
| `dbt Core - Client Installation` | 65167132865 |
| `II. Project Structure` | 66268563349 |
| `III. Model Development` | 66273019235 |
| `1. Schemas, Sources & Lineage` | 66574974978 |
| `2. Model Development Basics` | 66574549062 |
| `3. Materialization Strategy` | 66574155981 |
| `4. Incremental Models (Deep Dive)` | 66574516315 |
| `5. Snapshots, SCD2 & Seeds` | 66574516338 |
| `6. Advanced Patterns: Versioning, Governance & Feature Flags` | 66572616908 |
| `IV. Test & Run Orchestration Strategy` | 66273543254 |
| `Quick Reference (Cheat Sheet)` | 66267188549 |
| `FAQ & Troubleshooting` | 66213282159 |

Additional standards sources:

- `DBT Development Standards`: `https://sanofi.atlassian.net/wiki/spaces/USDFPAA/pages/67174269873/DBT+Development+Standards`. Reusable: layer-aware modeling, hash-based incremental change detection, naming, SQL/Jinja discipline, DQ gates, Elementary audit wiring. Project names and example schemas = local examples, not global defaults.
- DCFDP `6. dbt Standards` tree: hub `65443597350`; `6.1 Project structure and naming conventions` `65443597575`; `6.1.1 Managing dbt_project.yml and Model Organization` `65443859336`; `6.2 Models and Documentation Configuration` `65445232861`; `6.3 Building a model` `65443597707`. DD&O tree = source for the `psa`/`rsv`/`dwh`/`dmt` taxonomy, its folder-to-schema mapping in `dbt_project.yml`, and the `generate_schema_name` override.
- `dbt | Coding Standards`: `https://sanofi.atlassian.net/wiki/spaces/BCORE10/pages/66574254841/dbt+Coding+Standards`. Reuse generic naming, docs, tests, contracts, macro rules; ignore project-specific warehouse names.
- `dbt (Data Build Tool) setup and best practices`: `https://sanofi.atlassian.net/wiki/spaces/PADE/pages/66575630729/dbt+Data+Build+Tool+setup+and+best+practices`. Only general setup/toolchain cautions; ignore local Airflow roles and team implementation.
- CIDF `Best practices - dbt and SQL in general` `66074739903` and RDDP `IICS to dbt - Detailed Target State Architecture` `66814313816`: scoped CI, SQLFluff, packages, per-layer orchestration. CIDF also documents Snowflake persistence defaults (`copy_grants`, `transient: false`, `+full_refresh: false` on persistent layers) and tag-based orchestration selectors. Its `incremental` + `insert_overwrite` suggestion does NOT fit history-bearing models on Snowflake → [snowflake-materializations.md](skill://dbt/references/snowflake-materializations.md#tables-transience-and-grants).
- OneMesh `dbt Incremental Load – Implementation Guide` `67205533077`: generic table-to-incremental pattern; push the watermark filter into the driving table's `WHERE` for micro-partition pruning. `Data Quality Framework — dbt + Elementary` `67118465918`: `store_failures` triage schema, warn/error severity policy, control-total reconciliation tests.

## How to Use This Reference

| Task | Read |
|---|---|
| Setup, profiles/secrets, `dbt_project.yml` baseline, deprecations | `project-setup.md` |
| Model work | Structure, Naming, Sources, Layers, Development Practice here + `snowflake-materializations.md` (materializations, incremental design), `unit-tests.md` |
| Docs or tests | Local conventions here, then `writing-documentation.md` / `writing-data-tests.md` |
| CI/governance | Tags here + `state-and-ci.md` (selectors, state, defer, CI), `contracts-and-versions.md`, `upgrading.md`, `troubleshooting.md`, `operations.md` (Elementary, query tracking, feature flags, WAP) |

## Project Structure

Preserve the target repository's documented layer taxonomy. None documented ⇒ apply the applicable, approved, current team standard; NEVER infer a taxonomy from Draft/WIP guidance. Sanofi guidance describes more than one taxonomy; follow the repo's standard and NEVER force one onto the other.

| Taxonomy | Layers |
|---|---|
| Draft OneMesh | `models/staging` (one-to-one source-conformed) · `models/intermediate` (joins/enrichment/aggregation prep) · `models/marts` (business-ready; `marts/warehouse` = gold tables, `marts/published` = consumer views) |
| DD&O (DCFDP) | `models/psa_<source_system>` persistent staging (cleaned, renamed, lightly transformed raw; one folder per source system) · `models/rsv_<schema>` reservoir/intermediate working layer (prepares data before final consumption; rebuilt when needed) · `models/dwh_<schema>` integrated warehouse/business logic · `models/dmt_<schema>` business-facing marts (facts/dimensions) |

Adopt the Draft OneMesh layout only when the repo or approved team standard selected it; otherwise agree the taxonomy before creating layers.

**Cross-mapping.** staging ↔ `psa` (OneMesh even allows a `[stg/psa]_` prefix); intermediate ↔ `rsv`. The warehouse/mart split differs ⇒ check the repo's folder-to-schema mapping before placing a model:

| | OneMesh | DD&O |
|---|---|---|
| `fct_`/`dim_` models | `marts/warehouse` (schema `dwh`; tags `dwh`/`cmp`/`warehouse`) | `dmt` (reads from `dwh`) |
| Consumer views | `marts/published` (schema `dmt`; tags `pbl`/`dmt`/`published`/`datamart`) | `dmt` |
| Integrated business logic | `marts/warehouse` | `dwh` |

**Supporting folders:** `models/sources` (source YAML only), `snapshots`, `seeds`, `tests` (singular SQL tests), `analyses`, documented `macros`. Consistent organization; no arbitrary flat/nested mixing.

**Repo root.** Many Sanofi Snowflake/dbt repos keep dbt under a top-level `transformation/` beside `.github/workflows`, `ddl/`, `orchestration/`. Inspect the root before assuming it is the dbt project root.

## Naming and Aliases

Descriptive logical model names; `alias` for short, stable Snowflake object names. `ref()` and `source()` everywhere.

- **Patterns:** `[stg/psa]_[source]__[source_table]`, `int_{logical_grouping}__[description]`, `fct_<domain>__<fact>`, `dim_<domain>__<dimension>`, or project-local equivalent.
- **Zero-downtime refactor:** validate a replacement model, then move the stable physical alias ⇒ Snowflake and BI users keep querying the same object.
- **Rules:** lowercase `snake_case`; single underscores within a segment; one model per `.sql`; filename = model name. Double underscores separate source/domain segments from entity names when the repo grammar uses that. Prefixes (`src_`, `psa_`, `rsv_`, `dwh_`, `fct_`, `dim_`) when the repo uses those layers.
- **No phase/version markers** (`_phase_2`, `_v1`) in model names; use dbt versioning, aliases, or documented deprecation paths.
- **Keys and columns:** expose one grain key, tested `unique` + `not_null` (with hashed technical keys, commonly `tech_key_hash`). Technical columns prefixed `tech_`; timestamps `_ts`; SHOULD avoid reserved warehouse keywords.

## dbt Docs Node Colors

`docs.node_color` at folder level; per-model override for exceptions only.

| Node | Color |
|---|---|
| view/staging/published | `#4dabf7` |
| warehouse table | `#51cf66` |
| ephemeral | `#a9a9a9` |
| incremental | `#be4bdb` |
| snapshot | `#ffd43b` |
| seed | `#ff922b` |
| source | `#dee2e6` |

## Schemas, Sources, and Lineage

- **Schema ownership.** dbt SHOULD NOT manage schemas, grants, database permissions, or DDL outside model objects at Sanofi. Approved schema management (commonly Schemachange in CI/CD) owns schemas and grants; dbt creates tables/views inside pre-existing schemas. Example schema prefixes illustrative; follow data lead/platform naming.
- **Sources:** YAML with `source()`, descriptions, freshness where delivery matters; verify `loaded_at_field`.
- **Staging pass-through:** rename, cast, lightly clean/filter; NEVER join, aggregate, or apply complex business logic.
- **DAG shape:** shallow/wide; ≲4 source-to-mart hops; 3-4 downstream models per intermediate. `dbt_project_evaluator` flags orphans, fanout, deep chains, staging used directly in marts.

## Layers and Materializations

**Defaults:** sources raw references · seeds static mappings · snapshots SCD2 · staging `view` · intermediate `ephemeral` · warehouse marts `table`/`incremental` · published marts secure `view` where consumer schemas require.

**Exceptions:** staging `table` for heavy regex/large `VARIANT` flattening · incremental/snapshot near staging or PSA when sources lack history · intermediate `view` for frequent Snowflake debugging · `incremental` for massive/expensive facts. Avoid direct staging-to-mart jumps when joins or business logic exist.

**Cost framing:** views push compute to query time; tables cost build time, serve repeated use; incrementals avoid large rebuilds, add complexity; ephemerals can bloat compiled SQL. Snowflake `merge` or `delete+insert` only after validating uniqueness semantics. The FAQ's ~10M-row incremental threshold is a heuristic; also weigh query cost, cadence, rebuild time, volatility.

**`psa/rsv/dwh/dmt` repos — preserve the layer contract:**

| Layer | Materialization |
|---|---|
| `psa`, `dwh` | `table` or incremental `merge` (keyed by the technical grain key when the repo uses hashed keys) |
| `rsv` | Truncate/reload working layer; no history retained |
| `dmt`/consumer | Views/secure views unless the repo explicitly uses tables/full rebuilds or incremental facts |

Set each layer's `schema` explicitly in config; the DD&O `generate_schema_name` override uses it verbatim, else falls back to the target default. Match the repo's schema case convention (some lowercase; DD&O examples uppercase, e.g. `PSA_WORKDAY_HUB`, `DMT_PLAI`).

Snowflake rules (transient default, `copy_grants`, dynamic tables, incremental strategies, late-arriving data) → [snowflake-materializations.md](skill://dbt/references/snowflake-materializations.md). **NEVER** `insert_overwrite` on Snowflake to "replace a partition": it truncates and reloads the whole table every run, erasing history on history-bearing models.

## YAML Properties and Configuration

- **Sidecar YAML**, not one giant `schema.yml`: `<model>.yml` next to SQL; `_model.yml` for doc-on-top; `docs/<model>.yml` when folders are crowded.
- **YAML:** properties and model-scoped configs (descriptions, columns, tests, contracts, freshness, `unique_key`, Snowflake configs where the repo does so). **SQL `config()`:** query-local behavior (`alias`, incremental behavior, one-off overrides).
- **Precedence, low → high:** `dbt_project.yml` › model YAML `config` › SQL `{{ config(...) }}`.
- Project-level `persist_docs` when descriptions should reach Snowflake.

### Packages

- **Approval:** obtain approval through the project's authorized package-review process before adding or upgrading; review purpose, maintainer, security posture, dbt compatibility, project impact.
- **Source and pins:** trusted maintainer or approved internal mirror; explicit version or repo-approved bounded range in `packages.yml`; review release notes, compatibility, downstream impact before each upgrade. `dbt deps` after approved changes.
- **Preferences:** `dbt_utils` before custom macros; `dbt_project_evaluator` for standards checks; `dbt_audit_helper` for old-vs-new comparisons. No global materialization settings on Elementary package models; it needs its own incremental objects.

Recommended version bands:

| Package | Band |
|---|---|
| `dbt-labs/dbt_utils` | `>=1.0.0,<2.0.0` |
| `metaplane/dbt_expectations` | `>=0.10.0,<0.11.0` |
| `elementary-data/elementary` | `>=0.20.0,<1.0.0` |
| `dbt-labs/dbt_project_evaluator` | `>=1.0.0,<2.0.0` |
| `dbt-labs/audit_helper` | `>=0.9.0,<1.0.0` |

## Documentation

Detail → `writing-documentation.md`. Core OneMesh rules: model level = grain, purpose, edge cases; document calculated fields, encoded values, foreign keys, nullable columns, sources, tags, useful `meta`; AVOID descriptions restating object names. Shared marts or KPI-producing models: also refresh cadence, main consumers, owner/domain metadata, KPI/catalog codes when the repo uses them.

## Development Practice

- **No `SELECT *`** in dbt models; explicit columns limit downstream breakage from source schema drift and let Snowflake scan only needed data. Dev throttling predicates gated by `target.name`, never hardcoded into production behavior.
- **Macros:** check `dbt_utils` or an approved Sanofi package first; frequent: `dbt_utils.star`, `dbt_utils.generate_surrogate_key`, `dbt_utils.safe_divide`, `dbt_utils.date_spine`.
- **SQL shape:** readable CTEs: import/source CTEs, logical CTEs, `final`. No broad `select *` from sources; a final `select * from final` or `select f.* from final as f` is an acceptable local debugging convention once columns are explicitly shaped. SQLFluff/dbt templater enforces style when configured (commonly `.sqlfluff` at project root); lint failures in pre-commit or CI SHOULD block merge, not become review debates.
- **Jinja/macros:** default plain SQL. Extract a macro only when it removes real duplication, commonly 3+ repeats. Macros in `macros/`, one concern per file; document non-trivial ones with args/returns/example. NEVER hardcode database names, schemas, dates, or environment values; derive from `target`, `var()`, `env_var()`. Shared cross-project macros → approved dbt package, not copy-paste.

### Migrating hand-managed view DDL

Monolithic Schemachange script → dbt: one model per view; dependencies via `ref()`/`source()`; preserve final relation names, schemas, output columns so consumers are unaffected. Logic repeated across views → shared intermediate models, not copied CTEs. Validate against the legacy relation with parity checks: row counts by period, summed measures, distinct grain-key counts, null rates on key attributes, using audit_helper (`compare_relations`, `compare_column_values`, `compare_all_columns`, `compare_queries`).

## Testing

Detail → `writing-data-tests.md`.

- Data tests check real Snowflake data; unit tests check transformation logic on small mock inputs.
- **Layer focus:** staging `not_null`, `unique`, relationships, freshness · intermediate unit tests for complex or grain-changing logic · marts relationships, accepted values, business invariants.
- **Legacy snippets:** normalize Confluence `tests:` → `data_tests:` unless the repo is intentionally pinned to the older style.
- **`arguments`:** nest generic test parameters under `arguments` on dbt >= 1.10.8, or on 1.10.5-1.10.7 only after `flags: require_generic_test_arguments_property: true` (default there `false`; nested form otherwise raises `ArgumentsPropertyInGenericTestDeprecation`). Otherwise top-level test properties. From 1.10.8 the flag defaults `true` and top-level parameters warn. `severity`, `where`, `store_failures` stay under `config:`.
- **Unit tests** (placement, overrides, incremental cases, `--empty` prerequisites, production exclusion) → [unit-tests.md](skill://dbt/references/unit-tests.md).
- **`run_dq_check` macro** = pre-hook data quality gate. Standards-page example wraps `DQ_SF.SP_DQ_FETCH_CUSTOM_CHECKS`: a critical `PROCESS_HALT` result aborts the model, writes details to `DQ_ERROR_DETAILS`, propagates through the orchestrator/alerting path. Inspect the project macro before changing arguments or failure semantics.
- **Before PR merge:** relevant scoped dbt tests SHOULD pass with zero error-level failures. Minimum: grain `unique`/`not_null`; foreign keys `relationships`; controlled categorical mart fields `accepted_values` when allowed values are verified.

## Tags

Orchestration and discoverability: frequency (`hourly`, `daily`) · department/domain (`finance`) · compute (`heavy_compute`, for larger Snowflake warehouses). Orchestrators select by tag, not file path or model name ⇒ moving or renaming files in a refactor does not silently break scheduled runs.

## Snapshots

Snapshot staging models, not raw sources: cleaned, renamed columns keep the historical record understandable. Verify `updated_at` changes when source rows change.

- **Use when:** source systems overwrite data, audit/compliance requires history, or the business needs historical attributes.
- **Strategy:** `timestamp` when a reliable `updated_at` exists; `check` only without a reliable timestamp.
- **Deletes (dbt >= 1.9):** `hard_deletes: invalidate` (closes `dbt_valid_to`) or `hard_deletes: new_record` (adds a row with `dbt_is_deleted = True`, history gap-free); both replace `invalidate_hard_deletes`.
- **Definition:** YAML with a `config:` block; `target_schema` optional from 1.9, defaults to `generate_schema_name`. `dbt_valid_to_current: "to_date('9999-12-31')"` replaces `NULL` on current rows ⇒ simpler date-range joins.
- **Metadata columns:** `dbt_valid_from` (version became active) · `dbt_valid_to` (superseded; null for current) · `dbt_scd_id` (unique id of the row version).
- **Placement and runs:** dedicated schema when it reduces mart clutter. Snapshots are not executed by a standard `dbt run` ⇒ run before marts in production pipelines. State-based: `dbt snapshot --select state:modified` when the state manifest is available.

## Seeds

For small static reference data, mappings, country/status codes, test fixtures. NEVER for large datasets, frequently changing data, transactional data, or data from a governed source. Guide threshold ≈1000 rows; larger → Snowflake `COPY INTO`, external stage, Schemachange, or proper ELT. Configure seed schemas, `quote_columns`, docs colors, per-seed `column_types` in `dbt_project.yml` when the CSV needs explicit Snowflake types.

## Sources and Freshness

YAML + `source()`. Freshness where it matters; confirm `loaded_at_field` exists and is populated. dbt >= 1.10: `freshness` and `loaded_at_field` live under `config:`; `loaded_at_query` (1.10+) for derived or filtered timestamps, NEVER together with `loaded_at_field`. Neither set ⇒ Snowflake falls back to `LAST_ALTERED` metadata, which moves on any object change, not only data loads. `freshness: null` opts a table out.

## Exposures

For important downstream consumers: dashboards, applications, ML models, notebooks, analyses. Maturity: `high` production/SLA-bound · `medium` stable non-SLA · `low` experimental/POC. `+exposure:<name>` selectors for consumer-specific runs and tests.

## Sources

Version-sensitive on their own; setup, deprecation, and upgrade sources → [project-setup.md](skill://dbt/references/project-setup.md#sources). Re-check when the project's resolved versions differ:

- [Snapshots](https://docs.getdbt.com/docs/build/snapshots): `hard_deletes`, `dbt_valid_to_current`, optional `target_schema`.
- [Source freshness config](https://docs.getdbt.com/reference/resource-configs/freshness): `loaded_at_query`, `config:` nesting.
- [Data tests property](https://docs.getdbt.com/reference/resource-properties/data-tests): `arguments:` and `config:` placement.
