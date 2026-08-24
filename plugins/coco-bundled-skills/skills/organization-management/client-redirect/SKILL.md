---
name: organization-management-client-redirect
description: "Client redirect and connection management — redirect client connections for disaster recovery and account migration. Use when: connection url, client redirect, create connection, primary connection, secondary connection, failover setup, disaster recovery, account migration, business continuity, connection vs account locator, redirect client connections, promote connection, connection url structure, connection naming, drop connection, show connections, failover scenario."
parent_skill: organization-management
---

# Client Redirect & Connection Management

Redirect client connections to accounts in different regions for disaster recovery — without changing application connection settings.

## When to Use

- "Set up disaster recovery"
- "Create connection URL"
- "How do I failover to another region?"
- "Connection URL vs account locator"
- "Business continuity setup"

## Prerequisites

- **Role Required:** ACCOUNTADMIN
- **Account Requirements:** Accounts in different regions
- **Network Requirements:** DNS CNAME record if using private connectivity

**Note:** All examples assume ACCOUNTADMIN role.

---

## What is Client Redirect?

**Client Redirect** enables redirecting connections to accounts in different regions without changing application settings. When an outage occurs, promote a secondary connection to primary, and clients automatically connect to the failover account.

**Benefits:**
- Zero client changes
- Instant failover
- Business continuity
- Simplified migrations

**How it works:**
1. Create connection objects in two accounts (different regions)
2. Designate primary connection
3. Clients connect using connection URL
4. On outage: Promote secondary to primary
5. Clients automatically redirect

---

## Connection URL Structure

**Connection URL format:**

```
https://organization_name-connection_name.snowflakecomputing.com
```

**Example:** `https://myorg-prod_connection.snowflakecomputing.com`

**Key points:**
- URL does not specify account
- Account determined by which connection is primary
- Same URL works after failover

### Connection URL vs Account Identifiers

| Identifier | Format | Use Case |
|------------|--------|----------|
| **Connection URL** | `org-connection.snowflakecomputing.com` | Client redirect, failover |
| **Account URL** | `org-account.snowflakecomputing.com` | Direct account access |
| **Account Locator** | `AB12345.snowflakecomputing.com` | Legacy |
| **Account Name** | `org.account` | SQL commands |

---

## Creating Connections

**Primary connection syntax:**

```sql
CREATE CONNECTION [ IF NOT EXISTS ] <name>
  [ COMMENT = '<string>' ];
```

**Secondary connection syntax:**

```sql
CREATE CONNECTION [ IF NOT EXISTS ] <name>
  AS REPLICA OF <org_name>.<account_name>.<name>
  [ COMMENT = '<string>' ];
```

**Naming requirements:**
- Start with letter
- Letters, numbers, underscores only
- Primary: Unique across connections AND accounts
- Secondary: Must match primary name

**Example:**

```sql
CREATE CONNECTION prod_connection
  COMMENT = 'Primary production connection';
```

**Connection URL:** `https://myorg-prod_connection.snowflakecomputing.com`

**Create secondary (in different account):**

```sql
CREATE CONNECTION prod_connection
  AS REPLICA OF myorg.account_east.prod_connection;
```

---

## Managing Connections

### View Connections

```sql
SHOW CONNECTIONS;
```

**Key columns:** `name`, `is_primary`, `primary`, `snowflake_region`

### Promote Secondary (Failover)

```sql
ALTER CONNECTION prod_connection PRIMARY;
```

**Effect:** This connection becomes active primary, clients redirect to this account.

### Demote to Secondary

```sql
ALTER CONNECTION prod_connection SECONDARY;
```

### Rename Connection

```sql
ALTER CONNECTION old_name RENAME TO new_name;
```

**Important:** Rename all secondary replicas to match if renaming primary.

### Drop Connection

```sql
DROP CONNECTION prod_connection;
```

**Warning:** Clients using this URL cannot connect. Drop secondary connections before primary.

---

## Disaster Recovery Setup

**Complete DR workflow:**

**Step 1: Create accounts in different regions (as GLOBALORGADMIN)**

```sql
CREATE ACCOUNT account_east
  ADMIN_NAME = admin
  ADMIN_PASSWORD = '<password>'
  EMAIL = 'admin@myorg.com'
  EDITION = enterprise
  REGION = aws_us_east_1;

CREATE ACCOUNT account_west
  ADMIN_NAME = admin
  ADMIN_PASSWORD = '<password>'
  EMAIL = 'admin@myorg.com'
  EDITION = enterprise
  REGION = aws_us_west_2;
```

**Step 2: Create primary connection in account_east**

```sql
CREATE CONNECTION prod_conn;
```

**Step 3: Create secondary connection in account_west**

```sql
CREATE CONNECTION prod_conn
  AS REPLICA OF myorg.account_east.prod_conn;
```

**Step 4: Configure clients**

Update applications to use: `https://myorg-prod_conn.snowflakecomputing.com`

**Step 5: Set up replication (optional)**

Enable data replication between accounts:

```sql
SELECT SYSTEM$GLOBAL_ACCOUNT_SET_PARAMETER('myorg.account_east', 'ENABLE_ACCOUNT_DATABASE_REPLICATION', 'true');
SELECT SYSTEM$GLOBAL_ACCOUNT_SET_PARAMETER('myorg.account_west', 'ENABLE_ACCOUNT_DATABASE_REPLICATION', 'true');
```

Create replication groups to sync data.

### Failover Scenario

**When outage occurs:**

Log into secondary account (account_west):

```sql
ALTER CONNECTION prod_conn PRIMARY;
```

Verify:

```sql
SHOW CONNECTIONS;
```

Check `is_primary` is TRUE.

**Result:** Clients automatically connect to account_west.

### Failback After Recovery

Log into original primary (account_east):

```sql
ALTER CONNECTION prod_conn PRIMARY;
```

**Result:** Clients automatically connect back to account_east.

---

## Client Redirect for Reader Accounts

**Step 1: Create primary reader account**

```sql
CREATE MANAGED ACCOUNT reader_east
  ADMIN_NAME = admin,
  ADMIN_PASSWORD = '<password>',
  TYPE = READER;

CREATE CONNECTION reader_conn;
```

**Step 2: Create secondary reader account**

```sql
CREATE MANAGED ACCOUNT reader_west
  ADMIN_NAME = admin,
  ADMIN_PASSWORD = '<password>',
  TYPE = READER;

CREATE CONNECTION reader_conn
  AS REPLICA OF myorg.reader_east.reader_conn;
```

**Step 3: Share data with both**

```sql
ALTER SHARE my_share ADD ACCOUNTS = reader_east, reader_west;
```

**Step 4: Clients use connection URL**

```
https://myorg-reader_conn.snowflakecomputing.com
```

**Step 5: Failover when needed**

```sql
ALTER CONNECTION reader_conn PRIMARY;
```

---

## Private Connectivity

If using PrivateLink, network administrator must create DNS CNAME record:

**Example CNAME:**

```
myorg-prod_conn.snowflakecomputing.com → myorg-myaccount.privatelink.snowflakecomputing.com
```

After failover, update CNAME to point to new account's private endpoint.

---

## Troubleshooting

### "Connection name already exists"

**Cause:** Name conflicts with existing connection or account.

**Solution:** Choose different name. Must be unique across connections AND accounts.

### "Cannot create secondary - name mismatch"

**Cause:** Secondary name does not match primary.

**Solution:** Ensure both connections have identical names.

### "Clients cannot connect after failover"

**Cause:** DNS propagation delay or client DNS caching.

**Solution:** Wait a few minutes for DNS propagation, clear client DNS cache, restart clients.

### "Cannot promote secondary"

**Cause:** Connection not properly configured as replica.

**Solution:** Run `SHOW CONNECTIONS` and verify `primary` column shows fully qualified primary name.

### "Connection URL resolves to wrong account"

**Cause:** Multiple connections with same name, or primary not set.

**Solution:** Run `SHOW CONNECTIONS` and verify only one connection has `is_primary` = TRUE.

---

## Best Practices

### Connection Naming

- Use descriptive names: `prod_connection`, `sales_app_conn`
- Avoid generic names: `conn1`, `connection`
- Document primary/secondary mappings

### High Availability

1. **Geographic diversity** — Primary and secondary in different regions
2. **Data replication** — Keep accounts in sync
3. **Regular testing** — Practice failover quarterly
4. **Monitoring** — Alert on connection and account health
5. **Documentation** — Maintain failover runbooks

### Failover Planning

- **RPO** — How much data loss acceptable?
- **RTO** — How quickly must you failover?
- **Testing** — When will you test failover?
- **Communication** — How to notify stakeholders?
- **Rollback** — How to failback after recovery?

---

## Key Concepts

- **Account** — Physical deployment in a region
- **Connection** — Logical routing object for redirect
- **Primary** — Currently active connection
- **Secondary** — Standby failover connection
- **Promotion** — Makes connection active (`ALTER CONNECTION ... PRIMARY`)
- **Demotion** — Makes connection standby (`ALTER CONNECTION ... SECONDARY`)

---

## Related Skills

- **Account lifecycle** → `account-lifecycle/SKILL.md` for creating accounts
- **Reader accounts** → `reader-accounts/SKILL.md` for reader failover
- **Replication setup** → `replication-setup/SKILL.md` for data replication
- **GLOBALORGADMIN** → `globalorgadmin/SKILL.md` for org administrator role
