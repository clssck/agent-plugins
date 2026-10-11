# Running dbt from Airflow

Wiring a dbt project into a Sanofi MWAA DAG: choose the execution approach, pass run context, route failures, handle logs and backfills. Dominant orchestration use case. Scope: orchestration only; dbt project itself (model placement, SQL, materialization, YAML, tests) → dbt skill.

## Source of Truth

- **OneMesh pages:** `1. DAG Authoring Best Practices` `66486699835` (§ "Running dbt from Airflow"), `3. Performance & Troubleshooting` `66486175813`, `dbt Logs and Artifacts in MWAA` `65350434990` (logs/artifacts).
- **CIDF:** `Best practices - dbt and SQL in general` `66074739903` repeats the `BashOperator`/`DbtClient` and run-var patterns.
- **Package versions are environment facts, not choices.** Shared central MWAA ships `dbt-core` 1.11.x and `dbt-snowflake` 1.11.x; dedicated Airflow 3.2.1 tenants track slightly newer point releases. Confirm actual versions in the target environment before relying on a version-specific dbt feature.
- **Placeholders:** all project names, paths, roles, `dag_id`s below.
- **Cosmos:** `astronomer-cosmos` is pre-installed but **not used here**. Run dbt via `BashOperator` + `dbt_run.sh` or typed `DbtClient`. Revisit Cosmos only if per-model Airflow visibility becomes a hard requirement.

## Choosing an Approach

Both approaches are parse-time safe (no module-level `Variable.get()`/secrets/heavy imports) and scale to large projects. Both run dbt as a CLI invocation, so one task can cover many models. Choose by how the dbt command is built:

| Approach | When | Task visibility |
|---|---|---|
| `BashOperator` + `dbt_run.sh` | Most pipelines today; shared runner script | One task per dbt command |
| `@task.bash` + typed `DbtClient` | Refactoring toward typed, validated commands | One task per dbt command |

Per-owner alerting → split execution by selector (`tag:<team>`, `path:<domain>`) into separate tasks.

## BashOperator + dbt_run.sh

Shared `orchestration/scripts/dbt_run.sh` invoked via `BashOperator`: parse-time safe, stable at scale. **Keep the script small** — a `case` over run type plus a shared `$DBT_OPTS`. Resist deeply nested per-layer/per-exclude branches.

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

Replaces stringly-typed bash while staying on the dbt CLI. Typed, frozen `DbtClient` dataclass (via `sanofi-airflow-utils`) centralizes binary, project/profiles dirs, target, log paths; safely assembles `--select`, `--full-refresh`, `--vars`, extra args. Invoke inside `@task.bash` so command construction runs at execution time.

**Selection is explicit.** Pass it through the documented extra args. A run without one builds the whole project: allowed only when the user explicitly asked for it.

```python
@task.bash(env=snowflake_env_vars)
def run_models(**context) -> str:
    return dbt.build_command(
        "run",
        dbt_vars={"dag_run_id": context["dag_run"].run_id},
        extra_args="--select <selector>",
    )

@task.bash(env=snowflake_env_vars)
def run_tests() -> str:
    return dbt.build_command("test", extra_args="--select <selector> --exclude test_type:unit")
```

## Run Vars and Idempotent Windows

Pass Airflow run context into dbt → traceable, reprocessable runs. Common vars: `airflow_dag_id`, `airflow_dag_run_id`, `data_interval_start` / `data_interval_end`. Incremental models filter their source on the explicit window (instead of, or alongside, a `max()` watermark) → idempotent runs, replayable date ranges; see the dbt skill's incremental guidance.

- **NEVER build the `--vars` string at module level.** Build it inside a task or via `DbtClient`.
- **Airflow 3.x:** bare-cron schedules and asset-/API-triggered runs break window vars. Apply Airflow 3 Traps (SKILL.md) before passing the window to dbt.

## Execution Patterns

**Pick one per pipeline; never mix in one DAG.**

| Pattern | Shape | Use when |
|---|---|---|
| Single `dbt build` | One task per source/project: `dbt build --select tag:<x> --fail-fast`; dbt orders and tests models internally | Default; simplest |
| Per-layer `run` + `test` chain | One run+test task per layer, ordered staging → intermediate → warehouse → marts; intermediate test failures gate downstream layers | Test feedback needed between layers |

## Logs, Artifacts, and Failure Routing

Airflow task logs (UI + CloudWatch) are the default source of truth. dbt's own `dbt.log` and `target/` are ephemeral on MWAA workers unless the DAG persists them.

**Debug order:** DAG run → failed task instance → CloudWatch task log → dbt stdout/stderr in that log.

- **NEVER write dbt logs or artifacts into the S3 `dags/` prefix** (deployed code, not a runtime log archive).
- **NEVER point every project/run at one shared `dbt.log`.**
- **Persist artifacts only for a concrete need:** post-run analysis, audit evidence, model-level failure routing. Then: unique per-run path (`--log-path`/`--target-path`, or `DBT_LOG_PATH`/`DBT_TARGET_PATH`, keyed by dag/task/run id); upload only needed files (`run_results.json`, `manifest.json`) to an approved non-`dags` artifact bucket provisioned via IaC.
- **Route failures to owners without scraping logs:** split a bash run by selector (`tag:<team>`, `path:<domain>`) so a failure maps to a team. Parse `run_results.json` (per-node status, timing, message, node ids mapping to `manifest.json`) only when model-level routing cannot be expressed as separate tasks.

## Backfills

Prefer narrow date ranges over `--full-refresh` (slow; rebuilds every selected resource that allows it).

- **`full_refresh: false` beats the `--full-refresh` flag.** Protected persistent layers are NOT rebuilt by the flag; rebuilding one requires deliberately changing that config (dbt skill). NEVER assume the flag overrides it. `full_refresh: true` rebuilds even without the flag.
- **Backfill DAG pattern:** takes `{model/selector, start_date, end_date, run_tests}`, runs dbt over that window.
- **New incremental table:** one full refresh to seed, then incremental runs. Keep `--full-refresh` available for periodic rebuilds of unprotected models.
- **NEVER edit warehouse data directly** except as a documented emergency fix.

## Deprecated Patterns

Do not create `dbt_utils.py` / `common_util.py` helpers that call `Variable.get()`, import `snowflake.connector`/`cryptography` at module level, or use `sys.path.append` hacks → each fires secrets lookups and heavy imports on every parse cycle. Migrate such projects to a small `dbt_run.sh` or typed `DbtClient`.

## Verification

- Approach chosen: `BashOperator` + `dbt_run.sh` | `@task.bash` + `DbtClient`.
- No module-level `Variable.get()`, secrets, heavy imports.
- Run vars (`data_interval_start/end`, run id) passed for traceable, idempotent runs.
- One execution pattern (single `build` | per-layer `run`+`test`), not both.
- Logs/artifacts outside `dags/`; if persisted → approved artifact bucket, unique per-run path.
- `--select` expressions resolve (`dbt ls`); dbt project validated with the dbt skill (`dbt parse`/`compile`).
