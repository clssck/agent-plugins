---
name: dbt-migration
description: "Migrate dbt projects to run on Snowflake. Triggers: migrate, env_var, environment variable, env.yml, env yml, migration, prepare for snowflake."
parent_skill: dbt-projects-on-snowflake
---

# Migrate dbt Project to Snowflake

## When to Load

Main skill routes here for: "migrate", "env_var", "environment variable", "env.yml", "migration", "prepare for snowflake"

## Overview

**This is an ACTION skill** - proceed with creation of dbt project. Do not just analyze and report.

This skill helps migrate existing dbt projects to run on Snowflake using the `env.yml` environment variables feature.

## General Steps (Apply to All Migrations)

### Step 1: Create a Snowflake-Ready Copy

> **⚠️ MANDATORY — DO THIS FIRST BEFORE ANY OTHER CHANGES ⚠️**
>
> You MUST create a copy of the project BEFORE making any edits. **NEVER modify, edit, delete, or rename any file in the original project directory.** The original must remain byte-for-byte identical after migration.

```bash
cp -r <original_project> <original_project>_snowflake
```

Example:
```bash
cp -r /path/to/my_project /path/to/my_project_snowflake
```

**ALL subsequent edits go to the `_snowflake` copy ONLY.** Double-check every file path before editing — if it doesn't contain `_snowflake`, STOP and fix the path.

**Exception:** Only edit in-place if the user explicitly requests it (e.g., "edit files directly", "modify in place").

### Step 2: Update profiles.yml

Update `profiles.yml` for Snowflake-hosted dbt:

1. **Remove authentication fields** (`password`, `authenticator`, `private_key_path`, `private_key_passphrase`, `token`) - authentication is handled by the Snowflake session
2. **Keep `env_var()` calls** — they ARE supported when backed by an `env.yml` file
3. **Rename env_var keys to `DBT_` prefix UPPERCASE** — e.g., `env_var('SNOWFLAKE_ROLE')` becomes `env_var('DBT_CURRENT_ROLE')`
4. `account` and `user` fields can be set to `"not needed"` (auth is handled by the Snowflake session)

**Before (local dbt with env_var and password):**
```yaml
default:
  target: dev
  outputs:
    dev:
      type: snowflake
      account: "{{ env_var('SNOWFLAKE_ACCOUNT') }}"
      user: "{{ env_var('SNOWFLAKE_USER') }}"
      password: "{{ env_var('SNOWFLAKE_PASSWORD') }}"
      role: "{{ env_var('SNOWFLAKE_ROLE') }}"
      database: "{{ env_var('SNOWFLAKE_DATABASE') }}"
      warehouse: "{{ env_var('SNOWFLAKE_WAREHOUSE') }}"
      schema: "{{ env_var('SNOWFLAKE_SCHEMA') }}"
      threads: 4
```

**After (env_var backed by env.yml, password removed):**
```yaml
default:
  target: dev
  outputs:
    dev:
      type: snowflake
      account: "not needed"
      user: "not needed"
      role: "{{ env_var('DBT_CURRENT_ROLE') }}"
      database: "{{ env_var('DBT_CURRENT_DB') }}"
      warehouse: "{{ env_var('DBT_CURRENT_WH') }}"
      schema: "{{ env_var('DBT_CURRENT_SCHEMA') }}"
      threads: 4
```

See `references/profiles-yml.md` for all requirements.

### Step 3: Create env.yml

**Create `env.yml` in the project root** (same directory as `dbt_project.yml`). This file defines the environment variables that `env_var()` calls resolve from.

**Naming rules (enforced — run fails if broken):**
- Every key in `env:` must be prefixed with `DBT_`
- Every key must be UPPERCASE
- Keys in `secrets:` must be prefixed with `DBT_ENV_SECRET_`
- Key names must be plain text (no SQL on the left-hand side)
- Environment names are case sensitive (letters, numbers, underscores, up to 256 chars)

**Values in `env:` can be:**
- Plain text: `DBT_MY_VAR: my_value`
- SQL that returns one row, one VARCHAR column: `DBT_CURRENT_ROLE: "{{ select CURRENT_ROLE() }}"`
- Stored procedure calls: `DBT_SCHEMA: "{{ select * FROM TABLE(my_proc()) }}"`

**Example env.yml:**
```yaml
env_config:
  default_environment: dev
  environments:
    - name: dev
      env:
        DBT_CURRENT_WH: "{{ select CURRENT_WAREHOUSE() }}"
        DBT_CURRENT_DB: "{{ select CURRENT_DATABASE() }}"
        DBT_CURRENT_SCHEMA: "{{ select CURRENT_SCHEMA() }}"
        DBT_CURRENT_ROLE: "{{ select CURRENT_ROLE() }}"
        DBT_DATA_INTERVAL_START: "2020-01-01 00:00:00"
        DBT_DATA_INTERVAL_END: "2099-12-31 23:59:59"
    - name: prod
      env:
        DBT_CURRENT_WH: <your_prod_warehouse>
        DBT_CURRENT_DB: <your_prod_database>
        DBT_CURRENT_SCHEMA: <your_prod_schema>
        DBT_CURRENT_ROLE: <your_prod_role>
        DBT_DATA_INTERVAL_START: "{{ select (DATE_TRUNC('DAY', CURRENT_TIMESTAMP()) - INTERVAL '1 DAY')::string }}"
        DBT_DATA_INTERVAL_END: "{{ select (DATE_TRUNC('DAY', CURRENT_TIMESTAMP()) - INTERVAL '1 SECOND')::string }}"
```

### Step 4: Check for Special Cases

After general steps, check if any special handling is needed:

| Case | Detect | Action |
|------|--------|--------|
| **env_var() in project** | Models, macros, `dbt_project.yml` contain `env_var()` with non-`DBT_` prefixed names | Go to **Case 1** below |
| **Private Git packages** | `packages.yml` uses git tokens via `env_var()` | Go to **Case 2** below |

---

## Case 1: env_var() Rename Migration

### Why

Snowflake's `env.yml` requires all environment variable keys to be **UPPERCASE with a `DBT_` prefix**. Existing projects that use `env_var()` with non-conforming names (e.g., `env_var('SNOWFLAKE_ROLE')`, `env_var('my_schema')`) must rename those variables.

### Step 1: Scan for env_var() Usage

Search project files for all `env_var()` references:

```bash
grep -r "env_var" <project_path> --include="*.yml" --include="*.yaml" --include="*.sql"
```

Common locations:
- `profiles.yml` - connection settings
- `dbt_project.yml` - project-level variables and config
- `packages.yml` - package dependencies
- `models/**/*.sql` - model files
- `macros/**/*.sql` - macro files
- `models/**/*.yml` - schema/docs files

### Step 1b: Identify Secrets

**⚠️ CRITICAL: Never put secret values as plain text in env.yml!**

After scanning, identify any `env_var()` calls that reference secrets — variables whose names contain `SECRET`, `TOKEN`, `PASSWORD`, `CREDENTIAL`, `KEY`, or that will be renamed to `DBT_ENV_SECRET_*`. These MUST be handled via the `secrets:` section of `env.yml` (backed by Snowflake secret objects), never as plain `env:` values.

**Behavior:**
- **Auto-mode (non-interactive):** Skip secret variables entirely. In the generated `env.yml`, leave a commented-out `secrets:` block with TODO instructions:
  ```yaml
  env_config:
    default_environment: dev
    environments:
      - name: dev
        # TODO: Configure secrets. Create a Snowflake secret object for each value, then uncomment:
        # secrets:
        #   - snowflake_secret: <database>.<schema>.<secret_name>
        #     env_var_name: DBT_ENV_SECRET_GIT_TOKEN
        env:
          # ... plain env vars ...
  ```
  In the output summary, list all skipped secrets and tell the user they need to:
  1. Create Snowflake secret objects (`CREATE SECRET ... TYPE = GENERIC_STRING`)
  2. Grant `READ` on each secret to the executing role
  3. Uncomment and fill in the `secrets:` block
  4. Attach an External Access Integration at deploy time

- **Interactive mode:** Ask the user about each detected secret:
  - What Snowflake secret object should it reference? (existing or new)
  - If new: guide creation of `CREATE SECRET`, grant `READ`, and set up EAI

> ⚠️ **MANDATORY CHECKPOINT — STOP HERE:**
> Present all objects to be created/modified:
> - `CREATE SECRET <db>.<schema>.<secret_name> TYPE = GENERIC_STRING SECRET_STRING = '...';`
> - `GRANT READ ON SECRET <db>.<schema>.<secret_name> TO ROLE <role>;`
> - Any EAI changes (CREATE or ALTER)
>
> **Wait for explicit approval (Yes/No/Modify). NEVER proceed without user confirmation.**

  - Add the proper `secrets:` entry to env.yml

**Detection rules — treat as a secret if ANY of these match:**
- Variable name contains `SECRET`, `TOKEN`, `PASSWORD`, `CREDENTIAL`, `KEY`, `PAT` (case-insensitive)
- Variable name already has `DBT_ENV_SECRET_` prefix
- Variable is used in `packages.yml` as part of a git URL (e.g., `https://{{env_var('...')}}@github.com/...`)
- Variable value (from terminal or default arg) looks like a credential (starts with `ghp_`, `glpat-`, `AKIA`, contains 40+ hex chars, etc.)

**Never do this:**
```yaml
# ❌ WRONG — exposes secret value as plain text in env.yml
env:
  DBT_ENV_SECRET_GIT_TOKEN: "ghp_abc123..."
```

### Step 2: Build Variable Mapping

Create a mapping from old names to new `DBT_`-prefixed UPPERCASE names:

| Old Name | New Name | Source Value for env.yml |
|----------|----------|------------------------|
| `SNOWFLAKE_ROLE` | `DBT_CURRENT_ROLE` | `"{{ select CURRENT_ROLE() }}"` |
| `SNOWFLAKE_DATABASE` | `DBT_CURRENT_DB` | literal or SQL |
| `SNOWFLAKE_WAREHOUSE` | `DBT_CURRENT_WH` | `"{{ select CURRENT_WAREHOUSE() }}"` |
| `SNOWFLAKE_SCHEMA` | `DBT_CURRENT_SCHEMA` | `"{{ select CURRENT_SCHEMA() }}"` |
| `START_DATE` | `DBT_START_DATE` | value from `echo $START_DATE` or default arg |
| `my_schema` | `DBT_MY_SCHEMA` | value from context |

**To determine the value for each variable in env.yml:**
1. **`env_var()` second argument** — e.g., `env_var('START_DATE', '2024-01-01')` → use `"2024-01-01"` as the env.yml value
2. **Terminal value** — run `echo $VAR_NAME` to get the current value
3. **If it maps to a Snowflake context** (account, role, warehouse, user, schema, database) → use a `"{{ select CURRENT_X() }}"` expression
4. **If both are empty** — use a placeholder and tell the user

### Step 3: Rename env_var() References

Update all `env_var()` calls to use the new `DBT_`-prefixed names:

**In profiles.yml:**
```yaml
# Before
role: "{{ env_var('SNOWFLAKE_ROLE') }}"
# After
role: "{{ env_var('DBT_CURRENT_ROLE') }}"
```

**In SQL model/macro files:**
```sql
-- Before
SELECT * FROM table WHERE date >= '{{ env_var("START_DATE") }}'
-- After
SELECT * FROM table WHERE date >= '{{ env_var("DBT_START_DATE") }}'
```

**In dbt_project.yml:**
```yaml
# Fields like vars: use env_var() with DBT_ prefix:
# Before
vars:
  start_date: "{{ env_var('START_DATE', '2024-01-01') }}"
# After
vars:
  start_date: "{{ env_var('DBT_START_DATE', '2024-01-01') }}"
```

### Step 4: Add env variables to env.yml

Add all mapped variables to the `env:` section of the `env.yml` created in General Step 3.

### Step 5: Provide Execution Examples

After migration, provide examples showing how to execute with environments and overrides.

#### Snowflake CLI Example (snow dbt execute — requires CLI >= 3.22)

```bash
# Run with a specific environment
snow dbt execute --env prod my_project run

# Override specific variables
snow dbt execute --env-vars '{"DBT_START_DATE": "2024-06-01", "DBT_CURRENT_DB": "staging_db"}' my_project run

# Use shell environment variables (reads all DBT_-prefixed shell vars)
snow dbt execute --use-shell-env-vars my_project run
```

#### SQL Fallback (if CLI is older than 3.22)

```sql
-- Run with a specific environment
EXECUTE DBT PROJECT my_database.my_schema.my_project
  ARGS = 'run'
  ENVIRONMENT = 'prod';

-- Override specific variables for a single run
EXECUTE DBT PROJECT my_database.my_schema.my_project
  ARGS = 'run'
  ENV_VARS = ('DBT_START_DATE' = '2024-06-01', 'DBT_CURRENT_DB' = 'staging_db');
```

### Step 6: Output Summary

After completing migration, output a summary:

```
Migration complete for project: <project_name>

Created env.yml with X environment variables across Y environments.
Renamed Z env_var() references to use DBT_ prefix.

Execution options:

**SQL (EXECUTE DBT PROJECT):**
EXECUTE DBT PROJECT <database>.<schema>.<project_name>
  ARGS = 'run'
  ENVIRONMENT = 'dev';

**Snowflake CLI:**
snow dbt execute --env dev <project_name> run

**Override variables at runtime:**
EXECUTE DBT PROJECT <database>.<schema>.<project_name>
  ARGS = 'run'
  ENV_VARS = ('DBT_VAR1' = 'value1', 'DBT_VAR2' = 'value2');
```

### Checklist for Case 1

- [ ] Scan all `.yml`, `.yaml`, `.sql` files for `env_var()`
- [ ] Build variable mapping (old name → new `DBT_` prefixed UPPERCASE name)
- [ ] Create `env.yml` with all variables and at least one environment (dev)
- [ ] Rename all `env_var()` calls in profiles.yml, `dbt_project.yml`, packages.yml, models, macros, schema files
- [ ] Provide SQL and CLI execution examples
- [ ] Output ready-to-use commands

---

## Case 2: Private Git Packages (secrets)

⚠️ **MANDATORY CHECKPOINT:** Before creating any Snowflake objects (SECRET, NETWORK RULE, EAI), list all objects to be created and get explicit user confirmation. Wait for explicit user approval (Yes/No/Modify). NEVER proceed without confirmation.

**Load `references/private-git-packages.md`** for the full setup workflow.

---

## Reference: env.yml Structure

```yaml
env_config:                          # Required top-level key
  default_environment: dev           # Used when no environment specified at runtime
  environments:
    - name: dev                      # Environment name (case sensitive)
      secrets:                       # Optional: Snowflake secrets → masked env vars
        - snowflake_secret: db.schema.secret_name
          env_var_name: DBT_ENV_SECRET_MY_TOKEN
      env:                           # Optional: plain or SQL-computed env vars
        DBT_KEY: "plain_value"
        DBT_DYNAMIC: "{{ select CURRENT_USER() }}"
```

### Supported SQL in env: values

- Context functions: `CURRENT_USER()`, `CURRENT_ROLE()`, `CURRENT_DATABASE()`, `CURRENT_SCHEMA()`, `CURRENT_WAREHOUSE()`
- Date/time: `CURRENT_TIMESTAMP()`, `DATE_TRUNC(...)`, `DATEADD(...)`, etc.
- Any query returning one row, one VARCHAR column: `SELECT col FROM table LIMIT 1`
- Stored procedures: `SELECT * FROM TABLE(my_proc(...))`
- String ops and concatenation: `CURRENT_USER() || '_schema'`

### NOT supported in env: values

- Macros (`{{ ref(...) }}`, `{{ source(...) }}`)
- Jinja loops/conditionals (`{% for ... %}`, `{% if ... %}`)
- `CURRENT_SESSION()`, `CURRENT_CLIENT()`, `CURRENT_IP_ADDRESS()`

### Value Precedence (highest to lowest)

1. `--env-vars` / `EXECUTE ... ENV_VARS` (highest)
2. Shell variables (only with `--use-shell-env-vars`, reads `DBT_*` excluding `DBT_ENV_SECRET_*`)
3. `env.yml` selected environment (lowest)

### Environment Selection (highest to lowest)

1. `ENVIRONMENT = '...'` on `EXECUTE DBT PROJECT`
2. `DEFAULT_ENVIRONMENT` on the dbt project object
3. `default_environment` in `env.yml`

Use `NO_ENV` to run without any environment.

### File location and size

- Place `env.yml` in the root of your dbt project, next to `dbt_project.yml`
- 2 MB limit (roughly 12,000 lines)

---

## Stopping Points

- ⚠️ Case 2 (Private Git Packages): Before creating Snowflake objects (SECRET, NETWORK RULE, EAI), list all objects and get explicit user confirmation.

## Output

- Modified project files in the `_snowflake` copy (original project left untouched)
- Updated `profiles.yml` with `DBT_`-prefixed env_var() calls (password/auth fields removed)
- New `env.yml` file with environments and variables
- Execution examples (SQL and CLI) with ready-to-use commands

## Next Steps

After migration, ask the user if they would like to deploy the migrated project to Snowflake. If yes, load `deploy/SKILL.md` and proceed with deployment.
