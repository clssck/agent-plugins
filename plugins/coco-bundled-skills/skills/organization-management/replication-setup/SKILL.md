---
name: organization-management-replication-setup
description: "Account replication setup — enable replication and create replication groups for disaster recovery. Use when: enable replication, account replication, replication setup, enable account database replication, system global account set parameter, create replication group, primary replication group, secondary replication, replicate across accounts, cross-region replication, replication object types, business critical replication, replication edition requirements, failover group, replication refresh."
parent_skill: organization-management
---

# Account Replication Setup

Enable replication across accounts in your organization for disaster recovery, data distribution, and business continuity.

## When to Use

- "Enable replication for my accounts"
- "Replicate databases across accounts"
- "Create replication group"
- "Cross-region replication setup"
- "Business Critical replication features"

## Prerequisites

- **Roles:**
  - Enable replication: GLOBALORGADMIN or ORGADMIN
  - Manage replication groups: ACCOUNTADMIN
- **Editions:** Standard/Enterprise (databases only), Business Critical (all object types)
- **Regions:** Accounts must be in the same region group

**Note:** All replication group examples assume ACCOUNTADMIN role.

---

## Overview

**Account replication** enables replicating databases and account objects across accounts for disaster recovery, data distribution, and business continuity.

### Supported Object Types by Edition

| Object Type | Standard/Enterprise | Business Critical |
|-------------|---------------------|-------------------|
| Databases | ✅ | ✅ |
| External Volumes | ✅ | ✅ |
| Integrations | ❌ | ✅ |
| Network Policies | ❌ | ✅ |
| Account Parameters | ❌ | ✅ |
| Users, Roles | ❌ | ✅ |

---

## Step 1: Enable Replication

Enable replication for each account (organization administrator only):

```sql
SELECT SYSTEM$GLOBAL_ACCOUNT_SET_PARAMETER(
  '<org_name>.<account_name>',
  'ENABLE_ACCOUNT_DATABASE_REPLICATION',
  'true'
);
```

**Example:**

```sql
SELECT SYSTEM$GLOBAL_ACCOUNT_SET_PARAMETER('myorg.account_east', 'ENABLE_ACCOUNT_DATABASE_REPLICATION', 'true');
SELECT SYSTEM$GLOBAL_ACCOUNT_SET_PARAMETER('myorg.account_west', 'ENABLE_ACCOUNT_DATABASE_REPLICATION', 'true');
```

---

## Step 2: Create Primary Replication Group

**Syntax:**

```sql
CREATE REPLICATION GROUP <name>
  OBJECT_TYPES = <type> [ , <type> ... ]
  ALLOWED_ACCOUNTS = <org>.<account> [ , ... ]
  [ ALLOWED_DATABASES = <db_name> [ , ... ] ]
  [ REPLICATION_SCHEDULE = 'USING CRON <expr>' ];
```

**Object types:** DATABASES, INTEGRATIONS, NETWORK POLICIES, PARAMETERS, ROLES, USERS

**Examples:**

```sql
CREATE REPLICATION GROUP rg_databases
  OBJECT_TYPES = DATABASES
  ALLOWED_ACCOUNTS = myorg.account_west
  ALLOWED_DATABASES = sales_db, marketing_db
  REPLICATION_SCHEDULE = 'USING CRON 0 */4 * * * UTC';

CREATE REPLICATION GROUP rg_full_account
  OBJECT_TYPES = DATABASES, INTEGRATIONS, NETWORK POLICIES, PARAMETERS
  ALLOWED_ACCOUNTS = myorg.account_dr
  REPLICATION_SCHEDULE = 'USING CRON 0 * * * * UTC';
```

---

## Step 3: Create Secondary Replication Group

In each target account, create secondary as replica:

**Syntax:**

```sql
CREATE REPLICATION GROUP <name>
  AS REPLICA OF <org>.<source_account>.<primary_group_name>;
```

**Example:**

```sql
CREATE REPLICATION GROUP rg_databases
  AS REPLICA OF myorg.account_east.rg_databases;
```

**Important:** Secondary name must match primary name.

---

## Managing Replication

### View Replication Groups

```sql
SHOW REPLICATION GROUPS;
```

**Key columns:** `name`, `is_primary`, `primary`, `replication_schedule`, `next_scheduled_refresh`

### Refresh Replication

**Manual refresh:**

```sql
ALTER REPLICATION GROUP rg_databases REFRESH;
```

**Change schedule:**

```sql
ALTER REPLICATION GROUP rg_databases
  SET REPLICATION_SCHEDULE = 'USING CRON 0 */2 * * * UTC';
```

### Suspend/Resume

```sql
ALTER REPLICATION GROUP rg_databases SUSPEND;
ALTER REPLICATION GROUP rg_databases RESUME;
```

### Drop Replication Groups

Must drop all secondary groups before dropping primary:

```sql
DROP REPLICATION GROUP rg_databases;
```

---

## Complete DR Setup Example

**Scenario:** DR from us-east-1 to us-west-2 (Business Critical)

**Step 1: Enable replication (as GLOBALORGADMIN)**

```sql
SELECT SYSTEM$GLOBAL_ACCOUNT_SET_PARAMETER('myorg.prod_east', 'ENABLE_ACCOUNT_DATABASE_REPLICATION', 'true');
SELECT SYSTEM$GLOBAL_ACCOUNT_SET_PARAMETER('myorg.prod_west', 'ENABLE_ACCOUNT_DATABASE_REPLICATION', 'true');
```

**Step 2: Create primary group in prod_east**

```sql
CREATE REPLICATION GROUP rg_dr
  OBJECT_TYPES = DATABASES, INTEGRATIONS, NETWORK POLICIES, PARAMETERS
  ALLOWED_ACCOUNTS = myorg.prod_west
  REPLICATION_SCHEDULE = 'USING CRON 0 */1 * * * UTC';
```

**Step 3: Create secondary group in prod_west**

```sql
CREATE REPLICATION GROUP rg_dr
  AS REPLICA OF myorg.prod_east.rg_dr;
```

**Step 4: Test failover**

```sql
ALTER REPLICATION GROUP rg_dr REFRESH;
```

---

## Replication Schedules

| Schedule | CRON Expression |
|----------|----------------|
| Every hour | `USING CRON 0 * * * * UTC` |
| Every 4 hours | `USING CRON 0 */4 * * * UTC` |
| Daily at 2 AM | `USING CRON 0 2 * * * UTC` |
| Every 15 min | `USING CRON */15 * * * * UTC` |

---

## Troubleshooting

### "Account replication not enabled"

**Solution:** Enable using `SYSTEM$GLOBAL_ACCOUNT_SET_PARAMETER` as GLOBALORGADMIN/ORGADMIN.

### "Accounts in different region groups"

**Solution:** Check `SHOW REGIONS` — replication only works within same region group.

### "Cannot replicate integrations"

**Solution:** Integrations require Business Critical Edition. Upgrade or manually recreate.

### "Secondary group out of sync"

**Solution:**

```sql
SHOW REPLICATION GROUPS;
ALTER REPLICATION GROUP rg_databases RESUME;
ALTER REPLICATION GROUP rg_databases REFRESH;
```

### "Must drop secondary groups first"

**Solution:** Drop all secondary groups in target accounts before dropping primary.

---

## Edition-Specific Features

### Standard/Enterprise

**Can replicate:** Databases, external volumes  
**Cannot replicate:** Integrations, network policies, parameters, users, roles

### Business Critical

**Can replicate:** All Standard/Enterprise objects PLUS integrations, network policies, parameters, users, roles

---

## Monitoring Replication

**Check status:**

```sql
SHOW REPLICATION GROUPS;
```

**View history:**

```sql
SELECT *
FROM SNOWFLAKE.ACCOUNT_USAGE.REPLICATION_GROUP_REFRESH_HISTORY
WHERE REPLICATION_GROUP_NAME = 'rg_databases'
ORDER BY START_TIME DESC
LIMIT 10;
```

---

## Best Practices

### Replication Strategy

1. **Identify critical objects** — What must be replicated for DR?
2. **Choose frequency** — Balance RPO vs cost
3. **Test failover** — Practice quarterly
4. **Monitor lag** — Track replication delay
5. **Document procedures** — Maintain DR runbooks

### Frequency Guidelines

| RPO Target | Schedule | Use Case |
|------------|----------|----------|
| 1 hour | Every hour | Critical production |
| 4 hours | Every 4 hours | Standard production |
| Daily | Once per day | Reporting |

### Object Selection

**Replicate:** Production databases, UDFs, integrations (Business Critical), network policies (Business Critical)  
**Skip:** Transient tables, temporary tables, internal stages

---

## Key Concepts

- **Primary group** — Source account, defines what to replicate
- **Secondary group** — Target account, replica of primary
- **Refresh** — One-time immediate replication
- **Schedule** — Automatic periodic replication
- **Failover** — Switch production traffic to target (separate from replication)

---

## Related Skills

- **Account lifecycle** → `account-lifecycle/SKILL.md` for creating accounts in multiple regions
- **Client redirect** → `client-redirect/SKILL.md` for connection failover
- **GLOBALORGADMIN** → `globalorgadmin/SKILL.md` for organization administrator role
