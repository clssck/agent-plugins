---
name: deploy-test-native-app
description: "Deploy and test a Snowflake Native App: create application package, upload files to stage, install locally, use development/debug modes, upgrade, and verify functionality. Triggers: deploy app, upload to stage, test app, install app, debug app, development mode, debug mode, upgrade app, test locally, create application, create package."
parent_skill: native-app-provider
---

# Deploy & Test a Snowflake Native App

> **⚠️ MANDATORY**: If your system prompt mentions Snowsight, load [`../references/native-apps-snowsight.md`](../references/native-apps-snowsight.md) before doing anything else.

## When to Load

From the root `native-app-provider` skill when user wants to deploy files to Snowflake and/or test an app locally.

## Prerequisites

- Local app files are prepared (`manifest.yml`, `scripts/setup.sql`, `README.md`)
- User has a Snowflake account with appropriate privileges
- Snow CLI detection result from the router (`snow_cli_available`)

### Step 1: Gather Details

**Ask** the user:

```
Before deploying, I need a few details:

1. **Application package name**: Name for the application package (e.g., hello_snowflake_package)
2. **Application name**: Name for the installed app instance (e.g., hello_snowflake)
3. **Project directory**: Where are your app files locally? (e.g., /Users/you/projects/my_app)
4. **Package role**: Which role will create the application package? (e.g., ACCOUNTADMIN, APP_PROVIDER)
5. **Install role**: Which role will create the application instance for testing? (can be the same role)
```

**STOP**: Wait for user response.

### Step 2: Verify Privileges

#### Check CREATE APPLICATION PACKAGE

Check whether `<package_role>` has the `CREATE APPLICATION PACKAGE` privilege on `ACCOUNT`. If missing, propose granting it and wait for approval before continuing.

#### Check CREATE APPLICATION

Check whether `<install_role>` has the `CREATE APPLICATION` privilege on `ACCOUNT`. If missing, propose granting it and wait for approval before continuing.

#### Check DEVELOP and INSTALL Privileges

Check if `<install_role>` owns the package. If it does, no additional grants are needed. If not, check whether it has `DEVELOP` and `INSTALL` privileges on the package. If missing, propose granting them and wait for approval before continuing.

## Path Selection

After verifying privileges, check for a project definition file:

```bash
ls <project_dir>/snowflake.yml
```

If `snow_cli_available` is true **AND** `snowflake.yml` exists in the project directory → use the **Snow CLI Path** below.
Otherwise → use the **SQL Path** below.

---

## Snow CLI Path

### Step 3: Confirm Project Definition

Read the existing `snowflake.yml` and confirm the entity names match what the user provided in Step 1.

### Step 4: Deploy and Run

```bash
snow app run -c <connection>
```

This single command:
- Creates the application package (if it doesn't exist)
- Uploads all artifacts to the stage
- Creates the application instance (or upgrades it if it already exists)

> Run from the project directory containing `snowflake.yml`, or pass `--project <path>`.

If the command fails, check the error output. A common issue is a missing connection — add `-c <connection_name>` or configure a default connection.

**STOP**: Review test results with user. If issues found, fix and re-deploy.

### Step 5: Iterate

Development loop: edit files locally → `snow app run` → test → repeat.

`snow app run` automatically detects changes and uploads only modified files.

### Step 6: Next Steps

If tests pass, **ask** the user:
```
Tests look good! What would you like to do next?

1. Continue iterating — Make changes and re-test
2. Register a version — Load app-version-release skill to register a version and publish to consumers
3. Publish to consumers — Create a listing so other accounts can install the app
```

**STOP**: Wait for user selection. If option 2, load `app-version-release/SKILL.md`. If option 3, load `references/publish-listing.md` (note: requires a registered version with a release directive first — if not done yet, do option 2 first).

---

## SQL Path

> **All steps are idempotent** — safe to re-run if interrupted. Uses `IF NOT EXISTS`, `OVERWRITE=TRUE`, and `CREATE OR ALTER` for schemas and stages.
>
> **Important**: `CREATE OR REPLACE APPLICATION` and `CREATE OR ALTER APPLICATION` are NOT valid syntax. Always use `CREATE APPLICATION` (drop first if it already exists).

### Step 3: Create the Application Package

If the package already exists, skip this step.

**Execute** SQL to create the application package:

```sql
CREATE APPLICATION PACKAGE <app_pkg>;
```

Notes:
- Release channels are enabled by default. This skill only creates new packages with release channels enabled.
- This skill works with existing packages regardless of whether release channels are enabled or disabled.

### Step 4: Create a Named Stage

Check whether a stage already exists in the application package. If one exists, **use that existing stage** in all subsequent steps (do not create a new one with different naming). If not, create a schema and stage to hold the app files:

```sql
CREATE SCHEMA IF NOT EXISTS <app_pkg>.stage_content;

CREATE OR ALTER STAGE <app_pkg>.stage_content.app_code
  DIRECTORY = (ENABLE = TRUE);
```

### Step 5: Upload Files to Stage

The project directory should contain at minimum: `manifest.yml`, `scripts/setup.sql`, and `README.md`.

Generate a timestamp-based folder name (e.g., `v_20240319_001`) to avoid conflicts, then upload all files under that folder:

```sql
PUT 'file://<project_dir>/manifest.yml' @<app_pkg>.stage_content.app_code/<project_path>/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
PUT 'file://<project_dir>/scripts/setup.sql' @<app_pkg>.stage_content.app_code/<project_path>/scripts/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
PUT 'file://<project_dir>/README.md' @<app_pkg>.stage_content.app_code/<project_path>/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
```

Upload any additional files (Streamlit, stored procedures, etc.) following the same pattern. The stage path should mirror the local directory structure.

### Step 6: Verify Upload

```sql
LIST @<app_pkg>.stage_content.app_code/<project_path>;
```

Confirm the stage contains:
- `manifest.yml` at root
- `scripts/setup.sql`
- `README.md`

### Step 7: Create the App

```sql
CREATE APPLICATION <app_name>
  FROM APPLICATION PACKAGE <app_pkg>
  USING '@<app_pkg>.stage_content.app_code/<project_path>';
```

> **Important**: This creates a development-mode app installed from staged files. A dev-mode app cannot be upgraded to a versioned app — `ALTER APPLICATION ... UPGRADE USING VERSION` will fail. To install from a version later, drop this app first and create a new one with `USING VERSION`.

### Step 8: Verify Installation

Verify the app was created successfully:

- DESCRIBE the application to confirm it was created
- Run or query one of the stored procedures, UDFs, or views exposed to the consumer (the objects that have been granted to application roles) to verify the app works end-to-end

**STOP**: Review test results with user. If issues found, fix and re-upload files.

If tests pass, **ask** the user:
```
Tests look good! What would you like to do next?

1. Continue iterating — Make changes and re-test
2. Register a version — Load app-version-release skill to register a version and publish to consumers
3. Publish to consumers — Create a listing so other accounts can install the app
```

**STOP**: Wait for user selection. If option 2, load `app-version-release/SKILL.md`. If option 3, load `references/publish-listing.md` (note: requires a registered version with a release directive first — if not done yet, do option 2 first).

### Step 9: Upgrade the App

After making changes to the setup script or app code, re-upload files and upgrade:

```sql
ALTER APPLICATION <app_name>
  UPGRADE USING '@<app_pkg>.stage_content.app_code/<project_path>';
```

### Step 10: Iterate

Development loop: edit files locally → PUT to stage → `ALTER APPLICATION ... UPGRADE` → test → repeat.

For troubleshooting common errors, see `../references/troubleshooting.md`.

## Output

- Application package created in Snowflake
- Files uploaded to stage
- App installed and tested locally from staged files
- Issues identified and resolved
- User directed to app-version-release for versioning or publishing
