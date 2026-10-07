---
name: create-integration
description: >
  Create a new integration (generic overview). Use a type-specific CREATE command when available
---

# CREATE INTEGRATION


Creates a new integration in the system or replaces an existing integration. An integration is a Snowflake object that provides an interface between Snowflake and third-party services.

## Syntax

```sql
CREATE [ OR REPLACE ] <integration_type> INTEGRATION [ IF NOT EXISTS ] <object_name>
  [ <integration_type_params> ]
  [ COMMENT = '<string_literal>' ]
```

Where `<integration_type_params>` are specific to the integration type.

For specific syntax, usage notes, and examples, see:

- CREATE API INTEGRATION
- CREATE CATALOG INTEGRATION
- CREATE EXTERNAL ACCESS INTEGRATION
- CREATE NOTIFICATION INTEGRATION
- CREATE SECURITY INTEGRATION
- CREATE STORAGE INTEGRATION

## General usage notes

- OR REPLACE and IF NOT EXISTS clauses are mutually exclusive; they cannot both be used in the same statement.
- CREATE OR REPLACE <object> statements are atomic. That is, when an object is replaced, the old object is deleted and the new object is created in a single transaction.
