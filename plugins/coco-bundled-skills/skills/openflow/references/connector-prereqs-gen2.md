---
name: openflow-connector-prereqs-gen2
description: Prerequisites for a Gen2 Openflow connector installation. Load when
  any infrastructure object may be missing — DE/execute-as roles, destination DB,
  warehouse, secret, network rule, or EAI.
  Applies before any connector-specific reference (e.g. connector-postgres-gen2.md).
---

# Gen2 Connector Prerequisites

This reference guides you through verifying and fulfilling the prerequisites
for a Gen2 Openflow connector. For each object, follow the pattern:
**Discover** (check if it exists) → **Decide** (ask user) → **Act** (only if needed) → **Verify** (confirm).

Do not create objects without first checking whether suitable ones already exist.
Do not assume placeholder names — ask the user for confirmation on naming.

---

## Before You Start

This reference needs the target deployment/runtime, the runtime's execute-as role, and the `openflow_admin_role`. Where these come from depends on the surface:

- **SQL surface (Snowsight, or CLI + Gen2):** obtain them via SQL discovery — see `references/core-session-sql.md` (`SHOW OPENFLOW DEPLOYMENTS` / `SHOW OPENFLOW RUNTIMES IN ACCOUNT` / `DESCRIBE OPENFLOW RUNTIME`). No cache is involved.
- **CLI (Gen1/canvas, bootstrap done):** they are populated in the local cache by `references/bootstrap-discovery.md`. If the cache is missing or incomplete, **STOP** and load `references/bootstrap-cli.md` to run the bootstrap flow before returning here.

All infrastructure facts used below (admin role, runtime, execute-as role) come from session init — the two bullets above describe how each surface obtains them.

### Privilege Pre-Check

Before working through any infrastructure, determine what the current session can
actually do. This prevents hitting a permission wall partway through.

Check whether the current user can assume the admin role (the `openflow_admin_role` identified during session init):

```sql
SHOW GRANTS TO USER <current_user>;
-- Filter for: granted_on = 'ROLE', role = '<openflow_admin_role>'
```

Then confirm the admin role holds the grants needed for object creation:

```sql
SHOW GRANTS TO ROLE <openflow_admin_role>;
-- Looking for: CREATE ROLE on ACCOUNT, CREATE DATABASE on ACCOUNT (for new infra)
```

| Situation | Action |
|-----------|--------|
| Current user has the admin role with required grants | Proceed normally — you can create objects directly. |
| Admin role available but missing some grants | Note which grants are missing; generate them for an ACCOUNTADMIN to run. |
| Current user does NOT have the admin role | **Admin handoff (script mode).** Tell the user upfront: "Your current role can't create the required objects. I'll walk through the prerequisites and produce a complete SQL script for your account admin to run." Generate the full prerequisite SQL as you work through each section, rather than executing it. |

This mirrors the privilege handoff in `references/deploy-prereqs.md` — same mechanism (switch role if available, otherwise generate an admin script), applied to connector prerequisites rather than deployment.

Do not auto-escalate to ACCOUNTADMIN. If the user wants to switch roles, ask first.

### Collect Source Information from User

Before working through the infrastructure sections, ask the user:

1. **Source hostname and port** — needed to validate network rules.
   Clean the input: strip any protocol prefix, port suffix (capture separately),
   paths, and query params.
2. **Connector type** — check available definitions with `SHOW OPENFLOW CONNECTOR DEFINITIONS`.

> "What's the hostname and port for the source system? If you don't know it yet, that's fine — say so and we'll set up the other prerequisites first, then add the network rule for the host later."

If the user doesn't know the host yet, record it as pending and defer the network
rule (Section 6): complete the other prerequisites, then return to add the
network rule once the host is known. Never invent or assume a host.

### Surface Known Limitations Early

Before any infrastructure work, inform the user of connector-specific constraints.
Load the connector-specific reference (e.g. `connector-postgres-gen2.md`) to find
limitations for their connector type.

### Runtime Selection

There may be multiple runtimes. Do not assume the first one is
the right target. Some connectors (e.g. Postgres CDC) should run on a dedicated
runtime to avoid resource contention.

List all runtimes (known from session init) and check how many connectors each already hosts:

```sql
SHOW OPENFLOW RUNTIMES IN ACCOUNT;
```

For each candidate runtime, count existing connectors:

```sql
SHOW OPENFLOW CONNECTORS IN ACCOUNT;
-- Group by runtime to see which runtimes are empty vs in use
```

| Situation | Action |
|-----------|--------|
| An empty runtime exists | Recommend it for connectors that prefer isolation (e.g. CDC). |
| Only runtimes with existing connectors exist | Ask the user: "The available runtimes already host connectors. Would you like to use one of them, or create a new dedicated runtime?" If new → route to `deploy-greenfield-spcs.md` (or `-byoc.md`) to create it, then return here. |
| Connector-specific guidance | Check the connector reference — for Postgres CDC, a dedicated empty runtime is recommended. |

Record the selected runtime as the working runtime for the rest of this reference.

---

## 1. Infrastructure Database and Schema

### Discover

The infra DB/schema should already exist if a runtime is running (the runtime
lives IN this schema). Use the runtime's schema-qualified name (known from session init, e.g. from `SHOW OPENFLOW RUNTIMES IN ACCOUNT`):

```
e.g. "OPENFLOW.OPENFLOW.MY_RUNTIME" → DB=OPENFLOW, SCHEMA=OPENFLOW
```

Verify it exists:

```sql
SHOW DATABASES LIKE '<INFRA_DB>';
SHOW SCHEMAS LIKE '<INFRA_SCHEMA>' IN DATABASE <INFRA_DB>;
```

### Decide

| Situation | Action |
|-----------|--------|
| DB and schema exist | Show the user the resolved infra DB/schema and state that the connector's secret and network rule will be created there (e.g. "The runtime lives in `OPENFLOW.OPENFLOW`, so the secret and network rule will be created in that database/schema."). Confirm this is the intended location before proceeding to Section 2 — do not presume it. |
| Missing | Ask: "I wasn't able to find the infrastructure database/schema that the runtime should be in. This could indicate the deployment isn't complete, or that the current role lacks visibility. Is this expected?" If the user confirms it's unexpected or they haven't deployed yet → **STOP** and load `references/deploy-prereqs.md` to complete the deployment first. If it's a permissions issue, ask the user to confirm the correct DB/schema names. |

### Act

No creation from this reference. If the DB/schema is missing, route to
`references/deploy-prereqs.md` → `deploy-greenfield-spcs.md` or
`deploy-greenfield-byoc.md`.

### Verify

```sql
SHOW DATABASES LIKE '<INFRA_DB>';
SHOW SCHEMAS LIKE '<INFRA_SCHEMA>' IN DATABASE <INFRA_DB>;
-- Both must return results.
```

---

## 2. Roles

Two roles are needed: a **DE/creator role** (creates and manages connectors)
and an **execute-as role** (runs inside the connector's compute context).

### Discover

The execute-as role is already known from session init (it's the runtime's `execute_as_role`, from `DESCRIBE OPENFLOW RUNTIME`).
The DE role may or may not already exist.

Search by name pattern AND by grant — name patterns alone miss roles with
non-standard names (e.g. a DE role called `DATA_ENG_RL`):

```sql
-- Name-pattern search
SHOW ROLES LIKE '%OPENFLOW%';

-- Grant-based search: find roles already privileged on the infra schema
-- (catches roles that don't follow the OPENFLOW naming convention)
SHOW GRANTS ON SCHEMA <INFRA_DB>.<INFRA_SCHEMA>;
SHOW GRANTS ON DATABASE <INFRA_DB>;
-- A role holding CREATE OPENFLOW CONNECTOR on the schema is a strong DE-role signal
```

Validate the cached execute-as role's grants:

```sql
SHOW GRANTS TO ROLE <execute_as_role_from_cache>;
-- Check: does it have USAGE on the infra DB/schema?
```

Merge and deduplicate candidates from both searches before presenting to the user.

### Decide

Present findings to the user:

| Situation | Prompt |
|-----------|--------|
| Found roles that look like DE/connector roles | "I found `<role_names>`. Is one of these the DE role for creating connectors, or should I create a new one?" |
| Execute-as role exists but lacks infra DB grants | "The execute-as role `<name>` exists but doesn't have USAGE on `<INFRA_DB>.<INFRA_SCHEMA>`. I'll add those grants." |
| No DE-like role found | "I didn't find an existing DE role. Should I create one? (Suggested: `OPENFLOW_DE_RL` — a shared role for managing Openflow connectors across this account)" |

**Naming guidance:** Default to a broad, account-level name like `OPENFLOW_DE_RL`. Most users want one Openflow DE role (or one per connector family at most), not a separate DE role per connector instance. Only suggest a narrower name if the user has a specific separation-of-duties requirement.

### Act — Create DE role (if needed)

Only run this if the user confirmed creation is needed:

```sql
USE ROLE <admin_role>;
CREATE ROLE IF NOT EXISTS <DE_ROLE>
  COMMENT = 'Openflow DE role — creates and manages connectors. [openflow]';
GRANT ROLE <DE_ROLE> TO ROLE <admin_role>;

GRANT USAGE ON DATABASE <INFRA_DB> TO ROLE <DE_ROLE>;
GRANT USAGE ON SCHEMA <INFRA_DB>.<INFRA_SCHEMA> TO ROLE <DE_ROLE>;
GRANT CREATE OPENFLOW CONNECTOR ON SCHEMA <INFRA_DB>.<INFRA_SCHEMA> TO ROLE <DE_ROLE>;
GRANT CREATE SECRET ON SCHEMA <INFRA_DB>.<INFRA_SCHEMA> TO ROLE <DE_ROLE>;
```

### Act — Create execute-as role (if needed)

Usually this already exists (it was set when the runtime was created). Only
create if the user is setting up a new runtime-specific role:

```sql
USE ROLE <admin_role>;
CREATE ROLE IF NOT EXISTS <EXECUTE_AS_ROLE>
  COMMENT = 'Openflow execute-as role for connector runtime. [openflow]';

GRANT USAGE ON DATABASE <INFRA_DB> TO ROLE <EXECUTE_AS_ROLE>;
GRANT USAGE ON SCHEMA <INFRA_DB>.<INFRA_SCHEMA> TO ROLE <EXECUTE_AS_ROLE>;
```

### Verify

```sql
SHOW GRANTS TO ROLE <DE_ROLE>;
-- Confirm: USAGE on INFRA_DB, USAGE on INFRA_SCHEMA, CREATE OPENFLOW CONNECTOR on SCHEMA, CREATE SECRET on SCHEMA

SHOW GRANTS TO ROLE <EXECUTE_AS_ROLE>;
-- Confirm: USAGE on INFRA_DB, USAGE on INFRA_SCHEMA
```

---

## 3. Destination Database

### Discover

Ask the user what the destination should be. Recommend a dedicated database —
connectors typically create schemas and tables dynamically.

```sql
SHOW DATABASES;
-- Present any databases that look like they could be destinations
```

### Decide

> "Where should replicated data land? I recommend a dedicated database.
> Do you have an existing one to use, or should I create a new one?"

### Act (only if creating new)

```sql
USE ROLE <admin_role>;
CREATE DATABASE IF NOT EXISTS <DEST_DB>
  COMMENT = 'Openflow destination for connector data. [openflow]';

GRANT USAGE ON DATABASE <DEST_DB> TO ROLE <EXECUTE_AS_ROLE>;
GRANT CREATE SCHEMA ON DATABASE <DEST_DB> TO ROLE <EXECUTE_AS_ROLE>;
GRANT USAGE ON DATABASE <DEST_DB> TO ROLE <DE_ROLE>;
GRANT CREATE SCHEMA ON DATABASE <DEST_DB> TO ROLE <DE_ROLE>;
```

### Verify

```sql
SHOW GRANTS TO ROLE <EXECUTE_AS_ROLE>;
-- Confirm: USAGE on DATABASE <DEST_DB>, CREATE SCHEMA on DATABASE <DEST_DB>
```

---

## 4. Warehouse

We recommend the DE role has a default warehouse available. Not all connectors
require one, but it is needed for some connector operations.

### Discover

Check whether any warehouse is already accessible to the DE role, including
warehouses granted to PUBLIC (which every role inherits):

```sql
SHOW GRANTS TO ROLE <DE_ROLE>;
-- Filter for: privilege = 'USAGE', granted_on = 'WAREHOUSE'

-- Also check PUBLIC — warehouses granted here are accessible to every role
SHOW GRANTS TO ROLE PUBLIC;
-- Filter for: privilege = 'USAGE', granted_on = 'WAREHOUSE'
```

### Decide

| Situation | Prompt |
|-----------|--------|
| Warehouse granted directly to DE role | "Warehouse `<name>` is accessible to your DE role. That should be fine for connector use." |
| Warehouse granted to PUBLIC | "Warehouse `<name>` is accessible to all roles via PUBLIC, so the DE role can use it. That's sufficient." |
| No warehouse available | "The DE role doesn't have access to a warehouse. I recommend granting one. Should I create a dedicated warehouse, or grant access to an existing one?" |

### Act (only if creating new)

```sql
USE ROLE <admin_role>;
CREATE WAREHOUSE IF NOT EXISTS OPENFLOW_WH
  WITH WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 300
  AUTO_RESUME = TRUE
  COMMENT = 'Openflow default warehouse. [openflow]';

GRANT USAGE, OPERATE ON WAREHOUSE OPENFLOW_WH TO ROLE <DE_ROLE>;
GRANT USAGE, OPERATE ON WAREHOUSE OPENFLOW_WH TO ROLE <EXECUTE_AS_ROLE>;
```

### Verify

```sql
SHOW GRANTS TO ROLE <DE_ROLE>;
-- Confirm: USAGE + OPERATE on the warehouse
```

---

## 5. Secret — Source Credentials

### Safety Rules (non-negotiable)

- Secret type **must be `GENERIC_STRING`** (not `PASSWORD`) — the wizard's
  secret picker only shows generic strings.
- **Never execute `CREATE SECRET` directly.** The password must not pass through
  this session. Emit the SQL as a template for the user to run separately.

### Discover

Check for existing secrets that might already hold credentials for this source:

```sql
SHOW SECRETS IN SCHEMA <INFRA_DB>.<INFRA_SCHEMA>;
```

### Decide

| Situation | Prompt |
|-----------|--------|
| Secrets found in the infra schema | "I found these secrets: `<list>`. Does one of them hold the credentials for your source at `<hostname>`? (I cannot verify contents — only you know which is correct)" |
| No secrets found | "No secrets exist in the infra schema yet. I'll provide you with the SQL to create one." |
| User confirms one exists | DESCRIBE it to verify type = GENERIC_STRING. If not, warn and suggest creating a new one. |

**Never assume a secret is correct based on its name.** Always ask the user to confirm.

### Act (provide template — do NOT execute)

> "Run this in a Snowflake worksheet — replace `<YOUR_PASSWORD>` with the actual value:"

```sql
USE ROLE <admin_role>;
CREATE SECRET <INFRA_DB>.<INFRA_SCHEMA>.<SECRET_NAME>
  TYPE = GENERIC_STRING
  SECRET_STRING = '<YOUR_PASSWORD>'
  COMMENT = '<user-provided description>. [openflow]';
```

After the user confirms creation, continue to Verify.

### Verify

```sql
DESCRIBE SECRET <INFRA_DB>.<INFRA_SCHEMA>.<SECRET_NAME>;
-- Confirm: secret_type = GENERIC_STRING
```

If type is wrong (PASSWORD instead of GENERIC_STRING): warn the user that it
won't appear in the wizard dropdown and offer to create a new one.

Grant READ to the execute-as role:

```sql
GRANT READ ON SECRET <INFRA_DB>.<INFRA_SCHEMA>.<SECRET_NAME> TO ROLE <EXECUTE_AS_ROLE>;
```

---

## 6. Network Access (SPCS deployments only)

**Skip this section entirely for BYOC deployments** — they have direct network access.

For SPCS deployments, the runtime needs an External Access Integration (EAI)
with a network rule that covers the source host:port.

**Load `references/platform-eai.md`** — it provides the full workflow for:
- Discovering existing EAIs and network rules
- Deciding whether to reuse, extend, or create new
- Creating network rules and EAIs safely (never CREATE OR REPLACE)
- Attaching the EAI to the runtime

Pass it the source hostname and port collected earlier. After completing the EAI
workflow, return here to continue with the final checklist.

---

## 7. Source-Side Prerequisites

Source-side configuration is connector-specific. Load the appropriate
connector reference for instructions:

- Postgres CDC → `references/connector-postgres-gen2.md` (WAL level, publication, replication user, primary keys, source network access)
- MySQL CDC → `references/connector-mysql-gen2.md` (binary logging settings, replication user, server ID, primary keys, MariaDB: binlog_legacy_event_pos)

Present the source-side instructions to the user and ask them to confirm
completion before proceeding. Do not proceed with connector creation until
the user confirms all source-side items are ready.

---

## Final Checklist

Before returning to the connector-specific reference, verify ALL of the
following. Do not proceed with connector creation until every item is confirmed:

| # | Prerequisite | Verification |
|---|---|---|
| 1 | DE role exists with correct grants | `SHOW GRANTS TO ROLE <de_role>` — USAGE on infra DB/schema, CREATE OPENFLOW CONNECTOR |
| 2 | Execute-as role has USAGE on infra DB/schema | `SHOW GRANTS TO ROLE <execute_as_role>` |
| 3 | Destination DB exists with grants | `SHOW GRANTS TO ROLE <execute_as_role>` — USAGE + CREATE SCHEMA on dest DB |
| 4 | Warehouse accessible | `SHOW GRANTS TO ROLE <de_role>` — USAGE on warehouse |
| 5 | Secret is GENERIC_STRING with READ granted | `DESCRIBE SECRET` + `SHOW GRANTS ON SECRET` |
| 6 | Network rule + EAI attached to runtime (SPCS) | Completed via `references/platform-eai.md` |
| 7 | Source-side: user confirmed (connector-specific) | Per connector reference |

Only after all items pass → continue to Choose Your Path below.

---

## Choose Your Path

Prerequisites are complete. Ask the user how they want to create the connector:

| Path | When to use |
|------|-------------|
| **Guided Wizard** (UI) | First-time setup, prefer interactive validation, want richer table/column selection, or want to generate a config.json template. Load `references/connector-wizard.md`. |
| **CoCo / SQL** | Scripted or repeatable deployment, or you already have a config.json. Continue with the connector-specific reference (e.g. `connector-postgres-gen2.md`). |

> "Prerequisites are complete. Would you like to use the Guided Wizard in the Openflow UI, or continue here with SQL-based connector creation?"

If the user originally came from the Openflow UI setup flow, bias toward the
wizard. If they started in CoCo, bias toward continuing in CoCo — but offer the
wizard when richer schema/table/column selection would benefit them.

---

## See Also

- `references/connector-postgres-gen2.md` — Postgres CDC connector (source-side prereqs, lifecycle, config)
- `references/connector-mysql-gen2.md` — MySQL/MariaDB CDC connector (source-side prereqs, lifecycle, config)
- `references/connector-wizard.md` — Guided Wizard UI workflow
- `references/deploy-greenfield-spcs.md` — if the runtime itself does not yet exist (SPCS)
- `references/deploy-greenfield-byoc.md` — if the runtime itself does not yet exist (BYOC)
