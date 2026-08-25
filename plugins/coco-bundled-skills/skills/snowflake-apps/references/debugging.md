# Debugging Snowflake Apps

Reference for diagnosing and resolving issues across the Snowflake Apps lifecycle. Covers app creation, setup, deployment, upgrade, and operations.

> **Note:** `SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA` and similar observability system functions may evolve as the platform develops. If a function fails with "unknown function", check the latest Snowflake documentation.

> **First question in any app investigation: which manifest drives this project?** This guide describes the `snowflake.yml` flow unless a section says otherwise. If the project root has an `app.yml` with a top-level `version: 2`, that file owns the deployment configuration instead — read [`manifests.md`](manifests.md) for its fields and errors, and [Diagnosing an app.yml v2 project](#diagnosing-an-appyml-v2-project) for what changes.

---

## Happy Path Overview

### Phase 1: App Creation

1. **User requests a new app** — Triggers the `create` sub-skill.
2. **Template is copied** — The `create` sub-skill scaffolds the project from the chosen template subdirectory under `apps/snowflake-apps/create/` into a new directory.
3. **CoCo generates a working app** — Source files are modified to implement the user's requirements (pages, API routes, Snowflake queries, styling).
4. **`snow app setup --dry-run`** — Validates that all required Snowflake objects exist and resolves configuration values without writing anything. Each resolved value shows its source (`user input`, `account parameter`, `default`, `current session`, or `missing`).
5. **`snow app setup`** — Generates the actual deployment manifest: `snowflake.yml` by default, or an `app.yml` with `version: 2` when the `ENABLE_SAR_APP_YML_V2` CLI feature flag is on (see [`manifests.md`](manifests.md)). Either way it never overwrites an existing manifest. Resolution order:
   - CLI flags (`--compute-pool`, `--build-eai`) — highest priority
   - Account parameters (`DEFAULT_SNOWFLAKE_APPS_*`) — user-level defaults
   - Built-in defaults — personal database (`USER$<username>`), artifact repo (`<APP>_REPO`)
   - Current session — warehouse, database, schema from the active connection

   **When Personal Database (PDB) + Workspace is used:**
   - The database resolves to `USER$<username>`
   - The schema resolves to `PUBLIC`
   - A shared workspace `SNOWFLAKE_APPS` is created in the personal DB
   - `code_workspace` is set to `<DB>.<SCHEMA>.SNOWFLAKE_APPS` (each app gets its own subdirectory)
   - No per-app code stage is created

6. **Test locally** — The app is started per the template's local-development instructions. Snowflake queries use local SSO auth.

### Phase 2: App Deployment

7. **`snow app deploy --verbose`** — Executes three sequential phases:

   **Upload phase:**
   - Bundles local source files (respecting `artifacts` globs and `ignore` patterns in `snowflake.yml`)
   - Workspace flow: uploads files to `snow://workspace/<DB>.<SCHEMA>.SNOWFLAKE_APPS/versions/live/<app_name>/`, then commits the live version
   - Stage flow: uploads files to `@<DB>.<SCHEMA>.<APP>_CODE`

   **Build phase:**
   - Creates the artifact repository (`<APP>_REPO`) if it doesn't exist
   - Calls `SYSTEM$SPCS_TEST_BUILD_APP_ARTIFACT_REPO` with the source location, repo FQN, app name, compute pool, runtime image, and EAI config
   - A build job service (`<APP>_BUILD_JOB`) is created and runs on the specified compute pool
   - The job downloads dependencies (using the template's install step), builds the container image, and publishes to the artifact repo
   - CLI polls build status (PENDING → RUNNING → DONE/FAILED) every 5 seconds for up to 20 minutes
   - With `--verbose`, build logs stream in real time

   **Promote phase:**
   - Runs `CREATE APPLICATION SERVICE` from the artifact repository package (version `LATEST`)
   - If the service already exists (errno 2002), falls back to `ALTER APPLICATION SERVICE UPGRADE`
   - CLI polls `DESCRIBE APPLICATION SERVICE` waiting for the endpoint URL to become available
   - Returns the app URL (e.g. `https://<app>.snowflakecomputing.app`)
   - In an `app.yml` v2 project this phase is a single declarative `CREATE OR ALTER APPLICATION SERVICE` instead — see [Diagnosing an app.yml v2 project](#diagnosing-an-appyml-v2-project)

### Phase 3: App Upgrade

8. **`snow app deploy --verbose`** (subsequent deploys) — Same three phases, but the promote phase performs an upgrade instead of a create:
   - Upload: clears and re-uploads source files
   - Build: rebuilds the container image with updated source (new version in artifact repo)
   - Promote: `ALTER APPLICATION SERVICE UPGRADE TO VERSION LATEST`
   - CLI polls `is_upgrading` until the service URL is ready again
   - In an `app.yml` v2 project there is no separate upgrade path: every deploy re-applies the same `CREATE OR ALTER`, so `--promote-only` means "re-converge to the manifest" rather than "upgrade the existing service"

   **Manual upgrade (without re-uploading/rebuilding):**
   ```sql
   ALTER APPLICATION SERVICE <database>.<schema>.<app_name> UPGRADE;
   ALTER APPLICATION SERVICE <database>.<schema>.<app_name> UPGRADE TO VERSION <version>;
   ```

### Phase 4: Operations

9. **Monitoring and management** — Post-deploy lifecycle:
   - View logs: `CALL SYSTEM$GET_APPLICATION_SERVICE_LOGS('<fqn>')`
   - Check status: `DESCRIBE APPLICATION SERVICE <fqn>`
   - Suspend: `ALTER APPLICATION SERVICE <fqn> SUSPEND`
   - Resume: `ALTER APPLICATION SERVICE <fqn> RESUME`
   - Teardown: `snow app teardown --force`

---

## Setup Step

### How Setup Resolves Defaults

The CLI resolves configuration values using a **four-tier precedence** (highest to lowest):

1. **User input** — Flags passed on the command line (`--compute-pool`, `--build-eai`)
2. **Account parameters** — `DEFAULT_SNOWFLAKE_APPS_*` parameters set at the user level
3. **Built-in defaults** — Personal database (`USER$<username>`), default artifact repo name (`<APP_NAME>_REPO`)
4. **Current session** — Warehouse, database, schema from the active connection

### Backend Parameters Checked

The CLI runs `SHOW PARAMETERS LIKE 'DEFAULT_SNOWFLAKE_APPS_%' IN USER` to fetch user-level defaults:

| Parameter Name | Maps To | Purpose |
|---------------|---------|---------|
| `DEFAULT_SNOWFLAKE_APPS_QUERY_WAREHOUSE` | `query_warehouse` | Warehouse for SQL queries |
| `DEFAULT_SNOWFLAKE_APPS_BUILD_COMPUTE_POOL` | nothing | Account-level build pool default. Returned by the wildcard query, but `snow app setup` never writes a compute pool into `snowflake.yml`. |
| `DEFAULT_SNOWFLAKE_APPS_SERVICE_COMPUTE_POOL` | nothing | Account-level service pool default. Same caveat as above. |
| `DEFAULT_SNOWFLAKE_APPS_BUILD_EXTERNAL_ACCESS_INTEGRATION` | `build_eai` | EAI for build-time network access |
| `DEFAULT_SNOWFLAKE_APPS_DESTINATION_DATABASE` | `database` | Target database |
| `DEFAULT_SNOWFLAKE_APPS_DESTINATION_SCHEMA` | `schema` | Target schema |

Additional boolean parameters that affect behavior:

| Parameter | Effect When TRUE |
|-----------|-----------------|
| `ENABLE_APPLICATION_SERVICE_MANAGED_COMPUTE_POOL` | Account uses system-managed compute pools; user-specified pools may be ignored |
| `ENABLE_APPLICATION_SERVICE_MANAGED_COMPUTE_POOL_FALLBACK` | When managed pools are enabled, allows user-specified pools as a fallback |

### Diagnosing Setup Issues

```sql
-- Check what parameters are set for the current user
SHOW PARAMETERS LIKE 'DEFAULT_SNOWFLAKE_APPS_%' IN USER;

-- Check if managed compute pools are enabled
SHOW PARAMETERS LIKE 'ENABLE_APPLICATION_SERVICE_MANAGED_COMPUTE_POOL';

-- Verify personal database exists
SELECT 'USER$' || CURRENT_USER() AS personal_database;

-- Check current session context
SELECT CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA(), CURRENT_ROLE();
```

### Dry Run

Use `--dry-run` to preview resolved configuration without writing `snowflake.yml`:

```bash
snow app setup --app-name="<app_name>" --dry-run
```

Each value in the output shows its source (`user input`, `account parameter`, `default`, `current session`, or `missing`). If any required value shows `missing`, provide it via flags:

```bash
snow app setup --app-name="<app_name>" --compute-pool <pool> --build-eai <eai> --dry-run
```

### Common Setup Issues

| Error | Cause | Resolution |
|-------|-------|------------|
| `snowflake.yml already exists` | Setup was already run | Skip setup; edit `snowflake.yml` directly or delete it and re-run |
| `app.yml already exists. Skipping initialization.` and no manifest written | With the v2 flag on, setup skips when any `app.yml` is present — including the build-only one a template ships | Move the existing `app.yml` aside, re-run setup, then merge the build phases back into the generated file |
| `Could not derive app name` | Directory name contains only special characters | Pass `--app-name` explicitly |
| `Invalid app name` | Name contains characters other than letters, digits, underscores | Use only `[a-zA-Z0-9_]` |
| Missing `build_compute_pool` | No account parameter set and no `--compute-pool` flag | Run `SHOW COMPUTE POOLS` to find one, then pass `--compute-pool` |
| Missing `build_eai` | No account parameter set and no `--build-eai` flag | Run `SHOW EXTERNAL ACCESS INTEGRATIONS` to find one, then pass `--build-eai` |
| `Could not resolve personal database` | User identity not available or CURRENT_USER() returns empty | Verify connection and role are correct |

---

## snowflake.yml Structure

The `snowflake.yml` file defines the deployment configuration for a Snowflake App. It is generated by `snow app setup` and lives in the project root.

### Full Field Reference

```yaml
definition_version: "2"

entities:
  <entity_id>:                          # Entity identifier (used with --entity-id)
    type: snowflake-app                 # Must be "snowflake-app"

    identifier:
      name: MY_APP_NAME                 # UPPER_SNAKE_CASE Snowflake identifier
      database: <database>              # Target database for the app
      schema: <schema>                  # Target schema for the app

    meta:
      title: "Human-Readable Title"     # Display name; generated by snow app setup
                                        # Do not add description or icon here;
                                        # those go in app.yml profile block instead

    artifacts:                          # Source files to upload for build
      - src: ./*                        # Glob pattern for source files
        dest: ./                        # Destination in build context
        ignore:                         # Patterns to exclude
          - .env*
          - .git
          - output
          # plus dependency/build-output dirs for your template (e.g. anything in .gitignore)

    query_warehouse: <warehouse>        # Warehouse for SQL queries at runtime

    build_eai:                          # External access integration for builds
      name: <eai_name>

    service_eai:                        # External access integration for the running service
      name: <eai_name>

    # Code storage (mutually exclusive — use one or the other):
    code_stage: <stage_name>            # Stage-based storage (bare name or DB.SCHEMA.NAME)
    code_workspace: <workspace_fqn>     # Workspace-based storage (DB.SCHEMA.NAME)

    # Optional fields:
    artifact_repository:                # Override default artifact repo (<APP>_REPO)
      name: <repo_name>
      database: <database>              # Defaults to app database if omitted
      schema: <schema>                  # Defaults to app schema if omitted

    runtime_image: ""                   # Custom runtime image for SPCS
```

> **Unknown keys are rejected.** The `snowflake-app` entity model forbids extra fields, so a typo or an invented field fails validation before deploy rather than being ignored. This is the opposite of `app.yml`, where unknown keys are silently dropped. To see the authoritative field list for your installed CLI, run `snow helpers generate-project-schema`.

### Build-only app.yml Field Reference

This is the `app.yml` that accompanies a `snowflake.yml` — it has **no `version:` key** and controls the build and runtime, while `snowflake.yml` controls where the app is deployed. (For the `version: 2` manifest, which absorbs the deployment configuration too, see [`manifests.md`](manifests.md).) Nine top-level keys are accepted:

| Key | Purpose |
|-----|---------|
| `install` | `commands:` run before the build (e.g. `npm ci`) |
| `build` | `commands:` run during the build (e.g. `npm run build`) |
| `run` | `command:` that starts the container. **Accepts no other fields.** |
| `artifacts` | `src`/`dest` copy rules moving build output into the package |
| `profile` | `label`, `description`, `icon` display metadata |
| `secrets` | `name`/`secret` pairs mounted under `/secrets/<name>/` |
| `environment_variables` | `name`/`value` pairs exposed as env vars |
| `parameters` | `name`, `default_value`, `description` |
| `external_access_integrations` | EAI names the app needs at runtime for outbound network access |

> **Unknown keys are silently ignored here.** Unlike `snowflake.yml`, an invented or misspelled `app.yml` key produces no error and no warning — the deploy succeeds and the setting simply does nothing. `secrets:` and `environment_variables:` are top-level keys; nesting them under `run:` is the most common form of this failure.

### Key Fields for Debugging

| Field | Default | How Resolved | Debugging Notes |
|-------|---------|-------------|-----------------|
| `identifier.database` | Personal DB (`USER$<username>`) | Account param → personal DB → session | If empty, deploy fails with "Cannot resolve database" |
| `identifier.schema` | `PUBLIC` | Account param → `PUBLIC` → session | If empty, deploy fails with "Cannot resolve schema" |
| `query_warehouse` | None | Account param → session warehouse | Required for runtime queries |
| `build_eai` | None | Account param only | Required for dependency downloads during build |
| `service_eai` | None | Explicit only | Required for outbound network access from the running app |
| `artifact_repository` | `<APP_NAME>_REPO` | Explicit → default naming | Created automatically if it doesn't exist |
| `code_stage` | `<APP_NAME>_CODE` | Explicit or default | Used when NOT in personal DB flow |
| `code_workspace` | `<DB>.<SCHEMA>.SNOWFLAKE_APPS` | Generated by setup | Used in personal DB flow; shared across apps |

### Validating the manifest

```bash
# Validate structure without deploying
snow app validate [--entity-id "<id>"]

# Bundle artifacts locally to inspect what would be uploaded
snow app bundle [--entity-id "<id>"]
# Inspect output at: ./output/bundle/
```

In an `app.yml` v2 project, `validate` takes `--target "<name>"` instead of `--entity-id`, and `bundle` takes neither (all targets share one source tree). If a file is missing from the bundle there, check `ignore` — v2 has no `artifacts` `src`/`dest` rules, so `ignore` is the only thing that can exclude it.

---

## Diagnosing an app.yml v2 project

The upload and build phases are identical in both layouts, so everything in this guide about them applies verbatim. What differs is where configuration comes from and what the deploy phase does — [`manifests.md`](manifests.md) is the reference for both, including the field defaults and every v2-specific error message with its fix. Two things belong here instead, because they are diagnostic procedures rather than facts:

### "I changed app.yml and nothing happened"

Work through these in order; the first two cover most reports:

1. **Is a top-level `version: 2` present?** Without it the CLI treats the file as the legacy build-only manifest, ignores every deployment key in it, and reads `snowflake.yml` instead. It has to be 2 exactly — a higher value is rejected rather than accepted.
2. **Which target was deployed?** A field edited on the baseline is still overridden by whatever the selected target sets, and list fields (`secrets`, `environment_variables`, `external_access_integrations`) replace the baseline list rather than merging into it.
3. **Is the key one the CLI reads?** Unknown keys are silently dropped, as in the build-only manifest — a leftover `profile:` block or a misspelling produces no error at all.
4. **Does the installed CLI support v2?** `snow app deploy --help` lists `--target` only on a CLI that does.

### "A service property reverted on its own"

The v2 deploy phase is a single declarative `CREATE OR ALTER APPLICATION SERVICE`, so it converges the service to exactly what the manifest says and resets anything the manifest omits. When a property was right yesterday and is default today, look for a deploy that ran without it — most often a property set out of band with `ALTER APPLICATION SERVICE ... SET`, which does not survive a redeploy the way it does under `snowflake.yml`. `DESCRIBE APPLICATION SERVICE <fqn>` shows what the service is actually running; compare it against the manifest.

---

## Diagnosing Upload Failures

### Symptoms

- CLI reports errors during stage/workspace creation or file upload
- "Stage not found" or "Workspace not found" errors

### Diagnostic Commands

```sql
-- Check if the code stage exists
DESCRIBE STAGE <database>.<schema>.<app_name>_CODE;

-- Check if the workspace exists
DESCRIBE WORKSPACE <database>.<schema>.SNOWFLAKE_APPS;

-- List files in the stage
LIST @<database>.<schema>.<app_name>_CODE;

-- List files in the workspace (live version)
LIST snow://workspace/<database>.<schema>.SNOWFLAKE_APPS/versions/live/<app_name>/;
```

### Common Issues

| Error | Cause | Resolution |
|-------|-------|------------|
| `Insufficient privileges to operate on stage` | Role lacks `CREATE STAGE` on the schema | Grant `CREATE STAGE ON SCHEMA <db>.<schema> TO ROLE <role>` |
| Stage creation/upload fails when `database: USER$...` | Personal databases (name starts with `USER$`) currently don't support stages | Switch to `code_workspace` instead of `code_stage`, or deploy to a non-personal database the role can operate on. See [Code Storage Backends](#code-storage-backends). |
| `Workspace does not exist` | Workspace not yet created or wrong FQN | Run `CREATE WORKSPACE IF NOT EXISTS <fqn>` or re-run full deploy |
| `Stage owned by different role` | Stage was previously created by another role | Drop the stage and redeploy so the current role recreates it |
| Upload appears to succeed but build fails with "no files" | Artifacts config in `snowflake.yml` excludes required files | Check `artifacts` glob patterns and `ignore` rules |

### Retry

```bash
snow app deploy --upload-only [--entity-id "<id>"]
```

---

## Diagnosing Build Failures

The build phase creates a job service that downloads dependencies, builds a container image, and publishes it to the artifact repository.

### Symptoms

- CLI reports "Artifact repo build timed out" or status `FAILED`
- Build hangs in `PENDING` state indefinitely

### Diagnostic Commands

```sql
-- Check build job status (job service name is <APP_NAME>_BUILD_JOB)
SHOW SERVICES IN SCHEMA <database>.<schema>;

-- Get build job logs (primary debugging tool)
SELECT * FROM TABLE(<database>.<schema>.<app_name>_BUILD_JOB!SPCS_GET_LOGS());
```

### Build States

| State | Meaning |
|-------|---------|
| `PENDING` | Job service is waiting for compute resources |
| `RUNNING` | Build is actively executing |
| `DONE` | Build completed successfully |
| `FAILED` | Build encountered an error |
| `IDLE` | No build job service exists (hasn't started or was cleaned up) |

### Common Issues

| Error | Cause | Resolution |
|-------|-------|------------|
| Build stuck in `PENDING` | Compute pool has no available capacity | Check compute pool status: `SHOW COMPUTE POOLS`. Verify the pool is `ACTIVE`/`IDLE` and has available nodes. |
| `Could not parse build job name from output` | `SYSTEM$SPCS_TEST_BUILD_APP_ARTIFACT_REPO` returned unexpected output | Check the raw output in `--verbose` mode. May indicate a backend issue. |
| Dependency download failures in build logs | EAI does not allow egress to required hosts | Verify the build EAI allows egress to the package registry your template's dependencies are fetched from. See `references/permissions.md`. |
| Dependency install failures in build logs | Package resolution errors | Check your template's dependency manifest for invalid versions. Review build logs for the specific package that failed. |
| Build times out after 20 minutes | Large dependency tree or slow network | Check build logs for progress. Consider reducing dependencies or pre-building. |
| `SPCS only supports image for amd64 architecture` | Source includes pre-built binaries for ARM | Ensure no ARM-specific binaries are in the upload. The remote build handles architecture. |

### Retry

```bash
snow app deploy --build-only [--entity-id "<id>"]
```

Use `--verbose` to stream build logs in real time.

---

## Diagnosing Deploy (Service Creation) Failures

### Symptoms

- CLI reports "Endpoint provisioning timed out"
- Service status shows `FAILED`
- Upgrade hangs with `is_upgrading = TRUE`

### Diagnostic Commands

```sql
-- Describe the application service (primary status check)
DESCRIBE APPLICATION SERVICE <database>.<schema>.<app_name>;

-- Show all application services in schema
SHOW APPLICATION SERVICES IN SCHEMA <database>.<schema>;

-- Get application service logs
CALL SYSTEM$GET_APPLICATION_SERVICE_LOGS('<database>.<schema>.<app_name>');

-- With line limit
CALL SYSTEM$GET_APPLICATION_SERVICE_LOGS('<database>.<schema>.<app_name>', 1000);
```

### Application Service States

For the authoritative list of service states and their meanings, see `operate/SKILL.md` (the `status` row in the Check App Status section).

### DESCRIBE APPLICATION SERVICE Output

Key columns to check:

| Column | What to Look For |
|--------|-----------------|
| `status` | Should be `RUNNING` for a healthy app |
| `url` | The public endpoint URL; empty or "provisioning in progress" means not ready |
| `is_upgrading` | `TRUE` during an upgrade; if stuck, the upgrade may have failed |
| `compute_pool` | Verify it's the expected pool |
| `source` | JSON with `artifactRepository`, `package`, `version`, `alias` |

### Common Issues

| Error | Cause | Resolution |
|-------|-------|------------|
| Service already exists (errno 2002) | Re-deploying to an existing service | The CLI automatically falls back to `ALTER APPLICATION SERVICE UPGRADE`. If this also fails, teardown and redeploy. |
| Endpoint URL shows "provisioning in progress" | DNS/endpoint is still being allocated | Wait 2-3 minutes. If it persists beyond 5 minutes, check service logs. |
| Service status `FAILED` | Application crashed on startup | Check logs with `SYSTEM$GET_APPLICATION_SERVICE_LOGS`. Common causes: port mismatch, missing env vars, unhandled exceptions. |
| `Managed compute pools are enforced for this account` | Account uses system-managed pools but `snowflake.yml` specifies a custom pool | Remove `build_compute_pool` and `service_compute_pool` from `snowflake.yml`, or contact your admin. |
| Missing privileges | Role lacks `CREATE APPLICATION SERVICE` on schema | See `references/permissions.md` for required grants. |

### Retry

```bash
snow app deploy --promote-only [--entity-id "<id>"]
```

---

## Artifact Repository Commands

### Inspecting the Artifact Repository

```sql
-- Check if the artifact repository exists
SHOW ARTIFACT REPOSITORIES IN SCHEMA <database>.<schema>;

-- List packages in the repository
SHOW PACKAGES IN ARTIFACT REPOSITORY <database>.<schema>.<repo_name>;

-- List versions for a specific package
SHOW VERSIONS IN ARTIFACT REPOSITORY <database>.<schema>.<repo_name>
  FOR PACKAGE <package_name>;
```

### Artifact Repository Naming

By default, the CLI creates an artifact repository named `<APP_NAME>_REPO` in the same database/schema as the app. This can be overridden via the `artifact_repository` field in `snowflake.yml`.

---

## Build and Event Logs

### Build Job Logs

```sql
-- Get logs from the build job service
SELECT * FROM TABLE(<database>.<schema>.<app_name>_BUILD_JOB!SPCS_GET_LOGS());
```

### Event Table (Historical Logs)

Use this when the service has been deleted or restarted and live logs are no longer available, or when you need historical logs or structured metrics and events. For live log retrieval and the `SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA` function, see `operate/SKILL.md`.

Query the event table directly using `snow.service.id`. This is a numeric internal identifier not exposed in `DESCRIBE APPLICATION SERVICE`. The most practical approach when the service still exists is to use `SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA` (see `operate/SKILL.md`). For a deleted service, scan recent rows and identify by log content:

```sql
-- Step 1: Find the account event table
SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT;

-- Step 2: Scan recent service log rows to find your service by content
-- (Use this when the service is deleted and you can't use the system function)
SELECT timestamp,
       RESOURCE_ATTRIBUTES:"snow.service.id"::NUMBER AS service_id,
       RESOURCE_ATTRIBUTES:"snow.service.container.name"::STRING AS container,
       VALUE
FROM <EVENT_TABLE_NAME>
WHERE TRUE
    AND timestamp > DATEADD(day, -7, CURRENT_TIMESTAMP())
    AND RESOURCE_ATTRIBUTES:"snow.service.id" IS NOT NULL
    AND RESOURCE_ATTRIBUTES:"snow.service.container.name" != 'snowflake-ingress'
ORDER BY timestamp DESC
LIMIT 200;

-- Step 3: Once you identify the service_id, filter to just that service
SELECT timestamp, VALUE
FROM <EVENT_TABLE_NAME>
WHERE RESOURCE_ATTRIBUTES:"snow.service.id" = <service_id_from_step_2>
ORDER BY timestamp ASC;
```

---

## CLI Code Paths and Flags

### Verbose Mode

Use `--verbose` with `snow app deploy` to stream build logs in real time during the build phase. Without it, build log lines are suppressed until the build completes or fails.

### Phase-Specific Flags

| Flag | Phase Executed | Use When |
|------|---------------|----------|
| (none) | Upload + Build + Promote | First deploy or full redeploy |
| `--upload-only` | Upload only | Debugging artifact/bundle issues |
| `--build-only` | Build only | Retrying after upload succeeded but build failed |
| `--promote-only` | Promote only | Retrying after build succeeded but service creation failed |

### Non-Idempotent Behavior

`snow app deploy` is **not idempotent**. Running it again restarts the entire pipeline (upload + build + promote). If a build is already in progress, check its status before re-running to avoid conflicting builds.

### Code Storage Backends

The CLI supports two mutually exclusive code storage backends:

| Backend | Configuration | URI Format |
|---------|--------------|------------|
| Stage | `code_stage` (a `name:` block in `snowflake.yml`, a plain string in `app.yml` v2) | `@<database>.<schema>.<stage_name>` |
| Workspace | `code_workspace` (same shapes) | `snow://workspace/<database>.<schema>.<workspace>/versions/live/<app_name>/` |

The workspace flow is used when deploying to a personal database. Each app gets its own subdirectory under a shared `SNOWFLAKE_APPS` workspace.

In an `app.yml` v2 project both fields are normally omitted and the CLI picks the backend per deploy (see [`manifests.md`](manifests.md)), so read the upload-phase log line to see which one it chose rather than inferring it from the manifest.

> **Limitation — personal databases may not support stages.** Personal databases (those whose name starts with `USER$`) currently do not support stages (this may change in the future). If `snowflake.yml` has `database: USER$...` and you specify `code_stage`, deploy will very likely fail during the upload phase. Resolve it one of two ways:
> 1. **Use `code_workspace` instead of `code_stage`** (easy change) — this is the supported backend for personal DBs and is what `snow app setup` configures by default for the PDB flow.
> 2. **Use a non-personal database** — find or create a database the current role has permission to operate on, and set `identifier.database` to it.

---

## RBAC and Privilege Errors

### Application Service Privileges

| Privilege | Allows |
|-----------|--------|
| `CREATE APPLICATION SERVICE` (on schema) | Create new application services |

For USAGE, MONITOR, OPERATE, and OWNERSHIP on deployed services, see `references/permissions.md`.

### Quick Privilege Check

```sql
-- Check grants on the application service
SHOW GRANTS ON APPLICATION SERVICE <database>.<schema>.<app_name>;

-- Check what the current role can do
SHOW GRANTS TO ROLE <current_role>;

-- Verify compute pool access
SHOW GRANTS ON COMPUTE POOL <pool_name>;

-- Verify EAI access
SHOW GRANTS ON INTEGRATION <eai_name>;
```

For the full grant list required for deployment, see `references/permissions.md`.

### Caller's Rights Returns the Wrong Identity or No Rows

Caller's rights needs no app-side configuration. Snowflake declares every App Runtime app caller's-rights-capable and injects the `sf-context-current-user-token` header on every ingress request. There is no `app.yml` or `snowflake.yml` field to set, so a query running as the service identity is never caused by missing config.

Work through these in order:

```sql
-- 1. Which identity actually ran the query? Owner's rights returns SF$SERVICE$<id>.
--    Do NOT diagnose with CURRENT_ROLE() alone — it is ambiguous when the
--    deployer's default role and the app's owning role are the same name.
SELECT CURRENT_USER(), CURRENT_ROLE();

-- 2. Are caller grants in place on the app's OWNING role (not the end user)?
SHOW CALLER GRANTS TO ROLE <app_owner_role>;

-- 3. Does the calling user resolve to a role your policies expect, and a usable warehouse?
DESCRIBE USER <calling_user>;   -- check DEFAULT_ROLE, DEFAULT_SECONDARY_ROLES, DEFAULT_WAREHOUSE
```

| Symptom | Likely cause |
|---------|--------------|
| `CURRENT_USER()` is `SF$SERVICE$<id>` | The query did not pass `{ callersRights: true }`. Owner's rights is the default for every call that omits it. |
| Query errors on objects the user can access | Missing caller grants on the owning role (step 2). |
| Query succeeds but returns zero rows | The caller's default primary role is not one your row access policies expect, or secondary roles are disabled account-wide. The role cannot be changed after a caller's-rights session is established. |
| Caller's rights fails for every app in the account | Not an app problem. The account parameter gating SPCS caller's rights is off. It defaults to on and is not visible via `SHOW PARAMETERS`, so this needs a Snowflake-side check. Treat as a last resort. |

Caller's rights works over network ingress only, not service functions.

---

## End-to-End Debugging Checklist

When a deploy fails and the error is unclear:

1. **Check which phase failed** — Look at the CLI output for the last successful step message.
2. **For upload failures** — Verify stage/workspace permissions and that `snowflake.yml` artifacts config is correct.
3. **For build failures** — Get build logs: `SELECT * FROM TABLE(<app>_BUILD_JOB!SPCS_GET_LOGS())`. Check EAI allows egress to package registries.
4. **For deploy failures** — Run `DESCRIBE APPLICATION SERVICE <fqn>` and check `status`. Get service logs with `SYSTEM$GET_APPLICATION_SERVICE_LOGS`.
5. **Check compute pool** — `SHOW COMPUTE POOLS` to verify the pool is active and has capacity.
6. **Check permissions** — Cross-reference with `references/permissions.md`.
7. **Check event table** — For historical logs when the service/job no longer exists.
8. **Teardown and redeploy** — As a last resort: `snow app teardown --force` then `snow app deploy`.
