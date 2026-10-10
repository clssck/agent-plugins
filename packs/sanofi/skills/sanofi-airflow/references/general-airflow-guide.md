# General Airflow Guide

Sanofi Airflow guidance for the shared MWAA platform, derived from the OneMesh
"Airflow - how to guide" and its child pages, plus reusable DAG standards and
best-practice pages from other Sanofi Airflow spaces.

## Source of Truth

When project files disagree with examples here, treat the repository as the immediate
source of truth and call out the mismatch. For Sanofi platform behavior (scheduler,
parse cycle, MWAA sizing), prefer the OneMesh guide. Treat cross-space DAG standards as
supporting evidence when the same pattern recurs, not as a reason to overwrite a repo's
documented local contract.

Core references use base `https://sanofi.atlassian.net/wiki/spaces/OneMesh/pages/`:
`Airflow - how to guide` 66306933380; `1. DAG Authoring Best Practices` 66486699835;
`2. Deployment & Project Structure` 66485783031; `3. Performance & Troubleshooting`
66486175813; `4. Platform Architecture` 66480121490; `5. FAQ & Quick Reference`
66487551192; global `.airflowignore` 66531364329. A `2026-06-23` draft set (page 67178465278) tracks the move to dedicated-tenant MWAA on Airflow 3.2.1.

Additional standards sources:

- `Airflow DAG Standards` (USDFPAA space) `67161393536`: mandatory file/naming rules,
  the explicit DAG-config checklist, the `orchestration/dags` + `utils/` layout, Dataset
  cross-DAG scheduling, custom failure email, and ServiceNow/TACO incidents. Reuse the
  generic rules; treat `paa/caa/saa` `dag_id` prefixes and role names as local examples.
- `Airflow Best Practices` (USDFMSPA01 space) `66921496793`: Python/PEP 8 discipline,
  the pull-request DAG checklist, `@dag` decorator standard, central `DagBuilder`, task
  timeouts, tags, and atomic tasks.

All project names, `dag_id`s, folders, roles, schemas, warehouses, IAM group names,
paths, and dates in examples are placeholders unless explicitly identified as a Sanofi
platform fact. Adapt them to the target repository and current platform guidance.

## How to Use This Reference

Use this file as a routing index. For new DAGs read Parse-Time Safety, DAG
Configuration, TaskFlow, and Structure. For orchestration read Cross-DAG Datasets,
Sensors, and (for dbt) the separate [`orchestrating-dbt.md`](orchestrating-dbt.md). For
operations read Alerting, Access Control, CI/CD & Deployment, and Troubleshooting. For any
DAG targeting Airflow 3.x or a 2.x -> 3.x move, read Airflow 3 Migration.

## Platform Model

Sanofi runs Airflow on AWS MWAA. Two operating models exist:

- Shared central MWAA: a multi-tenant environment hosting 120-180+ projects across
  DEV/UAT/PROD, currently on Airflow 2.11. The scheduler imports every `.py` under
  `dags/` every 30-60s, so one project's bad DAG degrades the whole platform. Central
  package versions are platform facts you cannot change per project.
- Dedicated tenant MWAA: newer tenant-owned environments provisioned from the MWAA
  blueprint, targeting Airflow 3.2.1, with per-tenant sizing, private UI mode, and
  isolated scheduler/workers/metadata DB/DAG bucket. Airflow 2.11 is used only for a
  migration window when the first step is tenant isolation without a version change.

Confirm the environment's Airflow major version before writing version-sensitive code,
and read the ignore-file syntax from configuration, not from the version number:
`core.dag_ignore_file_syntax` (`AIRFLOW__CORE__DAG_IGNORE_FILE_SYNTAX`) is `regexp` or
`glob`. The Airflow default is `glob` from Airflow 3 and `regexp` before, but the
setting can be overridden. Check the live value for the target environment before
writing a project `.airflowignore`. Never copy an ignore file written for one syntax
into an environment configured for the other.

Amazon MWAA facts (AWS docs, checked 2026-10): MWAA supports 3.3.1, 3.2.1, 3.0.6, 2.11.2,
2.11.0, and older 2.7-2.10 releases; 2.11 and 3.x run Python 3.12 (2.10 and earlier: 3.11).
MWAA keeps Flask-AppBuilder auth on 3.x (no Simple Auth switch), and multi-team mode is
unsupported. MWAA only does in-place minor upgrades, so 2.x -> 3.x means a new environment
(blue/green), not an update. Which version a Sanofi platform runs (2.11 shared, 3.2.1
dedicated) is a Sanofi fact; confirm the live version before relying on it.

MWAA components (provisioned via Terraform): Scheduler, Workers (Celery), WebServer,
Metadata DB, S3 DAG bucket, and Secrets Manager. DAGs are deployed by syncing to the S3
`dags/` prefix, not by editing the environment directly.

Platform scheduler facts worth knowing: the scheduler re-parses existing files roughly
every 60s, but a newly added file only appears after one `dag_dir_list_interval` (on the
shared platform ~5 min in DEV, ~10 in UAT, ~15 in PROD), so a missing brand-new DAG is
often just not scanned yet. On Airflow 3.x that setting is `[dag_processor]
refresh_interval`, and `min_file_process_interval`, `parsing_processes`, and
`dag_file_processor_timeout` also moved from `[scheduler]`/`[core]` to
`[dag_processor]` (`airflow config lint` lists renames); an `AIRFLOW__SCHEDULER__*`
override written for 2.11 does nothing on 3.x. Each file has a hard import timeout of 180s
(`dagbag_import_timeout`); aim for a parse budget well under 30s. Workers autoscale
(`worker_autoscale=16,4`) and `task_acks_late=True` re-queues killed tasks, so retries
are mandatory. A DAG unseen for ~40 min is evicted from the UI.

The shared platform pre-installs a curated package set (dbt-core, dbt-snowflake,
dag-factory, the Snowflake connector/snowpark, `sanofi-airflow-utils`, and common
providers). Do not reinstall or pin these in a project; request additions or
version changes via a PR to the MWAA provisioning repo's `requirements.txt`. Treat exact
versions as environment facts that drift — verify the live `requirements.txt`/constraints
rather than hardcoding versions in a DAG.

Dedicated tenants own their `requirements.txt`. MWAA installs it with `pip3 install -r`
plus an Airflow constraints file (a `--constraint` line is required from Airflow 2.7.2),
and the install fails on any pin the constraints reject. Prove it locally first with the
uv recipe in SKILL.md (Local Environment) and, for MWAA parity,
`./run.sh test-requirements` from `aws/amazon-mwaa-docker-images`.

## Parse-Time Safety

This is the highest-value rule on the shared platform and the first thing to review.

**Never call `Variable.get()`, `Connection.get()`, or any secret lookup at module
level** (outside a task function). Module-level code runs on every scheduler parse
cycle, so a single top-level `Variable.get()` becomes thousands of Secrets Manager /
metadata-DB calls per minute across tenants, adds ~100-500ms per parse, and makes the
whole DAG fail to parse if the variable is missing.

Resolve configuration by where it is needed:

- `{{ var.value.KEY }}` (Jinja) in operator arguments/commands: evaluated at task
  execution time, not parse time. Preferred for simple task parameters.
- `Variable.get()` inside a task function: fine, because it runs only when the task runs.
- `os.environ.get("KEY", "default")` for DAG-level config such as `dag_id` suffix or
  schedule: reads a local env var with no DB call, so it is safe at module level.

Keep top-level code minimal. Allowed at module level: `from airflow.decorators import
dag, task`, operator imports, the DAG/task definitions, lightweight imports (`os`,
`yaml`), and static literals. Everything else — `import pandas`, `import
snowflake.connector`, DB connections, API calls, heavy computation — belongs inside task
functions.

| Method                           | Runs at parse time? | DB call? | Use for                           |
| -------------------------------- | ------------------- | -------- | --------------------------------- |
| `Variable.get()` at module level | Yes                 | Yes      | Never                             |
| `{{ var.value.key }}` (Jinja)    | No (execution)      | Yes      | Task parameters, commands         |
| `Variable.get()` inside a task   | No (execution)      | Yes      | Complex logic inside tasks        |
| `os.environ.get()`               | Yes                 | No       | `dag_id`, schedule, static config |

For shared config, prefer the `sanofi-airflow-utils` `ConfigLoader` (see Configuration
and Secrets) over ad-hoc `Variable.get()`.

## Project and Repo Structure

Many Sanofi repos keep dbt under `transformation/` and orchestration under
`orchestration/`. Inspect the repo root before assuming the DAG root. A common
`orchestration/` layout:

```
orchestration/
└── dags/
    ├── <data_product_or_pod>/   ← project DAGs (one folder per data product / pod)
    ├── shared_dags/             ← DAGs shared by multiple pods (project-prefixed)
    ├── config/                  ← common.yml + dev/uat/prod.yml (ConfigLoader)
    ├── unit_tests/              ← pytest DAG validation (excluded from parsing)
    ├── utils/                   ← importable modules, NOT parsed as DAGs
    │   ├── common/              ← shared Snowflake / date / email helpers
    │   ├── dag_utils/           ← DAG factory, default_args & schedule builders
    │   ├── data_quality_check/  ← row/schema validators
    │   ├── db_utils/            ← DB connection & query helpers
    │   ├── monitoring/          ← failure callbacks: email + ServiceNow/TACO
    │   └── __init__.py
    └── .airflowignore           ← excludes unit_tests/ and other non-DAG dirs
```

Only files needed by the scheduler should reach the S3 `dags/` path; uploading extra
files slows scans and wastes storage. The platform ships a global `.airflowignore` at
the `dags/` root that already excludes `transformation/`, `dbt_packages/`, `seeds/`,
`macros/`, non-Python files (`.sql`, `.yml`, `.csv`, `.json`, ...), build artifacts, and
IDE/VCS folders. Add a project-level `.airflowignore` only for custom exclusions, and
match the environment's configured `dag_ignore_file_syntax`.

## Naming

- One DAG per file; the filename equals the `dag_id` exactly so an alert names the file.
- Lowercase `snake_case` only — no capitals and no dots (dots break Python imports and
  DAG parsing).
- `dag_id` groups a data product with a stable prefix and entity, e.g.
  `<prefix>_<entity>` (repos vary: some use `paa/caa/saa` domain prefixes). Follow the
  repo's convention.
- `task_id` is verb-first and names one unit of work: `extract_*`, `validate_*`,
  `load_*`, `run_dbt_*`. It should read as a pipeline so it is clear what failed.
- Owner, emails, tags, and schedules come from shared constants/helpers, never inline
  literals.

## DAG Configuration

Every DAG must set these explicitly; implicit defaults cause surprise backfills and
stuck runs.

| Setting            | Standard                                                         | Why                                            |
| ------------------ | ---------------------------------------------------------------- | ---------------------------------------------- |
| `start_date`       | Static `datetime(...)`. Never `datetime.now()`                   | Dynamic start dates break scheduling/backfills |
| `catchup`          | `False` unless a backfill is genuinely intended                  | Stops a run storm when a paused DAG is enabled |
| `schedule`         | Explicit cron/preset; `None` for trigger-only                    | Removes ambiguity about when it runs           |
| `max_active_runs`  | Deliberate — `1` for any stateful load                           | Prevents two runs racing on the same target    |
| `max_active_tasks` | Set on wide DAGs (e.g. `16`)                                     | Stops one DAG flooding shared worker slots     |
| `dagrun_timeout`   | Set on anything that can hang                                    | A stuck run must not hold a slot indefinitely  |
| `tags`             | From a shared helper; include team, priority, schedule           | Findable in a crowded UI                       |
| `default_args`     | Shared dict; `email_on_failure=False`, `on_failure_callback` set | Consistent, predictable failure behavior       |

Recommended `default_args`:

```python
from datetime import timedelta

default_args = {
    "owner": "<team>",
    "retries": 2,
    "retry_delay": timedelta(seconds=30),
    "retry_exponential_backoff": True,
    "execution_timeout": timedelta(hours=2),
    "on_failure_callback": task_error_alert,
}
```

Retries and timeouts are not optional on this platform. Celery workers can be OOM-killed
(SIGKILL); `task_acks_late=True` re-queues killed tasks, so without retries a killed
task is a permanent failure. Set `execution_timeout` higher than the platform's
`killed_task_cleanup_time` (120s), and `dagrun_timeout` above the longest legitimate run.
`email_on_failure`/`email_on_retry` stay `False` — alerting is handled by the custom
`on_failure_callback`, not Airflow's built-in email.

## TaskFlow API

The TaskFlow API (`@dag`, `@task`) is the recommended authoring style; it removes
boilerplate and passes data via return values (implicit XCom) instead of manual
push/pull.

```python
import os
from datetime import datetime, timedelta
from airflow.decorators import dag, task  # 2.11; on 3.x: from airflow.sdk import dag, task

ENV = os.environ.get("MWAA_ENV", "dev").lower()

@dag(
    dag_id=f"<project>_pipeline_{ENV}",
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    max_active_tasks=16,
    default_args=default_args,
    tags=["<project>", "daily"],
)
def pipeline():

    @task
    def extract(**context) -> dict:
        import pandas as pd  # heavy import inside the task
        ...

    @task.bash
    def run_dbt() -> str:
        return "dbt run --project-dir /path --target {{ var.value.MWAA_ENV }}"

    @task(trigger_rule="all_done")
    def cleanup(**context) -> bool:
        ...  # runs even if upstream fails

    @task
    def mark_complete() -> None:
        ...  # default all_success: becomes upstream_failed when run_dbt fails

    dbt_run = run_dbt()
    extract() >> dbt_run
    dbt_run >> [cleanup(), mark_complete()]

pipeline()
```

A DAG run takes its state from its leaf tasks (those with no downstream tasks). A sole
`all_done` leaf runs after any upstream outcome and, if it succeeds, marks the whole run
`success` even when `run_dbt` failed. So give cleanup a sibling leaf with the default
`all_success` rule (`mark_complete`), which turns `upstream_failed` and fails the run
while cleanup still executes. Setup/teardown tasks (`as_setup()`/`as_teardown()`) are an
alternative when a real setup task exists; teardowns are ignored for run state by default
(`on_failure_fail_dagrun=True` changes that for the teardown itself).

Make tasks idempotent so retries and backfills are safe: UPSERT/MERGE instead of
INSERT, read and write one partition keyed on `data_interval_start` (never "latest"),
and never use `datetime.now()` for business logic inside a task.

Key decorators: `@task` (replaces `PythonOperator`), `@task.bash` (return the command
string; replaces `BashOperator`), `@task.short_circuit` (skip downstream),
`@task.branch` (choose a path). Keep tasks **atomic** — one action each — so retries,
logging, and recovery stay granular. Prefer a central `DagBuilder`/`dag_utils` factory
(`get_dag`, `get_python_operator`, `get_dbt_operator`) when the repo provides one, so
operator defaults stay consistent. Document the DAG with `doc_md` so its purpose shows
in the UI.

## Configuration and Secrets

Prefer the official shared library `sanofi-airflow-utils` (pre-installed on the
platform) over ad-hoc `Variable.get()` and hardcoded environment dicts. Its
`ConfigLoader` reads layered YAML (`config/common.yml` plus `config/<env>.yml`) and maps
logical secret names to Airflow Variable / Secrets Manager keys:

```python
from sanofi_airflow_utils import ConfigLoader

loader = ConfigLoader()                              # parse-safe at module level
project = loader.get_config("project_name")          # YAML only, no DB call
role = loader.get_config("snowflake.snowflake_role")

@task
def connect():
    # resolved when the task runs, never at parse time
    private_key = loader.get_secret("snowflake_private_key")
```

`get_config()` reads YAML with zero DB calls. `get_secret()` is lazy only in the sense
that `ConfigLoader()` does not resolve secrets on construction: every `get_secret()` call
runs `Variable.get()` immediately. Instantiating `ConfigLoader()` at module level is
safe; calling `get_secret()` at module level is a parse-time secret lookup. Call it
inside a task function.

Keep environment-specific values (roles, databases, warehouses, users) in
`config/<env>.yml` and shared values in `config/common.yml`.

Pick the right store for each value: Airflow **Variables** for project config, flags, and
toggles (read via `{{ var.value.key }}` or `ConfigLoader`); Airflow **Connections** for
database credentials and API endpoints (referenced by `conn_id` on an operator/hook, so
secrets never sit in DAG code); and AWS **Secrets Manager** for anything sensitive, which
MWAA fetches transparently. On the shared platform the CI sync maps GitHub `MWAA_*`
secrets into Secrets Manager under a fixed path convention
(`airflow/variables/emea/<env>/<project>/<KEY>` and `.../connections/...`), and the MWAA
secrets backend reads them automatically — you do not configure the backend yourself.

## Cross-DAG Orchestration

Run a DAG after another completes — including DAGs owned by other projects or repos —
using Airflow Datasets (data-aware scheduling), not hardcoded triggers. On Airflow 3.x
Datasets are called Assets (`from airflow.sdk import Asset`; `airflow.datasets.Dataset`
is deprecated). An upstream DAG publishes the asset when it finishes; downstream DAGs
schedule off it and run automatically. The upstream team never imports, names, or
triggers the downstream DAG, so the projects stay decoupled. Prefer Datasets/Assets over
`TriggerDagRunOperator` and `ExternalTaskSensor` for inter-DAG dependencies. Runs
triggered by an asset event have `logical_date=None` and no data interval (see Airflow 3
Migration).

## Sensors and Long Waits

Sensors hold a worker slot while waiting, which is expensive on a shared environment.

| Mode                | Behavior                                        | Use when                            |
| ------------------- | ----------------------------------------------- | ----------------------------------- |
| `poke` (default)    | Holds a worker slot continuously                | Short waits (<5 min)                |
| `mode="reschedule"` | Releases and re-acquires the slot between pokes | Long waits (>5 min)                 |
| `deferrable=True`   | Uses the triggerer, no worker slot              | Best for long waits (async support) |

Set `poke_interval`, `timeout`, and `execution_timeout` explicitly. Prefer deferrable
sensors/operators where supported; otherwise use `mode="reschedule"` for long waits.

## Dynamic DAG Generation

Generating DAGs in a loop is powerful but dangerous when it does real work at parse time.
Never query a database or call `Variable.get()` at module level to build DAGs. Drive
dynamic generation from a static YAML config file committed to the repo, or use
`dag-factory` (installed on the platform) to generate DAGs from YAML with no Python.

## Running dbt from Airflow

This is the dominant Sanofi orchestration use case and has its own reference. See
[`orchestrating-dbt.md`](orchestrating-dbt.md) for choosing and wiring a dbt execution
approach (`BashOperator` + `dbt_run.sh` or a typed `DbtClient`), logs/artifacts, backfills,
and run vars. For changes to the dbt models/SQL/tests themselves, use the dbt skill.

## Alerting and Failure Handling

Every production DAG must alert on failure with actionable context (which task, why, and
a link to the logs) via a shared `on_failure_callback`, not per-task
`email_on_failure=True`. Common Sanofi pattern: a callback that sends a custom failure
email and, for production failures needing human action, auto-creates a ServiceNow
incident through the TACO architecture.

```python
def task_error_alert(context):
    info = {
        "dag_id": context["dag"].dag_id,
        "task_id": context["task_instance"].task_id,
        "logical_date": context["logical_date"],
        "exception": str(context.get("exception", "")),
        "log_url": context["task_instance"].log_url,
    }
    send_alert(info)  # email helper in sanofi-airflow-utils; add incident on PROD
```

Rules for callbacks: a failure callback must **never raise** — catch and log internally
so the original task error and other callbacks still propagate. Gate incident creation to
production. Use a `trigger_rule="all_done"` cleanup/summary task for work that must run
regardless of upstream success (resource cleanup, failure summaries), but NEVER as the
sole leaf of the DAG: it would mark the run `success` after an upstream failure. Pair it
with a default-rule leaf as shown in the TaskFlow example.

## Access Control

Set `access_control` on DAGs so the right MWAA roles can view/edit them. Role names must
match the IAM role mappings configured by the platform team:

```python
ACCESS_CONTROL = {
    "MWAA_<PROJECT>_USERS": ["can_read"],
    "MWAA_<PROJECT>_DEVELOPERS": ["can_read", "can_edit"],
}
```

Keep DAG unit tests under a `unit_tests/` directory that is excluded from DAG parsing.
Cover: the DAG imports with no errors, there are no cycles, `default_args`/tags/timeouts
are set, and any custom builder logic behaves. Local commands and their order: Validation
Ladder in SKILL.md. `airflow tasks test` and `airflow dags test` **execute task code**; run
them only against a local/containerized Airflow with DEV connections.

## CI/CD and Deployment

GitHub Actions under `.github/workflows/` automate sync and docs. Common workflows:
`airflow-sync.yml` (sync DAGs/code to MWAA), `airflow-sync-secrets.yml` (sync
connections/variables/secrets), `autodoc.yml` (generate docs), and `changelog.yml`
(release notes on merge). Sanofi also publishes reusable workflows/actions (e.g. a
`reusable-airflow-sync` workflow and an `airflow-validate` action) — prefer these over
hand-rolled sync logic.

Validate DAGs in CI before deploy: load every DAG through Airflow's `DagBag` in an
ephemeral environment (SQLite, dummy Variables for anything read at import time) and fail
the build on import errors. This catches parse-time defects — module-level
`Variable.get()`, missing variables, heavy-import timeouts — before they reach the shared
scheduler. The deploy step then syncs the repo (typically `orchestration/` and
`transformation/`) to `s3://<mwaa-bucket>/dags/<project>/`, with an approval gate before
PROD and orphan-file cleanup (`delete_from_s3`). Never upload `.xlsx`/`.docx`/
`__pycache__` to the DAGs bucket; data files belong in a data bucket or dbt seeds.

For dedicated tenants, start from the blueprint `tenant-skeleton/`. `SERVICE` endpoint
management is the default (MWAA creates its own PrivateLink endpoints); UI access mode is
explicit (`aws_iam`, `sanofi_network`, or `ad_group`). Bootstrap uses CI-managed sync:
DAGs, `dags/constraints.txt`, and `dags/ca-bundle.pem` sync without an MWAA update, while
`requirements.txt`, `startup.sh`, and `plugins.zip` trigger an environment update only
when their S3 object version changes. Generate mandatory CE tags with the
`tags_mandatory_tags` Terraform module rather than hand-writing `CE_*` tags.

Dedicated MWAA sizing: use at least 2 schedulers for `dev`/`uat`/`prod` (1 only for
disposable `sbx`). Start `mw1.small` with `min_workers=1`, `max_workers=5` for normal
`dev`/`uat`; use `mw1.medium`, `schedulers=2`, `max_workers=10` as a safer first prod
baseline. Increase workers when queues back up; increase environment class when tasks
need more CPU/memory or scheduler headroom.

### Deployment Checklist

Before deploying a DAG to shared MWAA, confirm:

- No `Variable.get()` / secret / heavy import at module level (use the `grep` tool for
  `Variable\.get|get_secret` over `orchestration/dags/**/*.py`; every hit MUST sit inside
  a function or Jinja template).
- `default_args` sets `retries` and `execution_timeout`; the DAG sets `dagrun_timeout`.
- `dag_id` includes the environment (via `os.environ.get("MWAA_ENV")`).
- Config comes from `ConfigLoader`/YAML, not hardcoded env dicts.
- The file parses fast locally (Validation Ladder step 1, target <30s) and CI DagBag
  validation is clean.
- `access_control`, `max_active_runs`, and `max_active_tasks` are set.

## Troubleshooting

The scheduler loop runs continuously: Scan S3 `dags/` -> Parse (import each `.py`;
module-level code runs here) -> Serialize to the metadata DB -> Schedule/queue tasks ->
Evict DAGs not parsed within ~40 min. If a DAG cannot parse in time, it disappears from
the UI.

| Symptom                  | Likely cause                     | Fix                                                                                    |
| ------------------------ | -------------------------------- | -------------------------------------------------------------------------------------- |
| DAG missing from UI      | Import error                     | Search CloudWatch `DAGProcessing` for `Failed to import: <file>`; fix the Python error |
| DAG missing from UI      | Parse timeout (>180s)            | Move heavy imports / `Variable.get()` inside tasks                                     |
| DAG missing from UI      | Missing Variable                 | Search `Failed to retrieve secret`; create it or remove the top-level `Variable.get()` |
| DAG missing from UI      | Brand-new file not scanned yet   | Wait one `dag_dir_list_interval` (~5-15 min by env) before assuming a defect           |
| DAG missing from UI      | Stale eviction (>40 min)         | Confirm the file is valid Python and parses quickly                                    |
| Task exit 127            | Command not found (bash 127)     | Check the command name, `PATH`, and that the binary (e.g. `dbt`) is installed in the runtime |
| Task exit 137 / Signal 9 | SIGKILL (128+9); often OOM       | Check `Worker` logs for OOM or another kill cause first; then chunk/stream, cap memory-heavy tasks with a `pool`, add retries |
| Task logs missing        | Worker SIGKILLed before flushing | Check CloudWatch `Worker` logs directly by task/run id                                 |

Diagnose parse cost locally with Validation Ladder step 1 (SKILL.md). Key CloudWatch
log groups: `airflow-<env>-DAGProcessing` (parse errors/timeouts), `-Scheduler` (stale
DAGs/evictions), `-Task` (task execution), `-Worker` (OOM/celery), `-WebServer`. Watch
metrics: Scheduler CPU (<60% healthy, >80% critical), Worker CPU (<70%/>90%), Queued
Tasks (<50/>200), Stale DAGs (0 healthy). Highest-impact, lowest-effort fixes: move
`Variable.get()` and heavy imports into tasks, adopt `ConfigLoader`, set
`max_active_tasks`, and use `pool`s for memory-heavy work.

## Airflow 3 Migration

Apply when a DAG targets a 3.x tenant or is being prepared to move off the shared 2.11
platform. Review order: lint, imports, scheduling semantics, DB access, config, requirements.

1. **Lint first.** `uvx ruff@latest check <dags_dir> --select AIR301,AIR302` (ruff >= 0.13.1) flags
   removals and provider moves; `--fix` applies safe fixes, `--unsafe-fixes` also rewrites
   import paths (enable `F401` to drop leftovers). `AIR311`/`AIR312` are still-working but
   deprecated. Preview rules `AIR003` (`Variable.get()` outside a task) and `AIR304`
   (`datetime.now()`/random in DAG or task arguments: each parse produces a new DAG
   version) match this skill's parse-safety rule. `airflow config lint` checks config.
2. **Imports.**

   | 2.x import | 3.x import |
   | --- | --- |
   | `airflow.decorators.{dag,task,task_group,setup,teardown}` | `airflow.sdk.*` |
   | `airflow.models.DAG`, `airflow.models.baseoperator.BaseOperator` | `airflow.sdk.DAG`, `airflow.sdk.BaseOperator` |
   | `airflow.models.Variable`, `airflow.models.Connection` | `airflow.sdk.Variable`, `airflow.sdk.Connection` |
   | `airflow.hooks.base.BaseHook`, `airflow.sensors.base.BaseSensorOperator` | `airflow.sdk.BaseHook`, `airflow.sdk.BaseSensorOperator` |
   | `airflow.utils.task_group.TaskGroup`, `airflow.utils.context.Context` | `airflow.sdk.TaskGroup`, `airflow.sdk.Context` |
   | `airflow.datasets.Dataset` / `DatasetAlias` | `airflow.sdk.Asset` / `AssetAlias` |
   | `airflow.operators.bash.BashOperator`, `airflow.operators.python.PythonOperator`, `ExternalTaskSensor`, `FileSensor` | `airflow.providers.standard.*` (add `apache-airflow-providers-standard`) |

   Legacy paths work with deprecation warnings on 3.x and will be removed. The
   standard provider installs on 2.x too, so move those imports before the major upgrade.
   `CronDataIntervalTimetable`/`CronTriggerTimetable` import from `airflow.sdk` on 3.2+
   (`airflow.timetables.*` on earlier 3.x).
3. **Scheduling semantics.** `catchup_by_default` and `create_cron_data_intervals` default
   to `False`. A bare cron/preset string becomes `CronTriggerTimetable`: runs fire at the
   tick with `data_interval_start == data_interval_end`, and `ds`/`ts` shift. Where logic
   needs a contiguous window (dbt `--vars`, partitioned reads), pass
   `CronDataIntervalTimetable("0 1 * * *")` explicitly or set
   `create_cron_data_intervals=True` before upgrading; flipping it later skips one run.
   Do not assume a manual run's `data_interval` equals the supplied `logical_date`.
4. **Context.** Removed keys: `execution_date`, `prev_*`, `next_*`, `tomorrow_*`,
   `yesterday_*`; also `conf` and `dag_run.external_trigger`. For `logical_date=None` runs
   and the `xcom_pull()` default, see Airflow 3 Traps in SKILL.md.
5. **No metadata-DB access from tasks.** Remove ORM/session imports; use
   `airflow.sdk` `Variable`/`Connection`, `get_current_context()`, or the REST API through
   `apache-airflow-client` (`/api/v2`; `/api/v1` is gone). A `PostgresHook` against the
   metadata DB is a documented not-recommended workaround that will break.
6. **Removed features.** SubDAGs (use TaskGroups), SLAs/`sla_miss_callback` (Deadline
   Alerts, 3.1+), DAG/XCom pickling, `none_failed_or_skipped` (use
   `none_failed_min_one_success`), `dummy` trigger rule (use `always`), `fail_stop` (use
   `fail_fast`), core `EmailOperator` (smtp provider), `SequentialExecutor`, `--subdir`.
7. **`.airflowignore`.** Default syntax flips to `glob`; see Platform Model.
8. **Tests.** `DagBag` lives at `airflow.dag_processing.dagbag` on 3.2+ (absent on 3.0.6
   and 3.1.x, where it is `airflow.models.dagbag`); use the path the target version ships.

MWAA migration 2.x -> 3.x: start from a current 2.x environment (AWS's blog names 2.10.x;
Airflow's guide says upgrade to the latest 2.x, at least 2.7), build a new environment with
a new bucket, rebuild `requirements.txt` against the `constraints-<airflow>/constraints-3.12.txt`
file plus the standard provider, and test it with the uv recipe in SKILL.md or
`aws/amazon-mwaa-docker-images` (`./run.sh test-requirements`; PowerShell
`.\run.ps1 -Command test-requirements`). Pause a DAG in the old environment before enabling
it in the new one to avoid double runs, and set `catchup=True` only deliberately because a
clean environment has no run history.

## Sources

- Upgrading to Airflow 3 (breaking changes, ruff AIR rules, import map, xcom_pull, create_cron_data_intervals): https://airflow.apache.org/docs/apache-airflow/stable/installation/upgrading_to_airflow3.html
- Airflow release notes (3.0 removals table, config moves to `[dag_processor]`, `logical_date=None` for asset runs): https://airflow.apache.org/docs/apache-airflow/stable/release_notes.html
- Airflow timetables (trigger vs data-interval timetables, zero-width intervals): https://airflow.apache.org/docs/apache-airflow/stable/authoring-and-scheduling/timetable.html
- Airflow best practices (idempotent tasks, top-level code, Variables, DagBag test): https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html
- Airflow configuration reference (`dag_ignore_file_syntax`, `refresh_interval`): https://airflow.apache.org/docs/apache-airflow/stable/configurations-ref.html
- Ruff Airflow rules (AIR003, AIR301-AIR304, AIR311, AIR312, AIR321): https://docs.astral.sh/ruff/rules/#airflow-air
- Apache Airflow versions on Amazon MWAA (supported versions, minor-only upgrades, no multi-team mode): https://docs.aws.amazon.com/mwaa/latest/userguide/airflow-versions.html
- Python dependencies on Amazon MWAA (`pip3 install -r requirements.txt`, required `--constraint`): https://docs.aws.amazon.com/mwaa/latest/userguide/working-dags-dependencies.html
- Best practices for migrating from Airflow 2.x to 3.x on Amazon MWAA (blue/green, constraints, docker images): https://aws.amazon.com/blogs/big-data/best-practices-for-migrating-from-apache-airflow-2-x-to-apache-airflow-3-x-on-amazon-mwaa/
- Performance tuning for Apache Airflow on Amazon MWAA (v3 `dag_processor.*` options): https://docs.aws.amazon.com/mwaa/latest/userguide/best-practices-tuning.html
- aws/amazon-mwaa-docker-images (local MWAA-parity runtime): https://github.com/aws/amazon-mwaa-docker-images
