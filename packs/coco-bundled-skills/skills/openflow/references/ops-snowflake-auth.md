---
name: openflow-ops-snowflake-auth
description: Configure Snowflake authentication for flows writing to Snowflake. Use for KEY_PAIR setup, session token configuration, and auth troubleshooting.
---

# Snowflake Authentication

Configure Snowflake authentication for flows that write to Snowflake. Applies to connectors and custom flows.

**Note:** These operations modify service state. Apply the Check-Act-Check pattern from `references/core-guidelines.md`.

## Scope

- Snowflake destination authentication (connectors and custom flows)
- SPCS vs BYOC configuration differences
- Key-pair setup and troubleshooting

## Overview

The SnowflakeConnectionService is the core component for Snowflake connectivity. Properties are set via Parameter Context, which is required for assets like private keys.

Authentication strategy is determined by deployment type (from cache):

| Deployment | Default Strategy | Alternative Strategy |
|------------|------------------|----------------------|
| `spcs` | `SNOWFLAKE_MANAGED` | — |
| `byoc` | `SNOWFLAKE_MANAGED` | `KEY_PAIR` |

`SNOWFLAKE_MANAGED` is the current standard for runtime-role (managed token) auth on **both** SPCS and BYOC; `KEY_PAIR` is the BYOC alternative.

> **Legacy values (may be encountered):** Older deployments may show `SNOWFLAKE_SESSION_TOKEN` — this was the former SPCS value and is still a valid value in the connector enum, but `SNOWFLAKE_MANAGED` is now the standard for new configurations. The spelling `SNOWFLAKE_MANAGED_TOKEN` also appeared in older guidance but is **not** a valid value in the connector's `Authentication Strategy` enum — use `SNOWFLAKE_MANAGED`.

For deployment type background, see `references/core-guidelines.md`.

---

## Property Reference

### Always Required

| Property | Notes |
|----------|-------|
| Destination Database | Target database for operations |
| Snowflake Authentication Strategy | `SNOWFLAKE_MANAGED` (SPCS and BYOC runtime-role default) or `KEY_PAIR` (BYOC alternative). Legacy `SNOWFLAKE_SESSION_TOKEN` may be encountered on older SPCS deployments. |
| Snowflake Role | Role for operations |

### Required for BYOC Key-Pair Only

| Property | Notes |
|----------|-------|
| Snowflake Account Identifier | Format: `org-name.account-name` |
| Snowflake Username | Service user name |
| Private Key | Via asset upload |

### Commonly Set

| Property | Notes |
|----------|-------|
| Schema | Check connector/flow requirements - may have defaults |
| Snowflake Warehouse | Check connector/flow requirements - may have defaults |

The calling workflow (connector or custom flow) specifies which properties are needed. Check connector documentation or existing parameter context for pre-set values.

---

## SPCS Configuration

Snowflake manages authentication automatically via the runtime's execute-as role. Set `Snowflake Authentication Strategy` to `SNOWFLAKE_MANAGED` (the current standard; the runtime resolves the session token internally). Older SPCS deployments may show the legacy value `SNOWFLAKE_SESSION_TOKEN` — still valid, but prefer `SNOWFLAKE_MANAGED` for new configurations.

Set the required properties. Leave these empty (automatic from session):
- Snowflake Account Identifier
- Snowflake Username
- Private Key

### Execute-As Role

The `Snowflake Role` must match the runtime's `execute_as_role`. Read it from the cache:

```bash
cat ~/.snowflake/cortex/memory/openflow_infrastructure_*.json | jq -r '.deployments[].runtimes[] | select(.nipyapi_profile == "<profile>") | .execute_as_role'
```

### PrivateKeyService Bulletins

On SPCS, you may see bulletins about `PrivateKeyService` errors. Ignore these - this service is only used on BYOC.

---

## BYOC Configuration — Managed Token (Default)

New deployments use `SNOWFLAKE_MANAGED`. The runtime authenticates to Snowflake automatically using the role configured as `EXECUTE_AS_ROLE` on the runtime object — no service user or key pair required.

### Step 1: Verify Execute-As Role

Read `execute_as_role` from the cache for the current runtime:

```bash
cat ~/.snowflake/cortex/memory/openflow_infrastructure_*.json | jq -r '.deployments[].runtimes[] | select(.nipyapi_profile == "<profile>") | .execute_as_role'
```

If the cache is absent or stale, discover from Snowflake:

```sql
DESCRIBE OPENFLOW RUNTIME <db>.<schema>.<name>;  -- read execute_as_role
```

### Step 2: Verify Role Grants

```sql
SHOW GRANTS TO ROLE <execute_as_role>;
```

Ensure the role has:
- `USAGE, OPERATE` on the target warehouse
- `USAGE` on the target database and schema
- Additional connector-specific grants (see connector documentation)

### Step 3: Configure Parameters

Set only the required parameters — leave all key-pair fields empty:

| Parameter | Value |
|-----------|-------|
| `Snowflake Authentication Strategy` | `SNOWFLAKE_MANAGED` |
| `Snowflake Warehouse` | `<warehouse>` |
| `Destination Database` | `<database>` |
| `Snowflake Role` | `<execute_as_role>` (recommended) |
| `Snowflake Account Identifier` | (leave empty) |
| `Snowflake Username` | (leave empty) |
| `Snowflake Private Key` | (leave empty) |

```bash
nipyapi --profile <profile> ci configure_inherited_params \
  --process_group_id "<pg-id>" \
  --parameters '{"Snowflake Authentication Strategy": "SNOWFLAKE_MANAGED", "Snowflake Warehouse": "<wh>", "Destination Database": "<db>", "Snowflake Role": "<role>"}'
```

### Step 4: Start and Verify

```bash
nipyapi --profile <profile> ci start_flow --process_group_id "<pg-id>"
nipyapi --profile <profile> bulletins get_bulletin_board --pg_id "<pg-id>"
```

**Expected:** Snowflake Connection Pool enables, no Snowflake auth errors in bulletins.

**Expected (ignorable):** `verify_config` may report `Snowflake Private Key Service` as invalid — this service is not used with managed token. Ignore it.

---

## BYOC Configuration — Migrating from KEY_PAIR to Managed Token

For existing flows using key-pair auth:

1. Stop the flow
2. Verify runtime has `EXECUTE_AS_ROLE` set (Step 1 above)
3. Update parameters:
   ```bash
   nipyapi --profile <profile> ci configure_inherited_params \
     --process_group_id "<pg-id>" \
     --parameters '{"Snowflake Authentication Strategy": "SNOWFLAKE_MANAGED", "Snowflake Account Identifier": "", "Snowflake Username": "", "Snowflake Private Key": "", "Snowflake Private Key Password": "", "Snowflake Role": "<execute_as_role>"}'
   ```
4. Start flow and verify bulletins — only source-side errors should remain
5. Once confirmed working, the key-pair assets (private key file) can be removed from the parameter context

---

## BYOC Configuration — Key-Pair Authentication (Alternative)

BYOC requires explicit authentication. Key-pair is a valid alternative to managed token.

### Step 1: Confirm Service User

Ask the user: "Do you have a Snowflake service user for Openflow? If so, what is the username?"

If user has a service user, record the username and proceed to Step 2.

If user needs a service user, see [Service User Setup](#service-user-setup) below, then return here.

### Step 2: Confirm Key Pair

Ask the user: "Do you have an RSA key pair assigned to this user, or should I help set one up?"

**If user has an existing key pair:**
- Ask for the private key file path
- Proceed to Step 3

**If user needs a new key pair:**

Generate one in `~/.ssh/`:

```bash
# Generate encrypted private key
openssl genrsa 2048 | openssl pkcs8 -topk8 -v2 aes256 -inform PEM -out ~/.ssh/snowflake_rsa_key.p8

# Set restrictive permissions
chmod 600 ~/.ssh/snowflake_rsa_key.p8

# Extract public key
openssl rsa -in ~/.ssh/snowflake_rsa_key.p8 -pubout -out ~/.ssh/snowflake_rsa_key.pub
```

Assign the public key to the Snowflake user:

```sql
ALTER USER <username> SET RSA_PUBLIC_KEY = '<public_key_content>';
```

### Step 3: Upload Private Key

Use `references/ops-parameters-assets.md` to upload the private key to the parameter context.

### Step 4: Set Passphrase

If the private key is encrypted, use `references/ops-parameters-main.md` to set the `Private Key Passphrase` parameter.

### Step 5: Verify Grants

Ask the user: "Can you confirm the service user's role has the necessary grants for the target database and warehouse?"

If user is unsure, verify grants:

```sql
SHOW GRANTS TO ROLE <role>;
```

Check for:
- `USAGE` on the target database
- `USAGE`, `OPERATE` on the target warehouse
- Additional grants as specified by the connector/flow documentation

If grants are missing, see [Grant Setup](#grant-setup) below.

### Step 6: Configure Parameters

Use `references/ops-parameters-main.md` to set the required and commonly-set parameters for the deployment.

---

## Setup Procedures

### Service User Setup

Create a service user and role:

```sql
CREATE IF NOT EXISTS USER <username> TYPE = SERVICE;
CREATE IF NOT EXISTS ROLE <role_name>;
GRANT ROLE <role_name> TO USER <username>;
```

After creation, return to Step 2 to set up key pair authentication.

### Grant Setup

Grant minimum required permissions:

```sql
GRANT USAGE ON DATABASE <db> TO ROLE <role>;
GRANT USAGE, OPERATE ON WAREHOUSE <wh> TO ROLE <role>;
```

Additional grants depend on the connector/flow. Common additions:

```sql
-- For schema operations
GRANT USAGE ON SCHEMA <db>.<schema> TO ROLE <role>;
GRANT CREATE TABLE ON SCHEMA <db>.<schema> TO ROLE <role>;

-- For creating schemas
GRANT CREATE SCHEMA ON DATABASE <db> TO ROLE <role>;

-- For internal stage writes
GRANT READ, WRITE ON STAGE <db>.<schema>.<stage> TO ROLE <role>;
```

**SPCS Execute-As Role Naming:** On SPCS, the execute-as role is conventionally named `RUNTIMEROLE_<service_name>` (and `OPENFLOWRUNTIMEROLE_<runtime>` for SOM runtimes). Recognise these existing names when discovering or referencing the role. Don't confuse this with OAuth service names (`SF$OAUTH$...`) which appear in integration metadata. Use the actual execute-as role name for GRANT statements.

After granting, return to the verification step.

---

## Troubleshooting

### Deployment Mode Mismatch

**Symptom:** Auth errors on SPCS with BYOC-style parameters set.

**Check:** On SPCS, these should be empty:
- Snowflake Account Identifier
- Snowflake Username
- Private Key

**Fix:** Clear the conflicting parameters.

### Partial Flow Failure

**Symptom:** Some Snowflake processors work, others fail.

**Cause:** Different processors use different APIs (JDBC, Streaming, Iceberg REST). A misconfigured auth strategy may allow one pathway while another fails.

**Fix:** Verify auth strategy matches deployment type. Check all required parameters are set or unset as required for the failing pathway.

### Invalid Credentials

**On SPCS:**
- Verify `Snowflake Authentication Strategy` = `SNOWFLAKE_MANAGED` (older deployments may show the legacy `SNOWFLAKE_SESSION_TOKEN`)
- Check role has required permissions
- Verify no BYOC parameters are set (Account Identifier, Username, Private Key)

**On BYOC (managed token):**
- Verify runtime `execute_as_role` is set: `SHOW OPENFLOW RUNTIMES IN ACCOUNT;`
- Verify the role has required grants: `SHOW GRANTS TO ROLE <execute_as_role>;`
- Verify `Snowflake Authentication Strategy = SNOWFLAKE_MANAGED` in parameter context
- `Snowflake Private Key Service` invalid in verify_config is expected — ignore

**On BYOC (key-pair):**
- Verify public key assigned: `DESC USER <username>`
- Check private key format (PEM, PKCS#8)
- Verify passphrase if key is encrypted

### Insufficient Privileges

```sql
SHOW GRANTS TO ROLE <role>;
SHOW GRANTS TO USER <user>;
```

Compare against required grants for the connector/flow.

---

## Next Step

After configuring authentication, return to the calling workflow to continue.

## See Also

- `references/core-guidelines.md` - Deployment types
- `references/ops-parameters-main.md` - Parameter configuration
- `references/ops-parameters-assets.md` - Asset upload
