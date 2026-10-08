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
Layers and Materializations.
- OneMesh `dbt Incremental Load – Implementation Guide` `67205533077`: generic
  table-to-incremental pattern, notably pushing the watermark filter into the driving
  table's `WHERE` for micro-partition pruning. `Data Quality Framework — dbt + Elementary`
  `67118465918`: `store_failures` triage schema, warn/error severity policy, and
  control-total reconciliation tests.

All project names, schemas, model names, table names, domains, ticket IDs, and dates in
examples are placeholders unless explicitly identified as a Sanofi convention. Adapt
them to the target repository and current platform guidance.

## How to Use This Reference

Use this file as a routing index first. For setup read Setup, Profiles, Project YAML,
and packages. For model work read Structure, Naming, Sources, Layers, Development
Practice, and Incremental sections. For docs or tests prefer the focused references
after checking the local project conventions here. For CI/governance read Selectors,
Tags, Versioning, Feature Flags, WAP, and Troubleshooting.

## Setup and Environment

Use the repo's existing environment manager first. For new Sanofi dbt projects,
the current guide baseline is Python `>=3.11,<3.12` with `dbt-core==1.10.*`,
`dbt-snowflake==1.10.*`, `elementary-data[snowflake]>=0.20.0`,
`schemachange>=4.0.0`, `snowflake-connector-python>=3.0.0`, `dotenv>=0.9.9`,
`pre-commit>=4.3.0`, `ruff>=0.9.7`, `sqlfluff>=3.5`, and
`sqlfluff-templater-dbt>=3.5`. Optional orchestration/refactor packages from the guide:
`apache-airflow[amazon]==2.10.3`, `boto3>=1.40,<1.50`, `recce>=1.21,<1.22`,
`dbt-colibri>=0.2.6`, and
`dbterd>=1.0.0`.

Older installation SOPs may still pin dbt Core 1.9.2 for tool compatibility. Treat
the repository lockfile, `pyproject.toml`, and project onboarding docs as binding for
an existing project; use the OneMesh 1.10 baseline only when creating or modernizing a
project that has no stricter local version constraint. The `1.10.*` pins admit patch
releases below 1.10.5, where syntax such as the `arguments:` test property is not yet
available; check the resolved version before using patch-level features. They also admit
`dbt-snowflake` below 1.10.6, which can fail incremental models that combine
`on_schema_change: sync_all_columns` with collated string columns once Snowflake's
default string/binary column-size change (BCR 2118, scheduled for September 2026) is
deployed. Find exposed models with `dbt ls -s
config.materialized:incremental,config.on_schema_change:sync_all_columns
--resource-type model`; if any match, resolve `dbt-snowflake>=1.10.6`.

Engine naming changed in September 2026: dbt Core 1.x is now "dbt v1", and the Rust
Fusion engine is "dbt v2" (GA). `python -m pip install dbt` now installs dbt v2. For a
v1 project, NEVER run `pip install dbt`; install `dbt-core` and `dbt-snowflake` at the
repository's pins, and run `dbt --version` to confirm which engine is on `PATH` before
trusting a parse or test result. Both engines read the same project and write
compatible `manifest.json` (v12) artifacts, so `state:modified` and `--defer` work across
them, but v2 fails on what v1 only warned about: resolve every deprecation warning first,
and expect unknown config keys, missing macros, missing generic tests, and undefined
`var()` calls to fail at `dbt parse` rather than `dbt compile`. On dbt 1.12,
`--use-v2-parser` tests v2 parse compatibility without switching engines.

Use dbt Core (v1) for production-quality execution and validation unless the
repo/platform explicitly adopts dbt v2. Developer tooling such as dbt Fusion (dbt v2) may
help locally, but final verification should run through the repo's dbt Core workflow when
that is the documented Sanofi standard.

Use the Sanofi Artifactory PyPI mirror in new `pyproject.toml` files:
`https://artifactory.sanofi.com/artifactory/api/pypi/public-mirror-python-pypi/simple`.

Sanofi workstation setup: use a Python virtual environment per project. Activate it with
`source .venv/bin/activate` (macOS/Linux) or `.venv\Scripts\Activate.ps1` (Windows
PowerShell). Windows users should use PowerShell or Git Bash from VS Code; WSL is not an
option under the referenced Sanofi security guidance. Windows only: if Git TLS
validation blocks cloning, check whether the workstation needs `git config --global
http.sslbackend schannel`; PowerShell script activation may require
`Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`. Do not run those two Windows
configuration commands on macOS or Linux.

## Profiles and Secrets

Always prefix sensitive env vars with `DBT_ENV_SECRET_`, and read them only from
`profiles.yml` and `packages.yml`. dbt disallows secret env vars everywhere else
(including `dbt_project.yml`, sources, macros, vars, and model SQL) so secrets cannot
reach the warehouse or artifacts; use a non-secret `DBT_` variable for anything those
files need. dbt scrubs secret values from its logs. Scrubbing does not protect secrets
embedded into SQL literals that reach Snowflake `QUERY_HISTORY`, so never build secrets
into query text.

Profile patterns:

- Use one env-var-driven target when CI/CD injects all environment values.
- Use explicit targets (`local`, `dev_live`, `uat_live`, `prod_live`) when distinct
  target names make operations and feature flags clearer.
- Local targets commonly use `authenticator: externalbrowser`.
- Live/CI targets commonly use key-pair auth via `DBT_ENV_SECRET_SNOWFLAKE_PRIVATE_KEY`
  and `DBT_ENV_SECRET_SNOWFLAKE_PRIVATE_KEY_PASSPHRASE`.
- Keep `schema` env-var driven, usually defaulting to a technical temp schema locally.

Threading: use `DBT_THREADS` with a sensible default instead of hardcoding per
environment. For Sanofi CWH, default to 8 when no local guidance exists; 4-8 is normal,
8-16 can fit large parallel DAGs, and 1 is for sequential debugging only.
Single-threading production wastes CWH concurrency.

## dbt_project.yml Baseline

For new projects, ensure `dbt_project.yml` covers:

- `name`, `version`, `config-version`, and `profile`.
- `model-paths`, `analysis-paths`, `test-paths`, `seed-paths`, `macro-paths`,
  `snapshot-paths`.
- `clean-targets`: `target`, `dbt_packages`, and `logs`.
- `query-comment` including node/model name, target, and `invocation_id`.
- `vars` for packages such as Elementary and dbt_project_evaluator.
- Folder-level model configs that stop at the folder level instead of overfitting every
  model in `dbt_project.yml`.
- `persist_docs` when Snowflake comments should receive dbt descriptions.
- `on-run-start` and `on-run-end` logs or hooks when useful for auditability.
- dbt flags such as disabled anonymous usage stats and partial parsing where appropriate.
- `dispatch` if project macros intentionally override package/built-in behavior.

When adding a new folder or schema mapping, first confirm the target Snowflake schema
exists through the approved registry, DDL, or CI/CD path. Then update folder-level
config in `dbt_project.yml` and inspect the project's `generate_schema_name` macro
instead of assuming dbt's default schema concatenation behavior.

On Snowflake, set persistence defaults once at the project or folder level rather than
per model: `copy_grants: true` so grants survive rebuilds, `persist_docs` for relation
and column comments, `transient: false` on persisted layers so Fail-safe and Time Travel
apply, `on_schema_change: append_new_columns` on incrementals, and `+full_refresh: false`
on persistent-staging/history layers so an accidental `--full-refresh` cannot wipe
retained history.

Guide examples include these dbt flags; keep them only when compatible with the project
and dbt version:

- `require_explicit_package_overrides_for_builtin_materializations: true`
- `source_freshness_run_project_hooks: true`
- `send_anonymous_usage_stats: false`
- `partial_parse: true`

## Deprecations and Strict Validation

dbt 1.10 warns on project code that dbt v2 rejects, and 1.11 enables the JSON-schema
deprecation warnings by default on Snowflake. Treat each new warning as required work,
not log noise, and clear them before any move to dbt v2.

- Find them: `dbt parse --no-partial-parse --show-all-deprecations` (on dbt v2 omit
  `--no-partial-parse`; the flag is deprecated there, warning `dbt1700`).
- Fix them: run `uvx dbt-autofix deprecations --dry-run` on a clean git branch, review the
  diff, then apply. `--include-packages` edits are reverted by the next `dbt deps`; upgrade
  the package instead (`dbt-autofix packages` checks dbt v2 compatibility). Its
  `manual_fixes/` list covers what it cannot do: dynamic SQL, custom configuration read in
  macros, misspelled config keys, sources without tables, and incompatible packages.
- NEVER hide them as the fix. `--warn-error-options '{"silence": ["Deprecations"]}'` or
  `flags: warn_error_options: silence:` is a temporary noise filter. If CI uses `--warn-error`,
  1.10 promotes new deprecations to errors; scope with `"warn": ["Deprecations"]` while
  migrating. The old `include`/`exclude` keys of `warn_error_options` are now `error`/`warn`.

| Invalid on dbt >= 1.10 | Valid form |
|---|---|
| Custom keys (`owner: x`) under a resource, `config`, or at YAML top level | `config: {meta: {owner: x}}`; read with `config.meta_get('owner')` (1.11, backported to 1.10), not `config.get('owner')` |
| Top-level `freshness`, `meta`, `tags`, `docs`, `group`, `access` properties | Same keys under `config:` |
| `materialized: table` without `+` in `dbt_project.yml` | `+materialized: table`; only folder and file names go unprefixed |
| Standalone top-level YAML anchors | Define them under a top-level `anchors:` key |
| `-m` / `--model` / `--models` | `-s` / `--select` (silently ignored selection builds the whole DAG) |
| `dbt source freshness -o <path>` | `--target-path` for the whole step |
| `log-path` / `target-path` in `dbt_project.yml` (1.11) | `--log-path` / `--target-path` or `DBT_ENGINE_LOG_PATH` / `DBT_ENGINE_TARGET_PATH` |
| Source `overrides:` property | Enable or disable the package source instead |
| Duplicate YAML keys, orphan `{% endmacro %}` | Delete them (dbt used the last duplicate silently) |

From 1.11 engine environment variables use the `DBT_ENGINE_` prefix (`DBT_STATE` becomes
`DBT_ENGINE_STATE`); check CI scripts that export engine-level `DBT_*` flags against the
resolved version. Project-owned variables read with `env_var()` (for example
`DBT_THREADS`, `DBT_ENV_SECRET_*`) are not engine flags and keep their names.

On dbt 1.10.8+ the `require_generic_test_arguments_property` flag defaults to `true`, so
top-level test keyword arguments warn (`MissingArgumentsPropertyInGenericTestDeprecation`).
A custom generic test that already has a parameter named `arguments` must rename it
inside the macro, then pass it nested under `arguments:`.

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

NEVER use `insert_overwrite` on Snowflake to "replace a partition". dbt-snowflake's
`insert_overwrite` is not partition-based: it behaves like `INSERT OVERWRITE`, truncating
and re-inserting the whole table every run, so it keeps the object but erases any rows
the model query does not return — including history, on history-bearing models (SCD2,
PSA, anything where source rows disappear). Use it only when the model query rebuilds
the complete result every run; otherwise use `merge` (keyed by `unique_key`) or
`delete+insert` with `incremental_predicates`, which preserve unaffected rows and the
table's Time Travel lineage. A plain `table` drops and recreates the object every run,
which resets Time Travel and Fail-safe; keep it for small lookup/reference data where
history does not matter. Snowflake dynamic tables are an exception to use only when the
orchestrator cannot meet the required latency or for internal helper tables; document
the reason in the model YAML. When one is justified, set `copy_grants: true` (dbt-snowflake
>= 1.11; the default `false` drops grants when `--full-refresh` recreates it) and
`refresh_warehouse` apart from the DDL `snowflake_warehouse` (>= 1.11). On 1.12 dbt defaults
`scheduler` to `DISABLE`, but setting `target_lag` without `scheduler` turns Snowflake's
scheduler on, so set both deliberately.

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
rates on key attributes — using audit_helper.

## Testing

For data-test work, use `writing-data-tests.md`. Keep these routing rules in mind:

- Data tests check real Snowflake data; unit tests check transformation logic with
  small mock inputs.
- Staging focuses on `not_null`, `unique`, relationships, and freshness.
- Intermediate focuses on unit tests for complex or grain-changing logic.
- Marts focus on relationships, accepted values, and business invariants.
- Normalize legacy Confluence `tests:` snippets to `data_tests:` unless the repo is
  intentionally pinned to the older style.
- Nest generic test parameters under `arguments` only when the project runs dbt
  >= 1.10.5 (the property is documented as available from 1.10.5); on older versions
  keep them as top-level properties of the test. Config such as `severity`, `where`, and
  `store_failures` stays under `config:`. From 1.10.8 the flag default makes top-level
  parameters warn; 1.10.5-1.10.7 accept both forms.

If a repo uses a `run_dq_check` macro, treat it as a pre-hook data quality gate. In the
standards page example it wraps `DQ_SF.SP_DQ_FETCH_CUSTOM_CHECKS`; a critical
`PROCESS_HALT` result aborts the model, writes details to `DQ_ERROR_DETAILS`, and
propagates through the orchestrator/alerting path. Inspect the project macro before
changing arguments or failure semantics.

Before PR merge, relevant scoped dbt tests should pass with zero error-level failures.
At minimum, cover the model grain with `unique`/`not_null`, foreign keys with
`relationships`, and controlled categorical mart fields with `accepted_values` when
the allowed values are verified.

## Observability

Use Elementary for dbt-native observability when the project includes it. Add both the
dbt package and CLI dependency, isolate Elementary objects in a monitoring schema,
and run `dbt build` or `dbt run` plus `dbt test` before `edr report`; `dbt compile`
alone does not populate Elementary metadata. For local or WAP-silent runs, set the
Elementary vars that disable artifact autoupload, run results, and test results when
project policy requires shared monitoring tables to stay clean. Use anomaly tests such as
`elementary.volume_anomalies` and `elementary.freshness_anomalies` only where project
policy supports them. Elementary CLI reuses dbt profiles: `-t` selects the Elementary
connection target, while `--project-profile-target` points at the dbt target that
produced artifacts. Generated local reports land under `edr_target/`.

Some projects wire Elementary with a separate `elementary` profile/target,
`on-run-end` hooks such as `elementary.upload_dbt_invocation()`, and anomaly tests like
`elementary.volume_anomalies` and `elementary.freshness_anomalies` keyed on the model's
technical modified timestamp, often `tech_modified_ts`. Treat Elementary anomalies as
observability/reporting signals unless the project explicitly
hard-fails on them.

For triage, set `store_failures: true` (project-wide or per test) so failing test rows
persist into a dedicated DQ/audit schema instead of only a count; Elementary keeps
per-run history in its `test_results` and `test_result_rows` models on top of that. Tune
the captured sample size per test with `meta.elementary.test_sample_row_count`. Beyond
`edr report`, `edr monitor` sends failure and anomaly alerts to Slack, Teams, or email
when the project wires alerting.

## Unit Tests

Use dbt unit tests for business logic, calculations, currency/unit conversions,
conditional mappings, and edge cases that should be validated before scanning large
tables. Unit test YAML definitions belong under `model-paths` (default `models/`),
not in the `tests/` directory, which is reserved for data tests; fixture files can live
under test-path `fixtures` directories.

To unit-test an incremental model's `is_incremental()` branch, force it with
`overrides: {macros: {is_incremental: true}}` and mock the current target contents with a
`given` input of `this`; this is how you cover same-day dedup or merge logic
deterministically. Name cases `scenario__expected` and keep their YAML next to the
model under `models/<domain>/`. Run all unit tests with `dbt test --select
"test_type:unit"`, generic/schema tests with `dbt test --select "test_type:generic"`,
and a single unit-test case with `dbt test --select "unit_test:<case>"`. To select
generic tests by their generic-test name, use `dbt test --select "test_name:<name>"`.
Unit tests require dbt-core >= 1.8.

Unit-test prerequisites and limits:

- Direct parents (and the incremental model itself) must already exist in the target
  schema so dbt can read column types. In a clean CI schema build empty shells first:
  `dbt run --select "<parents>" --empty`, or `dbt run --select
  "config.materialized:incremental" --empty`.
- An ephemeral parent needs `format: sql` for that `given` input. SQL `join` logic needs
  aliased tables.
- Models using `materialized_view`, recursive SQL, or introspective queries cannot be
  unit tested; only models in the current project can.
- Run them in development and CI only. Their inputs are static, so production runs waste
  warehouse compute: `dbt build --exclude-resource-type unit_test` or
  `DBT_ENGINE_EXCLUDE_RESOURCE_TYPES=unit_test` (1.11+). For `dbt test`,
  `--select "test_type:data"` runs only data tests on both v1 and v2 (`--exclude-resource-type`
  works there on v1 only).
- A disabled model disables its unit tests (1.11+). On dbt v2, `dbt build` runs all unit
  tests before the rest of the DAG.

## Selectors and CI

Do not default to global runs. Select the smallest meaningful scope with upstream
(`+model_name`), downstream (`model_name+`), both directions (`+model_name+`), folder,
tag, or `state:modified+` selectors. Use state-based selection in CI/CD when a prior
successful `manifest.json` is available, and apply the same scoped selector to `run`,
`test`, or `build`. Include `--state` unless the orchestration environment already
supplies the prior manifest location; add `--defer` only when intentionally resolving
unchanged refs to the prior state.

For orchestration, pick one consistent gate pattern per DAG: `dbt build` for dependency-
ordered run/test behavior, or explicit per-layer `dbt run` plus `dbt test` tasks when
downstream layers must wait for intermediate test feedback. Do not mix both patterns
inside one pipeline without a documented reason. PR checks commonly combine scoped
`dbt compile`, scoped `dbt test`, SQLFluff over `transformation/`, and optional
dbt_project_evaluator where the repo has approved it. For authoring the Airflow/MWAA DAGs
that run dbt (`BashOperator` + `dbt_run.sh` or a typed `DbtClient`, scheduling, parse-time
safety, deployment), use the sanofi-airflow skill.

## Tags

Use tags for orchestration and discoverability:

- Frequency tags such as `hourly` or `daily`.
- Department/domain tags such as `finance`.
- Compute tags such as `heavy_compute` for larger Snowflake warehouses.

Have orchestrators select models by tag rather than by file path or model name, so that
moving or renaming files during a refactor does not silently break scheduled runs.

## Incremental Models

For incremental models, verify:

- `unique_key` is correct and truly unique.
- `incremental_strategy` matches the warehouse behavior.
- `on_schema_change` is intentional.
- `cluster_by` aligns with filter or predicate columns.
- `is_incremental()` includes an adequate lookback for late-arriving data.

Separate source and target pruning: `is_incremental()` filters source reads,
`incremental_predicates` filter destination scans, `unique_key` matches incoming rows
to target rows, and `cluster_by` should align with predicate/filter columns.

The source lookback window should be smaller than the target predicate window. Example:
read the last 3 days from source, but let Snowflake scan the last 7 days of the target
so late-arriving data can still merge into existing records.

On the first run, `is_incremental()` is false and the model should build full history.
On later incremental runs, it is true and should read only the configured delta window.

Schema-change choices: `ignore` for stable schemas, `append_new_columns` for evolving
schemas, `sync_all_columns` cautiously because it can break consumers, and `fail` when
drift should stop the run. Backfill with full refresh for small/medium tables,
variable windows for large tables, and direct DML only for exceptional fixes.

Full refresh may require drop permissions. Treat it as the simple but potentially costly
and disruptive option for large or permission-constrained tables. A resource config
`full_refresh: false` overrides the `--full-refresh` flag (the resource is never fully
refreshed) and `full_refresh: true` forces a rebuild even without the flag, so check the
resource config before assuming the flag rebuilds a protected layer. Snapshots ignore
both.

Microbatch: for large time-series models with a reliable event timestamp, consider
`incremental_strategy='microbatch'` (dbt >= 1.9) instead of a hand-written
`is_incremental()` window. On Snowflake dbt implements it with `delete+insert` per
batch, so no `unique_key` is needed and each batch is replaced as a whole. Rules:

- `event_time`, `begin`, and `batch_size` (`hour|day|month|year`) are required; `lookback`
  (default 1) reprocesses prior batches for late data. All values are UTC.
- Set `event_time` on the model AND on every upstream model that should be filtered. An
  upstream without it is fully scanned on every batch. Opt a ref out of filtering only
  deliberately, with `ref('x').render()`.
- The query MUST return exactly one batch window. NEVER add an `is_incremental()` filter.
- Set `full_refresh: false` (consistent with the persistent-layer rule above). Reprocess
  history with a bounded backfill; both bounds are required together:
  `dbt run --select <model> --event-time-start "2024-01-01" --event-time-end "2024-02-01"`.
  `dbt retry` reruns only failed batches; Snowflake batches can run concurrently
  (`concurrent_batches`).
- Poor fit: no trustworthy event timestamp, hash-based change detection, or logic that
  needs the previous table state. A reprocessed window drops rows the query no longer
  returns, so do not use it for history-bearing PSA/SCD models.

For hash-based incremental models, identify rows with a stable technical key hash
generated from the business key (for example with `dbt_utils.generate_surrogate_key`)
and detect changes with a payload hash generated from the payload columns. Use `merge`
with the technical key as `unique_key`, and exclude audit columns such as creation
timestamps from updates via `merge_exclude_columns` when the repo does so. Select new or
changed rows by hash comparison rather than a time watermark. Truncate/reload
working-layer exceptions should not carry an `is_incremental()` delta filter.

Filter placement matters for performance. Read the current high-water mark once in a
small watermark CTE (`select coalesce(max(<changed_ts>), <floor_date>) from {{ this }}`)
and apply that value inside the driving table's `WHERE`, before any joins, so Snowflake
prunes micro-partitions at the storage layer. Applying the same filter in an outer
`WHERE` after all joins have run is a common anti-pattern: Snowflake still scans the full
source and evaluates every join before discarding unchanged rows, which can be slower
than a full rebuild. Guard nullable watermark columns with `OR <col> IS NULL`, and for a
modification date that lives on a left-joined table add `OR <joined>.<date> IS NULL` so
unmatched rows are not silently dropped. If the timestamp is derived, use the same
expression (for example a `GREATEST(...)` of lifecycle timestamps) in the filter.

When the source exposes no reliable modification timestamp, `merge` or `delete+insert`
on the `unique_key` alone (no delta filter) still avoids the drop/recreate of a full
rebuild and preserves Time Travel, even though every source row is still scanned.

Orchestrated pipelines often make runs idempotent and reprocessable by filtering the
source on an explicit run window passed as vars (for example `var('data_interval_start')`
/ `var('data_interval_end')` from the scheduler) instead of, or alongside, a `max()`
watermark. Seed the table with one full refresh, then run incrementally; keep a manual
full refresh available for periodic rebuilds.

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

## Model Versioning and Contracts

Final dbt models consumed by other teams or systems behave like APIs. Use dbt model
versioning for breaking changes:

- Removing or renaming columns.
- Changing data types.
- Changing grain.

Keep older versions available until consumers migrate. Reference specific versions with
`ref('model_name', v=1)` when backward compatibility is required.

Use model contracts for shared models where downstream processes need schema guarantees:
define column names and data types, enforce the contract, and consider
`alias_types: false` on Snowflake when exact types matter.

## Snowflake Query Tracking

Use `query-comment` with node name, target, and `invocation_id`, plus `append: true`, to
make dbt runs traceable in Snowflake query history.

## Feature Flags

Use the local `disable_when()` macro pattern when present. Feature flags are for
temporary operational control such as WIP trunk models, sources not ready in higher
environments, risky rollouts, scheduled go-live, and kill switches; avoid them for
permanent disables, A/B testing, percentage rollout, user-specific logic, or normal
environment config. Use `targets`, `environments`, `databases`, or runtime `flag`
parameters according to the repo pattern. With multiple `disable_when()` parameters,
the guide's macro disables only when all supplied conditions match; database matching
is intended to be case-insensitive. Document each temporary flag with ticket, reason,
and expected removal date; add visibility tags; review regularly; remove released
flag code. Runtime values that disable a flag are `false`, `0`, `off`, `disabled`,
and `no`; unset flags default to enabled. Use names like `DBT_FLAG_<MODEL>`,
`DBT_FLAG_<FEATURE>`, or `DBT_FLAG_<TEAM>_<THING>`.

## Write Audit Publish

Use WAP only when the project has `sanofi-dbt-utils` WAP macros installed and configured.
WAP protects table/incremental models by writing to `__wap` tables, auditing tests,
then publishing with Snowflake metadata operations. Activation requires both runtime
`DBT_WAP_ENABLED=true` and model opt-in `meta: {wap_enabled: true}`. Prefer folder-level
WAP for protected warehouse marts, not views; keep it off locally unless testing WAP.
For incrementals, use the project WAP pre-hook so the WAP table starts from a zero-copy
clone. Register the WAP on-run-end hook, keep the audit table for compliance, and
initialize it with `wap_init_audit_table` when needed.

Typical WAP flow: run the WAP scope, test the same scope, inspect `wap_status`, publish
with `wap_publish_all`, then run or test the published layer. When Elementary is active,
silence Elementary during WAP runs and run a clean post-publish phase so reports capture
base-table artifacts, not `__wap` artifacts.

WAP safety: publishing should block recent `test_failed` audit status; the current safe
mode blocks publish when the audit table has a recent `test_failed` status for the
model, commonly within the last 24 hours. `force: true` is a human escape hatch after
investigation, never an automated default. Use `wap_status`, `wap_compare`, and
`wap_diff` before publishing, and discard/cleanup operations for failed or stale
`__wap` tables. Publish is per-table atomic, not multi-table atomic; orchestration must
skip publish if any protected model fails. First deploy promotes `__wap` by rename when
no base table exists. Audit statuses include `pending`,
`test_passed`, `test_failed`, `published`, and `discarded`, with invocation, logical
model, WAP/base table, schema/database, materialization, status, error, and timestamps.

WAP by environment:

- Local: off unless explicitly forced; the missing env var keeps the two-key lock off.
- Dev: optional for workflow testing.
- UAT: recommended to validate the full flow before production.
- Prod: required for protected warehouse tables when WAP is adopted.

Important WAP naming rule: macro arguments such as `table_name` usually mean the
physical Snowflake alias, not the dbt SQL filename.

## Troubleshooting Checklist

Common fixes: duplicates -> verify `unique_key` or stable project surrogate key;
missing new columns -> intentional `on_schema_change`; slow incrementals -> align
`cluster_by` with predicates; expensive full rebuilds -> consider justified
`incremental`; history wrong -> full refresh/backfill; late-arriving data -> widen
lookback; snapshot not changing -> verify `updated_at`; deletes missing -> hard-delete
invalidation; slow unit tests -> select `test_type:unit`; wrong schema -> inspect
`generate_schema_name` and `+schema`; secrets in logs -> `DBT_ENV_SECRET_`; wrong
source table -> `source()`; thread waste -> `DBT_THREADS` with local/project guidance;
WAP failure -> inspect `__wap`, run `wap_diff`, fix or discard, and use `force: true`
only after accepted risk.

## Anti-Patterns

Avoid `SELECT *`, hardcoded databases/schemas, one giant `schema.yml`, skipped staging
tests, full CI runs when `state:modified+` fits, snapshotting raw data, schema creation
through dbt, business logic or multi-source joins in staging, direct staging-to-mart
for complex transformations, permanent flags without cleanup tickets, automated WAP
`force: true`, stale `__wap` tables, global materialization overrides that affect
packages such as Elementary, and large CSV seeds.

## Command Reference

Use standard dbt commands with scoped selectors: `run`, `test`, `build`, `snapshot`,
`seed`, `source freshness`, `docs generate/serve`, `compile`, `ls`, `debug`, `deps`,
and `clean`. Sanofi-specific operations to remember: dbt_project_evaluator package
builds, `edr report`, WAP operations (`wap_status`, `wap_compare`, `wap_diff`,
`wap_publish_all`, discard/cleanup/init operations), and audit_helper comparisons
(`compare_relations`, `compare_column_values`, `compare_all_columns`,
`compare_queries`).

## Sources

External sources for the version-sensitive rules in this skill (dbt v1.10-v1.12, dbt v2,
dbt-snowflake). Re-check them when the project's resolved versions differ:

- [Upgrading to v1.10](https://docs.getdbt.com/docs/dbt-versions/core-upgrade/upgrading-to-v1.10): deprecation warnings, `meta`/`config` nesting, `anchors:`, `--models`, `warn_error_options` rename, dbt-snowflake 1.10.6 column-size note.
- [Upgrading to v1.11](https://docs.getdbt.com/docs/dbt-versions/core-upgrade/upgrading-to-v1.11): UDFs, `DBT_ENGINE_` env prefix, default-on JSON-schema deprecations, dynamic-table configs, `config.meta_get()`, disabled models disable unit tests.
- [Upgrading to v1.12](https://docs.getdbt.com/docs/dbt-versions/core-upgrade/upgrading-to-v1.12): `--use-v2-parser`, `scheduler` default for Snowflake dynamic tables, `--sql` for `run-operation`.
- [Upgrading to v2](https://docs.getdbt.com/docs/dbt-versions/core-upgrade/upgrading-to-v2): strict parse-time validation, `pip install dbt`, manifest compatibility, unit tests first in `dbt build`.
- [Deprecations](https://docs.getdbt.com/reference/deprecations): `--show-all-deprecations`, each warning's resolution, silencing.
- [Behavior change flags](https://docs.getdbt.com/reference/global-configs/behavior-changes) and [`require_generic_test_arguments_property`](https://docs.getdbt.com/reference/global-configs/behavior-flags/require_generic_test_arguments_property): `arguments:` introduced 1.10.5, default 1.10.8.
- [Data tests property](https://docs.getdbt.com/reference/resource-properties/data-tests): `arguments:` and `config:` placement.
- [Microbatch incremental models](https://docs.getdbt.com/docs/build/incremental-microbatch) and [Incremental strategies](https://docs.getdbt.com/docs/build/incremental-strategy): required configs, backfill, per-adapter implementation.
- [Unit tests](https://docs.getdbt.com/docs/build/unit-tests) and [`--resource-type`](https://docs.getdbt.com/reference/global-configs/resource-type): limits, `--empty`, ephemeral inputs, excluding unit tests in production.
- [Snapshots](https://docs.getdbt.com/docs/build/snapshots): `hard_deletes`, `dbt_valid_to_current`, optional `target_schema`.
- [Source freshness config](https://docs.getdbt.com/reference/resource-configs/freshness): `loaded_at_query`, `config:` nesting.
- [Snowflake configurations](https://docs.getdbt.com/reference/resource-configs/snowflake-configs): `insert_overwrite` behavior, dynamic tables, `copy_grants`, `LAST_ALTERED` freshness caveat.
- [Environment variable configs](https://docs.getdbt.com/reference/global-configs/environment-variable-configs): `DBT_ENGINE_` prefix.
- [dbt-autofix](https://github.com/dbt-labs/dbt-autofix): deprecation autofix, `packages`, `manual_fixes/`.
- [dbt v1 pip install best practices](https://docs.getdbt.com/faqs/Core/install-pip-best-practices): v1 installs use `dbt-core`/`dbt-<adapter>`.
