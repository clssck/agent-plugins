---
name: databricks-dbt-pipeline
description: >
  Build, deploy, and run end-to-end dbt pipelines on Databricks using
  Declarative Automation Bundles (DAB) and the Databricks CLI. Use when:
  dbt pipeline, dbt project, dbt Databricks, dbt-databricks, dbt task,
  dbt workflow, dbt job, dbt run, dbt seed, dbt test, dbt deps, dbt build,
  dbt models, dbt sources, dbt transformations, profiles.yml Databricks,
  dbt SQL warehouse, dbt serverless, dbt-core Databricks, dbt bundle,
  dbt-sql template, medallion dbt, dbt deploy, dbt schedule, dbt CI/CD,
  dbt DAB, dbt production, dbt development workflow.
---

# Databricks dbt Pipeline

Workflow skill for building end-to-end dbt-core pipelines on Databricks — from project scaffolding through DAB deployment and production scheduling.

## Prerequisites

- Databricks CLI v0.218.0+ installed and authenticated (see `databricks-cli-install` skill)
- Unity Catalog enabled on the target workspace
- A serverless or pro SQL warehouse available (for dbt SQL execution)
- Python 3.8+ with `dbt-core` and `dbt-databricks` installed locally for development
- Git repository for the dbt project (required for dbt job tasks)

## Concepts

**dbt on Databricks architecture:**
```
┌─────────────────────────────────────────────────────┐
│  Lakeflow Job                                       │
│  ┌───────────┐   ┌───────────┐   ┌───────────┐     │
│  │ dbt deps  │──▶│ dbt seed  │──▶│ dbt run   │     │
│  └───────────┘   └───────────┘   └───────────┘     │
│       dbt CLI compute                               │
│       (serverless or job cluster — runs Python)     │
│                        │                            │
│                        ▼                            │
│              SQL Warehouse                          │
│        (serverless or pro — runs SQL)               │
└─────────────────────────────────────────────────────┘
```

**Two compute layers in a dbt task:**
1. **dbt CLI compute** — runs the dbt Python process (command parsing, Jinja compilation, graph resolution). Uses serverless compute by default or a job cluster.
2. **SQL warehouse** — executes the generated SQL (CREATE TABLE, INSERT, MERGE, etc.). Must be serverless or pro.

**Recommended workflow:**
- **Development**: Run dbt locally against a SQL warehouse (use `dbt run`, `dbt test`)
- **Production**: Deploy as a dbt task in a Lakeflow Job via DAB

## Workflow

### Step 1: Scaffold the dbt Project

**Option A: Use the DAB `dbt-sql` template (recommended)**

```bash
databricks bundle init dbt-sql
```

Template prompts:
- `project_name`: e.g. `my_dbt_project`
- `personal_catalog`: Unity Catalog catalog for development (e.g. `dev_catalog`)
- `shared_catalog`: Catalog for staging/production (e.g. `prod_catalog`)
- `default_schema`: Schema for dbt models (e.g. `analytics`)

Generated structure:
```
my_dbt_project/
├── databricks.yml              # DAB config with dbt job resource
├── resources/
│   └── my_dbt_project.job.yml  # Job definition with dbt task
├── src/
│   ├── dbt_project.yml         # dbt project config
│   ├── profiles.yml            # Databricks connection profiles
│   ├── models/
│   │   └── example/
│   ├── seeds/
│   ├── tests/
│   └── macros/
├── .gitignore
└── README.md
```

**Option B: Create manually**

Create a standard dbt project:
```bash
pip install dbt-core dbt-databricks
dbt init my_dbt_project
```

Then wrap it in a DAB — see Step 4.

**⚠️ MANDATORY STOPPING POINT**: Confirm with the user which approach they prefer (DAB template vs manual) and which catalog/schema to target.

### Step 2: Configure profiles.yml

The `profiles.yml` tells dbt how to connect to Databricks.

**For local development (against a SQL warehouse):**
```yaml
my_dbt_project:
  target: dev
  outputs:
    dev:
      type: databricks
      method: http
      catalog: dev_catalog
      schema: analytics
      host: <workspace-host>.cloud.databricks.com
      http_path: /sql/1.0/warehouses/<warehouse-id>
      token: "{{ env_var('DATABRICKS_TOKEN') }}"
      threads: 4
```

**For production (DAB dbt task — token injected automatically):**
```yaml
my_dbt_project:
  target: databricks_job
  outputs:
    databricks_job:
      type: databricks
      method: http
      catalog: prod_catalog
      schema: analytics
      host: "{{ env_var('DBT_HOST', '<workspace-host>.cloud.databricks.com') }}"
      http_path: "{{ env_var('DBT_HTTP_PATH', '/sql/1.0/warehouses/<warehouse-id>') }}"
      token: "{{ env_var('DBT_ACCESS_TOKEN') }}"
      threads: 4
```

Key notes:
- `DBT_ACCESS_TOKEN` is **automatically injected** by the dbt task at runtime — do NOT hardcode tokens
- Use `dbt-databricks` adapter (not `dbt-spark`) — it is optimized for Databricks
- `catalog` requires Unity Catalog; omit for hive_metastore
- `threads` controls parallelism of dbt model execution

**⚠️ MANDATORY STOPPING POINT**: Confirm the workspace host, warehouse ID, catalog, and schema with the user before proceeding.

### Step 3: Build dbt Models

#### Source definitions (`models/sources.yml`)

```yaml
version: 2

sources:
  - name: raw
    catalog: raw_catalog
    schema: raw_schema
    tables:
      - name: orders
        description: Raw orders from source system
      - name: customers
        description: Raw customer records
```

#### Staging models (Silver — `models/staging/`)

```sql
-- models/staging/stg_orders.sql
WITH source AS (
    SELECT * FROM {{ source('raw', 'orders') }}
)

SELECT
    order_id,
    customer_id,
    order_date,
    status,
    amount
FROM source
WHERE order_id IS NOT NULL
```

```yaml
# models/staging/staging.yml
version: 2

models:
  - name: stg_orders
    description: Cleaned orders
    config:
      materialized: view
    columns:
      - name: order_id
        tests:
          - not_null
          - unique
```

#### Mart models (Gold — `models/marts/`)

```sql
-- models/marts/fct_orders.sql
WITH orders AS (
    SELECT * FROM {{ ref('stg_orders') }}
),
customers AS (
    SELECT * FROM {{ ref('stg_customers') }}
)

SELECT
    o.order_id,
    o.customer_id,
    c.customer_name,
    o.order_date,
    o.status,
    o.amount
FROM orders o
LEFT JOIN customers c ON o.customer_id = c.customer_id
```

```yaml
# models/marts/marts.yml
version: 2

models:
  - name: fct_orders
    description: Fact table for orders with customer details
    config:
      materialized: table
    columns:
      - name: order_id
        tests:
          - not_null
          - unique
      - name: customer_id
        tests:
          - not_null
          - relationships:
              to: ref('stg_customers')
              field: customer_id
```

#### dbt_project.yml configuration

```yaml
name: my_dbt_project
version: '1.0.0'
config-version: 2
profile: my_dbt_project

model-paths: ["models"]
seed-paths: ["seeds"]
test-paths: ["tests"]
macro-paths: ["macros"]

models:
  my_dbt_project:
    staging:
      +materialized: view
      +schema: staging
    marts:
      +materialized: table
      +schema: analytics
```

### Step 4: Wrap in a DAB for Deployment

If you used `databricks bundle init dbt-sql`, the DAB config is already generated. Otherwise, create these files:

**`databricks.yml`:**
```yaml
bundle:
  name: my_dbt_project

include:
  - resources/*.yml

targets:
  dev:
    mode: development
    default: true
    workspace:
      host: https://<workspace-host>.cloud.databricks.com
  prod:
    mode: production
    workspace:
      host: https://<workspace-host>.cloud.databricks.com
      root_path: /Shared/.bundle/prod/${bundle.name}
    run_as:
      service_principal_name: <sp-name>
```

**`resources/dbt_job.job.yml`:**
```yaml
resources:
  jobs:
    dbt_job:
      name: dbt_pipeline
      tasks:
        - task_key: dbt_transform
          dbt_task:
            project_directory: ../src
            commands:
              - dbt deps
              - dbt seed
              - dbt run
              - dbt test
            warehouse_id: <warehouse-id>
            catalog: prod_catalog
            schema: analytics
          environment_key: dbt_env
      environments:
        - environment_key: dbt_env
          spec:
            client: "1"
            dependencies:
              - dbt-databricks>=1.0.0,<2.0.0
      schedule:
        quartz_cron_expression: "0 0 8 * * ?"
        timezone_id: UTC
      tags:
        team: data-engineering
        project: dbt-pipeline
```

**CRITICAL — serverless compute:**
- dbt tasks on serverless compute do NOT support task-level `libraries`. You must use an `environments` block with `dependencies` instead.
- If you use a classic job cluster instead, task-level `libraries` with `pypi` packages work fine.

**CRITICAL — `project_directory` path:**
- The path is **relative to the resource YAML file**, not the bundle root. If your resource file is in `resources/` and your dbt project is in `src/`, use `../src`.

**dbt task configuration fields:**
| Field | Description |
|-------|-------------|
| `project_directory` | Relative path to dbt project root — **relative to the resource YAML file** |
| `commands` | Array of dbt commands to run in order (prefix each with `dbt`) |
| `warehouse_id` | SQL warehouse for executing generated SQL |
| `catalog` | Unity Catalog catalog override |
| `schema` | Schema override |
| `profiles_directory` | Path to custom `profiles.yml` (optional — defaults to project root) |
| `environment_key` | Environment to use for serverless (required if no `job_cluster_key`) |

**Using Git source instead of bundled files:**
```yaml
resources:
  jobs:
    dbt_job:
      name: dbt_pipeline
      git_source:
        git_url: https://github.com/org/dbt-project.git
        git_provider: gitHub
        git_branch: main
      tasks:
        - task_key: dbt_transform
          dbt_task:
            project_directory: .
            commands:
              - dbt deps
              - dbt seed
              - dbt run
              - dbt test
            warehouse_id: <warehouse-id>
          environment_key: dbt_env
      environments:
        - environment_key: dbt_env
          spec:
            client: "1"
            dependencies:
              - dbt-databricks>=1.0.0,<2.0.0
```

### Step 5: Validate and Deploy

```bash
databricks bundle validate
databricks bundle deploy -t dev
```

Run the dbt job:
```bash
databricks bundle run -t dev dbt_job
```

Check results:
```bash
databricks bundle run -t dev dbt_job --no-wait
databricks bundle open dbt_job
```

For production deployment:
```bash
databricks bundle deploy -t prod
```

See `databricks-automation-bundles` skill for full DAB lifecycle commands (validate, deploy, run, destroy, sync, plan).

### Step 6: Local Development Loop

Run dbt commands locally during development:

```bash
cd src/

dbt deps
dbt seed
dbt run --select staging
dbt test --select staging
dbt run --select marts
dbt test
dbt build  # runs seed + run + test in dependency order
```

Useful development commands:
```bash
dbt compile --select my_model        # Preview compiled SQL
dbt run --select my_model            # Run single model
dbt run --select staging+            # Run staging and all downstream
dbt test --select my_model           # Test single model
dbt run --full-refresh               # Recreate incremental models
dbt source freshness                 # Check source data freshness
dbt docs generate && dbt docs serve  # Generate and view documentation
```

### Step 7: Add dbt Tests

#### Generic tests (in YAML)

```yaml
# models/staging/staging.yml
models:
  - name: stg_orders
    columns:
      - name: order_id
        tests:
          - not_null
          - unique
      - name: status
        tests:
          - accepted_values:
              values: ['pending', 'shipped', 'delivered', 'cancelled']
```

#### Singular tests (in `tests/`)

```sql
-- tests/assert_positive_amounts.sql
SELECT order_id, amount
FROM {{ ref('fct_orders') }}
WHERE amount < 0
```

#### Source freshness

```yaml
# models/sources.yml
sources:
  - name: raw
    freshness:
      warn_after: {count: 12, period: hour}
      error_after: {count: 24, period: hour}
    loaded_at_field: _loaded_at
    tables:
      - name: orders
```

### Step 8: Multi-Task Workflows

Combine dbt with other task types in a single job:

```yaml
resources:
  jobs:
    etl_pipeline:
      name: full_etl_pipeline
      tasks:
        - task_key: ingest
          notebook_task:
            notebook_path: ../notebooks/ingest.py
        - task_key: transform
          depends_on:
            - task_key: ingest
          dbt_task:
            project_directory: ../src
            commands:
              - dbt deps
              - dbt run
              - dbt test
            warehouse_id: <warehouse-id>
          environment_key: dbt_env
        - task_key: report
          depends_on:
            - task_key: transform
          notebook_task:
            notebook_path: ../notebooks/generate_report.py
      environments:
        - environment_key: dbt_env
          spec:
            client: "1"
            dependencies:
              - dbt-databricks>=1.0.0,<2.0.0
      schedule:
        quartz_cron_expression: "0 0 6 * * ?"
        timezone_id: UTC
```

### Step 9: CI/CD with DAB

See `databricks-automation-bundles` skill for full CI/CD setup (GitHub Actions, OAuth M2M service principal auth). The pattern is:
- **PR**: `databricks bundle validate -t prod`
- **Merge to main**: `databricks bundle deploy -t prod --auto-approve`

## Stopping Points

- ✋ **Step 1**: Confirm DAB template vs manual setup, catalog, and schema
- ✋ **Step 2**: Confirm workspace host, warehouse ID, and connection details
- ✋ **Step 5**: If validation fails, fix errors before deploying
- ✋ **Step 5**: If run fails, diagnose before retrying

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `profiles.yml not found` | File not at expected path | Ensure `profiles.yml` is in the dbt project root or set `profiles_directory` in dbt task config |
| `Catalog not found` | UC not enabled or wrong catalog name | Verify catalog exists: `SHOW CATALOGS` on SQL warehouse |
| `dbt-databricks not installed` | Missing dependency in environment | Add `dbt-databricks>=1.0.0,<2.0.0` to `environments[].spec.dependencies` (serverless) or task `libraries` (classic cluster) |
| `Libraries field is not supported for serverless task` | Task-level `libraries` used with serverless compute | Move dependencies to `environments` block with `environment_key` — serverless does NOT support task-level `libraries` |
| `stat resources/src: no such file or directory` | Wrong `project_directory` path | Path is relative to the resource YAML file, not bundle root. Use `../src` if resource is in `resources/` and dbt project is in `src/` |
| `Missing required cluster or environment settings` | No compute specified for dbt task | Add `environment_key` (serverless) or `job_cluster_key` (classic) to the task |
| Token auth fails in production | Hardcoded or missing token | Use `{{ env_var('DBT_ACCESS_TOKEN') }}` — auto-injected by dbt task |
| SQL warehouse not found | Wrong warehouse ID or type | Only serverless and pro warehouses work; verify ID in warehouse settings |
| Python models fail | Python models need compute, not SQL warehouse | Python dbt models require all-purpose or job compute as the dbt target, not a SQL warehouse |
| `dbt deps` fails | No `packages.yml` or network issues | Create `packages.yml` in project root if using dbt packages; check compute has internet access |
| Slow dbt runs | Low thread count or small warehouse | Increase `threads` in profiles.yml; size up the SQL warehouse |
| Schema drift | Model changes not reflected | Run `dbt run --full-refresh` to rebuild incremental models |

## Cross-References

- **`databricks-automation-bundles`** — Full DAB lifecycle (validate, deploy, run, destroy, variables, permissions, CI/CD)
- **`databricks-cli-install`** — CLI installation and authentication (OAuth U2M, M2M, PAT)
- **`databricks-cost-optimization/sql-warehouses`** — SQL warehouse sizing and cost optimization
- **`databricks-etl-pyspark-notebooks`** — PySpark notebook ETL (alternative to dbt for Python-heavy transformations)

## Output

This skill produces:
- A scaffolded dbt project with models, tests, and profiles for Databricks
- A DAB-wrapped deployment with job definition, schedule, and target environments
- Validated and deployed dbt pipeline running on Databricks Lakeflow Jobs
- CI/CD configuration for automated validation and deployment
