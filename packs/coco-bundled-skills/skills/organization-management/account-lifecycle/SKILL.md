---
name: organization-management-account-lifecycle
description: "Account lifecycle management — CREATE and ALTER accounts in your organization. Use when: create account, create new account, provision account, alter account, modify account settings, change account parameters, account edition, upgrade edition, downgrade edition, change edition to business critical, account region, create account in different region, account naming conventions, account parameters, set account parameters, resource monitor, network policy, authentication policy, contact management."
parent_skill: organization-management
---

# Account Lifecycle Management

Manage accounts in your organization — create and configure accounts as GLOBALORGADMIN or ORGADMIN.

## When to Use

- "Create a new account"
- "How do I provision an account in a different region?"
- "Change account settings or parameters"
- "What editions are available?"
- "How do I upgrade to Business Critical?"

## Prerequisites

- **Role Required:**
  - **CREATE ACCOUNT:** GLOBALORGADMIN or ORGADMIN
  - **ALTER ACCOUNT (own account):** ACCOUNTADMIN
  - **ALTER ACCOUNT (other accounts):** GLOBALORGADMIN or ORGADMIN
- **Account Limit:** Maximum 25 accounts per organization by default (contact Snowflake Support to increase)

---

## Creating Accounts

### CREATE ACCOUNT Command

**Syntax:**

```sql
CREATE ACCOUNT <name>
  ADMIN_NAME = '<string>'
  { ADMIN_PASSWORD = '<string>' | ADMIN_RSA_PUBLIC_KEY = '<string>' }
  EMAIL = '<string>'
  EDITION = { STANDARD | ENTERPRISE | BUSINESS_CRITICAL }
  [ ADMIN_USER_TYPE = { PERSON | SERVICE | LEGACY_SERVICE | NULL } ]
  [ FIRST_NAME = '<string>' ]
  [ LAST_NAME = '<string>' ]
  [ MUST_CHANGE_PASSWORD = { TRUE | FALSE } ]
  [ REGION_GROUP = <region_group_id> ]
  [ REGION = <snowflake_region_id> ]
  [ COMMENT = '<string>' ]
  [ POLARIS = { TRUE | FALSE } ];
```

### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `name` | Account name (must conform to identifier requirements) | `myaccount1` |
| `ADMIN_NAME` | Login name for initial admin user | `admin` |
| `ADMIN_PASSWORD` | Password for admin user (or use `ADMIN_RSA_PUBLIC_KEY`) | `'<password>'` |
| `EMAIL` | Email for admin user and notifications | `'admin@myorg.com'` |
| `EDITION` | Snowflake Edition | `ENTERPRISE` |

### Optional Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ADMIN_USER_TYPE` | Type of admin user (PERSON, SERVICE) | `NULL` (same as PERSON) |
| `FIRST_NAME`, `LAST_NAME` | Admin user's name | `NULL` |
| `MUST_CHANGE_PASSWORD` | Force password change on first login | `FALSE` |
| `REGION_GROUP` | Region group ID (use `SHOW REGIONS`) | Current region group |
| `REGION` | Snowflake Region ID | Current region |
| `COMMENT` | Account description | `NULL` |
| `POLARIS` | Create Open Catalog account | `FALSE` |

### Edition Selection Guide

| Edition | Use Case | Features |
|---------|----------|----------|
| **STANDARD** | Basic workloads, dev/test | Core features, up to 1-day Time Travel |
| **ENTERPRISE** | Production workloads | Multi-cluster warehouses, up to 90-day Time Travel, data sharing |
| **BUSINESS_CRITICAL** | Regulated industries, high security | All Enterprise features plus HIPAA/PCI compliance, enhanced security, failover/fallback |

### Examples

**Create account in same region:**

```sql
USE ROLE GLOBALORGADMIN;

CREATE ACCOUNT myaccount1
  ADMIN_NAME = admin
  ADMIN_PASSWORD = '<password>'
  EMAIL = 'admin@myorg.com'
  EDITION = enterprise
  MUST_CHANGE_PASSWORD = true;
```

**Create account in specific region:**

```sql
USE ROLE GLOBALORGADMIN;

CREATE ACCOUNT myaccount_west
  ADMIN_NAME = admin
  ADMIN_PASSWORD = '<password>'
  EMAIL = 'admin@myorg.com'
  EDITION = enterprise
  REGION = aws_us_west_2
  COMMENT = 'West coast production account';
```

**Create account with key pair authentication:**

```sql
USE ROLE GLOBALORGADMIN;

CREATE ACCOUNT myaccount2
  ADMIN_NAME = admin
  ADMIN_RSA_PUBLIC_KEY = 'MIIBIjANBgkqhki...'
  EMAIL = 'admin@myorg.com'
  EDITION = business_critical
  FIRST_NAME = Jane
  LAST_NAME = Smith;
```

**Create Open Catalog (Polaris) account:**

```sql
USE ROLE GLOBALORGADMIN;

CREATE ACCOUNT catalog_account
  ADMIN_NAME = admin
  ADMIN_PASSWORD = '<password>'
  EMAIL = 'catalog@myorg.com'
  EDITION = enterprise
  REGION = aws_us_west_2
  POLARIS = true;
```

### Important Notes

- DNS propagation takes approximately 30 seconds before you can access a newly created account
- Account name must conform to identifier requirements (letters, numbers, underscores)
- Maximum 25 accounts per organization by default

---

## Modifying Accounts

### ALTER ACCOUNT Command

The `ALTER ACCOUNT` command has two purposes:

1. **Account administrators** (ACCOUNTADMIN) modify parameters and settings for their own account
2. **Organization administrators** (GLOBALORGADMIN/ORGADMIN) modify core characteristics of any account

### Altering Current Account (ACCOUNTADMIN)

**Set account parameters:**

```sql
USE ROLE ACCOUNTADMIN;

ALTER ACCOUNT SET DATA_RETENTION_TIME_IN_DAYS = 7;
ALTER ACCOUNT SET NETWORK_POLICY = my_network_policy;
ALTER ACCOUNT SET STATEMENT_TIMEOUT_IN_SECONDS = 3600;
```

**Set resource monitor:**

```sql
USE ROLE ACCOUNTADMIN;

ALTER ACCOUNT SET RESOURCE_MONITOR = my_monitor;
```

**Set authentication policy:**

```sql
USE ROLE ACCOUNTADMIN;

ALTER ACCOUNT SET AUTHENTICATION POLICY my_auth_policy FOR ALL PERSON USERS;
```

**Set password policy:**

```sql
USE ROLE ACCOUNTADMIN;

ALTER ACCOUNT SET PASSWORD POLICY my_password_policy;
```

**Set contact information:**

```sql
USE ROLE ACCOUNTADMIN;

ALTER ACCOUNT SET CONTACT 
  billing = billing_contact,
  technical = tech_contact;
```

**Add organization user groups:**

```sql
USE ROLE ACCOUNTADMIN;

ALTER ACCOUNT ADD ORGANIZATION USER GROUP my_org_group;
```

**Unset parameters:**

```sql
USE ROLE ACCOUNTADMIN;

ALTER ACCOUNT UNSET DATA_RETENTION_TIME_IN_DAYS;
ALTER ACCOUNT UNSET NETWORK_POLICY;
```

### Altering Other Accounts (GLOBALORGADMIN/ORGADMIN)

**Rename account:**

```sql
USE ROLE GLOBALORGADMIN;

ALTER ACCOUNT myaccount1 RENAME TO myaccount_renamed;
```

**Enable/disable ORGADMIN role:**

```sql
USE ROLE ORGADMIN;

ALTER ACCOUNT myaccount2 SET IS_ORG_ADMIN = TRUE;
ALTER ACCOUNT myaccount3 SET IS_ORG_ADMIN = FALSE;
```

**Set account comment:**

```sql
USE ROLE GLOBALORGADMIN;

ALTER ACCOUNT myaccount1 SET COMMENT = 'Production account for sales team';
```

**Suspend/resume account:**

```sql
USE ROLE GLOBALORGADMIN;

ALTER ACCOUNT myaccount1 SUSPEND;
ALTER ACCOUNT myaccount1 RESUME;
```

### Common Account Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `DATA_RETENTION_TIME_IN_DAYS` | Time Travel retention period (0-90 days) | `7` |
| `NETWORK_POLICY` | Network policy name | `my_policy` |
| `STATEMENT_TIMEOUT_IN_SECONDS` | Query timeout | `3600` |
| `ENABLE_UNREDACTED_QUERY_SYNTAX_ERROR` | Show full query text in errors | `TRUE` |
| `PERIODIC_DATA_REKEYING` | Enable automatic key rotation | `TRUE` |
| `READ_CONSISTENCY_MODE` | Consistency mode | `GLOBAL` |

---

## Viewing Accounts

### Show All Accounts

```sql
USE ROLE GLOBALORGADMIN;

SHOW ACCOUNTS;
```

**Output columns:**
- `organization_name` — Organization name
- `account_name` — Account name
- `region` — Snowflake Region
- `edition` — Account edition
- `account_locator` — Account locator
- `created_on` — Creation timestamp
- `is_org_admin` — Whether ORGADMIN is enabled

### Show Available Regions

```sql
USE ROLE GLOBALORGADMIN;

SHOW REGIONS;
```

**Use this to find valid values for:**
- `REGION` parameter in `CREATE ACCOUNT`
- `REGION_GROUP` parameter in `CREATE ACCOUNT`

---

## Troubleshooting

### "Cannot access newly created account"

**Cause:** DNS changes have not propagated yet.

**Solution:** Wait 30 seconds and try again. Account creation is asynchronous.

### "Account limit exceeded"

**Cause:** Organization has reached the default limit of 25 accounts.

**Solution:** Contact Snowflake Support to increase the account limit.

### "Cannot disable ORGADMIN in last account"

**Cause:** At least one account must have ORGADMIN enabled.

**Solution:** 
1. Enable ORGADMIN in another account first, OR
2. Create an organization account and migrate to GLOBALORGADMIN

---

## Key Concepts

### Account Identifiers

Snowflake uses multiple formats for identifying accounts:

| Format | Example | Use Case |
|--------|---------|----------|
| Account name | `myaccount` | `CREATE ACCOUNT`, `ALTER ACCOUNT` |
| Account locator | `AB12345` | Legacy connection strings |
| Fully qualified | `myorg.myaccount` | Cross-account references |
| Connection URL | `myorg-myaccount.snowflakecomputing.com` | Client connections |

### Account Naming Requirements

- Letters, numbers, and underscores only
- Must start with a letter
- Case-insensitive
- Cannot exceed 255 characters
- Must be unique within organization

### Edition Upgrades

You cannot directly upgrade an account edition with `ALTER ACCOUNT`. To upgrade:

1. Create a new account with the desired edition
2. Migrate objects using replication or data sharing
3. Update client connection strings
4. Retire the old account (contact Snowflake Support for assistance)

Alternatively, contact Snowflake Support for in-place edition upgrades.

---

## Related Skills

- **Account inventory** → See `accounts/SKILL.md` for read-only account analytics
- **GLOBALORGADMIN setup** → See `globalorgadmin/SKILL.md` for role management
- **Organization users** → See `organization-users/create/SKILL.md` for user management
- **Reader accounts** → See `reader-accounts/SKILL.md` for managed account lifecycle
