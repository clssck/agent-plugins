---
name: sanofi-airflow
description: "Author, review, deploy, and troubleshoot Airflow DAGs on Sanofi MWAA (shared central or dedicated tenant). Use when working with parse-time safety, sanofi-airflow-utils ConfigLoader and secrets, failure alerts, access_control roles, CI S3 sync, the Airflow 2.11 → 3.x migration, or running dbt via dbt_run.sh or DbtClient. Not for generic Airflow; dbt models/SQL — dbt skill; generic CI/CD — cicd-engineering; generic review — omp /review."
---

# Sanofi Airflow

Sanofi conventions for DAGs on AWS MWAA: shared central environment (2.11) and dedicated tenants (3.x). Covers parse-time safety, `sanofi-airflow-utils` config/secrets, failure alerts, access roles, CI/S3 sync, Airflow 3 migration, and dbt via `dbt_run.sh`/`DbtClient`. The governing principle: **the shared scheduler imports every `.py` under `dags/` every 30-60s, so one bad DAG degrades every tenant**. Parse safety comes first, before correctness of task logic.

This skill holds platform facts only. Run omp `/review` on the diff for generic defects, then apply this skill for Sanofi-specific ones. Generic Airflow is out of scope · dbt models/SQL/YAML/tests → dbt skill · generic CI/CD → cicd-engineering.

<critical>

- **Inspect the real repo first.** Derive `dags/` layout, `dag_id`/`task_id` convention, `default_args`, config/secrets loader, tags, roles, Airflow major version (2.11 vs 3.x), and dbt-run mechanism from files.
- **Examples are patterns.** NEVER copy example names, roles, paths, or versions verbatim.
- **Parse-time safety is review item one.** Module-level `Variable.get()`, `get_secret()`, heavy import, DB connection, API call = blocking defect, even when the DAG "works". Move it into the task body or Jinja (`{{ var.value.KEY }}`).
- **Ignore-file syntax follows configuration, not version.** Check `dag_ignore_file_syntax` (`regexp` | `glob`; default `glob` on Airflow 3, `regexp` before).
- **Imports follow the target major version.** 2.11: `airflow.decorators`, `airflow.operators.bash`, `Dataset`. 3.x: `airflow.sdk` (`dag`, `task`, `Asset`, `Variable`) and `airflow.providers.standard.operators.bash`. `airflow.sdk` absent on 2.11; legacy paths only warn on 3.x and are slated for removal.
- **Airflow 3 changes run semantics, not just imports.** Check every DAG headed to a 3.x tenant against [Airflow 3 Traps](#airflow-3-traps).
- **NEVER deploy to shared MWAA to test a DAG.** Prove changes locally or in CI.
- **Verification source:** the repo's README, Makefile, CI, or scripts > the [Validation Ladder](#validation-ladder).

</critical>

<instruction>

| Task | `read` |
|---|---|
| Platform model, repo layout, naming, DAG config, TaskFlow, config/secrets, Datasets/Assets, sensors, alerting, access control, CI/CD, troubleshooting, Airflow 3 migration | [general-airflow-guide.md](skill://sanofi-airflow/references/general-airflow-guide.md) |
| Running dbt from a DAG: `BashOperator` + `dbt_run.sh` or typed `DbtClient`, logs/artifacts, backfills, run vars | [orchestrating-dbt.md](skill://sanofi-airflow/references/orchestrating-dbt.md) |

- **Read every reference covering an area the change touches, and only those.**
- **Multi-area change order:** parse safety + DAG config → task logic → orchestration wiring → alerting/access/tags → deploy and run commands.

</instruction>

<procedure>

### Validation Ladder

Run the smallest step that proves the change. Steps 1-3 are static or import-only. Step 4 executes task code.

1. **Import and parse time** (always first): `uv run --no-project python -c "import <dag_module>"`.
   - Parse budget under ~30s. Hard `dagbag_import_timeout`: 180s on the shared platform (Airflow default 30s).
   - Timing: POSIX → prefix `time`; PowerShell → `Measure-Command { uv run --no-project python -c "import <dag_module>" }`.
2. **Project-wide import errors:** `airflow dags list-import-errors` and `airflow dags list` on local or containerized Airflow.
   - MWAA parity: `aws/amazon-mwaa-docker-images` at the target version (`./run.sh`; PowerShell `.\run.ps1`).
   - CI: load every DAG through `DagBag` (or the Sanofi `airflow-validate` action), with dummy Variables as `AIRFLOW_VAR_<KEY>` env vars.
3. **Structure, dependencies, cycles:** `airflow tasks list <dag_id>`, `airflow dags show <dag_id>`.
4. **Execution** (runs task code and side effects: warehouse writes, API calls, secret reads):
   - `airflow tasks test <dag_id> <task_id> <date>`: one task, ignores dependencies, records no state.
   - `airflow dags test <dag_id> <date>`: full DAG run in one process.
   - **MUST** use local or containerized Airflow with DEV connections only. NEVER shared MWAA or PROD credentials.
5. **Lint/type:** the repo's configured `ruff`, `pylint`, `pyright`, `pre-commit`.
   - Any DAG targeting 3.x: `uvx ruff@latest check <dags_dir> --select AIR3` (ruff ≥ 0.13.1; AIR301/AIR302 breaking) must be clean.
   - Preview parse checks: `uvx ruff@latest check <dags_dir> --preview --select AIR003,AIR304` (`Variable.get()` outside a task; runtime-changing DAG args).
6. **dbt side:** validate with the dbt skill (`dbt parse`/`dbt compile`). Confirm `--select` resolves with `dbt ls` before wiring it into a DAG.

No local Airflow → state the exact command and the missing prerequisite. NEVER discover parse errors by deploying.

</procedure>

<caution>

### Failure Masking

| Bad | Good |
|---|---|
| Sole leaf `cleanup` with `trigger_rule="all_done"` → run succeeds after upstream failure | Add a sibling leaf with default `all_success` downstream of the work task → run fails, cleanup still runs |
| Failure callback raises | Catch and log inside the callback |

Pattern and code: [general-airflow-guide.md](skill://sanofi-airflow/references/general-airflow-guide.md) (TaskFlow API, Alerting).

### Airflow 3 Traps

| Bad (2.x habit on a 3.x tenant) | Good |
|---|---|
| Bare cron/preset `schedule="@daily"` with tasks or dbt vars reading `data_interval_start/end` | 3.x default `CronTriggerTimetable` → zero-width interval (start == end). Use `CronDataIntervalTimetable` or `CronTriggerTimetable(..., interval=...)` explicitly |
| `context["data_interval_start"]` / `context["logical_date"]` in an Asset- or API-triggered DAG | Those runs have `logical_date=None` and no interval → `KeyError`. Check `dag_run.logical_date` / `context.get(...)` and fall back, or pass the window via params |
| `execution_date`, `prev_ds`, `next_ds`, `yesterday_ds`, `conf` in context or Jinja | `logical_date`, `data_interval_*`, `dag_run`, DAG `params` |
| `ti.xcom_pull(key=...)` without `task_ids` | Pass `task_ids=`; 3.x pulls only from the current task by default |
| SQLAlchemy session / ORM models on the metadata DB inside a task | Task SDK (`airflow.sdk.Variable`, `Connection`) or the REST API (`/api/v2`) |
| `SubDagOperator`, `sla`, `sla_miss_callback` | TaskGroups; Deadline Alerts (3.1+) |

Import map, config renames, removed features, MWAA migration rules: [general-airflow-guide.md](skill://sanofi-airflow/references/general-airflow-guide.md) (Airflow 3 Migration).
</caution>

## Local Environment

MWAA installs `requirements.txt` with `pip3` plus an Airflow constraints file. Mirror that locally with uv. NEVER `pip install` into system or Homebrew Python.

```bash
uv venv --python 3.12   # MWAA 2.11 and 3.x run Python 3.12
uv pip install "apache-airflow==<version>" -r requirements.txt \
  -c "https://raw.githubusercontent.com/apache/airflow/constraints-<version>/constraints-3.12.txt"
uv run --no-project airflow dags list-import-errors
```

- **Existing tooling wins.** If the repo already uses poetry, pip-tools, or `uv.lock`, keep it (`uv run` for uv projects). Recommend uv only for new work.
- **One-off CLIs without install:** `uvx ruff@latest ...`, `uvx pre-commit run --all-files`.

## Review Gates

A change is not done until every applicable gate holds:

| Gate | Requirement |
|---|---|
| Parse safety | No module-level `Variable.get()`, `get_secret()`, heavy import, DB or API call |
| Run settings | `retries`, `execution_timeout`, `dagrun_timeout`, `catchup`, `max_active_runs` set deliberately |
| Version fit | Imports and context keys match the target major; 3.x → `ruff check --select AIR3` clean |
| 3.x windows | Schedule feeding interval logic (dbt run vars, partitions) uses an explicit data-interval timetable |
| Config | Via `ConfigLoader`; secrets resolved inside tasks |
| Failure state | No `all_done` cleanup task masking upstream failure ([Failure Masking](#failure-masking)) |
| Ignore file | Syntax matches the environment's `dag_ignore_file_syntax` |
| Proof | Import/parse time verified locally; execution commands run only against DEV |
