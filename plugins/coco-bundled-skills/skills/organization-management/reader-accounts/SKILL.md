---
name: organization-management-reader-accounts
description: "Reader accounts (managed accounts) — share data with consumers who are not Snowflake customers. Use when: reader account, managed account, create reader account, create managed account, provision reader account, share data with non-snowflake customer, share without subscription, drop reader account, delete reader account, alter managed account, reader account restrictions, what can reader accounts do, reader account credits, who pays for reader account, data sharing without licensing, reader account limit, show managed accounts, view reader accounts."
parent_skill: organization-management
---

# Reader Accounts (Managed Accounts)

Enable data sharing with consumers who are not Snowflake customers — no setup costs, no licensing agreements required.

## When to Use

- "Share data with non-Snowflake customers"
- "Create a reader account"
- "What are managed accounts?"
- "How do I share data without requiring Snowflake subscription?"
- "Who pays for reader account credits?"
- "What can reader accounts do?"
- "Reader account restrictions"

## Prerequisites

- **Role Required:** ACCOUNTADMIN (or role granted CREATE ACCOUNT privilege)
- **Reader Account Limit:** Maximum 20 reader accounts per provider account by default
- **Retention Period:** 7 days after dropping a reader account before you can create a new one

---

## What Are Reader Accounts?

### Overview

A **reader account** (formerly "read-only account") enables you to share data with consumers who are not Snowflake customers. 

**Key characteristics:**
- **No cost to consumer** — No setup fees, no usage charges for the consumer
- **No licensing required** — Consumer does not need Snowflake subscription
- **Provider pays** — Provider account pays all credit charges
- **Provider managed** — Provider creates, owns, and manages the account
- **Limited sharing** — Reader account can only consume data from the provider that created it
- **Same edition and region** — Reader account uses same edition and region as provider

### Use Cases

1. **Data monetization** — Sell access to curated data products
2. **Partner sharing** — Share data with business partners without requiring Snowflake
3. **Customer analytics** — Provide customers with access to their own data
4. **Demo environments** — Create demonstration accounts for prospects
5. **External reporting** — Share data for external audits or compliance

---

## Reader Account Capabilities

### What Reader Accounts CAN Do

✅ **Query shared data** — Run SELECT queries on shared databases  
✅ **Create views** — Build views, including materialized views  
✅ **Create warehouses** — Provision compute resources  
✅ **Create users and roles** — Manage access within the reader account  
✅ **Unload data** — Use COPY INTO with connection credentials  
✅ **Set up resource monitors** — Control credit consumption  

### What Reader Accounts CANNOT Do

❌ **Upload data** — Cannot use INSERT, MERGE, or COPY INTO to load data  
❌ **Modify data** — Cannot use UPDATE or DELETE  
❌ **Create shares** — Cannot share data with other accounts  
❌ **Use data metric functions** — Cannot set data quality metrics  
❌ **Use storage integrations** — Limited unload capabilities  
❌ **Create row access policies** — Some security features restricted  

---

## Creating Reader Accounts

### CREATE MANAGED ACCOUNT Command

**Syntax:**

```sql
CREATE MANAGED ACCOUNT <account_name>
  ADMIN_NAME = <username>,
  ADMIN_PASSWORD = '<password>',
  TYPE = READER
  [ COMMENT = '<string>' ];
```

### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `account_name` | Reader account identifier | `reader_acct1` |
| `ADMIN_NAME` | Login name for initial admin user | `admin` |
| `ADMIN_PASSWORD` | Password for admin user | `'<password>'` |
| `TYPE` | Must be `READER` | `READER` |

### Examples

**Create reader account:**

```sql
USE ROLE ACCOUNTADMIN;

CREATE MANAGED ACCOUNT reader_acct1
  ADMIN_NAME = admin,
  ADMIN_PASSWORD = '<password>',
  TYPE = READER;
```

**Output:**

```json
{
  "accountName": "READER_ACCT1",
  "accountLocator": "IIB88126",
  "url": "https://myorg-reader_acct1.snowflakecomputing.com",
  "accountLocatorUrl": "https://iib88126.snowflakecomputing.com"
}
```

**Create reader account with comment:**

```sql
USE ROLE ACCOUNTADMIN;

CREATE MANAGED ACCOUNT customer_reporting
  ADMIN_NAME = admin,
  ADMIN_PASSWORD = '<password>',
  TYPE = READER,
  COMMENT = 'Reader account for customer ABC reporting';
```

### Account Creation Details

- **Edition:** Same as provider account
- **Region:** Same as provider account
- **Provisioning time:** Wait up to 5 minutes for full provisioning
- **URL format:** `https://orgname-accountname.snowflakecomputing.com`

### Important Post-Creation Steps

After creating a reader account, you must:

1. **Wait 5 minutes** for full provisioning
2. **Add to share** — Share databases with the reader account
3. **Configure warehouses** — Set up compute resources
4. **Set resource monitors** — Control credit consumption

---

## Managing Reader Accounts

### Adding Reader Account to Share

```sql
USE ROLE ACCOUNTADMIN;

ALTER SHARE my_share ADD ACCOUNTS = reader_acct1;
```

### Viewing Reader Accounts

**Show all reader accounts:**

```sql
USE ROLE ACCOUNTADMIN;

SHOW MANAGED ACCOUNTS;
```

**Output columns:**
- `name` — Reader account name
- `cloud` — Cloud provider
- `region` — Snowflake region
- `locator` — Account locator
- `created_on` — Creation timestamp
- `url` — Preferred connection URL
- `account_locator_url` — Legacy connection URL
- `is_reader` — Always TRUE for reader accounts

### Renaming Reader Account

Reader accounts must be renamed using standard ALTER ACCOUNT:

```sql
USE ROLE ACCOUNTADMIN;

ALTER ACCOUNT reader_acct1 RENAME TO reader_acct1_new;
```

### Dropping Reader Account

```sql
USE ROLE ACCOUNTADMIN;

DROP MANAGED ACCOUNT reader_acct1;
```

**⚠️ Warning:**
- **Immediate deletion** — All objects and data are dropped immediately
- **Access revoked** — All users lose access immediately
- **Cannot undo** — This operation is permanent
- **7-day retention** — Cannot create a new reader account for 7 days after dropping

---

## Configuring Reader Accounts

### Creating Warehouses

After creating the reader account, log in as admin and create warehouses:

```sql
USE ROLE ACCOUNTADMIN;

CREATE WAREHOUSE reader_wh
  WITH WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE;
```

### Setting Resource Monitors

**⚠️ Critical:** Reader accounts can consume unlimited credits charged to provider. Always set resource monitors.

```sql
USE ROLE ACCOUNTADMIN;

CREATE RESOURCE MONITOR reader_limit
  WITH CREDIT_QUOTA = 100
  FREQUENCY = MONTHLY
  START_TIMESTAMP = IMMEDIATELY
  TRIGGERS
    ON 75 PERCENT DO NOTIFY
    ON 100 PERCENT DO SUSPEND;

ALTER WAREHOUSE reader_wh SET RESOURCE_MONITOR = reader_limit;
```

### Granting Database Access

```sql
USE ROLE ACCOUNTADMIN;

GRANT IMPORTED PRIVILEGES ON DATABASE shared_db TO ROLE public;
```

---

## Cost Management

### Who Pays?

- **Provider pays all costs** — Credits, storage, data transfer
- **Consumer pays nothing** — No charges to reader account users
- **Unlimited consumption risk** — Reader accounts can consume unlimited credits

### Cost Control Strategies

1. **Resource Monitors** — Set credit quotas with suspend actions
2. **Warehouse Auto-Suspend** — Minimize idle compute costs
3. **Size Right** — Use smallest warehouse size that meets needs
4. **Monitor Usage** — Query READER_ACCOUNT_USAGE views regularly

**Example resource monitor with suspend:**

```sql
CREATE RESOURCE MONITOR strict_limit
  WITH CREDIT_QUOTA = 50
  FREQUENCY = MONTHLY
  START_TIMESTAMP = IMMEDIATELY
  TRIGGERS
    ON 90 PERCENT DO SUSPEND_IMMEDIATE;
```

---

## Monitoring Reader Accounts

### Query Reader Account Usage

```sql
USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWFLAKE;
USE SCHEMA READER_ACCOUNT_USAGE;

SELECT *
FROM WAREHOUSE_METERING_HISTORY
WHERE START_TIME >= DATEADD(day, -7, CURRENT_TIMESTAMP())
ORDER BY CREDITS_USED DESC;
```

### Check Reader Account Limit

```sql
USE ROLE ACCOUNTADMIN;

SHOW MANAGED ACCOUNTS;
```

Count the results to see how many reader accounts exist (limit: 20 by default).

---

## Support and Responsibilities

### Provider Responsibilities

As the provider, you are responsible for:

- **Credit charges** — All compute and storage costs
- **First-line support** — Field questions from reader account users
- **Configuration** — Set up warehouses and resource monitors
- **Data quality** — Ensure shared data is accurate and complete
- **Access management** — Add/remove accounts from shares

### Reader Account Users

Reader account users:

- **Cannot contact Snowflake Support directly** — No licensing agreement
- **Must contact provider** — All questions and issues go to provider
- **Limited functionality** — Cannot upload or modify data

### Escalation

If you cannot resolve reader account user issues:

1. Open a support ticket through your provider account
2. Include relevant details (error messages, query IDs)
3. Receive response from Snowflake Support
4. Communicate resolution back to reader account user

---

## Troubleshooting

### "Cannot create more than 20 reader accounts"

**Cause:** Reached the default limit of 20 reader accounts per provider.

**Solution:**
- Drop unused reader accounts, OR
- Contact Snowflake Support to increase limit

### "Cannot create reader account for 7 days"

**Cause:** Recently dropped a reader account (7-day retention period).

**Solution:**
- Wait 7 days before creating a new reader account, OR
- Use an existing dropped account name, OR
- Request limit increase to avoid needing to drop accounts

### "Reader account not accessible after creation"

**Cause:** Account is still provisioning.

**Solution:**
- Wait up to 5 minutes for full provisioning
- Check URL format: `https://orgname-accountname.snowflakecomputing.com`

### "Users cannot access shared data"

**Cause:** Reader account not added to share, or privileges not granted.

**Solution:**

```sql
USE ROLE ACCOUNTADMIN;

ALTER SHARE my_share ADD ACCOUNTS = reader_acct1;

GRANT IMPORTED PRIVILEGES ON DATABASE shared_db TO ROLE public;
```

### "Unexpected high credit usage"

**Cause:** No resource monitor set, or warehouse not auto-suspending.

**Solution:**

```sql
CREATE RESOURCE MONITOR reader_limit
  WITH CREDIT_QUOTA = 100
  FREQUENCY = MONTHLY
  TRIGGERS ON 100 PERCENT DO SUSPEND;

ALTER WAREHOUSE reader_wh SET RESOURCE_MONITOR = reader_limit;
ALTER WAREHOUSE reader_wh SET AUTO_SUSPEND = 60;
```

### "Reader account users report data is outdated"

**Cause:** Provider has not refreshed the share.

**Solution:**
- For dynamic tables: Ensure refresh is running
- For materialized views: Refresh manually or set refresh schedule
- For regular tables: Provider updates are immediately visible

---

## Disaster Recovery with Reader Accounts

### Client Redirect Setup

For business continuity, create reader accounts in multiple regions:

**Step 1: Create primary reader account (Region A):**

```sql
USE ROLE ACCOUNTADMIN;

CREATE MANAGED ACCOUNT reader_primary
  ADMIN_NAME = admin,
  ADMIN_PASSWORD = '<password>',
  TYPE = READER;
```

**Step 2: Create secondary reader account (Region B):**

```sql
USE ROLE ACCOUNTADMIN;

CREATE MANAGED ACCOUNT reader_secondary
  ADMIN_NAME = admin,
  ADMIN_PASSWORD = '<password>',
  TYPE = READER;
```

**Step 3: Configure client redirect:**

See `client-redirect/SKILL.md` for detailed client redirect setup.

**Step 4: In case of outage:**

Promote secondary connection to primary, clients automatically redirect to Region B.

---

## Delegating Reader Account Management

### Grant CREATE ACCOUNT Privilege

Allow other roles to create and manage reader accounts:

```sql
USE ROLE ACCOUNTADMIN;

GRANT CREATE ACCOUNT ON ACCOUNT TO ROLE data_steward;
```

**Users with data_steward role can now:**
- Create reader accounts
- Drop reader accounts they created
- View reader accounts they own

---

## Key Concepts

### Reader Account vs Regular Account

| Feature | Reader Account | Regular Account |
|---------|----------------|-----------------|
| **Cost to consumer** | Free | Pay-as-you-go |
| **Licensing** | Not required | Required |
| **Data upload** | Not allowed | Allowed |
| **Data sharing** | Cannot share | Can share |
| **Support** | Via provider | Direct Snowflake |
| **Management** | By provider | Self-managed |
| **Credit charges** | To provider | To consumer |

### Reader Account Naming

- Must be unique within your organization
- Cannot reuse name for 7 days after dropping
- Use descriptive names (e.g., `customer_abc_reporting`)
- Account URL: `https://orgname-accountname.snowflakecomputing.com`

### Reader Account Limits

| Limit Type | Default | How to Increase |
|------------|---------|-----------------|
| Total reader accounts | 20 | Contact Snowflake Support |
| Credits per reader account | Unlimited | Set resource monitors |
| Re-creation after drop | 7 days | Wait or contact support |

---

## Related Skills

- **Account lifecycle** → See `account-lifecycle/SKILL.md` for regular account operations
- **Data sharing** → See Snowflake documentation for share creation and management
- **Client redirect** → See `client-redirect/SKILL.md` for failover setup
- **Resource monitors** → See Snowflake documentation for credit control
