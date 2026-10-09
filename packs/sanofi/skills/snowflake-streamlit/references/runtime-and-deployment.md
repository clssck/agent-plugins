# Streamlit in Snowflake runtime and deployment

Check current Snowflake documentation before changing runtime or deployment syntax. Fetch the pages in
[Sources](#sources) with `read`, and use `web_search` for release notes newer than this file.

## Runtime choice

| | Warehouse runtime | Container runtime |
|---|---|---|
| `RUNTIME_NAME` | `'SYSTEM$WAREHOUSE_RUNTIME'` | `'SYSTEM$ST_CONTAINER_RUNTIME_PY3_11'` plus `COMPUTE_POOL` (or the `DEFAULT_STREAMLIT_COMPUTE_POOL` account default) |
| App code runs on | `QUERY_WAREHOUSE` (the code warehouse; switch with `session.use_warehouse(...)` for heavy queries) | Compute pool node; `QUERY_WAREHOUSE` runs queries only |
| Python | 3.9, 3.10, 3.11 | 3.11 only |
| Streamlit | 1.22+, limited selection from the Snowflake Conda channel | 1.50+, any PyPI version including `streamlit-nightly` |
| Package manager | conda, Snowflake Anaconda channel only | uv, from an attached artifact repository or an EAI-reachable index |
| Dependency file | `environment.yml`; pin with `=`, ranges with `*` | `pyproject.toml` (recommended) or `requirements.txt`; pin with `==`, ranges with `<`, `<=`, `>=`, `>` |
| Entrypoint (`MAIN_FILE`) | Filename at the source root only | Root or subdirectory path |
| Streamlit server | One temporary server per viewer session | One persistent server shared by all viewers |
| Caching | Single session only | `st.cache_data`/`st.cache_resource` shared across all viewers unless `scope="session"` |
| Session | `get_active_session()` or `st.connection("snowflake").session()` | `st.connection("snowflake").session()` only; `get_active_session()` is not thread-safe and unavailable |
| Secrets in code | `_snowflake.get_generic_secret_string('<name>')` | `st.secrets["<name>"]` or `os.environ["<name>"]`; no `_snowflake` module |
| `IMPORTS`, `ROOT_LOCATION` | Supported (`ROOT_LOCATION` is legacy) | Rejected |
| Execution rights | Owner's rights, restricted like owner's-rights stored procedures | Owner's rights by default; restricted caller's rights (Preview) |
| Lifetime | Sleep timer (`[snowflake.sleep]` in `config.toml`) | Suspends after three days without viewers; subject to the SPCS maintenance window |
| Message size | 32 MB per Streamlit message (`MessageSizeError`) | 200 MB default, configurable |
| Components v2 | Not supported | Supported |
| Regions | All | Not in government or China regions |

A migration between the two is an architecture and deployment change, not a dependency-only edit.
When the user requests one, follow Snowflake's migration checklist: convert `ROOT_LOCATION` apps to
`FROM`; move to Streamlit 1.50+ and Python 3.11; grant the owner role `USAGE` on the compute pool
and on the artifact repository or EAI; replace `environment.yml` with `pyproject.toml` or
`requirements.txt` (Conda and PyPI package names can differ, e.g. `opencv` vs `opencv-python`);
replace `get_active_session()` and `_snowflake` calls; review imported code for shared global
state, since one server handles every viewer; then run
`ALTER STREAMLIT ... SET RUNTIME_NAME = ... COMPUTE_POOL = ...`.

## Runtime default changed in the 2026_06 bundle

Behavior change BCR-2342 (2026_06 bundle, enabled by default since release 10.32, September 2026)
makes `CREATE STREAMLIT` without `RUNTIME_NAME` create a **container-runtime** app. Previously the
default was the warehouse runtime. Existing apps are unaffected, but every new `CREATE STREAMLIT`,
including `CREATE OR REPLACE` in a redeploy script, follows the new default. Government regions,
China regions, and Native App Streamlits keep the warehouse default.

A warehouse-designed script that omits `RUNTIME_NAME` therefore either fails or silently changes
runtime: the container runtime ignores `environment.yml` and breaks wherever the app calls
`get_active_session()` or `_snowflake`.

| Error | Cause | Fix that keeps the warehouse runtime |
|---|---|---|
| `STREAMLIT_NO_IMPORTS_CONTAINER_RUNTIME` | `IMPORTS` present | Add `RUNTIME_NAME = 'SYSTEM$WAREHOUSE_RUNTIME'` |
| `STREAMLIT_NO_EXECUTION_MODE_CONTAINER_RUNTIME` | `EXECUTE AS` present | Same |
| `STREAMLIT_COMPUTE_POOL_NOT_SET` | No pool and no account default | Same |
| `STREAMLIT_VALIDATION_FAILURE_NO_USAGE_ON_COMPUTE_POOL` | Owner role lacks `USAGE` on the pool | Same |
| `STREAMLIT_COMPUTE_POOL_NO_AUTO_RESUME` | Pool has `AUTO_RESUME = FALSE` | Same |
| `INVALID_PROPERTY` for `RUNTIME_NAME`/`COMPUTE_POOL` | SPCS not enabled on the account | Same |

## Warehouse source layout

The entrypoint and `environment.yml` belong at the root of the staged source directory. Imported
modules must also be within the deployed source tree. Pin a Snowflake-supported Streamlit version;
warehouse dependencies must be available from the Snowflake Anaconda channel and cannot be declared
as pip entries inside `environment.yml`. uv cannot install `environment.yml`; for a local
warehouse-runtime environment Snowflake documents conda with the channels
`https://repo.anaconda.com/pkgs/snowflake` and `nodefaults`.

Example source-version deployment:

```sql
create or replace streamlit DATABASE.SCHEMA.APP_NAME
  from '@DATABASE.SCHEMA.APP_STAGE/app_name'
  main_file = 'APP.py'
  query_warehouse = APP_WH
  runtime_name = 'SYSTEM$WAREHOUSE_RUNTIME';

alter streamlit DATABASE.SCHEMA.APP_NAME add live version from last;
```

- Write new `FROM` paths as quoted string literals (`FROM '@DB.SCH.STAGE/app'`); this is the house
  convention. Snowflake's `CREATE STREAMLIT` examples also show unquoted `FROM @stage`, so NEVER
  treat an existing unquoted repo statement as a bug that needs rewriting on its own.
- A new app is not live until `ALTER STREAMLIT ... ADD LIVE VERSION FROM LAST` runs, or until the
  owning role opens it in Snowsight.
- `CREATE STREAMLIT` copies the source files once. Later changes to the staged files do not update
  the app.
- `CREATE OR REPLACE` drops and recreates the object, so re-apply viewer grants afterwards.
  Snowflake CLI 3.21.0+ switched `--replace` to `ALTER STREAMLIT ... SET` specifically to preserve
  grants.
- Cloning a database or schema does not clone its Streamlit objects. Environment promotion MUST
  deploy each app explicitly.
- Treat `ROOT_LOCATION` as legacy. It is warehouse-only and lacks multi-file editing and Git
  integration.

## Container dependency files

Snowflake installs container-runtime dependencies with uv. It searches the entrypoint's directory,
then each parent up to the source root, and uses the first dependency file it finds. In one
directory, `requirements.txt` takes precedence over `pyproject.toml`, so a stray `requirements.txt`
silently bypasses `uv.lock`. A private or alternative index requires `pyproject.toml`.

```toml
[project]
name = "app-name"            # name and version are required but arbitrary
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "streamlit[snowflake]==1.50.0",
    "pandas>=2.0.0,<3.0.0",
]
```

Without a package source the app can only use the base image's packages. Any extra package, or any
version specifier on a pre-installed package, needs one of:

- **Artifact repository (recommended):** the owner role needs `SNOWFLAKE.PYPI_REPOSITORY_USER` for
  the built-in PyPI mirror, or `USAGE` on a customer-hosted repository. Attach it with
  `ALTER STREAMLIT ... SET ARTIFACT_REPOSITORIES = (snowflake.snowpark.pypi_shared_repository)`.
  Attaching or removing a repository restarts the app.
- **EAI fallback:** only when an artifact repository cannot be used, for example an EAI built on the
  managed rule `SNOWFLAKE.EXTERNAL_ACCESS.PYPI_RULE`. An attached artifact repository overrides EAIs
  for package installs.

## Sessions

`st.connection("snowflake").session()` works in both runtimes and locally, and is the only option on
a container runtime. `get_active_session()` works only in a deployed warehouse app. Keep any local
fallback explicit, so that a failed deployed session does not silently connect to a different
account, role, database, or schema.

## Secrets and external access

The setup is the same for both runtimes. Create the secret, then an EAI whose
`ALLOWED_AUTHENTICATION_SECRETS` lists it. Add `ALLOWED_NETWORK_RULES` for egress hosts. Then attach
both to the app. A secret cannot be attached without an EAI.

```sql
alter streamlit DATABASE.SCHEMA.APP_NAME
  set external_access_integrations = (APP_EAI)
  secrets = ('api_key' = DATABASE.SCHEMA.API_KEY_SECRET);
```

| Runtime | Read in code | Notes |
|---|---|---|
| Warehouse | `_snowflake.get_generic_secret_string('api_key')` | Owner role needs `USAGE` on the secret and the EAI |
| Container | `st.secrets["api_key"]`, `os.environ["api_key"]` | Generic string and basic-auth secrets only. Basic auth is exposed as `["username"]`/`["password"]` and `<name>_USERNAME`/`<name>_PASSWORD` |

- On a container runtime, a staged `.streamlit/secrets.toml` is merged with Snowflake secrets and
  **takes precedence** over them. It is plaintext on the stage. NEVER stage real secrets in it, and
  check that a leftover file is not shadowing a rotated Snowflake secret.
- Warehouse runtimes do not support `secrets.toml`.
- For a private index such as JFrog that cannot be a customer-hosted artifact repository, declare
  it in `[[tool.uv.index]]` and map a basic-auth secret to `UV_INDEX_<NAME>` (index name uppercased,
  non-alphanumerics as `_`) so the runtime injects uv's `UV_INDEX_<NAME>_USERNAME`/`_PASSWORD`. The
  network rule may also need the repository's cloud storage host.
- To call Cortex REST APIs from a container runtime, read the token from `/snowflake/session/token`.
  It replaces `_snowflake.send_snow_api_request()`.
- `config.toml`: warehouse runtimes honor only `[theme]`, `[theme.sidebar]`, and
  `[snowflake.sleep]`. Container runtimes also honor `[runner]` and a few `[client]`/`[global]`
  keys. Neither runtime honors `[server]` or `[browser]`.

## Snowflake CLI deployment

Install the CLI as an isolated uv tool, never with `pip` into a system or Homebrew Python:
`uv tool install snowflake-cli` (upgrade with `uv tool upgrade snowflake-cli`; one-off runs use
`uvx --from snowflake-cli snow ...`). Check it with `snow --version`.

`snow streamlit deploy` reads a `definition_version: 2` `snowflake.yml`. It uploads the artifacts to
`stage` (default `streamlit`, created if missing), then runs `CREATE STREAMLIT ... FROM` or, on
`--replace`, `ALTER STREAMLIT`. Pin `runtime_name` the same way as in SQL:

```yaml
definition_version: 2
entities:
  app_name:
    type: streamlit
    identifier:
      name: APP_NAME
      database: DATABASE
      schema: SCHEMA
    stage: APP_STAGE
    query_warehouse: APP_WH
    runtime_name: SYSTEM$WAREHOUSE_RUNTIME   # or SYSTEM$ST_CONTAINER_RUNTIME_PY3_11 + compute_pool
    main_file: APP.py
    artifacts:
      - APP.py
      - environment.yml   # container runtime: pyproject.toml and uv.lock instead
      - app_lib/
    grants:
      - privilege: USAGE
        role: APP_VIEWER_ROLE
```

Deploy with `snow streamlit deploy app_name --replace --connection <name>`.

| Behavior | What to do |
|---|---|
| CLI before 3.27.0 dropped `runtime_name: SYSTEM$WAREHOUSE_RUNTIME` from the DDL, so under BCR-2342 the app landed on the container runtime | Require CLI 3.27.0+ wherever `snowflake.yml` names a runtime |
| CLI 3.27.0+ applies `runtime_name` to existing apps: a mismatch issues `ALTER STREAMLIT ... SET RUNTIME_NAME` and moves the app | NEVER change `runtime_name`, or upgrade the CLI in CI, without checking every entity's runtime against the deployed app (`DESCRIBE STREAMLIT`) |
| `compute_pool` without `runtime_name` implies the container runtime; an empty `runtime_name` or `compute_pool` is an error; unknown runtime names are rejected | Omit unused keys entirely |
| `--replace` uploads and overwrites but never deletes staged files | Add `--prune` when files were removed or renamed |
| `--legacy` deploys with `ROOT_LOCATION` and cannot carry `runtime_name` | Use only for apps that already rely on the legacy contract |
| Omitting `tags:` leaves existing tags alone; `tags: []` clears them (3.22.1+) | Do not add `tags: []` by accident |
| `grants:` entries take exactly one of `role:` or `user:` (`user:` 3.28.0+); `sharing:` (3.28.0+) is the older alias for `USAGE` grants | Keep one spelling per repo |

- Validate the file in CI (3.20.0+):
  `snow helpers generate-project-schema -o snowflake-schema.json`, then
  `uvx check-jsonschema --schemafile snowflake-schema.json snowflake.yml`. The schema checks
  structure only; cross-field rules still fail at deploy time.
- Stream container-runtime logs with `snow streamlit logs` (3.18.0+).
- Since 3.27.0, a container-runtime `--replace` restarts the service, so content-only updates appear
  without a Snowsight restart.

## Security and platform behavior

Owner-rights execution means queries use the app owner's privileges, not the viewer's. Use a
dedicated owner role, and verify viewer-sensitive behavior against current Snowflake guidance.

Restricted caller's rights (Preview) work on container runtimes only and need Streamlit 1.53.1+:

- Use `st.connection("snowflake-callers-rights")` for viewer-scoped queries and
  `st.connection("snowflake")` for owner-scoped ones.
- An admin with `MANAGE CALLER GRANTS` must issue `GRANT CALLER ...` to the owner role.
- Create the connection at the top of the script, not behind branches or pages. Its token is valid
  for only two minutes after the session starts.
- The connection uses the viewer's **default** role, not the role selected in Snowsight.
- Cache its results only with `scope="session"`.
- It errors locally and on warehouse runtimes.

The Content Security Policy blocks scripts and styles from external domains, iframes of external
content, and `eval()`. Images, media, and fonts load from any HTTPS domain. Other platform
differences:

- `st.query_params` keys appear in the URL with a `streamlit-` prefix.
- The `page_title`, `page_icon`, and `menu_items` options of `st.set_page_config` are ignored.
- External stages, replication, and `.so` files are unsupported.

## Deployment contract tests

When deployment stages files individually, add a test that compares imported local modules with the
deployment manifest, the SQL list, or the `snowflake.yml` artifacts. Also verify that:

- the dependency file matching the runtime is staged, with `uv.lock` beside `pyproject.toml`;
- no `requirements.txt` shadows a `pyproject.toml` in the same directory;
- the entrypoint name matches `MAIN_FILE`;
- every `CREATE STREAMLIT` and every `snowflake.yml` streamlit entity names its runtime explicitly;
- the target role is least privilege;
- deployment targets the intended environment.

Local rendering cannot replace the final native smoke test for these properties.

## Sources

- [Runtime environments for Streamlit apps](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/runtime-environments)
- [CREATE STREAMLIT](https://docs.snowflake.com/en/sql-reference/sql/create-streamlit)
- [ALTER STREAMLIT](https://docs.snowflake.com/en/sql-reference/sql/alter-streamlit)
- [DESCRIBE STREAMLIT](https://docs.snowflake.com/en/sql-reference/sql/desc-streamlit)
- [BCR-2342: New Streamlits default to container runtime](https://docs.snowflake.com/en/release-notes/bcr-bundles/2026_06/bcr-2342)
- [2026_06 bundle status](https://docs.snowflake.com/en/release-notes/bcr-bundles/2026_06_bundle)
- [Migrating between runtime environments](https://docs.snowflake.com/en/developer-guide/streamlit/migrations-and-upgrades/runtime-migration)
- [Manage secrets and configure your Streamlit app](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/secrets-and-configuration)
- [Restricted caller's rights and Streamlit in Snowflake](https://docs.snowflake.com/en/developer-guide/streamlit/features/restricted-callers-rights)
- [Limitations and library changes](https://docs.snowflake.com/en/developer-guide/streamlit/limitations)
- [File organization](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/file-organization)
- [Dependency management](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/dependency-management)
- [Security overview](https://docs.snowflake.com/en/developer-guide/streamlit/object-management/security)
- [Installing Snowflake CLI](https://docs.snowflake.com/en/developer-guide/snowflake-cli/installation/installation)
- [Snowflake CLI: Creating a Streamlit app (snowflake.yml properties)](https://docs.snowflake.com/en/developer-guide/snowflake-cli/streamlit-apps/manage-apps/initialize-app)
- [Snowflake CLI: Deploying a Streamlit app](https://docs.snowflake.com/en/developer-guide/snowflake-cli/streamlit-apps/manage-apps/deploy-app)
- [snow streamlit deploy reference](https://docs.snowflake.com/en/developer-guide/snowflake-cli/command-reference/streamlit-commands/deploy)
- [Snowflake CLI release notes (GitHub)](https://github.com/snowflakedb/snowflake-cli/blob/main/RELEASE-NOTES.md)
- [Snowflake CLI streamlit entity model (GitHub)](https://github.com/snowflakedb/snowflake-cli/blob/main/src/snowflake/cli/_plugins/streamlit/streamlit_entity_model.py)
- [uv package indexes and credentials](https://docs.astral.sh/uv/concepts/indexes/)
