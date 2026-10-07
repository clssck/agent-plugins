---
name: openflow-deploy-greenfield-spcs
description: Deploy an Openflow SPCS deployment from scratch via SQL. Use when
  SHOW OPENFLOW DEPLOYMENTS returns empty, the account is SOM-enabled, and the
  user wants a SNOWFLAKE (SPCS) managed deployment. Covers admin role creation,
  infrastructure database/schema, deployment, and runtime provisioning.
---

# Greenfield Openflow Deployment — SPCS

End-to-end SQL setup for a new Openflow environment on Snowflake-managed compute.

**Reached from:** `references/deploy-prereqs.md` — ToS acceptance and privilege
verification should already be complete before loading this reference.

**Requires SOM:** This workflow uses SQL commands (`CREATE OPENFLOW DEPLOYMENT`,
`CREATE OPENFLOW RUNTIME`) that are only available on SOM-enabled accounts. If
`SHOW OPENFLOW DEPLOYMENTS` returns a SQL error rather than an empty result set,
the account is not SOM-enabled and this reference does not apply — the user must
deploy via the Openflow UI in Snowsight.

**Scope:** SNOWFLAKE (SPCS) deployment type only. For BYOC,
see `references/deploy-greenfield-byoc.md`.

---

## Step 1: Admin Role

Check for an existing admin role before creating one:

```sql
SHOW ROLES LIKE '%OPENFLOW%ADMIN%';
-- Also check: SHOW ROLES LIKE '%OPENFLOW%'
```

If a suitable admin role already exists, use it and proceed to Step 2.

If not, create one (requires ACCOUNTADMIN or a role with these account-level grants):

```sql
USE ROLE ACCOUNTADMIN;
CREATE ROLE IF NOT EXISTS OPENFLOW_ADMIN_RL
  COMMENT = 'Openflow admin role — owns deployments, runtimes, and infrastructure. [openflow]';

-- Account-level grants needed for SPCS deployment management:
GRANT CREATE DATABASE ON ACCOUNT TO ROLE OPENFLOW_ADMIN_RL;
GRANT CREATE ROLE ON ACCOUNT TO ROLE OPENFLOW_ADMIN_RL;
GRANT CREATE EXTERNAL ACCESS INTEGRATION ON ACCOUNT TO ROLE OPENFLOW_ADMIN_RL;
GRANT CREATE OPENFLOW DEPLOYMENT ON ACCOUNT TO ROLE OPENFLOW_ADMIN_RL;
GRANT CREATE COMPUTE POOL ON ACCOUNT TO ROLE OPENFLOW_ADMIN_RL;
GRANT ROLE OPENFLOW_ADMIN_RL TO USER <current_user>;
```

---

## Step 2: Infrastructure Database and Schema

The infra database and schema hold the Openflow runtime objects (connectors,
secrets, network rules). A common convention is `OPENFLOW.OPENFLOW` but any
names work — ask the user if they have a naming standard.

```sql
USE ROLE <admin_role>;
CREATE DATABASE IF NOT EXISTS OPENFLOW
  COMMENT = 'Openflow infrastructure database. [openflow]';
CREATE SCHEMA IF NOT EXISTS OPENFLOW.OPENFLOW
  COMMENT = 'Openflow infrastructure schema. [openflow]';
```

---

## Step 3: Deployment

Check how many SNOWFLAKE deployments already exist and whether the account has
capacity for a new one:

```sql
SHOW OPENFLOW DEPLOYMENTS;
```

`SHOW OPENFLOW DEPLOYMENTS` may return several. Do not silently pick one. If one
or more SNOWFLAKE deployments exist, list them by name and ask the user which to
use (a single deployment can host multiple runtimes), or whether to create a new
one. Record the chosen deployment name — the runtime in Step 5 is created into it
and **cannot be moved to another deployment later** (moving requires recreating
the runtime).

To create a new SNOWFLAKE deployment:

```sql
USE ROLE <admin_role>;
CREATE OPENFLOW DEPLOYMENT <deployment_name>
  COMMENT = 'Openflow deployment for <purpose>. [openflow]';
```

Grant the DE role access to the deployment:

```sql
GRANT USAGE ON OPENFLOW DEPLOYMENT <deployment_name> TO ROLE <de_role>;
```

Offer to set a display name (shown in the Openflow UI):

```sql
ALTER OPENFLOW DEPLOYMENT <deployment_name> SET DISPLAY_NAME = '<friendly name>';
```

---

## Step 4: Event Table (recommended)

Openflow sends runtime logs and metrics to a Snowflake event table. On a SOM
deployment this is controlled by the **data plane integration's `EVENT_TABLE`
property** (account/region-level, created by the Control Plane Service). By
default it may point at the account event table (`SNOWFLAKE.TELEMETRY.EVENTS`).
A dedicated Openflow event table is recommended — for query performance,
granular access control, and simpler monitoring — and the skill's diagnostics
(`references/core-troubleshooting.md`, `references/platform-diagnostics.md`)
expect a known event table, so confirm or set it up now.

**Discover** the data plane integration and its current event table:

```sql
SHOW OPENFLOW DATA PLANE INTEGRATIONS;
-- Note the integration name (type OPENFLOW_DATA_PLANE)

DESCRIBE OPENFLOW DATA PLANE INTEGRATION <integration_name>;
-- Read the EVENT_TABLE property — where logs/metrics currently land

-- Check whether the intended dedicated table already exists:
SHOW EVENT TABLES LIKE 'EVENTS' IN SCHEMA <INFRA_DB>.<INFRA_SCHEMA>;
```

If `SHOW OPENFLOW DATA PLANE INTEGRATIONS` returns no rows, the integration
isn't visible to the current role — retry as ACCOUNTADMIN. If it genuinely does
not exist, this account isn't using the SOM data-plane event-table mechanism;
skip this step and revisit after the deployment finishes provisioning.

**Decide** the target table. Default to a dedicated table in the infra schema
from Step 2: `<INFRA_DB>.<INFRA_SCHEMA>.EVENTS` (e.g. `OPENFLOW.OPENFLOW.EVENTS`).
Ask the user if they have a naming standard. Recommend the dedicated table
unless the user explicitly prefers to keep the account default.

**Act** — verify first, create only if needed:

- If `EVENT_TABLE` already points at a table that exists, nothing to create —
  go to Verify.
- Create the dedicated event table if it does not exist. The admin role owns the
  infra schema from Step 2, which carries `CREATE EVENT TABLE`. (If you are
  reusing a schema the admin role does not own, first
  `GRANT CREATE EVENT TABLE ON SCHEMA <INFRA_DB>.<INFRA_SCHEMA> TO ROLE <admin_role>`
  as ACCOUNTADMIN, or hand off the create to an account admin.)

```sql
USE ROLE <admin_role>;
CREATE EVENT TABLE IF NOT EXISTS <INFRA_DB>.<INFRA_SCHEMA>.EVENTS
  COMMENT = 'Openflow runtime logs and metrics. [openflow]';
```

- Point the data plane integration at it. `SET EVENT_TABLE` **replaces** the
  current value — the `DESCRIBE` above already showed it. Requires ACCOUNTADMIN
  or the integration owner:

```sql
ALTER OPENFLOW DATA PLANE INTEGRATION <integration_name>
  SET EVENT_TABLE = '<INFRA_DB>.<INFRA_SCHEMA>.EVENTS';
```

If the current role cannot `ALTER` the integration or `CREATE` the table,
generate these statements for an account admin to run and continue — do not fail
the flow (admin handoff, per `references/deploy-prereqs.md`).

**Verify** the table is set and the admin role can read it:

```sql
DESCRIBE OPENFLOW DATA PLANE INTEGRATION <integration_name>;
-- Confirm EVENT_TABLE = <INFRA_DB>.<INFRA_SCHEMA>.EVENTS
```

The admin role owns the infra schema, so `SELECT` on a table there is implicit.
If the event table lives in a different DB/schema, grant access explicitly:

```sql
GRANT USAGE ON DATABASE <db> TO ROLE <admin_role>;
GRANT USAGE ON SCHEMA <db>.<schema> TO ROLE <admin_role>;
GRANT SELECT ON EVENT TABLE <db>.<schema>.EVENTS TO ROLE <admin_role>;
```

Note the resolved event table. On the CLI surface, record it as the `event_table`
value when writing the session cache in the Verify step below; on the Snowsight (SQL-only) surface there is no cache.

---

## Step 5: Runtime

Create a runtime in the deployment. Node type and sizing depend on the intended
connector workload — consult the connector-specific reference for requirements.

Ask the user what node type and node count they need.

**Confirm the target deployment before creating the runtime.** Show the deployment
the runtime will be created in and confirm it explicitly before running the SQL:

> "I'll create runtime `<runtime_name>` in deployment `<deployment_name>`. A runtime can't be moved to a different deployment later — it would have to be recreated. Is `<deployment_name>` the right deployment?"

```sql
USE ROLE <admin_role>;
USE SCHEMA <INFRA_DB>.<INFRA_SCHEMA>;
CREATE OPENFLOW RUNTIME <runtime_name>
  IN OPENFLOW DEPLOYMENT <deployment_name>
  MIN_NODES = <min_nodes>
  MAX_NODES = <max_nodes>
  NODE_TYPE = '<node_type>'
  EXECUTE_AS_ROLE = '<execute_as_role>'
  COMMENT = 'Openflow runtime for <purpose>. [openflow]';
```

Wait for provisioning — this typically takes 5-10 minutes:

```sql
SELECT SYSTEM$WAIT_FOR_STABLE_OPENFLOW_RUNTIMES(600, '<INFRA_DB>.<INFRA_SCHEMA>.<runtime_name>');
```

Alternatively, poll manually:

```sql
DESCRIBE OPENFLOW RUNTIME <INFRA_DB>.<INFRA_SCHEMA>.<runtime_name>;
-- Check 'status' field — wait for ACTIVE
```

---

## Step 6: Grant DE Role Access

Once the runtime is ACTIVE, grant the DE/connector-management role access:

```sql
GRANT USAGE ON OPENFLOW RUNTIME <INFRA_DB>.<INFRA_SCHEMA>.<runtime_name> TO ROLE <de_role>;
```

---

## Step 7: Verify

Confirm the runtime is ready:

```sql
SHOW OPENFLOW RUNTIMES IN ACCOUNT;
-- Confirm status = ACTIVE for the new runtime

DESCRIBE OPENFLOW RUNTIME <INFRA_DB>.<INFRA_SCHEMA>.<runtime_name>;
-- Confirm 'server_url' is populated (e.g. https://of--<account>.snowflakecomputing.app:443/<key>/nifi/)
```

**CLI surface:** record the discovered infrastructure to the session cache via
`references/bootstrap-discovery.md` Step 3 before proceeding. **Snowsight (SQL-only):** there is no cache — skip this; the deployment and runtime remain discoverable any time via `SHOW OPENFLOW DEPLOYMENTS` / `SHOW OPENFLOW RUNTIMES IN ACCOUNT`.

---

## Next Step

The runtime is now ACTIVE. Before creating a Gen2 connector, load
`references/connector-prereqs-gen2.md` to verify and set up connector-level
infrastructure (roles, destination DB, secret, network access) and
source-side configuration.

---

## See Also

- `references/deploy-greenfield-byoc.md` — BYOC alternative
- `references/connector-prereqs-gen2.md` — connector prerequisites (after runtime is ready)
- `references/bootstrap-discovery.md` — write discovered infra to cache (CLI only)
