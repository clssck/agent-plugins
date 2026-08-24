---
name: openflow-bootstrap-discovery
description: CLI/terminal-surface discovery of Openflow deployments and runtimes. Load on the CLI path when the cache is missing or incomplete. The Snowsight/SQL-only equivalent is inline in core-session-sql.md.
---

# Infrastructure Discovery (CLI / terminal surface)

Discover Openflow deployments and runtimes, then write results to the nipyapi cache. This is the **CLI-surface** discovery path — it runs SQL discovery and maintains the local cache/profiles (`snow sql -c <connection>` for a deployment on a non-primary connection).

**Surface note:** On the **Snowsight (SQL-only)** surface, do NOT use this reference. The SQL-only discovery (plain SQL, no `-c`, no cache) is inline in `references/core-session-sql.md` Step 3. The Gen2-relevant discovery queries are intentionally duplicated there in surface-native form.

## Prerequisites

The bootstrap flow has selected a target connection. Run the SQL below on the active connection; use `snow sql -c <connection>` when the deployment is on a non-primary connection. Add `--format json` when parsing results into the cache.

For diagnostic queries (Alternative Discovery section), you may also need the `event_table` from the cache. If the cache exists, check:

```bash
cat ~/.snowflake/cortex/memory/openflow_infrastructure_*.json | jq '.deployments[].event_table'
```

## Step 1: Find Deployments and Runtimes

Run both queries together before drawing any conclusions:

```sql
SHOW OPENFLOW DEPLOYMENTS;
SHOW OPENFLOW RUNTIMES IN ACCOUNT;
```

| Deployments | Runtimes | Action |
|-------------|----------|--------|
| Found | Found | **SOM enabled.** Extract info from both, continue to Step 2 |
| Found | Empty | **SOM enabled.** Unusual. Ask: "I found deployments but no runtimes. Is a runtime being provisioned or recently removed?" |
| Empty | Found | **SOM enabled.** Ask: "I found runtimes but no deployments. Do you believe OpenFlow is deployed in this account? The account may have a non-standard configuration." |
| Empty | Empty | **SOM enabled.** Ask: "I did not find any Openflow deployments or runtimes in this account. Do you need to deploy Openflow here for the first time?" If yes → ask "SPCS (Snowflake-managed compute) or BYOC (your own compute)?" → load `references/deploy-greenfield-spcs.md` or `references/deploy-greenfield-byoc.md`. If no → check role permissions (user may lack SHOW grants) or confirm the account has Openflow enabled. |
| Permissions error | any | User/Role lacks grants. Tell user to check Openflow permissions in Snowflake. |

**SOM detection:** Interpret the probe by result *type*, not merely success/failure:
- **Rows (even empty)** → SOM-enabled (`som_enabled: true`).
- **SQL compilation / syntax error** (e.g. `unexpected 'DEPLOYMENTS'`) → the OPENFLOW grammar is absent → legacy/not-SOM (`som_enabled: false`). This is grammar-level and role-independent.
- **Any other error** (permission, transient) → inconclusive; report it and confirm with the user before concluding. Do NOT read a privilege or transient error as "not SOM".

For a deployment- and privilege-independent presence check, `SHOW OPENFLOW CONNECTOR DEFINITIONS` returns Snowflake's built-in Gen2 definitions whenever SOM is enabled (even with zero deployments and under a minimal role).

**Legacy → SOM upgrade detection:** If the cache has `som_enabled: false` but `SHOW OPENFLOW DEPLOYMENTS` now succeeds, the account has been upgraded to SOM since the last discovery. Update `som_enabled: true` in the cache and proceed through Step 2b to validate whether the existing admin role has the required SOM grants before attempting any SOM operations.

**Not SOM-enabled:** If the probe returns a **SQL compilation/syntax error** (OPENFLOW grammar absent — as distinct from a permission or transient error), the account does not support the SQL Object Model. The greenfield SQL path (`deploy-greenfield-spcs.md`, `deploy-greenfield-byoc.md`) is not available. Direct the user to Ingestion > Openflow in Snowsight to deploy via UI, and set `som_enabled: false` in the cache.

**Never conclude "not deployed" without asking the user first.** Queries may return empty due to role permissions, deployment state, or non-standard configurations.

**Note for pre-SOM accounts:** If `SHOW OPENFLOW DEPLOYMENTS` returns an error, the account may use the legacy integration model. Use `SHOW OPENFLOW DATA PLANE INTEGRATIONS` and `SHOW OPENFLOW RUNTIME INTEGRATIONS` instead and follow the legacy discovery path. Set `som_enabled: false` in the cache.

### Deployment Details

For each deployment from `SHOW OPENFLOW DEPLOYMENTS`, note:
- `name` — deployment name
- `type` — `SNOWFLAKE` (SPCS) or `BYOC`
- `key` — deployment key (internal identifier)
- `custom_ingress_hostname` — BYOC custom ingress host (may be null)

## Step 2: Extract Runtime Details

For each runtime from `SHOW OPENFLOW RUNTIMES IN ACCOUNT`, describe it to get the URL and role:

```sql
DESCRIBE OPENFLOW RUNTIME <db>.<schema>.<name>;
```

Extract from `DESCRIBE` output:
- `server_url` — full NiFi server URL (e.g. `https://host:443/runtime-key/nifi/`)
- `execute_as_role` — the Snowflake role used for managed token auth
- `key` — runtime key used in API paths

Construct the NiFi API URL by replacing the trailing `nifi/` with `nifi-api`:
```
https://host:443/runtime-key/nifi-api
```

Note: runtimes are schema-qualified objects (`<database>.<schema>.<name>`). Use the `database_name` and `schema_name` from `SHOW OPENFLOW RUNTIMES IN ACCOUNT` to construct the full name.

### Detect Deployment Type from URL

| Pattern | Type |
|---------|------|
| Host starts with `of--` | SPCS |
| Host contains `snowflake-customer.app` | BYOC |

## Step 2b: Discover Openflow Admin Role (SOM accounts only)

Skip this step for pre-SOM accounts (`som_enabled: false`).

The Openflow admin role owns infrastructure objects (deployments, runtimes,
databases, EAIs) and holds the account-level grants needed to create them. It
must be identified and cached so subsequent operations can switch to it correctly.

**Important for legacy → SOM migrations:** Accounts that previously ran Openflow
in the legacy (non-SOM) model may have existing admin and execute-as roles, but those
roles will not have the SOM-required account-level grants. Do not assume an
existing role is SOM-ready without completing the grant validation below.

### Identify the Admin Role

```sql
SHOW ROLES LIKE '%OPENFLOW%';
```

Name patterns alone miss roles with non-standard names. Also search by grant —
a role holding account-level Openflow privileges is a strong admin-role signal:

```sql
-- Roles with the SOM admin grants (catches roles not named with OPENFLOW)
SHOW GRANTS ON ACCOUNT;
-- Look for CREATE OPENFLOW DEPLOYMENT, CREATE DATABASE, CREATE ROLE held by the same role
```

Present matching roles (name-matched AND grant-matched, deduplicated) to the user.
If `OPENFLOW_ADMIN_RL` appears, suggest it as the most likely candidate. Then ask:

> "Which of these is the Openflow admin role for this account?
> (Suggested: `OPENFLOW_ADMIN_RL` if present, or the role that owns the
> `OPENFLOW.OPENFLOW` schema)"

If no roles match and this is a new environment (no deployments found), note
that the admin role will be created during deployment setup
(`references/deploy-prereqs.md`) and the cache should be updated then.

If the user is unsure, check which role owns the infra schema:

```sql
SHOW SCHEMAS LIKE 'OPENFLOW' IN DATABASE OPENFLOW;
-- Check 'owner' column
```

### Validate SOM Grants on the Admin Role

Once the role is identified, check whether it holds the SOM-required
account-level grants:

```sql
SHOW GRANTS TO ROLE <openflow_admin_role>;
-- Look for the following in the 'privilege' and 'granted_on' columns:
--   CREATE OPENFLOW DEPLOYMENT  on ACCOUNT
--   CREATE COMPUTE POOL         on ACCOUNT   (SPCS only — skip for BYOC-only accounts)
--   CREATE DATABASE             on ACCOUNT
--   CREATE ROLE                 on ACCOUNT
--   CREATE EXTERNAL ACCESS INTEGRATION on ACCOUNT
```

**If all five grants are present:** Role is SOM-ready. Store in cache and continue.

**If any grants are missing:** This role existed before SOM was enabled on the
account and has not been updated. **Do not proceed** with SOM or Gen2 connector
operations until the missing grants are added — they will fail with permission
errors.

Generate the missing grants as SQL for the user to run (requires ACCOUNTADMIN):

```sql
-- Run as ACCOUNTADMIN. Add only the grants that are missing:
GRANT CREATE OPENFLOW DEPLOYMENT ON ACCOUNT TO ROLE <openflow_admin_role>;
GRANT CREATE COMPUTE POOL ON ACCOUNT TO ROLE <openflow_admin_role>;         -- SPCS only
GRANT CREATE DATABASE ON ACCOUNT TO ROLE <openflow_admin_role>;
GRANT CREATE ROLE ON ACCOUNT TO ROLE <openflow_admin_role>;
GRANT CREATE EXTERNAL ACCESS INTEGRATION ON ACCOUNT TO ROLE <openflow_admin_role>;
```

After the user confirms the grants have been applied, re-run the `SHOW GRANTS`
check to verify before proceeding.

Store the confirmed, validated role name in the cache as `openflow_admin_role`.

### Validate Runtime / Execute-As Roles Against SOM Infra Objects

In SOM, every runtime is a schema-qualified object (`<INFRA_DB>.<INFRA_SCHEMA>.<name>`)
and all connectors run inside that schema. The execute-as role for each runtime
must have `USAGE` on the infra database and schema for connector operations to
succeed.

Legacy execute-as roles were created before these infra objects existed and will
not have this access. This causes connector operations to fail silently or with
cryptic permission errors — even if the runtime itself starts correctly.

**For each runtime discovered in Step 2, check its `execute_as_role`:**

```sql
SHOW GRANTS TO ROLE <execute_as_role>;
-- Required entries (check 'privilege' and 'name' columns):
--   USAGE on DATABASE  <INFRA_DB>
--   USAGE on SCHEMA    <INFRA_DB>.<INFRA_SCHEMA>
```

If the infra database and schema are not yet known (no existing SOM objects),
discover them:

```sql
SHOW DATABASES LIKE '%OPENFLOW%';
-- Look for the database that contains Openflow runtime objects
-- Then check its schemas:
SHOW SCHEMAS IN DATABASE <candidate_db>;
```

**If both USAGE grants are present:** Role is ready for SOM operations.

**If either USAGE grant is missing:** Generate the missing grants for the user
to run (requires the role that owns the infra database — typically the Openflow
admin role or ACCOUNTADMIN):

```sql
-- Run as <openflow_admin_role> or ACCOUNTADMIN:
GRANT USAGE ON DATABASE <INFRA_DB> TO ROLE <execute_as_role>;
GRANT USAGE ON SCHEMA <INFRA_DB>.<INFRA_SCHEMA> TO ROLE <execute_as_role>;
```

Repeat for each unique `execute_as_role` found across all runtimes. Wait for
the user to confirm grants are applied before proceeding with any SOM or Gen2
connector operations on those runtimes.

## Step 3: Write Cache

Create cache directory if not exists:

```bash
mkdir -p ~/.snowflake/cortex/memory
```

Update the cache file with the `deployments` section (merge with existing cache):

```bash
jq '.discovered_at = "<ISO_TIMESTAMP>" | .som_enabled = <true|false> | .openflow_admin_role = "<role_name>" | .deployments = [<DEPLOYMENTS_ARRAY>]' \
  ~/.snowflake/cortex/memory/openflow_infrastructure_${CONNECTION}.json > tmp && mv tmp ~/.snowflake/cortex/memory/openflow_infrastructure_${CONNECTION}.json
```

**Deployments structure:**

```json
{
  "deployment_name": "<name>",
  "deployment_type": "<spcs|byoc>",
  "deployment_key": "<key>",
  "event_table": "<table>",
  "runtimes": [
    {
      "runtime_name": "<db>.<schema>.<name>",
      "runtime_key": "<key>",
      "execute_as_role": "<role>",
      "url": "https://<host>/<key>/nifi-api",
      "nipyapi_profile": "<profile-name>"
    }
  ]
}
```

Notes:
- Runtime name is schema-qualified: `<database>.<schema>.<name>`
- `execute_as_role` is the managed token role (from `DESCRIBE OPENFLOW RUNTIME`)
- `nipyapi_profile` is added by the auth step, not discovery
- `tooling` section is managed by bootstrap-tooling, not discovery
- See `references/core-session-cli.md` for full cache schema

### Legacy Cache Fields (pre-SOM accounts)

Existing caches written before SOM will use different field names. When reading a cache, both schemas are valid:

| Legacy field | SOM field | Notes |
|---|---|---|
| `data_plane_integration` | `deployment_name` | Deployment identifier |
| `data_plane_id` | `deployment_key` | Internal key |
| `runtime_integration` | `runtime_name` | Runtime identifier (SOM name is schema-qualified) |
| `runtime_role` | `execute_as_role` | Role for Snowflake auth |
| `admin_role` | `openflow_admin_role` | Openflow admin role name — re-introduced in SOM schema (was briefly removed) |

If you read a cache with legacy fields, treat them as valid and do not re-discover unless the user asks. If you need to refresh the cache on a SOM account, write the new schema — old fields will be replaced when you overwrite the `deployments` array.

## Alternative: Discovery from Event Table

If `SHOW OPENFLOW RUNTIMES IN ACCOUNT` returns unexpected results, query the event table directly:

```sql
SELECT DISTINCT
  RESOURCE_ATTRIBUTES:"k8s.namespace.name"::STRING as namespace,
  REGEXP_SUBSTR(RESOURCE_ATTRIBUTES:"k8s.namespace.name"::STRING, 'runtime-(.+)', 1, 1, 'e', 1) as runtime_name
FROM <event_table>
WHERE RESOURCE_ATTRIBUTES:"k8s.namespace.name"::STRING ILIKE 'runtime-%'
  AND TIMESTAMP >= DATEADD(day, -7, CURRENT_TIMESTAMP())
```

**Note:** This may reveal:
- Incompletely deployed runtimes that emitted events before failing
- Previously removed runtimes that still have event history
- Runtimes not yet registered as integrations

Compare results with the integration list to identify discrepancies for investigation. See `references/platform-diagnostics.md` for runtime troubleshooting.

## Next Step

After writing cache, **continue** to `references/bootstrap-cli.md` Step 3 to validate the cache and create nipyapi profiles.

Do not stop here - the setup is not complete until profiles are created and connectivity is verified.
