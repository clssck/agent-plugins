---
name: dbt-deploy
description: "Deploy dbt projects to Snowflake"
parent_skill: dbt-projects-on-snowflake
---

# Deploy dbt Project

## When to Load

Main skill routes here for: "deploy", "create project", "upload dbt"

## Prerequisites

1. **Target schema must exist:**
   ```sql
   CREATE SCHEMA IF NOT EXISTS my_db.my_schema;
   ```

2. **profiles.yml requirements** - Load `references/profiles-yml.md` for details:
   - Do NOT use `env_var()` - dbt runs inside Snowflake
   - Do NOT include `password` or `authenticator` fields

3. **Minimum project structure:**
   ```
   my_dbt_project/
   ├── dbt_project.yml
   ├── profiles.yml      ← MUST be here, inside the project directory
   └── models/
       └── my_model.sql
   ```

   **IMPORTANT:** `profiles.yml` MUST be placed inside the dbt project directory (alongside `dbt_project.yml`), NOT in `~/.dbt/`. The `snow dbt deploy` command bundles `profiles.yml` from the project directory into the deployed project.

## Workflow

### Step 1: Validate Project

**Goal:** Ensure project is ready for deployment

**Actions:**
1. Check `dbt_project.yml` exists
2. Check `profiles.yml` exists and has no `env_var()` or `password` fields
3. Check `models/` directory has at least one `.sql` file

**If validation fails due to `env_var()` or `password` in profiles.yml / project files:**
This is a migration case. Load `migrate/SKILL.md` and run the migration workflow first, then return here to deploy the migrated project.

### Step 2: Create Target Schema

**Goal:** Ensure target schema exists

```sql
CREATE SCHEMA IF NOT EXISTS <database>.<schema>;
```

### Step 3: Check for External Access Requirements

**Goal:** Determine if the project needs external network access

**When is external access needed?**
If the project needs to reach external hosts at runtime (e.g., to resolve packages, call APIs, etc.), it needs an **External Access Integration (EAI)** attached at deploy time.

**Actions:**
1. Determine whether the project requires external network access
2. If yes, find an available EAI:
   ```sql
   SHOW EXTERNAL ACCESS INTEGRATIONS;
   ```
3. Pick the integration that grants access to the required hosts

### Step 4: Deploy Project

**Goal:** Upload project to Snowflake

**Command (works for new projects AND updates):**
```bash
snow dbt deploy <project_name> \
  --source <path_to_project> \
  --database <database> \
  --schema <schema> \
  --external-access-integration <integration_name>  # if project needs external network access
```

**Parameters:**
| Parameter | Description |
|-----------|-------------|
| `<project_name>` | Identifier for the project (required) |
| `--source` | Path to dbt project directory |
| `--database` | Target database |
| `--schema` | Target schema |
| `--external-access-integration` | Name of an External Access Integration (required if project needs external network access) |

**Example - Deploy without external packages:**
```bash
snow dbt deploy MY_PROJECT --source /path/to/project --database DB --schema SCHEMA
```

**Example - Deploy with external access:**
```bash
snow dbt deploy MY_PROJECT --source /path/to/project --database DB --schema SCHEMA \
  --external-access-integration MY_EAI
```

**Example - Update (creates VERSION$2, VERSION$3, etc.):**
```bash
# Same command! Just point to updated source
snow dbt deploy MY_PROJECT --source /path/to/updated_project --database DB --schema SCHEMA \
  --external-access-integration MY_EAI
```

### Step 5: Verify Deployment

**Goal:** Confirm project was deployed with correct version

```bash
snow dbt list --in schema <schema> --database <database>
```

> `--database` defaults to the connection's database if omitted. `--in schema` defaults to all schemas if omitted.

Check versions:
```sql
SHOW VERSIONS IN DBT PROJECT <database>.<schema>.<project_name>;
```

## Stopping Points

- ⚠️ Step 1: If profiles.yml has invalid fields

## Output

Deployed dbt project in Snowflake, ready for execution.

## Next Steps

After deployment, load `execute/SKILL.md` to run models.

**Important:** If you fixed an incremental model (changed `is_incremental()` logic, unique key, or strategy), you MUST execute with `--full-refresh` to rebuild the table from scratch. A normal run only processes new rows and won't fix data built by the old broken logic.
