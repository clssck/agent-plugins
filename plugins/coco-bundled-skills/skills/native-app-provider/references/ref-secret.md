---
name: ref-secret
description: "Reference for requesting access to a consumer-owned Secret via the references mechanism."
parent_skill: native-app-provider
---

# Reference: Consumer Secret

Reference document for configuring a Snowflake Native App to request access to an existing Secret in the consumer account using the references mechanism.

## When This Applies

The **consumer** creates and owns the Secret. The app requests access to it via a reference.

Use this approach when the secret is created by or from the consumer's account. This is commonly paired with an EXTERNAL ACCESS INTEGRATION reference (see `references/ref-eai.md`) when the app needs both the secret credentials and the network access.

## Manifest Reference Definition

```yaml
references:
  - consumer_secret:
      label: "API Secret"
      description: "Secret containing credentials for <service_name>"
      privileges:
        - USAGE
        - READ
      object_type: SECRET
      register_callback: <schema>.register_single_reference
      configuration_callback: <schema>.get_configuration_for_reference
```

**Notes:**
- `object_type` must be `SECRET`
- Allowed privileges are `USAGE` and `READ`
- **`configuration_callback` is required** for this object type — without it, Snowflake raises `Missing field 'configuration_callback'`
- SECRET references **cannot** have `multi_valued: true`

### Optional Fields

| Field | Description |
|-------|-------------|
| `required_at_setup` | Set to `true` to require this reference to be bound during app installation. Example: `required_at_setup: true` |

## Configuration Callback (Required)

References of type `SECRET` **require** a configuration callback procedure named `GET_CONFIGURATION_FOR_REFERENCE`. This is used when consumers bind the reference via Snowsight.

### OAUTH2 Secret

```sql
CREATE OR REPLACE PROCEDURE <schema>.get_configuration_for_reference(ref_name STRING)
  RETURNS STRING
  LANGUAGE SQL
AS $$
BEGIN
  CASE (ref_name)
    WHEN 'CONSUMER_SECRET' THEN
      RETURN '{
        "type": "CONFIGURATION",
        "payload": {
          "type": "OAUTH2",
          "security_integration": {
            "oauth_scopes": ["https://api.example.com/.default"],
            "oauth_token_endpoint": "https://provider.example.com/oauth2/token",
            "oauth_authorization_endpoint": "https://provider.example.com/oauth2/authorize"
          }
        }
      }';
  END CASE;
  RETURN '';
END;
$$;

GRANT USAGE ON PROCEDURE <schema>.get_configuration_for_reference(STRING)
  TO APPLICATION ROLE <app_role>;
```

### Configuration Payload Fields

The `payload.type` field determines the secret type. Valid values are:

| Type | Description |
|------|-------------|
| `OAUTH2` | OAuth2 grant flow — requires `security_integration` fields below |
| `GENERIC_STRING` | Generic string secret (e.g., API key) — no additional fields needed |
| `PASSWORD` | Username/password secret — no additional fields needed |

**Additional fields when `type` is `OAUTH2`:**

| Field | Required | Description |
|-------|----------|-------------|
| `security_integration.oauth_scopes` | Yes | List of OAuth scopes the secret needs |
| `security_integration.oauth_token_endpoint` | Yes | Token endpoint URL for the OAuth provider |
| `security_integration.oauth_authorization_endpoint` | Yes | Authorization endpoint URL. **Required in the JSON even for `CLIENT_CREDENTIALS` flows** — set to an empty string `""` if not used |

### GENERIC_STRING Secret

```sql
WHEN 'CONSUMER_SECRET' THEN
  RETURN '{
    "type": "CONFIGURATION",
    "payload": {
      "type": "GENERIC_STRING"
    }
  }';
```

### PASSWORD Secret

```sql
WHEN 'CONSUMER_SECRET' THEN
  RETURN '{
    "type": "CONFIGURATION",
    "payload": {
      "type": "PASSWORD"
    }
  }';
```

### Error Response

The configuration callback can also return an error if the reference is not ready:

```json
{
  "type": "ERROR",
  "payload": {
    "message": "The reference is not available for configuration."
  }
}
```

### Combining with EAI Reference

When used with an EAI reference, the secret reference name must appear in the EAI configuration callback's `secret_references` list. Both references and both configuration callback `WHEN` cases are typically in the same procedure:

```sql
CREATE OR REPLACE PROCEDURE <schema>.get_configuration_for_reference(ref_name STRING)
  RETURNS STRING
  LANGUAGE SQL
AS $$
BEGIN
  CASE (ref_name)
    WHEN 'CONSUMER_EXTERNAL_ACCESS' THEN
      RETURN '{
        "type": "CONFIGURATION",
        "payload": {
          "host_ports": ["api.example.com"],
          "allowed_secrets": "LIST",
          "secret_references": ["CONSUMER_SECRET"]
        }
      }';
    WHEN 'CONSUMER_SECRET' THEN
      RETURN '{
        "type": "CONFIGURATION",
        "payload": {
          "type": "OAUTH2",
          "security_integration": {
            "oauth_scopes": ["https://api.example.com/.default"],
            "oauth_token_endpoint": "https://provider.example.com/oauth2/token",
            "oauth_authorization_endpoint": "https://provider.example.com/oauth2/authorize"
          }
        }
      }';
  END CASE;
  RETURN '';
END;
$$;
```

## Register Callback

Uses the standard single-value register callback (see `references/ref-object.md` for the full template):

```sql
CREATE OR REPLACE PROCEDURE <schema>.register_single_reference(
  ref_name STRING, operation STRING, ref_or_alias STRING
)
  RETURNS STRING
  LANGUAGE SQL
AS $$
BEGIN
  CASE (operation)
    WHEN 'ADD' THEN
      SELECT SYSTEM$SET_REFERENCE(:ref_name, :ref_or_alias);
    WHEN 'REMOVE' THEN
      SELECT SYSTEM$REMOVE_REFERENCE(:ref_name, :ref_or_alias);
    WHEN 'CLEAR' THEN
      SELECT SYSTEM$REMOVE_ALL_REFERENCES(:ref_name);
    ELSE
      RETURN 'unknown operation: ' || operation;
  END CASE;
  RETURN NULL;
END;
$$;

GRANT USAGE ON PROCEDURE <schema>.register_single_reference(STRING, STRING, STRING)
  TO APPLICATION ROLE <app_role>;
```

> **Consumer binding syntax:** See `request-object-access/SKILL.md` § Step 6 for the `SYSTEM$REFERENCE` call pattern the consumer uses to invoke this callback.

## Using Secret References in App Code

> **Deferred Creation:** Functions or procedures that use `reference('...')` in `EXTERNAL_ACCESS_INTEGRATIONS` or `SECRETS` cannot be created at the top level of the setup script. At install time the reference is not yet bound, so Snowflake raises `Reference definition '...' is missing a reference association`. Wrap their creation in a helper procedure that is called from the register callback after the reference is bound via `SYSTEM$SET_REFERENCE`.

### Deferred Creation Helper

Create a helper procedure in the setup script. The register callback calls it on `'ADD'`.

> **CRITICAL — Guard check:** When both an EAI and a SECRET reference are required, the register callback fires for each reference independently. The first `'ADD'` fires before the second reference is bound. The deferred creation helper **MUST** check that **all** required references are bound before creating the function — otherwise it will fail with `Reference definition '...' is missing a reference association`. Use `SYSTEM$GET_ALL_REFERENCES('<ref_name>')` for each reference — it returns `'[]'` (empty list) when the reference is **unbound**. Strip spaces with `REPLACE` before comparing since the format may include whitespace (e.g. `'[ ]'`). **Do NOT skip this guard — the register callback is shared and fires for both references.**

> **Nested dollar-quoting:** The outer helper procedure uses `$$` as its body delimiter. The inner function/procedure body **cannot** also use `$$` — that would prematurely terminate the outer procedure and cause a syntax error at install time. Use a **single-quoted string** (`AS '...'`) for the inner body instead. If the code contains single quotes, escape them as `''`.

```sql
CREATE OR REPLACE PROCEDURE <schema>.create_api_function()
  RETURNS STRING
  LANGUAGE SQL
AS $$
BEGIN
  -- Guard: only proceed if BOTH references are bound
  -- SYSTEM$GET_ALL_REFERENCES returns '[]' (empty list) when the reference is unbound
  LET eai_refs VARCHAR := (SELECT SYSTEM$GET_ALL_REFERENCES('consumer_external_access'));
  LET secret_refs VARCHAR := (SELECT SYSTEM$GET_ALL_REFERENCES('consumer_secret'));
  IF (REPLACE(:eai_refs, ' ', '') = '[]' OR REPLACE(:secret_refs, ' ', '') = '[]') THEN
    RETURN 'Waiting for all references to be bound';
  END IF;

  CREATE OR REPLACE FUNCTION <schema>.internal_api_call(arg1 STRING)
    RETURNS STRING
    LANGUAGE PYTHON
    RUNTIME_VERSION = 3.11
    HANDLER = 'my_handler'
    EXTERNAL_ACCESS_INTEGRATIONS = (reference('consumer_external_access'))
    PACKAGES = ('snowflake-snowpark-python', 'requests')
    SECRETS = ('cred' = reference('consumer_secret'))
  AS 'import requests
def my_handler(arg1):
    resp = requests.get(arg1, timeout=10)
    return str(resp.status_code)';
  RETURN 'Function created';
END;
$$;
```

### Wrapper Pattern (Required for Consumer Access)

Consumers **cannot** directly call functions or stored procedures that use EAI or secret references. To expose this functionality to consumers, create a wrapper stored procedure at the top level of the setup script (safe — it does not use `reference()` directly):

```sql
CREATE OR REPLACE PROCEDURE <schema>.call_api(arg1 STRING)
  RETURNS STRING
  LANGUAGE SQL
AS $$
BEGIN
  RETURN (SELECT <schema>.internal_api_call(:arg1));
END;
$$;

GRANT USAGE ON PROCEDURE <schema>.call_api(STRING)
  TO APPLICATION ROLE <app_role>;
```

> **Note:** The wrapper must be a stored procedure, not a function. Other app components (Streamlit apps, tasks, other stored procedures) can also call functions that use EAI/secret references directly.

## Validation Rules

1. **Configuration callback is required** — without `GET_CONFIGURATION_FOR_REFERENCE`, Snowsight cannot build the reference binding UI for this type
2. **OAuth properties must be accurate** — scopes and endpoints must match the intended OAuth provider
3. **When paired with EAI** — the secret reference name must appear in the EAI's `secret_references` list
4. **Callback proc must be granted** to an application role

## Workflow

This is a reference document. Load it from `request-object-access/SKILL.md` when the user needs to reference a consumer-owned secret.
