# Organization Database Golden Queries

Verified SQL patterns for common Organization Database operations.

**Note**: Basic tag CRUD operations use standard Snowflake tag syntax. See [Object Tagging](https://docs.snowflake.com/en/user-guide/object-tagging) for general tag management patterns.

## Tag Management (Organization Account)

### Create Org Tags

```sql
-- With allowed values (recommended)
CREATE TAG ORGANIZATION$DB.TAGS.COST_CENTER
  ALLOWED_VALUES 'Marketing', 'Sales', 'Finance', 'Engineering'
  COMMENT = 'Cost center classification';

-- Without constraints
CREATE TAG ORGANIZATION$DB.TAGS.PROJECT
  COMMENT = 'Project identifier';

-- In custom schema
CREATE SCHEMA IF NOT EXISTS ORGANIZATION$DB.GOVERNANCE;
CREATE TAG ORGANIZATION$DB.GOVERNANCE.DATA_CLASSIFICATION
  ALLOWED_VALUES 'Public', 'Internal', 'Confidential'
  COMMENT = 'Data sensitivity classification';
```

### Modify Org Tags

```sql
-- Add allowed values
ALTER TAG ORGANIZATION$DB.TAGS.COST_CENTER 
  ADD ALLOWED_VALUES 'Operations', 'IT';

-- Remove allowed values
ALTER TAG ORGANIZATION$DB.TAGS.COST_CENTER 
  DROP ALLOWED_VALUES 'IT';

-- Update comment
ALTER TAG ORGANIZATION$DB.TAGS.PROJECT 
  SET COMMENT = 'Updated description';

-- Remove constraints
ALTER TAG ORGANIZATION$DB.TAGS.PROJECT 
  UNSET ALLOWED_VALUES;
```

### View Org Tags

```sql
-- All tags in org DB
SHOW TAGS IN DATABASE ORGANIZATION$DB;

-- Specific schema
SHOW TAGS IN SCHEMA ORGANIZATION$DB.TAGS;

-- Specific tag with details
SHOW TAGS LIKE 'COST_CENTER' IN SCHEMA ORGANIZATION$DB.TAGS;
```

### Drop Org Tags

```sql
DROP TAG ORGANIZATION$DB.TAGS.COST_CENTER;

-- With IF EXISTS
DROP TAG IF EXISTS ORGANIZATION$DB.TAGS.PROJECT;
```

## Tag Application (Any Account)

### Apply Tags to Resources

```sql
-- Single tag to warehouse
ALTER WAREHOUSE ANALYTICS_WH 
  SET TAG ORGANIZATION$DB.TAGS.COST_CENTER = 'Marketing';

-- Multiple tags
ALTER WAREHOUSE ANALYTICS_WH 
  SET TAG 
    ORGANIZATION$DB.TAGS.COST_CENTER = 'Marketing',
    ORGANIZATION$DB.TAGS.PROJECT = 'Q1_Campaign';

-- To other objects
ALTER DATABASE PROD_DB SET TAG ORGANIZATION$DB.TAGS.COST_CENTER = 'Sales';
ALTER SCHEMA PROD_DB.PUBLIC SET TAG ORGANIZATION$DB.TAGS.PROJECT = 'Analytics';
ALTER TABLE PROD_DB.PUBLIC.ORDERS SET TAG ORGANIZATION$DB.TAGS.DATA_CLASSIFICATION = 'Confidential';
ALTER USER john_doe SET TAG ORGANIZATION$DB.TAGS.COST_CENTER = 'Finance';

-- Remove tag
ALTER WAREHOUSE ANALYTICS_WH UNSET TAG ORGANIZATION$DB.TAGS.COST_CENTER;
```

## Tag Discovery & Reporting

### View Tagged Resources (Account-Level)

```sql
-- Requires warehouse

-- All org-tagged resources in current account
SELECT 
  OBJECT_NAME,
  DOMAIN as object_type,
  TAG_NAME,
  TAG_VALUE,
  TAG_APPLIED_ON
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE TAG_DATABASE = 'ORGANIZATION$DB'
ORDER BY TAG_NAME, TAG_VALUE;

-- Count by tag
SELECT 
  TAG_NAME,
  TAG_VALUE,
  DOMAIN,
  COUNT(*) as object_count
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE TAG_DATABASE = 'ORGANIZATION$DB' AND TAG_DELETED_ON IS NULL
GROUP BY 1, 2, 3
ORDER BY TAG_NAME, object_count DESC;

-- Warehouses by cost center
SELECT 
  OBJECT_NAME as warehouse_name,
  TAG_VALUE as cost_center
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE TAG_DATABASE = 'ORGANIZATION$DB'
  AND TAG_NAME = 'COST_CENTER'
  AND DOMAIN = 'WAREHOUSE'
  AND TAG_DELETED_ON IS NULL
ORDER BY cost_center;

-- Find untagged warehouses
SELECT WAREHOUSE_NAME
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSES
WHERE DELETED IS NULL
  AND WAREHOUSE_NAME NOT IN (
    SELECT OBJECT_NAME
    FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
    WHERE TAG_DATABASE = 'ORGANIZATION$DB'
      AND TAG_NAME = 'COST_CENTER'
      AND DOMAIN = 'WAREHOUSE'
      AND TAG_DELETED_ON IS NULL
  );
```

## Organization-Wide Queries (GLOBALORGADMIN)

### Tag Usage Across All Accounts

```sql
-- Requires GLOBALORGADMIN and warehouse

-- Tag usage by account
SELECT 
  ACCOUNT_NAME,
  TAG_NAME,
  TAG_VALUE,
  DOMAIN,
  COUNT(*) as object_count
FROM SNOWFLAKE.ORGANIZATION_USAGE.TAG_REFERENCES
WHERE TAG_DATABASE = 'ORGANIZATION$DB' AND TAG_DELETED_ON IS NULL
GROUP BY 1, 2, 3, 4
ORDER BY ACCOUNT_NAME, TAG_NAME;

-- Tag adoption summary
SELECT 
  TAG_NAME,
  COUNT(DISTINCT ACCOUNT_NAME) as accounts_using_tag,
  COUNT(DISTINCT TAG_VALUE) as unique_values,
  COUNT(*) as total_tagged_objects
FROM SNOWFLAKE.ORGANIZATION_USAGE.TAG_REFERENCES
WHERE TAG_DATABASE = 'ORGANIZATION$DB' AND TAG_DELETED_ON IS NULL
GROUP BY TAG_NAME
ORDER BY accounts_using_tag DESC;

-- Accounts not using org tags
WITH tagged_accounts AS (
  SELECT DISTINCT ACCOUNT_NAME
  FROM SNOWFLAKE.ORGANIZATION_USAGE.TAG_REFERENCES
  WHERE TAG_DATABASE = 'ORGANIZATION$DB'
)
SELECT a.ACCOUNT_NAME, a.REGION, a.EDITION
FROM SNOWFLAKE.ORGANIZATION_USAGE.ACCOUNTS a
LEFT JOIN tagged_accounts ta ON a.ACCOUNT_NAME = ta.ACCOUNT_NAME
WHERE ta.ACCOUNT_NAME IS NULL AND a.DELETED_ON IS NULL;

-- Cost center distribution
SELECT 
  TAG_VALUE as cost_center,
  COUNT(DISTINCT ACCOUNT_NAME) as accounts,
  COUNT(CASE WHEN DOMAIN = 'WAREHOUSE' THEN 1 END) as warehouses,
  COUNT(CASE WHEN DOMAIN = 'DATABASE' THEN 1 END) as databases
FROM SNOWFLAKE.ORGANIZATION_USAGE.TAG_REFERENCES
WHERE TAG_DATABASE = 'ORGANIZATION$DB'
  AND TAG_NAME = 'COST_CENTER'
  AND TAG_DELETED_ON IS NULL
GROUP BY cost_center
ORDER BY accounts DESC;
```

## Database Discovery

```sql
-- Check org DB existence
SHOW DATABASES LIKE 'ORGANIZATION$DB';

-- Database metadata
SELECT DATABASE_NAME, DATABASE_OWNER, CREATED
FROM SNOWFLAKE.INFORMATION_SCHEMA.DATABASES
WHERE DATABASE_NAME = 'ORGANIZATION$DB';

-- View schemas
SHOW SCHEMAS IN DATABASE ORGANIZATION$DB;

-- Count tags by schema
-- Requires warehouse
SELECT TAG_SCHEMA, COUNT(*) as tag_count
FROM SNOWFLAKE.ACCOUNT_USAGE.TAGS
WHERE TAG_DATABASE = 'ORGANIZATION$DB' AND DELETED IS NULL
GROUP BY TAG_SCHEMA;
```

## Troubleshooting Queries

### Verify Tag Allowed Values

```sql
SHOW TAGS LIKE 'COST_CENTER' IN SCHEMA ORGANIZATION$DB.TAGS;
-- Check 'allowed_values' column
```

### Find Tags on Specific Resource

```sql
-- Requires warehouse
SELECT TAG_NAME, TAG_VALUE, TAG_APPLIED_ON
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE OBJECT_NAME = 'ANALYTICS_WH'
  AND DOMAIN = 'WAREHOUSE'
  AND TAG_DATABASE = 'ORGANIZATION$DB'
ORDER BY TAG_NAME;
```

### Check Tag History (Deleted Tags)

```sql
-- Requires warehouse
SELECT TAG_NAME, TAG_VALUE, OBJECT_NAME, TAG_APPLIED_ON, TAG_DELETED_ON
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE TAG_DATABASE = 'ORGANIZATION$DB'
  AND TAG_DELETED_ON IS NOT NULL
  AND TAG_DELETED_ON >= DATEADD(day, -30, CURRENT_TIMESTAMP())
ORDER BY TAG_DELETED_ON DESC;
```

### Identify Name Conflicts (Org vs Account Tags)

```sql
-- Requires warehouse
-- Find resources with same-named org and account tags
WITH org_tags AS (
  SELECT OBJECT_NAME, DOMAIN, TAG_NAME
  FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
  WHERE TAG_DATABASE = 'ORGANIZATION$DB' AND TAG_DELETED_ON IS NULL
),
account_tags AS (
  SELECT OBJECT_NAME, DOMAIN, TAG_NAME
  FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
  WHERE TAG_DATABASE != 'ORGANIZATION$DB' AND TAG_DELETED_ON IS NULL
)
SELECT o.OBJECT_NAME, o.DOMAIN, o.TAG_NAME
FROM org_tags o
INNER JOIN account_tags a 
  ON o.OBJECT_NAME = a.OBJECT_NAME 
  AND o.DOMAIN = a.DOMAIN 
  AND o.TAG_NAME = a.TAG_NAME;
```

## Common Patterns

### Governance Check: Missing Required Tags

```sql
-- Requires warehouse
-- Warehouses without required cost center tag
SELECT w.WAREHOUSE_NAME, w.CREATED_ON
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSES w
LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES tr
  ON w.WAREHOUSE_NAME = tr.OBJECT_NAME
  AND tr.DOMAIN = 'WAREHOUSE'
  AND tr.TAG_DATABASE = 'ORGANIZATION$DB'
  AND tr.TAG_NAME = 'COST_CENTER'
  AND tr.TAG_DELETED_ON IS NULL
WHERE w.DELETED IS NULL AND tr.OBJECT_NAME IS NULL;
```

### Cost Attribution: Resources by Cost Center and Project

```sql
-- Requires warehouse
SELECT 
  tr1.OBJECT_NAME as warehouse,
  tr1.TAG_VALUE as cost_center,
  tr2.TAG_VALUE as project
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES tr1
LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES tr2
  ON tr1.OBJECT_NAME = tr2.OBJECT_NAME
  AND tr1.DOMAIN = tr2.DOMAIN
  AND tr2.TAG_DATABASE = 'ORGANIZATION$DB'
  AND tr2.TAG_NAME = 'PROJECT'
  AND tr2.TAG_DELETED_ON IS NULL
WHERE tr1.TAG_DATABASE = 'ORGANIZATION$DB'
  AND tr1.TAG_NAME = 'COST_CENTER'
  AND tr1.DOMAIN = 'WAREHOUSE'
  AND tr1.TAG_DELETED_ON IS NULL;
```

### Migration Audit: Find Account Tags to Migrate

```sql
-- Requires warehouse
-- Account-level tags with high usage (candidates for org tags)
SELECT 
  TAG_NAME,
  COUNT(DISTINCT TAG_DATABASE || '.' || TAG_SCHEMA) as schemas_with_tag,
  COUNT(*) as total_usage
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE TAG_DATABASE != 'ORGANIZATION$DB' AND TAG_DELETED_ON IS NULL
GROUP BY TAG_NAME
HAVING COUNT(*) > 10
ORDER BY total_usage DESC
LIMIT 20;
```

## Usage Notes

### Query Performance

- **SHOW commands**: Fast, no warehouse needed
- **ACCOUNT_USAGE queries**: Require warehouse, up to 2-hour latency
- **ORGANIZATION_USAGE queries**: Require warehouse and GLOBALORGADMIN, up to 2-hour latency

### Best Practices

1. Use SHOW commands for discovery (fast, no compute cost)
2. Use TAG_REFERENCES for reporting (structured, queryable)
3. Filter on `TAG_DATABASE = 'ORGANIZATION$DB'` to isolate org tags
4. Check `TAG_DELETED_ON IS NULL` to exclude deleted tags
5. Include `ACCOUNT_NAME` in org-wide queries for multi-account analysis
