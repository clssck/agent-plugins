---
name: add-containers
description: "Add Snowpark Container Services (SPCS) to a Snowflake Native App: configure container images, compute pools, service specifications, grant callbacks, and service lifecycle management. Focuses on SPCS nuances specific to Native Apps versus standalone SPCS. Triggers: container, SPCS, Snowpark Container Services, compute pool, service spec, container_services, grant_callback, service endpoint, add containers, specification file, specification template, container native app, default_web_endpoint, uses_gpu, upgrade service, version_initializer, SPCS upgrade, ALTER SERVICE, SYSTEM$WAIT_FOR_SERVICES, services, service job."
parent_skill: native-app-provider
---

# Add Containers (SPCS) to a Native App

> **⚠️ MANDATORY**: If your system prompt mentions Snowsight, load [`../references/native-apps-snowsight.md`](../references/native-apps-snowsight.md) before doing anything else.

## When to Load

From the root `native-app-provider` skill when the user wants to add Snowpark Container Services capabilities to a Native App. This skill covers the **nuances** of SPCS within Native Apps — it does NOT duplicate standalone SPCS guidance (see `deploy-to-spcs` for standalone).

## How This Differs from Standalone SPCS

| Aspect | Standalone SPCS | SPCS in Native App |
|--------|----------------|-------------------|
| Image source | Consumer builds & pushes to own repo | Provider pre-builds, bundles in app package |
| Compute pool | Consumer creates directly | App creates directly in setup script (`manifest_version: 2` auto-grants privileges) |
| Image path format | `<registry_url>/<db>/<schema>/<repo>/<image>` | `/<db>/<schema>/<repo>/<image>` (no registry URL) |
| Access control | `GRANT SERVICE ROLE ... TO ROLE <role>` | `GRANT ... TO APPLICATION ROLE <app_role>` |
| Lifecycle | Consumer manages directly | Provider exposes stored procs / Streamlit for consumer |
| Privileges | Implicit (consumer's own account) | `CREATE COMPUTE POOL` + `BIND SERVICE ENDPOINT` in manifest |

## Guard Rails

Before generating ANY code, internalize these hard constraints:

- **NO registry URLs** in spec files — image paths must be `/<db>/<schema>/<repo>/<image>` only
- **Services CANNOT be in versioned schemas** — use a separate non-versioned schema (e.g., `services`)
- **NO quoted service names** — quoted names are not supported in apps
- **Images are immutable** once a version is added to the app package — changes require a new version
- **Max 30 compute pools** per app across all consumer accounts
- **External image repos not supported** — only Snowflake image repositories
- **Telemetry limited to `ALL`** event definition for SPCS apps (see `references/event-definitions-reference.md`)
- If the service issues queries, the app must **also** request `CREATE WAREHOUSE`
- **Endpoint names** allow only lowercase alphanumeric + hyphens (`my-endpoint` ✅, `my_endpoint` ❌)
- **Hyphenated endpoint names in SQL DDL must be double-quoted**: `ENDPOINT = "mcp-endpoint"` ✅. Unquoted, the parser treats `-` as subtraction and raises a syntax error (`unexpected '-'`). Two safe patterns: (1) use a hyphen-free name in the spec (e.g. `mcp`, `prediction`) — no quoting needed anywhere; (2) keep the hyphenated name and always double-quote it in SQL. Do NOT use single quotes — `'mcp-endpoint'` is a string literal, not an identifier.
- **Service role names** must be valid SQL identifiers (no hyphens) for use after `!` in GRANT statements — derive from endpoint name by replacing hyphens with underscores (e.g. endpoint `my-endpoint` → role `my_endpoint_role`)
- **`serviceRoles` is a top-level key** in the spec YAML (sibling of `spec:`), NOT nested under `spec:`
- **Service functions always send POST** — container routes serving service functions must handle POST (e.g., Flask: `methods=['POST']`). GET-only routes return 405 Method Not Allowed

## Prerequisites

Gather the following from the user (skip items already known from context):

1. **Project directory** — where the native app files live (e.g., `/path/to/my_app`)
2. **Application package name** (e.g., `hello_snowflake_pkg`)
3. **Application name** (e.g., `hello_snowflake`)
4. **Image repository** — which database/schema to use for the image repo (e.g., `my_db.my_schema.my_repo`). Check if one exists first:
   ```sql
   SHOW IMAGE REPOSITORIES;
   ```
   Only create if it doesn't exist.
5. **Docker Desktop** installed for building images

**STOP**: Wait for user response before proceeding.

## Workflow

### Step 1: Determine Path

**Ask** the user:

```
Are you:
A) Creating a NEW native app with containers from scratch
B) Adding containers to an EXISTING native app (manifest and setup script already exist)
C) Upgrading an EXISTING app that already has containers (changing container code, image, or spec)
```

**Path A**: If no `manifest.yml` exists, load `setup-app/SKILL.md` first to create the base manifest and setup script, then return here.

**Path B**: Read the existing `manifest.yml` and setup script.

**Path C**: Read the existing `manifest.yml`, setup script, and container files. Then proceed through Steps 2–5, and pay close attention to the **Upgrade Support (Required)** section in Step 5.

**STOP**: Confirm path with user before proceeding.

### Step 2: Provider-Side Image Setup

**Goal:** Build and push the container image to the provider's image repository.

**Load** `../references/ref-spcs-image-registry.md` for auth paths, build commands, and ARM64 instructions.

**Native App difference from standalone SPCS:**
- Images must live in the **provider's** repository — consumers never build or push
- Images are **immutable** once a version is added — updates require a new version

**Service function response protocol:** Snowflake service functions use the external-function protocol. The container must accept POST requests with `{"data": [[row_index, arg1, ...], ...]}` and return `{"data": [[row_index, result], ...]}` — the row index must be echoed back as the first element of each result row. See the **Service Functions** section in `../references/ref-spcs-service-functions.md` for the full protocol and Flask example.

**Actions:**

1. **Create the image repository** if it doesn't already exist:
   ```sql
   CREATE IMAGE REPOSITORY IF NOT EXISTS <provider_db>.<provider_schema>.<repo_name>;
   ```

2. **Authenticate, build, and push** — follow the auth + build workflow in `../references/ref-spcs-image-registry.md`. The exact sequence is: (a) `snow spcs image-registry login` FIRST, (b) then create the buildx builder, (c) then `docker buildx build --platform linux/amd64 --push`. This ordering is critical — the builder must be created AFTER login. Do NOT use `--load` or plain `docker build`.

3. **Record** the spec-file path: `/<db>/<schema>/<repo>/<image_name>:<tag>` (no registry hostname).

**STOP**: Confirm image is pushed and spec-file path is recorded.

### Step 3: Update Manifest

**Goal:** Add SPCS configuration to `manifest.yml`.

**Load** `../references/manifest-reference.md` for field syntax and full examples.

Add these sections to the manifest:

1. `artifacts.container_services.images` — list of image paths (`/<db>/<schema>/<repo>/<image>:<tag>`)
2. `artifacts.container_services.uses_gpu: true` — if the app uses GPU. **Warning: once set to `true`, this field cannot be removed or set back to `false` in a published app package.** Confirm with the user before adding this field.
3. `artifacts.default_web_endpoint` — if the service exposes a web UI (set `service:` and `endpoint:`)
4. `privileges` — add `CREATE COMPUTE POOL` and `BIND SERVICE ENDPOINT` (auto-granted at install time with `manifest_version: 2`). Cross-ref: `request-account-privilege/SKILL.md`

5. `lifecycle_callbacks.version_initializer` — register the upgrade callback procedure (e.g., `core.version_init`). Required for safe service upgrades — see **Upgrade Pattern** in `../references/ref-spcs-setup-script.md`

**Note:** With `manifest_version: 2`, no `configuration.grant_callback` is needed — privileges are auto-granted and the setup script creates resources directly.

**Validation:** Before finalizing the manifest, cross-check every field and value against `../references/manifest-reference.md`. Only include fields listed there.

**For Path B:** Merge into the existing manifest, preserving existing content.

**STOP**: Present the manifest changes (as a diff for Path B) for user approval.

### Step 4: Create Service Specification File

**Goal:** Write the YAML service spec file.

**Actions:**

1. Create the spec file (e.g., `containers/service_spec.yaml`) using the **Service Specification File Template** in `../references/ref-spcs-service-spec.md`. Adjust `resources`, `env`, and `readinessProbe` for the app's requirements.

   > **CUSTOM MCP SERVER requirement**: If this endpoint will be registered as a `CUSTOM MCP SERVER` (via `CREATE CUSTOM MCP SERVER`), it **must** be declared `public: true` in the spec. Non-public endpoints are not accessible through the MCP client infrastructure used by Cortex Agents and Snowflake Intelligence — the MCP server will be unreachable.

2. If the service needs **external access** (calling external APIs), EAI must be configured separately — cross-ref: `request-external-access-integration/SKILL.md`.

3. If the service needs **consumer-provided configuration** (API URLs, model names, API keys), use one of the approaches below. Skip if no consumer-configurable values.

#### Approach 1: Specification Template + Configure Procedure

Use when the consumer needs to supply scalar values (strings, URLs, flags) injected as environment variables.

**Load** `../references/ref-spcs-service-spec.md` and `../references/ref-spcs-setup-script.md` — follow these sections in order:
1. **Specification Template File** — spec YAML with `{{ variable }}` placeholders and `grant_callback` integration with placeholder defaults
2. **Configure Procedure** — stored procedure the consumer calls to supply real values via `ALTER SERVICE ... USING (...)`

#### Approach 2: Object References (Secrets, EAIs)

Use when the consumer must bind Snowflake-managed objects they own (OAuth credentials, API key secrets, EAIs). The app cannot receive these as plain strings because they are sensitive or account-scoped objects.

**Load `request-object-access/SKILL.md`** for the full workflow — manifest `references:` block, `register_callback` signature, `SYSTEM$SET_REFERENCE` usage.

**STOP**: Present the spec file (and configure procedure / reference config if applicable) for review.

### Step 4.5: Service Needs External Access (EAI + Secret)

**Ask** the user: "Does the container need to call any external APIs (e.g., OAuth-authenticated services, public REST APIs)? If not, skip this step."

If yes, the app needs three linked pieces: a Security Integration (OAuth creds), a Secret (mounted into the container), and an External Access Integration (network egress).

**Decide who owns the EAI + Secret:**

- **Approach A — app-created** via auto-granted privileges + app specifications. The provider knows exactly which endpoints the app needs (or collects them from the consumer), and the application owns the secrets it plans to use.
- **Approach B — consumer-owned** via manifest `references`. The consumer supplies their own EAI and/or SECRET; the app binds them at install time via `register_callback`.

**Both approaches share the SPCS adaptations:**

- Mount the secret via a `secrets: - snowflakeSecret: ... directoryPath: ...` block in the service spec YAML. For Approach B (consumer-owned secret), use `snowflakeSecret: { objectReference: <manifest_ref_name> }` instead of a resolved FQN. See `../references/ref-spcs-service-spec.md` § Mounting Secrets for External API Authentication — including the Approach B `objectReference` pattern.
- Attach the EAI in SQL at `CREATE SERVICE` time (NOT in the YAML). See `../references/ref-spcs-setup-script.md` § Attaching EAI to a Service.
- **Approach A (manifest_version: 2):** Create the service **directly in the setup script** — app specs are auto-granted. Register a `specification_action` callback to **restart** the service on approval (so `access_token` gets refreshed).
- **Approach B:** **Defer `CREATE SERVICE`** — do NOT create the service in the setup script. The service must be created by a lifecycle callback after all references are BOUND. Use the reconciler design (`core.create_or_update_service`) documented in `../references/ref-spcs-setup-script.md` § Deferred Service Creation Pattern.

#### Step 4.5a — Approach A (app-created EAI/SI via specs)

1. Load **`request-security-integration/SKILL.md`** and follow it end-to-end. Creates the `SECURITY INTEGRATION` (OAuth creds) and the `SECURITY_INTEGRATION` app spec. Contains a **mandatory STOP** for placeholder credential replacement.

2. Load **`request-external-access-integration/SKILL.md` → Approach A (app-created)** and follow it end-to-end. Creates the network rule, the `SECRET` (`TYPE = OAUTH2` bound to the SI), the `EXTERNAL ACCESS INTEGRATION`, and the `EXTERNAL_ACCESS` app spec.

3. **Service lifecycle (manifest_version: 2):**
   - **Create the service directly in the setup script** with `CREATE SERVICE ... EXTERNAL_ACCESS_INTEGRATIONS = (<eai>)`. App specs are auto-granted, so the EAI is active at install time.
   - Implement `callbacks.on_spec_approved_or_declined(name, status, payload)` — on APPROVED, **restart the service** (e.g., `ALTER SERVICE ... SUSPEND` then `ALTER SERVICE ... RESUME`) so the `access_token` mount is refreshed.
   - Register both `lifecycle_callbacks.version_initializer: core.version_init` and `lifecycle_callbacks.specification_action: callbacks.on_spec_approved_or_declined` in the manifest.
   - `core.version_init()` handles upgrades via `ALTER SERVICE ... FROM SPECIFICATION_FILE` + `ALTER SERVICE ... SET EXTERNAL_ACCESS_INTEGRATIONS` + `SYSTEM$WAIT_FOR_SERVICES`.

   **manifest_version: 1** (lacks `specification_action`): use the **deferred pattern with a manual trigger**. Do **not** `CREATE SERVICE` in the setup script — specs are not auto-granted. Implement the reconciler (`core.create_or_update_service`) with a gate check (`SHOW APPROVED SPECIFICATIONS`). Add a `start_service()` procedure that delegates to the reconciler, and document the consumer install sequence as: install → approve both specs → `CALL <app>.<schema>.start_service()` → verify. See `../references/ref-spcs-setup-script.md` § Deferred Service Creation — manifest_version: 1 (manual trigger). Do **not** ship the legacy "create at install + consumer suspend/resume" workflow — it produces a broken 0-byte-token state and is an anti-pattern.

#### Step 4.5b — Approach B (consumer-owned EAI/SECRET via references)

1. Load **`request-external-access-integration/SKILL.md` → Approach B (consumer-owned via references)** and follow it end-to-end. Defines the manifest `references` for `CONSUMER_EXTERNAL_ACCESS` (EAI) and `CONSUMER_SECRET` (SECRET) and the paired `configuration_callback` that describes what the consumer must bind.

2. **Service lifecycle** — deferred creation is **REQUIRED**, not optional. `CREATE SERVICE` fails outright with an unbound-reference error if a referenced EAI or SECRET is not bound.
   - Implement `core.is_service_ready_to_deploy()` using `SYSTEM$GET_REFERENCE('CONSUMER_EXTERNAL_ACCESS', ...)` + `SYSTEM$GET_REFERENCE('CONSUMER_SECRET', ...)`; gate is true only when both return non-null bindings.
   - Implement `core.create_or_update_service()` reconciler. `CREATE SERVICE` uses `EXTERNAL_ACCESS_INTEGRATIONS = (reference('CONSUMER_EXTERNAL_ACCESS'))` and `ALLOWED_AUTHENTICATION_SECRETS = ALL` (Snowflake recommendation for consumer-supplied secrets).
   - Implement `config.register_ref_callback(ref_name, op, ref_or_alias)` — on `ADD`, call `SYSTEM$SET_REFERENCE` then the reconciler.
   - Register `lifecycle_callbacks.version_initializer: core.version_init` and each reference's `register_callback: config.register_ref_callback` in the manifest.
   - Service appears after the second reference binding (gate becomes true).

**STOP**: Present the combined SPCS + EAI + Secret + reconciler configuration for review before proceeding to Step 5.

### Step 5: Write Setup Script

**Goal:** Create compute pool, service, service functions, and lifecycle procedures directly in the setup script.

With `manifest_version: 2`, privileges (`CREATE COMPUTE POOL`, `BIND SERVICE ENDPOINT`) are **auto-granted** at install time. The setup script can create resources directly — no `grant_callback` needed.

Read `../references/ref-spcs-setup-script.md` and `../references/ref-spcs-compute-pool.md` before writing any SQL — follow the **setup script template**, **Multi-Cloud Compute Pool Pattern**, and **Common setup.sql Mistakes** sections.

Key implementation notes:
- Versioned schemas must use `CREATE OR ALTER VERSIONED SCHEMA` — `CREATE SCHEMA IF NOT EXISTS` cannot be upgraded to versioned after creation
- **Compute pool naming**: use `LET pool_name := (SELECT CURRENT_DATABASE()) || '_compute_pool';` then `IDENTIFIER(:pool_name)` in DDL — do NOT use `IDENTIFIER(CONCAT(...))` which causes syntax errors
- **Service creation**: use `FROM SPECIFICATION_FILE = '/path/to/spec.yaml'` (absolute path from project root) — do NOT use `FROM @stage`
- **Multi-cloud**: use `CURRENT_REGION()` to select instance family — see **Multi-Cloud Compute Pool Pattern** in the reference file
- Do NOT use `EXECUTE IMMEDIATE` for `CREATE COMPUTE POOL`, `CREATE SERVICE`, or `GRANT` statements — use plain SQL with `IDENTIFIER(:pool_name)` for dynamic names
- Do NOT wrap `INSTANCE_FAMILY` in `IDENTIFIER()` — use the bare keyword like `CPU_X64_XS`
- **For Path B**: integrate into the existing setup script alongside existing content
- **If Step 4.5 Approach A (manifest_version: 2)**: the setup script creates the compute pool, SI, secret, EAI, app specs, the service itself (`CREATE SERVICE ... EXTERNAL_ACCESS_INTEGRATIONS = (<eai>)`), and the `specification_action` callback for restart/suspend. See `../references/ref-spcs-setup-script.md` § Attaching EAI to a Service.
- **If Step 4.5 Approach B**: the setup script creates the compute pool, defines references, and the reconciler + callback procedures — but it does **NOT** `CREATE SERVICE`. The service is created later by the reconciler invoked from `register_callback`. See `../references/ref-spcs-setup-script.md` § Deferred Service Creation Pattern.

### Container Image Versioning for Service Resume (KB 000010129)

When a provider creates a new patch that changes the Docker image, any SPCS service that was previously suspended may fail to start — because the old image is no longer listed in the manifest. The error occurs at `resume` time when the service can't find its image.

**Two options:**

1. **Keep old images in manifest** (preferred for zero-disruption): Retain all historical images in `manifest.yml` `artifacts.container_services.images` alongside new ones. This lets consumers resume suspended services on old versions without needing an immediate upgrade.
2. **Use `version_initializer` to upgrade the service** (controlled migration): In the `version_initializer` callback, call `ALTER SERVICE ... FROM SPECIFICATION_FILE` with the new image to force an upgrade. The service may need to be briefly resumed then suspended for the callback to fire. See the [SPCS container upgrade guide](https://docs.snowflake.com/en/developer-guide/native-apps/container-upgrade) for details.

### Upgrade Support (Required)

`CREATE SERVICE IF NOT EXISTS` is a **no-op** when the service already exists — without upgrade handling, the service stays on the old spec after every app upgrade.

**You MUST:**

1. Read `../references/ref-spcs-setup-script.md` § **Upgrade Pattern** and implement it exactly — it covers `version_initializer` manifest registration, the `core.version_init()` procedure with `ALTER SERVICE` + `SYSTEM$WAIT_FOR_SERVICES`, and rollback behavior. **For each service**, the procedure **MUST** include `CALL SYSTEM$WAIT_FOR_SERVICES(600, 'services.<service_name>')` after its `ALTER SERVICE` — `ALTER SERVICE` is asynchronous and returns immediately, so without this the upgrade completes before the service is ready.

   **If Step 4.5 Approach A (manifest_version: 2):** `version_init` runs `ALTER SERVICE ... FROM SPECIFICATION_FILE` + `ALTER SERVICE ... SET EXTERNAL_ACCESS_INTEGRATIONS` + `SYSTEM$WAIT_FOR_SERVICES` directly — the service already exists (created in setup script).

   **If Step 4.5 Approach B:** `version_init` MUST delegate to `core.create_or_update_service()` — it must **not** run `ALTER SERVICE` directly. On first install the service does not exist yet; a direct `ALTER SERVICE` in `version_init` will fail and trigger rollback. The reconciler handles both "service absent, gate unmet → no-op success" and "service exists, gate met → ALTER". See `../references/ref-spcs-setup-script.md` § Deferred Service Creation Pattern → Wiring the callbacks.

2. Add to `manifest.yml`:
   ```yaml
   lifecycle_callbacks:
     version_initializer: core.version_init
     # If Step 4.5 Approach A:
     # specification_action: callbacks.on_spec_approved_or_declined
   ```

3. To deploy the upgrade after re-uploading files to stage, **read `deploy-test/SKILL.md`** and follow its **Step 8** exactly — it contains the precise `ALTER APPLICATION ... UPGRADE USING '@<pkg>.stage_content.app_code/<path>'` syntax required for dev-mode apps. Do NOT guess the upgrade command; you MUST load that file. The `version_initializer` callback fires automatically in both development mode and versioned upgrades — do NOT manually call the procedure after upgrading.

**STOP**: Present the setup script changes for review.

### Step 6: Service Lifecycle Management (Recommended)

**Ask** the user: "Do you want to give consumers lifecycle controls (suspend/resume/status/logs)? If not, skip this step."

**STOP**: Wait for user response.

> **If Step 4.5 applied (service mounts a secret backed by EAI/SI)**: lifecycle procedures remain **recommended** as standard consumer operations (cost control, troubleshooting). For Approach A with manifest_version: 2, the `specification_action` callback handles service restart on re-approval automatically. For manifest_version: 1, the consumer trigger is a dedicated `start_service()` procedure (which delegates to the reconciler).

**Goal:** Give consumers control over the service lifecycle.

Follow the lifecycle procedure templates in `../references/ref-spcs-setup-script.md` § **Service Lifecycle Procedures** — use the exact input/output signatures shown. Do not invent a different approach from memory.

Create all four procedures:
- `suspend_service()` — suspend to save compute costs
- `resume_service()` — resume a suspended service
- `get_service_status()` — check service health
- `get_service_logs(instance_id, container_name)` — retrieve logs for debugging

**Hard rules for lifecycle procedures:**
- All four procedures use **`RETURNS STRING`** — do NOT use `RETURNS TABLE`, `RESULTSET`, or `RESULT_SCAN`
- `get_service_status()` MUST call `SYSTEM$GET_SERVICE_STATUS('<schema>.<service_name>')` and return the result directly — do NOT use `SHOW SERVICES` or `RESULT_SCAN`
- `get_service_logs()` MUST call `SYSTEM$GET_SERVICE_LOGS(...)` and return the result directly
Grant all procedures to the application role.

### Step 7: Validate

**Validation Checklist:**

- [ ] `manifest.yml` `container_services.images` entries match the spec-file path (no registry URLs)
- [ ] `manifest.yml` has `CREATE COMPUTE POOL` and `BIND SERVICE ENDPOINT` in `privileges`
- [ ] If GPU: `container_services.uses_gpu: true` in manifest (irreversible — confirmed with user)
- [ ] If UI: `default_web_endpoint` configured in manifest
- [ ] `readinessProbe.port`, container `PORT` env var, and `endpoints.port` all aligned
- [ ] Compute pool names use `CURRENT_DATABASE()` prefix
- [ ] `serviceRoles` defined in spec for each public endpoint; `GRANT SERVICE ROLE svc!role` in setup script after `CREATE SERVICE`
- [ ] Service functions use `CREATE FUNCTION ... SERVICE = ... ENDPOINT = ... AS '/<path>'` syntax
- [ ] Service functions are granted to the application role
- [ ] If SPCS telemetry configured: only `ALL` event definition (cross-ref: `configure-telemetry-event-and-health-update/SKILL.md`)
- [ ] `lifecycle_callbacks.version_initializer` registered in manifest and procedure exists in versioned schema
- [ ] `version_init` calls `ALTER SERVICE` + `SYSTEM$WAIT_FOR_SERVICES` (simple service or Step 4.5 Approach A with manifest_version: 2) **OR** delegates to `core.create_or_update_service()` (Step 4.5 Approach B or manifest_version: 1)
- [ ] **If Step 4.5 applied (service needs external access):**
  - [ ] Chose Approach A (app-created specs) or Approach B (consumer-owned references)
  - [ ] If Approach A with manifest_version: 2: service created in setup script (app specs auto-granted)
  - [ ] If Approach A with manifest_version: 1: deferred via consumer-invoked `start_service()` procedure (NOT via "create at install + suspend/resume")
  - [ ] If Approach B: deferred via `register_callback` is implemented (required — direct CREATE SERVICE fails with unbound reference)
  - [ ] If Approach A with manifest_version: 2: service created directly in setup script with `EXTERNAL_ACCESS_INTEGRATIONS`; `specification_action` callback restarts service on APPROVED
  - [ ] If Approach B or manifest_version: 1: `core.create_or_update_service()` reconciler exists with `core.is_service_ready_to_deploy()` gate; setup script does **NOT** `CREATE SERVICE` directly
  - [ ] `CREATE SERVICE ... EXTERNAL_ACCESS_INTEGRATIONS = (<eai>)` (Approach A) or `... (reference('CONSUMER_EXTERNAL_ACCESS')) ALLOWED_AUTHENTICATION_SECRETS = ALL` (Approach B) — EAI attached in SQL, NOT in YAML
  - [ ] Secret mounted via `secrets: - snowflakeSecret: ... directoryPath: ...` block in the service spec YAML
  - [ ] `ALLOWED_AUTHENTICATION_SECRETS = ALL` on the EAI (works for both app-owned and consumer-owned secrets)
  - [ ] `ALLOWED_API_AUTHENTICATION_INTEGRATIONS` on the EAI includes the SI (Approach A only)
  - [ ] If Approach A with manifest_version: 2: `specification_action: callbacks.on_spec_approved_or_declined` registered in manifest; callback restarts service on APPROVED; procedure is granted to an application role
  - [ ] If Approach A with manifest_version: 1: `start_service()` procedure exists and is granted to the application role
  - [ ] If Approach B: `register_callback` specified for each reference in manifest; `config.register_ref_callback` procedure exists
  - [ ] README documents the consumer install sequence:
    - Approach A (manifest_version: 2): install → approve both specs → verify (callback handles creation automatically)
    - Approach A (manifest_version: 1): install → approve both specs → `CALL <app>.<schema>.start_service()` → verify
    - Approach B: install → bind EAI reference → bind SECRET reference → verify

## Output

- `manifest.yml` updated with SPCS configuration (images, privileges)
- Service specification file created
- Setup script with compute pool, service, service functions, and lifecycle procedures
- Ready to deploy and test — **load `deploy-test/SKILL.md`**
