---
name: request-external-access-integration
description: "Configure External Access Integrations (EAI) for a Snowflake Native App. Handles both approaches: (1) consumer-owned EAI via references, and (2) app-created EAI via privileges + app specifications. Includes paired secret/OAuth configuration, network rules, configuration callbacks, and the wrapper pattern. Triggers: external access integration, EAI, external API, network rule, app spec EAI, consumer EAI, external access, egress, outbound API, host_ports, allowed_network_rules, configuration_callback."
parent_skill: native-app-provider
---

# External Access Integration Configuration

> **⚠️ MANDATORY**: If your system prompt mentions Snowsight, load [`../references/native-apps-snowsight.md`](../references/native-apps-snowsight.md) before doing anything else.

## When to Load

From the root `native-app-provider` skill when the user needs to configure external API access for a Snowflake Native App — whether the EAI is created by the app or owned by the consumer.

This skill can also be loaded from `request-object-access/SKILL.md` or `request-account-privilege/SKILL.md` when EAI work is detected.

## Prerequisites

**Ask** the user for the following (skip any items already known from a prior skill):

```
To configure external access, I need:
1. **Project directory**: Where are your app files? (e.g., /Users/you/projects/my_app)
2. **Application package name**: What is the application package name? (e.g., MY_APP_PKG)
```

**Locate files:**
- Read `manifest.yml` from the project root
- Determine the setup script path from `artifacts.setup_script` in the manifest (default: `setup.sql`)
- Read the setup script

**STOP** if either file is missing: tell the user which file is missing and suggest loading `setup-app/SKILL.md` to create it.

**Additional prerequisites for Approach A** (app-created EAI):
- `manifest_version` must be `2`. If not, warn the user that auto-granting privileges requires version 2 and that changing it requires a major version upgrade (not a patch). **STOP** for approval before updating.
- The `CREATE EXTERNAL ACCESS INTEGRATION` privilege should be declared in `manifest.yml`. If not yet configured, load `request-account-privilege/SKILL.md` first to add it to the manifest.

## Key Concept

An **External Access Integration (EAI)** allows a Snowflake Native App to make outbound calls to external endpoints (REST APIs, webhooks, etc.). There are two approaches depending on **who creates the EAI**:

| Scenario | Who Creates the EAI | Approach | Section |
|----------|---------------------|----------|---------|
| App creates its own EAI | The app (provider) | **Privilege + App Specification** | [Approach A](#approach-a-app-created-eai-privilege--app-specification) |
| App uses consumer's existing EAI | The consumer | **Reference** (object access) | [Approach B](#approach-b-consumer-owned-eai-reference) |

**How to choose:**

- **Approach A** — The provider knows exactly which endpoints the app needs and wants to control the EAI. The consumer only approves/rejects the app specification. This is the more common pattern.
- **Approach B** — The consumer already has an EAI configured (e.g., for a shared corporate API gateway) and the app needs to use it. The consumer binds their existing EAI to the app after installation.

> **IMPORTANT — Account-Level Objects**: External access integrations and security integrations are **account-level objects**, NOT schema-level objects. Do NOT use a schema prefix when creating them:
> - ✅ Correct: `CREATE EXTERNAL ACCESS INTEGRATION my_eai ...`
> - ❌ Wrong: `CREATE EXTERNAL ACCESS INTEGRATION core.my_eai ...`
> - ✅ Correct: `CREATE SECURITY INTEGRATION my_si ...`
> - ❌ Wrong: `CREATE SECURITY INTEGRATION core.my_si ...`
>
> Only secrets and network rules are schema-level objects that require a schema prefix (e.g., `core.my_secret`, `core.my_network_rule`).

## Workflow

### Step 1: Determine Approach

**Ask** the user:

```
Who creates the External Access Integration?

A) **The app** creates and owns the EAI
   → The provider defines the endpoints; the consumer approves an app specification
   → Use this when the app needs to call specific known external APIs

B) **The consumer** creates and owns the EAI
   → The consumer has an existing EAI that the app needs to use
   → Use this when the app uses a consumer-provided integration
```

If the user's prior messages already indicate the approach (e.g., they mentioned "consumer's EAI" or "app needs to call api.example.com"), skip the prompt and proceed to the correct approach.

---

## Approach A: App-Created EAI (Privilege + App Specification)

The app creates its own EAI. This requires:
1. The `CREATE EXTERNAL ACCESS INTEGRATION` privilege in the manifest
2. A **network rule** defining allowed endpoints
3. An **external access integration** referencing the network rule
4. An **app specification** of type `EXTERNAL_ACCESS` declaring the host ports

The privilege is auto-granted at install, but the EAI is not usable until the consumer approves the app specification.

### Step A1: Collect Endpoint Details

**Ask** the user:

```
What external endpoints does your app need to reach?

1. **Hostname(s)**: e.g., api.example.com, api.example.com:443
2. **Purpose**: What does the app do with this endpoint?
3. **Does the app need a secret** (OAuth, API key) for authentication?
```

### Step A2: Add Manifest Privilege

Add to the `privileges` block in `manifest.yml`:

```yaml
privileges:
  - CREATE EXTERNAL ACCESS INTEGRATION:
      description: "Allows the app to connect to <service_name> for <purpose>"
```

### Step A3: Generate Setup Script Objects and App Specification

> **REQUIRED**: You MUST read the file `../references/app-spec-eai.md` before generating any SQL. It contains the exact syntax templates. Do NOT generate SQL from memory — the syntax is non-obvious and errors are hard to debug.

Using the endpoints collected in Step A1 and the templates from the reference file, generate the following objects in the setup script — **in this order**:

1. **Network rule** — `CREATE NETWORK RULE IF NOT EXISTS` with `TYPE = HOST_PORT`, `MODE = EGRESS`, and `VALUE_LIST` containing the user's endpoints
2. **External access integration** — `CREATE EXTERNAL ACCESS INTEGRATION IF NOT EXISTS` with `ALLOWED_NETWORK_RULES` referencing the network rule and `ENABLED = TRUE`
3. **Function or procedure** — the app code that calls the external API, with `EXTERNAL_ACCESS_INTEGRATIONS = (...)` binding it to the EAI. Grant `USAGE` to an application role.
4. **App specification** — `ALTER APPLICATION SET SPECIFICATION` with `TYPE = EXTERNAL_ACCESS`. The `HOST_PORTS` values must exactly match the `VALUE_LIST` in the network rule.

For each object, check if it already exists in the setup script before creating a new one. If it exists, update it to include the new endpoints rather than duplicating.

> **SPCS branch — if the EAI is used by an SPCS service (not a UDF/procedure):**
> - Attach the EAI via `CREATE SERVICE ... EXTERNAL_ACCESS_INTEGRATIONS = (<eai>)` in SQL. Do **NOT** put `EXTERNAL_ACCESS_INTEGRATIONS` in the service spec YAML.
> - If the service also mounts a `SECRET`, the secret is mounted via `secrets: - snowflakeSecret: ... directoryPath: ...` in the service spec YAML — not via `SECRETS = (...)` in SQL.
> - **Service creation:** With `manifest_version: 2`, app specs are auto-granted — the service can be created directly in the setup script. The OAuth token is populated on first container start. No deferred pattern or `specification_action` callback is needed. See `../references/ref-spcs-setup-script.md` § Attaching EAI to a Service.
> - **manifest_version: 1** (lacks `specification_action`): use the same deferred pattern with a **manual trigger**. Keep the reconciler and `version_init`; do **not** `CREATE SERVICE` in the setup script. Add a `start_service()` procedure that delegates to the reconciler, and document the consumer install sequence as: install → approve both specs → `CALL <app>.<schema>.start_service()` → verify. See `../references/ref-spcs-setup-script.md` § Deferred Service Creation — manifest_version: 1 (manual trigger). Do **not** ship the legacy "create at install + consumer suspend/resume" workflow — it produces a broken 0-byte-token state and is an anti-pattern.
> - See also `add-containers/SKILL.md` Step 4.5a, `../references/ref-spcs-service-spec.md` § Mounting Secrets for External API Authentication, and `../references/ref-spcs-setup-script.md` § Attaching EAI to a Service.

### Step A4: Validate (Approach A)

- [ ] `manifest_version` is `2`
- [ ] `CREATE EXTERNAL ACCESS INTEGRATION` privilege is in the manifest with a description
- [ ] Network rule exists in setup script with `TYPE = HOST_PORT` and `MODE = EGRESS`
- [ ] EAI exists in setup script referencing the network rule
- [ ] App specification exists with `TYPE = EXTERNAL_ACCESS`
- [ ] **`HOST_PORTS` in the app specification matches `VALUE_LIST` in the network rule** — mismatches cause approval failures
- [ ] Function/procedure using the EAI exists and is granted to an application role
- [ ] Inform user: the EAI is created at install, but external calls will fail until the consumer approves the app specification

---

## Approach B: Consumer-Owned EAI (Reference)

The consumer creates and owns the EAI. The app requests access via the references mechanism.

### Step B1: Collect Reference Details

**Ask** the user:

```
I'll configure a reference to the consumer's External Access Integration.

1. **Reference name**: A short identifier (e.g., consumer_external_access)
2. **Label**: Display name for the consumer (e.g., "External Access Integration")
3. **Description**: Why does the app need this EAI?
4. **Host ports**: What endpoints will the EAI allow? (e.g., api.example.com)
5. **Does the app also need a paired secret** for authentication (OAuth2, API key)?
```

If a paired secret is needed, also collect:

```
For the paired secret:
6. **Secret reference name**: (e.g., consumer_secret)
7. **Secret label**: Display name (e.g., "API Secret")
8. **Secret description**: Why does the app need this secret?
9. **Secret type**: One of:
   - **OAUTH2** — OAuth2 grant flow (most common for API authentication)
   - **GENERIC_STRING** — Generic string (e.g., API key, bearer token)
   - **PASSWORD** — Username/password pair
   If OAUTH2:
   - **OAuth scopes**: (e.g., https://api.example.com/.default)
   - **Token endpoint**: (e.g., https://provider.example.com/oauth2/token)
   - **Authorization endpoint** (optional): (e.g., https://provider.example.com/oauth2/authorize)
```

### Step B2: Add Manifest References and Generate Callbacks

**Read `../references/ref-eai.md`** for the EAI reference. It contains:
- Manifest reference definition template (with `object_type: EXTERNAL ACCESS INTEGRATION`)
- Configuration callback template (with `host_ports`, `allowed_secrets`, `secret_references`)
- Register callback template (with deferred creation call on `'ADD'`)
- Deferred creation helper pattern for functions using `reference()`
- Wrapper pattern (required for consumer access)

**If a paired secret is needed**, also **read `../references/ref-secret.md`**. It contains:
- Manifest reference definition template (with `object_type: SECRET`)
- Configuration callback template for OAUTH2 secrets (with `oauth_scopes`, `oauth_token_endpoint`)
- Instructions for combining EAI and SECRET `WHEN` cases in a single `GET_CONFIGURATION_FOR_REFERENCE` procedure

Follow the templates in those reference docs to generate:

1. **Manifest references** — Add EAI reference (and SECRET reference if paired) to `manifest.yml`
2. **Register callback** — Reuse existing or generate from template in the reference doc; must call the deferred creation helper on `'ADD'`
3. **Configuration callback** — Generate `GET_CONFIGURATION_FOR_REFERENCE` with `WHEN` cases for each reference, using collected details from Step B1
4. **Deferred creation helper** — A stored procedure that creates the function/procedure using `reference('...')` — see the deferred creation pattern in `../references/ref-eai.md`
5. **Wrapper procedure** — A consumer-callable stored procedure that calls the internal function

**Critical rules** (enforced regardless of reference doc templates):
- EAI references: only allowed privilege is `USAGE`; **cannot** have `multi_valued: true`; **must** have `configuration_callback`
- SECRET references: allowed privileges are `USAGE` and `READ`; **cannot** have `multi_valued: true`; **must** have `configuration_callback`
- Without `configuration_callback`, Snowflake raises `Missing field 'configuration_callback'`
- The EAI configuration's `secret_references` list must match the SECRET reference names in the manifest (UPPER CASE)
- If a configuration callback already exists in the setup script, add new `WHEN` cases rather than creating a duplicate procedure
- Do not place `CREATE FUNCTION/PROCEDURE ... EXTERNAL_ACCESS_INTEGRATIONS = (reference('...'))` at the top level of the setup script — use the deferred creation pattern in `../references/ref-eai.md`
- Inside the deferred creation helper, there are **two quoting levels**: (1) the outer `$$` body where single quotes are literal — use them for `reference('...')`, `PACKAGES = ('...')`, etc.; (2) the inner function body delimited by `AS '...'` where single quotes must be doubled (`''`). Do NOT double-quote `reference()` arguments — they are at the `$$` level. Only double quotes inside the `AS '...'` body string (e.g., Python code). See the template in `../references/ref-eai.md` for exact examples.
- **Guard check in deferred creation helper**: When both EAI and SECRET references are used, the register callback fires on each `'ADD'` independently. The deferred creation helper **MUST** check that all references are bound (using `SYSTEM$GET_ALL_REFERENCES`) before creating the function — see the template in `../references/ref-eai.md`. Without this guard, the first `'ADD'` will fail with `Reference definition '...' is missing a reference association`.

> **SPCS branch — if the reference is used by an SPCS service (not a UDF/procedure):**
> - Deferred creation is **REQUIRED, not optional**. `CREATE SERVICE` fails outright with an unbound-reference error if any referenced EAI or SECRET is not bound. Snowflake docs: *"If a service is created before all the references to an external access integration or secret is allowed, the service creation fails."*
> - Route service creation through `core.create_or_update_service()` called from `config.register_ref_callback` on each `'ADD'`. The gate helper uses `SYSTEM$GET_REFERENCE('CONSUMER_EXTERNAL_ACCESS', ...)` + `SYSTEM$GET_REFERENCE('CONSUMER_SECRET', ...)` — both must return non-null before the reconciler creates the service.
> - `CREATE SERVICE` uses `EXTERNAL_ACCESS_INTEGRATIONS = (reference('CONSUMER_EXTERNAL_ACCESS'))` with `ALLOWED_AUTHENTICATION_SECRETS = ALL` (Snowflake recommendation for consumer-supplied secrets — see [container-eai-example](https://docs.snowflake.com/en/developer-guide/native-apps/container-eai-example)).
> - The secret is mounted via `secrets: - snowflakeSecret: { objectReference: <manifest_ref_name> } directoryPath: ...` in the service spec YAML — use `objectReference` with the manifest reference name (e.g., `consumer_secret`); SPCS resolves the consumer-bound secret automatically. Do NOT resolve the secret name at runtime. See `../references/ref-spcs-service-spec.md` § Mounting Secrets for External API Authentication (the "Approach B" bullet under Key rules).
> - See also `add-containers/SKILL.md` Step 4.5b and `../references/ref-spcs-setup-script.md` § Deferred Service Creation Pattern → Reconciler — Approach B.

### Step B3: Validate (Approach B)

- [ ] Each EAI/SECRET reference has all required fields: `label`, `description`, `privileges`, `object_type`, `register_callback`, `configuration_callback`
- [ ] EAI privileges are exactly `[USAGE]`; SECRET privileges are `[USAGE, READ]`
- [ ] Neither EAI nor SECRET references have `multi_valued: true`
- [ ] `register_callback` procedure exists in setup script and is granted to an application role
- [ ] `GET_CONFIGURATION_FOR_REFERENCE` procedure exists in setup script with `WHEN` cases for each reference name (UPPER CASE)
- [ ] `host_ports` in the EAI configuration are accurate
- [ ] `secret_references` in the EAI configuration match the SECRET reference names in the manifest (UPPER CASE)
- [ ] OAuth properties (scopes, token endpoint) match the intended provider
- [ ] Configuration callback procedure is granted to an application role
- [ ] Functions using `reference('...')` are NOT at the top level of the setup script — they are inside a deferred creation helper procedure
- [ ] The inner function/procedure body inside the deferred creation helper uses single-quoted `AS '...'` (not `$$`) to avoid nested dollar-quoting. `reference()` arguments use normal single quotes (at `$$` level). Only Python/JS code inside `AS '...'` uses doubled quotes.
- [ ] The register callback calls the deferred creation helper on `'ADD'`
- [ ] A consumer-callable wrapper procedure exists and is granted to an application role

---

## Stopping Points

- Prerequisites: If files are missing
- Step 1: While determining approach (if ambiguous)
- Step A1 / B1: While collecting details from user
- Step A4 / B3: Present validation results

## Output

**Approach A (app-created):**
- Updated `manifest.yml` with `CREATE EXTERNAL ACCESS INTEGRATION` privilege
- Network rule, EAI, app specification, and function/procedure SQL added to setup script
- User informed about consumer approval requirement

**Approach B (consumer-owned):**
- Updated `manifest.yml` with EAI reference (and SECRET reference if paired)
- Register callback and configuration callback procedures added to setup script
- User informed about reference binding
