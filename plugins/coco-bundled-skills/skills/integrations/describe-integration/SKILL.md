---
name: describe-integration
description: >
  Describe the properties of a specific integration of any type
---

# DESCRIBE INTEGRATION


Describes the properties of an integration.

DESCRIBE can be abbreviated to DESC.

## Syntax

```sql
{ DESC | DESCRIBE } { API | CATALOG | EXTERNAL ACCESS | NOTIFICATION | SECURITY | STORAGE } INTEGRATION <name>
```

## Parameters

- **{ API | CATALOG | EXTERNAL ACCESS | NOTIFICATION | SECURITY | STORAGE }** (Required)

  Specifies the integration type. **Always include the type qualifier** (e.g., `DESCRIBE STORAGE INTEGRATION my_int`, `DESC NOTIFICATION INTEGRATION my_int`). While the syntax technically allows omitting the type, you should always specify it when the integration type is known.

- **<name>**

  Specifies the identifier for the integration to describe. If the identifier contains spaces or special characters, the entire string must be enclosed in double quotes. Identifiers enclosed in double quotes are also case-sensitive.

## Usage notes

- To post-process the output of this command, you can use the pipe operator (->>) or the RESULT_SCAN function. Both constructs treat the output as a result set that you can query.
- When you refer to the output columns, use double-quoted identifiers for the column names. For example, to select the output column type, specify `SELECT "type"`.
- If the integration is an API integration, then the output includes the API_KEY column. The API_KEY displays a masked value if an API key was entered. (This does not display either the original unencrypted key or the encrypted version of the key.)
- If the security integration has the TYPE property set to OAUTH (i.e. Snowflake OAuth), Snowflake returns two additional security integration properties in the query result that cannot be set with either a CREATE SECURITY INTEGRATION or an ALTER SECURITY INTEGRATION command:
  - OAUTH_ALLOWED_AUTHORIZATION_ENDPOINTS - A list of all supported endpoints for a client application to receive an authorization code from Snowflake.
  - OAUTH_ALLOWED_TOKEN_ENDPOINTS - A list of all supported endpoints for a client application to exchange an authorization code for an access token or to obtain a refresh token.

## Examples

Describe the properties of a storage integration named my_int:

```sql
DESC STORAGE INTEGRATION my_int;
```

Describe the properties of a notification integration:

```sql
DESCRIBE NOTIFICATION INTEGRATION my_alerts;
```
