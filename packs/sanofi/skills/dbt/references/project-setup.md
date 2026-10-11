# Project Setup, Profiles, and Deprecations

Environment, profiles and secrets, the `dbt_project.yml` baseline, and deprecation handling for Sanofi dbt projects. Moved from `general-dbt-guide.md`; layer, naming, and model-development rules stay there. Upgrade procedure → [upgrading.md](upgrading.md). Governing rule: existing project's lockfile and conventions bind; the baseline below applies only where nothing stricter exists.

## Setup and Environment

### Baseline and pins

Existing environment manager first. New Sanofi dbt projects, guide baseline: Python `>=3.11,<3.12`; `dbt-core==1.10.*`; `dbt-snowflake==1.10.*`; `elementary-data[snowflake]>=0.20.0`; `schemachange>=4.0.0`; `snowflake-connector-python>=3.0.0`; `dotenv>=0.9.9`; `pre-commit>=4.3.0`; `ruff>=0.9.7`; `sqlfluff>=3.5`; `sqlfluff-templater-dbt>=3.5`. Optional orchestration/refactor packages: `apache-airflow[amazon]==2.10.3`, `boto3>=1.40,<1.50`, `recce>=1.21,<1.22`, `dbt-colibri>=0.2.6`, `dbterd>=1.0.0`.

**Existing project:** repository lockfile, `pyproject.toml`, and onboarding docs bind. Older installation SOPs may still pin dbt Core 1.9.2 for tool compatibility. Use the OneMesh 1.10 baseline only when creating or modernizing a project with no stricter local constraint.

**Patch-level hazards admitted by `1.10.*` pins** — check the resolved version and flag before using patch-level features:

| Resolved | Hazard |
|---|---|
| dbt-core < 1.10.5 | `arguments:` test property unavailable |
| dbt-core 1.10.5-1.10.7 | `arguments:` needs `require_generic_test_arguments_property: true` |
| `dbt-snowflake` < 1.10.6 | Incrementals combining `on_schema_change: sync_all_columns` with collated string columns can fail once Snowflake's default string/binary column-size change ([BCR 2118](https://docs.snowflake.com/en/release-notes/bcr-bundles/un-bundled/bcr-2118)) deploys |

Snowflake postponed BCR 2118 to a future bundle, no date ⇒ hazard is conditional on eventual rollout. Find exposed models; any match ⇒ resolve `dbt-snowflake>=1.10.6`:

```bash
dbt ls -s config.materialized:incremental,config.on_schema_change:sync_all_columns --resource-type model
```

**Bare `dbt` is v2.** The bare `dbt` PyPI package is dbt v2 (since 2026-09-14). A 1.x project NEVER installs it (`pip install dbt`, `uv add dbt`, `uv tool install dbt`); install `dbt-core` and `dbt-snowflake` at the repository's pins; run `dbt --version` to confirm the engine on `PATH` before trusting a parse or test result. Procedure → [upgrading.md](upgrading.md#engines-and-install).

### Install with uv

Existing repo on poetry, pip-tools, or plain requirements files keeps its manager; recommend uv for new work only.

| Case | Steps |
|---|---|
| New project | `uv init`; `requires-python = ">=3.11,<3.12"`; `uv python pin 3.11`; `uv add "dbt-core==1.10.*" "dbt-snowflake==1.10.*"` plus the toolchain above. Commit `uv.lock`; run `uv run dbt ...`; CI `uv sync --locked` |
| Requirements-file repo | `uv venv --python 3.11`; `uv pip install -r requirements.txt` |
| Standalone v1 CLI outside a project | `uv tool install "dbt-core==<pin>" --with "dbt-snowflake==<pin>"` (adapter shares the tool environment) |

**NEVER** `pip install` into a system or Homebrew Python.

### Artifactory mirror

Default index in new `pyproject.toml` files:

```toml
[[tool.uv.index]]
name = "sanofi-artifactory"
url = "https://artifactory.sanofi.com/artifactory/api/pypi/public-mirror-python-pypi/simple"
default = true
```

Outside a project (`uv tool install`, `uvx`): `--default-index <mirror-url>` or `UV_DEFAULT_INDEX=<mirror-url>`.

### Workstations

One environment per project (`.venv`, created by uv). `uv run` needs no activation; manual: `source .venv/bin/activate` (macOS/Linux), `.venv\Scripts\Activate.ps1` (Windows PowerShell). Windows SHOULD use PowerShell or Git Bash from VS Code; WSL unavailable under the referenced Sanofi security guidance.

**Windows only** — NEVER run these on macOS/Linux:

- Git TLS validation blocks cloning → check whether the workstation needs `git config --global http.sslbackend schannel`.
- uv fails TLS against the mirror behind the corporate proxy → OS trust store: `--system-certs` or `UV_SYSTEM_CERTS=true`.
- Manual PowerShell activation may need `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`.

## Profiles and Secrets

**Secrets.** Prefix sensitive env vars `DBT_ENV_SECRET_`; read only from `profiles.yml` and `packages.yml`. dbt disallows them everywhere else (`dbt_project.yml`, sources, macros, vars, model SQL) so secrets cannot reach the warehouse or artifacts; use a non-secret `DBT_` variable for what those files need. dbt scrubs secret values from logs, but not secrets embedded in SQL literals that reach Snowflake `QUERY_HISTORY` ⇒ NEVER build secrets into query text.

| Pattern | Use when |
|---|---|
| One env-var-driven target | CI/CD injects all environment values |
| Explicit targets (`local`, `dev_live`, `uat_live`, `prod_live`) | Distinct target names clarify operations and feature flags |
| `authenticator: externalbrowser` | Local targets (common) |
| Key-pair auth via `DBT_ENV_SECRET_SNOWFLAKE_PRIVATE_KEY` + `DBT_ENV_SECRET_SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` | Live/CI targets (common) |

`schema`: env-var driven, usually defaulting to a technical temp schema locally.

**Threading.** `DBT_THREADS` with a sensible default, not hardcoded per environment. Sanofi CWH default 8 absent local guidance; 4-8 normal; 8-16 fits large parallel DAGs; 1 = sequential debugging only. Single-threading production wastes CWH concurrency.

## dbt_project.yml Baseline

New projects cover:

- `name`, `version`, `config-version`, `profile`.
- `model-paths`, `analysis-paths`, `test-paths`, `seed-paths`, `macro-paths`, `snapshot-paths`.
- `clean-targets`: `target`, `dbt_packages`, `logs`.
- `query-comment` with node/model name, target, `invocation_id`.
- `vars` for packages such as Elementary and dbt_project_evaluator.
- Folder-level model configs; stop at folder level, no per-model overfitting.
- `persist_docs` when Snowflake comments should receive dbt descriptions.
- `on-run-start`/`on-run-end` logs or hooks when useful for auditability.
- dbt flags: anonymous usage stats disabled, partial parsing where appropriate.
- `dispatch` if project macros intentionally override package/built-in behavior.

**New folder or schema mapping:** confirm the target Snowflake schema exists through the approved registry, DDL, or CI/CD path → update folder-level config in `dbt_project.yml` → inspect the project's `generate_schema_name` macro; never assume dbt's default schema concatenation.

**Snowflake persistence defaults** — set once at project or folder level, not per model:

| Setting | Effect |
|---|---|
| `copy_grants: true` | Grants survive rebuilds |
| `persist_docs` | Relation and column comments |
| `transient: false` on persisted layers | Fail-safe and Time Travel apply |
| `on_schema_change: append_new_columns` on incrementals | New columns flow in |
| `+full_refresh: false` on persistent-staging/history layers | Accidental `--full-refresh` cannot wipe retained history |

See [snowflake-materializations.md](snowflake-materializations.md#tables-transience-and-grants).

Guide examples include these flags; keep only when compatible with project and dbt version:

- `require_explicit_package_overrides_for_builtin_materializations: true`
- `source_freshness_run_project_hooks: true`
- `send_anonymous_usage_stats: false`
- `partial_parse: true`

## Deprecations and Strict Validation

dbt 1.10 warns on project code later versions reject; 1.11 enables the JSON-schema deprecation warnings by default on Snowflake. Each new warning is required work, not log noise.

- **Find:** `dbt parse --no-partial-parse --show-all-deprecations`.
- **Fix:** `uvx dbt-autofix deprecations --dry-run` on a clean git branch → review diff → apply. `--include-packages` edits are reverted by the next `dbt deps` ⇒ upgrade the package instead (`dbt-autofix packages` checks package compatibility). Its `manual_fixes/` list covers what it cannot do: dynamic SQL, custom configuration read in macros, misspelled config keys, sources without tables, incompatible packages.
- **NEVER hide them as the fix.** `--warn-error-options '{"silence": ["Deprecations"]}'` or `flags: warn_error_options: silence:` is a temporary noise filter. CI with `--warn-error` ⇒ 1.10 promotes new deprecations to errors; scope with `"warn": ["Deprecations"]` while migrating. `warn_error_options` keys `include`/`exclude` are now `error`/`warn`.

| Invalid on dbt >= 1.10 | Valid form |
|---|---|
| Custom keys (`owner: x`) under a resource, `config`, or at YAML top level | `config: {meta: {owner: x}}`; read with `config.meta_get('owner')` (1.11, backported to 1.10), not `config.get('owner')` |
| Top-level `freshness`, `meta`, `tags`, `docs`, `group`, `access` properties | Same keys under `config:` |
| `materialized: table` without `+` in `dbt_project.yml` | `+materialized: table`; only folder and file names go unprefixed |
| Standalone top-level YAML anchors | Define under a top-level `anchors:` key |
| `-m` / `--model` / `--models` | `-s` / `--select` (silently ignored selection builds the whole DAG) |
| `dbt source freshness -o <path>` | `--target-path` for the whole step |
| `log-path` / `target-path` in `dbt_project.yml` (1.11) | `--log-path` / `--target-path` or `DBT_ENGINE_LOG_PATH` / `DBT_ENGINE_TARGET_PATH` |
| Source `overrides:` property | Enable or disable the package source instead |
| Duplicate YAML keys, orphan `{% endmacro %}` | Delete (dbt used the last duplicate silently) |

**`DBT_ENGINE_` prefix (1.11+).** Engine environment variables take the prefix (`DBT_STATE` → `DBT_ENGINE_STATE`); check CI scripts exporting engine-level `DBT_*` flags against the resolved version. Project-owned variables read via `env_var()` (`DBT_THREADS`, `DBT_ENV_SECRET_*`) are not engine flags; names unchanged.

**`require_generic_test_arguments_property`:**

| dbt | Default | Behavior |
|---|---|---|
| 1.10.8+ | `true` | Top-level test keyword arguments warn (`MissingArgumentsPropertyInGenericTestDeprecation`) |
| 1.10.5-1.10.7 | `false` | Nested form warns (`ArgumentsPropertyInGenericTestDeprecation`) unless flag set `true` in `dbt_project.yml` |

Custom generic test already having a parameter named `arguments` MUST rename it inside the macro, then pass it nested under `arguments:`.

## Verification

- Existing project: lockfile and `pyproject.toml` followed; `dbt --version` confirms engine; no bare `dbt` install in a v1 project.
- Secrets only via `DBT_ENV_SECRET_*` in `profiles.yml` and `packages.yml`.
- Baseline covered; schema mappings confirmed with the approved registry before folder config changes.
- Deprecation parse clean (`--show-all-deprecations`); warnings fixed, not silenced.

## Sources

External sources for the version-sensitive rules here (dbt 1.10-1.12, dbt-snowflake). Re-check when resolved versions differ:

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
