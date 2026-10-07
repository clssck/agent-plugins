---
name: app-spec-security-integration
description: "Reference for configuring Security Integration app specifications in a Snowflake Native App."
parent_skill: native-app-provider
---

# App Specification: Security Integration

Loaded by `request-account-privilege` when `CREATE SECURITY INTEGRATION` is detected.

## When This Applies

The **app itself** creates the Security Integration. This requires:

1. The `CREATE SECURITY INTEGRATION` privilege in the manifest
2. A **security integration** of type `API_AUTHENTICATION` in the setup script
3. An **app specification** of type `SECURITY_INTEGRATION` declaring OAuth properties

The privilege is auto-granted at install, but the security integration is not usable until the consumer approves the app specification.

Use this approach when the app creates and owns the security integration. If the **consumer** creates and owns the secret/security integration, use the reference approach instead (`references/ref-secret.md`).

**Note**: Snowflake Native Apps only support security integrations of type `API_AUTHENTICATION`.

## Supported OAuth Grant Types

| `OAUTH_GRANT` Value | Description | App Specification Required Properties | App Specification Optional Properties |
|---------------------|-------------|---------------------------------------|---------------------------------------|
| `CLIENT_CREDENTIALS` | Use client credentials | `OAUTH_TOKEN_ENDPOINT`, `OAUTH_ALLOWED_SCOPES` | |
| `AUTHORIZATION_CODE` | Use an authorization code | `OAUTH_TOKEN_ENDPOINT` | `OAUTH_AUTHORIZATION_ENDPOINT`, `OAUTH_ALLOWED_SCOPES` |
| `JWT_BEARER` | Use a JWT bearer token | `OAUTH_TOKEN_ENDPOINT` | `OAUTH_AUTHORIZATION_ENDPOINT`, `OAUTH_ALLOWED_SCOPES` |

## Required Objects

### 1. Manifest privilege

```yaml
manifest_version: 2

privileges:
  - CREATE SECURITY INTEGRATION:
      description: "Allows the app to create security integrations for OAuth authentication with <provider>"
```

### 2. Security integration (in setup script)

**CLIENT_CREDENTIALS:**

```sql
CREATE SECURITY INTEGRATION IF NOT EXISTS <integration_name>
  TYPE = API_AUTHENTICATION
  AUTH_TYPE = OAUTH2
  OAUTH_CLIENT_AUTH_METHOD = { CLIENT_SECRET_BASIC | CLIENT_SECRET_POST }
  OAUTH_CLIENT_ID = 'CLIENT_ID_PLACEHOLDER'
  OAUTH_CLIENT_SECRET = 'CLIENT_SECRET_PLACEHOLDER'
  OAUTH_GRANT = 'CLIENT_CREDENTIALS'
  OAUTH_TOKEN_ENDPOINT = '<token_endpoint>'
  OAUTH_ALLOWED_SCOPES = ('<scope_1>')
  ENABLED = TRUE;
```

**AUTHORIZATION_CODE:**

```sql
CREATE SECURITY INTEGRATION IF NOT EXISTS <integration_name>
  TYPE = API_AUTHENTICATION
  AUTH_TYPE = OAUTH2
  OAUTH_AUTHORIZATION_ENDPOINT = '<authorization_endpoint>'
  OAUTH_TOKEN_ENDPOINT = '<token_endpoint>'
  OAUTH_CLIENT_AUTH_METHOD = { CLIENT_SECRET_BASIC | CLIENT_SECRET_POST }
  OAUTH_CLIENT_ID = 'CLIENT_ID_PLACEHOLDER'
  OAUTH_CLIENT_SECRET = 'CLIENT_SECRET_PLACEHOLDER'
  OAUTH_GRANT = 'AUTHORIZATION_CODE'
  ENABLED = TRUE;
```

**JWT_BEARER:**

```sql
CREATE SECURITY INTEGRATION IF NOT EXISTS <integration_name>
  TYPE = API_AUTHENTICATION
  AUTH_TYPE = OAUTH2
  OAUTH_AUTHORIZATION_ENDPOINT = '<authorization_endpoint>'
  OAUTH_TOKEN_ENDPOINT = '<token_endpoint>'
  OAUTH_CLIENT_AUTH_METHOD = { CLIENT_SECRET_BASIC | CLIENT_SECRET_POST }
  OAUTH_CLIENT_ID = 'CLIENT_ID_PLACEHOLDER'
  OAUTH_CLIENT_SECRET = 'CLIENT_SECRET_PLACEHOLDER'
  OAUTH_GRANT = 'JWT_BEARER'
  ENABLED = TRUE;
```

The `OAUTH_GRANT` value determines which OAuth flow is used: `CLIENT_CREDENTIALS`, `AUTHORIZATION_CODE`, or `JWT_BEARER`.

### 3. App specification

**CLIENT_CREDENTIALS example:**

```sql
ALTER APPLICATION SET SPECIFICATION oauth_spec
  TYPE = SECURITY_INTEGRATION
  LABEL = 'Connection to <provider>'
  DESCRIPTION = 'Integrates <provider> for <purpose>'
  OAUTH_TYPE = 'CLIENT_CREDENTIALS'
  OAUTH_TOKEN_ENDPOINT = 'https://login.microsoftonline.com/<tenant_id>/oauth2/v2.0/token'
  OAUTH_ALLOWED_SCOPES = ('https://graph.microsoft.com/.default');
```

**AUTHORIZATION_CODE example:**

```sql
ALTER APPLICATION SET SPECIFICATION oauth_spec
  TYPE = SECURITY_INTEGRATION
  LABEL = 'User authentication with <provider>'
  DESCRIPTION = 'Enables user-delegated access to <provider>'
  OAUTH_TYPE = 'AUTHORIZATION_CODE'
  OAUTH_TOKEN_ENDPOINT = 'https://login.microsoftonline.com/<tenant_id>/oauth2/v2.0/token'
  OAUTH_AUTHORIZATION_ENDPOINT = 'https://login.microsoftonline.com/<tenant_id>/oauth2/v2.0/authorize';
```

**JWT_BEARER example:**

```sql
ALTER APPLICATION SET SPECIFICATION oauth_spec
  TYPE = SECURITY_INTEGRATION
  LABEL = 'JWT auth with <provider>'
  DESCRIPTION = 'Token-based authentication with <provider>'
  OAUTH_TYPE = 'JWT_BEARER'
  OAUTH_TOKEN_ENDPOINT = 'https://login.microsoftonline.com/<tenant_id>/oauth2/v2.0/token';
```

### App specification properties

| Property | Required | Description |
|----------|----------|-------------|
| `TYPE` | Yes | Must be `SECURITY_INTEGRATION` |
| `LABEL` | Yes | Short display name shown to consumer |
| `DESCRIPTION` | Yes | Explains why the app needs this integration |
| `OAUTH_TYPE` | Yes | One of: `CLIENT_CREDENTIALS`, `AUTHORIZATION_CODE`, `JWT_BEARER` |
| `OAUTH_TOKEN_ENDPOINT` | Yes | Token endpoint URL (must match the security integration) |
| `OAUTH_ALLOWED_SCOPES` | For `CLIENT_CREDENTIALS` | Scopes the app requests |
| `OAUTH_AUTHORIZATION_ENDPOINT` | Optional | Authorization endpoint URL |

## Critical Validation Rules

1. **Values must match**: The values in the app specification (`OAUTH_TOKEN_ENDPOINT`, `OAUTH_ALLOWED_SCOPES`, etc.) must be identical to those used when creating the security integration. Mismatches cause failures.
2. **Only API_AUTHENTICATION type**: Native Apps only support `TYPE = API_AUTHENTICATION` for security integrations.
3. **Not usable until approved**: The security integration is created at install, but OAuth calls fail until the consumer approves the app specification.
4. **EAI must allow the secret and security integration**: If a UDF or procedure uses both an EAI (`EXTERNAL_ACCESS_INTEGRATIONS`) and a secret backed by this security integration (`SECRETS`), the EAI must include the secret in `ALLOWED_AUTHENTICATION_SECRETS` and the security integration in `ALLOWED_API_AUTHENTICATION_INTEGRATIONS`. See `references/app-spec-eai.md` for configuration details.

## Workflow Steps

When the `request-account-privilege` skill detects `CREATE SECURITY INTEGRATION`:

1. **Check** if a security integration already exists in the setup script
   - If not, ask the user which OAuth provider they need and which grant type (`CLIENT_CREDENTIALS`, `AUTHORIZATION_CODE`, or `JWT_BEARER`)
   - Generate the `CREATE SECURITY INTEGRATION` statement
2. **Determine the OAuth type** from the existing or new security integration
3. **Check** if an app specification already exists
   - If not, generate the `ALTER APPLICATION SET SPECIFICATION` statement matching the security integration's OAuth properties
   - Add it to the setup script (after the security integration creation)
4. **Validate** that OAuth properties in the spec match those in the security integration
5. **Validate EAI compatibility** — if the security integration is used by a UDF or procedure that also references an EAI, verify that the EAI's `ALLOWED_AUTHENTICATION_SECRETS` includes the secret associated with this security integration, and that `ALLOWED_API_AUTHENTICATION_INTEGRATIONS` includes this security integration. See `references/app-spec-eai.md` for the EAI configuration details.
6. **Inform** the user that the consumer must approve this specification before OAuth works

## Output

- Security integration and app specification SQL added to the setup script
- Manifest updated with `CREATE SECURITY INTEGRATION` privilege
- User informed about consumer approval requirement
