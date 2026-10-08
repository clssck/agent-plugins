# Running dbt from Airflow

How to run a dbt project from a Sanofi MWAA DAG. This is the dominant orchestration use
case. Use this reference to pick and wire the execution approach; use the dbt skill
for the dbt project itself (model placement, SQL, materialization, YAML, tests).

## Source of Truth

Primary reference is OneMesh `1. DAG Authoring Best Practices` `66486699835` (§ "Running
dbt from Airflow"), `3. Performance & Troubleshooting` `66486175813`, and `dbt Logs and
Artifacts in MWAA` `65350434990` (logs/artifacts handling). The `BashOperator`/`DbtClient`
and run-var patterns also appear in CIDF `Best practices - dbt and SQL in general`
`66074739903`.

Platform package versions are environment facts, not choices: shared central MWAA ships
`dbt-core` (1.11.x) and `dbt-snowflake` (1.11.x); dedicated Airflow 3.2.1 tenants track
slightly newer point releases. Confirm the actual versions in the target environment
before relying on a version-specific dbt feature. All project names, paths, roles, and
`dag_id`s below are placeholders.

> Cosmos (`astronomer-cosmos`) is pre-installed on the platform but is **not used here** —
> run dbt via `BashOperator` + `dbt_run.sh` or the typed `DbtClient`. Revisit Cosmos only
> if per-model Airflow visibility ever becomes a hard requirement.

## Choosing an Approach

Both approaches are parse-time safe (no module-level `Variable.get()`/secrets/heavy
imports) and scale to large projects. Choose by how you want to build the dbt command:

| Approach                         | When                                         | Task visibility          |
| -------------------------------- | -------------------------------------------- | ------------------------ |
| `BashOperator` + `dbt_run.sh`    | Most pipelines today; a shared runner script | One task per dbt command |
| `@task.bash` + typed `DbtClient` | Refactoring toward typed, validated commands | One task per dbt command |

Both run dbt as a CLI invocation, so a single task can cover many models. For per-owner
alerting, split execution by selector (`tag:<team>`, `path:<domain>`) into separate tasks.

## BashOperator + dbt_run.sh

The most common pattern: a shared `orchestration/scripts/dbt_run.sh` invoked via
`BashOperator`. It is parse-time safe and stable at scale. Keep the script small (a `case`
over run type plus a shared `$DBT_OPTS`); resist letting it grow into deeply nested
per-layer/per-exclude branches.

```python
from airflow.operators.bash import BashOperator  # 3.x: airflow.providers.standard.operators.bash

run_dbt = BashOperator(
    task_id="run_dbt_models",
    bash_command=("/usr/local/airflow/dags/<project>/orchestration/scripts/"
                  "dbt_run.sh run False 'stg.*,tag:daily'"),
    env={"SNOWFLAKE_ENV": ENV, **snowflake_env_vars},
)
```

## Typed DbtClient

To move away from stringly-typed bash while staying on the dbt CLI, build dbt commands
with a typed, frozen `DbtClient` dataclass (available via `sanofi-airflow-utils`). It
centralizes the binary, project/profiles dirs, target, and log paths, and safely assembles
`--select`, `--full-refresh`, `--vars`, and extra args. Invoke it inside `@task.bash` so
command construction runs at execution time:

```python
@task.bash(env=snowflake_env_vars)
def run_models(**context) -> str:
    return dbt.build_command("run", dbt_vars={"dag_run_id": context["dag_run"].run_id})

@task.bash(env=snowflake_env_vars)
def run_tests() -> str:
    return dbt.build_command("test", extra_args="--exclude test_type:unit")
```

## Passing Run Vars and Idempotent Windows

Pass Airflow run context into dbt so runs are traceable and reprocessable. Common vars:
`airflow_dag_id`, `airflow_dag_run_id`, and the interval boundaries
`data_interval_start` / `data_interval_end`. Incremental models can filter their source
on that explicit window (instead of, or alongside, a `max()` watermark) to make each run
idempotent and any date range replayable — see the dbt skill's incremental guidance.
Build the `--vars` string inside a task or via `DbtClient`, never at module level.

On Airflow 3.x a bare cron/preset `schedule` uses `CronTriggerTimetable`, so
`data_interval_start == data_interval_end`, and asset-/API-triggered runs have no data
interval at all (`logical_date=None`). Either schedule with `CronDataIntervalTimetable`
or compute the window explicitly, and fall back when the keys are absent, before
passing them as dbt vars (see Airflow 3 Migration in the general guide).

## Execution Patterns

Pick one pattern per pipeline and stay consistent; do not mix them in one DAG:

1. Single `dbt build` per source/project: one task runs `dbt build --select tag:<x>
   --fail-fast`. Simplest; dbt orders and tests models internally.
2. Per-layer `run` + `test` chained: one run+test task per layer, ordered
   staging -> intermediate -> warehouse -> marts, so intermediate test failures gate
   downstream layers. Use when you want test feedback between layers.

## Logs, Artifacts, and Failure Routing

Airflow task logs (Airflow UI plus CloudWatch) are the default source of truth for
debugging a dbt run; dbt's own `dbt.log` and `target/` artifacts are ephemeral on MWAA
workers unless the DAG persists them. Debug in this order: open the DAG run, open the
failed task instance, read its CloudWatch task log, then read the dbt stdout/stderr in
that task's log.

Never write dbt logs or artifacts into the S3 `dags/` prefix, and never point every
project/run at one shared `dbt.log` — the `dags/` prefix is deployed code, not a runtime
log archive. Persist artifacts only when there is a concrete need (post-run analysis,
audit evidence, model-level failure routing). When you do, write to a unique per-run path
(`--log-path`/`--target-path`, or `DBT_LOG_PATH`/`DBT_TARGET_PATH`, keyed by dag/task/run
id) and upload only the files you need (`run_results.json`, `manifest.json`) to an
approved non-`dags` artifact bucket provisioned via IaC.

Route failures to owners without scraping logs: split a bash run by selector
(`tag:<team>`, `path:<domain>`) so a failure maps to a team. Parse `run_results.json`
(per-node status, timing, message, and node ids that map back to `manifest.json`) only
when model-level routing cannot be expressed as separate tasks.

## Backfills

Prefer narrow date ranges over `--full-refresh` (full refreshes are slow and rebuild
every selected resource that allows it). A resource config `full_refresh: false` takes
precedence over the `--full-refresh` flag, so protected persistent layers are NOT
rebuilt by the flag; a rebuild of such a model requires deliberately changing that config
(see the dbt skill) — NEVER assume the flag overrides it. `full_refresh: true` rebuilds
even without the flag, and snapshots ignore both. A common pattern is a dedicated
backfill DAG that takes `{model/selector, start_date, end_date, run_tests}` and runs dbt
over that window. Seed a new incremental table with one full refresh, then run
incrementally; keep `--full-refresh` available for periodic rebuilds of unprotected
models. Never edit warehouse data directly except as a documented emergency fix.

## Deprecated Patterns

Do not create `dbt_utils.py` / `common_util.py` helper modules that call `Variable.get()`
or import `snowflake.connector`/`cryptography` at module level, or use `sys.path.append`
hacks — they fire secrets lookups and heavy imports on every parse cycle. Migrate such
projects to a small `dbt_run.sh` or the typed `DbtClient`.

## Checklist

- [ ] Approach chosen (`BashOperator` + `dbt_run.sh` or `@task.bash` + `DbtClient`).
- [ ] No module-level `Variable.get()`, secrets, or heavy imports.
- [ ] Run vars (`data_interval_start/end`, run id) passed for traceable/idempotent runs.
- [ ] One execution pattern (single `build` vs per-layer `run`+`test`), not both.
- [ ] Logs/artifacts stay out of the `dags/` prefix; if persisted, they go to an approved
      artifact bucket under a unique per-run path.
- [ ] `--select` expressions resolve (`dbt ls`) and the dbt project is validated with the
      dbt skill (`dbt parse`/`compile`).
