# SQL Templates - Query Contacts

## Overview

This document contains SQL templates for querying contacts, generating reports, removing contacts, and managing privileges.

---

## Query Contacts

### Template 10: View Contacts for Specific Object

```sql
SELECT *
FROM TABLE(SNOWFLAKE.CORE.GET_CONTACTS('<object_name>', '<object_type>'));
```

**Example:**
```sql
SELECT *
FROM TABLE(SNOWFLAKE.CORE.GET_CONTACTS('ANALYTICS_DB.SALES.CUSTOMERS', 'TABLE'));
```

### Template 11: List All Contacts in Account

```sql
SELECT 
  contact_database,
  contact_schema,
  contact_name,
  communication_method,
  communication_value,
  created,
  last_altered
FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACTS
WHERE deleted IS NULL
ORDER BY contact_database, contact_schema, contact_name;
```

### Template 12: Find Objects with Specific Contact

```sql
SELECT 
  object_database,
  object_schema,
  object_name,
  object_domain AS object_type,
  purpose,
  is_inherited,
  parent_object_name AS inherited_from
FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES
WHERE UPPER(contact_name) = UPPER('<contact_name>')
  AND deleted IS NULL
ORDER BY object_database, object_schema, object_name;
```

**Example:**
```sql
SELECT 
  object_database,
  object_schema,
  object_name,
  object_domain AS object_type,
  purpose,
  is_inherited,
  parent_object_name AS inherited_from
FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES
WHERE UPPER(contact_name) = UPPER('data_stewards')
  AND deleted IS NULL
ORDER BY object_database, object_schema, object_name;
```

### Template 13: Find Objects WITHOUT Contacts

```sql
WITH all_objects AS (
  SELECT 
    table_catalog AS database_name,
    table_schema AS schema_name,
    table_name AS object_name,
    table_type AS object_type
  FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
  WHERE deleted IS NULL
    AND table_catalog = '<database>'
    AND table_schema = '<schema>'
),
objects_with_contacts AS (
  SELECT DISTINCT
    object_database,
    object_schema,
    object_name
  FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES
  WHERE deleted IS NULL
    AND purpose = 'STEWARD'
)
SELECT 
  ao.database_name,
  ao.schema_name,
  ao.object_name,
  ao.object_type
FROM all_objects ao
LEFT JOIN objects_with_contacts owc
  ON ao.database_name = owc.object_database
  AND ao.schema_name = owc.object_schema
  AND ao.object_name = owc.object_name
WHERE owc.object_name IS NULL
ORDER BY ao.database_name, ao.schema_name, ao.object_name;
```

---

## Generate Reports

### Template 14: Contact Coverage Report

```sql
WITH object_stats AS (
  SELECT 
    table_catalog AS database_name,
    table_schema AS schema_name,
    COUNT(*) AS total_objects,
    SUM(CASE WHEN table_type = 'BASE TABLE' THEN 1 ELSE 0 END) AS table_count,
    SUM(CASE WHEN table_type = 'VIEW' THEN 1 ELSE 0 END) AS view_count
  FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
  WHERE deleted IS NULL
  GROUP BY table_catalog, table_schema
),
contact_stats AS (
  SELECT 
    object_database,
    object_schema,
    purpose,
    COUNT(DISTINCT object_name) AS objects_with_contact
  FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES
  WHERE deleted IS NULL
  GROUP BY object_database, object_schema, purpose
)
SELECT 
  os.database_name,
  os.schema_name,
  os.total_objects,
  os.table_count,
  os.view_count,
  COALESCE(cs_steward.objects_with_contact, 0) AS steward_count,
  COALESCE(cs_support.objects_with_contact, 0) AS support_count,
  COALESCE(cs_approval.objects_with_contact, 0) AS approval_count,
  ROUND(COALESCE(cs_steward.objects_with_contact, 0) * 100.0 / NULLIF(os.total_objects, 0), 2) AS steward_coverage_pct
FROM object_stats os
LEFT JOIN contact_stats cs_steward
  ON os.database_name = cs_steward.object_database
  AND os.schema_name = cs_steward.object_schema
  AND cs_steward.purpose = 'STEWARD'
LEFT JOIN contact_stats cs_support
  ON os.database_name = cs_support.object_database
  AND os.schema_name = cs_support.object_schema
  AND cs_support.purpose = 'SUPPORT'
LEFT JOIN contact_stats cs_approval
  ON os.database_name = cs_approval.object_database
  AND os.schema_name = cs_approval.object_schema
  AND cs_approval.purpose = 'ACCESS_APPROVAL'
ORDER BY os.database_name, os.schema_name;
```

### Template 15: Inheritance Analysis Report

```sql
SELECT 
  object_database,
  object_schema,
  object_name,
  object_domain,
  contact_name,
  purpose,
  CASE 
    WHEN is_inherited = TRUE THEN 'Inherited from ' || parent_object_name
    ELSE 'Direct Assignment'
  END AS assignment_detail,
  c.communication_method,
  c.communication_value
FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES cr
JOIN SNOWFLAKE.ACCOUNT_USAGE.CONTACTS c
  ON cr.contact_name = c.contact_name
  AND cr.contact_schema = c.contact_schema
  AND cr.contact_database = c.contact_database
WHERE cr.object_database = '<database>'
  AND cr.deleted IS NULL
  AND c.deleted IS NULL
ORDER BY 
  cr.object_database,
  cr.object_schema,
  cr.is_inherited DESC,
  cr.object_name;
```

### Template 16: Contact Detail Report

```sql
SELECT 
  c.contact_database,
  c.contact_schema,
  c.contact_name,
  c.communication_method,
  c.communication_value,
  COUNT(cr.object_name) AS objects_associated,
  SUM(CASE WHEN cr.is_inherited = FALSE THEN 1 ELSE 0 END) AS direct_assignments,
  SUM(CASE WHEN cr.is_inherited = TRUE THEN 1 ELSE 0 END) AS inherited_assignments
FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACTS c
LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES cr
  ON c.contact_name = cr.contact_name
  AND c.contact_schema = cr.contact_schema
  AND c.contact_database = cr.contact_database
  AND cr.deleted IS NULL
WHERE c.deleted IS NULL
GROUP BY 
  c.contact_database,
  c.contact_schema,
  c.contact_name,
  c.communication_method,
  c.communication_value
ORDER BY objects_associated DESC;
```

---

## Remove Contacts

### Template 17: Unset Contact from Object

```sql
ALTER TABLE <database>.<schema>.<table_name>
  UNSET CONTACT <purpose>;
```

**Example:**
```sql
ALTER TABLE ANALYTICS_DB.SALES.CUSTOMERS
  UNSET CONTACT STEWARD;
```

### Template 18: Drop Contact (Remove Completely)

```sql
-- First, check where it's used
SELECT object_database, object_schema, object_name
FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES
WHERE contact_name = '<contact_name>'
  AND deleted IS NULL;

-- If safe to drop
DROP CONTACT <database>.<schema>.<contact_name>;
```

**Example:**
```sql
DROP CONTACT GOVERNANCE_DB.CONTACTS.old_steward;
```

### Template 19: Replace Contact Across All Objects

```sql
-- Find all objects with old contact
WITH objects_to_update AS (
  SELECT 
    object_database,
    object_schema,
    object_name,
    object_domain,
    purpose
  FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES
  WHERE contact_name = '<old_contact>'
    AND is_inherited = FALSE
    AND deleted IS NULL
)
SELECT 
  'ALTER ' || object_domain || ' ' || 
  object_database || '.' || object_schema || '.' || object_name ||
  ' SET CONTACT ' || purpose || ' = ' || '<new_contact>' || ';' AS migration_sql
FROM objects_to_update;
```

---

## Complete Workflow Examples

### Workflow 1: Setup Governance Contacts for New Database

```sql
-- Step 1: Create governance schema for contacts
CREATE SCHEMA IF NOT EXISTS GOVERNANCE_DB.CONTACTS;

-- Step 2: Create contacts
CREATE CONTACT GOVERNANCE_DB.CONTACTS.data_stewards
  EMAIL_DISTRIBUTION_LIST = 'data_stewards@company.com';

CREATE CONTACT GOVERNANCE_DB.CONTACTS.tech_support
  URL = 'https://support.company.com/data';

CREATE CONTACT GOVERNANCE_DB.CONTACTS.access_approvers
  EMAIL_DISTRIBUTION_LIST = 'access_team@company.com';

-- Step 3: Grant privileges
GRANT APPLY ON CONTACT GOVERNANCE_DB.CONTACTS.data_stewards TO ROLE GOVERNANCE_ADMIN;
GRANT APPLY ON CONTACT GOVERNANCE_DB.CONTACTS.tech_support TO ROLE GOVERNANCE_ADMIN;
GRANT APPLY ON CONTACT GOVERNANCE_DB.CONTACTS.access_approvers TO ROLE GOVERNANCE_ADMIN;

-- Step 4: Assign at database level for inheritance
ALTER DATABASE ANALYTICS_DB
  SET CONTACT 
    STEWARD = GOVERNANCE_DB.CONTACTS.data_stewards,
    SUPPORT = GOVERNANCE_DB.CONTACTS.tech_support;

-- Step 5: Verify
SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES
WHERE object_database = 'ANALYTICS_DB'
  AND deleted IS NULL;
```

### Workflow 2: Migrate Contact Assignments

```sql
-- Step 1: Create new contact
CREATE CONTACT GOVERNANCE_DB.CONTACTS.new_steward
  EMAIL_DISTRIBUTION_LIST = 'new_team@company.com';

-- Step 2: Find objects with old contact
SELECT 
  object_database,
  object_schema,
  object_name,
  object_domain,
  purpose
FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES
WHERE contact_name = 'old_steward'
  AND is_inherited = FALSE
  AND deleted IS NULL;

-- Step 3: Update at schema level (if applicable)
ALTER SCHEMA ANALYTICS_DB.SALES
  SET CONTACT STEWARD = GOVERNANCE_DB.CONTACTS.new_steward;

-- Step 4: Update individual objects (if needed)
ALTER TABLE ANALYTICS_DB.SALES.CUSTOMERS
  SET CONTACT STEWARD = GOVERNANCE_DB.CONTACTS.new_steward;

-- Step 5: Verify migration
SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES
WHERE contact_name IN ('old_steward', 'new_steward')
  AND deleted IS NULL;

-- Step 6: Drop old contact (after verification)
DROP CONTACT GOVERNANCE_DB.CONTACTS.old_steward;
```

### Workflow 3: Generate Governance Compliance Report

```sql
-- Comprehensive contact compliance report
WITH all_tables AS (
  SELECT 
    table_catalog,
    table_schema,
    table_name,
    table_type,
    row_count,
    bytes
  FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
  WHERE deleted IS NULL
    AND table_catalog = '<database>'
),
steward_contacts AS (
  SELECT 
    cr.object_database,
    cr.object_schema,
    cr.object_name,
    cr.contact_name AS steward_contact,
    cr.is_inherited AS steward_inherited,
    c.communication_value AS steward_email
  FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES cr
  JOIN SNOWFLAKE.ACCOUNT_USAGE.CONTACTS c
    ON cr.contact_name = c.contact_name
    AND cr.contact_schema = c.contact_schema
    AND cr.contact_database = c.contact_database
  WHERE cr.purpose = 'STEWARD'
    AND cr.deleted IS NULL
    AND c.deleted IS NULL
),
support_contacts AS (
  SELECT 
    cr.object_database,
    cr.object_schema,
    cr.object_name,
    cr.contact_name AS support_contact,
    c.communication_value AS support_value
  FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES cr
  JOIN SNOWFLAKE.ACCOUNT_USAGE.CONTACTS c
    ON cr.contact_name = c.contact_name
    AND cr.contact_schema = c.contact_schema
    AND cr.contact_database = c.contact_database
  WHERE cr.purpose = 'SUPPORT'
    AND cr.deleted IS NULL
    AND c.deleted IS NULL
)
SELECT 
  at.table_catalog AS database_name,
  at.table_schema AS schema_name,
  at.table_name AS object_name,
  at.table_type AS object_type,
  COALESCE(sc.steward_contact, '⚠️ NO STEWARD') AS data_steward,
  COALESCE(sc.steward_email, '-') AS steward_contact_info,
  CASE 
    WHEN sc.steward_inherited = TRUE THEN 'Inherited'
    WHEN sc.steward_inherited = FALSE THEN 'Direct'
    ELSE '-'
  END AS steward_assignment,
  COALESCE(sup.support_contact, '-') AS support_contact,
  COALESCE(sup.support_value, '-') AS support_info,
  at.row_count,
  ROUND(at.bytes / 1024 / 1024, 2) AS size_mb
FROM all_tables at
LEFT JOIN steward_contacts sc
  ON at.table_catalog = sc.object_database
  AND at.table_schema = sc.object_schema
  AND at.table_name = sc.object_name
LEFT JOIN support_contacts sup
  ON at.table_catalog = sup.object_database
  AND at.table_schema = sup.object_schema
  AND at.table_name = sup.object_name
ORDER BY 
  CASE WHEN sc.steward_contact IS NULL THEN 0 ELSE 1 END,
  at.table_catalog,
  at.table_schema,
  at.table_name;
```

---

## Advanced Templates

### Template 20: Contact Usage Matrix

```sql
-- Show which contacts are used for which purposes
SELECT 
  cr.contact_name,
  c.communication_method,
  c.communication_value,
  SUM(CASE WHEN cr.purpose = 'STEWARD' THEN 1 ELSE 0 END) AS steward_assignments,
  SUM(CASE WHEN cr.purpose = 'SUPPORT' THEN 1 ELSE 0 END) AS support_assignments,
  SUM(CASE WHEN cr.purpose = 'ACCESS_APPROVAL' THEN 1 ELSE 0 END) AS approval_assignments,
  COUNT(DISTINCT cr.object_name) AS total_objects
FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES cr
JOIN SNOWFLAKE.ACCOUNT_USAGE.CONTACTS c
  ON cr.contact_name = c.contact_name
  AND cr.contact_schema = c.contact_schema
  AND cr.contact_database = c.contact_database
WHERE cr.deleted IS NULL
  AND c.deleted IS NULL
GROUP BY cr.contact_name, c.communication_method, c.communication_value
ORDER BY total_objects DESC;
```

### Template 21: Inheritance Impact Analysis

```sql
-- Show what happens if you assign contact at schema level
SELECT 
  '<schema_level_assignment>' AS assignment_level,
  table_catalog,
  table_schema,
  COUNT(*) AS objects_that_will_inherit
FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
WHERE table_schema = '<schema>'
  AND table_catalog = '<database>'
  AND deleted IS NULL
GROUP BY table_catalog, table_schema;
```

### Template 22: Contact Change History

```sql
-- Track contact changes (using ACCOUNT_USAGE latency)
SELECT 
  contact_name,
  contact_database,
  contact_schema,
  communication_method,
  communication_value,
  created,
  last_altered,
  deleted,
  CASE 
    WHEN deleted IS NOT NULL THEN 'Deleted'
    WHEN last_altered > created THEN 'Modified'
    ELSE 'Active'
  END AS status
FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACTS
WHERE contact_name = '<contact_name>'
ORDER BY created DESC;
```

---

## Privilege Management

### Template 23: Grant Contact Apply Privileges

```sql
-- Grant ability to apply specific contact to objects
GRANT APPLY ON CONTACT <database>.<schema>.<contact_name> 
  TO ROLE <role_name>;

-- Grant ability to apply ANY contact to objects (account-level)
GRANT APPLY CONTACT ON ACCOUNT TO ROLE <role_name>;
```

### Template 24: Grant Contact Creation Privileges

```sql
GRANT CREATE CONTACT ON SCHEMA <database>.<schema> TO ROLE <role_name>;
GRANT USAGE ON SCHEMA <database>.<schema> TO ROLE <role_name>;
GRANT USAGE ON DATABASE <database> TO ROLE <role_name>;
```

---

## Testing & Validation

### Template 25: Verify Contact Inheritance

```sql
-- Check what a user sees for an object
SELECT 
  contact_name,
  purpose,
  communication_method,
  communication_value,
  is_inherited,
  CASE 
    WHEN is_inherited = TRUE THEN inherited_from
    ELSE 'Direct'
  END AS source
FROM TABLE(SNOWFLAKE.CORE.GET_CONTACTS('<object_name>', '<object_type>'));
```

### Template 26: Test Contact Accessibility

```sql
-- Check if users can see the contact
USE ROLE <test_role>;
SELECT * FROM TABLE(SNOWFLAKE.CORE.GET_CONTACTS('<object_name>', 'TABLE'));
```

---

## Notes

- **ACCOUNT_USAGE Latency**: Up to 90 minutes for CONTACTS and CONTACT_REFERENCES views
- **GET_CONTACTS Function**: Real-time, use for immediate verification
- **Inheritance**: Database → Schema → Table/View hierarchy
- **Override**: Direct assignment overrides inherited contact with same purpose
- **Fully Qualified Names**: Always use `DATABASE.SCHEMA.CONTACT_NAME` for clarity
