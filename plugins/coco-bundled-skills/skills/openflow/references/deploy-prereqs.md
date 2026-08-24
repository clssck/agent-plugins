---
name: openflow-deploy-prereqs
description: Account-level prerequisites for deploying Openflow for the first
  time. Covers Terms of Service acceptance, privilege verification, and
  admin handoff if the current user lacks sufficient rights. Ends with
  the SPCS vs BYOC deployment type question. Load before deploy-greenfield-spcs.md
  or deploy-greenfield-byoc.md.
---

# Openflow Deployment Prerequisites

Work through these checks before attempting any deployment. They are account-level
gates that apply equally to SPCS and BYOC deployments.

---

## Step 1: Terms of Service Acceptance

Openflow requires an **ORGADMIN** to accept the Openflow Terms of Service before
any deployment is possible. This is a one-time, account-level action.

**Check whether ToS has already been accepted:**

```sql
SHOW OPENFLOW DEPLOYMENTS;
```

| Result | Meaning |
|--------|---------|
| Returns rows or an empty result set | ToS accepted — proceed to Step 2 |
| SQL error: "feature not enabled", "not available", or similar | ToS not yet accepted |

**If ToS is not accepted:**

The user (or a colleague with ORGADMIN) must accept in Snowsight:
> Admin > Billing & Terms > Snowflake Feature Terms > Openflow

Once accepted, `SHOW OPENFLOW DEPLOYMENTS` should execute without error. This
may take a few minutes to propagate. Do not proceed until this query runs cleanly.

If the current user is not an ORGADMIN and cannot accept the terms themselves,
identify the account's ORGADMIN and request they accept before continuing.

---

## Step 2: Privilege Check

Deploying Openflow requires elevated account-level privileges. Determine what
the current role can do:

```sql
SELECT CURRENT_USER() AS current_user, CURRENT_ROLE() AS active_role;
SHOW GRANTS TO ROLE <current_role>;
```

**Minimum privileges for SPCS deployment:**

| Privilege | Object | Required For |
|-----------|--------|-------------|
| `CREATE OPENFLOW DEPLOYMENT` | Account | Creating the deployment |
| `CREATE COMPUTE POOL` | Account | SPCS runtime compute |
| `CREATE DATABASE` | Account | Infra and destination databases |
| `CREATE ROLE` | Account | Admin, DE, execute-as roles |
| `CREATE EXTERNAL ACCESS INTEGRATION` | Account | EAI for source network access |

**For BYOC deployment:** Same as above except `CREATE COMPUTE POOL` is not required
(compute is managed externally).

ACCOUNTADMIN satisfies all of these. If the current role is not ACCOUNTADMIN,
check whether it has been granted these specific privileges.

**Check if ACCOUNTADMIN is available:**

```sql
SHOW GRANTS TO USER <current_user>;
-- Filter for ROLE = 'ACCOUNTADMIN'
```

---

## Step 3: Handling Insufficient Privileges

If the current role lacks the required privileges, there are two paths:

### Option A — Switch roles (if ACCOUNTADMIN is available)

```sql
USE ROLE ACCOUNTADMIN;
SHOW OPENFLOW DEPLOYMENTS;
-- Confirm this works before proceeding
```

If `SHOW OPENFLOW DEPLOYMENTS` runs cleanly with ACCOUNTADMIN, proceed to Step 4.

### Option B — Admin handoff (if ACCOUNTADMIN is not available)

Identify which steps need elevated privileges and generate the SQL for the
account admin to run. The deployment steps that specifically require ACCOUNTADMIN
(or account-level grants) are:

- Creating the admin role with account-level grants
- Creating the EAI (`CREATE EXTERNAL ACCESS INTEGRATION`)
- Granting `CREATE OPENFLOW DEPLOYMENT`, `CREATE COMPUTE POOL` to the admin role

Offer to generate a script of these statements that the user can send to their
account admin. The remaining steps (infra DB/schema, runtime creation once the
deployment exists) can be done with a lesser role that has been granted the
appropriate object-level privileges.

---

## Step 4: Choose Deployment Type

With prerequisites confirmed, ask the user which type of deployment they need:

**SPCS — Snowflake-managed compute**
- Snowflake provisions and manages the runtime infrastructure
- Simpler setup — fully SQL-driven
- → Load `references/deploy-greenfield-spcs.md`

**BYOC — Bring Your Own Compute**
- Runtime runs on customer-managed AWS compute
- Requires external infrastructure steps before any SQL
- No SNOWFLAKE deployment slot limit; `CREATE COMPUTE POOL` grant not needed
- → Load `references/deploy-greenfield-byoc.md`

If the user is unsure which to choose, recommend SPCS as the simpler starting
point unless they have a specific requirement for compute control, cost, or
network topology that makes BYOC preferable.

---

## See Also

- `references/deploy-greenfield-spcs.md` — SPCS deployment from this point
- `references/deploy-greenfield-byoc.md` — BYOC deployment from this point
