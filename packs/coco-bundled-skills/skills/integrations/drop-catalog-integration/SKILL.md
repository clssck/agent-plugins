---
name: drop-catalog-integration
description: >
  Remove a catalog integration from the Snowflake account
---

# DROP CATALOG INTEGRATION


Removes a catalog integration from the account.

## Syntax

```sql
DROP CATALOG INTEGRATION [ IF EXISTS ] <name>
```

## Parameters

- **`<name>`**

  Specifies the identifier for the catalog integration to drop. If the identifier contains spaces, special characters, or mixed-case characters, the entire string must be enclosed in double quotes. Identifiers enclosed in double quotes are also case-sensitive (for example, `"My Catalog"`).

## Access control requirements

A role used to execute this operation must have the following privileges at a minimum:

| Privilege | Object | Notes |
|---|---|---|
| OWNERSHIP | Integration (catalog) | OWNERSHIP is a special privilege on an object that is automatically granted to the role that created the object, but can also be transferred using the GRANT OWNERSHIP command to a different role by the owning role (or any role with the MANAGE GRANTS privilege). |

## Usage notes

- Dropped catalog integrations cannot be recovered; they must be recreated.

- When the IF EXISTS clause is specified and the target object does not exist, the command completes successfully without returning an error.

- You cannot drop or replace a catalog integration if one or more Apache Iceberg tables are associated with the catalog integration.

  To view the tables that depend on a catalog integration, you can use the SHOW ICEBERG TABLES command and a query using the pipe operator (`->>`) that filters on the `catalog_name` column.

  **Note**

  The column identifier (`catalog_name`) is case-sensitive. Specify the column identifier exactly as it appears in the SHOW ICEBERG TABLES output.

  For example:

  ```sql
  SHOW ICEBERG TABLES
    ->> SELECT *
          FROM $1
          WHERE "catalog_name" = 'my_catalog_integration_1';
  ```

## Examples

Drop a catalog integration:

```sql
DROP CATALOG INTEGRATION myInt;
```

Drop the catalog integration again, but do not raise an error if the integration does not exist:

```sql
DROP CATALOG INTEGRATION IF EXISTS myInt;
```
