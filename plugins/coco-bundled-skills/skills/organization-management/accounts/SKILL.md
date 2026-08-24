---
name: organization-management-accounts
description: "Snowflake account inventory, editions, and role analytics across your organization. Use when the user asks about: what accounts are in my org, list all accounts, show me our accounts, how many accounts do we have, account inventory, what edition is each account on, which accounts are enterprise, which accounts are standard, which accounts are business critical, edition distribution, edition breakdown, accounts by region, accounts by edition, account status, inactive accounts, suspended accounts, reader accounts, managed accounts, who has globalorgadmin, who has accountadmin, account admins, how many admins, account roles, account locator, account URL, service level, tell me about my accounts."
parent_skill: organization-management
---

# Account Analytics & Insights

Comprehensive read-only analytics for accounts in your Snowflake organization.

## When to Use

- **Organization overview**: "Tell me about my organization account", "Show organization metadata"
- **Account inventory**: "List all accounts in my organization", "What accounts do we have?"
- **Edition analytics**: "What editions are our accounts on?", "Show edition distribution"
- **Reader accounts**: "How many reader accounts do we have?", "Show managed accounts"
- **Role analytics**: "Who has GLOBALORGADMIN?", "How many account admins per account?"

## When NOT to Use

- **Account lifecycle operations** (create, drop, restore accounts) — Out of scope for this read-only analytics skill
- **Organization user operations** — Use `organization-users/SKILL.md`
- **Executive insights and org health** — Use `org-hub/SKILL.md`
- **View discovery and mapping** — Use `org-usage-view/SKILL.md`

## Key Command Distinctions

**Use the right command:**

| Command | Purpose | Returns |
|---------|---------|---------|
| `SHOW ACCOUNTS;` ⭐ | List all active accounts (most common) | All active accounts |
| `SHOW ACCOUNTS HISTORY;` | Include dropped accounts | Active + dropped accounts |
| `SHOW ORGANIZATION ACCOUNTS;` | Show THE org account (singular) | Organization account metadata |

**Important:** 
- `SHOW ACCOUNTS` = List member accounts (plural)
- `SHOW ORGANIZATION ACCOUNTS` = Show org account (singular, NOT a list)

## Setup

1. **Load** `../references/global_guardrails.md`: Required context for all organization management operations.

## Prerequisites

### Warehouse Requirements

- **Analytics queries** (RESULT_SCAN, ORGANIZATION_USAGE views) → **Warehouse required**
- **SHOW commands** (SHOW ACCOUNTS, SHOW ORGANIZATION ACCOUNTS) → **No warehouse needed**

Follow the Warehouse Context rules in `global_guardrails.md` to auto-detect and set a warehouse when analytics are requested.

## Workflow

### Step 1: Set Role Context

First, check the current role:

```sql
SELECT CURRENT_ROLE();
```

- If the result is already `GLOBALORGADMIN` → **skip the role switch** and proceed to Step 2.
- If the result is a different role → switch and confirm:

```sql
USE ROLE GLOBALORGADMIN;
SELECT CURRENT_ROLE();
```

Only proceed if `CURRENT_ROLE()` returns `GLOBALORGADMIN`.

### Step 2: Understand User Intent

Determine what type of query the user is asking for:
- **Organization metadata** → Use SHOW ORGANIZATION ACCOUNTS (no warehouse needed)
- **Account list/inventory** → Use SHOW ACCOUNTS (no warehouse needed)
- **Analytics/statistics** → Use ORGANIZATION_USAGE views (**warehouse required**)

### Step 3: Check Warehouse (If Analytics Requested)

If user asks for statistics, analytics, or queries involving RESULT_SCAN() or ORGANIZATION_USAGE, follow the Warehouse Context rules in `global_guardrails.md`: check `CURRENT_WAREHOUSE()`, auto-select if null, only ask if none available.

### Step 4: Execute Appropriate Query

Follow the relevant section below based on user intent.

### Step 5: Present Results

Format results clearly with:
- Tables for lists
- Statistics with percentages
- Timestamps in readable format
- Clear explanations of what metrics mean

---

## Organization Account Information

**Command:** `SHOW ORGANIZATION ACCOUNTS` (singular - see Key Command Distinctions above)

For queries about THE organization account (singular, not member accounts):

```sql
-- Show organization account metadata
SHOW ORGANIZATION ACCOUNTS;
```

This returns metadata about the organization account itself, including:
- Organization name
- Account name
- Region
- Created date
- Organization metadata

**Use this for**: "Tell me about my organization account", "Show the organization account", "What is the org account?"

**Important:** This is NOT for listing all accounts. Use `SHOW ACCOUNTS` for account inventory.

---

## Account Inventory (All Accounts)

**Commands:** `SHOW ACCOUNTS` or `SHOW ACCOUNTS HISTORY` (see Key Command Distinctions above)

For queries about ALL accounts in the organization (plural):

### List Active Accounts Only

**Most common use case** - Use this by default:

```sql
-- List all active accounts
SHOW ACCOUNTS;
```

**Key columns:**
- `organization_name`, `account_name`
- `region` - Cloud region (AWS_US_WEST_2, etc.)
- `edition` - STANDARD, ENTERPRISE, BUSINESS_CRITICAL
- `account_url` - Connection URL
- `created_on` - Account creation timestamp
- `managed_accounts` - Count of reader/managed accounts created by this account
- `is_org_admin` - Whether ORGADMIN is enabled
- `is_organization_account` - Whether this is the org account

### List All Accounts (Including Dropped)

**Only use when user explicitly asks for dropped/deleted accounts:**

```sql
-- Include dropped accounts (within grace period)
SHOW ACCOUNTS HISTORY;
```

All columns from `SHOW ACCOUNTS` plus:
- `dropped_on` - When account was dropped (NULL for active)
- `scheduled_deletion_time` - When permanent deletion will occur
- `restored_on` - If account was previously restored

**Important:** Don't use `SHOW ACCOUNTS HISTORY` by default - only when user asks for deleted/dropped accounts.

---

## Edition Distribution & Statistics

### Edition Summary

```sql
-- Ensure warehouse is active (see Warehouse Context in global_guardrails.md)

-- Count accounts by edition
SHOW ACCOUNTS;

SELECT 
  "edition",
  COUNT(*) as account_count,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "edition" IS NOT NULL
GROUP BY "edition"
ORDER BY account_count DESC;
```

**Output**: Edition name, count, percentage

### Account Details by Edition

```sql
-- List all accounts with edition info
SHOW ACCOUNTS;

SELECT 
  "organization_name",
  "account_name",
  "edition",
  "region",
  "created_on"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
ORDER BY "edition", "account_name";
```

---

## Reader/Managed Accounts

**Note**: Reader accounts and managed accounts are the same thing.

### Total Reader Accounts Across Organization

```sql
-- Ensure warehouse is active (see Warehouse Context in global_guardrails.md)

-- Sum of all reader/managed accounts
SHOW ACCOUNTS;

SELECT 
  SUM("managed_accounts") as total_reader_accounts,
  COUNT(*) as total_parent_accounts
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
```

### Accounts with Reader Accounts

```sql
-- Show which accounts have reader accounts
SHOW ACCOUNTS;

SELECT 
  "account_name",
  "managed_accounts" as reader_account_count,
  "edition"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "managed_accounts" > 0
ORDER BY "managed_accounts" DESC;
```

### Detailed Reader Account Information

For more detailed information about reader accounts, use ORGANIZATION_USAGE:

```sql
-- Query reader accounts from ORGANIZATION_USAGE
SELECT 
  account_name,
  created_on,
  region,
  edition,
  comment
FROM SNOWFLAKE.ORGANIZATION_USAGE.ACCOUNTS
WHERE is_managed = TRUE
ORDER BY created_on DESC;
```

---

## Role Analytics

### Users with GLOBALORGADMIN

**Option 1: SHOW command (no warehouse needed):**

```sql
-- Show all users with GLOBALORGADMIN role
SHOW GRANTS OF ROLE GLOBALORGADMIN;
```

**Option 2: ORGANIZATION_USAGE:**

```sql
-- Ensure warehouse is active (see Warehouse Context in global_guardrails.md)

-- Users with GLOBALORGADMIN across organization
SELECT 
  grantee_name,
  created_on,
  granted_by
FROM SNOWFLAKE.ORGANIZATION_USAGE.GRANTS_TO_USERS
WHERE role = 'GLOBALORGADMIN'
  AND deleted_on IS NULL
ORDER BY created_on DESC;
```

### ACCOUNTADMIN Counts Per Account

```sql
-- Ensure warehouse is active (see Warehouse Context in global_guardrails.md)

-- How many ACCOUNTADMINs per account
SELECT 
  account_name,
  COUNT(DISTINCT grantee_name) as accountadmin_count,
  LISTAGG(DISTINCT grantee_name, ', ') as accountadmins
FROM SNOWFLAKE.ORGANIZATION_USAGE.GRANTS_TO_USERS
WHERE role = 'ACCOUNTADMIN'
  AND deleted_on IS NULL
GROUP BY account_name
ORDER BY accountadmin_count DESC;
```

### Total Role Count Per Account

```sql
-- Ensure warehouse is active (see Warehouse Context in global_guardrails.md)

-- How many roles in each account
SELECT 
  account_name,
  COUNT(DISTINCT name) as total_roles,

  -- system_roles: Account-level administrative roles only
  -- (Excludes PUBLIC pseudo-role for clearer reporting)
  SUM(CASE WHEN name IN ('ACCOUNTADMIN', 'SECURITYADMIN', 'SYSADMIN', 'USERADMIN') 
    THEN 1 ELSE 0 END) as system_roles,

  -- org_level_roles: Organization-level administrative roles
  SUM(CASE WHEN name IN ('ORGADMIN', 'GLOBALORGADMIN') 
    THEN 1 ELSE 0 END) as org_level_roles,

  -- custom_roles: User-defined roles only
  -- (Excludes ALL 7 system-defined roles including PUBLIC)
  COUNT(DISTINCT name) - 
  SUM(CASE WHEN name IN (
    'ACCOUNTADMIN', 'SECURITYADMIN', 'SYSADMIN', 'USERADMIN',   -- Account admin roles (4)
    'PUBLIC',                                                   -- Universal pseudo-role (1)
    'ORGADMIN', 'GLOBALORGADMIN'                                -- Org-level roles (2)
  ) THEN 1 ELSE 0 END) as custom_roles

FROM SNOWFLAKE.ORGANIZATION_USAGE.ROLES
WHERE deleted_on IS NULL
GROUP BY account_name
ORDER BY total_roles DESC;
```

---

## Output Format

Present results clearly:

### For Lists
Use markdown tables:

| Account Name | Edition | Region | Created On |
|--------------|---------|--------|------------|
| PROD_EAST | ENTERPRISE | AWS_US_EAST_1 | 2024-01-15 |
| DEV_WEST | STANDARD | AWS_US_WEST_2 | 2024-02-01 |

### For Statistics
Show counts and percentages:

```
Edition Distribution:
- ENTERPRISE: 45 accounts (60%)
- BUSINESS_CRITICAL: 20 accounts (27%)
- STANDARD: 10 accounts (13%)

Total: 75 accounts
```

---

## Important Notes

1. **Reader vs Managed Accounts**: Same thing, different terminology

2. **Performance**: ORGANIZATION_USAGE queries can be slow for large orgs (100+ accounts)

3. **Data Freshness**: ORGANIZATION_USAGE views have latency (typically 24 hours)

---

## Official Documentation

- [Managing Accounts](https://docs.snowflake.com/en/user-guide/organizations-manage-accounts)
- [SHOW ACCOUNTS](https://docs.snowflake.com/en/sql-reference/sql/show-accounts)
- [SHOW ORGANIZATION ACCOUNTS](https://docs.snowflake.com/en/sql-reference/sql/show-organization-accounts)
- [ORGANIZATION_USAGE.ACCOUNTS](https://docs.snowflake.com/en/sql-reference/organization-usage/accounts)
- [ORGANIZATION_USAGE.ROLES](https://docs.snowflake.com/en/sql-reference/organization-usage/roles)
