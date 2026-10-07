---
name: app-spec-eai
description: "Reference for configuring External Access Integration (EAI) app specifications in a Snowflake Native App."
parent_skill: native-app-provider
---

# App Specification: External Access Integration (EAI)

Loaded by `request-external-access-integration` (Step A3) for app-created EAI configuration.

## When This Applies

The **app itself** creates the External Access Integration. This requires:

1. The `CREATE EXTERNAL ACCESS INTEGRATION` privilege in the manifest
2. A **network rule** defining allowed endpoints
3. An **external access integration** (EAI) referencing the network rule
4. An **app specification** of type `EXTERNAL_ACCESS` declaring the host ports

The privilege is auto-granted at install, but the EAI is not usable until the consumer approves the app specification.

Use this approach when the app creates and owns the EAI. If the **consumer** creates and owns the EAI, use Approach B in `request-external-access-integration/SKILL.md` instead.

## Required Objects

### 1. Manifest privilege

```yaml
manifest_version: 2

privileges:
  - CREATE EXTERNAL ACCESS INTEGRATION:
      description: "Allows the app to connect to <service_name> for <purpose>"
```

### 2. Network rule (in setup script)

```sql
CREATE NETWORK RULE IF NOT EXISTS <schema>.my_network_rule
  TYPE = HOST_PORT
  VALUE_LIST = ('api.example.com', 'api.example.com:443')
  MODE = EGRESS;
```

- `TYPE` must be `HOST_PORT`
- `VALUE_LIST` lists the domains/ports the app needs to reach
- `MODE` is `EGRESS` (outbound)

### 3. External access integration (in setup script)

```sql
CREATE EXTERNAL ACCESS INTEGRATION IF NOT EXISTS my_eai
  ALLOWED_NETWORK_RULES = (<schema>.my_network_rule)
  ENABLED = TRUE;
```

**Note**: If the UDF or stored procedure associated with this EAI also uses a **secret** (e.g., for OAuth credentials) or a **security integration**, configure the EAI to allow them:

- `ALLOWED_AUTHENTICATION_SECRETS` — use `ALL` to permit any secret (recommended). This avoids listing specific secrets and works for both app-owned and consumer-owned patterns.
- `ALLOWED_API_AUTHENTICATION_INTEGRATIONS` — list the specific security integrations the EAI should permit (e.g., `(my_security_integration)`). This is required when the secret is backed by an `API_AUTHENTICATION` security integration.

Example with secrets and security integration:

```sql
CREATE EXTERNAL ACCESS INTEGRATION IF NOT EXISTS my_eai
  ALLOWED_NETWORK_RULES = (<schema>.my_network_rule)
  ALLOWED_AUTHENTICATION_SECRETS = ALL
  ALLOWED_API_AUTHENTICATION_INTEGRATIONS = (my_security_integration)
  ENABLED = TRUE;
```

See `references/app-spec-security-integration.md` for details on configuring the security integration itself.

### 4. UDF or procedure using the EAI (in setup script)

```sql
CREATE OR REPLACE FUNCTION <schema>.call_external_api(url STRING)
  RETURNS STRING
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  HANDLER = 'call_api'
  EXTERNAL_ACCESS_INTEGRATIONS = (my_eai)
  PACKAGES = ('requests')
AS $$
import requests
def call_api(url):
    return requests.get(url).text
$$;

GRANT USAGE ON FUNCTION <schema>.call_external_api(STRING)
  TO APPLICATION ROLE app_public;
```

The key is `EXTERNAL_ACCESS_INTEGRATIONS = (my_eai)` which binds the function to the EAI.

### 5. App specification

```sql
ALTER APPLICATION SET SPECIFICATION eai_spec
  TYPE = EXTERNAL_ACCESS
  LABEL = 'Connection to <service_name>'
  DESCRIPTION = 'Access <service_name> for <purpose>'
  HOST_PORTS = ('api.example.com', 'api.example.com:443');
```

Properties:

| Property | Required | Description |
|----------|----------|-------------|
| `TYPE` | Yes | Must be `EXTERNAL_ACCESS` |
| `LABEL` | Yes | Short display name shown to consumer |
| `DESCRIPTION` | Yes | Explains why the app needs this access |
| `HOST_PORTS` | Yes* | List of host:port values from the network rule |
| `PRIVATE_HOST_PORTS` | Yes* | List of private host ports for private connectivity |

*At least one of `HOST_PORTS` or `PRIVATE_HOST_PORTS` is required.

## Important Notes

1. **HOST_PORTS must match VALUE_LIST**: The host ports in the app specification must match the values in the network rule's `VALUE_LIST`. Mismatches cause approval failures.
2. **Group related endpoints into separate specs**: While a single app specification can cover all EAIs, it is best practice to group related endpoints into separate network rules and app specifications (e.g., one for analytics APIs, one for auth endpoints). When any endpoint in a spec changes, the consumer must re-approve the entire spec — so a monolithic spec with 10 endpoints forces re-approval of all 10 even if only one changed. Logical grouping minimizes consumer friction during upgrades.
3. **EAI is not usable until approved**: The EAI object is created at install, but external calls will fail until the consumer approves the app specification.
