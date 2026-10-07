# SQL Templates - Assign Contacts

## Overview

This document contains SQL templates for assigning contacts to Snowflake objects.

---

## Template 5: Assign Contact to Table

```sql
ALTER TABLE <database>.<schema>.<table_name>
  SET CONTACT <purpose> = <contact_name>;
```

**Example:**
```sql
ALTER TABLE ANALYTICS_DB.SALES.CUSTOMERS
  SET CONTACT STEWARD = GOVERNANCE_DB.CONTACTS.data_stewards;
```

---

## Template 6: Assign Contact to Schema (Inheritance)

```sql
ALTER SCHEMA <database>.<schema>
  SET CONTACT <purpose> = <contact_name>;
```

**Example:**
```sql
-- All tables in SALES schema inherit data_stewards contact
ALTER SCHEMA ANALYTICS_DB.SALES
  SET CONTACT STEWARD = GOVERNANCE_DB.CONTACTS.data_stewards;
```

---

## Template 7: Assign Contact to Database (Broad Inheritance)

```sql
ALTER DATABASE <database>
  SET CONTACT <purpose> = <contact_name>;
```

**Example:**
```sql
-- All schemas and tables in ANALYTICS_DB inherit this contact
ALTER DATABASE ANALYTICS_DB
  SET CONTACT SUPPORT = GOVERNANCE_DB.CONTACTS.tech_support;
```

---

## Template 8: Assign Multiple Contacts (All Purposes)

```sql
ALTER TABLE <database>.<schema>.<table_name>
  SET CONTACT 
    STEWARD = <steward_contact>,
    SUPPORT = <support_contact>,
    ACCESS_APPROVAL = <approval_contact>;
```

**Example:**
```sql
ALTER TABLE ANALYTICS_DB.SALES.CUSTOMERS
  SET CONTACT 
    STEWARD = GOVERNANCE_DB.CONTACTS.data_stewards,
    SUPPORT = GOVERNANCE_DB.CONTACTS.tech_support,
    ACCESS_APPROVAL = GOVERNANCE_DB.CONTACTS.access_approvers;
```

---

## Template 9: Batch Assign to Multiple Tables

```sql
-- Assign steward to all tables in a schema.
-- Uses ACCOUNT_USAGE.TABLES for consistency with the rest of this skill.
-- Fallback: if the role lacks SNOWFLAKE.ACCOUNT_USAGE access, replace with
--   INFORMATION_SCHEMA.TABLES (same columns, but scoped to the current database).
BEGIN
  LET tables CURSOR FOR 
    SELECT table_name 
    FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES 
    WHERE table_catalog = '<database>'
      AND table_schema = '<schema>' 
      AND table_type = 'BASE TABLE'
      AND deleted IS NULL;
  
  FOR table_rec IN tables DO
    LET sql := 'ALTER TABLE <database>.<schema>.' || table_rec.table_name || 
               ' SET CONTACT STEWARD = <contact_name>';
    EXECUTE IMMEDIATE :sql;
  END FOR;
END;
```

---

## Contact Purposes

| Purpose | SQL Value | Description |
|---------|-----------|-------------|
| **Steward** | `STEWARD` | Data accuracy, consistency, reliability |
| **Support** | `SUPPORT` | Technical support |
| **Access Approval** | `ACCESS_APPROVAL` | Access request approval |

---

## Inheritance vs Direct Assignment

### Schema/Database Level (Inheritance)
✅ All current objects inherit automatically  
✅ All future objects inherit automatically  
✅ Easy to manage at scale  
✅ Single point of control  

**Use when:** You want consistent governance across multiple objects

### Table/View Level (Direct)
✅ Specific control per object  
✅ Override inherited contacts  
✅ Fine-grained management  

**Use when:** You need different contacts for specific objects

---

## Notes

- **Required Privilege**: APPLY CONTACT on account OR (APPLY on contact + OWNERSHIP on object)
- **Inheritance**: Database → Schema → Table/View
- **Override**: Direct assignment overrides inherited contact with same purpose
- **Best Practice**: Use schema/database level for consistency, direct for exceptions
