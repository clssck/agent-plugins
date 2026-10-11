# General dbt Guide

Sanofi dbt guidance derived from the OneMesh "dbt - how to guide" Confluence hub,
its first-level sections, the split model-development subpages, and reusable patterns
from other Sanofi dbt standards pages.

## Source of Truth

When guidance conflicts, apply this precedence: (1) the target repository's documented
contract, including documented local exceptions; (2) the applicable, approved, current
team standard; (3) cross-space standards as supporting evidence; and (4) Draft/WIP
material as advisory only. Do not use a lower-ranked source to override a higher-ranked
contract. If applicability, approval status, currency, or conflict resolution is unclear,
ask before proceeding.

Core references use base `https://sanofi.atlassian.net/wiki/spaces/OneMesh/pages/`:
`dbt - how to guide` 66171471965; `I. Getting Started` 66274656737;
`dbt Core - Client Installation` 65167132865; `II. Project Structure` 66268563349;
`III. Model Development` 66273019235; `1. Schemas, Sources & Lineage` 66574974978;
`2. Model Development Basics` 66574549062; `3. Materialization Strategy` 66574155981;
`4. Incremental Models (Deep Dive)` 66574516315; `5. Snapshots, SCD2 & Seeds`
66574516338; `6. Advanced Patterns: Versioning, Governance & Feature Flags`
66572616908; `IV. Test & Run Orchestration Strategy` 66273543254;
`Quick Reference (Cheat Sheet)` 66267188549; `FAQ & Troubleshooting` 66213282159.

Additional standards source:

- `DBT Development Standards`: `https://sanofi.atlassian.net/wiki/spaces/USDFPAA/pages/67174269873/DBT+Development+Standards`.
  Extract its reusable rules for layer-aware modeling, hash-based incremental change
  detection, naming, SQL/Jinja discipline, DQ gates, and Elementary audit wiring. Treat
  project names and example schemas as local examples, not global defaults.
- DCFDP `6. dbt Standards` tree: hub `65443597350`, `6.1 Project structure and
naming conventions` `65443597575`, `6.1.1 Managing dbt_project.yml and Model
Organization` `65443859336`, `6.2 Models and Documentation Configuration`
  `65445232861`, and `6.3 Building a model` `65443597707`. This DD&O tree is the source
  for the `psa`/`rsv`/`dwh`/`dmt` layer taxonomy, its folder-to-schema mapping in
  `dbt_project.yml`, and the `generate_schema_name` override.
- `dbt | Coding Standards`: `https://sanofi.atlassian.net/wiki/spaces/BCORE10/pages/66574254841/dbt+Coding+Standards`.
  Reuse its generic naming, docs, tests, contracts, and macro rules while ignoring
  project-specific warehouse names.
- `dbt (Data Build Tool) setup and best practices`: `https://sanofi.atlassian.net/wiki/spaces/PADE/pages/66575630729/dbt+Data+Build+Tool+setup+and+best+practices`.
  Use only the general setup/toolchain cautions; ignore local Airflow roles and team
  implementation details.
- CIDF `Best practices - dbt and SQL in general` `66074739903` and RDDP `IICS to dbt
  - Detailed Target State Architecture` `66814313816` reinforce scoped CI, SQLFluff,
package, and per-layer orchestration patterns. CIDF also documents Snowflake
persistence defaults (`copy_grants`, `transient: false`, `+full_refresh: false` on
persistent layers) and tag-based orchestration selectors. Its `incremental` +
`insert_overwrite` suggestion does NOT fit history-bearing models on Snowflake; see
[snowflake-materializations.md](snowflake-materializations.md#tables-transience-and-grants).
- OneMesh `dbt Incremental Load – Implementation Guide` `67205533077`: generic
  table-to-incremental pattern, notably pushing the watermark filter into the driving
  table's `WHERE` for micro-partition pruning. `Data Quality Framework — dbt + Elementary`
  `67118465918`: `store_failures` triage schema, warn/error severity policy, and
  control-total reconciliation tests.

All project names, schemas, model names, table names, domains, ticket IDs, and dates in
examples are placeholders unless explicitly identified as a Sanofi convention. Adapt
them to the target repository and current platform guidance.

## How to Use This Reference

Use this file as a routing index first. Setup, profiles and secrets, the
`dbt_project.yml` baseline, and deprecation handling are in `project-setup.md`. For model
work read Structure, Naming, Sources, Layers, Development Practice here, plus the focused
references: Snowflake materializations and incremental design in
`snowflake-materializations.md`, unit tests in `unit-tests.md`. For docs or tests prefer
`writing-documentation.md` and `writing-data-tests.md` after checking the local project
conventions here. For CI/governance read Tags here, plus `state-and-ci.md` (selectors,
state, defer, CI), `contracts-and-versions.md` (contracts, versions, access),
`upgrading.md` (upgrades), `troubleshooting.md`, and `operations.md`
(Elementary, query tracking, feature flags, WAP).

## Project Structure

Preserve the target repository's documented layer taxonomy. If it has none, apply the
applicable, approved, current team standard; do not infer a taxonomy from Draft/WIP
guidance. The Draft OneMesh guide proposes `models/staging` for one-to-one
source-conformed models, `models/intermediate` for joins/enrichment/aggregation prep,
and `models/marts` for business-ready warehouse or published models. Adopt that layout
only when the repository or approved team standard has selected it; otherwise agree the
taxonomy before creating new layers. Supporting folders can include `models/sources` for
source YAML only, `snapshots`, `seeds`, `tests` for singular SQL tests, `analyses`, and
documented `macros`. Keep folder organization consistent; do not mix flat and nested
patterns arbitrarily.

Many Sanofi Snowflake/dbt repositories keep dbt under a top-level `transformation/`
folder alongside `.github/workflows`, `ddl/`, and `orchestration/`. Inspect the repo
root before assuming the dbt project root is the repository root.

Sanofi guidance describes more than one dbt layer taxonomy; follow the target
repository's applicable, approved, current standard and never force one onto the other.
The Draft OneMesh guide uses `staging` / `intermediate` / `marts` (with
`marts/warehouse` for the gold/table layer and `marts/published` for the consumer view
layer). The DD&O (DCFDP) standard uses `psa` / `rsv` / `dwh` / `dmt`:
`models/psa_<source_system>` for the
persistent staging area (cleaned, renamed, lightly transformed raw data, one folder per
source system), `models/rsv_<schema>` for the reservoir/intermediate working layer
(prepares data before final consumption, rebuilt when needed), `models/dwh_<schema>` for
the integrated data warehouse/business logic, and `models/dmt_<schema>` for the
business-facing data marts (facts/dimensions).

The ingestion and working layers line up cleanly: staging corresponds to `psa` (OneMesh
even allows a `[stg/psa]_` staging prefix) and intermediate to `rsv`. The warehouse/mart
split differs, so check the repo's folder-to-schema mapping before placing a model.
OneMesh splits `marts` into `marts/warehouse` (schema `dwh`; gold tables holding the
`fct_`/`dim_` models; tags `dwh`/`cmp`/`warehouse`) and `marts/published` (schema `dmt`;
consumer views; tags `pbl`/`dmt`/`published`/`datamart`). DD&O instead uses `dwh` for
integrated business logic and places the `fct_`/`dim_` marts in `dmt` (which reads from
`dwh`). So `fct_`/`dim_` models live in the warehouse (`dwh`) layer under OneMesh but in
the `dmt` layer under DD&O — follow whichever the repo uses.

## Naming and Aliases

Favor descriptive logical dbt model names and use `alias` for short, stable Snowflake
object names. Naming patterns: `[stg/psa]_[source]__[source_table]`,
`int_{logical_grouping}__[description]`, `fct_<domain>__<fact>`,
`dim_<domain>__<dimension>`, or the project-local equivalent. Use `ref()` and `source()`
everywhere. Use aliases
deliberately for zero-downtime refactors by validating a replacement model, then moving
the stable physical alias so Snowflake and BI users keep querying the same object.

Reusable naming standards from the development standards page: use lowercase
`snake_case`, single underscores within a segment, one model per `.sql` file, and
filename equals model name. Use double underscores to separate source/domain segments
from entity names when the repo's naming grammar uses that pattern. Common prefixes
include `src_`, `psa_`, `rsv_`, `dwh_`, `fct_`, and `dim_` when the repo uses those
layers. Avoid phase/version markers such as `_phase_2` or `_v1` in model names; use
dbt versioning, aliases, or documented deprecation paths instead. Expose one grain key
and test it with `unique` and `not_null`; when the repo uses hashed technical keys this
is commonly `tech_key_hash`. Technical columns use a clear prefix such as `tech_`,
timestamps use `_ts`, and column names should avoid reserved warehouse keywords.

## dbt Docs Node Colors

Use `docs.node_color` at folder level for visual consistency; override per model only
for exceptions. Recommended palette: view/staging/published `#4dabf7`, warehouse table
`#51cf66`, ephemeral `#a9a9a9`, incremental `#be4bdb`, snapshot `#ffd43b`, seed
`#ff922b`, source `#dee2e6`.

## Schemas, Sources, and Lineage

dbt should not manage schemas, grants, database permissions, or DDL outside model
objects at Sanofi. Use approved schema management, commonly Schemachange in CI/CD, for
schemas and grants; dbt may create tables/views inside pre-existing schemas. Treat
example schema prefixes as illustrative and follow the data lead/platform naming.
Define sources in YAML with `source()`, descriptions, and freshness where delivery
matters; verify `loaded_at_field`. Keep staging pass-through: rename, cast, lightly
clean/filter, but do not join, aggregate, or apply complex business logic. Keep DAGs
shallow/wide: roughly <=4 source-to-mart hops and 3-4 downstream models per
intermediate. Use dbt_project_evaluator for orphans, fanout, deep chains, and staging
used directly in marts.

## Layers and Materializations

Default materializations: sources raw references, seeds static mappings, snapshots
SCD2, staging `view`, intermediate `ephemeral`, warehouse marts `table`/`incremental`,
and published marts secure `view` where consumer schemas require it. Exceptions:
staging `table` for heavy regex/large `VARIANT` flattening; incremental/snapshot near
staging or PSA when sources lack history; intermediate `view` for frequent Snowflake
debugging; `incremental` for massive/expensive facts. Avoid direct staging-to-mart
jumps when joins or business logic exist. Cost framing: views push compute to query
time; tables cost build time but serve repeated use; incrementals avoid large rebuilds
but add complexity; ephemerals can bloat compiled SQL. Use Snowflake `merge` or
`delete+insert` only after validating uniqueness semantics. The FAQ's ~10M-row
incremental threshold is a heuristic; also weigh query cost, cadence, rebuild time,
and volatility.

For repos using `psa/rsv/dwh/dmt`, preserve their materialization contract: `psa` and
`dwh` are commonly `table` or incremental `merge` models (keyed by the technical grain
key when the repo uses hashed keys), `rsv` uses a truncate/reload working-layer pattern
and does not retain history, and `dmt` or other consumer layers default to views/secure
views unless the repo explicitly uses tables/full rebuilds or incremental facts. Set
each layer's `schema` explicitly in config; the DD&O `generate_schema_name` override
uses that value verbatim and otherwise falls back to the target default. Match the
repo's schema case convention (some use lowercase, DD&O examples use uppercase such as
`PSA_WORKDAY_HUB` and `DMT_PLAI`).

Snowflake rules (transient default, `copy_grants`, dynamic tables, incremental strategies,
late-arriving data) are in [snowflake-materializations.md](snowflake-materializations.md).
NEVER use `insert_overwrite` on Snowflake to "replace a partition": it truncates and reloads
the whole table every run, erasing history on history-bearing models.

## YAML Properties and Configuration

Avoid one giant `schema.yml`. Prefer sidecar YAML: `<model>.yml` next to SQL,
`_model.yml` for doc-on-top style, or `docs/<model>.yml` when folders are crowded.
Use YAML for properties and model-scoped configs such as descriptions, columns, tests,
contracts, freshness, `unique_key`, and Snowflake configs where the repo does so. Use
SQL `config()` for query-local behavior, especially `alias`, incremental behavior, and
one-off overrides.

Configuration precedence from low to high: `dbt_project.yml`, model YAML `config`,
then SQL file `{{ config(...) }}`.

Use project-level `persist_docs` when descriptions should be pushed into Snowflake.

Package notes: before adding or upgrading a package, obtain approval through the
project's authorized package-review process. Then review its purpose, maintainer,
security posture, dbt compatibility, and project impact. Source packages only from a
trusted maintainer or approved internal mirror; pin each package to an explicit version
or repository-approved bounded range in `packages.yml`; and review release notes,
compatibility, and downstream impact before each upgrade. Run `dbt deps` after approved
changes. Prefer `dbt_utils` before custom macros, use `dbt_project_evaluator` for
standards checks, use `dbt_audit_helper` for old-vs-new comparisons, and do not apply
global materialization settings to Elementary package models because it needs its own
incremental objects.

Recommended package version bands from the guide:

- `dbt-labs/dbt_utils`: `>=1.0.0,<2.0.0`
- `metaplane/dbt_expectations`: `>=0.10.0,<0.11.0`
- `elementary-data/elementary`: `>=0.20.0,<1.0.0`
- `dbt-labs/dbt_project_evaluator`: `>=1.0.0,<2.0.0`
- `dbt-labs/audit_helper`: `>=0.9.0,<1.0.0`

## Documentation

For documentation work, use `writing-documentation.md`. The core OneMesh rules are:
include grain, purpose, and edge cases at model level; document calculated fields,
encoded values, foreign keys, nullable columns, sources, tags, and useful `meta`; avoid
descriptions that only restate object names. For shared marts or KPI-producing models,
also capture refresh cadence, main consumers, owner/domain metadata, and KPI/catalog
codes when the repo uses them.

## Development Practice

Never use `SELECT *` in dbt models. Explicit column lists reduce downstream breakage
from source schema drift and help Snowflake scan only needed data. Use local/dev
throttling predicates during iteration, gated by `target.name`, not hardcoded into
production behavior.

Before writing a custom macro, check whether `dbt_utils` or an approved Sanofi package
already provides it; frequently reused macros include `dbt_utils.star`,
`dbt_utils.generate_surrogate_key`, `dbt_utils.safe_divide`, and `dbt_utils.date_spine`.

Structure model SQL as readable CTEs, commonly import/source CTEs, logical CTEs, then
`final`. Avoid broad `select *` from sources; a final `select * from final` or
`select f.* from final as f` can be a local debugging convention after columns have
already been explicitly shaped. Let SQLFluff/dbt templater enforce style when configured
(commonly via a `.sqlfluff` at the project root); lint failures in pre-commit or CI
should block merge rather than becoming subjective review debates.

For Jinja/macros, default to plain SQL. Extract a macro only when it removes real
duplication, commonly after the same logic appears three or more times. Keep macros in
`macros/`, one concern per file, document non-trivial macros with args/returns/example,
and never hardcode database names, schemas, dates, or environment values; derive them
from `target`, `var()`, or `env_var()`. Shared cross-project macros belong in an
approved dbt package rather than being copy-pasted between repositories.

When migrating hand-managed view DDL (for example a monolithic Schemachange script) into
dbt, create one model per view, wire dependencies with `ref()`/`source()`, and preserve
the final relation names, schemas, and output columns so downstream consumers are
unaffected. Extract logic repeated across several views into shared intermediate models
instead of copying CTEs. Validate the refactor against the legacy relation with parity
checks — row counts by period, summed measures, distinct grain-key counts, and null
rates on key attributes — using audit_helper (`compare_relations`, `compare_column_values`,
`compare_all_columns`, `compare_queries`).

## Testing

For data-test work, use `writing-data-tests.md`. Keep these routing rules in mind:

- Data tests check real Snowflake data; unit tests check transformation logic with
  small mock inputs.
- Staging focuses on `not_null`, `unique`, relationships, and freshness.
- Intermediate focuses on unit tests for complex or grain-changing logic.
- Marts focus on relationships, accepted values, and business invariants.
- Normalize legacy Confluence `tests:` snippets to `data_tests:` unless the repo is
  intentionally pinned to the older style.
- Nest generic test parameters under `arguments` when the project runs dbt >= 1.10.8, or
  on 1.10.5-1.10.7 only after setting `flags: require_generic_test_arguments_property: true`
  (its default there is `false`, and the nested form then raises
  `ArgumentsPropertyInGenericTestDeprecation`). Otherwise keep them as top-level
  properties of the test. Config such as `severity`, `where`, and `store_failures` stays
  under `config:`. From 1.10.8 the flag defaults to `true` and top-level parameters warn.
- Unit tests (placement, overrides, incremental cases, `--empty` prerequisites, production
  exclusion): see [unit-tests.md](unit-tests.md).

If a repo uses a `run_dq_check` macro, treat it as a pre-hook data quality gate. In the
standards page example it wraps `DQ_SF.SP_DQ_FETCH_CUSTOM_CHECKS`; a critical
`PROCESS_HALT` result aborts the model, writes details to `DQ_ERROR_DETAILS`, and
propagates through the orchestrator/alerting path. Inspect the project macro before
changing arguments or failure semantics.

Before PR merge, relevant scoped dbt tests should pass with zero error-level failures.
At minimum, cover the model grain with `unique`/`not_null`, foreign keys with
`relationships`, and controlled categorical mart fields with `accepted_values` when
the allowed values are verified.

## Tags

Use tags for orchestration and discoverability:

- Frequency tags such as `hourly` or `daily`.
- Department/domain tags such as `finance`.
- Compute tags such as `heavy_compute` for larger Snowflake warehouses.

Have orchestrators select models by tag rather than by file path or model name, so that
moving or renaming files during a refactor does not silently break scheduled runs.

## Snapshots

Snapshot staging models, not raw sources. Use cleaned, renamed columns so the historical
record is understandable. Verify `updated_at` changes when source rows change. To track
deletes on dbt >= 1.9 set `hard_deletes: invalidate` (closes `dbt_valid_to`) or
`hard_deletes: new_record` (adds a row with `dbt_is_deleted = True`, keeping history
gap-free); both replace `invalidate_hard_deletes`. Define snapshots in YAML with a
`config:` block; `target_schema` is optional from 1.9 and defaults to
`generate_schema_name`. `dbt_valid_to_current: "to_date('9999-12-31')"` replaces the
`NULL` on current rows, which simplifies date-range joins.

Use snapshots when source systems overwrite data, audit/compliance requires history, or
the business needs historical attributes. Prefer the `timestamp` strategy when a reliable
`updated_at` exists; use `check` only when no reliable timestamp is available.

dbt snapshot tables add metadata columns:

- `dbt_valid_from`: when the version became active.
- `dbt_valid_to`: when it was superseded; null for the current version.
- `dbt_scd_id`: unique identifier for that row version.

Keep snapshots in a dedicated schema when that reduces mart clutter.

Run snapshots before marts in production pipelines; snapshots are not executed by a
standard `dbt run`.

Use `dbt snapshot --select state:modified` for state-based snapshot runs when the state
manifest is available.

## Seeds

Use seeds for small static reference data, mappings, country/status codes, and test
fixtures. Do not use seeds for large datasets, frequently changing data, transactional
data, or data that should come from a governed source.

The guide's threshold is roughly 1000 rows. For larger files, use Snowflake `COPY INTO`,
an external stage, Schemachange, or proper ELT.

Configure seed schemas, `quote_columns`, docs colors, and per-seed `column_types` in
`dbt_project.yml` when the CSV needs explicit Snowflake types.

## Sources and Freshness

Define sources in YAML and reference them with `source()`. Add source freshness where
freshness matters and confirm that `loaded_at_field` exists and is populated. On dbt
>= 1.10 `freshness` and `loaded_at_field` live under `config:`; use `loaded_at_query`
(1.10+) for derived or filtered timestamps, never together with `loaded_at_field`.
Without either, Snowflake falls back to `LAST_ALTERED` metadata, which moves on any
object change, not only data loads. Set `freshness: null` to opt a table out.

## Exposures

Use exposures for important downstream consumers: dashboards, applications, ML models,
notebooks, and analyses. Set maturity to `high` for production/SLA-bound consumers,
`medium` for stable non-SLA consumers, and `low` for experimental or POC consumers. Use
`+exposure:<name>` selectors for consumer-specific runs and tests.

## Sources

Sources for the rules in this file that are version-sensitive on their own; setup,
deprecation, and upgrade sources are listed in [project-setup.md](project-setup.md#sources).
Re-check them when the project's resolved versions differ:

- [Snapshots](https://docs.getdbt.com/docs/build/snapshots): `hard_deletes`, `dbt_valid_to_current`, optional `target_schema`.
- [Source freshness config](https://docs.getdbt.com/reference/resource-configs/freshness): `loaded_at_query`, `config:` nesting.
- [Data tests property](https://docs.getdbt.com/reference/resource-properties/data-tests): `arguments:` and `config:` placement.
