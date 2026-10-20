# Snowflake-Native dbt Projects and Semantic Views

Capabilities that differ materially from ordinary dbt Core: Snowflake `DBT PROJECT` objects, `snow dbt` / `EXECUTE DBT PROJECT`, Snowflake Tasks scheduling, migration from an external dbt runtime, and semantic views via `dbt_semantic_view`. Governing principle: the surface changes quickly and an established runtime has owners → verify against current first-party docs, preserve the existing orchestrator, and stop before any destructive or architectural change.

Scope split: normal model SQL, project structure, tests, documentation, incremental logic, selectors, packages, CI, dbt Core commands → `general-dbt-guide.md`, `snowflake-materializations.md`, `state-and-ci.md`, `project-setup.md` (routed from SKILL.md). Load them in addition when a native-project request also changes ordinary dbt code.

## Sources and Currency

Before implementing, `read` the pages below that cover the command and verify syntax, supported dbt versions, commands, and flags:

- [Manage dbt Projects with Snowflake CLI](https://docs.snowflake.com/en/developer-guide/snowflake-cli/data-pipelines/dbt-projects)
- [`snow dbt` command reference](https://docs.snowflake.com/en/developer-guide/snowflake-cli/command-reference/dbt-commands/overview)
- [`EXECUTE DBT PROJECT`](https://docs.snowflake.com/en/sql-reference/sql/execute-dbt-project)
- [Supported dbt commands and flags](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-supported-commands)
- [Snowflake-Labs `dbt_semantic_view`](https://github.com/Snowflake-Labs/dbt_semantic_view)
- [`CREATE SEMANTIC VIEW`](https://docs.snowflake.com/en/sql-reference/sql/create-semantic-view)
- [Supported dbt versions for dbt Projects on Snowflake](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-dbt-core-versions)

NEVER rely on remembered preview-era syntax. Minimums at time of writing: native dbt project commands need Snowflake CLI >= 3.13; `env.yml`, `--env`, and related environment flags need >= 3.21. Recheck when acting.

## Intent and Architecture Check

Inspect the repository and Snowflake deployment model first; confirm which case applies:

1. Project already uses Snowflake `DBT PROJECT` objects.
2. User explicitly wants to evaluate or migrate to native execution.
3. Only a semantic-view model is needed in an otherwise ordinary dbt Core project.

**Existence of native execution is not a reason to migrate.** For established projects, preserve the documented orchestrator, authentication model, CI gates, deployment ownership, and rollback path unless the user explicitly authorizes an architecture change.

## Native Project Preflight

Before deploying or executing:

- Inspect `dbt_project.yml`, package configuration, project root, selectors, current runtime commands.
- `snow --version`; verify required features against current docs.
- Resolve database, schema, project-object name, role, warehouse, target, environment — no invented defaults.
- Project contains `dbt_project.yml` plus `dbt_projects_profiles.yml` or `profiles.yml`; both present → Snowflake prefers `dbt_projects_profiles.yml`.
- Credentials stay out of deployed profile files; inspect how the selected profile role determines execution privileges.
- Packages or private repositories needing an external access integration: identify them.
- Compare the requested dbt command and flags with the current supported-command matrix.
- Run the repository's normal parse, compile, lint, and test gates before deployment.

## Deploy and Execute

Use current Snowflake CLI syntax; NEVER translate ordinary dbt commands by guesswork. Representative shapes (shell-neutral; `snow` behaves the same on every OS; line continuation differs — POSIX `\`, PowerShell backtick — or put each command on one line):

```shell
snow dbt deploy <project_object> --source <project_directory> --database <database> --schema <schema>

snow dbt execute <project_object> build --select <selector>
snow dbt execute <project_object> test --select <selector>
snow dbt execute <project_object> show --select <model>
```

Add `--profiles-dir`, an external access integration, a default target, or an environment file only when the inspected project requires them. Verify option names against the installed CLI version.

**Environment variables.** `--env-vars` keys MUST be uppercase `DBT_*` names with string values; they appear in query text and query history → NEVER pass credentials that way; keep them in the `secrets:` block of `env.yml`. `--use-shell-env-vars` forwards exported `DBT_*` shell variables, excludes `DBT_ENV_SECRET_*`. `--env`, `--env-vars`, `--use-shell-env-vars` need Snowflake CLI >= 3.21 and are missing from `snow dbt execute --help` before 3.28.0.

**SQL-driven execution.** Use documented `EXECUTE DBT PROJECT` syntax; the dbt command and selector go inside `ARGS`:

```sql
EXECUTE DBT PROJECT <database>.<schema>.<project_object>
  ARGS = 'run --select <selector> --target <target>';
```

**Support differs per surface.** Example: `docs generate` may work through SQL or Workspaces yet be unsupported by `snow dbt execute`; check the live matrix.

**`snow dbt deploy --force` recreates the project object and removes existing versions and run history.** NEVER add `--force` as a routine retry; require explicit authorization after explaining that impact.

**After changing incremental logic**, decide how existing rows are repaired: full refresh is often appropriate, but a bounded backfill or other project-approved repair may be safer for a large or permission-constrained relation. Full refresh is not an unconditional rule; inspect the model and deployment constraints.

## Runtime Version

`DBT_VERSION` selects the native runtime, not the repository's lockfile. `1.x` → dbt Core (Python); `2.x` → Rust dbt v2 (Fusion) engine.

- **List, do not hard-code:** `SELECT SYSTEM$SUPPORTED_DBT_VERSIONS();` — at time of writing: Core 1.9.4, 1.10.15, 1.11.11, 1.12.3 and the 2.x line.
- **Pin explicitly:** `snow dbt deploy <project_object> --dbt-version '<version>'` · `snow dbt execute --dbt-version '<version>' <project_object> <command>` · `ALTER DBT PROJECT <project_object> SET DBT_VERSION = '<version>'`. The `DEFAULT_DBT_VERSION` account parameter applies only to projects created later without an explicit version → an unpinned project can run a different engine than repo CI.
- **Match the pin** to the dbt Core version the repository's CI resolves. NEVER move a dbt Core project to `2.x` without explicit authorization; that is an engine migration (see Migration to Native Execution).
- Snowflake keeps deprecated and end-of-life dbt Core versions running; a decommissioned version fails to execute until the pin is updated.

## Manage, Monitor, and Schedule

Use current `snow dbt list`, `describe`, `drop` or the documented Snowflake SQL object-management syntax. **Destructive:** drop, replace, rename, forced deploy, version removal, execution-history removal.

Inspect actual native execution results and artifacts; NEVER invent filesystem locations. Preserve query identifiers and invocation metadata needed for diagnosis.

Snowflake Tasks can run `EXECUTE DBT PROJECT`, including separate run and downstream test tasks. Adding or replacing scheduling is an orchestration decision: inspect existing Airflow, ECS, GitHub Actions, or other schedulers, define retry and alerting ownership, and require explicit authorization before creating or switching schedules.

## Migration to Native Execution

Design and rollout exercise, not command substitution. Produce a gap assessment covering:

- Supported dbt Core versions, commands, flags, packages, adapters, macros.
- Profile, role, warehouse, secret, environment-variable, external-access changes.
- CI validation, deployment/versioning, artifact retention, monitoring, rollback.
- Orchestration behavior, selectors, retries, alerts, concurrency, service ownership.
- Representative output parity and performance validation.

Keep the current runtime available until a representative native run passes the same project tests and accepted parity checks. NEVER alter production scheduling during an assessment.

## Semantic Views with dbt

Use `dbt_semantic_view` only when the user explicitly wants a Snowflake semantic view. Before adding the dependency: follow the project's package approval process, verify current release and dbt compatibility, pin an approved version.

**Engine compatibility.** dbt's Snowflake configuration page states the package requires dbt `>=1.0.0, <2.0.0` → targets dbt v1 (Core 1.x). The package's own `require-dbt-version` is `<2.0.0` in v1.0.0-v1.0.3 and `<3.0.0` from v1.0.4 (v1.0.6 latest tag checked), conflicting with that page. The bare `dbt` PyPI package and native `DBT_VERSION` `2.x` run dbt v2 → do not combine `dbt_semantic_view` with a `2.x` runtime until the project has proven `dbt deps` and a scoped `dbt build` of the semantic-view models on that exact version; otherwise keep those projects on dbt 1.x.

A semantic-view model = package materialization + Snowflake semantic-view SQL body:

```sql
{{ config(materialized='semantic_view') }}

TABLES (...)
RELATIONSHIPS (...)
FACTS (...)
DIMENSIONS (...)
METRICS (...)
```

Derive tables, relationships, facts, dimensions, metrics, grain, and access requirements from the real project and consumer questions. Use `ref()` and `source()` where supported; NEVER manufacture a semantic layer from column names alone.

Package behavior to recheck before implementation:

- `persist_docs` does not populate semantic-view documentation → inline `COMMENT` clauses when documentation must reach the Snowflake object.
- `copy_grants` applies to replacement behavior; `CREATE OR ALTER` preserves the object without `COPY GRANTS`.
- Managing semantic-view materializations through package configuration: prefer non-destructive `create_or_alter` and supply the required staleness settings; confirm current package semantics first.

**Validation:** scoped dbt parse/build plus focused Snowflake queries exercising representative dimensions, metrics, joins, filters, access roles. A view serving an application, analyst, or AI consumer → document as a dbt exposure.

## Stop Rules

Stop and obtain direction before:

- Migrating an established runtime or changing its scheduler.
- Forced deployment, drop, replace, rename, or version/history removal.
- Adding external network access or changing execution roles.
- Deploying a semantic contract whose grain, measures, relationships, or consumers are not established.
