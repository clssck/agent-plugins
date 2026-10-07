---
name: databricks-automation-bundles
description: "Create, configure, deploy, and run Databricks Declarative Automation Bundles (DAB, formerly Databricks Asset Bundles). Use when: initializing bundle projects, defining jobs, pipelines, Python wheels, Scala JARs, MLOps stacks, or Databricks apps as code, deploying bundles to workspaces, running bundle workflows, validating configurations, generating bundle config from existing resources, binding resources, creating custom templates, or managing the full bundle lifecycle (init → validate → deploy → run → destroy). Triggers: bundle, DAB, asset bundle, declarative automation bundle, bundle init, bundle deploy, bundle run, bundle validate, bundle destroy, databricks.yml, job bundle, pipeline bundle, python wheel bundle, scala jar bundle, mlops stacks, bundle template, CI/CD databricks, infrastructure as code databricks."
---

# Databricks Declarative Automation Bundles (DAB)

Workflow skill for creating, configuring, deploying, and running Declarative Automation Bundles (formerly Databricks Asset Bundles) using the Databricks CLI.

## Prerequisites

- Databricks CLI v0.218.0+ installed and authenticated (see `databricks-cli-install` skill)
- Remote workspace must have workspace files enabled (Databricks Runtime 11.3 LTS+)
- For pipelines: CLI v0.283.0+
- For Python projects: `uv` installed (for tests and dependency management)
- For Scala projects: JDK 17, sbt, IntelliJ IDEA
- Unity Catalog enabled (for most templates)

## Concepts

A bundle is an **infrastructure-as-code (IaC) project** that packages:
- Source files (notebooks, Python files, Scala files)
- Resource definitions (jobs, pipelines, dashboards, model serving endpoints, experiments, registered models, etc.)
- Workspace configuration and deployment targets
- Build artifacts (Python wheels, JARs)
- Unit and integration tests

The core configuration file is `databricks.yml` at the project root. Resource definitions live in `resources/*.yml`. Source code lives in `src/`.

**Bundle lifecycle:**
```
init → develop → validate → deploy → run → destroy
```

**Key configuration structure:**
```yaml
bundle:
  name: <bundle-name>            # Required

include:
  - resources/*.yml              # Additional config files

artifacts:
  <name>:
    type: whl                    # Build artifacts (Python wheels, JARs)
    build: <build-command>
    path: .

variables:
  <name>:
    description: <text>
    default: <value>

workspace:
  host: <workspace-url>

permissions:
  - level: CAN_MANAGE
    group_name: <group>

resources:
  jobs:
    <job-key>: ...
  pipelines:
    <pipeline-key>: ...
  dashboards:
    <dashboard-key>: ...
  experiments:
    <experiment-key>: ...
  registered_models:
    <model-key>: ...
  model_serving_endpoints:
    <endpoint-key>: ...
  schemas:
    <schema-key>: ...
  volumes:
    <volume-key>: ...
  clusters:
    <cluster-key>: ...
  apps:
    <app-key>: ...
  quality_monitors:
    <monitor-key>: ...
  alerts:
    <alert-key>: ...

targets:
  dev:
    mode: development
    default: true
    workspace:
      host: <dev-workspace-url>
  prod:
    mode: production
    workspace:
      host: <prod-workspace-url>
      root_path: /Shared/.bundle/prod/${bundle.name}
    run_as:
      service_principal_name: <sp-name>
```

## Workflow

### Step 1: Identify the Goal

Determine what the user wants to bundle:

| Goal | Route |
|------|-------|
| Create a job (notebook, Python, SQL) | Job Bundle |
| Create an ETL pipeline (Lakeflow/DLT) | Pipeline Bundle |
| Build & deploy a Python wheel | Python Wheel Bundle |
| Build & deploy a Scala JAR | Scala JAR Bundle |
| Set up MLOps with best practices | MLOps Stacks Bundle |
| Create from scratch (no template) | Manual Bundle |
| Create a custom reusable template | Custom Template |
| Import an existing workspace resource | Generate & Bind |

**⚠️ MANDATORY STOPPING POINT**: If the user's goal is ambiguous, ask which type of bundle they want before proceeding.

### Step 2: Initialize the Bundle

#### Option A: Use a Default Template

```bash
databricks bundle init
```

This presents an interactive menu of available templates:

| Template | Description |
|----------|-------------|
| `default-python` | Python project with job, pipeline, and/or Python wheel |
| `default-scala` | Scala JAR project for serverless compute |
| `default-sql` | SQL queries running on SQL warehouse |
| `default-minimal` | Empty bundle with only required files |
| `dbt-sql` | dbt-core project with bundle deployment |
| `mlops-stacks` | Full MLOps project (training, inference, monitoring) |
| `pydabs` | Python-based bundle configuration (instead of YAML) |

To skip the interactive menu and use a specific template directly:
```bash
databricks bundle init default-python
databricks bundle init default-scala
databricks bundle init mlops-stacks
```

#### Option B: Initialize from a Git Repo or Custom Template

```bash
databricks bundle init https://github.com/org/custom-template
databricks bundle init /local/path/to/template
databricks bundle init https://github.com/org/repo --branch main
```

#### Option C: Create Manually (No Template)

1. Create a project directory
2. Create `databricks.yml` at the root
3. Add source files (notebooks, Python, etc.)
4. Add resource definitions

### Step 3: Develop the Bundle

#### Job Bundle (Notebook Task)

The default-python template generates:
```
my_project/
├── databricks.yml
├── pyproject.toml
├── resources/
│   └── sample_job.job.yml
├── src/
│   └── sample_notebook.ipynb
└── tests/
```

**Job resource definition** (`resources/sample_job.job.yml`):
```yaml
resources:
  jobs:
    my_job:
      name: my_job
      tasks:
        - task_key: notebook_task
          notebook_task:
            notebook_path: ../src/sample_notebook.ipynb
        - task_key: second_task
          depends_on:
            - task_key: notebook_task
          notebook_task:
            notebook_path: ../src/another_notebook.py
      job_clusters:
        - job_cluster_key: my_cluster
          new_cluster:
            spark_version: 13.3.x-scala2.12
            node_type_id: Standard_DS3_v2
            num_workers: 1
      schedule:
        quartz_cron_expression: '0 0 9 * * ?'
        timezone_id: UTC
      parameters:
        - name: my_param
          default: default_value
```

**Job with multiple task types:**
```yaml
resources:
  jobs:
    multi_task_job:
      name: multi_task_job
      tasks:
        - task_key: notebook_task
          notebook_task:
            notebook_path: ../src/notebook.py
        - task_key: python_task
          depends_on:
            - task_key: notebook_task
          python_wheel_task:
            entry_point: main
            package_name: my_package
          libraries:
            - whl: ../dist/*.whl
        - task_key: sql_task
          sql_task:
            query:
              query_id: <query-id>
            warehouse_id: <warehouse-id>
        - task_key: spark_jar_task
          spark_jar_task:
            main_class_name: com.example.Main
          libraries:
            - jar: ../target/*.jar
```

#### Pipeline Bundle (Lakeflow / DLT)

Initialize using the dedicated pipeline command:
```bash
databricks pipelines init
```

This generates:
```
my_pipeline_project/
├── databricks.yml
├── pyproject.toml
├── resources/
│   ├── my_pipeline_project_etl.pipeline.yml
│   └── sample_job.job.yml
└── src/
    └── my_pipeline_project_etl/
        ├── explorations/
        │   └── sample_exploration.ipynb
        └── transformations/
            ├── sample_trips.py
            └── sample_zones.py
```

**Pipeline resource definition** (`resources/my_pipeline.pipeline.yml`):
```yaml
resources:
  pipelines:
    my_pipeline:
      name: my_pipeline
      catalog: my_catalog
      schema: my_schema
      target: my_pipeline_target
      libraries:
        - notebook:
            path: ../src/transformations/sample.py
      channel: CURRENT
      photon: true
      configuration:
        my_config_key: my_config_value
```

**Pipeline-specific CLI commands:**
```bash
databricks pipelines init                              # Create a pipeline bundle
databricks pipelines deploy --target dev               # Deploy pipeline
databricks pipelines run my_pipeline --target dev      # Run pipeline
databricks pipelines history my_pipeline               # View update history
databricks pipelines logs my_pipeline                  # View event logs (JSON)
databricks pipelines destroy --target dev              # Destroy pipeline resources
```

#### Python Wheel Bundle

Initialize with the default-python template, selecting "Include a stub Python package: yes":
```bash
databricks bundle init
# Template: default-python
# Include a job that runs a notebook: no
# Include an ETL pipeline: no
# Include a stub (sample) Python package: yes
```

**databricks.yml with artifacts:**
```yaml
bundle:
  name: my-wheel-bundle

artifacts:
  default:
    type: whl
    build: uv build    # or: poetry build / python3 setup.py bdist_wheel
    path: .

resources:
  jobs:
    wheel-job:
      name: wheel-job
      tasks:
        - task_key: wheel-task
          python_wheel_task:
            entry_point: main
            package_name: my_package
          libraries:
            - whl: ./dist/*.whl
```

**Alternative build tools:**

Poetry:
```yaml
artifacts:
  default:
    type: whl
    build: poetry build
    path: .
```

Setuptools:
```yaml
artifacts:
  default:
    type: whl
    build: python3 setup.py bdist_wheel
    path: .
```

#### Scala JAR Bundle

```bash
databricks bundle init default-scala
```

Requires: JDK 17, sbt, a Unity Catalog volume for artifact storage.

Generates:
```
my_scala_project/
├── databricks.yml
├── build.sbt
├── resources/
│   └── my_scala_project.job.yml
└── src/
    └── main/scala/com/examples/Main.scala
```

The JAR is uploaded to a Unity Catalog volume path specified during init.

#### MLOps Stacks Bundle

```bash
databricks bundle init mlops-stacks
```

Options during init:
- `CICD_and_Project` (default) — full ML code + CI/CD
- `Project_Only` — ML code only (for data scientists)
- `CICD_Only` — CI/CD infra only (for ML engineers)

Generates a complete MLOps project with:
- Model training jobs
- Batch inference jobs
- Feature table jobs
- ML experiment definitions
- Registered model definitions
- CI/CD configuration (GitHub Actions / Azure DevOps)
- Multi-environment targets (dev, staging, prod)

#### Manual Bundle (From Scratch)

Create `databricks.yml`:
```yaml
bundle:
  name: my-bundle

resources:
  jobs:
    my-job:
      name: my-job
      job_clusters:
        - job_cluster_key: shared-cluster
          new_cluster:
            spark_version: 13.3.x-scala2.12
            node_type_id: Standard_DS3_v2
            num_workers: 1
      tasks:
        - task_key: first-task
          job_cluster_key: shared-cluster
          notebook_task:
            notebook_path: ./notebooks/step1.py
        - task_key: second-task
          depends_on:
            - task_key: first-task
          job_cluster_key: shared-cluster
          notebook_task:
            notebook_path: ./notebooks/step2.py

targets:
  dev:
    mode: development
    default: true
    workspace:
      host: <workspace-url>
  prod:
    mode: production
    workspace:
      host: <workspace-url>
      root_path: /Shared/.bundle/prod/${bundle.name}
    run_as:
      service_principal_name: <sp-name>
```

### Step 4: Validate the Bundle

```bash
databricks bundle validate
```

Expected output on success:
```
Name: my-bundle
Target: dev
Workspace:
  Host: https://my-host.cloud.databricks.com
  User: someone@example.com
  Path: /Users/someone@example.com/.bundle/my-bundle/dev

Validation OK!
```

Fix any errors and re-validate before deploying.

**Generate a JSON schema for IDE autocomplete:**
```bash
databricks bundle schema > bundle_config_schema.json
```

Then add to `databricks.yml`:
```yaml
# yaml-language-server: $schema=bundle_config_schema.json
bundle:
  name: my-bundle
```

### Step 5: Deploy the Bundle

```bash
databricks bundle deploy -t dev
databricks bundle deploy -t prod
```

Useful flags:
- `--auto-approve` — skip interactive confirmations
- `--cluster-id <id>` — override cluster in deployment
- `--force-lock` — force acquire deployment lock (stale lock recovery)
- `--fail-on-active-runs` — fail if jobs/pipelines are currently running

**What deploy does:**
1. Builds artifacts (wheels, JARs) if `artifacts` are defined
2. Uploads source files to the workspace (under `~/.bundle/<name>/<target>/files/`)
3. Creates/updates resources (jobs, pipelines, etc.) in the workspace
4. Stores deployment state for tracking

### Step 6: Run the Bundle

**Run a job:**
```bash
databricks bundle run -t dev my_job
databricks bundle run -t dev my_job --params message=HelloWorld
databricks bundle run -t dev my_job -- --key1 value1 --key2 value2
```

**Run a pipeline:**
```bash
databricks bundle run -t dev my_pipeline
databricks bundle run -t dev my_pipeline --full-refresh-all
databricks bundle run -t dev my_pipeline --refresh my_table
databricks bundle run -t dev my_pipeline --validate-only
```

Or use the dedicated pipeline commands:
```bash
databricks pipelines run my_pipeline --target dev
databricks pipelines run my_pipeline --target dev --full-refresh-all
```

**Run a script defined in the bundle:**
```yaml
# In databricks.yml
scripts:
  integration_test:
    content: python3 tests/integration_test.py
```
```bash
databricks bundle run integration_test
```

**Run an inline command with bundle auth context:**
```bash
databricks bundle run -- python3 -c 'import os; print(os.getcwd())'
```

Useful run flags:
- `--no-wait` — don't wait for completion
- `--restart` — cancel and restart if already running

### Step 7: Additional Operations

#### View Bundle Summary
```bash
databricks bundle summary
databricks bundle summary -t prod
```

#### Open Resource in Browser
```bash
databricks bundle open my_job
databricks bundle open my_pipeline
```

#### Preview Deployment Plan (Without Deploying)
```bash
databricks bundle plan
databricks bundle plan -t prod
```

#### Sync Files Continuously (Development Loop)
```bash
databricks bundle sync --watch
databricks bundle sync --watch -t dev
```

#### Generate Config from Existing Resources
```bash
databricks bundle generate job --existing-job-id 12345 --bind
databricks bundle generate pipeline --existing-pipeline-id abc-123 --bind
databricks bundle generate dashboard --existing-id abc123
databricks bundle generate app --existing-app-name my-app
```

The `--bind` flag links the generated config to the existing resource so future deploys update it rather than creating a new one.

#### Bind/Unbind Existing Resources
```bash
databricks bundle deployment bind my_job 12345 -t prod
databricks bundle deployment unbind my_job
```

Supported resources for bind: app, cluster, dashboard, job, model_serving_endpoint, pipeline, quality_monitor, registered_model, schema, volume.

### Step 8: Clean Up / Destroy

```bash
databricks bundle destroy -t dev
databricks bundle destroy -t prod --auto-approve
```

**WARNING:** This permanently deletes all deployed resources (jobs, pipelines, files). It cannot be undone.

Use the `lifecycle` resource setting to prevent specific resources from being destroyed:
```yaml
resources:
  jobs:
    critical_job:
      lifecycle:
        prevent_destroy: true
```

## Target Modes

| Mode | Behavior |
|------|----------|
| `development` | Prefixes resource names with `[dev <username>]`, pauses schedules, enables development-specific defaults |
| `production` | Production naming, enforces `run_as`, schedules are active |

```yaml
targets:
  dev:
    mode: development
    default: true
  prod:
    mode: production
    run_as:
      service_principal_name: <sp-name>
```

## Variables

Define reusable variables:
```yaml
variables:
  warehouse_id:
    description: SQL warehouse ID
    default: abc123
  catalog:
    description: Target catalog
    lookup:
      catalog: my_catalog

targets:
  prod:
    variables:
      warehouse_id: xyz789
      catalog: prod_catalog
```

Override at deploy/run time:
```bash
databricks bundle deploy --var="warehouse_id=abc123"
```

## Permissions

```yaml
permissions:
  - level: CAN_VIEW
    group_name: data-analysts
  - level: CAN_MANAGE
    user_name: admin@company.com
  - level: CAN_MANAGE_RUN
    service_principal_name: ci-bot
```

## Custom Bundle Templates

To create reusable templates for your organization:

**Minimum template structure:**
```
my-template/
├── databricks_template_schema.json    # Input prompts and validation
└── template/
    └── {{.project_name}}/
        ├── databricks.yml.tmpl        # Main config template
        ├── resources/
        │   └── {{.project_name}}_job.yml.tmpl
        └── src/
            └── notebook.ipynb
```

**Template schema** (`databricks_template_schema.json`):
```json
{
  "properties": {
    "project_name": {
      "type": "string",
      "default": "my_project",
      "description": "Unique name for this project",
      "order": 1,
      "pattern": "^[^ .\\\\/]{3,}$",
      "pattern_match_failure_message": "Name must be 3+ chars, no spaces or special chars."
    }
  },
  "welcome_message": "Welcome to the custom bundle template!",
  "success_message": "Your bundle '{{.project_name}}' has been created.",
  "min_databricks_cli_version": "0.218.0"
}
```

**Available template helpers:**
- `{{workspace_host}}` — current workspace URL
- `{{user_name}}` — full name of the user
- `{{short_name}}` — short name of the user
- `{{is_service_principal}}` — boolean
- `{{default_catalog}}` — default workspace catalog
- `{{smallest_node_type}}` — smallest available node type
- `{{uuid}}` — stable UUID for the template execution
- `{{skip <glob>}}` — skip generating matching files

**Use the custom template:**
```bash
databricks bundle init /path/to/my-template
databricks bundle init https://github.com/org/my-template
```

## CI/CD Integration

For GitHub Actions:
```yaml
# .github/workflows/deploy.yml
name: Deploy Bundle
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: databricks/setup-cli@main
      - run: databricks bundle deploy -t prod
        env:
          DATABRICKS_HOST: ${{ secrets.DATABRICKS_HOST }}
          DATABRICKS_CLIENT_ID: ${{ secrets.DATABRICKS_CLIENT_ID }}
          DATABRICKS_CLIENT_SECRET: ${{ secrets.DATABRICKS_CLIENT_SECRET }}
```

For automated workflows, use OAuth M2M (service principal) authentication.

## CLI Command Quick Reference

| Command | Description |
|---------|-------------|
| `databricks bundle init [TEMPLATE]` | Create a new bundle from template |
| `databricks bundle validate` | Validate bundle configuration |
| `databricks bundle deploy -t <target>` | Deploy to target workspace |
| `databricks bundle run -t <target> <resource>` | Run a job/pipeline/script |
| `databricks bundle plan` | Preview deployment changes |
| `databricks bundle summary` | Show deployed resource summary |
| `databricks bundle open <resource>` | Open resource in browser |
| `databricks bundle sync --watch` | Continuous file sync |
| `databricks bundle destroy -t <target>` | Delete all deployed resources |
| `databricks bundle schema` | Output JSON schema for config |
| `databricks bundle generate job --existing-job-id <id>` | Generate config from existing job |
| `databricks bundle generate pipeline --existing-pipeline-id <id>` | Generate config from existing pipeline |
| `databricks bundle deployment bind <key> <id>` | Bind resource to workspace |
| `databricks bundle deployment unbind <key>` | Unbind resource |
| `databricks pipelines init` | Create a pipeline bundle |
| `databricks pipelines deploy -t <target>` | Deploy pipeline |
| `databricks pipelines run <name> -t <target>` | Run pipeline |
| `databricks pipelines history <name>` | View pipeline history |
| `databricks pipelines logs <name>` | View pipeline event logs |
| `databricks pipelines destroy -t <target>` | Destroy pipeline resources |

## Global Flags (Available on All Bundle Commands)

| Flag | Description |
|------|-------------|
| `-t, --target <name>` | Target to use |
| `-p, --profile <name>` | Auth profile from ~/.databrickscfg |
| `--var "key=value"` | Set bundle variable |
| `--output json` | JSON output |
| `--debug` | Enable debug logging |
| `--log-file <path>` | Write logs to file |

## Stopping Points

- After Step 1 if user intent is unclear (ask which bundle type)
- After Step 2 if template prompts require user input
- After Step 4 if validation fails (fix errors before deploying)
- After Step 6 if run fails (diagnose before retrying)

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Error: Databricks CLI version 0.218.0+ required` | Update CLI: `brew upgrade databricks` or reinstall |
| `Validation failed: resource not found` | Check `databricks.yml` references match actual file paths |
| `Deployment lock conflict` | Use `--force-lock` if previous deploy crashed |
| `Permission denied on deploy` | Verify auth profile has workspace-level permissions |
| `Bundle identity changed` | Do not change `bundle.name`, target name, or workspace between deploys without destroying first |
| `Resource already exists` | Use `bundle generate --bind` to link existing resources, or `bundle deployment bind` |
| `Pipeline requires CLI v0.283.0+` | Update CLI for `databricks pipelines init/deploy/run` commands |
| `Python wheel not found` | Ensure `artifacts` mapping is configured and `build` command is correct |
| `Libraries field is not supported for serverless task` | Serverless tasks cannot use task-level `libraries`. Move dependencies into an `environments` block and reference with `environment_key` on the task. See example below |
| `Missing required cluster or environment settings` | Every task needs compute. Add `environment_key` (serverless), `job_cluster_key` (job cluster), or `existing_cluster_id` (all-purpose) |
| `stat resources/<path>: no such file or directory` | Paths in resource YAMLs (e.g. `notebook_path`, `project_directory`) are relative to the resource YAML file, not the bundle root. Use `../src/` if resource is in `resources/` |

## Serverless Environment Pattern

Serverless tasks do NOT support task-level `libraries`. Use this pattern instead:

```yaml
resources:
  jobs:
    my_job:
      name: my_job
      tasks:
        - task_key: my_task
          # ... task config ...
          environment_key: default_env
      environments:
        - environment_key: default_env
          spec:
            client: "1"
            dependencies:
              - dbt-databricks>=1.0.0,<2.0.0
              - some-other-package==1.2.3
```

Key points:
- `client: "1"` is required in the environment spec
- List pip packages under `dependencies` (same format as `pip install`)
- Reference the environment from the task with `environment_key`
- If using a classic `job_cluster_key` instead, task-level `libraries` with `pypi` packages still work

## Output

This skill produces:
- Initialized bundle project directories with `databricks.yml` and resource configs
- Validated, deployed, and running Databricks workflows (jobs, pipelines, etc.)
- Generated bundle configuration from existing workspace resources
- Custom bundle templates for organizational reuse
