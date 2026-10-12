# General Airflow Guide

Sanofi Airflow guidance for the shared MWAA platform, derived from the OneMesh "Airflow - how to guide" and child pages, plus reusable DAG standards and best-practice pages from other Sanofi Airflow spaces. Read by task: new DAG → Parse-Time Safety, DAG Configuration, TaskFlow API, Project and Repo Structure · orchestration → Cross-DAG Orchestration, Sensors, [`orchestrating-dbt.md`](skill://sanofi-airflow/references/orchestrating-dbt.md) for dbt · operations → Alerting, Access Control, CI/CD and Deployment, Troubleshooting · Airflow 3.x target or 2.x → 3.x move → Airflow 3 Migration.

## Source of Truth

- **Precedence:** repository files > examples here; call out any mismatch. Platform behavior (scheduler, parse cycle, MWAA sizing) → OneMesh guide. Cross-space DAG standards = supporting evidence when a pattern recurs, never grounds to overwrite a repo's documented local contract.
- **Placeholders:** all project names, `dag_id`s, folders, roles, schemas, warehouses, IAM group names, paths, dates in examples, unless explicitly marked as a Sanofi platform fact. Adapt to the target repo and current platform guidance.

Core references, base `https://sanofi.atlassian.net/wiki/spaces/OneMesh/pages/`:

| Page | ID |
|---|---|
| `Airflow - how to guide` | 66306933380 |
| `1. DAG Authoring Best Practices` | 66486699835 |
| `2. Deployment & Project Structure` | 66485783031 |
| `3. Performance & Troubleshooting` | 66486175813 |
| `4. Platform Architecture` | 66480121490 |
| `5. FAQ & Quick Reference` | 66487551192 |
| global `.airflowignore` | 66531364329 |

A `2026-06-23` draft set (page 67178465278) tracks the move to dedicated-tenant MWAA on Airflow 3.2.1.

Additional standards sources:

- `Airflow DAG Standards` (USDFPAA space) `67161393536`: mandatory file/naming rules, explicit DAG-config checklist, `orchestration/dags` + `utils/` layout, Dataset cross-DAG scheduling, custom failure email, ServiceNow/TACO incidents. Reuse the generic rules; `paa/caa/saa` `dag_id` prefixes and role names = local examples.
- `Airflow Best Practices` (USDFMSPA01 space) `66921496793`: Python/PEP 8 discipline, pull-request DAG checklist, `@dag` decorator standard, central `DagBuilder`, task timeouts, tags, atomic tasks.

## Platform Model

Sanofi runs Airflow on AWS MWAA, two operating models:

| Model | Shape |
|---|---|
| Shared central MWAA | Multi-tenant; 120-180+ projects across DEV/UAT/PROD; Airflow 2.11. Scheduler imports every `.py` under `dags/` every 30-60s → one project's bad DAG degrades the platform. Central package versions = platform facts, not changeable per project |
| Dedicated tenant MWAA | Tenant-owned, provisioned from the MWAA blueprint; Airflow 3.2.1; per-tenant sizing, private UI mode, isolated scheduler/workers/metadata DB/DAG bucket. 2.11 only for a migration window when step one is tenant isolation without a version change |

**Confirm the environment's Airflow major version before writing version-sensitive code.**

**Ignore-file syntax is read from config, never inferred from version.** `core.dag_ignore_file_syntax` (`AIRFLOW__CORE__DAG_IGNORE_FILE_SYNTAX`) = `regexp` | `glob`. Airflow default: `glob` from 3, `regexp` before; overridable. Check the live value before writing a project `.airflowignore`. NEVER copy an ignore file written for one syntax into an environment configured for the other.

### Amazon MWAA facts (AWS docs, checked 2026-10)

- **Supported versions:** 3.3.1, 3.2.1, 3.0.6, 2.11.2, 2.11.0, older 2.7-2.10.
- **Python:** 2.11 and 3.x → 3.12; 2.10 and earlier → 3.11.
- **Auth:** Flask-AppBuilder stays on 3.x (no Simple Auth switch). Multi-team mode unsupported.
- **Upgrades:** MWAA does in-place minor upgrades only ⇒ 2.x → 3.x = new environment (blue/green), not an update.
- **Sanofi facts:** 2.11 shared, 3.2.1 dedicated. Confirm the live version before relying on it.

### Components and deployment

MWAA components (Terraform-provisioned): Scheduler, Workers (Celery), WebServer, Metadata DB, S3 DAG bucket, Secrets Manager. Deploy = sync to the S3 `dags/` prefix; NEVER edit the environment directly.

### Scheduler facts

- **Re-parse cadence:** existing files ~60s. A newly added file appears only after one `dag_dir_list_interval` (shared platform: ~5 min DEV, ~10 UAT, ~15 PROD) ⇒ a missing brand-new DAG is often just not scanned yet.
- **Airflow 3.x config moves:** `dag_dir_list_interval` → `[dag_processor] refresh_interval`; `min_file_process_interval`, `parsing_processes`, `dag_file_processor_timeout` also move from `[scheduler]`/`[core]` to `[dag_processor]` (`airflow config lint` lists renames). An `AIRFLOW__SCHEDULER__*` override written for 2.11 does nothing on 3.x.
- **Parse limits:** hard import timeout 180s per file (`dagbag_import_timeout`); budget well under 30s.
- **Workers:** autoscale (`worker_autoscale=16,4`); `task_acks_late=True` re-queues killed tasks ⇒ retries mandatory.
- **Eviction:** DAG unseen ~40 min → evicted from the UI.

### Packages

- **Shared platform pre-installs** a curated set: dbt-core, dbt-snowflake, dag-factory, Snowflake connector/snowpark, `sanofi-airflow-utils`, common providers. NEVER reinstall or pin them in a project; request additions/version changes via PR to the MWAA provisioning repo's `requirements.txt`. Versions drift: verify the live `requirements.txt`/constraints, never hardcode versions in a DAG.
- **Dedicated tenants own their `requirements.txt`.** MWAA installs it with `pip3 install -r` plus an Airflow constraints file (`--constraint` line required from Airflow 2.7.2); install fails on any pin the constraints reject. Prove locally first: uv recipe in SKILL.md (Local Environment); MWAA parity → `./run.sh test-requirements` from `aws/amazon-mwaa-docker-images`.

## Parse-Time Safety

Highest-value rule on the shared platform; first review item.

**NEVER call `Variable.get()`, `Connection.get()`, or any secret lookup at module level** (outside a task function). Module-level code runs every scheduler parse cycle: one top-level `Variable.get()` → thousands of Secrets Manager/metadata-DB calls per minute across tenants, ~100-500ms added per parse, and the whole DAG fails to parse if the variable is missing.

| Method | At parse time? | DB call? | Use for |
|---|---|---|---|
| `Variable.get()` at module level | Yes | Yes | Never |
| `{{ var.value.key }}` (Jinja) | No (execution) | Yes | Task parameters, commands; preferred for simple params |
| `Variable.get()` inside a task | No (execution) | Yes | Complex logic inside tasks |
| `os.environ.get("KEY", "default")` | Yes | No | DAG-level config: `dag_id` suffix, schedule, static config; safe at module level |

- **Allowed at module level:** `from airflow.decorators import dag, task`, operator imports, DAG/task definitions, lightweight imports (`os`, `yaml`), static literals.
- **Inside task functions:** everything else — `import pandas`, `import snowflake.connector`, DB connections, API calls, heavy computation.
- **Shared config:** prefer `sanofi-airflow-utils` `ConfigLoader` (Configuration and Secrets) over ad-hoc `Variable.get()`.

## Project and Repo Structure

Many Sanofi repos keep dbt under `transformation/` and orchestration under `orchestration/`. Inspect the repo root before assuming the DAG root. Common `orchestration/` layout:

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

- **Upload only what the scheduler needs.** Extra files in S3 `dags/` slow scans and waste storage (SHOULD).
- **Global `.airflowignore`:** shipped at the `dags/` root; already excludes `transformation/`, `dbt_packages/`, `seeds/`, `macros/`, non-Python files (`.sql`, `.yml`, `.csv`, `.json`, ...), build artifacts, IDE/VCS folders. Add a project-level `.airflowignore` only for custom exclusions, matching the environment's configured `dag_ignore_file_syntax`.

## Naming

- **One DAG per file;** filename = `dag_id` exactly, so an alert names the file.
- **Lowercase `snake_case` only:** no capitals, no dots (dots break Python imports and DAG parsing).
- **`dag_id`:** stable prefix + entity, `<prefix>_<entity>` (repos vary; some use `paa/caa/saa` domain prefixes). Follow the repo's convention.
- **`task_id`:** verb-first, one unit of work: `extract_*`, `validate_*`, `load_*`, `run_dbt_*`. Should read as a pipeline so a failure names what broke.
- **Owner, emails, tags, schedules:** from shared constants/helpers, NEVER inline literals.

## DAG Configuration

Every DAG MUST set these explicitly; implicit defaults cause surprise backfills and stuck runs.

| Setting | Standard | Why |
|---|---|---|
| `start_date` | Static `datetime(...)`; never `datetime.now()` | Dynamic start dates break scheduling/backfills |
| `catchup` | `False` unless a backfill is genuinely intended | Stops a run storm when a paused DAG is enabled |
| `schedule` | Explicit cron/preset; `None` for trigger-only | Removes ambiguity about when it runs |
| `max_active_runs` | Deliberate; `1` for any stateful load | Prevents two runs racing on the same target |
| `max_active_tasks` | Set on wide DAGs (e.g. `16`) | Stops one DAG flooding shared worker slots |
| `dagrun_timeout` | Set on anything that can hang | A stuck run MUST NOT hold a slot indefinitely |
| `tags` | From a shared helper; team, priority, schedule | Findable in a crowded UI |
| `default_args` | Shared dict; `email_on_failure=False`, `on_failure_callback` set | Consistent, predictable failure behavior |

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

- **Retries and timeouts are mandatory.** Celery workers can be OOM-killed (SIGKILL); `task_acks_late=True` re-queues killed tasks ⇒ without retries a killed task = permanent failure.
- **Timeout ordering:** `execution_timeout` > platform `killed_task_cleanup_time` (120s); `dagrun_timeout` > longest legitimate run.
- **Email:** `email_on_failure`/`email_on_retry` stay `False`; alerting = custom `on_failure_callback`, not Airflow's built-in email.

## TaskFlow API

`@dag`/`@task` = recommended authoring style: less boilerplate, data via return values (implicit XCom) instead of manual push/pull.

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

### Run state and failure masking

DAG run state comes from leaf tasks (no downstream). A sole `all_done` leaf runs after any upstream outcome and, on success, marks the run `success` even when `run_dbt` failed. Fix: give cleanup a sibling leaf with default `all_success` (`mark_complete`) → becomes `upstream_failed`, fails the run, cleanup still executes. Alternative when a real setup task exists: `as_setup()`/`as_teardown()`; teardowns are ignored for run state by default (`on_failure_fail_dagrun=True` changes that for the teardown itself).

### Task design

- **Idempotent** so retries and backfills are safe: UPSERT/MERGE, not INSERT; read and write one partition keyed on `data_interval_start` (NEVER "latest"); NEVER `datetime.now()` for business logic in a task.
- **Decorators:** `@task` (replaces `PythonOperator`) · `@task.bash` (returns the command string; replaces `BashOperator`) · `@task.short_circuit` (skip downstream) · `@task.branch` (choose a path).
- **Atomic tasks:** one action each → retries, logging, recovery stay granular.
- **Central builder:** prefer a `DagBuilder`/`dag_utils` factory (`get_dag`, `get_python_operator`, `get_dbt_operator`) when the repo provides one → consistent operator defaults.
- **Docs:** set `doc_md` so the DAG's purpose shows in the UI.

## Configuration and Secrets

Prefer `sanofi-airflow-utils` (pre-installed) over ad-hoc `Variable.get()` and hardcoded environment dicts. `ConfigLoader` reads layered YAML (`config/common.yml` + `config/<env>.yml`) and maps logical secret names to Airflow Variable / Secrets Manager keys.

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

- **`get_config()`:** reads YAML, zero DB calls.
- **`get_secret()`:** `ConfigLoader()` construction does not resolve secrets, but every `get_secret()` call runs `Variable.get()` immediately. `ConfigLoader()` at module level = safe; `get_secret()` at module level = parse-time secret lookup. Call it inside a task.
- **Layout:** environment-specific values (roles, databases, warehouses, users) → `config/<env>.yml`; shared values → `config/common.yml`.

| Store | Holds | Access |
|---|---|---|
| Airflow Variables | Project config, flags, toggles | `{{ var.value.key }}` or `ConfigLoader` |
| Airflow Connections | Database credentials, API endpoints | `conn_id` on operator/hook; secrets never in DAG code |
| AWS Secrets Manager | Anything sensitive; MWAA fetches transparently | Via secrets backend |

On the shared platform, CI sync maps GitHub `MWAA_*` secrets into Secrets Manager under a fixed path convention (`airflow/variables/emea/<env>/<project>/<KEY>` and `.../connections/...`); the MWAA secrets backend reads them automatically ⇒ never configure the backend yourself.

## Cross-DAG Orchestration

Run a DAG after another completes, including DAGs of other projects/repos, with Datasets (data-aware scheduling), not hardcoded triggers. Airflow 3.x: Datasets → Assets (`from airflow.sdk import Asset`; `airflow.datasets.Dataset` deprecated).

- **Mechanism:** upstream DAG publishes the asset on finish; downstream DAGs schedule off it. Upstream never imports, names, or triggers downstream ⇒ projects stay decoupled.
- **Prefer Datasets/Assets over `TriggerDagRunOperator` and `ExternalTaskSensor`.**
- **Asset-triggered runs:** `logical_date=None`, no data interval (Airflow 3 Migration).

## Sensors and Long Waits

Sensors hold a worker slot while waiting: expensive on a shared environment.

| Mode | Behavior | Use when |
|---|---|---|
| `poke` (default) | Holds a worker slot continuously | Short waits (<5 min) |
| `mode="reschedule"` | Releases and re-acquires the slot between pokes | Long waits (>5 min) |
| `deferrable=True` | Uses the triggerer, no worker slot | Best for long waits (async support) |

Set `poke_interval`, `timeout`, `execution_timeout` explicitly. Prefer deferrable sensors/operators where supported; else `mode="reschedule"` for long waits.

## Dynamic DAG Generation

Loop-generated DAGs are dangerous when real work runs at parse time. NEVER query a database or call `Variable.get()` at module level to build DAGs. Drive generation from a static YAML config committed to the repo, or use `dag-factory` (installed on the platform) to generate DAGs from YAML with no Python.

## Running dbt from Airflow

Dominant Sanofi orchestration use case; own reference: [`orchestrating-dbt.md`](skill://sanofi-airflow/references/orchestrating-dbt.md) (choosing/wiring `BashOperator` + `dbt_run.sh` or typed `DbtClient`, logs/artifacts, backfills, run vars). dbt models/SQL/tests → dbt skill.

## Alerting and Failure Handling

Every production DAG MUST alert on failure with actionable context (which task, why, log link) via a shared `on_failure_callback`, not per-task `email_on_failure=True`. Common Sanofi pattern: callback sends a custom failure email and, for production failures needing human action, auto-creates a ServiceNow incident through the TACO architecture.

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

- **A failure callback MUST NEVER raise.** Catch and log internally so the original task error and other callbacks still propagate.
- **Gate incident creation to production.**
- **`trigger_rule="all_done"` cleanup/summary task:** for work that MUST run regardless of upstream outcome (resource cleanup, failure summaries). NEVER the sole DAG leaf (marks the run `success` after upstream failure); pair with a default-rule leaf as in the TaskFlow example.

## Access Control

Set `access_control` on DAGs so the right MWAA roles can view/edit. Role names MUST match the IAM role mappings configured by the platform team.

```python
ACCESS_CONTROL = {
    "MWAA_<PROJECT>_USERS": ["can_read"],
    "MWAA_<PROJECT>_DEVELOPERS": ["can_read", "can_edit"],
}
```

### DAG unit tests

Live under a `unit_tests/` directory excluded from DAG parsing. Cover: DAG imports with no errors, no cycles, `default_args`/tags/timeouts set, custom builder logic. Local commands and order: Validation Ladder in SKILL.md. **`airflow tasks test` and `airflow dags test` execute task code** → only against local/containerized Airflow with DEV connections.

## CI/CD and Deployment

GitHub Actions under `.github/workflows/`:

| Workflow | Role |
|---|---|
| `airflow-sync.yml` | Sync DAGs/code to MWAA |
| `airflow-sync-secrets.yml` | Sync connections/variables/secrets |
| `autodoc.yml` | Generate docs |
| `changelog.yml` | Release notes on merge |

Sanofi also publishes reusable workflows/actions (e.g. `reusable-airflow-sync` workflow, `airflow-validate` action): prefer them over hand-rolled sync logic.

- **Validate in CI before deploy.** Load every DAG through Airflow's `DagBag` in an ephemeral environment (SQLite, dummy Variables for anything read at import time); fail the build on import errors. Catches module-level `Variable.get()`, missing variables, heavy-import timeouts before they reach the shared scheduler.
- **Deploy step:** sync the repo (typically `orchestration/` and `transformation/`) to `s3://<mwaa-bucket>/dags/<project>/`; approval gate before PROD; orphan-file cleanup (`delete_from_s3`).
- **NEVER upload** `.xlsx`/`.docx`/`__pycache__` to the DAGs bucket. Data files → data bucket or dbt seeds.

### Dedicated tenants

- **Start from** blueprint `tenant-skeleton/`.
- **Endpoints:** `SERVICE` endpoint management is the default (MWAA creates its own PrivateLink endpoints). UI access mode is explicit: `aws_iam` | `sanofi_network` | `ad_group`.
- **Bootstrap = CI-managed sync.** DAGs, `dags/constraints.txt`, `dags/ca-bundle.pem` sync without an MWAA update; `requirements.txt`, `startup.sh`, `plugins.zip` trigger an environment update only when their S3 object version changes.
- **Tags:** generate mandatory CE tags with the `tags_mandatory_tags` Terraform module; NEVER hand-write `CE_*` tags.

### Dedicated MWAA sizing

| Env | Schedulers | Class / workers |
|---|---|---|
| `dev`/`uat`/`prod` | ≥ 2 | — |
| `sbx` (disposable) | 1 | — |
| normal `dev`/`uat` start | — | `mw1.small`, `min_workers=1`, `max_workers=5` |
| first prod baseline (safer) | 2 | `mw1.medium`, `max_workers=10` |

Queues back up → add workers. Tasks need more CPU/memory or scheduler headroom → raise environment class.

### Deployment gates (shared MWAA)

- No `Variable.get()` / secret / heavy import at module level: `grep` `Variable\.get|get_secret` over `orchestration/dags/**/*.py`; every hit MUST sit inside a function or Jinja template.
- `default_args` sets `retries` and `execution_timeout`; DAG sets `dagrun_timeout`.
- `dag_id` includes the environment (via `os.environ.get("MWAA_ENV")`).
- Config from `ConfigLoader`/YAML, not hardcoded env dicts.
- File parses fast locally (Validation Ladder step 1, target <30s); CI DagBag validation clean.
- `access_control`, `max_active_runs`, `max_active_tasks` set.

## Troubleshooting

Scheduler loop: scan S3 `dags/` → parse (import each `.py`; module-level code runs here) → serialize to metadata DB → schedule/queue tasks → evict DAGs not parsed within ~40 min. A DAG that cannot parse in time disappears from the UI.

| Symptom | Likely cause | Fix |
|---|---|---|
| DAG missing from UI | Import error | Search CloudWatch `DAGProcessing` for `Failed to import: <file>`; fix the Python error |
| DAG missing from UI | Parse timeout (>180s) | Move heavy imports / `Variable.get()` inside tasks |
| DAG missing from UI | Missing Variable | Search `Failed to retrieve secret`; create it or remove the top-level `Variable.get()` |
| DAG missing from UI | Brand-new file not scanned yet | Wait one `dag_dir_list_interval` (~5-15 min by env) before assuming a defect |
| DAG missing from UI | Stale eviction (>40 min) | Confirm the file is valid Python and parses quickly |
| Task exit 127 | Command not found (bash 127) | Check command name, `PATH`, and that the binary (e.g. `dbt`) is installed in the runtime |
| Task exit 137 / Signal 9 | SIGKILL (128+9); often OOM | Check `Worker` logs for OOM or another kill cause first; then chunk/stream, cap memory-heavy tasks with a `pool`, add retries |
| Task logs missing | Worker SIGKILLed before flushing | Check CloudWatch `Worker` logs directly by task/run id |

- **Parse cost:** diagnose locally with Validation Ladder step 1 (SKILL.md).
- **CloudWatch log groups:** `airflow-<env>-DAGProcessing` (parse errors/timeouts) · `-Scheduler` (stale DAGs/evictions) · `-Task` (task execution) · `-Worker` (OOM/celery) · `-WebServer`.
- **Metrics (healthy / critical):** Scheduler CPU <60% / >80% · Worker CPU <70% / >90% · Queued Tasks <50 / >200 · Stale DAGs 0 healthy.
- **Highest-impact, lowest-effort fixes:** move `Variable.get()` and heavy imports into tasks; adopt `ConfigLoader`; set `max_active_tasks`; use `pool`s for memory-heavy work.

## Airflow 3 Migration

Applies when a DAG targets a 3.x tenant or is being prepared to leave the shared 2.11 platform. Review order: lint → imports → scheduling semantics → DB access → config → requirements.

1. **Lint first.** `uvx ruff@latest check <dags_dir> --select AIR301,AIR302` (ruff ≥ 0.13.1) flags removals and provider moves. `--fix` applies safe fixes; `--unsafe-fixes` also rewrites import paths (enable `F401` to drop leftovers). `AIR311`/`AIR312` = still working but deprecated. Preview rules `AIR003` (`Variable.get()` outside a task) and `AIR304` (`datetime.now()`/random in DAG or task arguments: each parse produces a new DAG version) match this skill's parse-safety rule. `airflow config lint` checks config.
2. **Imports.**

   | 2.x import | 3.x import |
   |---|---|
   | `airflow.decorators.{dag,task,task_group,setup,teardown}` | `airflow.sdk.*` |
   | `airflow.models.DAG`, `airflow.models.baseoperator.BaseOperator` | `airflow.sdk.DAG`, `airflow.sdk.BaseOperator` |
   | `airflow.models.Variable`, `airflow.models.Connection` | `airflow.sdk.Variable`, `airflow.sdk.Connection` |
   | `airflow.hooks.base.BaseHook`, `airflow.sensors.base.BaseSensorOperator` | `airflow.sdk.BaseHook`, `airflow.sdk.BaseSensorOperator` |
   | `airflow.utils.task_group.TaskGroup`, `airflow.utils.context.Context` | `airflow.sdk.TaskGroup`, `airflow.sdk.Context` |
   | `airflow.datasets.Dataset` / `DatasetAlias` | `airflow.sdk.Asset` / `AssetAlias` |
   | `airflow.operators.bash.BashOperator`, `airflow.operators.python.PythonOperator`, `ExternalTaskSensor`, `FileSensor` | `airflow.providers.standard.*` (add `apache-airflow-providers-standard`) |

   Legacy paths work with deprecation warnings on 3.x, to be removed. The standard provider installs on 2.x too ⇒ move those imports before the major upgrade. `CronDataIntervalTimetable`/`CronTriggerTimetable` import from `airflow.sdk` on 3.2+ (`airflow.timetables.*` on earlier 3.x).
3. **Scheduling semantics.** `catchup_by_default` and `create_cron_data_intervals` default `False`. Bare cron/preset string → `CronTriggerTimetable`: runs fire at the tick with `data_interval_start == data_interval_end`; `ds`/`ts` shift. Where logic needs a contiguous window (dbt `--vars`, partitioned reads) → pass `CronDataIntervalTimetable("0 1 * * *")` explicitly, or set `create_cron_data_intervals=True` before upgrading (flipping it later skips one run). Do not assume a manual run's `data_interval` equals the supplied `logical_date`.
4. **Context.** Removed keys: `execution_date`, `prev_*`, `next_*`, `tomorrow_*`, `yesterday_*`, `conf`, `dag_run.external_trigger`. `logical_date=None` runs and the `xcom_pull()` default → Airflow 3 Traps in SKILL.md.
5. **No metadata-DB access from tasks.** Remove ORM/session imports; use `airflow.sdk` `Variable`/`Connection`, `get_current_context()`, or the REST API via `apache-airflow-client` (`/api/v2`; `/api/v1` gone). `PostgresHook` against the metadata DB = documented not-recommended workaround that will break.
6. **Removed features.** SubDAGs (→ TaskGroups) · SLAs/`sla_miss_callback` (→ Deadline Alerts, 3.1+) · DAG/XCom pickling · `none_failed_or_skipped` (→ `none_failed_min_one_success`) · `dummy` trigger rule (→ `always`) · `fail_stop` (→ `fail_fast`) · core `EmailOperator` (→ smtp provider) · `SequentialExecutor` · `--subdir`.
7. **`.airflowignore`.** Default syntax flips to `glob`; see Platform Model.
8. **Tests.** `DagBag` at `airflow.dag_processing.dagbag` on 3.2+; absent on 3.0.6 and 3.1.x, where it is `airflow.models.dagbag`. Use the path the target version ships.

### MWAA 2.x → 3.x

- **Source:** start from a current 2.x environment (AWS's blog names 2.10.x; Airflow's guide: latest 2.x, at least 2.7).
- **Build** a new environment with a new bucket; rebuild `requirements.txt` against `constraints-<airflow>/constraints-3.12.txt` plus the standard provider.
- **Test** with the uv recipe in SKILL.md or `aws/amazon-mwaa-docker-images` (`./run.sh test-requirements`; PowerShell `.\run.ps1 -Command test-requirements`).
- **Cutover:** pause a DAG in the old environment before enabling it in the new one → no double runs. `catchup=True` only deliberately: a clean environment has no run history.

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
