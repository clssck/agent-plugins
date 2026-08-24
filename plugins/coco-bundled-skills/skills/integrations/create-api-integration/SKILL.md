---
name: create-api-integration
description: >
  Create a new API integration for AWS API Gateway, Azure API Management, Google Cloud API Gateway, or Git repositories
---

# CREATE API INTEGRATION


Creates a new API integration object in the account or replaces an existing API integration.

An API integration object stores information about a service reached via HTTPS API, including information about some of the following:

- A cloud platform provider (such as Amazon AWS).

- A Git repository API.

- The type of service (such as when a cloud platform provider offers more than one type of proxy service).

- The identifier and access credentials for the external service that has sufficient privileges to use the service. For example, on AWS, the role's ARN (Amazon resource name) serves as the identifier and access credentials.

When this user is granted appropriate privileges, Snowflake can use this user to access resources. For example, this might be an instance of the cloud platform's native HTTPS proxy service, for example, an instance of an Amazon API Gateway.

An API integration object also specifies allowed (and optionally blocked) endpoints and resources on those services.

## Syntax

The syntax is different for each external API.

### For Amazon API Gateway

```sql
CREATE [ OR REPLACE ] API INTEGRATION [ IF NOT EXISTS ] <integration_name>
  API_PROVIDER = { aws_api_gateway | aws_private_api_gateway | aws_gov_api_gateway | aws_gov_private_api_gateway }
  API_AWS_ROLE_ARN = '<iam_role>'
  [ API_KEY = '<api_key>' ]
  API_ALLOWED_PREFIXES = ('<...>')
  ENABLED = { TRUE | FALSE }
  [ COMMENT = '<string_literal>' ]
  ;
```

Note that `aws_api_gateway` or `aws_private_api_gateway` or `aws_gov_api_gateway` or `aws_gov_private_api_gateway` should not be in quotation marks.

### For Azure API Management

```sql
CREATE [ OR REPLACE ] API INTEGRATION [ IF NOT EXISTS ] <integration_name>
  API_PROVIDER = azure_api_management
  AZURE_TENANT_ID = '<tenant_id>'
  AZURE_AD_APPLICATION_ID = '<azure_application_id>'
  [ API_KEY = '<api_key>' ]
  API_ALLOWED_PREFIXES = ( '<...>' )
  [ API_BLOCKED_PREFIXES = ( '<...>' ) ]
  ENABLED = { TRUE | FALSE }
  [ COMMENT = '<string_literal>' ]
  ;
```

Note that `azure_api_management` should not be in quotation marks.

### For Google Cloud API Gateway

```sql
CREATE [ OR REPLACE ] API INTEGRATION [ IF NOT EXISTS ] <integration_name>
  API_PROVIDER = google_api_gateway
  GOOGLE_AUDIENCE = '<google_audience_claim>'
  API_ALLOWED_PREFIXES = ( '<...>' )
  [ API_BLOCKED_PREFIXES = ( '<...>' ) ]
  ENABLED = { TRUE | FALSE }
  [ COMMENT = '<string_literal>' ]
  ;
```

Note that `google_api_gateway` should not be in quotation marks.

### For Git repository

When integrating with a Git repository, you can use a personal access token or OAuth.

OAuth support is generally available only when the repository is hosted at github.com.

OAuth support is in preview for repository providers other than github.com.

```sql
CREATE [ OR REPLACE ] API INTEGRATION [ IF NOT EXISTS ] <integration_name>
  API_PROVIDER = git_https_api
  API_ALLOWED_PREFIXES = ('<...>')
  [ API_BLOCKED_PREFIXES = ('<...>') ]
  [ ALLOWED_AUTHENTICATION_SECRETS = ( { <secret_name> [, <secret_name>, ... ] } ) | all | none ]
  ENABLED = { TRUE | FALSE }
  [ COMMENT = '<string_literal>' ]
  ;
```

```sql
CREATE [ OR REPLACE ] API INTEGRATION [ IF NOT EXISTS ] <integration_name>
  API_PROVIDER = git_https_api
  API_ALLOWED_PREFIXES = ('https://github.com/<...>')
  [ API_BLOCKED_PREFIXES = ('<...>') ]
  API_USER_AUTHENTICATION = (
    TYPE = SNOWFLAKE_GITHUB_APP
  )
  ENABLED = { TRUE | FALSE }
  [ COMMENT = '<string_literal>' ]
  ;
```

```sql
CREATE [ OR REPLACE ] API INTEGRATION [ IF NOT EXISTS ] <integration_name>
  API_PROVIDER = git_https_api
  API_ALLOWED_PREFIXES = ('https://example.com/<...>')
  [ API_BLOCKED_PREFIXES = ('<...>') ]
  API_USER_AUTHENTICATION = (
    TYPE = OAUTH2
    {oauth_parameters}
  )
  ENABLED = { TRUE | FALSE }
  [ COMMENT = '<string_literal>' ]
  ;
```

```sql
CREATE [ OR REPLACE ] API INTEGRATION [ IF NOT EXISTS ] <integration_name>
  API_PROVIDER = git_https_api
  API_ALLOWED_PREFIXES = ('<...>')
  [ API_BLOCKED_PREFIXES = ('<...>') ]
  [ ALLOWED_AUTHENTICATION_SECRETS = ( { <secret_name> [, <secret_name>, ... ] } ) | all | none ]
  USE_PRIVATELINK_ENDPOINT = { TRUE | FALSE }
  [ TLS_TRUSTED_CERTIFICATES = ( { <secret_name> [, <secret_name>, ... ] } ) ]
  ENABLED = { TRUE | FALSE }
  [ COMMENT = '<string_literal>' ]
  ;
```

Note that `git_https_api` should not be in quotation marks.

You can combine Private Link routing with OAuth2 user authentication.

## Required parameters

### For Amazon API Gateway

- **<integration_name>**
  Specifies the name of the API integration. This name follows the rules for Object identifiers. The name must be unique among API integrations in your account.

- **API_PROVIDER = { aws_api_gateway | aws_private_api_gateway | aws_gov_api_gateway | aws_gov_private_api_gateway }**
  Specifies the HTTPS proxy service type. Valid values are:
  - `aws_api_gateway`: for Amazon API Gateway using regional endpoints.
  - `aws_private_api_gateway`: for Amazon API Gateway using private endpoints.
  - `aws_gov_api_gateway`: for Amazon API Gateway using U.S. government GovCloud endpoints.
  - `aws_gov_private_api_gateway`: for Amazon API Gateway using U.S. government GovCloud endpoints that are also private endpoints.

- **API_AWS_ROLE_ARN = <iam_role>**
  For Amazon AWS, this is the ARN (Amazon resource name) of a cloud platform role.

- **API_ALLOWED_PREFIXES = (...)**
  Explicitly limits external functions that use the integration to reference one or more HTTPS proxy service endpoints (such as Amazon API Gateway) and resources within those proxies. Supports a comma-separated list of URLs, which are treated as prefixes (for details, see below).

  Each URL in API_ALLOWED_PREFIXES = (...) is treated as a prefix. For example, if you specify:

  `https://xyz.amazonaws.com/production/`

  that means all resources under

  `https://xyz.amazonaws.com/production/`

  are allowed. For example the following is allowed:

  `https://xyz.amazonaws.com/production/ml1`

  To maximize security, you should restrict allowed locations as narrowly as practical.

- **ENABLED = { TRUE | FALSE }**
  Specifies whether this API integration is enabled or disabled. If the API integration is disabled, any external function that relies on it will not work.

  The value is case-insensitive.

  The default is TRUE.

### For Azure API Management Service

- **<integration_name>**
  Specifies the name of the API integration. This name follows the rules for Object identifiers. The name should be unique among API integrations in your account.

- **API_PROVIDER = azure_api_management**
  Specifies that this integration is used with Azure API Management services. Do not use quotation marks around azure_api_management.

- **AZURE_TENANT_ID = <tenant_id>**
  Specifies the ID for your Office 365 tenant that all Azure API Management instances belong to. An API integration can authenticate to only one tenant, and so the allowed and blocked locations must refer to API Management instances that all belong to this tenant.

  To find your tenant ID, sign in to the Azure portal and select Azure Active Directory » Properties. The tenant ID is displayed in the Tenant ID field.

- **AZURE_AD_APPLICATION_ID = <azure_application_id>**
  The "Application (client) id" of the Azure AD (Active Directory) app for your remote service. If you followed the instructions in Creating external functions on Microsoft Azure, then this is the Azure Function App AD Application ID that you recorded in the worksheet in those instructions.

- **API_ALLOWED_PREFIXES = (...)**
  Explicitly limits external functions that use the integration to reference one or more HTTPS proxy service endpoints (such as Azure API Management services) and resources within those proxies. Supports a comma-separated list of URLs, which are treated as prefixes (for details, see below).

  Each URL in API_ALLOWED_PREFIXES = (...) is treated as a prefix. For example, if you specify:

  `https://my-external-function-demo.azure-api.net/my-function-app-name`

  that means all resources under

  `https://my-external-function-demo.azure-api.net/my-function-app-name`

  are allowed. For example the following is allowed:

  `https://my-external-function-demo.azure-api.net/my-function-app-name/my-http-trigger-function`

  To maximize security, you should restrict allowed locations as narrowly as practical.

- **ENABLED = { TRUE | FALSE }**
  Specifies whether this API integration is enabled or disabled. If the API integration is disabled, any external function that relies on it will not work.

  The value is case-insensitive.

  The default is TRUE.

### For Google Cloud API Gateway

- **<integration_name>**
  Specifies the name of the API integration. This name follows the rules for Object identifiers. The name should be unique among API integrations in your account.

- **API_PROVIDER = google_api_gateway**
  Specifies that this integration is used with Google Cloud. The only valid value for this purpose is google_api_gateway. The value must not be in quotation marks.

- **GOOGLE_AUDIENCE = <google_audience>**
  This is used as the audience claim when generating the JWT (JSON Web Token) to authenticate to the Google API Gateway. For more information about authenticating with Google, please see the Google service account authentication documentation.

- **API_ALLOWED_PREFIXES = (...)**
  Explicitly limits external functions that use the integration to reference one or more HTTPS proxy service endpoints (such as Google Cloud API Gateways) and resources within those proxies. Supports a comma-separated list of URLs, which are treated as prefixes (for details, see below).

  Each URL in API_ALLOWED_PREFIXES = (...) is treated as a prefix. For example, if you specify:

  `https://my-external-function-demo.uc.gateway.dev/x`

  that means all resources under

  `https://my-external-function-demo.uc.gateway.dev/x`

  are allowed. For example the following is allowed:

  `https://my-external-function-demo.uc.gateway.dev/x/y`

  To maximize security, you should restrict allowed locations as narrowly as practical.

- **ENABLED = { TRUE | FALSE }**
  Specifies whether this API integration is enabled or disabled. If the API integration is disabled, any external function that relies on it will not work.

  The value is case-insensitive.

  The default is TRUE.

### For Git repository

OAuth support is generally available only when the repository is hosted at github.com.

OAuth support is in preview for repository providers other than github.com.

For an example, see Setting up Snowflake to use Git.

- **<integration_name>**
  Specifies the name of the API integration. This name follows the rules for Object identifiers. The name must be unique among API integrations in your account.

- **API_PROVIDER = git_https_api**
  Specifies that this integration is used with CREATE GIT REPOSITORY to create an integration with a remote Git repository. The only valid value for this purpose is git_https_api. The value must not be in quotation marks.

- **API_ALLOWED_PREFIXES = (...)**
  Explicitly limits requests that use the integration to reference one or more HTTPS endpoints and resources beneath those endpoints. Supports a comma-separated list of URLs, which are treated as prefixes.

  In most cases, Snowflake supports any HTTPS Git repository URL. For example, you can specify a custom URL to a corporate Git server within your own domain.

  `https://example.com/my-repo`

  Each URL in API_ALLOWED_PREFIXES = (...) is treated as a prefix. For example, you can specify the following:

  `https://example.com/my-account`

  With this prefix, all resources under that URL are allowed. For example, the following is allowed:

  `https://example.com/my-account/myproject`

  To maximize security, you should restrict allowed locations as narrowly as practical.

- **ENABLED = { TRUE | FALSE }**
  Specifies whether this API integration is enabled or disabled. If the API integration is disabled, the Git repository will not be accessible.

  The value is case-insensitive.

  The default is TRUE.

## Optional parameters

### For all integrations

- **API_KEY = <api_key>**
  The API key (also called a "subscription key").

- **API_BLOCKED_PREFIXES = (...)**
  Lists the endpoints and resources in the HTTPS proxy service that are not allowed to be called from Snowflake.

  The possible values for locations follow the same rules as for API_ALLOWED_PREFIXES above.

  API_BLOCKED_PREFIXES takes precedence over API_ALLOWED_PREFIXES. If a prefix matches both, then it is blocked. In other words, Snowflake allows all values that match API_ALLOWED_PREFIXES except values that also match API_BLOCKED_PREFIXES.

  If a value is outside API_ALLOWED_PREFIXES, you do not need to explicitly block it.

- **COMMENT = '<string_literal>'**
  A description of the integration.

### For Git repository

OAuth support is generally available only when the repository is hosted at github.com.

OAuth support is in preview for repository providers other than github.com.

In addition to parameters for all integrations, use the following parameters when you're using the integration to connect to a remote Git repository by setting the integration's API_PROVIDER parameter to git_https_api.

- **ALLOWED_AUTHENTICATION_SECRETS = ( < <secret_name> [, <secret_name> ... ] | all | none > )**
  Specifies the secrets that UDF or procedure handler code can use when accessing the Git repository at the API_ALLOWED_PREFIXES value. You specify a secret from this list when specifying Git credentials with the GIT_CREDENTIALS parameter.

  This parameter's value must be one of the following:
  - One or more fully-qualified Snowflake secret names to allow any of the listed secrets.
  - (Default) all to allow any secret.
  - none to allow no secrets.

  The ALLOWED_API_AUTHENTICATION_INTEGRATIONS parameter can also specify allowed secrets. For more information, see Usage notes.

  For reference information about secrets, refer to CREATE SECRET.

- **API_USER_AUTHENTICATION = ( < TYPE = snowflake_github_app | TYPE = OAUTH2 <oauth_parameters> > )**
  Specifies security integration settings for an OAuth 2.0 flow.

  How you set this parameter differs depending on the repository provider. For more information, see Configure for authenticating with OAuth.
  - TYPE = snowflake_github_app: Authenticate with GitHub using the Snowflake GitHub App, as described in Configure for authenticating with OAuth. No other values are required for API_USER_AUTHENTICATION in this case.
  - TYPE = OAUTH2: Authenticate using OAuth2 parameters, as described in Configure for authenticating with OAuth.

    When you specify this value, you must also specify the parameters, as required, under oauth_parameters (next).
  - oauth_parameters: Authenticate using the specified OAuth 2.0 parameters, including the following parameters:
    - OAUTH_AUTHORIZATION_ENDPOINT = 'endpoint_url'
      Specifies the URL for authenticating to the repository.
    - OAUTH_TOKEN_ENDPOINT = 'token_endpoint_url'
      Specifies the token endpoint used by the client to obtain an access token by presenting its authorization grant or refresh token. The client uses the token endpoint with every authorization grant except for the implicit grant type (because an access token is issued directly).
    - OAUTH_CLIENT_ID = 'client_id'
      Specifies the client ID for the OAuth application in the repository provider. The value for this parameter is specific to your organization.
    - OAUTH_CLIENT_SECRET = 'client_secret'
      Specifies the client secret for the OAuth application in the repository provider. The value for this parameter is specific to your organization.
    - OAUTH_ACCESS_TOKEN_VALIDITY = integer
      Specifies the default lifetime, in seconds, of the OAuth access token issued by an OAuth server.

      The value set in this property is used if the access token lifetime is not returned as part of OAuth token response. When both values are available, the smaller of the two values is used to refresh the access token.
    - OAUTH_REFRESH_TOKEN_VALIDITY = integer
      Specifies the value, in seconds, to determine the validity of the refresh token obtained from the OAuth server.
    - OAUTH_ALLOWED_SCOPES = ( { 'read_api' | 'read_repository' | 'write_repository' } [ , ... ] )
      Specifies the scope to use when making a request from the provider. Specify the following values:
      - 'read_api': Read from the repository provider's API.
      - 'read_repository': Read from the repository.
      - 'write_repository': Write to the repository.
    - OAUTH_USERNAME = 'string_literal'
      Optional. The Git repository username. Set this value based on the repository provider's requirements. For example, for Bitbucket, set this x-token-auth.

- **TLS_TRUSTED_CERTIFICATES = ( {secret_name} [, {secret_name} ... ] )**
  Specifies secrets containing self-signed certificates to be used when authenticating with a Git repository server over private link. This parameter is needed only when the certificate is self-signed, rather than signed by a certificate authority.

  This parameter's value must be one or more fully qualified Snowflake secret names. The secrets must be of type generic string whose SECRET_STRING value is Base64-encoded certificate data.

- **USE_PRIVATELINK_ENDPOINT = { TRUE | FALSE }**
  Specifies whether this API integration will be used only to configure access to a remote Git repository over an outbound private link connection through private connectivity.

  This parameter must be set to FALSE (the default) for public Git servers.

  The default is FALSE.

## Access control requirements

A role used to execute this operation must have the following privileges at a minimum:

| Privilege | Object | Notes |
|---|---|---|
| CREATE INTEGRATION | Account | Only the ACCOUNTADMIN role has this privilege by default. The privilege can be granted to additional roles as needed. |

## Usage notes

- Only Snowflake roles with OWNERSHIP or USAGE privileges on the API integration can use the API integration directly (for example, by creating an external function that specifies that API integration).

- An API integration object is tied to a specific cloud platform account and role within that account, but not to a specific HTTPS proxy URL. You can create more than one instance of an HTTPS proxy service in a cloud provider account, and you can use the same API integration to authenticate to multiple proxy services in that account.

- Your Snowflake account can have multiple API integration objects, for example, for different cloud platform accounts.

- Multiple external functions can use the same API integration object, and thus the same HTTPS proxy service.

- Regarding metadata:

  Customers should ensure that no personal data (other than for a User object), sensitive data, export-controlled data, or other regulated data is entered as metadata when using the Snowflake service. For more information, see Metadata fields in Snowflake.

- The OR REPLACE and IF NOT EXISTS clauses are mutually exclusive. They can't both be used in the same statement.

- CREATE OR REPLACE <object> statements are atomic. That is, when an object is replaced, the old object is deleted and the new object is created in a single transaction.

## Examples

### Amazon API Gateway

The following example shows creation of an API integration and use of that API integration in a subsequent CREATE EXTERNAL FUNCTION statement:

```sql
CREATE OR REPLACE API INTEGRATION demonstration_external_api_integration_01
  API_PROVIDER = aws_api_gateway
  API_AWS_ROLE_ARN = 'arn:aws:iam::123456789012:role/my_cloud_account_role'
  API_ALLOWED_PREFIXES = ('https://xyz.execute-api.us-west-2.amazonaws.com/production')
  ENABLED = TRUE;

CREATE OR REPLACE EXTERNAL FUNCTION local_echo(string_col VARCHAR)
  RETURNS VARIANT
  API_INTEGRATION = demonstration_external_api_integration_01
  AS 'https://xyz.execute-api.us-west-2.amazonaws.com/production/remote_echo';
```

### Git repository

For an example of an API integration used to integrate a Git repository, see Setting up Snowflake to use Git.
