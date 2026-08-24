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
| `--force` | Overwrite existing project |
| `-c, --connection` | Snowflake connection name |

**Examples:**
```bash
# Deploy without external packages
snow dbt deploy my_project --source ./my_dbt --database ANALYTICS --schema DBT_MODELS

# Deploy with external access
snow dbt deploy my_project --source ./my_dbt --database ANALYTICS --schema DBT_MODELS \
  --external-access-integration MY_EAI
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
| `NAME` | Project name |
| `COMMAND` | dbt command (show/run/test/build/seed/snapshot) |

**Examples:**
```bash
# Preview model output (no materialization)
snow dbt execute -c default --database DB --schema SCHEMA my_project show --select my_model

# Run all models
snow dbt execute -c default --database DB --schema SCHEMA my_project run

# Run specific models
snow dbt execute -c default --database DB --schema SCHEMA my_project run --select my_model

# Run tests
snow dbt execute -c default --database DB --schema SCHEMA my_project test

# Build everything
snow dbt execute -c default --database DB --schema SCHEMA my_project build
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
