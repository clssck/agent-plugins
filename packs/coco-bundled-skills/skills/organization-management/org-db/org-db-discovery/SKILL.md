---
name: organization-database-discovery
description: "Discover and verify Organization Database status, view org DB metadata, check replication status. Use when the user asks about: what is org db, show organization database, org db status, view org db, check org db, ORGANIZATION$DB, is org db enabled, organization database replication, org db info."
parent_skill: organization-database
---

# Organization Database Discovery

Discover, verify, and understand the Organization Database (Org DB) in your environment.

## When to Use

- **Check if org DB exists**: "Is organization database enabled?", "Do we have org DB?"
- **View org DB status**: "Show me the organization database", "What's in ORGANIZATION$DB?"
- **Understand structure**: "What schemas are in org DB?", "How is org DB organized?"
- **Verify replication**: "Is org DB replicated?", "Check org DB replication status"

## When NOT to Use

- **Create/manage org tags** — Use `org-tags/SKILL.md`
- **Account operations** — Use parent `organization-management` skills

## Setup

1. **Load** `../references/org-db-concepts.md`: Core concepts
2. **Load** `../../references/global_guardrails.md`: Role and warehouse management

## Role & Warehouse Requirements

**Roles**: ACCOUNTADMIN or GLOBALORGADMIN (GLOBALORGADMIN for org-wide views)

**Warehouse**: Not required for SHOW commands; required for view queries

## Workflow

Follow `global_guardrails.md` for role context:

```sql
SELECT CURRENT_ROLE();
USE ROLE ACCOUNTADMIN;
USE ROLE GLOBALORGADMIN;
```

Use ACCOUNTADMIN for account-level operations or GLOBALORGADMIN for org-wide visibility.

### Detect User Intent

| Intent | Action |
|--------|--------|
| "Does org DB exist?" | **Check Org DB Existence** |
| "Show me org DB" | **View Org DB Details** |
| "What's in org DB?" | **View Org DB Contents** |
| "Is it replicated?" | **Check Replication Status** |
| "Explain org DB" | **Explain Org DB Concept** |

---

## Check Org DB Existence

```sql
SHOW DATABASES LIKE 'ORGANIZATION$DB';
```

**Results**:
- Rows returned: Org DB exists and accessible
- No rows: Not provisioned or role lacks USAGE privilege

If no rows, try ACCOUNTADMIN or GLOBALORGADMIN role.

---

## View Org DB Details

```sql
SHOW DATABASES LIKE 'ORGANIZATION$DB';

SELECT DATABASE_NAME, DATABASE_OWNER, CREATED
FROM SNOWFLAKE.INFORMATION_SCHEMA.DATABASES
WHERE DATABASE_NAME = 'ORGANIZATION$DB';
```

**Key properties**: Reserved name (ORGANIZATION$DB), owned by SYSTEM (child) or database role (org account)

**In child accounts**: Database is read-only. Users can view and apply org tags but cannot modify tag definitions.

---

## View Org DB Contents

### View Schemas

```sql
SHOW SCHEMAS IN DATABASE ORGANIZATION$DB;
```

Default schema: **TAGS** (for org tags)

### View Tags

```sql
SHOW TAGS IN DATABASE ORGANIZATION$DB;

SHOW TAGS IN SCHEMA ORGANIZATION$DB.TAGS;
```

### Count Objects

Requires warehouse:

```sql
SELECT TAG_SCHEMA, COUNT(*) as tag_count
FROM SNOWFLAKE.ACCOUNT_USAGE.TAGS
WHERE TAG_DATABASE = 'ORGANIZATION$DB' AND DELETED IS NULL
GROUP BY TAG_SCHEMA;
```

---

## Check Replication Status

### Replication Behavior

Explain to user:

> **Organization Database Replication**
>
> - **Automatic**: No configuration needed
> - **Frequency**: TBD (pending implementation details)
> - **Scope**: All accounts in organization
> - **Content**: Tags and definitions
> - **Cost**: Zero

### Verify in Child Account

```sql
SHOW DATABASES LIKE 'ORGANIZATION$DB';
SHOW TAGS IN DATABASE ORGANIZATION$DB;
```

### Organization-Wide View (GLOBALORGADMIN)

Requires warehouse:

```sql
SELECT DISTINCT ACCOUNT_NAME
FROM SNOWFLAKE.ORGANIZATION_USAGE.TAG_REFERENCES
WHERE TAG_DATABASE = 'ORGANIZATION$DB'
ORDER BY ACCOUNT_NAME;

SELECT COUNT(DISTINCT ACCOUNT_NAME) as accounts_with_org_tags
FROM SNOWFLAKE.ORGANIZATION_USAGE.TAG_REFERENCES
WHERE TAG_DATABASE = 'ORGANIZATION$DB';
```

**Note**: Above shows accounts with applied tags. All accounts receive ORGANIZATION$DB via replication.

---

## Explain Org DB Concept

When user asks "what is org DB":

> # What is Organization Database?
>
> ORGANIZATION$DB is a special database serving as the **single source of truth for organization-wide objects**.
>
> ## Key Features
>
> **Automatic Provisioning**: Created automatically when organization is enrolled
>
> **Centralized Management**: Define once in org account, replicate to all child accounts
>
> **Read-Only in Child Accounts**: Full access in org account (GLOBALORGADMIN), read-only in child accounts
>
> **Zero Cost**: No storage or replication charges
>
> **Current Scope**: Organization Tags for consistent classification across accounts
>
> ## Organization Tags
>
> Create tags once in ORGANIZATION$DB.TAGS, automatically replicate to all accounts, apply to resources for consistent cost center, project, or environment tagging.
>
> ### In Organization Account (GLOBALORGADMIN)
> ```sql
> CREATE TAG ORGANIZATION$DB.TAGS.COST_CENTER
>   ALLOWED_VALUES 'Marketing', 'Sales', 'Finance';
> ```
>
> ### In Child Accounts (ACCOUNTADMIN)
> ```sql
> SHOW TAGS IN DATABASE ORGANIZATION$DB;
> ALTER WAREHOUSE my_wh SET TAG ORGANIZATION$DB.TAGS.COST_CENTER = 'Marketing';
> ```
>
> ## Benefits
>
> 1. Consistency across all accounts
> 2. Centralized governance
> 3. Define once, use everywhere
> 4. Accurate cross-account cost tracking
> 5. Zero cost

---

## Example Workflows

### First-Time Discovery

```sql
USE ROLE ACCOUNTADMIN;
SHOW DATABASES LIKE 'ORGANIZATION$DB';
SHOW SCHEMAS IN DATABASE ORGANIZATION$DB;
SHOW TAGS IN DATABASE ORGANIZATION$DB;

SELECT OBJECT_NAME, TAG_NAME, TAG_VALUE
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE TAG_DATABASE = 'ORGANIZATION$DB'
LIMIT 10;
```

### Organization-Wide Audit (GLOBALORGADMIN)

```sql
USE ROLE GLOBALORGADMIN;

SHOW TAGS IN DATABASE ORGANIZATION$DB;

SELECT ACCOUNT_NAME, TAG_NAME, TAG_VALUE, COUNT(*) as object_count
FROM SNOWFLAKE.ORGANIZATION_USAGE.TAG_REFERENCES
WHERE TAG_DATABASE = 'ORGANIZATION$DB'
GROUP BY 1, 2, 3
ORDER BY ACCOUNT_NAME;
```

The last query requires warehouse.

---

## Troubleshooting

### "Database 'ORGANIZATION$DB' does not exist"

**Cause**: Organization not enrolled.

**Resolution**: For Private Preview, contact Snowflake support. Post-Public Preview, new org accounts get Org DB automatically.

### "No rows returned" when showing org DB

**Cause**: Role lacks USAGE privilege.

**Resolution**: Use ACCOUNTADMIN or GLOBALORGADMIN.

### Cannot see org tags created recently

**Cause**: Replication in progress.

**Resolution**: Wait a few minutes. If still not visible after 10 minutes, verify:
1. Tag created successfully in org account
2. Current account is part of organization
3. Replication functioning normally

---

## Output Format

### Existence Check

```
✅ Organization Database: ENABLED

Database: ORGANIZATION$DB
Schemas: 1 (TAGS)
Org Tags: 3
```

### Content Summary

| Schema | Object Type | Count |
|--------|-------------|-------|
| TAGS | Tags | 3 |

### Replication Status

```
🔄 Replication: ACTIVE

Target: All organization accounts
Accounts Using Tags: 12
Total Tagged Objects: 487
```

---

## Official Documentation

- [SHOW DATABASES](https://docs.snowflake.com/en/sql-reference/sql/show-databases)
- [INFORMATION_SCHEMA.DATABASES](https://docs.snowflake.com/en/sql-reference/info-schema/databases)
