---
name: ref-eai
description: "Reference for requesting access to a consumer-owned External Access Integration via the references mechanism."
parent_skill: native-app-provider
---

# Reference: Consumer External Access Integration

Reference document for configuring a Snowflake Native App to request access to an existing External Access Integration (EAI) in the consumer account using the references mechanism.

## When This Applies

The **consumer** creates and owns the External Access Integration. The app requests access to it via a reference.

Use this approach when the EAI is created by or from the consumer's account. If the **app itself** creates the EAI, use the app specification approach instead (`references/app-spec-eai.md`).

## Manifest Reference Definition

```yaml
references:
  - consumer_external_access:
      label: "External Access Integration"
      description: "An external access integration for connecting to <service_name>"
      privileges:
        - USAGE
      object_type: EXTERNAL ACCESS INTEGRATION
      register_callback: <schema>.register_single_reference
      configuration_callback: <schema>.get_configuration_for_reference
```

**Notes:**
- `object_type` must be `EXTERNAL ACCESS INTEGRATION`
- The only allowed privilege is `USAGE`
- **`configuration_callback` is required** for this object type — without it, Snowflake raises `Missing field 'configuration_callback'`
- EAI references **cannot** have `multi_valued: true`

### Optional Fields

| Field | Description |
|-------|-------------|
| `required_at_setup` | Set to `true` to require this reference to be bound during app installation. Example: `required_at_setup: true` |

## Configuration Callback (Required)

References of type `EXTERNAL ACCESS INTEGRATION` **require** a configuration callback procedure named `GET_CONFIGURATION_FOR_REFERENCE`. This is used when consumers bind the reference via Snowsight.

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
  END CASE;
  RETURN '';
END;
$$;

GRANT USAGE ON PROCEDURE <schema>.get_configuration_for_reference(STRING)
  TO APPLICATION ROLE <app_role>;
```

### Configuration Payload Fields

| Field | Required | Description |
|-------|----------|-------------|
| `host_ports` | Yes | List of host:port endpoints the EAI should allow |
| `allowed_secrets` | Yes | Set to `"LIST"` to allow secrets from `secret_references` |
| `secret_references` | Yes | List of reference names for secrets used with this EAI (must match secret reference names in the manifest) |

> **Tip:** If `allowed_secrets` is `"LIST"`, Snowsight implicitly handles the paired secret configuration — consumers do not need a separate `request_reference` call for the secret.

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

### Pairing with a Secret Reference

An EAI reference typically needs a paired SECRET reference. When the EAI configuration includes `secret_references`, each entry must correspond to a reference defined in the manifest:

```yaml
references:
  - consumer_external_access:
      label: "External Access Integration"
      description: "EAI for connecting to example.com"
      privileges:
        - USAGE
      object_type: EXTERNAL ACCESS INTEGRATION
      register_callback: <schema>.register_single_reference
      configuration_callback: <schema>.get_configuration_for_reference
  - consumer_secret:
      label: "API Secret"
      description: "Secret containing credentials for example.com"
      privileges:
        - USAGE
        - READ
      object_type: SECRET
      register_callback: <schema>.register_single_reference
      configuration_callback: <schema>.get_configuration_for_reference
```

See `references/ref-secret.md` for the SECRET configuration callback details.

## Register Callback

Uses the standard single-value register callback. On `'ADD'`, it sets the reference and then calls the deferred creation helper. Since this callback is shared by both the EAI and SECRET references, the deferred creation helper must guard against missing references (see [Guard check](#deferred-creation-helper)):

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
      -- Safe to call on every 'ADD' because the helper has a guard check
      CALL <schema>.create_eai_function();
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

## Using EAI References in App Code

> **Deferred Creation:** Functions or procedures that use `reference('...')` in `EXTERNAL_ACCESS_INTEGRATIONS` or `SECRETS` cannot be created at the top level of the setup script. At install time the reference is not yet bound, so Snowflake raises `Reference definition '...' is missing a reference association`. Wrap their creation in a helper procedure that is called from the register callback after the reference is bound via `SYSTEM$SET_REFERENCE`.

### Deferred Creation Helper

Create a helper procedure in the setup script. The register callback calls it on `'ADD'`.

> **CRITICAL — Guard check:** When both an EAI and a SECRET reference are required, the register callback fires for each reference independently. The first `'ADD'` fires before the second reference is bound. The deferred creation helper **MUST** check that **all** required references are bound before creating the function — otherwise it will fail with `Reference definition '...' is missing a reference association`. Use `SYSTEM$GET_ALL_REFERENCES('<ref_name>')` for each reference — it returns `'[]'` (empty list) when the reference is **unbound**. Strip spaces with `REPLACE` before comparing since the format may include whitespace (e.g. `'[ ]'`). **Do NOT skip this guard — the register callback is shared and fires for both references.**

> **Nested dollar-quoting — TWO quoting levels:** The outer helper procedure uses `$$` as its body delimiter. Inside `$$`, single quotes are literal — use them normally for `reference('...')`, `PACKAGES = ('...')`, string literals, etc. The inner function/procedure body **cannot** also use `$$` — that would prematurely terminate the outer procedure. Use a **single-quoted string** (`AS '...'`) for the inner body instead. Inside `AS '...'`, every single quote must be **doubled** (`''`). **Do NOT double quotes outside `AS '...'`** — only inside the inner body string.
>
> Summary of quoting rules inside the `$$` block:
> - `reference('consumer_external_access')` — single quotes (at `$$` level, NOT inside `AS '...'`)
> - `PACKAGES = ('snowflake-snowpark-python')` — single quotes (at `$$` level)
> - `SECRETS = ('cred' = reference('consumer_secret'))` — single quotes (at `$$` level)
> - `AS '...code...'` — the inner body string delimiter
> - `_snowflake.get_oauth_access_token(''cred'')` — doubled quotes (INSIDE `AS '...'`)

```sql
CREATE OR REPLACE PROCEDURE <schema>.create_eai_function()
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

  -- Create the internal function using reference() for EAI and secret bindings
  CREATE OR REPLACE FUNCTION <schema>.internal_api_call()
    RETURNS STRING
    LANGUAGE PYTHON
    RUNTIME_VERSION = 3.11
    HANDLER = 'run'
    EXTERNAL_ACCESS_INTEGRATIONS = (reference('consumer_external_access'))
    PACKAGES = ('snowflake-snowpark-python')
    SECRETS = ('cred' = reference('consumer_secret'))
  AS 'import _snowflake
def run():
    token = _snowflake.get_oauth_access_token(''cred'')
    if token and len(token) > 0:
        return ''true''
    return ''false''
';
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
2. **`host_ports` must be accurate** — they define what endpoints the consumer's EAI will allow
3. **`secret_references` must match manifest** — each entry must correspond to a SECRET reference name defined in the manifest
4. **Callback proc must be granted** to an application role

## Workflow

This is a reference document. Load it from `request-object-access/SKILL.md` when the user needs to reference a consumer-owned EAI.
