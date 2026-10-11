# Project Setup, Profiles, and Deprecations

Environment setup, profiles and secrets, the `dbt_project.yml` baseline, and deprecation
handling for Sanofi dbt projects. Moved from `general-dbt-guide.md`; layer, naming, and
model-development rules stay there. Upgrade procedure is in
[upgrading.md](upgrading.md).

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
available, and 1.10.5-1.10.7, where it needs `require_generic_test_arguments_property: true`;
check the resolved version and flag before using patch-level features. They also admit
`dbt-snowflake` below 1.10.6, which can fail incremental models that combine
`on_schema_change: sync_all_columns` with collated string columns once Snowflake's
default string/binary column-size change ([BCR 2118](https://docs.snowflake.com/en/release-notes/bcr-bundles/un-bundled/bcr-2118))
is deployed. Snowflake has postponed BCR 2118 to a future bundle with no date, so treat
this as conditional on its eventual rollout. Find exposed models with `dbt ls -s
config.materialized:incremental,config.on_schema_change:sync_all_columns
--resource-type model`; if any match, resolve `dbt-snowflake>=1.10.6`.

The bare `dbt` PyPI package is dbt v2 (since 2026-09-14), so for a 1.x project NEVER install
it (`pip install dbt`, `uv add dbt`, `uv tool install dbt`); install `dbt-core` and
`dbt-snowflake` at the repository's pins and run `dbt --version` to confirm the engine on
`PATH` before trusting a parse or test result. The upgrade procedure is in
[upgrading.md](upgrading.md#engines-and-install).

Install with uv. An existing repo on poetry, pip-tools, or plain requirements files keeps
its manager; recommend uv for new work only.

- New project: `uv init`, set `requires-python = ">=3.11,<3.12"`, `uv python pin 3.11`,
  then `uv add "dbt-core==1.10.*" "dbt-snowflake==1.10.*"` plus the toolchain above.
  Commit `uv.lock`; run dbt as `uv run dbt ...`; CI uses `uv sync --locked`.
- Requirements-file repo: `uv venv --python 3.11`, then
  `uv pip install -r requirements.txt`.
- Standalone v1 CLI outside a project: `uv tool install "dbt-core==<pin>" --with
  "dbt-snowflake==<pin>"` (adapter shares the tool environment).
- NEVER `pip install` into a system or Homebrew Python.

Use the Sanofi Artifactory PyPI mirror in new `pyproject.toml` files as the default index:

```toml
[[tool.uv.index]]
name = "sanofi-artifactory"
url = "https://artifactory.sanofi.com/artifactory/api/pypi/public-mirror-python-pypi/simple"
default = true
```

Outside a project (`uv tool install`, `uvx`), pass `--default-index <mirror-url>` or set
`UV_DEFAULT_INDEX=<mirror-url>`.

Sanofi workstations: one environment per project (`.venv`, created by uv). `uv run`
needs no activation; to activate manually use `source .venv/bin/activate` (macOS/Linux)
or `.venv\Scripts\Activate.ps1` (Windows PowerShell). Windows users SHOULD use PowerShell
or Git Bash from VS Code; WSL is not an option under the referenced Sanofi security
guidance. Windows only: if Git TLS validation blocks cloning, check whether the
workstation needs `git config --global http.sslbackend schannel`; if uv fails TLS against
the mirror behind the corporate proxy, use the OS trust store with `--system-certs` or
`UV_SYSTEM_CERTS=true`. Manual PowerShell activation may require
`Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`. Do not run the `git config` or
`Set-ExecutionPolicy` commands on macOS or Linux.

## Profiles and Secrets

Always prefix sensitive env vars with `DBT_ENV_SECRET_`, and read them only from
`profiles.yml` and `packages.yml`. dbt disallows secret env vars everywhere else
(including `dbt_project.yml`, sources, macros, vars, and model SQL) so secrets cannot
reach the warehouse or artifacts; use a non-secret `DBT_` variable for anything those
files need. dbt scrubs secret values from its logs. Scrubbing does not protect secrets
embedded into SQL literals that reach Snowflake `QUERY_HISTORY`, so NEVER build secrets
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
retained history. See [snowflake-materializations.md](snowflake-materializations.md#tables-transience-and-grants).

Guide examples include these dbt flags; keep them only when compatible with the project
and dbt version:

- `require_explicit_package_overrides_for_builtin_materializations: true`
- `source_freshness_run_project_hooks: true`
- `send_anonymous_usage_stats: false`
- `partial_parse: true`

## Deprecations and Strict Validation

dbt 1.10 warns on project code that later versions reject, and 1.11 enables the JSON-schema
deprecation warnings by default on Snowflake. Treat each new warning as required work,
not log noise.

- Find them: `dbt parse --no-partial-parse --show-all-deprecations`.
- Fix them: run `uvx dbt-autofix deprecations --dry-run` on a clean git branch, review the
  diff, then apply. `--include-packages` edits are reverted by the next `dbt deps`; upgrade
  the package instead (`dbt-autofix packages` checks package compatibility). Its
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
On 1.10.5-1.10.7 the default is `false` and the nested form warns instead
(`ArgumentsPropertyInGenericTestDeprecation`) unless the flag is set to `true` in
`dbt_project.yml`. A custom generic test that already has a parameter named `arguments`
MUST rename it inside the macro, then pass it nested under `arguments:`.

## Checklist

- Existing project: repository lockfile and `pyproject.toml` followed; engine confirmed with `dbt --version`; no bare `dbt` install in a v1 project.
- Secrets only through `DBT_ENV_SECRET_*` in `profiles.yml` and `packages.yml`.
- `dbt_project.yml` baseline covered; schema mappings confirmed with the approved registry before folder config changes.
- Deprecation parse clean (`--show-all-deprecations`); warnings fixed, not silenced.

## Sources

External sources for the version-sensitive rules in this file (dbt 1.10-1.12,
dbt-snowflake). Re-check them when the project's resolved versions differ:

- [Upgrading to v1.10](https://docs.getdbt.com/docs/dbt-versions/dbt-upgrade/upgrading-to-v1.10): deprecation warnings, `meta`/`config` nesting, `anchors:`, `--models`, `warn_error_options` rename, dbt-snowflake 1.10.6 column-size note.
- [Upgrading to v1.11](https://docs.getdbt.com/docs/dbt-versions/dbt-upgrade/upgrading-to-v1.11): UDFs, `DBT_ENGINE_` env prefix, default-on JSON-schema deprecations, dynamic-table configs, `config.meta_get()`, disabled models disable unit tests.
- [Upgrading to v1.12](https://docs.getdbt.com/docs/dbt-versions/dbt-upgrade/upgrading-to-v1.12): `scheduler` default for Snowflake dynamic tables, `--sql` for `run-operation`.
- [Deprecations](https://docs.getdbt.com/reference/deprecations): `--show-all-deprecations`, each warning's resolution, silencing.
- [Behavior change flags](https://docs.getdbt.com/reference/global-configs/behavior-changes) and [`require_generic_test_arguments_property`](https://docs.getdbt.com/reference/global-configs/behavior-flags/require_generic_test_arguments_property): `arguments:` introduced 1.10.5, default 1.10.8.
- [Data tests property](https://docs.getdbt.com/reference/resource-properties/data-tests): `arguments:` and `config:` placement.
- [Snapshots](https://docs.getdbt.com/docs/build/snapshots): `hard_deletes`, `dbt_valid_to_current`, optional `target_schema`.
- [Source freshness config](https://docs.getdbt.com/reference/resource-configs/freshness): `loaded_at_query`, `config:` nesting.
- [Environment variable configs](https://docs.getdbt.com/reference/global-configs/environment-variable-configs): `DBT_ENGINE_` prefix.
- [dbt-autofix](https://github.com/dbt-labs/dbt-autofix): deprecation autofix, `packages`, `manual_fixes/`.
- [Installing dbt v1 with pip](https://docs.getdbt.com/faqs/Core/install-pip-best-practices.md): v1 installs use `dbt-core`/`dbt-<adapter>`; [dbt platform CLI migration](https://docs.getdbt.com/docs/platform/platform-cli-migration): `dbt` on PyPI is v2 from 2026-09-14.
- uv: [package indexes](https://docs.astral.sh/uv/concepts/indexes/) (`[[tool.uv.index]]`, `default = true`, `UV_DEFAULT_INDEX`) and [TLS certificates](https://docs.astral.sh/uv/concepts/authentication/certificates/) (`--system-certs`, `UV_SYSTEM_CERTS`).
