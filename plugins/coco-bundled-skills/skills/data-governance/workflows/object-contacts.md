# Object Contacts Management

Help users manage Snowflake object contacts to establish clear data stewardship and support responsibilities for databases, schemas, tables, and views.

Reference: [Snowflake Contacts Documentation](https://docs.snowflake.com/en/user-guide/contacts-using) · [Best practices & troubleshooting](../reference/object-contacts/object-contacts-reference.md)

**SQL template libraries** (load on demand for advanced scenarios):
- [Create templates](../templates/object-contacts/create.md) — `CREATE CONTACT` variants, batch creation
- [Assign templates](../templates/object-contacts/assign.md) — assign, batch assign, inheritance patterns
- [Query & report templates](../templates/object-contacts/query.md) — find contacts, coverage reports, migration, privilege management
- [Practical examples](../reference/object-contacts/object-contacts-examples.md) — 7 end-to-end scenarios (new DB setup, department stewards, migration, audit)

## Core Concepts

**Contact Purposes:** `STEWARD` (data accuracy/reliability) · `SUPPORT` (technical help) · `ACCESS_APPROVAL` (access requests)

**Communication Methods:** `URL` · `EMAIL_DISTRIBUTION_LIST` · `USERS` (list of Snowflake usernames)

**Supported Objects:** Database, Schema, Table, View, Iceberg table, External table, Dynamic table, Event table, Materialized view, Task

**Inheritance:** Contacts cascade to child objects. Direct assignment on a child overrides the parent for that same purpose.

---

## Step 1: Understand User Intent

**Ask user:**
```
What would you like to do with object contacts?

1. Associate an existing contact with an object
2. Create a new contact
3. Assign contact to a schema/database (inheritance) or directly to specific objects
4. Find all objects with a specific contact
5. Generate a contact report for objects in a database/schema
```

✋ **STOP** — wait for selection before proceeding.

---

## Option 1: Associate Existing Contact with Object

### Step 1.1: Gather Details & Verify Contact Exists

**Ask user:**
```
Please provide:
- Contact name: (e.g., finance_dept, data_stewards)
- Object to associate with: (e.g., MY_DB.MY_SCHEMA.MY_TABLE)
- Purpose: STEWARD / SUPPORT / ACCESS_APPROVAL
```

**Execute to verify contact exists:**
```sql
SELECT contact_name, contact_schema, contact_database,
       communication_method, communication_value
FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACTS
WHERE UPPER(contact_name) = UPPER('<contact_name>')
  AND deleted IS NULL
ORDER BY created DESC
LIMIT 1;
```

If not found: offer to create the contact first (go to Option 2).

### Step 1.2: Approval Gate → Associate Contact

⚠️ **STOP — Confirm before executing:**
```
About to run:

  -- For tables/views:
  ALTER TABLE <database>.<schema>.<object_name>
    SET CONTACT <purpose> = <contact_name>;

  -- For schemas:
  ALTER SCHEMA <database>.<schema>
    SET CONTACT <purpose> = <contact_name>;

  -- For databases:
  ALTER DATABASE <database>
    SET CONTACT <purpose> = <contact_name>;

Reply YES to proceed or NO to cancel.
```

**After confirmation, execute the appropriate statement, then verify:**
```sql
SELECT *
FROM TABLE(SNOWFLAKE.CORE.GET_CONTACTS('<object_name>', '<object_type>'));
```

**Success message:**
```
✅ Contact '<contact_name>' successfully associated with <object_name> as <purpose>
- Communication Method: <method>
- Contact Value: <value>
```

**Next:** Return to Step 1 menu to perform another action, or let me know if you're done.

---

## Option 2: Create New Contact

### Step 2.1: Gather Contact Details

**Ask user:**
```
Let's create a new contact. Please provide:

1. Contact Name: (e.g., finance_team, sales_stewards)
2. Schema Location: (e.g., GOVERNANCE_DB.CONTACTS)
3. Communication Method:
   - URL (website)
   - EMAIL_DISTRIBUTION_LIST (email or distribution list)
   - USERS (list of Snowflake usernames)
4. Communication Value: (the URL, email address, or usernames)
```

### Step 2.2: Verify Schema Exists

**Execute:**
```sql
SHOW SCHEMAS LIKE '<schema_name>' IN DATABASE <database_name>;
```

If not found, ask:
```
⚠️ Schema does not exist. Would you like to:
a) Create the schema first
b) Use a different schema
```

✋ **STOP** — wait for response before continuing.

### Step 2.3: Approval Gate → Create Contact

⚠️ **STOP — Confirm before executing:**
```
About to create:

  -- URL method:
  CREATE CONTACT <database>.<schema>.<contact_name>
    URL = '<url_value>';

  -- Email method:
  CREATE CONTACT <database>.<schema>.<contact_name>
    EMAIL_DISTRIBUTION_LIST = '<email_value>';

  -- Users method:
  CREATE CONTACT <database>.<schema>.<contact_name>
    USERS = ('<user1>', '<user2>');

Reply YES to proceed or NO to cancel.
```

**After confirmation, execute, then verify:**
```sql
SELECT contact_name, contact_schema, contact_database,
       communication_method, communication_value
FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACTS
WHERE UPPER(contact_name) = UPPER('<contact_name>')
  AND deleted IS NULL;
```

**Success message:**
```
✅ Contact '<contact_name>' created successfully!
- Location: <database>.<schema>.<contact_name>
- Method: <communication_method>
- Value: <communication_value>

Would you like to associate this contact with an object now? (go to Option 1)
```

**Next:** Return to Step 1 menu or proceed to Option 1 to assign.

---

## Option 3: Schema/Database vs Direct Assignment

### Step 3.1: Explain Inheritance vs Direct

**Present to user:**
```
📋 Understanding Contact Assignment Approaches:

Option A — Schema/Database Assignment (recommended for consistency)
✅ All current AND future objects inherit the contact automatically
✅ Single point of control; easy to govern at scale
❌ Cannot have different stewards for individual tables

Option B — Direct Object Assignment (granular control)
✅ Specific steward per table/view; overrides inherited contacts
❌ Must assign per object; new objects won't auto-inherit

Example:
  Schema Assignment:
    SALES_DB.ANALYTICS (contact: sales_stewards)
      ├── CUSTOMERS ← inherits sales_stewards
      └── ORDERS    ← inherits sales_stewards

  Direct Assignment:
    SALES_DB.ANALYTICS (no contact)
      ├── CUSTOMERS → contact: customer_team
      └── ORDERS    → contact: order_team

Which approach?
```

✋ **STOP** — wait for choice.

### Step 3.2: Approval Gate → Execute Assignment

#### Option A — Schema/Database Assignment

**Ask user:**
```
Please provide:
- Database or Schema: (e.g., ANALYTICS_DB or ANALYTICS_DB.SALES)
- Contact Name:
- Purpose: STEWARD / SUPPORT / ACCESS_APPROVAL
```

**Show impact first** (read-only — execute immediately):
```sql
-- Count objects that will inherit the contact
-- Note: ACCOUNT_USAGE views have up to 90-minute latency —
--       counts may not reflect objects created in the last 90 minutes.
SELECT 'Tables' AS object_type, COUNT(*) AS object_count
FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
WHERE UPPER(table_schema)  = UPPER('<schema>')
  AND UPPER(table_catalog) = UPPER('<database>')
  AND deleted IS NULL
UNION ALL
SELECT 'Views', COUNT(*)
FROM SNOWFLAKE.ACCOUNT_USAGE.VIEWS
WHERE UPPER(table_schema)  = UPPER('<schema>')
  AND UPPER(table_catalog) = UPPER('<database>')
  AND deleted IS NULL;
```

⚠️ **STOP — Confirm before executing:**
```
This will set <contact_name> as <purpose> on <object_level>.
~<count> tables and ~<count> views will inherit this contact.

About to run:
  ALTER SCHEMA <database>.<schema>
    SET CONTACT <purpose> = <contact_name>;
  -- or:
  ALTER DATABASE <database>
    SET CONTACT <purpose> = <contact_name>;

Reply YES to proceed or NO to cancel.
```

**Success message:**
```
✅ Contact assigned to <object_level>!
- ~<count> tables and ~<count> views will inherit this contact
- All future objects in this <object_level> will automatically inherit the contact

Next: Run Option 5 to generate a verification report.
```

#### Option B — Direct Object Assignment

**Ask user:**
```
Please provide:
- Objects to assign (comma-separated): (e.g., TABLE1, TABLE2, VIEW1)
- Database.Schema: (e.g., ANALYTICS_DB.SALES)
- Contact Name:
- Purpose: STEWARD / SUPPORT / ACCESS_APPROVAL
```

**Resolve object types:**
```sql
SELECT table_name, table_type
FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
WHERE UPPER(table_catalog) = UPPER('<database>')
  AND UPPER(table_schema)  = UPPER('<schema>')
  AND UPPER(table_name) IN (<quoted_list>)
  AND deleted IS NULL;
```

⚠️ **STOP — Confirm before executing:**
```
About to assign <contact_name> as <purpose> to:
  - <database>.<schema>.<object1>
  - <database>.<schema>.<object2>
  ...

Reply YES to proceed or NO to cancel.
```

**Execute for each object:**
```sql
ALTER TABLE <database>.<schema>.<object_name>
  SET CONTACT <purpose> = <contact_name>;
```

**Success message:**
```
✅ Contact assigned to <count> objects:
  - <object1>: ✅ Success
  - <object2>: ✅ Success
```

**Next:** Return to Step 1 menu or run Option 5 to verify.

---

## Option 4: Find All Objects with Specific Contact

### Step 4.1: Gather Search Criteria

**Ask user:**
```
Find objects by contact:
- Contact Name: (e.g., data_stewards)
- Purpose filter (optional): STEWARD / SUPPORT / ACCESS_APPROVAL / ALL
- Object type filter (optional): TABLE / VIEW / SCHEMA / DATABASE / ALL
- Scope filter (optional): specific database or schema name
```

### Step 4.2: Query Contact References

**Execute:**
```sql
SELECT
  cr.contact_name,
  cr.object_database,
  cr.object_schema,
  cr.object_name,
  cr.object_domain        AS object_type,
  cr.purpose,
  CASE WHEN cr.is_inherited THEN 'Inherited' ELSE 'Direct' END AS assignment_type,
  cr.parent_object_name   AS inherited_from,
  c.communication_method,
  c.communication_value
FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES cr
JOIN SNOWFLAKE.ACCOUNT_USAGE.CONTACTS c
  ON  cr.contact_name     = c.contact_name
  AND cr.contact_schema   = c.contact_schema
  AND cr.contact_database = c.contact_database
WHERE UPPER(cr.contact_name) = UPPER('<contact_name>')
  AND cr.deleted IS NULL
  AND c.deleted  IS NULL
  AND (cr.purpose       = '<purpose>'      OR '<purpose>'      = 'ALL')
  AND (cr.object_domain = '<object_type>'  OR '<object_type>'  = 'ALL')
  AND (UPPER(cr.object_database) = UPPER('<database>') OR '<database>' IS NULL)
  AND (UPPER(cr.object_schema)   = UPPER('<schema>')   OR '<schema>'   IS NULL)
ORDER BY cr.object_database, cr.object_schema, cr.object_name;
```

### Step 4.3: Present Results

```
📊 Objects Associated with Contact: <contact_name>
- Method: <communication_method>  Value: <value>

Found <count> objects:

Database: <database>
  Schema: <schema>
    ✓ TABLE: <table1>  (Purpose: STEWARD, Assignment: Direct)
    ✓ TABLE: <table2>  (Purpose: STEWARD, Assignment: Inherited from <schema>)
    ✓ VIEW:  <view1>   (Purpose: SUPPORT, Assignment: Inherited from <database>)

Summary:
- Direct Assignments: <count>
- Inherited Assignments: <count>
- Total Objects: <count>
```

**Next:** Return to Step 1 menu or run Option 5 for a full report.

---

## Option 5: Generate Contact Report

### Step 5.1: Define Report Scope

**Ask user:**
```
Generate contact report for:
1. Specific database  — provide: database name
2. Specific schema    — provide: database.schema
3. All accessible objects

Include object types:
- Tables: YES / NO  (default: YES)
- Views:  YES / NO  (default: YES)
- Show inherited contacts: YES / NO  (default: YES)
```

✋ **STOP** — wait for all inputs.

### Step 5.2: Execute Report Query

**Substitute `<include_tables>` and `<include_views>` from user's YES/NO answers.**
**Apply only the scope WHERE block that matches the user's scope selection.**

```sql
WITH object_contacts AS (
  SELECT
    t.table_catalog AS database_name,
    t.table_schema  AS schema_name,
    t.table_name    AS object_name,
    t.table_type    AS object_type,
    t.created       AS object_created,
    t.row_count,
    t.bytes
  FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES t
  WHERE t.deleted IS NULL
    -- ── Scope filter: uncomment the block matching the user's scope choice ──
    -- Scope 1 — specific database:
    --   AND UPPER(t.table_catalog) = UPPER('<database>')
    -- Scope 2 — specific schema:
    --   AND UPPER(t.table_catalog) = UPPER('<database>')
    --   AND UPPER(t.table_schema)  = UPPER('<schema>')
    -- Scope 3 — all objects: no additional filter
    -- ── Object type filter (from user's YES/NO inputs) ──
    AND (
         (t.table_type = 'BASE TABLE' AND '<include_tables>' = 'YES')
      OR (t.table_type = 'VIEW'       AND '<include_views>'  = 'YES')
    )
),
contact_details AS (
  SELECT
    cr.object_database,
    cr.object_schema,
    cr.object_name,
    cr.contact_name,
    cr.purpose,
    CASE WHEN cr.is_inherited THEN 'Inherited' ELSE 'Direct' END AS assignment_type,
    cr.parent_object_name AS inherited_from,
    c.communication_method,
    c.communication_value
  FROM SNOWFLAKE.ACCOUNT_USAGE.CONTACT_REFERENCES cr
  JOIN SNOWFLAKE.ACCOUNT_USAGE.CONTACTS c
    ON  cr.contact_name     = c.contact_name
    AND cr.contact_schema   = c.contact_schema
    AND cr.contact_database = c.contact_database
  WHERE cr.deleted IS NULL
    AND c.deleted  IS NULL
)
SELECT
  oc.database_name,
  oc.schema_name,
  oc.object_name,
  oc.object_type,
  MAX(CASE WHEN cd.purpose = 'STEWARD'          THEN cd.contact_name       END) AS steward_contact,
  MAX(CASE WHEN cd.purpose = 'STEWARD'          THEN cd.communication_value END) AS steward_value,
  MAX(CASE WHEN cd.purpose = 'STEWARD'          THEN cd.assignment_type    END) AS steward_assignment,
  MAX(CASE WHEN cd.purpose = 'STEWARD'          THEN cd.inherited_from     END) AS steward_inherited_from,
  MAX(CASE WHEN cd.purpose = 'SUPPORT'          THEN cd.contact_name       END) AS support_contact,
  MAX(CASE WHEN cd.purpose = 'SUPPORT'          THEN cd.communication_value END) AS support_value,
  MAX(CASE WHEN cd.purpose = 'SUPPORT'          THEN cd.assignment_type    END) AS support_assignment,
  MAX(CASE WHEN cd.purpose = 'ACCESS_APPROVAL'  THEN cd.contact_name       END) AS approver_contact,
  MAX(CASE WHEN cd.purpose = 'ACCESS_APPROVAL'  THEN cd.communication_value END) AS approver_value,
  MAX(CASE WHEN cd.purpose = 'ACCESS_APPROVAL'  THEN cd.assignment_type    END) AS approver_assignment,
  oc.object_created,
  oc.row_count,
  ROUND(oc.bytes / 1024 / 1024, 2) AS size_mb
FROM object_contacts oc
LEFT JOIN contact_details cd
  ON  oc.database_name = cd.object_database
  AND oc.schema_name   = cd.object_schema
  AND oc.object_name   = cd.object_name
GROUP BY
  oc.database_name, oc.schema_name, oc.object_name, oc.object_type,
  oc.object_created, oc.row_count, oc.bytes
ORDER BY
  oc.database_name, oc.schema_name, oc.object_name;
```

> ⚠️ **Note:** `ACCOUNT_USAGE` views have up to 90-minute latency. Counts and contact assignments may not reflect objects created or modified in the last 90 minutes.

### Step 5.3: Present Formatted Report

```
📊 Contact Report: <scope>
Generated: <timestamp>  |  Objects Analyzed: <count>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Database: <database> › Schema: <schema>

Object: <table_name>  (Table, <size_mb> MB, <rows> rows)
  📧 Steward:  <contact> → <value>  (<Direct|Inherited from …>)
  🔧 Support:  <contact> → <value>  (<Direct|Inherited from …>)
  🔑 Approver: (None assigned)
  Created: <date>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Summary:
- Total Objects:   <n>
- With Steward:    <n> (<pct>%)
- With Support:    <n> (<pct>%)
- With Approver:   <n> (<pct>%)
- No Contacts:     <n> (<pct>%)

Objects Without Steward:
  - <database>.<schema>.<table1>

Recommendations:
⚠️  <n> objects have no steward assigned
💡 Consider assigning contacts at schema level for consistency
```

### Step 5.4: Export Options

**Offer:**
```
Would you like to export this report?
1. View the SQL query for customization
2. Save as a table in Snowflake
3. No export needed
```

For table export (requires confirmation — apply approval gate):
```sql
CREATE OR REPLACE TABLE <database>.<schema>.object_contacts_report AS
<report_query>;

GRANT SELECT ON TABLE <database>.<schema>.object_contacts_report
  TO ROLE GOVERNANCE_ADMIN;
```

**Next:** Return to Step 1 menu or confirm done.

---

## Stopping Points

- ✋ **Step 1** — present menu; wait for selection
- ✋ **Step 1.1** — wait for contact/object/purpose inputs
- ✋ **Step 1.2** — approval gate before `ALTER … SET CONTACT`
- ✋ **Step 2.2** — confirm schema exists; wait if action needed
- ✋ **Step 2.3** — approval gate before `CREATE CONTACT`
- ✋ **Step 3.1** — wait for inheritance vs direct choice
- ✋ **Step 3.2** — approval gate before `ALTER SCHEMA/DATABASE SET CONTACT` or bulk `ALTER TABLE`
- ✋ **Step 5.1** — wait for scope and include inputs
- ✋ **Step 5.4** — approval gate before `CREATE OR REPLACE TABLE`
