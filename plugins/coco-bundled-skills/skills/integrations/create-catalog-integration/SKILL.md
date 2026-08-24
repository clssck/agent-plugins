---
name: create-catalog-integration
description: >
  Create a new catalog integration for Apache Iceberg tables (AWS Glue, Object Store, Snowflake Open Catalog, Apache Iceberg REST, or SAP Business Data Cloud)
---

# CREATE CATALOG INTEGRATION


Creates a new catalog integration in the account or replaces an existing catalog integration. A catalog integration allows Snowflake to interact with external Apache Iceberg catalogs, enabling the creation and management of Iceberg tables backed by external catalog metadata.

The syntax depends on the type of external Iceberg catalog that you use. Snowflake supports five catalog sources: AWS Glue, Object Storage, Snowflake Open Catalog (Polaris), Apache Iceberg REST, and SAP Business Data Cloud.

## Syntax

**AWS Glue**

```sql
CREATE [ OR REPLACE ] CATALOG INTEGRATION [IF NOT EXISTS]
  <name>
  CATALOG_SOURCE = GLUE
  TABLE_FORMAT = ICEBERG
  GLUE_AWS_ROLE_ARN = '<arn-for-AWS-role-to-assume>'
  GLUE_CATALOG_ID = '<glue-catalog-id>'
  [ GLUE_REGION = '<AWS-region-of-the-glue-catalog>' ]
  [ CATALOG_NAMESPACE = '<catalog-namespace>' ]
  ENABLED = { TRUE | FALSE }
  [ REFRESH_INTERVAL_SECONDS = <value> ]
  [ COMMENT = '<string_literal>' ]
```

**Object Storage**

```sql
CREATE [ OR REPLACE ] CATALOG INTEGRATION [IF NOT EXISTS]
  <name>
  CATALOG_SOURCE = OBJECT_STORE
  TABLE_FORMAT = { ICEBERG | DELTA }
  ENABLED = { TRUE | FALSE }
  [ REFRESH_INTERVAL_SECONDS = <value> ]
  [ COMMENT = '<string_literal>' ]
```

**Snowflake Open Catalog (Polaris)**

```sql
CREATE [ OR REPLACE ] CATALOG INTEGRATION [IF NOT EXISTS]
  <name>
  CATALOG_SOURCE = POLARIS
  TABLE_FORMAT = ICEBERG
  [ CATALOG_NAMESPACE = '<open_catalog_namespace>' ]
  REST_CONFIG = (
    CATALOG_URI = '<open_catalog_account_url>'
    [ CATALOG_API_TYPE = { PUBLIC | PRIVATE } ]
    CATALOG_NAME = '<open_catalog_catalog_name>'
    [ ACCESS_DELEGATION_MODE = { VENDED_CREDENTIALS | EXTERNAL_VOLUME_CREDENTIALS } ]
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    [ OAUTH_TOKEN_URI = 'https://<token_server_uri>' ]
    OAUTH_CLIENT_ID = '<oauth_client_id>'
    OAUTH_CLIENT_SECRET = '<oauth_secret>'
    OAUTH_ALLOWED_SCOPES = ('<scope 1>' [ , '<scope 2>' ... ] )
  )
  ENABLED = { TRUE | FALSE }
  [ REFRESH_INTERVAL_SECONDS = <value> ]
  [ COMMENT = '<string_literal>' ]
```

**Apache Iceberg REST**

```sql
CREATE [ OR REPLACE ] CATALOG INTEGRATION [IF NOT EXISTS]
  <name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  [ CATALOG_NAMESPACE = '<namespace>' ]
  REST_CONFIG = (
    CATALOG_URI = '<rest_api_endpoint_url>'
    [ PREFIX = '<prefix>' ]
    [ CATALOG_NAME = '<catalog_name>' ]
    [ CATALOG_API_TYPE = { PUBLIC | PRIVATE | AWS_API_GATEWAY | AWS_PRIVATE_API_GATEWAY | AWS_GLUE | AWS_PRIVATE_GLUE } ]
    [ ACCESS_DELEGATION_MODE = { VENDED_CREDENTIALS | EXTERNAL_VOLUME_CREDENTIALS } ]
  )
  REST_AUTHENTICATION = (
    restAuthenticationParams
  )
  ENABLED = { TRUE | FALSE }
  [ REFRESH_INTERVAL_SECONDS = <value> ]
  [ COMMENT = '<string_literal>' ]
```

Where:

```sql
restAuthenticationParams (for OAuth) ::=
  TYPE = OAUTH
  [ OAUTH_TOKEN_URI = 'https://<token_server_uri>' ]
  OAUTH_CLIENT_ID = '<oauth_client_id>'
  OAUTH_CLIENT_SECRET = '<oauth_client_secret>'
  OAUTH_ALLOWED_SCOPES = ('<scope_1>' [ , '<scope_2>' ... ] )
```

```sql
restAuthenticationParams (for Bearer token) ::=
  TYPE = BEARER
  BEARER_TOKEN = '<bearer_token>'
```

```sql
restAuthenticationParams (for SigV4) ::=
  TYPE = SIGV4
  SIGV4_IAM_ROLE = '<iam_role_arn>'
  [ SIGV4_SIGNING_REGION = '<region>' ]
  [ SIGV4_EXTERNAL_ID = '<external_id>' ]
```

**SAP Business Data Cloud**

```sql
CREATE [ OR REPLACE ] CATALOG INTEGRATION [IF NOT EXISTS]
  <name>
  CATALOG_SOURCE = SAP_BDC
  TABLE_FORMAT = DELTA
  REST_CONFIG = (
    SAP_BDC_INVITATION_LINK = '<invitation_link_from_sap_bdc>'
    [ ACCESS_DELEGATION_MODE = { VENDED_CREDENTIALS } ]
  )
  ENABLED = { TRUE | FALSE }
  [ REFRESH_INTERVAL_SECONDS = <value> ]
  [ COMMENT = '<string_literal>' ]
```

## Required parameters

- **<name>**
  String that specifies the identifier (i.e. name) for the integration; must be unique in your account.
  In addition, the identifier must start with an alphabetic character and cannot contain spaces or special characters unless the entire identifier string is enclosed in double quotes (e.g. `"My object"`). Identifiers enclosed in double quotes are also case-sensitive.

- **CATALOG_SOURCE = { GLUE | OBJECT_STORE | POLARIS | ICEBERG_REST | SAP_BDC }**
  Specifies the type of external Iceberg catalog:
  - `GLUE`: AWS Glue Data Catalog.
  - `OBJECT_STORE`: External Iceberg metadata files or Delta files in object storage.
  - `POLARIS`: Snowflake Open Catalog.
  - `ICEBERG_REST`: A REST catalog compliant with the Apache Iceberg REST specification.
  - `SAP_BDC`: SAP Business Data Cloud.

- **TABLE_FORMAT = { ICEBERG | DELTA }**
  Specifies the table format from the catalog:
  - `ICEBERG`: For Apache Iceberg tables. Required for GLUE, POLARIS, and ICEBERG_REST catalog sources.
  - `DELTA`: For Delta tables. Required for SAP_BDC. Also supported with OBJECT_STORE.

- **ENABLED = { TRUE | FALSE }**
  Specifies whether this catalog integration is available for usage in Iceberg tables.
  - `TRUE` allows users to create new Iceberg tables that reference this integration. Existing tables that reference this integration function normally.
  - `FALSE` prevents users from creating new Iceberg tables that reference this integration. Existing tables that reference this integration cannot access the catalog definition.

## AWS Glue parameters

- **GLUE_AWS_ROLE_ARN = '<arn-for-AWS-role-to-assume>'** (required)
  The Amazon Resource Name (ARN) of an IAM role that Snowflake assumes to access your Glue Data Catalog. Additional AWS configuration steps are necessary to establish a trust relationship between Snowflake and the IAM role.

- **GLUE_CATALOG_ID = '<glue-catalog-id>'** (required)
  Your AWS account ID where the Glue Data Catalog resides.

- **GLUE_REGION = '<AWS-region-of-the-glue-catalog>'** (optional)
  The AWS region hosting your Glue Data Catalog. Required if your Snowflake account is not hosted on AWS; otherwise defaults to your Snowflake deployment region.

## REST config parameters (for Snowflake Open Catalog)

- **CATALOG_URI = '<open_catalog_account_url>'** (required)
  The Open Catalog account URL. For PUBLIC API type: `https://<orgname>-<account-name>.snowflakecomputing.com/polaris/api/catalog` or `https://<locator>.<region>.<cloud>.snowflakecomputing.com/polaris/api/catalog`. For PRIVATE API type: `https://<privatelink-url>/polaris/api/catalog`.

- **CATALOG_NAME = '<open_catalog_catalog_name>'** (required)
  The catalog identifier within Open Catalog to use.

- **CATALOG_API_TYPE = { PUBLIC | PRIVATE }** (optional)
  The connection method. `PUBLIC` routes through the internet. `PRIVATE` uses private IP addresses for inbound traffic. Required when using private connectivity.
  Default: `PUBLIC`

- **ACCESS_DELEGATION_MODE = { VENDED_CREDENTIALS | EXTERNAL_VOLUME_CREDENTIALS }** (optional)
  The access method for Iceberg files. `VENDED_CREDENTIALS` uses Snowflake-issued credentials from the catalog. `EXTERNAL_VOLUME_CREDENTIALS` uses an external volume for file access.
  Default: `EXTERNAL_VOLUME_CREDENTIALS`

## REST config parameters (for Apache Iceberg REST)

- **CATALOG_URI = '<rest_api_endpoint_url>'** (required)
  The endpoint URL for your catalog REST API.

- **PREFIX = '<prefix>'** (optional)
  A prefix appended to all API routes.

- **CATALOG_NAME = '<catalog_name>'** (optional)
  The catalog or identifier from the remote catalog service. For AWS_GLUE API type, this is the AWS account ID.

- **CATALOG_API_TYPE = { PUBLIC | PRIVATE | AWS_API_GATEWAY | AWS_PRIVATE_API_GATEWAY | AWS_GLUE | AWS_PRIVATE_GLUE }** (optional)
  The connection type:
  - `PUBLIC`: Non-SigV4, routes through the internet.
  - `PRIVATE`: Uses a private endpoint.
  - `AWS_API_GATEWAY`: AWS API Gateway endpoint.
  - `AWS_PRIVATE_API_GATEWAY`: AWS private API Gateway endpoint.
  - `AWS_GLUE`: AWS Glue via REST API.
  - `AWS_PRIVATE_GLUE`: AWS Glue via private REST API.
  Default: `PUBLIC`

- **ACCESS_DELEGATION_MODE = { VENDED_CREDENTIALS | EXTERNAL_VOLUME_CREDENTIALS }** (optional)
  The access method for Iceberg files. `VENDED_CREDENTIALS` uses Snowflake-issued credentials from the catalog. `EXTERNAL_VOLUME_CREDENTIALS` uses an external volume for file access.
  Default: `EXTERNAL_VOLUME_CREDENTIALS`

## REST authentication parameters

**OAuth** (for Snowflake Open Catalog and Apache Iceberg REST)

- **TYPE = OAUTH** (required)
  Specifies OAuth as the authentication mechanism.

- **OAUTH_TOKEN_URI = 'https://<token_server_uri>'** (optional)
  URL for a third-party identity provider. If omitted, Snowflake assumes the remote catalog provider handles identity.

- **OAUTH_CLIENT_ID = '<oauth_client_id>'** (required)
  Your OAuth2 client identifier.

- **OAUTH_CLIENT_SECRET = '<oauth_client_secret>'** (required)
  Your OAuth2 client secret.

- **OAUTH_ALLOWED_SCOPES = ('<scope_1>' [ , '<scope_2>' ... ] )** (required)
  One or more OAuth token scopes as a list (e.g., `('PRINCIPAL_ROLE:ALL')`).

**Bearer token** (for Apache Iceberg REST)

- **TYPE = BEARER** (required)
  Specifies bearer token authentication.

- **BEARER_TOKEN = '<bearer_token>'** (required)
  The bearer token for your identity provider. You can alternatively specify a personal access token (PAT).

**SigV4** (for Apache Iceberg REST with AWS)

- **TYPE = SIGV4** (required)
  Specifies AWS Signature Version 4 authentication.

- **SIGV4_IAM_ROLE = '<iam_role_arn>'** (required)
  The Amazon Resource Name (ARN) for an IAM role that has permission to access your REST API in API Gateway.

- **SIGV4_SIGNING_REGION = '<region>'** (optional)
  The AWS region for signing requests. Defaults to the Snowflake account region.

- **SIGV4_EXTERNAL_ID = '<external_id>'** (optional)
  An external ID for establishing a trust relationship with AWS. Auto-generated if omitted.

## SAP Business Data Cloud parameters

- **SAP_BDC_INVITATION_LINK = '<invitation_link_from_sap_bdc>'** (required)
  The invitation link obtained from SAP 4 Me as documented in Provisioning SAP Business Data Cloud Connect.

- **ACCESS_DELEGATION_MODE = { VENDED_CREDENTIALS }** (optional)
  Access delegation method. Currently only `VENDED_CREDENTIALS` is supported for SAP BDC.

## Optional parameters (common)

- **CATALOG_NAMESPACE = '<namespace>'**
  Default namespace for associated Iceberg tables. Can be overridden at table creation. Must be specified at the table level if omitted here.
  Applies to: GLUE, POLARIS, ICEBERG_REST.
  For Snowflake Open Catalog when syncing Snowflake-managed tables to external catalogs, Snowflake applies a predefined naming rule (e.g., `db1.public.table1` becomes `catalog1.db1.public.table1`).

- **REFRESH_INTERVAL_SECONDS = <value>**
  Specifies the number of seconds that Snowflake waits between attempts to poll the external Iceberg catalog for metadata updates for automated refresh. For Delta-based tables, specifies the polling interval for new metadata in external cloud storage.
  Values: 30 to 86400, inclusive.
  Default: 30 seconds.
  Note: For OBJECT_STORE, this parameter is only supported when TABLE_FORMAT = DELTA.

- **COMMENT = '<string_literal>'**
  String (literal) that specifies a comment for the integration.
  Default: No value

## Access control requirements

A role used to execute this operation must have the following privileges at a minimum:

| Privilege | Object | Notes |
|---|---|---|
| CREATE INTEGRATION | Account | Only the ACCOUNTADMIN role has this privilege by default. The privilege can be granted to additional roles as needed. |

## Usage notes

- Catalog integrations provide read-only access to external Iceberg catalogs.

- Existing catalog integrations cannot be modified directly (except through ALTER CATALOG INTEGRATION for limited properties). Use `CREATE OR REPLACE` to make changes to most properties.

- Cannot drop or replace a catalog integration that has associated Iceberg tables. Use `SHOW ICEBERG TABLES` and filter on the case-sensitive `"catalog_name"` column to identify dependent tables.

- The OR REPLACE and IF NOT EXISTS clauses are mutually exclusive. They cannot both be used in the same statement.

- CREATE OR REPLACE <object> statements are atomic. That is, when an object is replaced, the old object is deleted and the new object is created in a single transaction.

- For Snowflake Open Catalog: when using External OAuth with CATALOG_API_TYPE = PRIVATE, token requests traverse the public internet.

- For AWS Glue: additional AWS configuration steps are necessary to establish a Snowflake-to-Glue trust relationship.

Regarding metadata:

Attention

Customers should ensure that no personal data (other than for a User object), sensitive data, export-controlled data, or other regulated data is entered as metadata when using the Snowflake service. For more information, see Metadata fields in Snowflake.

## Examples

**AWS Glue**

```sql
CREATE CATALOG INTEGRATION glueCatalogInt
  CATALOG_SOURCE = GLUE
  CATALOG_NAMESPACE = 'myGlueDatabase'
  TABLE_FORMAT = ICEBERG
  GLUE_AWS_ROLE_ARN = 'arn:aws:iam::123456789012:role/myGlueRole'
  GLUE_CATALOG_ID = '123456789012'
  GLUE_REGION = 'us-east-2'
  ENABLED = TRUE;
```

**Object Storage (Iceberg)**

```sql
CREATE CATALOG INTEGRATION myCatalogInt
  CATALOG_SOURCE = OBJECT_STORE
  TABLE_FORMAT = ICEBERG
  ENABLED = TRUE;
```

**Object Storage (Delta)**

```sql
CREATE CATALOG INTEGRATION myDeltaCatalogInt
  CATALOG_SOURCE = OBJECT_STORE
  TABLE_FORMAT = DELTA
  ENABLED = TRUE;
```

**Snowflake Open Catalog (querying tables in a namespace)**

```sql
CREATE OR REPLACE CATALOG INTEGRATION open_catalog_int
  CATALOG_SOURCE = POLARIS
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = 'my_catalog_namespace'
  REST_CONFIG = (
    CATALOG_URI = 'https://my_org_name-my_snowflake_open_catalog_account_name.snowflakecomputing.com/polaris/api/catalog'
    CATALOG_NAME = 'my_catalog_name'
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    OAUTH_CLIENT_ID = 'my_client_id'
    OAUTH_CLIENT_SECRET = 'my_client_secret'
    OAUTH_ALLOWED_SCOPES = ('PRINCIPAL_ROLE:ALL')
  )
  ENABLED = TRUE;
```

**Snowflake Open Catalog (syncing Snowflake-managed tables to external catalog)**

```sql
CREATE OR REPLACE CATALOG INTEGRATION open_catalog_int2
  CATALOG_SOURCE = POLARIS
  TABLE_FORMAT = ICEBERG
  REST_CONFIG = (
    CATALOG_URI = 'https://my_org_name-my_snowflake_open_catalog_account_name.snowflakecomputing.com/polaris/api/catalog'
    CATALOG_NAME = 'customers'
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    OAUTH_CLIENT_ID = 'my_client_id'
    OAUTH_CLIENT_SECRET = 'my_client_secret'
    OAUTH_ALLOWED_SCOPES = ('PRINCIPAL_ROLE:my-principal-role', 'PRINCIPAL_ROLE:my-principal-role2', 'PRINCIPAL_ROLE:my-principal-role3')
  )
  ENABLED = TRUE;
```

**Apache Iceberg REST with OAuth (Tabular)**

```sql
CREATE OR REPLACE CATALOG INTEGRATION tabular_catalog_int
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = 'default'
  REST_CONFIG = (
    CATALOG_URI = 'https://api.tabular.io/ws'
    CATALOG_NAME = '<tabular_warehouse_name>'
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    OAUTH_TOKEN_URI = 'https://api.tabular.io/ws/v1/oauth/tokens'
    OAUTH_CLIENT_ID = '<oauth_client_id>'
    OAUTH_CLIENT_SECRET = '<oauth_client_secret>'
    OAUTH_ALLOWED_SCOPES = ('catalog')
  )
  ENABLED = TRUE;
```

**Apache Iceberg REST with SigV4 (AWS Glue REST)**

```sql
CREATE CATALOG INTEGRATION glue_rest_catalog_int
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = 'rest_catalog_integration'
  REST_CONFIG = (
    CATALOG_URI = 'https://glue.us-west-2.amazonaws.com/iceberg'
    CATALOG_API_TYPE = AWS_GLUE
    CATALOG_NAME = '123456789012'
  )
  REST_AUTHENTICATION = (
    TYPE = SIGV4
    SIGV4_IAM_ROLE = 'arn:aws:iam::123456789012:role/my-role'
    SIGV4_SIGNING_REGION = 'us-west-2'
  )
  ENABLED = TRUE;
```

**Apache Iceberg REST with Bearer token**

```sql
CREATE CATALOG INTEGRATION my_rest_catalog_int
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = 'my_namespace'
  REST_CONFIG = (
    CATALOG_URI = 'https://my-catalog-server.example.com/api/v1'
  )
  REST_AUTHENTICATION = (
    TYPE = BEARER
    BEARER_TOKEN = 'my-personal-access-token'
  )
  ENABLED = TRUE;
```

**SAP Business Data Cloud**

```sql
CREATE OR REPLACE CATALOG INTEGRATION my_sap_bdc_catalog_int
  CATALOG_SOURCE = SAP_BDC
  TABLE_FORMAT = DELTA
  REST_CONFIG = (
    SAP_BDC_INVITATION_LINK = '<Invitation URL from SAP BDC>'
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  ENABLED = TRUE
  COMMENT = 'My SAP BDC catalog integration';
```
