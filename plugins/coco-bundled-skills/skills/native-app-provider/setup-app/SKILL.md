---
name: setup-native-app
description: "Prepare local files for a new Snowflake Native App: write manifest.yml, setup script, and README. No SQL execution — deployment is handled by deploy-test. Triggers: create native app, new app, write manifest, setup script, prepare app files, scaffold app."
parent_skill: native-app-provider
---

# Prepare a Snowflake Native App

> **⚠️ MANDATORY**: If your system prompt mentions Snowsight, load [`../references/native-apps-snowsight.md`](../references/native-apps-snowsight.md) before doing anything else.

## When to Load

From the root `native-app-provider` skill when user wants to create a new native app from scratch. This skill prepares all local files; deployment to Snowflake is handled by the `deploy-test` skill.

## Workflow

### Step 1: Gather Requirements

**Ask** the user:

```
To set up your native app, I need:
1. **Application package name** (e.g., "hello_snowflake_pkg"): The package that holds app files and versions
2. **Purpose**: What does this app do? (data sharing, analytics, ML model, etc.)
3. **Distribution**: Internal (within org) or external (Snowflake Marketplace)?
4. **Project directory**: Where should I create the app files? (e.g., "./my_app" or "/Users/you/projects/my_app")
```

**STOP**: Wait for user response before proceeding.

### Step 2: Create Initial Files

After gathering requirements, check the project directory and choose a path:

```bash
ls <project_dir>/
```

#### Path A: Snow CLI (`snow_cli_available` AND project directory has `snowflake.yml` or user explicitly indicates they want to use the Snow CLI)

If `snowflake.yml` **already exists**, skip `snow init` — proceed to Step 3.

If the project directory is **empty**, scaffold it with Snow CLI. Choose a template based on the app's needs — if unsure, use `app_basic` and customize in Step 3:

| Template | Use When |
|----------|----------|
| `app_basic` | Minimal app — SQL-only logic (stored procedures, views, UDFs). No UI, no containers. |
| `app_streamlit_python` | App with a Streamlit UI and Python extension code. Includes test infrastructure. |
| `app_streamlit_java` | App with a Streamlit UI and Java extension code (Maven build). |
| `app_streamlit_js` | App with a Streamlit UI and JavaScript extension code. |
| `app_spcs_basic` | Containerized app on Snowpark Container Services (SPCS). Includes Dockerfile and build script. |

```bash
snow init <project_dir> --template <template_name> --no-interactive
```

> **Important**: The target directory must not already exist — `snow init` creates it. Do not run `mkdir` before `snow init`, or it will fail with "directory already exists". The `--no-interactive` flag prevents prompts that can hang in non-interactive environments.

The scaffolded project structure depends on the template. For `app_basic`:

```
<project_dir>/
  snowflake.yml          ← project definition (CLI reads this)
  .gitignore
  README.md              ← project-level README
  app/
    manifest.yml         ← app manifest
    setup_script.sql     ← setup script (runs on install/upgrade)
    README.md            ← consumer-facing README
```

Other templates add more files (e.g., `src/` for extension code, `service/` for containers) but all share the same `snowflake.yml` + `app/` core structure.

#### Path B: Manual (CLI not available, or files exist without `snowflake.yml`)

Create the following files by hand in `<project_dir>`:

**`manifest.yml`** — **Load** `../references/manifest-reference.md` if detailed field info is needed. Use `manifest_version: 2` for new apps.

Minimal manifest (no Streamlit, no containers):

```yaml
manifest_version: 2

version:
  name: v1
  label: "Version 1.0"
  comment: "Initial release"

artifacts:
  setup_script: scripts/setup.sql
  readme: README.md
```

With Streamlit:

```yaml
manifest_version: 2

version:
  name: v1
  label: "Version 1.0"

artifacts:
  setup_script: scripts/setup.sql
  readme: README.md
  default_streamlit: core.main_streamlit
```

With containers (SPCS):

```yaml
manifest_version: 2

version:
  name: v1
  label: "Version 1.0"

artifacts:
  setup_script: scripts/setup.sql
  readme: README.md
  container_services:
    images:
      - /<db>/<schema>/<repo>/<image_name>

configuration:
  grant_callback: app_schema.grant_callback

privileges:
  - CREATE COMPUTE POOL:
      description: "Required to create compute pools for the app"
  - BIND SERVICE ENDPOINT:
      description: "Required to expose service endpoints externally"
```

If the app needs consumer privileges or references, add:

```yaml
privileges:
  - <PRIVILEGE_NAME>:
      description: "Why the app needs this privilege"

references:
  - <reference_name>:
      label: "Display label for consumer"
      description: "Why this reference is needed"
      privileges:
        - SELECT
      object_type: TABLE
      register_callback: app_schema.register_callback
```

**`scripts/setup.sql`** — Create with a minimal template:

```sql
CREATE APPLICATION ROLE IF NOT EXISTS app_user;

CREATE OR ALTER VERSIONED SCHEMA core;
GRANT USAGE ON SCHEMA core TO APPLICATION ROLE app_user;
```

**`README.md`** — Create with app name and description.

### Step 3: Customize Files

Whether files came from `snow init` (Path A) or were created manually (Path B), review and edit them to match the user's requirements.

**If Snow CLI was used**, also load `../references/snowflake-yml-reference.md` and update **snowflake.yml** entity identifiers to match the desired package and app names.

**Manifest** (`manifest.yml`): Update based on user requirements — add privileges, references, version info, and other fields as needed. Load `../references/manifest-reference.md` for field details.

**Setup script** (`setup_script.sql` or `scripts/setup.sql`): This is the most critical file — errors here cause installation failures. Add application roles, procedures, views, and grants for the app's actual logic.

**Template setup script:**

```sql
-- Create an application role for consumers
CREATE APPLICATION ROLE IF NOT EXISTS app_user;

-- Create a versioned schema for app objects
CREATE OR ALTER VERSIONED SCHEMA core;
GRANT USAGE ON SCHEMA core TO APPLICATION ROLE app_user;

-- Example: Create a stored procedure
CREATE OR REPLACE PROCEDURE core.hello()
  RETURNS STRING
  LANGUAGE SQL
  EXECUTE AS OWNER
  AS
  BEGIN
    RETURN 'Hello from the native app!';
  END;
GRANT USAGE ON PROCEDURE core.hello() TO APPLICATION ROLE app_user;

-- If sharing data: create secure views over shared content
-- CREATE VIEW IF NOT EXISTS core.shared_view
--   AS SELECT * FROM shared_schema.shared_table;
-- GRANT SELECT ON VIEW core.shared_view TO APPLICATION ROLE app_user;
```

**Setup script rules:**
- Use `CREATE OR REPLACE` for schema-level objects in versioned schemas (functions, procedures, views). Use `CREATE IF NOT EXISTS` for account-level objects (EAI, security integrations, network rules, secrets) and for objects that may be modified by user input after installation. Application roles should always use `CREATE APPLICATION ROLE IF NOT EXISTS`.
- Always qualify objects with target schema (`core.hello()` not just `hello()`)
- **Never** use `USE DATABASE`, `USE SCHEMA`, or `USE ROLE` — these are not allowed in setup scripts
- **Never** create or invoke procedures that are `EXECUTE AS CALLER`
- Grant privileges to application roles, not account roles
- Use versioned schemas (`CREATE OR ALTER VERSIONED SCHEMA`) for stateless objects like code (functions/sprocs) and views that can be recreated by the setup script for every new patch. Versioned schemas support version pinning — long-running queries execute against the same version of objects for their entire lifecycle and won't see new versions or partially-applied upgrades if an upgrade happens while the query is running.

**If the setup script is large**, use modular scripts:

```sql
-- In scripts/setup.sql (primary)
EXECUTE IMMEDIATE FROM 'setup_schemas.sql';
EXECUTE IMMEDIATE FROM 'setup_procs.sql';
EXECUTE IMMEDIATE FROM 'setup_views.sql';
```

**README** (`README.md`): Update with app name, description, features, and getting-started instructions.

```markdown
# <App Name>

<Brief description of what this app does.>

## Features
- Feature 1
- Feature 2

## Getting Started
After installation, run the following to verify:
\`\`\`sql
CALL core.hello();
\`\`\`
```

**STOP**: Present all files to the user for review before proceeding.

## Project Structure

After this skill completes, the local project directory looks like:

```
<project_dir>/
├── manifest.yml
├── README.md
└── scripts/
    └── setup.sql
```

## Output

- `manifest.yml`, `scripts/setup.sql`, and `README.md` written to `<project_dir>`
- Ready to deploy and test — **load `deploy-test/SKILL.md`** to create the application package, upload files to stage, and install the app
