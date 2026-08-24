---
name: show-integrations
description: >
  List integrations in the account, optionally filtered by type. Syntax: SHOW <type> INTEGRATIONS
---

# SHOW INTEGRATIONS


Lists the integrations in your account.

The output returns integration metadata and properties.

## Syntax

```sql
SHOW { API | CATALOG | EXTERNAL ACCESS | NOTIFICATION | SECURITY | STORAGE } INTEGRATIONS [ LIKE '<pattern>' ]
```

## Parameters

- **{ API | CATALOG | EXTERNAL ACCESS | NOTIFICATION | SECURITY | STORAGE }** (Required)

  Specifies the integration type. **Always include the type qualifier** (e.g., `SHOW STORAGE INTEGRATIONS`, `SHOW NOTIFICATION INTEGRATIONS`). While the syntax technically allows omitting the type, you should always specify it when the integration type is known.

- **LIKE '<pattern>'**

  Optionally filters the command output by object name. The filter uses case-insensitive pattern matching, with support for SQL wildcard characters (% and _).

  For example, the following patterns return the same results:

  - `LIKE '%testing%'`
  - `LIKE '%TESTING%'`

  Default: No value (no filtering is applied to the output).

## Access control requirements

A role used to execute this SQL command must have at least one of the following privileges at a minimum:

| Privilege | Object | Notes |
|-----------|--------|-------|
| USAGE | Integration | |
| OWNERSHIP | Integration | OWNERSHIP is a special privilege on an object that is automatically granted to the role that created the object, but can also be transferred using the GRANT OWNERSHIP command to a different role by the owning role (or any role with the MANAGE GRANTS privilege). |

## Usage notes

- **Always specify the integration type** when it is known (e.g., `SHOW CATALOG INTEGRATIONS`, not just `SHOW INTEGRATIONS`).
- The command doesn't require a running warehouse to execute.
- The command only returns objects for which the current user's current role has been granted at least one access privilege.
- The MANAGE GRANTS access privilege implicitly allows its holder to see every object in the account. By default, only the account administrator (users with the ACCOUNTADMIN role) and security administrator (users with the SECURITYADMIN role) have the MANAGE GRANTS privilege.
- To post-process the output of this command, you can use the pipe operator (->>) or the RESULT_SCAN function. Both constructs treat the output as a result set that you can query.
- When you refer to the output columns, use double-quoted identifiers for the column names. For example, to select the output column type, specify `SELECT "type"`.

## Output

The command output provides integration properties and metadata in the following columns:

| Column | Description |
|--------|-------------|
| name | Name of the integration |
| type | Type of the integration |
| category | Category of the integration |
| enabled | Current status of the integration, either TRUE (enabled) or FALSE (disabled) |
| comment | Comment for the integration |
| created_on | Date and time when the integration was created |

## Examples

Show all notification integrations:

```sql
SHOW NOTIFICATION INTEGRATIONS;
```

Show all the integrations whose name starts with line that you have privileges to view:

```sql
SHOW INTEGRATIONS LIKE 'line%';
```
