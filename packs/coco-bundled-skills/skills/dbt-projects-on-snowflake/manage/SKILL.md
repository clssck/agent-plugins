---
name: dbt-manage
description: "Manage dbt projects in Snowflake (list, rename, drop, describe, add version)"
parent_skill: dbt-projects-on-snowflake
---

# Manage dbt Projects

## When to Load

Main skill routes here for: "list", "show", "rename", "drop", "delete", "describe", "add version", "new version", "update version"

## Quick Reference

```sql
-- Add a new version from staged files (most common)
ALTER DBT PROJECT <db>.<schema>.<project> ADD VERSION [<alias>] FROM '@<db>.<schema>.<stage>/path';

-- List projects
SHOW DBT PROJECTS IN SCHEMA <db>.<schema>;

-- Describe project
DESCRIBE DBT PROJECT <db>.<schema>.<project>;

-- Show versions
SHOW VERSIONS IN DBT PROJECT <db>.<schema>.<project>;

-- Rename (use fully qualified names for BOTH)
ALTER DBT PROJECT <db>.<schema>.<old> RENAME TO <db>.<schema>.<new>;

-- Drop
DROP DBT PROJECT [IF EXISTS] <db>.<schema>.<project>;
```

## Workflow

### List Projects

**Goal:** View deployed dbt projects

```bash
# List in a database
snow dbt list --in database my_db

# List in a schema (use --database separately; defaults to connection's database if omitted)
snow dbt list --in schema my_schema --database my_db

# Filter by pattern
snow dbt list --like "my_%"
```

**SQL alternative** (supports `db.schema` notation directly):
```sql
SHOW DBT PROJECTS IN SCHEMA my_db.my_schema;
```

### Describe Project

**Goal:** View project details

```sql
DESCRIBE DBT PROJECT my_db.my_schema.my_project;
```

Key properties returned by DESCRIBE:

| Property | Description |
|----------|-------------|
| `default_version_location_uri` | `snow://dbt/...` URI pointing to the deployed project's files |
| `default_version_source_location_uri` | Original source location (workspace or stage) |

### Access Deployed Project Files

**Goal:** List and download the actual model SQL, YAML, and config files from a deployed project.

Use the `default_version_location_uri` from DESCRIBE with LIST and GET:

```sql
-- Step 1: Get the snow:// URI
DESCRIBE DBT PROJECT my_db.my_schema.my_project;
-- Look for default_version_location_uri, e.g.:
-- snow://dbt/MY_DB.MY_SCHEMA.MY_PROJECT/versions/version$2/

-- Step 2: List files in the deployed project
LIST 'snow://dbt/MY_DB.MY_SCHEMA.MY_PROJECT/versions/version$N/';
LIST 'snow://dbt/MY_DB.MY_SCHEMA.MY_PROJECT/versions/version$N/models/';

-- Step 3: Download individual files
GET 'snow://dbt/MY_DB.MY_SCHEMA.MY_PROJECT/versions/version$N/models/marts/fct_orders.sql'
    'file:///tmp/project_files/';

-- Step 3 (alt): Download entire project as ZIP
GET 'snow://dbt/MY_DB.MY_SCHEMA.MY_PROJECT/versions/version$N/dbt_artifacts.zip'
    'file:///tmp/project_files/';
```

**Notes:**
- The `snow://dbt/` URI is only obtainable from DESCRIBE output — it cannot be guessed
- `GET` requires `file://` prefix with an absolute local path
- `dbt_artifacts.zip` is created at deploy time and contains the full project
- `@stage` notation does NOT work for dbt project internal stages — use the `snow://dbt/` URI
- `snow stage copy` (Snow CLI) does NOT support `snow://` URIs — use SQL GET

### Rename Project

**Goal:** Rename an existing dbt project

**⚠️ MANDATORY CHECKPOINT:** Confirm new name with user before executing.

**CRITICAL:** Use fully qualified names for BOTH old and new names to keep project in same schema:

```sql
ALTER DBT PROJECT my_db.my_schema.old_name RENAME TO my_db.my_schema.new_name;
```

**Why fully qualified?** Unqualified new name moves project to session's current schema context.

### Add Version

**Goal:** Add a new version to an existing dbt project from updated source files

dbt projects are versioned (VERSION$1, VERSION$2, etc.). Each version is immutable. To update a project, add a new version.

**Syntax:**
```sql
ALTER DBT PROJECT <db>.<schema>.<project_name>
  ADD VERSION [<version_alias>]
  FROM '<source_location>';
```
**Version aliases** are optional human-readable names (e.g., `v2_release`, `hotfix_20240115`). The version identifier (VERSION$2, VERSION$3, etc.) is auto-incremented.

**Examples:**
```sql
-- Add version from a stage (most common)
ALTER DBT PROJECT my_db.my_schema.my_project
  ADD VERSION v2_release
  FROM '@my_db.my_schema.dbt_stage/updated_project';

-- Add version without alias (just gets VERSION$N)
ALTER DBT PROJECT my_db.my_schema.my_project
  ADD VERSION
  FROM '@my_db.my_schema.dbt_stage/updated_project';
```

**Source location formats:**
- Stage: `'@db.schema.stage/path'`
- Another project: `'snow://dbt/db.schema.project/versions/last'`
- Workspace: `'snow://workspace/user$.public."workspace"/versions/live'`

**Verify versions after adding:**
```sql
SHOW VERSIONS IN DBT PROJECT <db>.<schema>.<project>;
```

### Drop Project

**Goal:** Delete a dbt project

**⚠️ MANDATORY CHECKPOINT:** Confirm deletion with user before executing.

```sql
DROP DBT PROJECT [IF EXISTS] my_db.my_schema.my_project;
```

**Note:** This removes the project definition. Tables/views created by the project remain.


### Set/Unset Project Properties

**Goal:** Modify project configuration (comment, default target, external access)

**No CLI support** - Use SQL directly.

```sql
-- Set comment
ALTER DBT PROJECT my_db.my_schema.my_project SET COMMENT = 'My description';

-- Set default target
ALTER DBT PROJECT my_db.my_schema.my_project SET DEFAULT_TARGET = 'prod';

-- Set external access integrations
ALTER DBT PROJECT my_db.my_schema.my_project SET EXTERNAL_ACCESS_INTEGRATIONS = (my_integration);

-- Unset properties
ALTER DBT PROJECT my_db.my_schema.my_project UNSET COMMENT;
ALTER DBT PROJECT my_db.my_schema.my_project UNSET DEFAULT_TARGET;
ALTER DBT PROJECT my_db.my_schema.my_project UNSET EXTERNAL_ACCESS_INTEGRATIONS;
```

## SQL Reference

| Operation | SQL |
|-----------|-----|
| List | `SHOW DBT PROJECTS IN SCHEMA db.schema;` |
| Describe | `DESCRIBE DBT PROJECT db.schema.project;` |
| Rename | `ALTER DBT PROJECT db.schema.old RENAME TO db.schema.new;` |
| Drop | `DROP DBT PROJECT [IF EXISTS] db.schema.project;` |
| Add Version | `ALTER DBT PROJECT db.schema.project ADD VERSION [alias] FROM '<source>';` |

## CLI Reference

```bash
snow dbt list [--database <db>] [--in database <db>] [--in schema <schema>] [--like <pattern>]
```

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--database` | Database context | Connection default |
| `--in database` | List projects in database | — |
| `--in schema` | List projects in schema (single name, not `db.schema`) | All schemas |
| `--like` | SQL LIKE pattern filter | — |

## Stopping Points

- ⚠️ Before RENAME: Confirm new project name
- ⚠️ Before DROP: Confirm user wants to delete

## Output

- List of projects with names and schemas
- Project details from DESCRIBE
- Confirmation of rename/drop operations
