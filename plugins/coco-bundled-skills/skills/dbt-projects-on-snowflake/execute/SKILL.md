---
name: dbt-execute
description: "Execute dbt commands on Snowflake (run, test, build, seed, snapshot, show). Triggers: run, test, build, seed, execute, snapshot, show, preview, deployed object, deployed project, run in deployed, using the deployed, except, exclude, all models except, data quality tests, run tests, seed CSV, load seed, load CSV, seed data, CSV data, preview model, preview output, show output, dbt show."
parent_skill: dbt-projects-on-snowflake
---

# Execute dbt Commands

## When to Load

Main skill routes here for: "run", "test", "build", "seed", "execute", "snapshot", "show", "preview", "deployed object", "deployed project", "run in deployed", "using the deployed", "except", "exclude", "all models except", "data quality tests", "run tests", "seed CSV", "load seed", "load CSV", "seed data", "CSV data", "preview model", "preview output", "show output", "dbt show", "docs", "documentation", "catalog", "lineage", "dbt docs", "generate docs"

## ⚠️ `docs generate` - Use SQL Command (NOT `snow dbt execute`)

**`snow dbt execute` does NOT support `docs generate`.** You MUST use SQL with `EXECUTE DBT PROJECT`:

### ✅ CORRECT Syntax (copy this EXACTLY):
```sql
EXECUTE DBT PROJECT <DATABASE>.<SCHEMA>.<PROJECT_NAME> ARGS='docs generate'
```

**Via snow sql CLI:**
```bash
snow sql -q "EXECUTE DBT PROJECT <DATABASE>.<SCHEMA>.<PROJECT_NAME> ARGS='docs generate'"
```

**Concrete example:**
```bash
snow sql -q "EXECUTE DBT PROJECT SNOVA_EVAL_SCRATCH.MY_SCHEMA.EVAL_DBT_PROJECT ARGS='docs generate'"
```

### ❌ WRONG - Do NOT use JSON array format (will fail):
```sql
-- WRONG: JSON array format - causes "command not supported" error
EXECUTE DBT PROJECT db.schema.project ARGS='["docs", "generate"]'
EXECUTE DBT PROJECT db.schema.project ARGS = '["docs", "generate"]'
```

**CRITICAL: The ARGS value must be a plain string (not a JSON array). Both `ARGS='docs generate'` and `ARGS = 'docs generate'` are valid.**

---

## Critical Syntax

**Connection flags MUST come BEFORE the project name:**

```bash
# ✅ CORRECT
snow dbt execute -c default --database my_db --schema my_schema my_project run

# ❌ WRONG - flags after project name
snow dbt execute my_project run --database my_db
```

## ⚠️ CRITICAL: Preview vs Run

**To PREVIEW model output without creating objects, use `show`:**
```bash
snow dbt execute -c default --database my_db --schema my_schema my_project show --select model_name
```

**Do NOT use `run` for preview tasks!** `run` creates actual tables/views in the database.

| Task | Command | Creates Objects? |
|------|---------|------------------|
| Preview/inspect data | `show` | ❌ No |
| Materialize models | `run` | ✅ Yes |

## Workflow

### Step 1: Identify Command

| User Intent | dbt Command |
|-------------|-------------|
| List resources/models in project | `list` |
| Preview model output (no materialization) | `show` |
| Compile SQL without executing | `compile` |
| Run models | `run` |
| Run against a specific target/profile (e.g., prod) | `run --target <name>` |
| Run tests | `test` |
| Run + test + seed + snapshot | `build` |
| Load CSV seed data | `seed` |
| Capture snapshots | `snapshot` |

### Step 2: Execute Command

**Goal:** Run the dbt command via Snowflake-native execution

**Syntax:**
```bash
snow dbt execute -c <connection> --database <db> --schema <schema> <project> <command> [options]
```

### Available Commands

#### List Resources/Models in Project
```bash
snow dbt execute -c default --database my_db --schema my_schema my_project list
```
Shows all resources (models, seeds, tests, snapshots) defined in the project.

**Note:** This is different from `snow dbt list` which lists **projects** in a schema (see `manage/SKILL.md`).
#### Preview Model Output (show)
```bash
snow dbt execute -c default --database my_db --schema my_schema my_project show --select model_name
```
Previews the compiled SQL output of a model **without materializing any objects**. Use this to inspect what data a model would produce before running it.

**Key behavior:**
- Does NOT create tables or views
- Returns sample rows from the model's query
- Useful for debugging and validating model logic

**Example - preview specific model:**
```bash
snow dbt execute -c default --database my_db --schema my_schema my_project show --select stg_customers
```

#### Compile SQL Without Executing (compile)
```bash
snow dbt execute -c default --database my_db --schema my_schema my_project compile
```
Compiles dbt models into raw SQL **without executing anything**. No tables or views are created. Use this when the user wants to see the generated SQL or verify compilation.

#### Run Models
```bash
snow dbt execute -c default --database my_db --schema my_schema my_project run
```
Creates tables/views from models.

#### Run Specific Models
```bash
snow dbt execute -c default --database my_db --schema my_schema my_project run --select model_name
```

#### Full Refresh (Rebuild Incremental Models)
```bash
snow dbt execute -c default --database my_db --schema my_schema my_project run --full-refresh
```
Drops and rebuilds incremental tables from scratch. **Required** after fixing incremental model logic (e.g., changing `is_incremental()` blocks, unique keys, or incremental strategy) — a normal run only appends/merges new rows and won't fix data built by broken logic.

Can combine with `--select`:
```bash
snow dbt execute -c default --database my_db --schema my_schema my_project run --select model_name --full-refresh
```

#### Run Specific Models WITH dependencies
Use graph selectors to include dependencies:

```bash
# Include upstream deps of the target
snow dbt execute -c default --database my_db --schema my_schema my_project run --select +target_model

# Include downstream deps of the target
snow dbt execute -c default --database my_db --schema my_schema my_project run --select target_model+

# Include both upstream and downstream around the target
snow dbt execute -c default --database my_db --schema my_schema my_project run --select +target_model+
```

#### Run Tests
```bash
snow dbt execute -c default --database my_db --schema my_schema my_project test
```
Executes all schema and data tests.

#### Build (All-in-One)
```bash
snow dbt execute -c default --database my_db --schema my_schema my_project build
```
Runs models + tests + seeds + snapshots in dependency order.

Build with full refresh (rebuild all incremental models):
```bash
snow dbt execute -c default --database my_db --schema my_schema my_project build --full-refresh
```

#### Load Seed Data
```bash
snow dbt execute -c default --database my_db --schema my_schema my_project seed
```
Loads CSV files from `seeds/` directory into tables.

#### Capture Snapshots
```bash
snow dbt execute -c default --database my_db --schema my_schema my_project snapshot
```
Creates SCD Type 2 snapshot tables.

#### Select Models by Materialization Type
Use dbt's config selector to run only models with a specific materialization:

```bash
# Run only models materialized as tables
snow dbt execute -c default --database my_db --schema my_schema my_project run --select config.materialized:table

# Run only models materialized as views
snow dbt execute -c default --database my_db --schema my_schema my_project run --select config.materialized:view

# Run only incremental models
snow dbt execute -c default --database my_db --schema my_schema my_project run --select config.materialized:incremental
```

**IMPORTANT:** Use `config.materialized:type` syntax, NOT model names. For example:
- ✅ `--select config.materialized:table` (selects ALL table-materialized models)
- ❌ `--select table_model` (selects a model named "table_model")

#### Run with a Specific Target (--target)
```bash
snow dbt execute -c default --database my_db --schema my_schema my_project run --target prod
```
Select a specific profile output (target) defined in `profiles.yml`. Without `--target`, dbt uses the default target from the profile. When the user asks to run against a specific target/profile/environment, pass `--target <name>`.

**Example:** If profiles.yml has outputs `dev` and `prod`:
```bash
snow dbt execute -c default --database DB --schema SCHEMA my_project run --target prod
```

#### Run with Runtime Variables (--vars)
```bash
snow dbt execute -c default --database my_db --schema my_schema my_project run --vars '{"var_name": "value"}'
```
Pass runtime variables to dbt models. The vars are passed through to dbt and can be accessed with `{{ var('var_name') }}` in models.

**Example:** If model has `{{ var('name_alias', 'default_name') }}`:
```bash
snow dbt execute -c default --database DB --schema SCHEMA my_project run --vars '{"name_alias": "custom_column_name"}'
```

#### Execute with Specific dbt Version

**Use SQL syntax to specify a dbt version** (the CLI `snow dbt execute` does not support `--dbt-version`):

```sql
EXECUTE DBT PROJECT <DATABASE>.<SCHEMA>.<PROJECT_NAME> DBT_VERSION='1.9.4' ARGS='run'
```

**Via snow sql CLI:**
```bash
snow sql -q "EXECUTE DBT PROJECT my_db.my_schema.my_project DBT_VERSION='1.9.4' ARGS='run'"
```

Runs the project using a specific dbt version instead of the project's default. The `DBT_VERSION` parameter must be placed before `ARGS`.

### Step 3: Verify Results

**Goal:** Confirm command succeeded

1. Check command output for `PASS=N ERROR=0`
2. Optionally verify objects were created:
   ```sql
   SHOW TABLES IN SCHEMA <db>.<schema>;
   ```

## CLI Reference

```bash
snow dbt execute [CONNECTION_FLAGS] NAME COMMAND [dbt_options]
```

| Parameter | Position | Description |
|-----------|----------|-------------|
| `-c, --connection` | Before NAME | Snowflake connection |
| `--database` | Before NAME | Target database |
| `--schema` | Before NAME | Target schema |
| `NAME` | After flags | Project identifier |
| `COMMAND` | After NAME | dbt command (list/show/compile/run/test/build/seed/snapshot) |

**dbt Options (after COMMAND):**
| Option | Description |
|--------|-------------|
| `--select <selector>` | Select specific models/resources |
| `--target <name>` | Use a specific profile target (e.g., prod, qa) |
| `--vars '<json>'` | Pass runtime variables as JSON |

**dbt Commands:**
| Command | Creates |
|---------|---------|
| `list` | - (displays resources) |
| `show` | - (previews data only, no objects created) |
| `compile` | - (generates SQL, no execution) |
| `run` | Tables/views from models |
| `test` | - (validates data) |
| `build` | Tables + snapshots (runs all) |
| `seed` | Seed tables from CSVs |
| `snapshot` | SCD Type 2 snapshot tables |

## Stopping Points

- ⚠️ If command fails, check troubleshooting in `references/troubleshooting.md`

## Output

- Materialized tables/views in target schema
- Test results (pass/fail counts)
- Seed tables from CSV data
- Snapshot tables with SCD columns
