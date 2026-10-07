# snow dbt CLI Reference

Quick reference for all `snow dbt` commands.

## Commands Overview

| Command | Description |
|---------|-------------|
| `snow dbt deploy` | Deploy a dbt project to Snowflake |
| `snow dbt execute` | Execute dbt commands (show, run, test, build, seed, snapshot) |
| `snow dbt list` | List deployed dbt projects |

## Deploy

```bash
snow dbt deploy NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `NAME` | Project name (required) |
| `--source PATH` | Path to dbt project directory |
| `--database DB` | Target database |
| `--schema SCHEMA` | Target schema |
| `--external-access-integration NAME` | EAI for external network access (required if project needs to reach external hosts) |
| `--default-env NAME` | Sets the default environment for the dbt project object (requires CLI >= 3.22) |
| `--default-target NAME` | Sets the default target for the dbt project object |
| `--env-file-dir PATH` | Path to directory containing an `env.yml` (overrides the one in project root; requires CLI >= 3.22) |
| `--force` | Overwrite existing project |
| `-c, --connection` | Snowflake connection name |

**Examples:**
```bash
# Deploy without external packages
snow dbt deploy my_project --source ./my_dbt --database ANALYTICS --schema DBT_MODELS

# Deploy with external access and default environment
snow dbt deploy my_project --source ./my_dbt --database ANALYTICS --schema DBT_MODELS \
  --external-access-integration MY_EAI --default-env prod

# Deploy with env.yml from a different directory
snow dbt deploy my_project --source ./my_dbt --env-file-dir ./environments
```

## Execute

```bash
snow dbt execute [FLAGS] NAME COMMAND [dbt_options]
```

**CRITICAL:** Flags must come BEFORE the project name.

| Option | Description |
|--------|-------------|
| `-c, --connection` | Snowflake connection name |
| `--database` | Target database |
| `--schema` | Target schema |
| `--env NAME` | Select environment from env.yml for this execution (requires CLI >= 3.22) |
| `--env-vars JSON` | Inline key/value overrides (JSON object) — highest precedence (requires CLI >= 3.22) |
| `--use-shell-env-vars` | Pull `DBT_`-prefixed shell env vars into the run (requires CLI >= 3.22) |
| `--external-access-integration NAME` | EAI to attach for this execution (required if project has a `secrets:` block in env.yml) |
| `--dbt-version VER` | Run with a specific dbt version |
| `NAME` | Project name |
| `COMMAND` | dbt command (show/run/test/build/seed/snapshot) |

> **Note:** `--env`, `--env-vars`, and `--use-shell-env-vars` require Snowflake CLI >= 3.22. If using an older CLI, use the SQL `EXECUTE DBT PROJECT` syntax with `ENVIRONMENT` and `ENV_VARS` parameters instead.

> **Tip:** `--env-vars` works standalone without `--env`. If no environment is specified, the project's default environment (or none) is used and overrides still apply.

**Examples:**
```bash
# Preview model output (no materialization)
snow dbt execute -c default --database DB --schema SCHEMA my_project show --select my_model

# Run all models
snow dbt execute -c default --database DB --schema SCHEMA my_project run

# Run with a specific environment
snow dbt execute --env prod my_project run

# Override a single environment variable
snow dbt execute --env-vars '{"DBT_DATABASE": "staging_db"}' my_project run

# Override multiple environment variables
snow dbt execute --env-vars '{"DBT_DATABASE": "staging_db", "DBT_START_DATE": "2024-01-01", "DBT_SCHEMA_SUFFIX": "_v2"}' my_project run

# Execute with EAI (required when env.yml has a secrets: block)
snow dbt execute --external-access-integration MY_EAI --env prod my_project run

# Use shell environment variables (reads all DBT_-prefixed vars)
snow dbt execute --use-shell-env-vars my_project run

# Run specific models
snow dbt execute -c default --database DB --schema SCHEMA my_project run --select my_model

# Run tests
snow dbt execute -c default --database DB --schema SCHEMA my_project test

# Build everything
snow dbt execute -c default --database DB --schema SCHEMA my_project build
```

## EXECUTE DBT PROJECT (SQL)

```sql
EXECUTE DBT PROJECT <database>.<schema>.<project_name>
  [DBT_VERSION = '<version>']
  [ENVIRONMENT = '<env_name>']
  [ENV_VARS = ('<DBT_KEY>' = '<value>', ...)]
  [EXTERNAL_ACCESS_INTEGRATIONS = (<eai_name>)]
  ARGS = '<dbt_command>';
```

| Parameter | Description |
|-----------|-------------|
| `DBT_VERSION` | Optional. Run with a specific dbt version |
| `ENVIRONMENT` | Optional. Select environment from env.yml (overrides DEFAULT_ENVIRONMENT) |
| `ENV_VARS` | Optional. Override individual variables (highest precedence). Values can be SQL, literals, or session vars (`$var`) |
| `EXTERNAL_ACCESS_INTEGRATIONS` | Optional. Attach EAI for this execution (required if env.yml has a `secrets:` block) |
| `ARGS` | Required. The dbt command string (e.g., `'run'`, `'run --select my_model'`) |

**Examples:**
```sql
-- Basic run
EXECUTE DBT PROJECT db.schema.my_project ARGS = 'run';

-- With environment selection
EXECUTE DBT PROJECT db.schema.my_project
  ARGS = 'run'
  ENVIRONMENT = 'prod';

-- With variable overrides
EXECUTE DBT PROJECT db.schema.my_project
  ARGS = 'run'
  ENV_VARS = ('DBT_CURRENT_DB' = 'staging_db', 'DBT_START_DATE' = '2024-01-01');

-- With SQL-based override
EXECUTE DBT PROJECT db.schema.my_project
  ARGS = 'run'
  ENV_VARS = ('DBT_END_DATE' = '{{ select CURRENT_TIMESTAMP()::string }}');

-- Run without any environment
EXECUTE DBT PROJECT db.schema.my_project
  ARGS = 'run'
  ENVIRONMENT = 'NO_ENV';
```

## List

```bash
snow dbt list [OPTIONS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--database DB` | Database context | Connection default |
| `--in database DB` | List projects in database | — |
| `--in schema SCHEMA` | List projects in schema (single name, not `DB.SCHEMA`) | All schemas |
| `--like PATTERN` | Filter by SQL LIKE pattern | — |

> **Note:** `--in schema` takes a single schema name. Use `--database` separately to specify the database. If `--database` is omitted, the connection's default database is used.

**Examples:**
```bash
# List in schema (specify database separately)
snow dbt list --in schema DBT_MODELS --database ANALYTICS

# List in schema using connection's default database
snow dbt list --in schema DBT_MODELS

# Filter by pattern
snow dbt list --like "prod_%"
```
