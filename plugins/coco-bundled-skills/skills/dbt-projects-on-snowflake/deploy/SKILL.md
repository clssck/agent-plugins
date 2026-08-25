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
   - `env_var()` is supported when backed by an `env.yml` file (variable names must be `DBT_`-prefixed UPPERCASE)
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
2. Check `profiles.yml` exists and has no `password`/`authenticator` fields
3. Check `models/` directory has at least one `.sql` file
4. If `profiles.yml` uses `env_var()`, verify an `env.yml` exists in the project root with the referenced variables

**If validation fails due to `password` in profiles.yml:**
Remove auth fields. Load `migrate/SKILL.md` if a full migration workflow is needed.

**If `env_var()` is used without a corresponding `env.yml`:**
The user needs to create an `env.yml`. Load `migrate/SKILL.md` for the full migration workflow.

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

### Step 3b: Private Git Packages (secrets)

**When:** `packages.yml` uses `env_var()` to inject a git token for private repositories.

⚠️ **MANDATORY CHECKPOINT:** Before creating any Snowflake objects (SECRET, NETWORK RULE, EAI), list all objects to be created and get explicit user confirmation. Wait for explicit user approval (Yes/No/Modify). NEVER proceed without confirmation.

**Load `references/private-git-packages.md`** for the full setup (SECRET creation, EAI, env.yml secrets section, packages.yml update, deploy command).

⚠️ **CRITICAL — When using an EXISTING EAI:** After creating the secret, you MUST ALTER the EAI to include the new secret in `ALLOWED_AUTHENTICATION_SECRETS`. This step is mandatory — without it, the secret cannot be resolved at runtime even though it is referenced in env.yml.

```sql
-- 1. Check current state
DESCRIBE EXTERNAL ACCESS INTEGRATION <eai_name>;
-- 2. ALTER to add the new secret (skip only if ALLOWED_AUTHENTICATION_SECRETS = ALL)
ALTER EXTERNAL ACCESS INTEGRATION <eai_name>
  SET ALLOWED_AUTHENTICATION_SECRETS = (<database>.<schema>.<secret_name>);
```

If the EAI already lists other secrets, append yours: `SET ALLOWED_AUTHENTICATION_SECRETS = (<existing>, <new>)`.

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
| `--default-env` | Sets the default environment for the dbt project object (requires CLI >= 3.22; fallback: use `ALTER DBT PROJECT ... SET DEFAULT_ENVIRONMENT`) |
| `--env-file-dir` | Path to directory containing an `env.yml` (overrides the one in project root; requires CLI >= 3.22) |

**Example - Deploy without external packages:**
```bash
snow dbt deploy MY_PROJECT --source /path/to/project --database DB --schema SCHEMA
```

**Example - Deploy with external access:**
```bash
snow dbt deploy MY_PROJECT --source /path/to/project --database DB --schema SCHEMA \
  --external-access-integration MY_EAI --default-env dev
```

**Example - Deploy with private git packages (secrets):**

The deploy command is identical to the external access example above. The difference is in the prerequisites: you must have a Snowflake SECRET + `secrets:` section in `env.yml` (see Step 3b above).

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
