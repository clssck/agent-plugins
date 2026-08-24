---
name: openflow-deploy-greenfield-byoc
description: Deploy an Openflow BYOC deployment on customer-managed AWS compute.
  Use when SHOW OPENFLOW DEPLOYMENTS returns empty or the user wants a new BYOC
  deployment, the account is SOM-enabled, and external AWS infrastructure is ready.
  External infrastructure must be deployed before the SQL steps in this reference.
---

# Greenfield Openflow Deployment — BYOC

Setup for an Openflow environment on customer-managed AWS compute.

**Reached from:** `references/deploy-prereqs.md` — ToS acceptance and privilege
verification should already be complete before loading this reference.

**Requires SOM:** This workflow uses SQL commands (`SHOW OPENFLOW DEPLOYMENTS`,
`CREATE OPENFLOW RUNTIME`) that are only available on SOM-enabled accounts. If
`SHOW OPENFLOW DEPLOYMENTS` returns a SQL error rather than an empty result set,
the account is not SOM-enabled and this reference does not apply — the user must
deploy via the Openflow UI in Snowsight.

**Scope:** BYOC (Bring Your Own Compute) deployment type only. For Snowflake-managed
SPCS, see `references/deploy-greenfield-spcs.md`.

**BYOC vs SPCS:** BYOC runtimes run on compute you own and operate in AWS.
Snowflake provides the control plane and connector definitions; you provide the
runtime environment. BYOC runtimes have **direct network access** from your VPC
and do not require EAI or Snowflake network rules.

---

## Overview

```
External infrastructure deployment
    ↓
Agent connects to Snowflake control plane
    ↓
BYOC deployment appears in SHOW OPENFLOW DEPLOYMENTS
    ↓
Create runtime in that deployment (SQL)
    ↓
Runtime ACTIVE → connector-prereqs-gen2.md
```

---

## Step 1: Deploy External Infrastructure (Non-SQL)

These steps happen outside Snowflake. Direct the user to:

1. **Get the BYOC deployment package** from the Openflow UI:
   Ingestion > Openflow > New Deployment > BYOC
   The UI provides a deployment token and configuration values specific to
   the Snowflake account.

2. **Deploy using the provided template** for AWS.
   Refer to Snowflake documentation for the current deployment package and
   template instructions.

3. **Configure the agent** with the Snowflake account URL and authentication
   credentials from Step 1.

4. **Start the agent.** Once running, it registers with the Openflow control
   plane and the deployment becomes visible in Snowflake.

Refer the user to Snowflake documentation for current template versions and
detailed deployment instructions — these change with product releases.

---

## Step 2: Verify Registration

Poll until the BYOC deployment appears in Snowflake:

```sql
SHOW OPENFLOW DEPLOYMENTS;
-- Wait for an entry with type = BYOC to appear.
-- This may take several minutes after the agent starts.
```

Do not proceed until the BYOC deployment shows `ACTIVE` status.

---

## Step 3: Admin Role (if not already created)

If an admin role does not yet exist, create one:

```sql
USE ROLE ACCOUNTADMIN;
CREATE ROLE IF NOT EXISTS OPENFLOW_ADMIN_RL
  COMMENT = 'Openflow admin role — owns deployments, runtimes, and infrastructure. [openflow]';

GRANT CREATE DATABASE ON ACCOUNT TO ROLE OPENFLOW_ADMIN_RL;
GRANT CREATE ROLE ON ACCOUNT TO ROLE OPENFLOW_ADMIN_RL;
GRANT CREATE EXTERNAL ACCESS INTEGRATION ON ACCOUNT TO ROLE OPENFLOW_ADMIN_RL;
GRANT ROLE OPENFLOW_ADMIN_RL TO USER <current_user>;
```

If an admin role already exists, reuse it.

---

## Step 4: Infrastructure Database and Schema

```sql
USE ROLE <admin_role>;
CREATE DATABASE IF NOT EXISTS OPENFLOW
  COMMENT = 'Openflow infrastructure database. [openflow]';
CREATE SCHEMA IF NOT EXISTS OPENFLOW.OPENFLOW
  COMMENT = 'Openflow infrastructure schema. [openflow]';
```

If the infra database already exists from a SPCS deployment, reuse it.

---

## Step 5: Event Table (recommended)

Openflow sends runtime logs and metrics to a Snowflake event table. On a SOM
account this is controlled by the **data plane integration's `EVENT_TABLE`
property** (account/region-level). By default it may point at the account event
table (`SNOWFLAKE.TELEMETRY.EVENTS`). A dedicated Openflow event table is
recommended — for query performance, granular access control, and simpler
monitoring — and the skill's diagnostics expect a known event table, so confirm
or set it up now.

> The data plane integration is account/region-level and shared with any SPCS
> deployment on the same account. If you already set the event table during an
> SPCS deployment, it applies here too — just verify it.

**Discover** the integration and its current event table:

```sql
SHOW OPENFLOW DATA PLANE INTEGRATIONS;
-- Note the integration name (type OPENFLOW_DATA_PLANE)

DESCRIBE OPENFLOW DATA PLANE INTEGRATION <integration_name>;
-- Read the EVENT_TABLE property

-- Check whether the intended dedicated table already exists:
SHOW EVENT TABLES LIKE 'EVENTS' IN SCHEMA <INFRA_DB>.<INFRA_SCHEMA>;
```

If `SHOW OPENFLOW DATA PLANE INTEGRATIONS` returns no rows, retry as
ACCOUNTADMIN; if it genuinely does not exist, this account isn't using the SOM
data-plane event-table mechanism — skip this step.

**Decide** the target table. Default to a dedicated table in the infra schema
from Step 4: `<INFRA_DB>.<INFRA_SCHEMA>.EVENTS` (e.g. `OPENFLOW.OPENFLOW.EVENTS`).
Ask the user for a naming standard; recommend the dedicated table over the
account default.

**Act** — verify first, create only if needed. The admin role owns the infra
schema from Step 4, which carries `CREATE EVENT TABLE`. (If reusing a schema it
does not own, `GRANT CREATE EVENT TABLE ON SCHEMA <INFRA_DB>.<INFRA_SCHEMA> TO
ROLE <admin_role>` as ACCOUNTADMIN first, or hand off the create.)

```sql
USE ROLE <admin_role>;
CREATE EVENT TABLE IF NOT EXISTS <INFRA_DB>.<INFRA_SCHEMA>.EVENTS
  COMMENT = 'Openflow runtime logs and metrics. [openflow]';
```

```sql
-- SET EVENT_TABLE replaces the current value (shown by DESCRIBE above).
-- Requires ACCOUNTADMIN or the integration owner:
ALTER OPENFLOW DATA PLANE INTEGRATION <integration_name>
  SET EVENT_TABLE = '<INFRA_DB>.<INFRA_SCHEMA>.EVENTS';
```

If the current role cannot `ALTER` the integration or `CREATE` the table,
generate the statements for an account admin and continue — do not fail the flow.

**Verify**:

```sql
DESCRIBE OPENFLOW DATA PLANE INTEGRATION <integration_name>;
-- Confirm EVENT_TABLE = <INFRA_DB>.<INFRA_SCHEMA>.EVENTS
```

The admin role owns the infra schema, so `SELECT` is implicit. If the event
table lives in a different DB/schema, grant access explicitly:

```sql
GRANT USAGE ON DATABASE <db> TO ROLE <admin_role>;
GRANT USAGE ON SCHEMA <db>.<schema> TO ROLE <admin_role>;
GRANT SELECT ON EVENT TABLE <db>.<schema>.EVENTS TO ROLE <admin_role>;
```

Note the resolved event table. On the CLI surface, record it as the `event_table`
value when writing the session cache in the Verify step below; on the Snowsight (SQL-only) surface there is no cache.

---

## Step 6: Runtime on BYOC Deployment

Create a runtime in the BYOC deployment. Node sizing is controlled by the
external compute you provisioned in Step 1 — specify values that match your
external cluster capacity.

```sql
USE ROLE <admin_role>;
USE SCHEMA <INFRA_DB>.<INFRA_SCHEMA>;
CREATE OPENFLOW RUNTIME <runtime_name>
  IN OPENFLOW DEPLOYMENT <byoc_deployment_name>
  MIN_NODES = <n>
  MAX_NODES = <n>
  NODE_TYPE = '<node_type>'
  EXECUTE_AS_ROLE = '<execute_as_role>'
  COMMENT = 'Openflow runtime for <purpose>. [openflow]';
```

Wait for provisioning:

```sql
SELECT SYSTEM$WAIT_FOR_STABLE_OPENFLOW_RUNTIMES(600, '<INFRA_DB>.<INFRA_SCHEMA>.<runtime_name>');
```

Alternatively, poll manually:

```sql
DESCRIBE OPENFLOW RUNTIME <INFRA_DB>.<INFRA_SCHEMA>.<runtime_name>;
-- Wait for status = ACTIVE
```

---

## Step 7: Grant DE Role Access

```sql
GRANT USAGE ON OPENFLOW DEPLOYMENT <byoc_deployment_name> TO ROLE <de_role>;
GRANT USAGE ON OPENFLOW RUNTIME <INFRA_DB>.<INFRA_SCHEMA>.<runtime_name> TO ROLE <de_role>;
```

---

## Step 8: Verify

```sql
SHOW OPENFLOW RUNTIMES IN ACCOUNT;
-- Confirm status = ACTIVE for the new runtime

DESCRIBE OPENFLOW RUNTIME <INFRA_DB>.<INFRA_SCHEMA>.<runtime_name>;
-- Confirm 'server_url' is populated
```

**CLI surface:** record the discovered infrastructure to the session cache via
`references/bootstrap-discovery.md` Step 3 before proceeding. **Snowsight (SQL-only):** there is no cache — skip this; the deployment and runtime remain discoverable any time via `SHOW OPENFLOW DEPLOYMENTS` / `SHOW OPENFLOW RUNTIMES IN ACCOUNT`.

---

## Network Access for BYOC

BYOC runtimes have **direct network access** from the external compute environment.
Snowflake EAI and network rules are not required.

The runtime must be able to reach the source system. The user should ensure
network connectivity is in place. If connectivity issues arise later, use
`references/ops-network-testing.md` to validate.

When using `references/connector-prereqs-gen2.md` after this setup, **skip**
the "Network Rule" and "External Access Integration" sections — those apply
to SPCS only.

---

## Next Step

The runtime is now ACTIVE. Load `references/connector-prereqs-gen2.md` to
verify and set up connector-level infrastructure (roles, destination DB,
warehouse, secret, source-side configuration). Skip the network access
section — BYOC has direct connectivity.

---

## See Also

- `references/deploy-greenfield-spcs.md` — SPCS alternative
- `references/connector-prereqs-gen2.md` — connector prerequisites (skip EAI/network rule sections for BYOC)
- `references/bootstrap-discovery.md` — write discovered infra to cache (CLI only)
