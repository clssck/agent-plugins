---
name: drop-integration
description: >
  Remove any type of integration from the Snowflake account. Syntax: DROP <type> INTEGRATION <name>
---

# DROP INTEGRATION


Removes an integration from the account.

## Syntax

```sql
DROP { API | CATALOG | EXTERNAL ACCESS | NOTIFICATION | SECURITY | STORAGE } INTEGRATION [ IF EXISTS ] <name>
```

## Parameters

- **{ API | CATALOG | EXTERNAL ACCESS | NOTIFICATION | SECURITY | STORAGE }** (Required)

  Specifies the integration type. **Always include the type qualifier** (e.g., `DROP STORAGE INTEGRATION my_int`, `DROP CATALOG INTEGRATION IF EXISTS my_int`). While the syntax technically allows omitting the type, you should always specify it when the integration type is known.

- **<name>**

  Specifies the identifier for the integration to drop. If the identifier contains spaces, special characters, or mixed-case characters, the entire string must be enclosed in double quotes. Identifiers enclosed in double quotes are also case-sensitive (e.g. "My Object").

## Usage notes

- Dropped integrations cannot be recovered; they must be recreated.
- Disabling or dropping the integrations may not take effect immediately, since integrations may be cached. It is recommended to remove the integration privilege from the cloud provider to take effect sooner.
- When the IF EXISTS clause is specified and the target object doesn't exist, the command completes successfully without returning an error.

## Examples

Drop a storage integration:

```sql
SHOW STORAGE INTEGRATIONS LIKE 't2%';

DROP STORAGE INTEGRATION t2;

SHOW STORAGE INTEGRATIONS LIKE 't2%';
```

Drop a catalog integration, but don't raise an error if the integration does not exist:

```sql
DROP CATALOG INTEGRATION IF EXISTS t2;
```
