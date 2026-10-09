# Snowflake-Native dbt Projects and Semantic Views

Use this reference only for capabilities that differ materially from ordinary dbt Core:

- deploying and operating a dbt project as a Snowflake `DBT PROJECT` object;
- executing that object with `snow dbt` or `EXECUTE DBT PROJECT`;
- scheduling native project execution with Snowflake Tasks;
- migrating an existing external dbt runtime to Snowflake-native execution; or
- authoring Snowflake semantic views through the `dbt_semantic_view` package.

For normal model SQL, project structure, tests, documentation, incremental logic,
selectors, packages, CI, or dbt Core commands, use `general-dbt-guide.md` instead. Add
that guide when a native-project request also changes ordinary dbt code.

## Sources and Currency

This surface changes quickly. Before implementing, verify command syntax, supported dbt
versions, commands, and flags against current first-party sources:

- [Manage dbt Projects with Snowflake CLI](https://docs.snowflake.com/en/developer-guide/snowflake-cli/data-pipelines/dbt-projects)
- [`snow dbt` command reference](https://docs.snowflake.com/en/developer-guide/snowflake-cli/command-reference/dbt-commands/overview)
- [`EXECUTE DBT PROJECT`](https://docs.snowflake.com/en/sql-reference/sql/execute-dbt-project)
- [Supported dbt commands and flags](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-supported-commands)
- [Snowflake-Labs `dbt_semantic_view`](https://github.com/Snowflake-Labs/dbt_semantic_view)
- [`CREATE SEMANTIC VIEW`](https://docs.snowflake.com/en/sql-reference/sql/create-semantic-view)
- [Supported dbt versions for dbt Projects on Snowflake](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-dbt-core-versions)

Do not rely on remembered preview-era syntax. At the time this reference was written,
native dbt project commands require Snowflake CLI 3.13 or later; `env.yml`, `--env`, and
related environment flags require 3.21 or later. Recheck these minimums when acting.

## Intent and Architecture Check

Inspect the repository and Snowflake deployment model first. Confirm which situation
actually applies:

1. The project already uses Snowflake `DBT PROJECT` objects.
2. The user explicitly wants to evaluate or migrate to native execution.
3. Only a semantic-view model is needed in an otherwise ordinary dbt Core project.

Do not propose or perform a runtime migration simply because native execution exists.
For established projects, preserve the documented orchestrator, authentication model,
CI gates, deployment ownership, and rollback path unless the user explicitly authorizes
an architecture change.

## Native Project Preflight

Before deploying or executing:

- inspect `dbt_project.yml`, package configuration, project root, selectors, and current
  runtime commands;
- run `snow --version` and verify required features against current documentation;
- resolve the intended database, schema, project-object name, role, warehouse, target,
  and environment without inventing defaults;
- confirm the project contains `dbt_project.yml` and an appropriate
  `dbt_projects_profiles.yml` or `profiles.yml`; when both exist, Snowflake prefers
  `dbt_projects_profiles.yml`;
- keep credentials out of deployed profile files and inspect how the selected profile
  role determines execution privileges;
- identify packages or private repositories that need an external access integration;
- compare the requested dbt command and flags with the current supported-command matrix.

Use the repository's normal parse, compile, lint, and test gates before deployment.

## Deploy and Execute

Use the current Snowflake CLI syntax rather than translating ordinary dbt commands by
guesswork. Representative shapes are (shell-neutral; `snow` behaves the same on every
OS). Line continuation differs: POSIX shells use `\`, PowerShell uses a backtick; or put
each command on one line.

```shell
snow dbt deploy <project_object> --source <project_directory> --database <database> --schema <schema>

snow dbt execute <project_object> build
snow dbt execute <project_object> test --select <selector>
snow dbt execute <project_object> show --select <model>
```

Add `--profiles-dir`, an external access integration, a default target, or an environment
file only when the inspected project requires them. Verify option names against the
installed CLI version.

Environment variables: `--env-vars` keys MUST be uppercase `DBT_*` names with string
values, and they appear in query text and query history, so NEVER pass credentials that
way; keep them in the `secrets:` block of `env.yml`. `--use-shell-env-vars` forwards
exported `DBT_*` shell variables but excludes `DBT_ENV_SECRET_*`. `--env`, `--env-vars`,
and `--use-shell-env-vars` need Snowflake CLI 3.21 or later and are missing from
`snow dbt execute --help` before 3.28.0.

For SQL-driven execution, use the documented `EXECUTE DBT PROJECT` syntax and keep the
dbt command and selector inside `ARGS`, for example:

```sql
EXECUTE DBT PROJECT <database>.<schema>.<project_object>
  ARGS = 'run --select <selector> --target <target>';
```

Do not assume every command is supported by every execution surface. For example,
`docs generate` may be supported through SQL or Workspaces while remaining unsupported
by `snow dbt execute`; check the live matrix.

`snow dbt deploy --force` recreates the project object and removes existing versions and
run history. Never add `--force` as a routine retry. Require explicit authorization after
explaining that impact.

After changing incremental logic, determine how existing rows will be repaired. A full
refresh is often appropriate, but a bounded backfill or another project-approved repair
may be safer for a large or permission-constrained relation. Do not make full refresh an
unconditional rule without inspecting the model and deployment constraints.

## Runtime Version

The native runtime is selected by `DBT_VERSION`, not by the repository's lockfile. A `1.x`
value runs dbt Core (Python); a `2.x` value runs the Rust dbt v2 (Fusion) engine.

- List what the account supports with `SELECT SYSTEM$SUPPORTED_DBT_VERSIONS();` instead
  of hard-coding versions; at the time of writing it returned Core 1.9.4, 1.10.15,
  1.11.11, 1.12.3 and the 2.x line.
- Pin explicitly: `snow dbt deploy <project_object> --dbt-version '<version>'`,
  `snow dbt execute --dbt-version '<version>' <project_object> <command>`, or
  `ALTER DBT PROJECT <project_object> SET DBT_VERSION = '<version>'`. The
  `DEFAULT_DBT_VERSION` account parameter only applies to projects created later without
  an explicit version, so an unpinned project can run a different engine than repo CI.
- Match the pin to the dbt Core version the repository's CI resolves. NEVER move a dbt
  Core project to a `2.x` version without explicit authorization; that is an engine
  migration (see Migration to Native Execution).
- Snowflake keeps deprecated and end-of-life dbt Core versions running, but a
  decommissioned version fails to execute until the pin is updated.

## Manage, Monitor, and Schedule

Use current `snow dbt list`, `describe`, and `drop` commands or the documented Snowflake
SQL object-management syntax. Treat drop, replace, rename, forced deploy, version removal,
and execution-history removal as destructive operations.

Inspect actual native execution results and artifacts rather than inventing filesystem
locations. Preserve query identifiers and invocation metadata needed for diagnosis.

Snowflake Tasks can run `EXECUTE DBT PROJECT`, including separate run and downstream test
tasks. Adding or replacing scheduling is an orchestration decision: inspect existing
Airflow, ECS, GitHub Actions, or other schedulers, define retry and alerting ownership,
and require explicit authorization before creating or switching schedules.

## Migration to Native Execution

Treat migration as a design and rollout exercise, not a command substitution. Produce a
gap assessment covering:

- supported dbt Core versions, commands, flags, packages, adapters, and macros;
- profile, role, warehouse, secret, environment-variable, and external-access changes;
- CI validation, deployment/versioning, artifact retention, monitoring, and rollback;
- orchestration behavior, selectors, retries, alerts, concurrency, and service ownership;
- representative output parity and performance validation.

Keep the current runtime available until a representative native run passes the same
project tests and accepted parity checks. Do not alter production scheduling during an
assessment.

## Semantic Views with dbt

Use `dbt_semantic_view` only when the user explicitly wants a Snowflake semantic view.
Before adding the dependency, follow the project's package approval process, verify the
current release and dbt compatibility, and pin an approved version.

A semantic-view model uses the package materialization plus Snowflake's semantic-view SQL
body:

```sql
{{ config(materialized='semantic_view') }}

TABLES (...)
RELATIONSHIPS (...)
FACTS (...)
DIMENSIONS (...)
METRICS (...)
```

Derive tables, relationships, facts, dimensions, metrics, grain, and access requirements
from the real project and consumer questions. Use `ref()` and `source()` where supported;
do not manufacture a semantic layer from column names alone.

Important current package behavior to recheck before implementation:

- `persist_docs` does not populate semantic-view documentation; use supported inline
  `COMMENT` clauses when documentation must be applied to the Snowflake object.
- `copy_grants` applies to replacement behavior, while `CREATE OR ALTER` preserves the
  object without using `COPY GRANTS`.
- when managing semantic-view materializations through package configuration, prefer
  non-destructive `create_or_alter` behavior and supply the required staleness settings;
  confirm current package semantics first.

Validate semantic views with a scoped dbt parse/build and focused Snowflake queries that
exercise representative dimensions, metrics, joins, filters, and access roles. If the
view serves an application, analyst, or AI consumer, document it as a dbt exposure.

## Stopping Conditions

Stop and obtain direction before:

- migrating an established runtime or changing its scheduler;
- forced deployment, drop, replace, rename, or version/history removal;
- adding external network access or changing execution roles;
- deploying a semantic contract whose grain, measures, relationships, or consumers are
  not established.
