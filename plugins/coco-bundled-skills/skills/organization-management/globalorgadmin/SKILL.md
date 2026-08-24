---
name: organization-management-globalorgadmin
description: "GLOBALORGADMIN and ORGADMIN role reference — when to use each role, how to set them up, how to check grants, how to enable or disable ORGADMIN in accounts. Use when the user asks about: GLOBALORGADMIN, ORGADMIN, organization administrator, org admin role, who has globalorgadmin, how to get globalorgadmin, enable orgadmin, disable orgadmin, organization admin setup, org admin permissions, what can globalorgadmin do, difference between orgadmin and globalorgadmin, organization account roles, create organization account, delegate organization privileges."
parent_skill: organization-management
---

# GLOBALORGADMIN & ORGADMIN Reference

Authoritative reference for Snowflake organization administrator roles.

## Two Ways to Administer an Organization

Snowflake provides two roles for organization-level tasks:

| Role | Where It Runs | Status | Recommended |
|---|---|---|---|
| **GLOBALORGADMIN** | Organization account only | Active — preferred | ✅ Yes |
| **ORGADMIN** | Any ORGADMIN-enabled account | Being phased out | ⚠️ Legacy |

**For multi-account organizations, always use GLOBALORGADMIN in the organization account.** ORGADMIN in regular accounts is being phased out. Snowflake will send notification emails at least three months prior to phasing out the ORGADMIN role.

## GLOBALORGADMIN

### What It Is

The GLOBALORGADMIN role is the preferred role for performing organization-level tasks. It is available in the **organization account** only. A user with this role is also known as the **global organization administrator**.

### How to Use It

1. Sign in to the **organization account**.
2. Switch to the GLOBALORGADMIN role:

```sql
USE ROLE GLOBALORGADMIN;
SELECT CURRENT_ROLE();
```

If `CURRENT_ROLE()` does not return `GLOBALORGADMIN`, the user does not have the role granted. Check grants:

```sql
SHOW GRANTS TO USER CURRENT_USER();
```

### Who Should Have GLOBALORGADMIN

- Organization administrators responsible for multi-account governance
- Users who need to view organization-wide usage, cost, and security data
- Users who manage account lifecycle (create, alter, drop)
- Users who manage organization users and user groups

### Privileges Assignable by GLOBALORGADMIN

The GLOBALORGADMIN role can assign specific organization-level privileges to other roles, allowing delegation of organization tasks without granting full GLOBALORGADMIN access.

**Assignable Privileges:**

- **APPLY TAG** — Apply tags to organization-level objects
- **MANAGE ACCOUNTS** — Create, alter, and drop accounts in the organization
- **MANAGE LISTING AUTO FULFILLMENT** — Manage automatic fulfillment of data listings
- **MANAGE ORGANIZATION CONTACTS** — Manage organization contact information
- **MANAGE ORGANIZATION TERMS** — Manage Snowflake Marketplace terms organization-wide
- **MANAGE ORGANIZATION USERS** — Manage organization users
- **MANAGE ORGANIZATION USER GROUPS** — Manage organization user groups
- **PURCHASE DATA EXCHANGE LISTING** — Purchase data exchange listings on behalf of the organization

**Example:**

```sql
USE ROLE GLOBALORGADMIN;
GRANT MANAGE ACCOUNTS ON ACCOUNT TO ROLE custom_admin_role;
```

---

## Creating an Organization Account

### What Is an Organization Account?

The **organization account** is a special type of account that organization administrators use to perform tasks affecting the entire organization. There is **only one** organization account per organization.

Key capabilities available in the organization account:

1. **View organization-level data** — Query history, login history, usage data from all accounts
2. **Manage organization-level objects** — Organization users and organization user groups  
3. **Manage account lifecycle** — Create, alter, and drop accounts
4. **Enable replication** — Set up account replication
5. **Enable Marketplace terms** — Approve Snowflake Marketplace terms organization-wide

### Prerequisites for Creating an Organization Account

Before creating the organization account:

- You must have an existing account with ORGADMIN role enabled
- Recommended: Create in a regulated region if you have accounts in U.S. SnowGov Regions
- Note: Creating an organization account incurs additional costs for ORGANIZATION_USAGE premium views

### How to Create the Organization Account

1. Sign in to an ORGADMIN-enabled account
2. Switch to the ORGADMIN role:

```sql
USE ROLE ORGADMIN;
```

3. Create the organization account:

```sql
CREATE ORGANIZATION ACCOUNT myorgaccount
  ADMIN_NAME = admin
  ADMIN_PASSWORD = '<password>'
  EMAIL = 'myemail@myorg.org'
  MUST_CHANGE_PASSWORD = true
  EDITION = enterprise;
```

**Important Notes:**
- Snowflake does not support custom account locators for organization accounts
- The organization account contains premium views in `SNOWFLAKE.ORGANIZATION_USAGE` schema that incur additional costs

---

## GLOBALORGADMIN: Full Capability Catalog

### 1. Cost Governance

As GLOBALORGADMIN you have visibility into all spending across the entire organization.

| Capability | SQL / View | What You Can See |
|---|---|---|
| Total org spend | `SNOWFLAKE.ORGANIZATION_USAGE.USAGE_IN_CURRENCY_DAILY` | Daily spend by account, service type, currency |
| Compute credit consumption | `SNOWFLAKE.ORGANIZATION_USAGE.METERING_DAILY_HISTORY` | Credits used/billed by service type per day |
| Warehouse-level credits | `SNOWFLAKE.ORGANIZATION_USAGE.WAREHOUSE_METERING_HISTORY` | Credits per warehouse (compute + cloud services) |
| Contract and balance | `SNOWFLAKE.ORGANIZATION_USAGE.CONTRACT_ITEMS` | Contract terms, committed amounts |
| Remaining balance | `SNOWFLAKE.ORGANIZATION_USAGE.REMAINING_BALANCE_DAILY` | Daily remaining credit balance |

**Key focus areas:**
- **Spend concentration** — identify which accounts drive the most cost
- **Runaway warehouses** — find warehouses burning credits disproportionately
- **Service sprawl** — track AI, Snowpipe, serverless, and other service costs growing quickly

### 2. Security Posture

Full visibility into authentication patterns, admin sprawl, and trust center findings across every account.

| Capability | SQL / View | What You Can See |
|---|---|---|
| Trust Center findings | `SNOWFLAKE.ORGANIZATION_USAGE.TRUST_CENTER_FINDINGS` | Security violations by severity, scanner, account, state |
| Login history | `SNOWFLAKE.ORGANIZATION_USAGE.LOGIN_HISTORY` | Every login event: user, auth method, success/failure, client type |
| User inventory | `SNOWFLAKE.ORGANIZATION_USAGE.USERS` | All users across all accounts |
| Session history | `SNOWFLAKE.ORGANIZATION_USAGE.SESSIONS` | Active and historical sessions |
| Role grants | `SNOWFLAKE.ORGANIZATION_USAGE.GRANTS_TO_USERS` | Who has which roles in which accounts |
| Role definitions | `SNOWFLAKE.ORGANIZATION_USAGE.GRANTS_TO_ROLES` | Role hierarchy and privilege grants |
| Network policies | `SNOWFLAKE.ORGANIZATION_USAGE.NETWORK_POLICIES` | Network policy definitions across accounts |

**Key focus areas:**
- **Password-only logins without MFA** — accounts vulnerable to credential attacks
- **Admin sprawl** — too many ACCOUNTADMIN/SECURITYADMIN grants across accounts
- **SSO adoption** — track SAML vs password vs OAuth login ratios
- **Trust Center violations** — critical and high-severity findings needing remediation

### 3. Account Lifecycle

Complete control over the organization's account inventory.

| Capability | SQL Command | What It Does |
|---|---|---|
| List all accounts | `SHOW ACCOUNTS` | All member accounts with name, region, status, creation date |
| Organization account metadata | `SHOW ORGANIZATION ACCOUNTS` | The organization account itself |
| Create account | `CREATE ACCOUNT <name> ...` | Provision new member accounts |
| Alter account | `ALTER ACCOUNT <name> SET ...` | Modify account parameters |
| Drop account | `DROP ACCOUNT <name>` | Remove accounts (high-risk) |
| Account history | `SHOW ACCOUNTS HISTORY` | Include dropped/deleted accounts |
| Enable ORGADMIN | `ALTER ACCOUNT <name> SET IS_ORG_ADMIN = TRUE` | Legacy — enable ORGADMIN in an account |

**Key focus areas:**
- **Account inventory** — know what exists, who owns it, what region it's in
- **Region sprawl** — data residency, latency, and compliance implications of accounts spread across regions

### 4. Organization Users & Groups

Manage identity at the organization level — users and groups that span accounts.

| Capability | SQL Command | What It Does |
|---|---|---|
| List org users | `SHOW ORGANIZATION USERS` | All organization-level users |
| List org user groups | `SHOW ORGANIZATION USER GROUPS` | All organization-level user groups |
| Create org user | `CREATE ORGANIZATION USER <name> ...` | Create a user at the org level |
| Alter org user | `ALTER ORGANIZATION USER <name> ...` | Modify org user properties |
| Drop org user | `DROP ORGANIZATION USER <name>` | Remove an org user |
| Create org user group | `CREATE ORGANIZATION USER GROUP <name>` | Create a group at the org level |
| Alter org user group | `ALTER ORGANIZATION USER GROUP <name> ...` | Modify group membership/properties |
| Drop org user group | `DROP ORGANIZATION USER GROUP <name>` | Remove an org user group |

**Note:** Organization users and user groups require Enterprise Edition or higher.

### 5. Compliance & Audit

Visibility into data access patterns, privilege changes, and policy enforcement across the organization.

| Capability | SQL / View | What You Can See |
|---|---|---|
| Trust Center findings | `SNOWFLAKE.ORGANIZATION_USAGE.TRUST_CENTER_FINDINGS` | Security recommendations and violations (CIS benchmarks, MFA, strong auth) |
| Access history | `SNOWFLAKE.ORGANIZATION_USAGE.ACCESS_HISTORY` | Who accessed what data, when |
| Grant changes | `SNOWFLAKE.ORGANIZATION_USAGE.GRANTS_TO_USERS` | Current role assignments; track privilege changes over time |
| Login anomalies | `SNOWFLAKE.ORGANIZATION_USAGE.LOGIN_HISTORY` | Failed logins, unusual patterns, auth method distribution |
| Masking policies | `SNOWFLAKE.ORGANIZATION_USAGE.MASKING_POLICIES` | Data masking policy definitions across accounts |
| Row access policies | `SNOWFLAKE.ORGANIZATION_USAGE.ROW_ACCESS_POLICIES` | Row-level security policies across accounts |
| Policy references | `SNOWFLAKE.ORGANIZATION_USAGE.POLICY_REFERENCES` | Where policies are applied |

**Key focus areas:**
- **Trust Center findings** — CIS benchmark violations, MFA readiness, strong auth compliance
- **Access history** — who accessed sensitive data and when
- **Grant changes** — detect privilege escalation or unexpected role assignments
- **Login anomalies** — failed login spikes, unusual client types, geographic anomalies

### 6. Capacity & Reliability

Monitor compute, storage, and operational health across the organization.

| Capability | SQL / View | What You Can See |
|---|---|---|
| Storage trends | `SNOWFLAKE.ORGANIZATION_USAGE.STORAGE_DAILY_HISTORY` | Daily storage by account (columns: `USAGE_DATE`, `ACCOUNT_NAME`, `AVERAGE_BYTES`) |
| Database storage | `SNOWFLAKE.ORGANIZATION_USAGE.DATABASE_STORAGE_USAGE_HISTORY` | Per-database storage across accounts |
| Warehouse load | `SNOWFLAKE.ORGANIZATION_USAGE.WAREHOUSE_LOAD_HISTORY` | Running and queued load per warehouse |
| Query history | `SNOWFLAKE.ORGANIZATION_USAGE.QUERY_HISTORY` | All queries across org (very large — 3-day max window) |
| Task history | `SNOWFLAKE.ORGANIZATION_USAGE.TASK_HISTORY` | Snowflake Task execution history |
| Replication | `SNOWFLAKE.ORGANIZATION_USAGE.REPLICATION_GROUP_USAGE_HISTORY` | Replication group credit and data transfer usage |
| Data transfer | `SNOWFLAKE.ORGANIZATION_USAGE.DATA_TRANSFER_HISTORY` | Cross-region and cross-cloud data transfer |
| Pipe usage | `SNOWFLAKE.ORGANIZATION_USAGE.PIPE_USAGE_HISTORY` | Snowpipe ingestion credits |
| Materialized views | `SNOWFLAKE.ORGANIZATION_USAGE.MATERIALIZED_VIEW_REFRESH_HISTORY` | MV refresh credit usage |
| Search optimization | `SNOWFLAKE.ORGANIZATION_USAGE.SEARCH_OPTIMIZATION_HISTORY` | Search optimization service credits |
| Query acceleration | `SNOWFLAKE.ORGANIZATION_USAGE.QUERY_ACCELERATION_HISTORY` | QAS credit usage |
| Auto-clustering | `SNOWFLAKE.ORGANIZATION_USAGE.AUTOMATIC_CLUSTERING_HISTORY` | Automatic clustering credit usage |

**Key focus areas:**
- **Query failures** — syntax errors indicate training gaps; timeouts indicate sizing issues
- **Warehouse queuing** — P99 queue time indicates undersizing
- **Storage growth** — unbounded growth leads to surprise bills

### 7. Object Inventory & Governance

Visibility into databases, tables, views, and governance objects across all accounts.

| Capability | SQL / View | What You Can See |
|---|---|---|
| Databases | `SNOWFLAKE.ORGANIZATION_USAGE.DATABASES` | All databases across accounts |
| Tables | `SNOWFLAKE.ORGANIZATION_USAGE.TABLES` | All tables across accounts |
| Views | `SNOWFLAKE.ORGANIZATION_USAGE.VIEWS` | All views across accounts |
| Roles | `SNOWFLAKE.ORGANIZATION_USAGE.ROLES` | All roles across accounts |
| Tags | `SNOWFLAKE.ORGANIZATION_USAGE.TAGS` | Tag definitions |
| Tag references | `SNOWFLAKE.ORGANIZATION_USAGE.TAG_REFERENCES` | Where tags are applied |

### 8. GLOBALORGADMIN Self-Administration

Managing the GLOBALORGADMIN role itself and ORGADMIN legacy role.

| Capability | SQL Command | What It Does |
|---|---|---|
| See who has GLOBALORGADMIN | `SHOW GRANTS OF ROLE GLOBALORGADMIN` | List all grantees |
| Grant GLOBALORGADMIN | `GRANT ROLE GLOBALORGADMIN TO USER <name>` | Give org admin access |
| Revoke GLOBALORGADMIN | `REVOKE ROLE GLOBALORGADMIN FROM USER <name>` | Remove org admin access |
| Delegate privileges | `GRANT <privilege> ON ACCOUNT TO ROLE <name>` | See "Privileges Assignable by GLOBALORGADMIN" section above |
| Enable ORGADMIN in account | `ALTER ACCOUNT <name> SET IS_ORG_ADMIN = TRUE` | Legacy — max 8 accounts |
| Disable ORGADMIN in account | `ALTER ACCOUNT <name> SET IS_ORG_ADMIN = FALSE` | Must run from a different ORGADMIN account |
| Check ORGADMIN status | `SHOW ACCOUNTS` → `"is_org_admin"` column | See which accounts have ORGADMIN |

---

## ORGADMIN (Legacy)

### What It Is

The ORGADMIN role allows organization-level tasks from **any ORGADMIN-enabled account**, not just the organization account. It is being **phased out** for multi-account organizations.

### How to Use It

1. Sign in to an ORGADMIN-enabled account.
2. Switch to the ORGADMIN role:

```sql
USE ROLE ORGADMIN;
SELECT CURRENT_ROLE();
```

### Enabling ORGADMIN in an Account

The first account in an organization has ORGADMIN enabled by default. To enable it in other accounts:

```sql
USE ROLE ORGADMIN;
ALTER ACCOUNT <account_name> SET IS_ORG_ADMIN = TRUE;
```

**Rules:**
- The `ALTER ACCOUNT` syntax only accepts the **account name format** of the account identifier — you cannot use the account locator.
- By default, ORGADMIN can be enabled in a **maximum of 8 accounts**. Contact Snowflake Support if you need more.
- ORGADMIN **cannot** be enabled for reader accounts.

### Disabling ORGADMIN in an Account

To prevent an account from performing organization-level tasks:

1. Sign in to a **different** ORGADMIN-enabled account.
2. Execute:

```sql
USE ROLE ORGADMIN;
ALTER ACCOUNT <account_name> SET IS_ORG_ADMIN = FALSE;
```

**Rules:**
- Must be run from a different ORGADMIN-enabled account — you cannot disable it from the account being modified.
- The `ALTER ACCOUNT` syntax only accepts the **account name format** — not the account locator.
- You **cannot** disable ORGADMIN if it is the last account that has the role enabled. Contact Snowflake Support in that case.

## ORGADMIN vs GLOBALORGADMIN

| Aspect | ORGADMIN | GLOBALORGADMIN |
|---|---|---|
| Level | Account-level role | Organization-level principal |
| Scope | Operates within an ORGADMIN-enabled account | Operates in the organization account |
| Where it exists | Inside a Snowflake account | The organization account |
| Granted via | `GRANT ROLE ORGADMIN TO USER <name>` within account | `GRANT ROLE GLOBALORGADMIN TO USER <name>` in org account |
| Can create accounts | ✅ Yes | ✅ Yes |
| Can view ORGANIZATION_USAGE | ✅ Yes (from ORGADMIN-enabled account) | ✅ Yes |
| Can manage org users/groups | ❌ No | ✅ Yes |
| Can delegate org privileges | ❌ No | ✅ Yes (see "Privileges Assignable by GLOBALORGADMIN" section) |
| Account limit | Maximum 8 accounts by default | N/A (single organization account) |
| Can be enabled for reader accounts | ❌ No | N/A |
| Status | Being phased out | Preferred |

## Decision Guide

When user asks "which role should I use?" or "how do I perform org-level tasks?":

| Scenario | Recommended Role |
|---|---|
| Multi-account organization, any org-level task | GLOBALORGADMIN in the organization account |
| Need to view ORGANIZATION_USAGE | GLOBALORGADMIN (required) |
| Need to manage organization users/groups | GLOBALORGADMIN in the organization account |
| Need to delegate organization privileges to custom roles | GLOBALORGADMIN in the organization account |
| Creating a new organization account | ORGADMIN from an existing ORGADMIN-enabled account |
| Legacy setup, single-account org operations | ORGADMIN (but recommend migrating to GLOBALORGADMIN) |
| User asks about ORGADMIN specifically | Acknowledge it exists, note it is being phased out, suggest GLOBALORGADMIN |

## Troubleshooting

### "I can't switch to GLOBALORGADMIN"
- Confirm the user is signed in to the **organization account**, not a regular member account. GLOBALORGADMIN only exists in the organization account.
- Check if the role is granted: `SHOW GRANTS TO USER CURRENT_USER();`
- The role must be explicitly granted by another GLOBALORGADMIN user.

### "ORGANIZATION_USAGE views say schema does not exist"
- The user is not using GLOBALORGADMIN. Run `USE ROLE GLOBALORGADMIN;` first.
- Or the user is in a regular account, not the organization account.

### "ALTER ACCOUNT fails with invalid identifier"
- The `ALTER ACCOUNT` command requires the **account name format**, not the account locator.
- Use: `ALTER ACCOUNT my_account_name SET ...`
- Do NOT use: `ALTER ACCOUNT AB12345 SET ...`

### "I want to enable ORGADMIN in more than 8 accounts"
- The default limit is 8 ORGADMIN-enabled accounts. Contact Snowflake Support to increase.

### "Cannot create ORGANIZATION ACCOUNT"

**Cause:** Must use ORGADMIN role from an existing ORGADMIN-enabled account, not GLOBALORGADMIN.

**Solution:**
- Use ORGADMIN role in an existing ORGADMIN-enabled account:

```sql
USE ROLE ORGADMIN;
CREATE ORGANIZATION ACCOUNT myorgaccount ...;
```

- You cannot convert an existing ORGADMIN-enabled account to be the organization account.

### "Cannot disable ORGADMIN in the last account"

**Cause:** At least one account must have ORGADMIN enabled.

**Solution:**
- Contact Snowflake Support if you need to disable ORGADMIN in the last remaining account.
- Consider creating an organization account and migrating to GLOBALORGADMIN instead.

---

## Reference Links

- [Organization administrators](https://docs.snowflake.com/en/user-guide/organization-administrators)
- [Organization account](https://docs.snowflake.com/en/user-guide/organization-account)
- [Managing accounts](https://docs.snowflake.com/en/user-guide/managing-accounts)
- [Organization users](https://docs.snowflake.com/en/user-guide/organization-users)

