---
name: alter-catalog-integration
description: >
  Modify properties of an existing catalog integration for Apache Iceberg tables
---

# ALTER CATALOG INTEGRATION


Modifies the properties of an existing catalog integration. Only a limited set of properties can be altered: REST authentication credentials, the refresh interval, and the comment. To modify other properties (such as CATALOG_SOURCE, TABLE_FORMAT, CATALOG_URI, etc.), you must use CREATE OR REPLACE CATALOG INTEGRATION.

## Syntax

```sql
ALTER CATALOG INTEGRATION [ IF EXISTS ] <name> SET
  [ REST_AUTHENTICATION = (
    restAuthenticationParams
  ) ]
  [ REFRESH_INTERVAL_SECONDS = <value> ]
  [ COMMENT = '<string_literal>' ]
```

The `restAuthenticationParams` are as follows, depending on your authentication method:

**OAuth**

```sql
restAuthenticationParams (for OAuth) ::=

  OAUTH_CLIENT_SECRET = '<oauth_client_secret>'
```

**Bearer token**

```sql
restAuthenticationParams (for Bearer token) ::=

  BEARER_TOKEN = '<bearer_token>'
```

## Parameters

- **`<name>`**

  Specifies the identifier for the catalog integration to alter.

  If the identifier contains spaces or special characters, the entire string must be enclosed in double quotes. Identifiers enclosed in double quotes are also case-sensitive.

- **`SET ...`**

  Sets one or more specified properties or parameters for the catalog integration:

  - **`REST_AUTHENTICATION = ( restAuthenticationParams )`**

    Updates the authentication credentials for REST-based catalog integrations (Snowflake Open Catalog, Apache Iceberg REST). The specific parameters depend on the authentication method used when the integration was created.

  - **`REFRESH_INTERVAL_SECONDS = <value>`**

    Specifies the number of seconds that Snowflake waits between attempts to poll the external Iceberg catalog for metadata updates for automated refresh.

    For Delta-based tables, specifies the number of seconds that Snowflake waits between attempts to poll your external cloud storage for new metadata.

    Values: 30 to 86400, inclusive

    Default: 30 seconds

  - **`COMMENT = '<string_literal>'`**

    String (literal) that specifies a comment for the integration.

    Default: No value

### REST authentication parameters (restAuthenticationParams)

**OAuth**

**`OAUTH_CLIENT_SECRET = '<oauth_client_secret>'`**

Your OAuth2 client secret. Use this to rotate or update the client secret for integrations that use OAuth authentication (Snowflake Open Catalog or Apache Iceberg REST with TYPE = OAUTH).

**Bearer token**

**`BEARER_TOKEN = '<bearer_token>'`**

The bearer token for your identity provider. You can alternatively specify a personal access token (PAT). Use this to rotate or update the token for integrations that use bearer token authentication (Apache Iceberg REST with TYPE = BEARER).

## Access control requirements

A role used to execute this operation must have the following privileges at a minimum:

| Privilege | Object | Notes |
|---|---|---|
| OWNERSHIP | Integration (catalog) | OWNERSHIP is a special privilege on an object that is automatically granted to the role that created the object, but can also be transferred using the GRANT OWNERSHIP command to a different role by the owning role (or any role with the MANAGE GRANTS privilege). |

## Usage notes

- Only REST authentication credentials, REFRESH_INTERVAL_SECONDS, and COMMENT can be altered. To modify other integration properties (CATALOG_SOURCE, TABLE_FORMAT, GLUE_AWS_ROLE_ARN, CATALOG_URI, CATALOG_NAME, etc.), you must recreate the integration using CREATE OR REPLACE CATALOG INTEGRATION.

- This command does not support SET TAG, UNSET TAG, or UNSET syntax variants. Use SET to update the supported properties.

- This command applies to REST-based catalog integrations (Snowflake Open Catalog and Apache Iceberg REST). For AWS Glue and Object Storage catalog integrations, which do not use REST authentication, only REFRESH_INTERVAL_SECONDS and COMMENT can be altered.

- Regarding metadata:

**Attention**

Customers should ensure that no personal data (other than for a User object), sensitive data, export-controlled data, or other regulated data is entered as metadata when using the Snowflake service.

## Examples

Update the refresh interval for automated refresh to 60 seconds:

```sql
ALTER CATALOG INTEGRATION myCatalogIntegration SET REFRESH_INTERVAL_SECONDS = 60;
```

Rotate the OAuth client secret for a Snowflake Open Catalog integration:

```sql
ALTER CATALOG INTEGRATION my_open_catalog_int SET
  REST_AUTHENTICATION = (
    OAUTH_CLIENT_SECRET = 'new_client_secret_value'
  );
```

Update the bearer token for an Apache Iceberg REST integration:

```sql
ALTER CATALOG INTEGRATION my_rest_catalog_int SET
  REST_AUTHENTICATION = (
    BEARER_TOKEN = 'new-personal-access-token'
  );
```

Update both the refresh interval and comment:

```sql
ALTER CATALOG INTEGRATION myCatalogIntegration SET
  REFRESH_INTERVAL_SECONDS = 300
  COMMENT = 'Updated refresh interval to 5 minutes';
```
