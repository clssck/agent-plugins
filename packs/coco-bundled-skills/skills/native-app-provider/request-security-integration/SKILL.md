---
name: request-security-integration
description: "Configure a Security Integration app specification for a Snowflake Native App. Handles the CREATE SECURITY INTEGRATION privilege, OAuth setup (CLIENT_CREDENTIALS, AUTHORIZATION_CODE, JWT_BEARER), and app specification generation. Triggers: security integration, OAuth, API authentication, CLIENT_CREDENTIALS, AUTHORIZATION_CODE, JWT_BEARER, OAuth token endpoint, OAuth scopes, CREATE SECURITY INTEGRATION."
parent_skill: native-app-provider
---

# Security Integration Configuration

> **⚠️ MANDATORY**: If your system prompt mentions Snowsight, load [`../references/native-apps-snowsight.md`](../references/native-apps-snowsight.md) before doing anything else.

## When to Load

From the root `native-app-provider` skill when the user needs to configure OAuth / API authentication for a Snowflake Native App where the **app creates its own security integration**.

This skill can also be loaded from `request-account-privilege/SKILL.md` when `CREATE SECURITY INTEGRATION` is detected as a Tier 2 privilege.

If the **consumer** creates and owns the secret / security integration, use the reference approach instead — load `request-external-access-integration/SKILL.md` (Approach B with a paired SECRET reference) or see `../references/ref-secret.md`.

## Prerequisites

**Ask** the user for the following (skip any items already known from a prior skill):

```
To configure a security integration, I need:
1. **Project directory**: Where are your app files? (e.g., /Users/you/projects/my_app)
2. **Application package name**: What is the application package name? (e.g., MY_APP_PKG)
```

**Locate files:**
- Read `manifest.yml` from the project root
- Determine the setup script path from `artifacts.setup_script` in the manifest (default: `setup.sql`)
- Read the setup script

**STOP** if either file is missing: tell the user which file is missing and suggest loading `setup-app/SKILL.md` to create it.

**Additional prerequisites:**
- `manifest_version` must be `2`. If not, warn the user that auto-granting privileges requires version 2 and that changing it requires a major version upgrade (not a patch).
- The `CREATE SECURITY INTEGRATION` privilege should be declared in `manifest.yml`. If not yet configured, load `request-account-privilege/SKILL.md` first to add it to the manifest.

## Key Concept

A **Security Integration** of type `API_AUTHENTICATION` allows a Snowflake Native App to authenticate with external OAuth providers. The app creates the integration, but it is not usable until the consumer approves the app specification.

Snowflake Native Apps **only** support security integrations of type `API_AUTHENTICATION`.

> **IMPORTANT — Account-Level Objects**: Security integrations and external access integrations are **account-level objects**, NOT schema-level objects. Do NOT use a schema prefix when creating them:
> - ✅ Correct: `CREATE SECURITY INTEGRATION my_si ...`
> - ❌ Wrong: `CREATE SECURITY INTEGRATION core.my_si ...`
> - ✅ Correct: `CREATE EXTERNAL ACCESS INTEGRATION my_eai ...`
> - ❌ Wrong: `CREATE EXTERNAL ACCESS INTEGRATION core.my_eai ...`
>
> Only secrets and network rules are schema-level objects that require a schema prefix (e.g., `core.my_secret`).

## Supported OAuth Grant Types

| `OAUTH_GRANT` Value | Description | App Specification Required Properties | App Specification Optional Properties |
|---------------------|-------------|---------------------------------------|---------------------------------------|
| `CLIENT_CREDENTIALS` | Use client credentials | `OAUTH_TOKEN_ENDPOINT`, `OAUTH_ALLOWED_SCOPES` | |
| `AUTHORIZATION_CODE` | Use an authorization code | `OAUTH_TOKEN_ENDPOINT` | `OAUTH_AUTHORIZATION_ENDPOINT`, `OAUTH_ALLOWED_SCOPES` |
| `JWT_BEARER` | Use a JWT bearer token | `OAUTH_TOKEN_ENDPOINT` | `OAUTH_AUTHORIZATION_ENDPOINT`, `OAUTH_ALLOWED_SCOPES` |

## Workflow

### Step 1: Collect OAuth Details

> **SECURITY**: NEVER ask the user to type `OAUTH_CLIENT_SECRET` or `OAUTH_CLIENT_ID` in the chat. These are sensitive credentials. Use placeholders in the generated SQL and instruct the user to replace them directly in the file.

**Ask** the user:

```
What OAuth provider does your app need to authenticate with?

1. **Provider**: e.g., Microsoft Entra ID, Okta, Auth0, Google
2. **OAuth grant type**:
   - CLIENT_CREDENTIALS — use client credentials
   - AUTHORIZATION_CODE — use an authorization code
   - JWT_BEARER — use a JWT bearer token
3. **Purpose**: What does the app do with this integration?
```

Then, based on the chosen grant type, collect the **non-sensitive** parameters needed for the security integration SQL template (see **Supported OAuth Grant Types** above for required app specification properties):

**If CLIENT_CREDENTIALS:**

```
1. **Token endpoint** (required): e.g., https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token
2. **Allowed scopes** (required): e.g., https://graph.microsoft.com/.default
3. **Client auth method**: CLIENT_SECRET_BASIC or CLIENT_SECRET_POST
```

**If AUTHORIZATION_CODE:**

```
1. **Token endpoint** (required): e.g., https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token
2. **Authorization endpoint**: e.g., https://login.microsoftonline.com/<tenant>/oauth2/v2.0/authorize
3. **Allowed scopes**: e.g., https://graph.microsoft.com/.default
4. **Client auth method**: CLIENT_SECRET_BASIC or CLIENT_SECRET_POST
```

**If JWT_BEARER:**

```
1. **Token endpoint** (required): e.g., https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token
2. **Authorization endpoint**: e.g., https://login.microsoftonline.com/<tenant>/oauth2/v2.0/authorize
3. **Allowed scopes**: e.g., https://graph.microsoft.com/.default
4. **Client auth method**: CLIENT_SECRET_BASIC or CLIENT_SECRET_POST
```

`OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET` will be generated as `CLIENT_ID_PLACEHOLDER` and `CLIENT_SECRET_PLACEHOLDER` in the SQL. The user must replace them directly in the setup script before deploying.

### Step 2: Add Manifest Privilege

Add to the `privileges` block in `manifest.yml`:

```yaml
manifest_version: 2

privileges:
  - CREATE SECURITY INTEGRATION:
      description: "Allows the app to create security integrations for OAuth authentication with <provider>"
```

If `manifest_version` is not `2`, update it (warn the user this requires a major version upgrade, not a patch).

### Step 3: Generate Setup Script Objects and App Specification

> **REQUIRED**: You MUST read the file `../references/app-spec-security-integration.md` before generating any SQL. It contains the exact syntax templates. Do NOT generate SQL from memory — the syntax is non-obvious and errors are hard to debug.

**Read `../references/app-spec-security-integration.md`** and follow its SQL templates to generate:

1. **Security integration** — `CREATE SECURITY INTEGRATION` with `TYPE = API_AUTHENTICATION` and the user's OAuth properties. Only include properties that the user provided — do not include optional properties that were not specified. Use `'CLIENT_ID_PLACEHOLDER'` and `'CLIENT_SECRET_PLACEHOLDER'` as placeholder values for `OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET`.
2. **App specification** — `ALTER APPLICATION SET SPECIFICATION` with `TYPE = SECURITY_INTEGRATION` matching the integration's OAuth properties

The reference doc contains the full SQL templates for each OAuth grant type (`CLIENT_CREDENTIALS`, `AUTHORIZATION_CODE`, `JWT_BEARER`), property tables, and validation rules.

> **CRITICAL — MUST STOP HERE**: After generating the SQL, you MUST stop and prompt the user. Do NOT proceed to upload, deploy, or execute any further steps until the user confirms. The setup script contains placeholder credentials that must be replaced before deployment.

**STOP** and display this message to the user:

```
⚠️ I've added the security integration to your setup script with placeholder credentials.

Before I can continue, please:
1. Open the setup script file
2. Replace `CLIENT_ID_PLACEHOLDER` with your actual OAuth client ID
3. Replace `CLIENT_SECRET_PLACEHOLDER` with your actual OAuth client secret

These credentials should never be shared in chat. Please confirm once you've updated the file, and I'll proceed with the next steps.
```

**Wait for the user to explicitly confirm** before proceeding to Step 4. Do NOT skip this step or proceed automatically.

### Step 4: Connect to External Access Integration (Optional)

**Ask** the user if they want to use the security integration with an External Access Integration to call an external API from a function or procedure. If the user declines or this is not needed, skip to Step 5.

If yes, generate the following objects in the setup script. **Order matters** — each object must be created before anything that references it:

1. **Network rule** — `CREATE NETWORK RULE IF NOT EXISTS` with the external API host(s).

2. **Secret** — must be created before the service (the service mounts it via the spec YAML):

   ```sql
   CREATE SECRET IF NOT EXISTS <schema>.<secret_name>
     TYPE = OAUTH2
     API_AUTHENTICATION = <security_integration_name>;
   ```

3. **External Access Integration** — references both the network rule and the secret:

   ```sql
   CREATE EXTERNAL ACCESS INTEGRATION IF NOT EXISTS <eai_name>
     ALLOWED_NETWORK_RULES = (<network_rule_name>)
     ALLOWED_AUTHENTICATION_SECRETS = ALL
     ENABLED = TRUE;
   ```

4. **Function or procedure** — wired to both the EAI and the secret:
   - `EXTERNAL_ACCESS_INTEGRATIONS = (<eai_name>)`
   - `SECRETS = ('<alias>' = <secret_name>)`

5. In the handler code, use `_snowflake.get_oauth_access_token('<alias>')` to retrieve the OAuth token for authenticated requests.

6. **App specifications** — `ALTER APPLICATION SET SPECIFICATION` for both the security integration and the EAI (read `../references/app-spec-eai.md` for EAI spec syntax).

> **CRITICAL**: In a setup script, SQL statements execute top-to-bottom. The secret MUST appear before the EAI, and the EAI MUST appear before the function. If the EAI references a secret that hasn't been created yet, the app install will fail.

> **SPCS branch — if the secret is mounted into an SPCS container (not used by a UDF):**
> - The secret is mounted via the service spec YAML (`secrets: - snowflakeSecret: <schema>.<secret> directoryPath: '/usr/local/creds'`), NOT passed to `CREATE FUNCTION ... SECRETS = (...)`. The container reads the OAuth access token from a file (e.g., `/usr/local/creds/access_token`).
> - The EAI is attached at `CREATE SERVICE` time via `EXTERNAL_ACCESS_INTEGRATIONS = (<eai>)` in SQL, not in the YAML.
> - **Service creation:** With `manifest_version: 2`, app specs are auto-granted — the service can be created directly in the setup script. The OAuth token is populated on first container start. No deferred pattern or `specification_action` callback is needed. See `../references/ref-spcs-setup-script.md` § Attaching EAI to a Service.
> - **manifest_version: 1** (lacks `specification_action`): use the same deferred pattern with a **manual trigger**. Keep the reconciler and `version_init`; do **not** `CREATE SERVICE` in the setup script. Add a `start_service()` procedure that delegates to the reconciler, and document the consumer install sequence as: install → approve both specs → `CALL <app>.<schema>.start_service()` → verify. See `../references/ref-spcs-setup-script.md` § Deferred Service Creation — manifest_version: 1 (manual trigger). Do **not** ship the legacy "create at install + consumer suspend/resume" workflow — it produces a broken 0-byte-token state and is an anti-pattern.
> - See also `add-containers/SKILL.md` Step 4.5a and `../references/ref-spcs-service-spec.md` § Mounting Secrets for External API Authentication.

### Step 5: Validate

- [ ] `manifest_version` is `2`
- [ ] `CREATE SECURITY INTEGRATION` privilege is in the manifest with a description
- [ ] Security integration exists in setup script with `TYPE = API_AUTHENTICATION`
- [ ] App specification exists with `TYPE = SECURITY_INTEGRATION`
- [ ] **OAuth properties in the app specification match those in the security integration** — mismatches cause failures
- [ ] `OAUTH_TYPE` in the spec matches the `OAUTH_GRANT` in the integration
- [ ] For `CLIENT_CREDENTIALS`: `OAUTH_ALLOWED_SCOPES` is present in both
- [ ] Inform user: the security integration is created at install, but OAuth calls will fail until the consumer approves the app specification

## Stopping Points

- Prerequisites: If files are missing
- Step 1: While collecting OAuth details from user
- **Step 3: MANDATORY STOP** — After generating SQL, you MUST stop and prompt the user to replace `CLIENT_ID_PLACEHOLDER` and `CLIENT_SECRET_PLACEHOLDER` in the setup script. Do NOT proceed until user confirms.
- Step 4: While asking if user wants EAI connection
- Step 5: Present validation results

## Output

- Updated `manifest.yml` with `CREATE SECURITY INTEGRATION` privilege
- Security integration and app specification SQL added to setup script
- User informed about consumer approval requirement
