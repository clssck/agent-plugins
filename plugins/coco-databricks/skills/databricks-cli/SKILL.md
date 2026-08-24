---
name: databricks-cli
description: "Run Databricks CLI commands for day-to-day workspace operations. Use when: managing clusters, running jobs, listing or cancelling job runs, managing SQL warehouses, working with workspace files and notebooks, managing secrets and scopes, managing users/groups/service-principals/permissions, querying serving endpoints, interacting with ML experiments and model registry, using the filesystem (DBFS/Volumes), executing arbitrary REST API calls, or any general databricks CLI operation not covered by the bundle, install, UC, or ETL skills. Triggers: databricks cli, clusters, jobs, job runs, pipelines, SQL warehouse, workspace, notebooks, secrets, fs, dbfs, serving endpoints, model serving, experiments, model registry, users, groups, service principals, permissions, grants, alerts, queries, instance pools, libraries, repos, git credentials, account, api, REST."
---

# Databricks CLI

General-purpose skill for running Databricks CLI commands across all major command groups. For installation and authentication, see the `databricks-cli-install` skill. For Declarative Automation Bundles, see `databricks-automation-bundles`. For Unity Catalog browsing, see `databricks-unity-catalog`.

## Prerequisites

- Databricks CLI v0.205+ installed and authenticated (see `databricks-cli-install` skill)
- A valid configuration profile or environment variables set

## Concepts

### Command Structure

```
databricks <command-group> <command> [args] [--flags]
```

Get help at any level:
```bash
databricks -h
databricks clusters -h
databricks clusters list -h
```

### Global Flags

| Flag | Description |
|------|-------------|
| `-p, --profile <name>` | Use a specific auth profile from `~/.databrickscfg` |
| `--host <url>` | Override workspace host |
| `--output json\|text` | Output format (default: text) |
| `--debug` | Enable debug logging |
| `--log-file <path>` | Write debug logs to file |
| `--log-level <level>` | Log level: `trace`, `debug`, `info`, `warn`, `error` |

**Always use `--output json`** when you need to parse or process results programmatically.

### JSON Input

Many commands accept `--json` for structured input. On Linux/macOS, wrap in single quotes:
```bash
databricks clusters create --json '{
  "cluster_name": "my-cluster",
  "spark_version": "15.4.x-scala2.12",
  "node_type_id": "m5d.xlarge",
  "num_workers": 2
}'
```

### Filtering Output with jq

```bash
databricks clusters list --output json | jq '.[].cluster_name'
databricks jobs list --output json | jq '.[] | select(.settings.name | test("etl"))'
```

### Profiles

```bash
databricks auth profiles                    # List all profiles
databricks auth env --profile <name>        # Show profile details
databricks auth token -p <name>             # Show current token + expiry
```

## Workflow

### Step 1: Identify the User's Goal

Route to the appropriate command group:

| Goal | Command Group | Section |
|------|--------------|---------|
| Manage clusters | `clusters` | Compute |
| Manage instance pools | `instance-pools` | Compute |
| Manage cluster policies | `cluster-policies` | Compute |
| Install libraries on clusters | `libraries` | Compute |
| Create/run/manage jobs | `jobs` | Jobs |
| Manage pipelines (DLT) | `pipelines` | Pipelines |
| Manage SQL warehouses | `warehouses` | SQL |
| Work with files (DBFS/Volumes) | `fs` | Workspace & Files |
| Import/export notebooks | `workspace` | Workspace & Files |
| Manage git repos | `repos` | Workspace & Files |
| Manage secrets | `secrets` | Secrets |
| Manage users/groups/SPs | `users`, `groups`, `service-principals` | Identity |
| Manage permissions | `permissions` | Identity |
| ML experiments | `experiments` | ML & Serving |
| Model registry | `model-registry` | ML & Serving |
| Model serving endpoints | `serving-endpoints` | ML & Serving |
| Account-level admin | `account` | Account |
| Call any REST API | `api` | API Escape Hatch |

**⚠️ STOP**: If the user's intent maps to an existing skill, route there instead:
- Unity Catalog browsing → `databricks-unity-catalog`
- Bundle lifecycle → `databricks-automation-bundles`
- CLI install/auth → `databricks-cli-install`
- ETL notebooks → `databricks-etl-pyspark-notebooks`

---

### Compute

#### Clusters

```bash
databricks clusters list --output json
databricks clusters get <CLUSTER_ID> --output json
databricks clusters create --json '<JSON>'
databricks clusters edit --json '<JSON>'
databricks clusters start <CLUSTER_ID>
databricks clusters restart <CLUSTER_ID>
databricks clusters delete <CLUSTER_ID>              # Terminate
databricks clusters permanent-delete <CLUSTER_ID>    # Permanent delete
databricks clusters pin <CLUSTER_ID>
databricks clusters unpin <CLUSTER_ID>
databricks clusters events <CLUSTER_ID> --output json
databricks clusters spark-versions                    # List available runtimes
databricks clusters list-node-types --output json     # List available node types
```

Create cluster example:
```bash
databricks clusters create --json '{
  "cluster_name": "dev-cluster",
  "spark_version": "15.4.x-scala2.12",
  "node_type_id": "m5d.xlarge",
  "autoscale": {"min_workers": 1, "max_workers": 4},
  "autotermination_minutes": 30
}'
```

#### Instance Pools

```bash
databricks instance-pools list --output json
databricks instance-pools get <POOL_ID> --output json
databricks instance-pools create --json '<JSON>'
databricks instance-pools edit --json '<JSON>'
databricks instance-pools delete --json '{"instance_pool_id": "<POOL_ID>"}'
```

#### Libraries

```bash
databricks libraries all-cluster-statuses --output json
databricks libraries cluster-status <CLUSTER_ID> --output json
databricks libraries install --cluster-id <CLUSTER_ID> --json '{
  "libraries": [{"pypi": {"package": "pandas==2.1.0"}}]
}'
databricks libraries uninstall --cluster-id <CLUSTER_ID> --json '{
  "libraries": [{"pypi": {"package": "pandas"}}]
}'
```

---

### Jobs

```bash
databricks jobs list --output json
databricks jobs list --name "etl" --output json        # Filter by name
databricks jobs get <JOB_ID> --output json
databricks jobs create --json '<JSON>'
databricks jobs reset <JOB_ID> --json '<JSON>'         # Full replace
databricks jobs update <JOB_ID> --json '<JSON>'        # Partial update
databricks jobs delete <JOB_ID>
```

#### Running Jobs

```bash
databricks jobs run-now <JOB_ID>                       # Trigger a run
databricks jobs run-now <JOB_ID> --json '{
  "notebook_params": {"key": "value"}
}'
databricks jobs list-runs --job-id <JOB_ID> --output json
databricks jobs get-run <RUN_ID> --output json
databricks jobs get-run-output <RUN_ID> --output json
databricks jobs cancel-run <RUN_ID>
databricks jobs cancel-all-runs <JOB_ID>
databricks jobs repair-run <RUN_ID> --json '<JSON>'    # Retry failed tasks
databricks jobs delete-run <RUN_ID>
databricks jobs export-run <RUN_ID> --output json
```

#### One-time Runs (no saved job)

```bash
databricks jobs submit --json '{
  "run_name": "one-off-task",
  "tasks": [{
    "task_key": "main",
    "notebook_task": {
      "notebook_path": "/Users/me/notebook"
    },
    "new_cluster": {
      "spark_version": "15.4.x-scala2.12",
      "node_type_id": "m5d.xlarge",
      "num_workers": 1
    }
  }]
}'
```

---

### Pipelines (Lakeflow / DLT)

```bash
databricks pipelines list-pipelines --output json
databricks pipelines get <PIPELINE_ID> --output json
databricks pipelines create --json '<JSON>'
databricks pipelines update <PIPELINE_ID> --json '<JSON>'
databricks pipelines delete <PIPELINE_ID>
databricks pipelines start-update <PIPELINE_ID>
databricks pipelines start-update <PIPELINE_ID> --full-refresh true
databricks pipelines stop <PIPELINE_ID>
databricks pipelines list-updates <PIPELINE_ID> --output json
databricks pipelines get-update <PIPELINE_ID> --update-id <UPDATE_ID>
databricks pipelines list-pipeline-events <PIPELINE_ID> --output json
```

For bundle-managed pipelines, see the `databricks-automation-bundles` skill.

---

### SQL

#### Warehouses

```bash
databricks warehouses list --output json
databricks warehouses get <WAREHOUSE_ID> --output json
databricks warehouses create --json '<JSON>'
databricks warehouses edit <WAREHOUSE_ID> --json '<JSON>'
databricks warehouses start <WAREHOUSE_ID>
databricks warehouses stop <WAREHOUSE_ID>
databricks warehouses delete <WAREHOUSE_ID>
```

#### Execute SQL Statements

**Important:** There is NO dedicated `databricks sql` or `databricks statement-execution` CLI command. SQL execution goes through the REST API escape hatch:

```bash
databricks api post /api/2.0/sql/statements --json '{
  "statement": "SELECT * FROM catalog.schema.table LIMIT 10",
  "warehouse_id": "<WAREHOUSE_ID>",
  "wait_timeout": "50s"
}'
```

The `databricks api` command uses the authenticated CLI profile -- no Bearer token or manual auth header is needed.

#### SQL Without Unity Catalog (Hive Metastore)

If the workspace uses the legacy Hive Metastore instead of Unity Catalog, SQL execution still works via the same API. Use two-level naming (`database.table`) instead of three-level:

```bash
databricks api post /api/2.0/sql/statements --json '{
  "statement": "SELECT * FROM default.my_table LIMIT 10",
  "warehouse_id": "<WAREHOUSE_ID>",
  "wait_timeout": "50s"
}'
```

Useful Hive Metastore discovery queries:
- `SHOW DATABASES` -- list all databases
- `SHOW TABLES IN <database>` -- list tables in a database
- `DESCRIBE TABLE <database>.<table>` -- get table schema

If no SQL warehouse exists, the alternative is to run SQL via a notebook on an all-purpose cluster (use the `databricks-etl-pyspark-notebooks` skill for that workflow).

#### Alerts and Queries

```bash
databricks alerts list --output json
databricks alerts get <ALERT_ID> --output json
databricks alerts create --json '<JSON>'
databricks alerts delete <ALERT_ID>
databricks queries list --output json
databricks queries get <QUERY_ID> --output json
```

---

### Workspace & Files

#### Filesystem (DBFS and Volumes)

```bash
databricks fs ls dbfs:/path/to/dir
databricks fs ls /Volumes/catalog/schema/volume/path
databricks fs cp local-file.csv dbfs:/uploads/file.csv
databricks fs cp dbfs:/uploads/file.csv ./local-file.csv
databricks fs cp local-dir/ dbfs:/uploads/dir/ --recursive
databricks fs mkdir dbfs:/new-dir
databricks fs rm dbfs:/old-file.csv
databricks fs rm dbfs:/old-dir/ --recursive
databricks fs cat dbfs:/path/to/file.txt
```

#### Workspace (Notebooks and Folders)

```bash
databricks workspace list /Users/me --output json
databricks workspace get-status /Users/me/notebook --output json
databricks workspace export /Users/me/notebook --format SOURCE -o notebook.py
databricks workspace export-dir /Users/me/project ./local-dir
databricks workspace import ./notebook.py /Users/me/notebook --format SOURCE --language PYTHON
databricks workspace import-dir ./local-dir /Users/me/project
databricks workspace mkdirs /Users/me/new-folder
databricks workspace delete /Users/me/old-notebook
databricks workspace delete /Users/me/old-folder --recursive
```

#### Git Repos

```bash
databricks repos list --output json
databricks repos get <REPO_ID> --output json
databricks repos create --json '{
  "url": "https://github.com/org/repo",
  "provider": "gitHub",
  "path": "/Repos/me/my-repo"
}'
databricks repos update <REPO_ID> --json '{"branch": "main"}'
databricks repos delete <REPO_ID>
```

---

### Secrets

```bash
databricks secrets list-scopes --output json
databricks secrets create-scope <SCOPE_NAME>
databricks secrets delete-scope <SCOPE_NAME>
databricks secrets put-secret <SCOPE_NAME> <KEY> --string-value "<VALUE>"
databricks secrets list-secrets <SCOPE_NAME> --output json
databricks secrets get-secret <SCOPE_NAME> <KEY>
databricks secrets delete-secret <SCOPE_NAME> <KEY>
```

#### Secret ACLs

```bash
databricks secrets list-acls <SCOPE_NAME> --output json
databricks secrets get-acl <SCOPE_NAME> --principal <PRINCIPAL>
databricks secrets put-acl <SCOPE_NAME> --principal <PRINCIPAL> --permission MANAGE|READ|WRITE
databricks secrets delete-acl <SCOPE_NAME> --principal <PRINCIPAL>
```

---

### Identity & Access

#### Users

```bash
databricks users list --output json
databricks users get <USER_ID> --output json
databricks users create --json '{"userName": "user@example.com"}'
databricks users delete <USER_ID>
```

#### Groups

```bash
databricks groups list --output json
databricks groups get <GROUP_ID> --output json
databricks groups create --json '{"displayName": "data-engineers"}'
databricks groups patch <GROUP_ID> --json '{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [{"op": "add", "path": "members", "value": [{"value": "<USER_ID>"}]}]
}'
databricks groups delete <GROUP_ID>
```

#### Service Principals

```bash
databricks service-principals list --output json
databricks service-principals get <SP_ID> --output json
databricks service-principals create --json '{"displayName": "ci-bot", "active": true}'
databricks service-principals delete <SP_ID>
```

#### Permissions

```bash
databricks permissions get <OBJECT_TYPE> <OBJECT_ID> --output json
databricks permissions set <OBJECT_TYPE> <OBJECT_ID> --json '{
  "access_control_list": [
    {"group_name": "data-engineers", "permission_level": "CAN_MANAGE"}
  ]
}'
databricks permissions update <OBJECT_TYPE> <OBJECT_ID> --json '<JSON>'
```

Object types: `clusters`, `cluster-policies`, `instance-pools`, `jobs`, `pipelines`, `notebooks`, `directories`, `repos`, `serving-endpoints`, `warehouses`, `registered-models`, `experiments`.

---

### ML & Serving

#### Experiments (MLflow)

```bash
databricks experiments list-experiments --output json
databricks experiments get-experiment <EXPERIMENT_ID> --output json
databricks experiments get-by-name --experiment-name "/Users/me/experiment"
databricks experiments create-experiment --name "/Users/me/new-experiment"
databricks experiments search-runs --experiment-ids <ID> --output json
databricks experiments delete-experiment --experiment-id <ID>
```

#### Model Registry

```bash
databricks model-registry list-models --output json
databricks model-registry get-model --name "my_model" --output json
databricks model-registry get-latest-versions --name "my_model" --output json
databricks model-registry search-model-versions --filter "name='my_model'" --output json
databricks model-registry transition-stage --name "my_model" --version 3 --stage Production --archive-existing-versions
```

#### Serving Endpoints

```bash
databricks serving-endpoints list --output json
databricks serving-endpoints get <ENDPOINT_NAME> --output json
databricks serving-endpoints create --json '<JSON>'
databricks serving-endpoints update-config <ENDPOINT_NAME> --json '<JSON>'
databricks serving-endpoints delete <ENDPOINT_NAME>
databricks serving-endpoints query <ENDPOINT_NAME> --json '{
  "inputs": [{"question": "What is Databricks?"}]
}'
databricks serving-endpoints logs <ENDPOINT_NAME> --served-model-name <MODEL>
databricks serving-endpoints build-logs <ENDPOINT_NAME> --served-model-name <MODEL>
```

---

### Account-Level Commands

Account commands require account-level auth (`--host https://accounts.cloud.databricks.com --account-id <ID>`).

```bash
databricks account users list --output json
databricks account groups list --output json
databricks account service-principals list --output json
databricks account workspaces list --output json
databricks account metastores list --output json
databricks account budgets list --output json
databricks account billable-usage download --start-month 2025-01 --end-month 2025-12 -o usage.csv
```

---

### API Escape Hatch

For any Databricks REST API endpoint not directly exposed as a CLI command:

```bash
databricks api get /api/2.0/<endpoint> --output json
databricks api post /api/2.0/<endpoint> --json '<JSON>'
databricks api put /api/2.0/<endpoint> --json '<JSON>'
databricks api delete /api/2.0/<endpoint>
databricks api patch /api/2.0/<endpoint> --json '<JSON>'
```

Example — get current user:
```bash
databricks api get /api/2.0/preview/scim/v2/Me --output json
```

Example — run SQL:
```bash
databricks api post /api/2.0/sql/statements --json '{
  "statement": "SHOW TABLES IN catalog.schema",
  "warehouse_id": "<WAREHOUSE_ID>",
  "wait_timeout": "50s"
}'
```

## Stopping Points

- After Step 1 if user intent is ambiguous (ask which operation)
- Before any destructive operation (`delete`, `permanent-delete`, `destroy`) — confirm with the user
- If authentication fails — route to `databricks-cli-install` skill

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `command not found: databricks` | CLI not installed. See `databricks-cli-install` skill. |
| `Error: authentication required` | No valid profile or env vars. Run `databricks auth login --host <url>`. |
| `Error: ... 403 Forbidden` | User lacks permissions. Check with `databricks permissions get`. |
| `Error: ... 404 Not Found` | Resource ID is wrong or resource was deleted. Verify with a `list` command. |
| `Error: ... rate limit exceeded` | Too many API calls. Wait and retry, or batch operations. |
| `--output json` not recognized | CLI version too old. Update: `brew upgrade databricks`. |
| Profile not found | List profiles with `databricks auth profiles`. Check `~/.databrickscfg`. |
| `Error: cluster is not running` | Start the cluster first: `databricks clusters start <ID>`. |
| Timeout on SQL statement | Increase `wait_timeout` (max `50s`). For long queries, poll with statement ID. |

## Output

This skill produces:
- Databricks resource management via CLI (clusters, jobs, warehouses, endpoints, etc.)
- JSON output from list/get commands for further processing
- Created, updated, or deleted Databricks resources as requested
