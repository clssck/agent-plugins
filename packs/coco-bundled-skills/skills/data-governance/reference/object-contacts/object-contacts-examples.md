# Object Contacts - Practical Examples

## Example 1: Setup Data Steward for Analytics Database

**Scenario:** Assign analytics data steward team as responsible contact for all tables in ANALYTICS_DB.

**Solution:**

```sql
-- Create governance schema
CREATE SCHEMA IF NOT EXISTS GOVERNANCE_DB.CONTACTS;

-- Create data steward contact
CREATE CONTACT GOVERNANCE_DB.CONTACTS.analytics_stewards
  EMAIL_DISTRIBUTION_LIST = 'analytics_stewards@company.com';

-- Assign at database level (all objects inherit)
ALTER DATABASE ANALYTICS_DB
  SET CONTACT STEWARD = GOVERNANCE_DB.CONTACTS.analytics_stewards;

-- Verify inheritance
SELECT 
  object_database,
  object_schema,
  object_name,
  is_inherited,
  parent_object_name
FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES
WHERE object_database = 'ANALYTICS_DB'
  AND purpose = 'STEWARD'
  AND deleted IS NULL
LIMIT 10;
```

**Result:** All 250+ tables in ANALYTICS_DB inherit the analytics_stewards contact.

---

## Example 2: Assign Different Stewards by Department

**Scenario:** Different schemas represent different departments, each with their own steward team.

**Solution:**

```sql
-- Create department-specific contacts
CREATE CONTACT GOVERNANCE_DB.CONTACTS.sales_stewards
  EMAIL_DISTRIBUTION_LIST = 'sales_data@company.com';

CREATE CONTACT GOVERNANCE_DB.CONTACTS.finance_stewards
  EMAIL_DISTRIBUTION_LIST = 'finance_data@company.com';

CREATE CONTACT GOVERNANCE_DB.CONTACTS.hr_stewards
  EMAIL_DISTRIBUTION_LIST = 'hr_data@company.com';

-- Assign at schema level (inheritance)
ALTER SCHEMA ANALYTICS_DB.SALES
  SET CONTACT STEWARD = GOVERNANCE_DB.CONTACTS.sales_stewards;

ALTER SCHEMA ANALYTICS_DB.FINANCE
  SET CONTACT STEWARD = GOVERNANCE_DB.CONTACTS.finance_stewards;

ALTER SCHEMA ANALYTICS_DB.HR
  SET CONTACT STEWARD = GOVERNANCE_DB.CONTACTS.hr_stewards;

-- Verify by schema
SELECT 
  object_schema,
  contact_name,
  COUNT(*) AS objects_with_contact
FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES cr
JOIN SNOWFLAKE.ACCOUNT_USAGE.CONTACTS c
  ON cr.contact_name = c.contact_name
  AND cr.contact_schema = c.contact_schema
  AND cr.contact_database = c.contact_database
WHERE cr.object_database = 'ANALYTICS_DB'
  AND cr.purpose = 'STEWARD'
  AND cr.deleted IS NULL
  AND c.deleted IS NULL
GROUP BY object_schema, cr.contact_name;
```

**Result:**
- SALES schema: 50 objects → sales_stewards@company.com
- FINANCE schema: 30 objects → finance_data@company.com
- HR schema: 15 objects → hr_data@company.com

---

## Example 3: Override Inherited Contact for Sensitive Table

**Scenario:** Most tables in SALES schema use general sales_stewards, but CUSTOMERS_PII needs a specific privacy officer.

**Solution:**

```sql
-- Create privacy officer contact
CREATE CONTACT GOVERNANCE_DB.CONTACTS.privacy_officer
  USERS = ('PRIVACY_ADMIN', 'DPO_USER');

-- Schema has general steward (inherited by all tables)
ALTER SCHEMA ANALYTICS_DB.SALES
  SET CONTACT STEWARD = GOVERNANCE_DB.CONTACTS.sales_stewards;

-- Override for sensitive table (direct assignment)
ALTER TABLE ANALYTICS_DB.SALES.CUSTOMERS_PII
  SET CONTACT 
    STEWARD = GOVERNANCE_DB.CONTACTS.privacy_officer,
    ACCESS_APPROVAL = GOVERNANCE_DB.CONTACTS.privacy_officer;

-- Compare inheritance vs override
SELECT * FROM TABLE(SNOWFLAKE.CORE.GET_CONTACTS('ANALYTICS_DB.SALES.CUSTOMERS_PII', 'TABLE'));
SELECT * FROM TABLE(SNOWFLAKE.CORE.GET_CONTACTS('ANALYTICS_DB.SALES.ORDERS', 'TABLE'));
```

**Result:**
- CUSTOMERS_PII: privacy_officer (Direct override)
- ORDERS: sales_stewards (Inherited from schema)

---

## Example 4: Find All Objects with Specific Contact

**Scenario:** Find all objects where "john_doe_steward" is the data steward during team reorganization.

**Solution:**

```sql
SELECT 
  object_database,
  object_schema,
  object_name,
  object_domain AS object_type,
  purpose,
  CASE 
    WHEN is_inherited = TRUE THEN 'Inherited from ' || parent_object_name
    ELSE 'Direct Assignment'
  END AS assignment_type
FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES
WHERE UPPER(contact_name) = UPPER('john_doe_steward')
  AND deleted IS NULL
ORDER BY 
  object_database,
  object_schema,
  is_inherited DESC,
  object_name;
```

**Result:**
```
Found 45 objects:
- 2 direct assignments (SALES.CUSTOMERS, FINANCE.REVENUE)
- 43 inherited assignments (from ANALYTICS_DB database-level contact)

Recommendation: Update database-level contact to new steward, then reassign direct ones.
```

---

## Example 5: Comprehensive Contact Report for Database

**Scenario:** Generate audit documentation showing all data stewards for ANALYTICS_DB.

**Solution:**

```sql
WITH objects AS (
  SELECT 
    table_catalog,
    table_schema,
    table_name,
    table_type,
    row_count,
    bytes
  FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
  WHERE table_catalog = 'ANALYTICS_DB'
    AND deleted IS NULL
),
stewards AS (
  SELECT 
    cr.object_database,
    cr.object_schema,
    cr.object_name,
    cr.contact_name,
    cr.is_inherited,
    cr.parent_object_name,
    c.communication_value
  FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES cr
  JOIN SNOWFLAKE.ACCOUNT_USAGE.CONTACTS c
    ON cr.contact_name = c.contact_name
    AND cr.contact_schema = c.contact_schema
    AND cr.contact_database = c.contact_database
  WHERE cr.purpose = 'STEWARD'
    AND cr.deleted IS NULL
    AND c.deleted IS NULL
)
SELECT 
  o.table_schema,
  o.table_name,
  o.table_type,
  COALESCE(s.contact_name, '⚠️ NO STEWARD') AS steward,
  COALESCE(s.communication_value, '-') AS contact_info,
  CASE 
    WHEN s.is_inherited = TRUE THEN '↓ ' || s.parent_object_name
    WHEN s.is_inherited = FALSE THEN '✓ Direct'
    ELSE '-'
  END AS assignment,
  o.row_count,
  ROUND(o.bytes / 1024 / 1024, 2) AS size_mb
FROM objects o
LEFT JOIN stewards s
  ON o.table_catalog = s.object_database
  AND o.table_schema = s.object_schema
  AND o.table_name = s.object_name
ORDER BY 
  CASE WHEN s.contact_name IS NULL THEN 0 ELSE 1 END,
  o.table_schema,
  o.table_name
LIMIT 50;
```

**Result:** Comprehensive report showing steward, contact method, assignment type, and object metadata.

---

## Example 6: Find Objects Without Stewards

**Scenario:** Compliance requirement - all tables must have a data steward assigned.

**Solution:**

```sql
WITH all_tables AS (
  SELECT 
    table_catalog,
    table_schema,
    table_name,
    row_count,
    bytes
  FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
  WHERE table_catalog = 'ANALYTICS_DB'
    AND table_type = 'BASE TABLE'
    AND deleted IS NULL
),
steward_assigned AS (
  SELECT DISTINCT
    object_database,
    object_schema,
    object_name
  FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES
  WHERE purpose = 'STEWARD'
    AND deleted IS NULL
)
SELECT 
  at.table_catalog AS database,
  at.table_schema AS schema,
  at.table_name AS table_name,
  at.row_count,
  ROUND(at.bytes / 1024 / 1024 / 1024, 2) AS size_gb,
  '⚠️ NO STEWARD ASSIGNED' AS status
FROM all_tables at
LEFT JOIN steward_assigned sa
  ON at.table_catalog = sa.object_database
  AND at.table_schema = sa.object_schema
  AND at.table_name = sa.object_name
WHERE sa.object_name IS NULL
ORDER BY at.bytes DESC;
```

**Action Plan:**
```
Found 25 tables without steward contacts:

High Priority (>100 GB):
  - ANALYTICS_DB.SALES.TRANSACTIONS (150 GB)
  - ANALYTICS_DB.CUSTOMER.PROFILES (120 GB)

Recommendation: Assign steward at schema level to cover all tables.
```

---

## Example 7: Contact Migration During Reorganization

**Scenario:** Finance department split into two teams. Need to migrate contacts.

**Solution:**

```sql
-- Create new contacts
CREATE CONTACT GOVERNANCE_DB.CONTACTS.finance_revenue_team
  EMAIL_DISTRIBUTION_LIST = 'revenue@company.com';

CREATE CONTACT GOVERNANCE_DB.CONTACTS.finance_expense_team
  EMAIL_DISTRIBUTION_LIST = 'expenses@company.com';

-- Find objects with old contact
SELECT 
  object_schema,
  object_name,
  object_domain
FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES
WHERE contact_name = 'finance_team'
  AND is_inherited = FALSE
  AND deleted IS NULL;

-- Migrate revenue tables
ALTER TABLE ANALYTICS_DB.FINANCE.REVENUE
  SET CONTACT STEWARD = GOVERNANCE_DB.CONTACTS.finance_revenue_team;

ALTER TABLE ANALYTICS_DB.FINANCE.SALES_METRICS
  SET CONTACT STEWARD = GOVERNANCE_DB.CONTACTS.finance_revenue_team;

-- Migrate expense tables
ALTER TABLE ANALYTICS_DB.FINANCE.EXPENSES
  SET CONTACT STEWARD = GOVERNANCE_DB.CONTACTS.finance_expense_team;

ALTER TABLE ANALYTICS_DB.FINANCE.COST_CENTERS
  SET CONTACT STEWARD = GOVERNANCE_DB.CONTACTS.finance_expense_team;

-- Verify migration
SELECT contact_name, COUNT(*) 
FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES
WHERE contact_name IN ('finance_revenue_team', 'finance_expense_team', 'finance_team')
  AND deleted IS NULL
GROUP BY contact_name;

-- Drop old contact (after verification)
DROP CONTACT GOVERNANCE_DB.CONTACTS.finance_team;
```

---

## Key Takeaways

### Best Practices
✅ **Use schema-level assignment** for consistency and scale  
✅ **Direct assignment** only for exceptions (e.g., sensitive data)  
✅ **Create contacts in dedicated schema** (GOVERNANCE_DB.CONTACTS)  
✅ **Use GET_CONTACTS()** for real-time verification (no latency)  
✅ **Use ACCOUNT_USAGE views** for reporting (up to 90-minute latency)  
✅ **Regular audits** to identify gaps in coverage  

### Common Patterns

**Pattern 1: New Database Setup**
1. Create contacts schema
2. Create steward/support contacts
3. Assign at database level
4. Verify inheritance

**Pattern 2: Schema-Level Governance**
1. Create department-specific contacts
2. Assign at schema level
3. All tables inherit automatically
4. Override only when necessary

**Pattern 3: Finding Gaps**
1. Query all objects
2. Left join with CONTACT_REFERENCES
3. Identify objects without contacts
4. Assign at appropriate level

**Pattern 4: Migration**
1. Create new contacts
2. Find objects with old contact
3. Update assignments
4. Verify migration
5. Drop old contact

---

## Quick Reference Commands

```sql
-- View contacts for object (real-time)
SELECT * FROM TABLE(SNOWFLAKE.CORE.GET_CONTACTS('<object_name>', 'TABLE'));

-- Find objects by contact (up to 90-minute latency)
SELECT object_database, object_schema, object_name
FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES
WHERE contact_name = '<name>' AND deleted IS NULL;

-- Coverage statistics
SELECT 
  COUNT(*) AS total_objects,
  COUNT(DISTINCT CASE WHEN cr.purpose = 'STEWARD' THEN t.table_name END) AS with_steward
FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES t
LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES cr
  ON t.table_catalog = cr.object_database
  AND t.table_schema = cr.object_schema
  AND t.table_name = cr.object_name
WHERE t.table_catalog = '<database>' AND t.deleted IS NULL;
```
