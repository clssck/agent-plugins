---
name: sanofi-airflow
description: Sanofi MWAA Airflow conventions - parse-time safety, sanofi-airflow-utils config/secrets, failure alerts, access roles, CI/S3 sync, Airflow 3 migration, dbt via dbt_run.sh/DbtClient. Use when creating, reviewing, deploying, or troubleshooting DAGs in a Sanofi orchestration repo. Not for generic Airflow (coco-airflow), dbt models/SQL (dbt), or generic CI/CD (cicd-engineering).
---

# Sanofi Airflow

Sanofi conventions for DAGs on AWS MWAA: shared central environment and dedicated tenants. Platform facts only; generic review stays with omp `/review`. Run it on the diff, then apply this skill for Sanofi-specific defects.

## Core Rules

- **MUST inspect the real repo first.** Derive `dags/` layout, `dag_id`/`task_id` convention, `default_args`, config/secrets loader, tags, roles, Airflow major version (2.11 vs 3.x), dbt-run mechanism from files.
- **Examples are patterns.** NEVER copy example names, roles, paths, or versions verbatim.
- **Parse-time safety is review item one.** Shared MWAA scheduler imports every `.py` under `dags/` every 30-60s; one bad DAG degrades every tenant.
- **Module-level `Variable.get()`, `get_secret()`, heavy import, DB connection, API call = blocking defect.** Even if the DAG "works". Move into the task body or Jinja (`{{ var.value.KEY }}`).
- **Version-sensitive syntax follows configuration, not version.** Check `dag_ignore_file_syntax` (`regexp` or `glob`; default `glob` in Airflow 3, `regexp` before).
- **Imports follow the target major version.** 2.11: `airflow.decorators`, `airflow.operators.bash`, `Dataset`. 3.x: `airflow.sdk` (`dag`, `task`, `Asset`, `Variable`) and `airflow.providers.standard.operators.bash`. `airflow.sdk` is not part of 2.11; legacy paths only warn on 3.x and are slated for removal.
- **Airflow 3 changes run semantics, not just imports.** Check every DAG headed to a 3.x tenant against [Airflow 3 Traps](#airflow-3-traps).
- **NEVER deploy to shared MWAA to test a DAG.** Prove changes locally or in CI.
- **Prefer the repo's README, Makefile, CI, or scripts** for verification; otherwise use the ladder below.

## Routing

| Task | `read` |
|---|---|
| Platform model, repo layout, naming, DAG config, TaskFlow, config/secrets, Datasets/Assets, sensors, alerting, access control, CI/CD, troubleshooting, Airflow 3 migration | [general-airflow-guide.md](references/general-airflow-guide.md) |
| Running dbt from a DAG: `BashOperator` + `dbt_run.sh` or typed `DbtClient`, logs/artifacts, backfills, run vars | [orchestrating-dbt.md](references/orchestrating-dbt.md) |

- dbt models, SQL, YAML, tests → use the dbt skill.
- Multi-area change order: parse safety + DAG config → task logic → orchestration wiring → alerting/access/tags → deploy and run commands.
- Read only the reference the task needs.

## Local Environment

MWAA installs `requirements.txt` with `pip3` plus an Airflow constraints file. Mirror it locally with uv; NEVER `pip install` into system or Homebrew Python.

```bash
uv venv --python 3.12   # MWAA 2.11 and 3.x run Python 3.12
uv pip install "apache-airflow==<version>" -r requirements.txt \
  -c "https://raw.githubusercontent.com/apache/airflow/constraints-<version>/constraints-3.12.txt"
uv run --no-project airflow dags list-import-errors
```

- Repo already on poetry, pip-tools, or `uv.lock`: keep its tooling (`uv run` for uv projects). Recommend uv only for new work.
- Run one-off CLIs without installing: `uvx ruff@latest ...`, `uvx pre-commit run --all-files`.

## Validation Ladder

Smallest step that proves the change. Steps 1-3 are static or import-only; step 4 executes task code.

1. **Import and parse time** (always first): `uv run --no-project python -c "import <dag_module>"` in the local env.
   - Parse budget under ~30s; hard `dagbag_import_timeout` on the shared platform is 180s (Airflow default 30s).
   - POSIX: prefix `time`. PowerShell: `Measure-Command { uv run --no-project python -c "import <dag_module>" }`.
2. **Project-wide import errors**: `airflow dags list-import-errors`, `airflow dags list` on local/containerized Airflow; for MWAA parity use `aws/amazon-mwaa-docker-images` at the target version (`./run.sh`, PowerShell `.\run.ps1`). CI: load every DAG through `DagBag` (or the Sanofi `airflow-validate` action) with dummy Variables (`AIRFLOW_VAR_<KEY>` env vars).
3. **Structure, dependencies, cycles**: `airflow tasks list <dag_id>`, `airflow dags show <dag_id>`.
4. **Execution** (runs task code and side effects; warehouse writes, API calls, secret reads):
   - `airflow tasks test <dag_id> <task_id> <date>`: one task, ignores dependencies, records no state.
   - `airflow dags test <dag_id> <date>`: full DAG run in one process.
   - MUST use local/containerized Airflow with DEV connections only. NEVER shared MWAA or PROD credentials.
5. **Lint/type**: run the repo's configured `ruff`, `pylint`, `pyright`, `pre-commit`. Any DAG targeting 3.x: `uvx ruff@latest check <dags_dir> --select AIR3` (ruff ≥ 0.13.1; AIR301/AIR302 are breaking). Preview parse checks: `uvx ruff@latest check <dags_dir> --preview --select AIR003,AIR304` (`Variable.get()` outside a task, runtime-changing DAG args).
6. **dbt side**: validate with the dbt skill (`dbt parse`/`dbt compile`); confirm `--select` resolves with `dbt ls` before wiring into a DAG.

No local Airflow? State the exact command and the missing prerequisite. NEVER discover parse errors by deploying.

## Failure Masking

| Bad | Good |
|---|---|
| Sole leaf `cleanup` with `trigger_rule="all_done"`: run succeeds after upstream failure | Add a sibling leaf with default `all_success` downstream of the work task; run fails, cleanup still runs |
| Failure callback raises | Catch and log inside the callback |

Pattern and code: [general-airflow-guide.md](references/general-airflow-guide.md) (TaskFlow API, Alerting).

## Airflow 3 Traps

| Bad (2.x habit on a 3.x tenant) | Good |
|---|---|
| Bare cron/preset `schedule="@daily"` with tasks or dbt vars reading `data_interval_start/end` | 3.x default `CronTriggerTimetable` gives a zero-width interval (start == end). Use `CronDataIntervalTimetable` or `CronTriggerTimetable(..., interval=...)` explicitly |
| `context["data_interval_start"]` / `context["logical_date"]` in an Asset-triggered or API-triggered DAG | Those runs have `logical_date=None` and no interval; the keys raise `KeyError`. Check `dag_run.logical_date` / `context.get(...)` and fall back, or pass the window via params |
| `execution_date`, `prev_ds`, `next_ds`, `yesterday_ds`, `conf` in context or Jinja | `logical_date`, `data_interval_*`, `dag_run`, DAG `params` |
| `ti.xcom_pull(key=...)` without `task_ids` | Pass `task_ids=`; 3.x pulls only from the current task by default |
| SQLAlchemy session / ORM models on the metadata DB inside a task | Task SDK (`airflow.sdk.Variable`, `Connection`) or the REST API (`/api/v2`) |
| `SubDagOperator`, `sla`, `sla_miss_callback` | TaskGroups; Deadline Alerts (3.1+) |

Import map, config renames, removed features, and MWAA migration rules: [general-airflow-guide.md](references/general-airflow-guide.md) (Airflow 3 Migration).

## Checklist

- No module-level `Variable.get()`, `get_secret()`, heavy import, DB or API call.
- `retries`, `execution_timeout`, `dagrun_timeout`, `catchup`, `max_active_runs` set deliberately.
- Imports and context keys match the target major version; for 3.x, `ruff check --select AIR3` is clean.
- On 3.x, any schedule feeding interval-based logic (dbt run vars, partitions) uses an explicit data-interval timetable.
- Config via `ConfigLoader`; secrets resolved inside tasks.
- No `all_done` cleanup task masking upstream failure.
- Ignore-file syntax matches the environment's `dag_ignore_file_syntax`.
- Import and parse time verified locally; execution commands run only against DEV.
- Reference files read for every area touched.
