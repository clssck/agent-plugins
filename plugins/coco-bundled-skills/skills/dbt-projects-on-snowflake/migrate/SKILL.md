---
name: dbt-migration
description: "Migrate dbt projects to run on Snowflake. Triggers: migrate, env_var, environment variable, convert to var, migration, prepare for snowflake."
parent_skill: dbt-projects-on-snowflake
---

# Migrate dbt Project to Snowflake

## When to Load

Main skill routes here for: "migrate", "env_var", "environment variable", "convert to var", "migration", "prepare for snowflake"

## Overview

**This is an ACTION skill** - proceed with creation of dbt project. Do not just analyze and report.

This skill helps migrate existing dbt projects to run on Snowflake.

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

### Resolving env_var() Values

Whenever you replace an `env_var()` call with a literal value (in `profiles.yml`, `dbt_project.yml`, or `packages.yml`), resolve it using this priority order:

1. **`env_var()` second argument** — e.g., `env_var('START_DATE', '2024-01-01')` → use `"2024-01-01"`
2. **Terminal value** — **MUST** run `echo $VAR_NAME` in bash for every env var that lacks a second argument. Do NOT skip this step. Batch multiple variables in one command: `echo "SNOWFLAKE_ACCOUNT=$SNOWFLAKE_ACCOUNT SNOWFLAKE_ROLE=$SNOWFLAKE_ROLE ..."`
3. **If both are empty** (no second argument AND `echo` returned empty) — use `TODO_INSERT_<VAR_NAME>` placeholder and tell the user which values need to be filled in before deployment

### Step 2: Update profiles.yml

Update `profiles.yml` for Snowflake-hosted dbt:

**CRITICAL: Snowflake-hosted dbt does NOT support `env_var()` in profiles.yml!**

You must:
1. **Remove authentication fields** (`password`, `authenticator`, `private_key_path`, `private_key_passphrase`, `token`) - authentication is handled by the Snowflake session
2. **Keep all other fields** - do not remove fields like `database`, `warehouse`, `schema`, etc.
3. **Replace ALL `env_var()` calls with literal values** using the resolution priority above

**Before (local dbt with env_var and password):**
```yaml
account: "{{ env_var('SNOWFLAKE_ACCOUNT') }}"
user: "{{ env_var('SNOWFLAKE_USER') }}"
password: "{{ env_var('SNOWFLAKE_PASSWORD') }}"  # REMOVE this line
role: "{{ env_var('SNOWFLAKE_ROLE') }}"
...
```

**After (real values from `echo $VAR_NAME`, password removed):**
```yaml
account: "myorg-myaccount"      # from: echo $SNOWFLAKE_ACCOUNT
user: "dbt_user"                # from: echo $SNOWFLAKE_USER
role: "TODO_INSERT_SNOWFLAKE_ROLE"   # env var was empty - user must fill in before deployment
...
# password line removed
```

See `references/profiles-yml.md` for all requirements.

### Step 3: Check for Special Cases

After general steps, check if any special handling is needed:

| Case | Detect | Action |
|------|--------|--------|
| **env_var() in project** | `dbt_project.yml`, `packages.yml`, or models contain `env_var()` | Go to **Case 1** below |

---

## Case 1: env_var() Migration

### Why

**Snowflake does not currently support `env_var()` in dbt projects.** The deployment will fail for projects with `env_var()`.

**Important:** Not all files can use `var()` as a replacement. dbt parses `dbt_project.yml`, `packages.yml`, and `profiles.yml` **before** Jinja renders, so `vars` from `dbt_project.yml` do NOT work in these files. Also, Snowflake managed project doesn't support `--vars` to be provided during project creation. So only SQL models, schema.yml, macros, and other Jinja-rendered files support `vars` from `dbt_project.yml` for Snowflake managed dbt projects.

**Solution (two-tier):**
- **Pre-Jinja files** (`dbt_project.yml` config fields, `packages.yml`): Replace `env_var()` with **literal values** resolved from the terminal (same approach as profiles.yml in Step 2)
- **Jinja-rendered files** (`.sql` models, `schema.yml`, macros, snapshots): Convert `env_var()` to `var()` and pass values at runtime using `--vars`

### Step 1: Scan for env_var() Usage

Search project files (excluding `profiles.yml` which was handled in General Steps):

```bash
grep -r "env_var" <project_path> --include="*.yml" --include="*.yaml" --include="*.sql"
```

Common locations:
- `dbt_project.yml` - project-level variables and config
- `packages.yml` - package dependencies (e.g., private package URLs with tokens)
- `models/**/*.sql` - model files
- `macros/**/*.sql` - macro files
- `models/**/*.yml` - schema/docs files

### Step 2: Replace env_var() Calls

**CRITICAL: Different files require different handling!**

#### In `dbt_project.yml` (outside `vars:`) and `packages.yml` → Replace with LITERAL VALUES

These files are parsed before Jinja renders, so `var()` does NOT work here. Replace `env_var()` with literal values using the **resolution priority** from the General Steps section.

- **Do NOT inline secrets or tokens** (e.g., git tokens in `packages.yml`). If `env_var()` is used for credentials, flag it to the user — those need a different solution.

**Before (`dbt_project.yml` config):**
```yaml
name: 'my_project'
profile: "{{ env_var('DBT_PROFILE') }}"
```

**After:**
```yaml
name: 'my_project'
profile: "default"  # from: echo $DBT_PROFILE
```

#### In `dbt_project.yml` `vars:` section → Use PLAIN STRING defaults (NO Jinja)
**CRITICAL: Different handling for vars section vs everything else!**
The `vars:` section defines default values. Use simple strings, NOT `{{ var(...) }}` which causes infinite recursion.

Resolve values using the **resolution priority** from the General Steps section.

**Before:**
```yaml
# dbt_project.yml
vars:
  start_date: "{{ env_var('START_DATE', '2024-01-01') }}"
  environment: "{{ env_var('ENVIRONMENT') }}"
```

**After (CORRECT):**
```yaml
# Snowflake does not currently support env_var() in dbt projects.
# This project was updated to use vars instead. To override vars at runtime:
# CLI: snow dbt execute <project> run --vars '{"start_date": "2024-01-01", "environment": "dev"}'
# SQL: EXECUTE DBT PROJECT <name> ARGS = 'run --vars ''{"start_date": "2024-01-01", "environment": "dev"}''';

name: 'my_project'
# ... rest of config ...
vars:
  start_date: "2024-01-01"          # from env_var default argument
  environment: "TODO_INSERT_ENVIRONMENT"  # env var was empty - user must fill in
```

**IMPORTANT:** Always add a comment block at the top of `dbt_project.yml` explaining why vars are used (Snowflake doesn't support env_var) and showing how to override vars using both CLI and SQL syntax. Use 3 example variables from the project.

**WRONG (causes infinite recursion - DO NOT DO THIS):**
```yaml
# dbt_project.yml
vars:
  start_date: "{{ var('start_date') }}"  # WRONG! Infinite recursion!
```

#### In SQL model/macro files → Use `{{ var('key') }}`

In `.sql` files, you CAN use `{{ var('key') }}` to reference variables:

**Before (model.sql):**
```sql
SELECT * FROM table WHERE date >= '{{ env_var("START_DATE") }}'
```

**After (model.sql):**
```sql
SELECT * FROM table WHERE date >= '{{ var("start_date") }}'
```

### Step 3: Provide Execution Examples

After migration, provide examples showing how to pass variables at runtime.

#### SQL Example (EXECUTE DBT PROJECT)

The `--vars` syntax requires escaping single quotes inside the SQL string:

```sql
-- Project variables can be overridden during execution using --vars
EXECUTE DBT PROJECT my_database.my_schema.my_project
  ARGS = 'run --vars ''{"start_date": "2024-01-01", "environment": "prod", "debug": "false"}''';
```

**Syntax breakdown:**
- `ARGS = '...'` - SQL string containing the dbt command
- `''{"key": "value"}''` - Escaped single quotes around JSON object (use `''` to escape `'` in SQL)

#### Snowflake CLI Example (snow dbt execute)

The CLI syntax is simpler - just pass JSON directly:

```bash
# Project variables can be overridden using --vars flag
snow dbt execute my_project run --vars '{"start_date": "2024-01-01", "environment": "prod", "debug": "false"}'
```

### Step 4: Output Summary

After completing migration, output a summary with ready-to-use commands:

```
Migration complete for project: <project_name>

Found and converted X env_var() calls to var().

Project variables can be overridden during execution in the following ways:

**SQL (EXECUTE DBT PROJECT):**
EXECUTE DBT PROJECT <database>.<schema>.<project_name>
  ARGS = 'run --vars ''{"var1": "value1", "var2": "value2"}''';

**Snowflake CLI:**
snow dbt execute <project_name> run --vars '{"var1": "value1", "var2": "value2"}'
```

Include a ready-to-use command with all the project's migrated variable keys.

### Checklist for Case 1

- [ ] Scan all `.yml`, `.yaml`, `.sql` files for `env_var()`
- [ ] In `dbt_project.yml` (outside `vars:`) and `packages.yml`: Replace `env_var()` with literal values (use resolution priority)
- [ ] In `dbt_project.yml` `vars:` section: Replace `env_var('KEY')` with PLAIN STRING defaults (NOT `{{ var(...) }}`)
- [ ] **Add comment block at top of `dbt_project.yml`** explaining why vars are used (Snowflake doesn't support env_var) and showing how to override vars (CLI and SQL examples with 3 vars)
- [ ] In SQL model/macro files: Replace `env_var('KEY')` with `{{ var('key') }}`
- [ ] Provide SQL execution example with `--vars` syntax
- [ ] Provide CLI execution example with `--vars` syntax
- [ ] Output ready-to-use commands with all project variables

---

## Stopping Points

None - proceed with migration. The original files are preserved by creating a copy first (Step 1).

## Output

- Modified project files in the `_snowflake` copy (original project left untouched)
- Updated `profiles.yml` with actual values (or `TODO_INSERT_<VAR_NAME>` placeholders for unset variables)
- Execution examples (SQL and CLI) with ready-to-use commands (e.g., Case 1 includes `--vars` syntax with all project variable keys)

## Next Steps

After migration, ask the user if they would like to deploy the migrated project to Snowflake. If yes, load `deploy/SKILL.md` and proceed with deployment.
