---
name: organization-database-tags
description: "Create and manage organization-level tags in ORGANIZATION$DB for centralized governance. Use when the user asks about: create org tag, organization tag, centralized tag, replicated tag, manage org tags, alter org tag, drop org tag, apply org tag to warehouse, apply org tag to database, tag resources with org tag, ORGANIZATION$DB.TAGS, allowed values for org tag, org tag replication."
parent_skill: organization-database
---

# Organization Tags

Create, manage, and apply organization-level tags for centralized governance across all accounts.

## When to Use

- **Create org tags**: "Create an organization tag for cost center", "Define a centralized tag"
- **Modify org tags**: "Add allowed values to org tag", "Change org tag definition"
- **Apply org tags**: "Tag my warehouse with org tag", "Apply cost center tag to database"
- **View org tags**: "Show me all org tags", "What org tags are available?"
- **Drop org tags**: "Remove org tag", "Delete organization tag"

## When NOT to Use

- **Account-level tags** — Use standard tag management (not this skill)
- **Organization budgets** — Coming in future release

## Setup

1. **Load** `../references/org-db-concepts.md`: Core concepts about Organization Database
2. **Load** `../references/golden-queries.md`: Verified SQL patterns
3. **Load** `../../references/global_guardrails.md`: Role and warehouse management

## Role & Permission Requirements

| Operation | Organization Account | Child Accounts |
|-----------|---------------------|----------------|
| Create/Alter/Drop org tags | GLOBALORGADMIN | Not allowed (read-only) |
| View org tags | GLOBALORGADMIN | ACCOUNTADMIN or delegated |
| Apply org tags to resources | GLOBALORGADMIN | ACCOUNTADMIN or delegated |

**Warehouse**: Not required for SHOW commands; required for TAG_REFERENCES queries.

## Workflow

### Step 1: Set Role Context

Follow `global_guardrails.md` role context rules:

```sql
SELECT CURRENT_ROLE();

USE ROLE GLOBALORGADMIN;
USE ROLE ACCOUNTADMIN;
```

Use GLOBALORGADMIN for tag management in org account, or ACCOUNTADMIN for applying tags in child accounts.

### Step 2: Detect User Intent

| Intent | Action |
|--------|--------|
| Create tag | **Create Org Tag** section |
| Modify tag | **Modify Org Tag** section |
| Apply tag | **Apply Org Tag** section |
| View tags | **View Org Tags** section |
| Drop tag | **Drop Org Tag** section |

---

## Create Org Tag

**Prerequisite**: GLOBALORGADMIN in organization account

### Gather Information

Ask user for:
1. Tag name (e.g., COST_CENTER, PROJECT)
2. Schema (default: TAGS)
3. Allowed values or accept any string?
4. Optional comment

### Create Tag

Create with allowed values (recommended):

```sql
CREATE TAG ORGANIZATION$DB.TAGS.COST_CENTER
  ALLOWED_VALUES 'Marketing', 'Sales', 'Finance', 'Engineering'
  COMMENT = 'Cost center classification';
```

Create without constraints to accept any string:

```sql
CREATE TAG ORGANIZATION$DB.TAGS.PROJECT
  COMMENT = 'Project identifier';
```

Create in custom schema:

```sql
CREATE SCHEMA IF NOT EXISTS ORGANIZATION$DB.GOVERNANCE;
CREATE TAG ORGANIZATION$DB.GOVERNANCE.DATA_CLASSIFICATION
  ALLOWED_VALUES 'Public', 'Internal', 'Confidential'
  COMMENT = 'Data sensitivity classification';
```

### Verify & Explain

```sql
SHOW TAGS IN DATABASE ORGANIZATION$DB;
```

Inform user: Tag will replicate to all accounts automatically. Child accounts can apply it (read-only), changes propagate automatically.

---

## Modify Org Tag

**Prerequisite**: GLOBALORGADMIN in organization account

Add allowed values:

```sql
ALTER TAG ORGANIZATION$DB.TAGS.COST_CENTER 
  ADD ALLOWED_VALUES 'Operations', 'IT';
```

**WARNING**: Removing allowed values invalidates existing assignments with those values:

```sql
ALTER TAG ORGANIZATION$DB.TAGS.COST_CENTER 
  DROP ALLOWED_VALUES 'IT';
```

Update comment:

```sql
ALTER TAG ORGANIZATION$DB.TAGS.COST_CENTER 
  SET COMMENT = 'Updated description';
```

Remove all constraints:

```sql
ALTER TAG ORGANIZATION$DB.TAGS.PROJECT 
  UNSET ALLOWED_VALUES;
```

---

## Apply Org Tag

**Available to**: GLOBALORGADMIN or ACCOUNTADMIN in any account

### Check Available Tags & Values

**CRITICAL**: Always check allowed values before applying tags to avoid errors.

```sql
SHOW TAGS IN DATABASE ORGANIZATION$DB;

SHOW TAGS LIKE 'COST_CENTER' IN SCHEMA ORGANIZATION$DB.TAGS;
```

### Apply to Resources

Apply single tag to warehouse:

```sql
ALTER WAREHOUSE ANALYTICS_WH 
  SET TAG ORGANIZATION$DB.TAGS.COST_CENTER = 'Marketing';
```

Apply multiple tags at once:

```sql
ALTER WAREHOUSE ANALYTICS_WH 
  SET TAG 
    ORGANIZATION$DB.TAGS.COST_CENTER = 'Marketing',
    ORGANIZATION$DB.TAGS.PROJECT = 'Q1Campaign';
```

Apply to other object types:

```sql
ALTER DATABASE PROD_DB 
  SET TAG ORGANIZATION$DB.TAGS.COST_CENTER = 'Sales';

ALTER SCHEMA PROD_DB.PUBLIC 
  SET TAG ORGANIZATION$DB.TAGS.PROJECT = 'Analytics';

ALTER TABLE PROD_DB.PUBLIC.ORDERS 
  SET TAG ORGANIZATION$DB.TAGS.DATA_CLASSIFICATION = 'Confidential';

ALTER USER john_doe 
  SET TAG ORGANIZATION$DB.TAGS.COST_CENTER = 'Finance';
```

Remove tag from resource:

```sql
ALTER WAREHOUSE ANALYTICS_WH 
  UNSET TAG ORGANIZATION$DB.TAGS.COST_CENTER;
```

---

## View Org Tags

### View Tag Definitions

```sql
SHOW TAGS IN DATABASE ORGANIZATION$DB;

SHOW TAGS LIKE 'COST_CENTER' IN SCHEMA ORGANIZATION$DB.TAGS;
```

Key columns: `name`, `database_name`, `schema_name`, `allowed_values`, `comment`, `owner`

### View Tagged Resources (Account-Level)

Requires warehouse (see `global_guardrails.md`):

```sql
SELECT 
  OBJECT_NAME,
  DOMAIN as object_type,
  TAG_NAME,
  TAG_VALUE
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE TAG_DATABASE = 'ORGANIZATION$DB'
ORDER BY TAG_NAME, TAG_VALUE;
```

### View Tagged Resources (Organization-Wide)

Requires GLOBALORGADMIN and warehouse:

Query org-wide usage:

```sql
SELECT 
  ACCOUNT_NAME,
  OBJECT_NAME,
  DOMAIN as object_type,
  TAG_NAME,
  TAG_VALUE
FROM SNOWFLAKE.ORGANIZATION_USAGE.TAG_REFERENCES
WHERE TAG_DATABASE = 'ORGANIZATION$DB'
ORDER BY ACCOUNT_NAME, TAG_NAME;
```

Summary by account:

```sql
SELECT 
  ACCOUNT_NAME,
  TAG_NAME,
  TAG_VALUE,
  COUNT(*) as object_count
FROM SNOWFLAKE.ORGANIZATION_USAGE.TAG_REFERENCES
WHERE TAG_DATABASE = 'ORGANIZATION$DB'
GROUP BY 1, 2, 3
ORDER BY ACCOUNT_NAME, object_count DESC;
```

---

## Drop Org Tag

**Prerequisite**: GLOBALORGADMIN in organization account

**⚠️ Warning**: Removes tag definition and all assignments across all accounts.

```sql
DROP TAG ORGANIZATION$DB.TAGS.COST_CENTER;

DROP TAG IF EXISTS ORGANIZATION$DB.TAGS.PROJECT;
```

Inform user: Changes replicate automatically, all assignments removed from all accounts.

---

## Name Collisions

Org tags (ORGANIZATION$DB.TAGS.COST_CENTER) and account tags (FINANCE_DB.TAGS.COST_CENTER) are distinct due to fully qualified names. To avoid confusion, use descriptive naming and consider migrating account tags to org tags for consistency.

---

## Troubleshooting

### "Database does not exist: ORGANIZATION$DB"

**Cause**: Organization not enrolled in Organization Database.

**Resolution**: For Private Preview, contact Snowflake support. Post-Public Preview, new org accounts get Org DB automatically.

### "Insufficient privileges to operate on database ORGANIZATION$DB"

**Cause**: Wrong role.

**Resolution**: Use GLOBALORGADMIN (org account) or ACCOUNTADMIN (child account).

### "Cannot create object in read-only database"

**Cause**: Attempting to create/modify tags in child account.

**Resolution**: Manage tags from organization account with GLOBALORGADMIN.

### "Value 'XYZ' is not allowed by the specified allowed_values"

**Cause**: Tag has allowed values constraint.

**Resolution**: Check allowed values (`SHOW TAGS LIKE ...`) and use valid value, or have GLOBALORGADMIN add the value.

### Tag changes not showing in child accounts

**Cause**: Replication in progress.

**Resolution**: Wait a few minutes and retry.

---

## Output Format

### Tag Creation Confirmation

| Property | Value |
|----------|-------|
| Tag Name | ORGANIZATION$DB.TAGS.COST_CENTER |
| Allowed Values | Marketing, Sales, Finance |
| Replication | Automatic to all accounts |
| Read-Only | Yes (in child accounts) |

### Tag Application Confirmation

```
✅ Tag applied successfully!

Resource: WAREHOUSE ANALYTICS_WH
Tag: ORGANIZATION$DB.TAGS.COST_CENTER = 'Marketing'
```

---

## Official Documentation

- [CREATE TAG](https://docs.snowflake.com/en/sql-reference/sql/create-tag)
- [ALTER TAG](https://docs.snowflake.com/en/sql-reference/sql/alter-tag)
- [Object Tagging](https://docs.snowflake.com/en/user-guide/object-tagging)
- [TAG_REFERENCES View](https://docs.snowflake.com/en/sql-reference/account-usage/tag_references)
