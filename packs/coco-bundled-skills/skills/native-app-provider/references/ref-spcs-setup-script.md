---
name: ref-spcs-setup-script
description: "Setup script templates for SPCS in Native Apps: configure procedure, default setup script template, grant_callback pattern, and common setup.sql mistakes."
parent_skill: native-app-provider
---

# SPCS Setup Script Reference

## Configure Procedure

Snowflake recommends: *"When creating a service using a specification template, store the arguments provided by the consumer inside your application instance. This allows them to be passed as arguments when upgrading a service."* ([container-services](https://docs.snowflake.com/en/developer-guide/native-apps/container-services))

A common pattern to fulfill this: expose a stored procedure that accepts consumer values, persists them to an app table, and applies them via `ALTER SERVICE ... USING (...)`. The `core.configure()` procedure below implements this pattern — it is not a named Snowflake feature, but is built on documented primitives.

```sql
CREATE OR REPLACE PROCEDURE core.configure(api_url VARCHAR, model_name VARCHAR)
  RETURNS STRING
  LANGUAGE SQL
  EXECUTE AS OWNER
AS $$
BEGIN
  -- Persist for upgrades / status reporting
  CREATE TABLE IF NOT EXISTS core.app_config (key VARCHAR, value VARCHAR);
  MERGE INTO core.app_config t
    USING (SELECT * FROM VALUES ('api_url', :api_url), ('model_name', :model_name)) s(key, value)
    ON t.key = s.key
    WHEN MATCHED THEN UPDATE SET t.value = s.value
    WHEN NOT MATCHED THEN INSERT (key, value) VALUES (s.key, s.value);

  -- Apply new values — restarts containers with updated env vars
  ALTER SERVICE services.<service_name>
    FROM SPECIFICATION_TEMPLATE_FILE = '/containers/service_spec.yaml'
    USING (api_url => :api_url, model_name => :model_name);

  RETURN 'Configured successfully';
END;
$$;
GRANT USAGE ON PROCEDURE core.configure(VARCHAR, VARCHAR) TO APPLICATION ROLE app_user;
```

**Notes:**
- `EXECUTE AS OWNER` is required — consumers cannot directly alter services
- `ALTER SERVICE ... USING (...)` restarts containers; existing connections are dropped
- Adjust parameter names and types to match the spec template variables

## Setup Script Template (Default)

With `manifest_version: 2`, the privileges `CREATE COMPUTE POOL` and `BIND SERVICE ENDPOINT` are **auto-granted** when the app is installed. The setup script can create compute pools, services, and service functions directly — no `grant_callback` needed.

**Important:** The setup script must create the application role and schemas before any GRANTs or service objects. Use `CREATE OR ALTER VERSIONED SCHEMA` for schemas that need versioning — not `CREATE SCHEMA IF NOT EXISTS`, which creates a non-versioned schema that cannot be upgraded later.

**Complete setup script template:**
```sql
-- Preamble
CREATE APPLICATION ROLE IF NOT EXISTS app_user;
CREATE OR ALTER VERSIONED SCHEMA core;
GRANT USAGE ON SCHEMA core TO APPLICATION ROLE app_user;
CREATE SCHEMA IF NOT EXISTS services;
GRANT USAGE ON SCHEMA services TO APPLICATION ROLE app_user;

-- Create compute pool (name must be unique across account)
LET pool_name := (SELECT CURRENT_DATABASE()) || '_compute_pool';
-- Use IDENTIFIER(:pool_name) because pool names are object identifiers.
-- Use a string literal for INSTANCE_FAMILY — do NOT wrap it in IDENTIFIER().
CREATE COMPUTE POOL IF NOT EXISTS IDENTIFIER(:pool_name)
  MIN_NODES = 1
  MAX_NODES = 1
  INSTANCE_FAMILY = CPU_X64_XS
  AUTO_RESUME = TRUE
  AUTO_SUSPEND_SECS = 300;

-- Create service
CREATE SERVICE IF NOT EXISTS services.<service_name>
  IN COMPUTE POOL IDENTIFIER(:pool_name)
  FROM SPECIFICATION_FILE = '/containers/<spec_file>.yaml'
  MIN_INSTANCES = 1
  MAX_INSTANCES = 1;
GRANT USAGE ON SERVICE services.<service_name> TO APPLICATION ROLE app_user;
-- Grant the per-endpoint service role defined in the spec's serviceRoles field.
GRANT SERVICE ROLE services.<service_name>!<service_role_name> TO APPLICATION ROLE app_user;

-- Create service function (after CREATE SERVICE)
CREATE FUNCTION IF NOT EXISTS core.<function_name>()
  RETURNS VARCHAR
  SERVICE = services.<service_name>
  ENDPOINT = '<endpoint_name>'
  AS '/';
GRANT USAGE ON FUNCTION core.<function_name>() TO APPLICATION ROLE app_user;

-- Lifecycle procedures (see Service Lifecycle Procedures section below)
-- ... suspend_service, resume_service, get_service_status, get_service_logs ...
```

## Grant Callback Template (Legacy — manifest_version: 1)

With `manifest_version: 1`, privileges are **not** auto-granted. The consumer must manually grant them via Snowsight, and Snowflake invokes the `grant_callback` procedure each time a privilege is granted. The callback receives the full list of currently-granted privileges and is responsible for creating resources.

Prefer `manifest_version: 2` (Setup Script Template above) for all new apps — it eliminates the manual consumer step and the callback entirely.

The `grant_callback` is invoked when the consumer grants privileges to the app. It should create compute pools and services conditionally.

**CRITICAL — The `grant_callback` signature MUST be exactly `(privileges ARRAY)`.** Snowflake passes all granted privileges as a single array. Using `(privilege STRING)` or multiple STRING parameters will cause `Invalid argument types` errors at runtime.

```sql
CREATE OR REPLACE PROCEDURE <schema>.grant_callback(privileges ARRAY)
  RETURNS STRING
  LANGUAGE SQL
  EXECUTE AS OWNER
AS $$
BEGIN
  -- Create compute pool when CREATE COMPUTE POOL is granted
  IF (ARRAY_CONTAINS('CREATE COMPUTE POOL'::VARIANT, :privileges)) THEN
    LET pool_name := (SELECT CURRENT_DATABASE()) || '_compute_pool';
    -- Use IDENTIFIER(:pool_name) because pool names are object identifiers.
    -- Use a string literal for INSTANCE_FAMILY — do NOT wrap it in IDENTIFIER().
    CREATE COMPUTE POOL IF NOT EXISTS IDENTIFIER(:pool_name)
      MIN_NODES = 1
      MAX_NODES = 1
      INSTANCE_FAMILY = CPU_X64_XS
      AUTO_RESUME = TRUE
      AUTO_SUSPEND_SECS = 300;
  END IF;

  -- Create service when BIND SERVICE ENDPOINT is granted
  IF (ARRAY_CONTAINS('BIND SERVICE ENDPOINT'::VARIANT, :privileges)) THEN
    LET pool_name := (SELECT CURRENT_DATABASE()) || '_compute_pool';
    CREATE SERVICE IF NOT EXISTS <schema>.<service_name>
      IN COMPUTE POOL IDENTIFIER(:pool_name)
      FROM SPECIFICATION_FILE = '/containers/<spec_file>.yaml'
      MIN_INSTANCES = 1
      MAX_INSTANCES = 1;
    GRANT USAGE ON SERVICE <schema>.<service_name> TO APPLICATION ROLE app_user;
    -- Grant the per-endpoint service role defined in the spec's serviceRoles field.
    -- serviceRoles are created as part of the service object and are available immediately
    -- after CREATE SERVICE returns — no need to wait for containers to be RUNNING.
    -- IMPORTANT: The role name after ! must be a valid SQL identifier (no hyphens).
    -- Use the <service_role_name> from the spec's serviceRoles, NOT the endpoint name.
    GRANT SERVICE ROLE <schema>.<service_name>!<service_role_name> TO APPLICATION ROLE app_user;

    -- Create service functions AFTER the service exists (see ref-spcs-service-functions.md)
    CREATE FUNCTION IF NOT EXISTS <user_facing_schema>.<function_name>()
      RETURNS VARCHAR
      SERVICE = <schema>.<service_name>
      ENDPOINT = '<endpoint_name>'
      AS '/';
    GRANT USAGE ON FUNCTION <user_facing_schema>.<function_name>() TO APPLICATION ROLE app_user;
  END IF;

  RETURN 'DONE';
END;
$$;

GRANT USAGE ON PROCEDURE <schema>.grant_callback(ARRAY) TO APPLICATION ROLE app_user;
```

**Important:** The `grant_callback` is NOT called automatically in dev-mode apps (`USING @stage`). If using this pattern for testing, you must explicitly call it: `CALL {app}.{schema}.grant_callback(ARRAY_CONSTRUCT('CREATE COMPUTE POOL', 'BIND SERVICE ENDPOINT'))`. For most apps, prefer the Setup Script Template instead.

## Attaching EAI to a Service

When an SPCS service needs to reach external endpoints (e.g., for OAuth auth or API calls), attach the `EXTERNAL ACCESS INTEGRATION` **in SQL at `CREATE SERVICE` time**, not in the service spec YAML:

```sql
CREATE SERVICE IF NOT EXISTS <schema>.<service_name>
  IN COMPUTE POOL IDENTIFIER(:pool_name)
  FROM SPECIFICATION_FILE = '/containers/service_spec.yaml'
  EXTERNAL_ACCESS_INTEGRATIONS = (<eai_name>)
  MIN_INSTANCES = 1
  MAX_INSTANCES = 1;
```

On upgrade, re-apply via `ALTER SERVICE` inside `version_initializer`:

```sql
ALTER SERVICE <schema>.<service_name>
  FROM SPECIFICATION_FILE = '/containers/service_spec.yaml';
ALTER SERVICE <schema>.<service_name>
  SET EXTERNAL_ACCESS_INTEGRATIONS = (<eai_name>);
CALL SYSTEM$WAIT_FOR_SERVICES(600, '<schema>.<service_name>');
```

**Ordering in the setup script (Approach A, manifest_version: 2)** — every dependency must exist **before** the service is created:

1. `CREATE NETWORK RULE` — the egress host rule
2. `CREATE SECURITY INTEGRATION` — with `TYPE = API_AUTHENTICATION` and OAuth creds (see `request-security-integration/SKILL.md`)
3. `CREATE SECRET ... TYPE = OAUTH2 API_AUTHENTICATION = <si>` — bound to the SI
4. `CREATE EXTERNAL ACCESS INTEGRATION ... ALLOWED_NETWORK_RULES ... ALLOWED_AUTHENTICATION_SECRETS = ALL ... ALLOWED_API_AUTHENTICATION_INTEGRATIONS`
5. `ALTER APPLICATION SET SPECIFICATION` for both `TYPE = SECURITY_INTEGRATION` and `TYPE = EXTERNAL_ACCESS`
6. `CREATE SERVICE ... EXTERNAL_ACCESS_INTEGRATIONS = (<eai>)` — app specs are auto-granted, so the service can be created directly
7. Register `callbacks.on_spec_approved_or_declined` (restarts service on APPROVED) and `core.version_init` + matching `lifecycle_callbacks` entries in the manifest

The service spec YAML mounts the secret via `snowflakeSecret` + `directoryPath` — see `ref-spcs-service-spec.md` § Mounting Secrets for External API Authentication.

> **Approach B (consumer-owned references) must defer `CREATE SERVICE`** — it fails outright with an unbound-reference error. **Approach A with `manifest_version: 2`** can create the service directly in the setup script because app specs are auto-granted. See § Deferred Service Creation Pattern below for Approach B and manifest_version: 1.

## Deferred Service Creation Pattern (Approach B and manifest_version: 1)

> **Scope:** This pattern applies to **Approach B** (consumer-owned references — always required) and **Approach A with manifest_version: 1** (specs not auto-granted). For **Approach A with manifest_version: 2**, app specs are auto-granted — create the service directly in the setup script (see ordering above) and use `specification_action` only to restart/suspend the service on spec status changes.

**The problem:** An SPCS service that depends on consumer-owned references or unapproved specs cannot be created until its security dependencies are in place:

- **Approach B (consumer-owned EAI/SECRET via references)**: `CREATE SERVICE` **fails outright** when any referenced EAI or secret is unbound. Snowflake docs: *"If a service is created before all the references to an external access integration or secret is allowed, the service creation fails."*
- **Approach A with manifest_version: 1**: OAuth token file is empty (0 bytes) until the consumer approves both specs; SPCS does **not** auto-rotate the mount on spec approval, so deferred creation is required.

**The pattern:** Don't create the service at install. Register a single idempotent reconciler procedure `core.create_or_update_service()` and have every lifecycle hook delegate to it:

```
version_initializer ──┐
register_callback ────┘──► core.create_or_update_service()
```

The reconciler implements a 2×2 matrix over (gate met × service exists):

| Gate met | Service exists | Action |
|----------|----------------|--------|
| No | No | No-op, return success (`deferred; waiting for gate`) |
| No | Yes | No-op, return success (`gate temporarily unmet; leaving service on current spec`) |
| Yes | No | `CREATE SERVICE ... EXTERNAL_ACCESS_INTEGRATIONS = (...)` + `SYSTEM$WAIT_FOR_SERVICES` |
| Yes | Yes | `ALTER SERVICE ... FROM SPECIFICATION_FILE ...` + `ALTER SERVICE ... SET EXTERNAL_ACCESS_INTEGRATIONS = (...)` + `SYSTEM$WAIT_FOR_SERVICES` |

No-op paths return success so install/upgrade succeeds even before the gate is met — Snowflake's built-in rollback only fires on procedure error. CREATE/ALTER failures propagate up through `version_init` and trigger rollback as before.

**The gate** differs between approaches:

- **Approach A**: both `SECURITY_INTEGRATION` and `EXTERNAL_ACCESS` specs are APPROVED (query `SHOW APPROVED SPECIFICATIONS` — omit `IN APPLICATION` when running inside the app context).
- **Approach B**: every required reference returns a non-empty list from `SYSTEM$GET_ALL_REFERENCES(...)` (returns `'[]'` when unbound).

### Reconciler — Approach A with manifest_version: 1 (app-created EAI/SI via specs)

```sql
CREATE OR REPLACE PROCEDURE core.is_service_ready_to_deploy()
  RETURNS BOOLEAN
  LANGUAGE SQL
  EXECUTE AS OWNER
AS $$
BEGIN
  -- Approach A: require BOTH a SECURITY_INTEGRATION and EXTERNAL_ACCESS spec to be APPROVED
  -- NOTE: Inside the app context, use SHOW APPROVED SPECIFICATIONS without IN APPLICATION.
  -- Adding IN APPLICATION causes Snowflake to look for a literal app named "APPLICATION".
  SHOW APPROVED SPECIFICATIONS;
  LET approved_count INTEGER := (
    SELECT COUNT(DISTINCT "type") FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
    WHERE "type" IN ('SECURITY_INTEGRATION', 'EXTERNAL_ACCESS')
  );
  RETURN (:approved_count >= 2);
END;
$$;

CREATE OR REPLACE PROCEDURE core.create_or_update_service()
  RETURNS STRING
  LANGUAGE SQL
  EXECUTE AS OWNER
AS $$
DECLARE
  svc_exists BOOLEAN DEFAULT FALSE;
  gate_met BOOLEAN DEFAULT FALSE;
BEGIN
  CALL core.is_service_ready_to_deploy() INTO :gate_met;

  SHOW SERVICES LIKE '<SERVICE_NAME>' IN SCHEMA services;
  LET svc_count INTEGER := (SELECT COUNT(*) FROM TABLE(RESULT_SCAN(LAST_QUERY_ID())));
  svc_exists := (:svc_count > 0);

  IF (NOT :gate_met) THEN
    IF (:svc_exists) THEN
      RETURN 'gate temporarily unmet; leaving service on current spec';
    ELSE
      RETURN 'deferred; waiting for gate';
    END IF;
  END IF;

  LET pool_name VARCHAR := (SELECT CURRENT_DATABASE()) || '_compute_pool';

  IF (:svc_exists) THEN
    ALTER SERVICE services.<service_name>
      FROM SPECIFICATION_FILE = '/containers/<spec_file>.yaml';
    ALTER SERVICE services.<service_name>
      SET EXTERNAL_ACCESS_INTEGRATIONS = (<eai_name>);
    -- Resume if suspended (e.g. after a spec was declined then re-approved).
    -- SYSTEM$WAIT_FOR_SERVICES fails if the service is in a suspended/suspending state.
    BEGIN
      ALTER SERVICE services.<service_name> RESUME;
    EXCEPTION WHEN OTHER THEN NULL;
    END;
    CALL SYSTEM$WAIT_FOR_SERVICES(600, 'services.<service_name>');
    RETURN 'service upgraded';
  ELSE
    CREATE SERVICE services.<service_name>
      IN COMPUTE POOL IDENTIFIER(:pool_name)
      FROM SPECIFICATION_FILE = '/containers/<spec_file>.yaml'
      EXTERNAL_ACCESS_INTEGRATIONS = (<eai_name>)
      MIN_INSTANCES = 1
      MAX_INSTANCES = 1;
    GRANT USAGE ON SERVICE services.<service_name> TO APPLICATION ROLE app_user;
    GRANT SERVICE ROLE services.<service_name>!<service_role_name> TO APPLICATION ROLE app_user;
    CALL SYSTEM$WAIT_FOR_SERVICES(600, 'services.<service_name>');
    RETURN 'service created';
  END IF;
END;
$$;
GRANT USAGE ON PROCEDURE core.create_or_update_service() TO APPLICATION ROLE app_user;
```

### Reconciler — Approach B (consumer-owned EAI/SECRET via references)

Same reconciler skeleton as Approach A; the `is_service_ready_to_deploy` helper and the `CREATE SERVICE` call differ.

```sql
CREATE OR REPLACE PROCEDURE core.is_service_ready_to_deploy()
  RETURNS BOOLEAN
  LANGUAGE SQL
  EXECUTE AS OWNER
AS $$
DECLARE
  eai_refs VARCHAR;
  secret_refs VARCHAR;
BEGIN
  -- Approach B: require all required references to be bound
  -- SYSTEM$GET_ALL_REFERENCES returns '[]' (empty list) when the reference is unbound.
  -- Strip spaces with REPLACE before comparing since the format may include whitespace.
  eai_refs := (SELECT SYSTEM$GET_ALL_REFERENCES('consumer_external_access'));
  secret_refs := (SELECT SYSTEM$GET_ALL_REFERENCES('consumer_secret'));
  RETURN (REPLACE(:eai_refs, ' ', '') != '[]' AND REPLACE(:secret_refs, ' ', '') != '[]');
END;
$$;
```

In the reconciler's CREATE SERVICE branch, use `reference(...)` for the EAI:

```sql
CREATE SERVICE services.<service_name>
  IN COMPUTE POOL IDENTIFIER(:pool_name)
  FROM SPECIFICATION_FILE = '/containers/<spec_file>.yaml'
  EXTERNAL_ACCESS_INTEGRATIONS = (reference('CONSUMER_EXTERNAL_ACCESS'))
  MIN_INSTANCES = 1
  MAX_INSTANCES = 1;
```

The consumer-supplied secret is mounted into the container via the `secrets:` block in the service spec YAML — no `ALLOWED_AUTHENTICATION_SECRETS` property is needed on `CREATE SERVICE`. On `ALTER SERVICE` use `SET EXTERNAL_ACCESS_INTEGRATIONS = (reference('CONSUMER_EXTERNAL_ACCESS'))`.

Inside the service spec YAML, the secret mount uses `objectReference: <manifest_reference_name>` — SPCS resolves the consumer-bound secret automatically via the manifest reference binding. Do NOT attempt runtime name resolution via `SYSTEM$GET_ALL_REFERENCES` or `SHOW REFERENCES`. See `ref-spcs-service-spec.md` § Mounting Secrets for External API Authentication (the "Approach B" bullet under Key rules).

### Wiring the callbacks

**`version_initializer`** — delegates to the reconciler; fires at install and upgrade. **No direct `CREATE SERVICE` or `ALTER SERVICE`** — doing so on a fresh install breaks the install:

```sql
CREATE OR REPLACE PROCEDURE core.version_init()
  RETURNS STRING
  LANGUAGE SQL
  EXECUTE AS OWNER
AS $$
BEGIN
  -- Compute pool always exists after install/upgrade
  LET pool_name VARCHAR := (SELECT CURRENT_DATABASE()) || '_compute_pool';
  CREATE COMPUTE POOL IF NOT EXISTS IDENTIFIER(:pool_name)
    MIN_NODES = 1 MAX_NODES = 1
    INSTANCE_FAMILY = CPU_X64_XS
    AUTO_RESUME = TRUE AUTO_SUSPEND_SECS = 300;

  -- Delegate all service lifecycle to the reconciler
  CALL core.create_or_update_service();
  RETURN 'OK';
END;
$$;
```

**`specification_action` (Approach A, manifest_version: 2)** — fires when the consumer approves/declines a spec. With manifest_version: 2 the service is created directly in the setup script, so this callback **restarts** the service on approval to refresh the `access_token` mount. Register in the manifest:

```yaml
lifecycle_callbacks:
  version_initializer: core.version_init
  specification_action: callbacks.on_spec_approved_or_declined
```

Implement the callback:

```sql
CREATE OR REPLACE PROCEDURE callbacks.on_spec_approved_or_declined(name STRING, status STRING, payload STRING)
  RETURNS STRING
  LANGUAGE SQL
  EXECUTE AS OWNER
AS $$
BEGIN
  IF (:status = 'APPROVED') THEN
    -- Restart the service so SPCS re-mounts the access_token with valid credentials.
    BEGIN
      ALTER SERVICE services.<service_name> SUSPEND;
    EXCEPTION WHEN OTHER THEN NULL;
    END;
    ALTER SERVICE services.<service_name> RESUME;
    CALL SYSTEM$WAIT_FOR_SERVICES(600, 'services.<service_name>');
  END IF;
  RETURN 'on_spec_approved_or_declined: ' || :name || ' ' || :status;
END;
$$;
-- IMPORTANT: The specification_action callback must be granted to an application role.
-- Without this grant, app installation warns "specification_action does not exist or
-- is not granted to an application role" and the callback will not fire on spec approval.
GRANT USAGE ON PROCEDURE callbacks.on_spec_approved_or_declined(STRING, STRING, STRING)
  TO APPLICATION ROLE app_user;
```

> **manifest_version: 1** does not support `specification_action`. Use the deferred pattern with a manual `start_service()` trigger instead — see § Deferred Service Creation — manifest_version: 1 below.

**`register_callback` (Approach B)** — standard `SYSTEM$SET_REFERENCE` handling, then reconciler on `ADD`:

```sql
CREATE OR REPLACE PROCEDURE config.register_ref_callback(ref_name STRING, op STRING, ref_or_alias STRING)
  RETURNS STRING
  LANGUAGE SQL
  EXECUTE AS OWNER
AS $$
BEGIN
  CASE (:op)
    WHEN 'ADD' THEN
      SELECT SYSTEM$SET_REFERENCE(:ref_name, :ref_or_alias);
      -- Reconciler returns no-op if gate is still unmet (e.g., only 1 of 2 refs bound so far)
      CALL core.create_or_update_service();
    WHEN 'REMOVE' THEN
      SELECT SYSTEM$REMOVE_REFERENCE(:ref_name);
    WHEN 'CLEAR' THEN
      SELECT SYSTEM$REMOVE_REFERENCE(:ref_name);
  END CASE;
  RETURN 'register_ref_callback: ' || :ref_name || ' ' || :op;
END;
$$;
GRANT USAGE ON PROCEDURE config.register_ref_callback(STRING, STRING, STRING)
  TO APPLICATION ROLE app_user;
```

### Setup-script ordering (updated)

With deferred creation, the setup script creates everything **except** the service itself. The service appears later, via callback, once the gate is met.

> **Note:** This ordering applies to **Approach B** and **Approach A with manifest_version: 1**. For **Approach A with manifest_version: 2**, the service is created directly in the setup script — see the ordering section above (§ Attaching EAI to a Service).

**Approach B:**

1. Define `references` for the EAI and SECRET in the manifest (set `required_at_setup: true` on the EAI)
2. Implement `configuration_callback` for each reference (see `ref-eai.md` / `ref-secret.md`)
3. Register `core.is_service_ready_to_deploy`, `core.create_or_update_service`, `core.version_init`, `config.register_ref_callback`
4. Register `lifecycle_callbacks.version_initializer` in the manifest; reference `config.register_ref_callback` from each reference's `register_callback` property
5. ❌ **Do NOT `CREATE SERVICE` in the setup script**

Consumer binds both references → `register_ref_callback` fires for each binding → reconciler creates service after the second binding (gate becomes true). `CREATE SERVICE` succeeds because all references are bound.

### Failure semantics

- **No-op paths return success.** Install/upgrade succeed before the gate is met. `version_init` does not fail on fresh install.
- **`CREATE`/`ALTER` failures propagate.** They trigger Snowflake's built-in rollback (schema + setup script + `version_init` revert). The reconciler only `CREATE`s or `ALTER`s when the gate is met — so failures here are genuinely about service config, not timing.
- **Upgrade with bumped spec sequence.** Specs re-enter `PENDING`. Gate returns `FALSE`. Service stays on the old spec (still running on the old token). Consumer re-approves → `on_spec_approved_or_declined` → reconciler `ALTER`s to new spec. This is the correct behavior — it prevents the service from running the new spec against an unapproved EAI/SI.
- **`DECLINED`.** The service continues running. Consumer can re-approve later; the `specification_action` callback will restart the service to refresh the token.

## Deferred Service Creation — manifest_version: 1 (manual trigger)

> **Same principle as manifest_version: 2 — defer `CREATE SERVICE` until the gate is met.** `manifest_version: 1` lacks `specification_action`, so the gate-crossing trigger is **a consumer-invoked procedure** instead of an automatic callback. The reconciler, gate check, and `version_init` delegator are **identical** to the `manifest_version: 2` Approach A code above.

**Do NOT** create the service at install with the specs still `PENDING`. Doing so produces a broken service with a **zero-byte** mounted secret file (OAuth fetch fails because the SI is not yet active), and the platform does **not** auto-rotate the mount when the SI later transitions to `APPROVED`. Suspend/resume after approval is a workaround for that broken state — deferred creation avoids the broken state entirely.

### Wiring (manifest_version: 1)

Use the **Approach A** reconciler and gate helper from the Deferred Service Creation Pattern above. The only differences:

1. **No `specification_action`** in the manifest (not supported in manifest_version: 1).
2. **`version_init`** already delegates to `core.create_or_update_service()` — on fresh install the gate is unmet, so it returns `'deferred; waiting for gate'` and install succeeds.
3. **Add a consumer-facing `start_service` procedure** that delegates to the reconciler. The consumer calls it once, after approving both specs.

```sql
CREATE OR REPLACE PROCEDURE <schema>.start_service()
  RETURNS STRING
  LANGUAGE SQL
  EXECUTE AS OWNER
AS $$
BEGIN
  -- Idempotent: no-op if gate still unmet, creates service if first call after approval,
  -- ALTERs to current spec if service already exists.
  CALL core.create_or_update_service();
  RETURN 'start_service: ok';
END;
$$;
GRANT USAGE ON PROCEDURE <schema>.start_service() TO APPLICATION ROLE app_user;
```

`resume_service` MAY also delegate to the reconciler so that it works as a recovery entry point (e.g., consumer approved specs late and service was suspended). A minimal implementation simply calls `ALTER SERVICE ... RESUME`; if the service does not yet exist, delegating to the reconciler is safer.

### Consumer install sequence (manifest_version: 1)

```sql
-- 1. Install the app
CREATE APPLICATION <app_name>
  FROM APPLICATION PACKAGE <pkg_name>
  USING '@<pkg>.<schema>.<stage>';

-- 2. Approve both app specifications
ALTER APPLICATION <app_name>
  APPROVE SPECIFICATION oauth_spec SEQUENCE_NUMBER = 1;
ALTER APPLICATION <app_name>
  APPROVE SPECIFICATION eai_spec SEQUENCE_NUMBER = 1;

-- 3. Trigger the reconciler (CREATE SERVICE happens here, against approved specs)
CALL <app_name>.<schema>.start_service();

-- 4. Verify service is ready
CALL <app_name>.<schema>.get_service_status();
```

Step 3 creates the service against the **already-approved** specs, so the OAuth fetch succeeds on the first container start. No suspend/resume is required.

### Anti-pattern (do NOT ship)

Creating the service at install with pending specs and documenting "consumer must suspend+resume after approval" as the supported path. This produces a broken intermediate state (zero-byte token file) that:

- Confuses monitoring (the service appears `READY` while all outbound calls fail with empty-credential errors).
- Requires extra consumer steps for no benefit — if the consumer is already going to run a procedure after approval, that procedure should create the service correctly the first time, not restart a broken one.
- Doesn't compose with upgrades (a spec change with a sequence bump re-`PENDING`s the specs; the service keeps running with a now-invalid token until another suspend/resume).

If you encounter a legacy app that already ships the suspend/resume workflow, migrate it to deferred creation on the next version. The migration is: move `CREATE SERVICE` out of the setup script into the reconciler, add `start_service` as the consumer entry point, and update the README.

## Service Lifecycle Procedures

Provide stored procedures so consumers can manage the service lifecycle. All four procedures use `RETURNS STRING` and return the result directly. Do NOT change the return type to `RETURNS TABLE` or wrap results in `RESULTSET` / `RESULT_SCAN` / `SHOW SERVICES` — these patterns cause syntax errors or incorrect behavior in native apps.

```sql
-- Suspend the service (saves compute costs)
CREATE OR REPLACE PROCEDURE <schema>.suspend_service()
  RETURNS STRING
  LANGUAGE SQL
  EXECUTE AS OWNER
AS $$
BEGIN
  ALTER SERVICE <schema>.<service_name> SUSPEND;
  RETURN 'Service suspended';
END;
$$;
GRANT USAGE ON PROCEDURE <schema>.suspend_service() TO APPLICATION ROLE app_user;

-- Resume the service
CREATE OR REPLACE PROCEDURE <schema>.resume_service()
  RETURNS STRING
  LANGUAGE SQL
  EXECUTE AS OWNER
AS $$
BEGIN
  ALTER SERVICE <schema>.<service_name> RESUME;
  RETURN 'Service resumed';
END;
$$;
GRANT USAGE ON PROCEDURE <schema>.resume_service() TO APPLICATION ROLE app_user;

-- Get service status
CREATE OR REPLACE PROCEDURE <schema>.get_service_status()
  RETURNS STRING
  LANGUAGE SQL
  EXECUTE AS OWNER
AS $$
BEGIN
  RETURN SYSTEM$GET_SERVICE_STATUS('<schema>.<service_name>');
END;
$$;
GRANT USAGE ON PROCEDURE <schema>.get_service_status() TO APPLICATION ROLE app_user;

-- Get service logs (for debugging)
CREATE OR REPLACE PROCEDURE <schema>.get_service_logs(instance_id VARCHAR, container_name VARCHAR)
  RETURNS STRING
  LANGUAGE SQL
  EXECUTE AS OWNER
AS $$
BEGIN
  RETURN SYSTEM$GET_SERVICE_LOGS('<schema>.<service_name>', :instance_id, :container_name);
END;
$$;
GRANT USAGE ON PROCEDURE <schema>.get_service_logs(VARCHAR, VARCHAR) TO APPLICATION ROLE app_user;
```

## Upgrade Pattern

The setup script re-runs fully on every upgrade. `CREATE SERVICE IF NOT EXISTS` is a no-op when the service already exists — the service stays on the old spec. To apply the new version's spec, you need `ALTER SERVICE`.

**The mismatch problem:** If you put `ALTER SERVICE` directly in the setup script and the script fails *after* it fires, the service is already on the new spec but versioned schema objects revert to the previous version — a broken state.

**Recommended:** Put `ALTER SERVICE` inside a `version_initializer` callback. If it fails, Snowflake calls the previous version's `version_initializer` to roll back.

> **Approach B and manifest_version: 1 services must route through the reconciler, not directly `ALTER SERVICE` here.** See § Deferred Service Creation Pattern for the reconciler-based `version_init` that handles both first-install (no service yet, gate not met → no-op) and upgrade (service exists, gate met → ALTER). **Approach A with manifest_version: 2** can use direct `ALTER SERVICE` here because the service is created in the setup script and app specs are auto-granted — see § version_initializer — service uses EAI/secret (Approach A, manifest_version: 2).

### Manifest registration

```yaml
lifecycle_callbacks:
  version_initializer: core.version_init
```

### version_initializer — static spec (simple service, no EAI/secret)

```sql
CREATE OR REPLACE PROCEDURE core.version_init()
  RETURNS STRING
  LANGUAGE SQL
  EXECUTE AS OWNER
AS $$
BEGIN
  ALTER SERVICE services.<service_name>
    FROM SPECIFICATION_FILE = '/containers/spec.yaml';
  CALL SYSTEM$WAIT_FOR_SERVICES(600, 'services.<service_name>');
  RETURN 'OK';
END;
$$;
```

**Note:** 600s (10 min) is a reasonable default for SPCS cold-start. Adjust based on the app's expected startup time.

### version_initializer — template spec with consumer config (simple service, no EAI/secret)

When the spec uses `{{ variable }}` placeholders, the initializer must read stored consumer config from `core.app_config` and re-apply it:

```sql
CREATE OR REPLACE PROCEDURE core.version_init()
  RETURNS STRING
  LANGUAGE SQL
  EXECUTE AS OWNER
AS $$
BEGIN
  LET config_count INTEGER := (SELECT COUNT(*) FROM core.app_config WHERE key = 'api_url');
  IF (:config_count > 0) THEN
    LET api_url VARCHAR := (SELECT value FROM core.app_config WHERE key = 'api_url');
    ALTER SERVICE services.<service_name>
      FROM SPECIFICATION_TEMPLATE_FILE = '/containers/spec.yaml'
      USING (api_url => :api_url);
  ELSE
    -- Fresh install — consumer hasn't configured yet, apply with defaults
    ALTER SERVICE services.<service_name>
      FROM SPECIFICATION_TEMPLATE_FILE = '/containers/spec.yaml'
      USING (api_url => 'https://placeholder.example.com');
  END IF;
  CALL SYSTEM$WAIT_FOR_SERVICES(600, 'services.<service_name>');
  RETURN 'OK';
END;
$$;
```

### version_initializer — service uses EAI/secret (Approach A, manifest_version: 2)

The service already exists (created in setup script). `version_init` runs `ALTER SERVICE` directly — same as a simple service, but also re-applies the EAI:

```sql
CREATE OR REPLACE PROCEDURE core.version_init()
  RETURNS STRING
  LANGUAGE SQL
  EXECUTE AS OWNER
AS $$
BEGIN
  ALTER SERVICE services.<service_name>
    FROM SPECIFICATION_FILE = '/containers/spec.yaml';
  ALTER SERVICE services.<service_name>
    SET EXTERNAL_ACCESS_INTEGRATIONS = (<eai_name>);
  CALL SYSTEM$WAIT_FOR_SERVICES(600, 'services.<service_name>');
  RETURN 'OK';
END;
$$;
```

### version_initializer — service uses EAI/secret (Approach B or manifest_version: 1 — deferred pattern)

See § Deferred Service Creation Pattern → Wiring the callbacks → `version_initializer`. The body becomes a thin delegator: `CALL core.create_or_update_service();`.

### How rollback works

The `version_init` procedure lives in the versioned schema `core`. On rollback, Snowflake reverts the schema to the previous version, so the previous version's `version_init` runs — which references its own spec file. The spec file also belongs to the previous version. Both automatically point to the old code.

```
v2 setup script succeeds → v2 version_init fires → ALTER SERVICE to v2 spec → fails
    ↓
Snowflake reverts versioned schemas to v1
    ↓
v1 version_init fires → ALTER SERVICE to v1 spec → service rolled back  ✓
```

Source: https://docs.snowflake.com/en/developer-guide/native-apps/update-app-develop

## Common setup.sql Mistakes

These errors cause partial script execution — the app installs but procedures/functions are missing:

- **Do NOT `CREATE SCHEMA IF NOT EXISTS core` then `CREATE OR ALTER VERSIONED SCHEMA core`** — fails with `Property 'versioned' cannot be changed`. Use only `CREATE OR ALTER VERSIONED SCHEMA core;`.
- **No `INFORMATION_SCHEMA.COMPUTE_POOLS` or `INFORMATION_SCHEMA.SERVICES`** — these views don't exist in the app context. Use `SHOW COMPUTE POOLS` / `SHOW SERVICES IN APPLICATION` from outside the app instead.
- **No stage prefix for spec files** — use `FROM SPECIFICATION_FILE = '/containers/spec.yaml'`, NOT `FROM @stage SPECIFICATION_FILE = '...'`. In apps, the path is relative to the app root; no stage is needed.
- **No `EXECUTE IMMEDIATE` for static DDL** — write `CREATE COMPUTE POOL`, `CREATE SERVICE` etc. as plain statements. Dynamic SQL adds unnecessary error surface.
- **`CREATE APPLICATION ROLE` must come before any `GRANT ... TO APPLICATION ROLE`** — if the role doesn't exist when a GRANT runs, the setup script fails with "Application role 'APP_USER' does not exist or not authorized."
- **Do NOT use `RETURNS TABLE` for lifecycle procedures** — use `RETURNS STRING`. The `RESULTSET` / `RESULT_SCAN` pattern introduces unnecessary complexity, fragile SQL, and often causes syntax errors at install time.
- **Do NOT `GRANT USAGE ON COMPUTE POOL ... TO APPLICATION`** — the app already owns its compute pools. This statement fails with "Privileges on objects in an application must be granted/revoked via application roles." Only grant statements shown in the Grant Callback Template are needed.
- **Every non-versioned schema the consumer accesses needs `GRANT USAGE ON SCHEMA ... TO APPLICATION ROLE`** — without it, Snowflake's application redaction hides the entire schema. The consumer gets "schema does not exist or not authorized" even if individual objects inside the schema were granted. This applies to the `services` schema and any other non-versioned schemas.
- **Do NOT wrap `INSTANCE_FAMILY` in `IDENTIFIER()`** — `INSTANCE_FAMILY` takes a keyword value like `CPU_X64_XS`, not an object name. Writing `INSTANCE_FAMILY = IDENTIFIER(:var)` fails with "invalid value [TOK_OBJECT_LITERAL] for parameter 'INSTANCE_FAMILY'". Use `INSTANCE_FAMILY = CPU_X64_XS` (bare keyword) or `INSTANCE_FAMILY = :var` (variable holding the string). `IDENTIFIER()` is only for object names like compute pool names.
