# SQL Templates - Create Contacts

## Overview

This document contains SQL templates for creating contacts in Snowflake for data governance.

---

## Template 1: Create Contact with Email

```sql
CREATE CONTACT <database>.<schema>.<contact_name>
  EMAIL_DISTRIBUTION_LIST = '<email_address>';
```

**Example:**
```sql
CREATE CONTACT GOVERNANCE_DB.CONTACTS.data_stewards
  EMAIL_DISTRIBUTION_LIST = 'data_stewards@company.com';
```

---

## Template 2: Create Contact with URL

```sql
CREATE CONTACT <database>.<schema>.<contact_name>
  URL = '<support_url>';
```

**Example:**
```sql
CREATE CONTACT GOVERNANCE_DB.CONTACTS.tech_support
  URL = 'https://support.internal.com/data-help';
```

---

## Template 3: Create Contact with Users

```sql
CREATE CONTACT <database>.<schema>.<contact_name>
  USERS = ('<user1>', '<user2>', '<user3>');
```

**Example:**
```sql
CREATE CONTACT GOVERNANCE_DB.CONTACTS.analytics_team
  USERS = ('JOHN_DOE', 'JANE_SMITH', 'BOB_JONES');
```

---

## Template 4: Create Multiple Contacts (Batch)

```sql
-- Data Stewards
CREATE CONTACT GOVERNANCE_DB.CONTACTS.data_stewards
  EMAIL_DISTRIBUTION_LIST = 'stewards@company.com';

-- Technical Support
CREATE CONTACT GOVERNANCE_DB.CONTACTS.tech_support
  URL = 'https://support.company.com';

-- Access Approvers
CREATE CONTACT GOVERNANCE_DB.CONTACTS.access_approvers
  EMAIL_DISTRIBUTION_LIST = 'access_approvers@company.com';
```

---

## Notes

- **Contact Methods**: EMAIL_DISTRIBUTION_LIST, URL, or USERS
- **Required Privilege**: CREATE CONTACT on schema
- **Best Practice**: Create contacts in dedicated schema (e.g., GOVERNANCE_DB.CONTACTS)
- **Naming Convention**: Use descriptive names (data_stewards, tech_support, etc.)
