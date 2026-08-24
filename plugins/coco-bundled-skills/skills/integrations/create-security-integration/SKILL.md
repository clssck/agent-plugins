---
name: create-security-integration
description: >
  Create a new security integration (SCIM, SAML2, Snowflake OAuth, External OAuth, External API Authentication, or AWS IAM Authentication) for interfacing with third-party identity and authentication services
---

# CREATE SECURITY INTEGRATION


Creates a new security integration in the account or replaces an existing integration. A security integration is a Snowflake object that provides an interface between Snowflake and a third-party service for authentication, identity management, or API access.

The syntax varies by security integration type. Six subtypes are supported: SCIM (user/group provisioning), SAML2 (federated single sign-on), Snowflake OAuth for partner applications, Snowflake OAuth for custom clients, External OAuth (third-party authorization servers), and External API Authentication (OAuth2 client credentials, authorization code, JWT bearer, or AWS IAM).

## Syntax

**SCIM:**

```sql
CREATE [ OR REPLACE ] SECURITY INTEGRATION [ IF NOT EXISTS ]
  <name>
  TYPE = SCIM
  ENABLED = { TRUE | FALSE }
  SCIM_CLIENT = { 'OKTA' | 'AZURE' | 'GENERIC' }
  RUN_AS_ROLE = { 'OKTA_PROVISIONER' | 'AAD_PROVISIONER' | 'GENERIC_SCIM_PROVISIONER' | '<custom_role>' }
  [ NETWORK_POLICY = '<network_policy>' ]
  [ SYNC_PASSWORD = { TRUE | FALSE } ]
  [ COMMENT = '<string_literal>' ]
```

**SAML2:**

```sql
CREATE [ OR REPLACE ] SECURITY INTEGRATION [ IF NOT EXISTS ]
  <name>
  TYPE = SAML2
  ENABLED = { TRUE | FALSE }
  { METADATA_URL = '<string_literal>' | <idp_parameters> }
  [ ALLOWED_USER_DOMAINS = ( '<string_literal>' [ , '<string_literal>' , ... ] ) ]
  [ ALLOWED_EMAIL_PATTERNS = ( '<string_literal>' [ , '<string_literal>' , ... ] ) ]
  [ SAML2_SP_INITIATED_LOGIN_PAGE_LABEL = '<string_literal>' ]
  [ SAML2_ENABLE_SP_INITIATED = TRUE | FALSE ]
  [ SAML2_SNOWFLAKE_X509_CERT = '<string_literal>' ]
  [ SAML2_SIGN_REQUEST = TRUE | FALSE ]
  [ SAML2_REQUESTED_NAMEID_FORMAT = '<string_literal>' ]
  [ SAML2_POST_LOGOUT_REDIRECT_URL = '<string_literal>' ]
  [ SAML2_FORCE_AUTHN = TRUE | FALSE ]
  [ SAML2_SNOWFLAKE_ISSUER_URL = '<string_literal>' ]
  [ SAML2_SNOWFLAKE_ACS_URL = '<string_literal>' ]
  [ COMMENT = '<string_literal>' ]
```

Where:

```sql
idp_parameters ::=
  SAML2_ISSUER = '<string_literal>'
  SAML2_SSO_URL = '<string_literal>'
  SAML2_PROVIDER = '<string_literal>'
  SAML2_X509_CERT = '<string_literal>'
```

**Snowflake OAuth (Partner Applications):**

```sql
CREATE [ OR REPLACE ] SECURITY INTEGRATION [ IF NOT EXISTS ]
  <name>
  TYPE = OAUTH
  OAUTH_CLIENT = <partner_application>
  [ OAUTH_REDIRECT_URI = '<uri>' ]
  [ ENABLED = { TRUE | FALSE } ]
  [ OAUTH_ISSUE_REFRESH_TOKENS = { TRUE | FALSE } ]
  [ OAUTH_REFRESH_TOKEN_VALIDITY = <integer> ]
  [ OAUTH_SINGLE_USE_REFRESH_TOKENS_REQUIRED = { TRUE | FALSE } ]
  [ OAUTH_USE_SECONDARY_ROLES = { IMPLICIT | NONE } ]
  [ NETWORK_POLICY = '<network_policy>' ]
  [ BLOCKED_ROLES_LIST = ( '<role_name>' [ , '<role_name>' , ... ] ) ]
  [ USE_PRIVATELINK_FOR_AUTHORIZATION_ENDPOINT = { TRUE | FALSE } ]
  [ COMMENT = '<string_literal>' ]
```

**Snowflake OAuth (Custom Clients):**

```sql
CREATE [ OR REPLACE ] SECURITY INTEGRATION [ IF NOT EXISTS ]
  <name>
  TYPE = OAUTH
  OAUTH_CLIENT = CUSTOM
  OAUTH_CLIENT_TYPE = 'CONFIDENTIAL' | 'PUBLIC'
  OAUTH_REDIRECT_URI = '<uri>'
  [ ENABLED = { TRUE | FALSE } ]
  [ OAUTH_ALLOW_NON_TLS_REDIRECT_URI = { TRUE | FALSE } ]
  [ OAUTH_ENFORCE_PKCE = { TRUE | FALSE } ]
  [ OAUTH_SINGLE_USE_REFRESH_TOKENS_REQUIRED = { TRUE | FALSE } ]
  [ OAUTH_USE_SECONDARY_ROLES = { IMPLICIT | NONE } ]
  [ PRE_AUTHORIZED_ROLES_LIST = ( '<role_name>' [ , '<role_name>' , ... ] ) ]
  [ BLOCKED_ROLES_LIST = ( '<role_name>' [ , '<role_name>' , ... ] ) ]
  [ OAUTH_ISSUE_REFRESH_TOKENS = { TRUE | FALSE } ]
  [ OAUTH_REFRESH_TOKEN_VALIDITY = <integer> ]
  [ NETWORK_POLICY = '<network_policy>' ]
  [ OAUTH_CLIENT_RSA_PUBLIC_KEY = <public_key1> ]
  [ OAUTH_CLIENT_RSA_PUBLIC_KEY_2 = <public_key2> ]
  [ USE_PRIVATELINK_FOR_AUTHORIZATION_ENDPOINT = { TRUE | FALSE } ]
  [ COMMENT = '<string_literal>' ]
```

**External OAuth:**

```sql
CREATE [ OR REPLACE ] SECURITY INTEGRATION [ IF NOT EXISTS ]
  <name>
  TYPE = EXTERNAL_OAUTH
  ENABLED = { TRUE | FALSE }
  EXTERNAL_OAUTH_TYPE = { OKTA | AZURE | PING_FEDERATE | CUSTOM }
  EXTERNAL_OAUTH_ISSUER = '<string_literal>'
  EXTERNAL_OAUTH_TOKEN_USER_MAPPING_CLAIM = { '<string_literal>' | ('<string_literal>' [ , '<string_literal>' , ... ] ) }
  EXTERNAL_OAUTH_SNOWFLAKE_USER_MAPPING_ATTRIBUTE = { 'LOGIN_NAME' | 'EMAIL_ADDRESS' }
  [ EXTERNAL_OAUTH_JWS_KEYS_URL = { '<string_literal>' | ('<string_literal>' [ , '<string_literal>' , ... ] ) } ]
  [ EXTERNAL_OAUTH_BLOCKED_ROLES_LIST = ( '<role_name>' [ , '<role_name>' , ... ] ) ]
  [ EXTERNAL_OAUTH_ALLOWED_ROLES_LIST = ( '<role_name>' [ , '<role_name>' , ... ] ) ]
  [ EXTERNAL_OAUTH_RSA_PUBLIC_KEY = <public_key1> ]
  [ EXTERNAL_OAUTH_RSA_PUBLIC_KEY_2 = <public_key2> ]
  [ EXTERNAL_OAUTH_AUDIENCE_LIST = { '<string_literal>' | ('<string_literal>' [ , '<string_literal>' , ... ] ) } ]
  [ EXTERNAL_OAUTH_ANY_ROLE_MODE = { DISABLE | ENABLE | ENABLE_FOR_PRIVILEGE } ]
  [ EXTERNAL_OAUTH_SCOPE_DELIMITER = '<string_literal>' ]
  [ EXTERNAL_OAUTH_SCOPE_MAPPING_ATTRIBUTE = '<string_literal>' ]
  [ NETWORK_POLICY = '<network_policy>' ]
  [ COMMENT = '<string_literal>' ]
```

**External API Authentication (OAuth2 Client Credentials):**

```sql
CREATE SECURITY INTEGRATION <name>
  TYPE = API_AUTHENTICATION
  AUTH_TYPE = OAUTH2
  ENABLED = { TRUE | FALSE }
  [ OAUTH_TOKEN_ENDPOINT = '<string_literal>' ]
  [ OAUTH_CLIENT_AUTH_METHOD = { CLIENT_SECRET_BASIC | CLIENT_SECRET_POST } ]
  [ OAUTH_CLIENT_ID = '<string_literal>' ]
  [ OAUTH_CLIENT_SECRET = '<string_literal>' ]
  [ OAUTH_GRANT = 'CLIENT_CREDENTIALS' ]
  [ OAUTH_ACCESS_TOKEN_VALIDITY = <integer> ]
  [ OAUTH_ALLOWED_SCOPES = ( '<scope_1>' [ , '<scope_2>' ... ] ) ]
  [ COMMENT = '<string_literal>' ]
```

**External API Authentication (OAuth2 Authorization Code Grant):**

```sql
CREATE SECURITY INTEGRATION <name>
  TYPE = API_AUTHENTICATION
  AUTH_TYPE = OAUTH2
  ENABLED = { TRUE | FALSE }
  [ OAUTH_AUTHORIZATION_ENDPOINT = '<string_literal>' ]
  [ OAUTH_TOKEN_ENDPOINT = '<string_literal>' ]
  [ OAUTH_CLIENT_AUTH_METHOD = { CLIENT_SECRET_BASIC | CLIENT_SECRET_POST } ]
  [ OAUTH_CLIENT_ID = '<string_literal>' ]
  [ OAUTH_CLIENT_SECRET = '<string_literal>' ]
  [ OAUTH_GRANT = 'AUTHORIZATION_CODE' ]
  [ OAUTH_ACCESS_TOKEN_VALIDITY = <integer> ]
  [ OAUTH_REFRESH_TOKEN_VALIDITY = <integer> ]
  [ COMMENT = '<string_literal>' ]
```

**External API Authentication (OAuth2 JWT Bearer):**

```sql
CREATE SECURITY INTEGRATION <name>
  TYPE = API_AUTHENTICATION
  AUTH_TYPE = OAUTH2
  ENABLED = { TRUE | FALSE }
  [ OAUTH_AUTHORIZATION_ENDPOINT = '<string_literal>' ]
  [ OAUTH_TOKEN_ENDPOINT = '<string_literal>' ]
  [ OAUTH_CLIENT_AUTH_METHOD = { CLIENT_SECRET_BASIC | CLIENT_SECRET_POST } ]
  [ OAUTH_CLIENT_ID = '<string_literal>' ]
  [ OAUTH_CLIENT_SECRET = '<string_literal>' ]
  [ OAUTH_GRANT = 'JWT_BEARER' ]
  [ OAUTH_ACCESS_TOKEN_VALIDITY = <integer> ]
  [ OAUTH_REFRESH_TOKEN_VALIDITY = <integer> ]
  [ COMMENT = '<string_literal>' ]
```

**External API Authentication (AWS IAM):**

```sql
CREATE SECURITY INTEGRATION <name>
  TYPE = API_AUTHENTICATION
  AUTH_TYPE = AWS_IAM
  AWS_ROLE_ARN = '<iam_role_arn>'
  ENABLED = { TRUE | FALSE }
  [ COMMENT = '<string_literal>' ]
```

## Required parameters

- **<name>**
  String that specifies the identifier (i.e. name) for the integration; must be unique in your account.
  In addition, the identifier must start with an alphabetic character and cannot contain spaces or special characters unless the entire identifier string is enclosed in double quotes (e.g. `"My object"`). Identifiers enclosed in double quotes are also case-sensitive.

- **TYPE = { SCIM | SAML2 | OAUTH | EXTERNAL_OAUTH | API_AUTHENTICATION }**
  Specifies the type of security integration:
  - `SCIM`: Creates an interface for automated user and group provisioning via the SCIM 2.0 protocol.
  - `SAML2`: Creates an interface for federated single sign-on using the SAML 2.0 protocol.
  - `OAUTH`: Creates an interface for Snowflake OAuth (partner applications or custom clients).
  - `EXTERNAL_OAUTH`: Creates an interface for external OAuth authorization servers.
  - `API_AUTHENTICATION`: Creates an interface for external API authentication (OAuth2 or AWS IAM).

- **ENABLED = { TRUE | FALSE }**
  Specifies whether this security integration is available for usage.
  - `TRUE` activates the integration for immediate operation.
  - `FALSE` suspends the integration. When disabled, integration with third-party services fails.

## SCIM required parameters

- **SCIM_CLIENT = { 'OKTA' | 'AZURE' | 'GENERIC' }**
  Specifies the SCIM client identity provider:
  - `'OKTA'`: Okta identity provider.
  - `'AZURE'`: Microsoft Azure Active Directory (Entra ID).
  - `'GENERIC'`: Any other SCIM 2.0-compliant identity provider.

- **RUN_AS_ROLE = { 'OKTA_PROVISIONER' | 'AAD_PROVISIONER' | 'GENERIC_SCIM_PROVISIONER' | '<custom_role>' }**
  Specifies the Snowflake role that owns users and roles created by the SCIM client. The role name is case-sensitive. Predefined roles:
  - `'OKTA_PROVISIONER'`: Use with SCIM_CLIENT = 'OKTA'.
  - `'AAD_PROVISIONER'`: Use with SCIM_CLIENT = 'AZURE'.
  - `'GENERIC_SCIM_PROVISIONER'`: Use with SCIM_CLIENT = 'GENERIC'.
  - A custom role may also be specified if the predefined roles do not meet your needs.

## SAML2 required parameters

You must specify either METADATA_URL or the full set of idp_parameters. These two approaches are mutually exclusive.

- **METADATA_URL = '<string_literal>'**
  Specifies the URL of the IdP SAML metadata document. Use this for identity providers that publish a metadata endpoint. This parameter is only supported for Okta and Microsoft Entra ID.

- **SAML2_ISSUER = '<string_literal>'**
  Specifies the entity ID (issuer) of the IdP. Required when not using METADATA_URL.

- **SAML2_SSO_URL = '<string_literal>'**
  Specifies the URL of the IdP single sign-on endpoint. Required when not using METADATA_URL.

- **SAML2_PROVIDER = '<string_literal>'**
  The string describing the IdP. One of the following: `'OKTA'`, `'ADFS'`, `'Custom'`. Required when not using METADATA_URL.

- **SAML2_X509_CERT = '<string_literal>'**
  The Base64 encoded IdP signing certificate on a single line without the leading `-----BEGIN CERTIFICATE-----` and ending `-----END CERTIFICATE-----` markers. Required when not using METADATA_URL.

## Snowflake OAuth (Partner Applications) required parameters

- **OAUTH_CLIENT = <partner_application>**
  Specifies the partner application. Supported values:
  - `TABLEAU_DESKTOP`: Tableau Desktop.
  - `TABLEAU_SERVER`: Tableau Server or Tableau Cloud.
  - `LOOKER`: Looker.

- **OAUTH_REDIRECT_URI = '<uri>'**
  Specifies the client redirect URI. Required for LOOKER. For Tableau clients, this is typically set by the application.

## Snowflake OAuth (Custom Clients) required parameters

- **OAUTH_CLIENT = CUSTOM**
  Specifies that this is a custom OAuth client (not a partner application).

- **OAUTH_CLIENT_TYPE = 'CONFIDENTIAL' | 'PUBLIC'**
  Specifies the OAuth client type:
  - `'CONFIDENTIAL'`: The client can securely store a client secret (e.g. server-side applications).
  - `'PUBLIC'`: The client cannot securely store a client secret (e.g. single-page or mobile applications).

- **OAUTH_REDIRECT_URI = '<uri>'**
  Specifies the client redirect URI. The URI must use TLS (HTTPS) unless OAUTH_ALLOW_NON_TLS_REDIRECT_URI is set to TRUE.

## External OAuth required parameters

- **EXTERNAL_OAUTH_TYPE = { OKTA | AZURE | PING_FEDERATE | CUSTOM }**
  Specifies the external OAuth authorization server type:
  - `OKTA`: Okta authorization server.
  - `AZURE`: Microsoft Entra ID.
  - `PING_FEDERATE`: PingFederate.
  - `CUSTOM`: Any other OAuth 2.0-compliant authorization server.

- **EXTERNAL_OAUTH_ISSUER = '<string_literal>'**
  Specifies the URL of the external OAuth authorization server issuer.

- **EXTERNAL_OAUTH_TOKEN_USER_MAPPING_CLAIM = { '<string_literal>' | ('<string_literal>' [ , '<string_literal>' , ... ] ) }**
  Specifies the access token claim(s) that map to the Snowflake user. Common values: `'sub'` (Okta), `'upn'` (Azure).

- **EXTERNAL_OAUTH_SNOWFLAKE_USER_MAPPING_ATTRIBUTE = { 'LOGIN_NAME' | 'EMAIL_ADDRESS' }**
  Specifies the Snowflake user attribute that the token claim maps to:
  - `'LOGIN_NAME'`: Maps to the user's login name.
  - `'EMAIL_ADDRESS'`: Maps to the user's email address.

## External API Authentication (OAuth2) required parameters

- **AUTH_TYPE = OAUTH2**
  Specifies OAuth2 as the authentication method for external API access.

## External API Authentication (AWS IAM) required parameters

- **AUTH_TYPE = AWS_IAM**
  Specifies AWS IAM as the authentication method.

- **AWS_ROLE_ARN = '<iam_role_arn>'**
  Specifies the Amazon Resource Name (ARN) of the AWS IAM role to assume for authentication. For example: `'arn:aws:iam::001234567890:role/myrole'`.

## Optional parameters

### Common optional parameters

- **COMMENT = '<string_literal>'**
  String (literal) that specifies a comment for the integration.
  Default: No value

### SCIM optional parameters

- **NETWORK_POLICY = '<network_policy>'**
  Specifies the name of an existing network policy to apply to the SCIM integration. Controls which IP addresses can make SCIM API requests.

- **SYNC_PASSWORD = { TRUE | FALSE }**
  Specifies whether to synchronize user passwords from the identity provider. Supported for Okta and Custom SCIM integrations. Microsoft Entra ID SCIM integrations are not supported.
  Default: `FALSE`

### SAML2 optional parameters

- **ALLOWED_USER_DOMAINS = ( '<string_literal>' [ , '<string_literal>' , ... ] )**
  Specifies a list of email domains that are allowed to authenticate via this SAML integration.

- **ALLOWED_EMAIL_PATTERNS = ( '<string_literal>' [ , '<string_literal>' , ... ] )**
  Specifies a list of regular expression patterns for email addresses that are allowed to authenticate via this SAML integration.

- **SAML2_SP_INITIATED_LOGIN_PAGE_LABEL = '<string_literal>'**
  The string containing the label to display after the Log In With button on the login page.

- **SAML2_ENABLE_SP_INITIATED = { TRUE | FALSE }**
  Specifies whether SP-initiated single sign-on is enabled.

- **SAML2_SNOWFLAKE_X509_CERT = '<string_literal>'**
  The Base64 encoded self-signed certificate generated by Snowflake used for encrypting SAML assertions and sending signed SAML requests.

- **SAML2_SIGN_REQUEST = { TRUE | FALSE }**
  Specifies whether SAML requests sent to the IdP are signed.

- **SAML2_REQUESTED_NAMEID_FORMAT = '<string_literal>'**
  Specifies the NameID format requested from the IdP. Valid formats:
  - `'urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified'`
  - `'urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress'` (default)
  - `'urn:oasis:names:tc:SAML:1.1:nameid-format:X509SubjectName'`
  - `'urn:oasis:names:tc:SAML:1.1:nameid-format:WindowsDomainQualifiedName'`
  - `'urn:oasis:names:tc:SAML:2.0:nameid-format:kerberos'`
  - `'urn:oasis:names:tc:SAML:2.0:nameid-format:persistent'`
  - `'urn:oasis:names:tc:SAML:2.0:nameid-format:transient'`

- **SAML2_POST_LOGOUT_REDIRECT_URL = '<string_literal>'**
  The endpoint to which Snowflake redirects users after clicking the Log Out button in Snowsight. Snowflake terminates the Snowflake session upon redirecting to the specified endpoint.

- **SAML2_FORCE_AUTHN = { TRUE | FALSE }**
  Specifies whether to force the IdP to re-authenticate the user, even if an active session exists.
  Default: `FALSE`

- **SAML2_SNOWFLAKE_ISSUER_URL = '<string_literal>'**
  Specifies the Snowflake entity ID (issuer URL) for the SAML service provider. Use this to customize the issuer URL, for example when using private connectivity.

- **SAML2_SNOWFLAKE_ACS_URL = '<string_literal>'**
  Specifies the Snowflake Assertion Consumer Service (ACS) URL. Use this to customize the ACS URL, for example when using private connectivity.

### Snowflake OAuth (Partner Applications) optional parameters

- **ENABLED = { TRUE | FALSE }**
  Specifies whether the integration is enabled.
  Default: `TRUE`

- **OAUTH_ISSUE_REFRESH_TOKENS = { TRUE | FALSE }**
  Specifies whether the client can exchange a refresh token for an access token when the current access token expires.
  Default: `TRUE`

- **OAUTH_REFRESH_TOKEN_VALIDITY = <integer>**
  Specifies the number of seconds that a refresh token is valid. Minimum: `3600` (1 hour). Maximum: `7776000` (90 days).
  Default: `7776000`

- **OAUTH_SINGLE_USE_REFRESH_TOKENS_REQUIRED = { TRUE | FALSE }**
  Specifies whether each refresh token can only be used once to obtain a new access token.
  Default: `FALSE`

- **OAUTH_USE_SECONDARY_ROLES = { IMPLICIT | NONE }**
  Specifies whether default secondary roles are activated in the user session:
  - `IMPLICIT`: Secondary roles are activated.
  - `NONE`: Only roles explicitly granted to the user are available.
  Default: `NONE`

- **NETWORK_POLICY = '<network_policy>'**
  Specifies the name of an existing network policy to apply to OAuth sessions.

- **BLOCKED_ROLES_LIST = ( '<role_name>' [ , '<role_name>' , ... ] )**
  Specifies a list of Snowflake roles that users cannot consent to use through OAuth. The roles ACCOUNTADMIN, ORGADMIN, GLOBALORGADMIN, and SECURITYADMIN are included in this list by default.

- **USE_PRIVATELINK_FOR_AUTHORIZATION_ENDPOINT = { TRUE | FALSE }**
  Specifies whether to use a private link for the OAuth authorization endpoint.
  Default: `FALSE`

### Snowflake OAuth (Custom Clients) optional parameters

- **ENABLED = { TRUE | FALSE }**
  Specifies whether the integration is enabled.
  Default: `TRUE`

- **OAUTH_ALLOW_NON_TLS_REDIRECT_URI = { TRUE | FALSE }**
  Specifies whether the redirect URI can use non-TLS (HTTP) connections. Set to TRUE only for development or testing; production environments should always use TLS.
  Default: `FALSE`

- **OAUTH_ENFORCE_PKCE = { TRUE | FALSE }**
  Specifies whether the client must use Proof Key for Code Exchange (PKCE) during the authorization flow.
  Default: `FALSE`

- **OAUTH_SINGLE_USE_REFRESH_TOKENS_REQUIRED = { TRUE | FALSE }**
  Specifies whether each refresh token can only be used once.
  Default: `FALSE`

- **OAUTH_USE_SECONDARY_ROLES = { IMPLICIT | NONE }**
  Specifies whether default secondary roles are activated in the user session.
  Default: `NONE`

- **PRE_AUTHORIZED_ROLES_LIST = ( '<role_name>' [ , '<role_name>' , ... ] )**
  Specifies a list of roles that do not require user consent to be used in the OAuth flow. Only available for CONFIDENTIAL client types. The roles ACCOUNTADMIN, ORGADMIN, GLOBALORGADMIN, and SECURITYADMIN cannot be pre-authorized.

- **BLOCKED_ROLES_LIST = ( '<role_name>' [ , '<role_name>' , ... ] )**
  Specifies a list of Snowflake roles that users cannot consent to use through OAuth. The ACCOUNTADMIN, ORGADMIN, GLOBALORGADMIN, and SECURITYADMIN roles are included in this list by default.

- **OAUTH_ISSUE_REFRESH_TOKENS = { TRUE | FALSE }**
  Specifies whether the client can exchange a refresh token for an access token.
  Default: `TRUE`

- **OAUTH_REFRESH_TOKEN_VALIDITY = <integer>**
  Specifies the number of seconds that a refresh token is valid. Minimum: `86400` (1 day). Maximum: `7776000` (90 days).
  Default: `7776000`

- **NETWORK_POLICY = '<network_policy>'**
  Specifies the name of an existing network policy to apply to OAuth sessions.

- **OAUTH_CLIENT_RSA_PUBLIC_KEY = <public_key1>**
  Specifies an RSA public key.

- **OAUTH_CLIENT_RSA_PUBLIC_KEY_2 = <public_key2>**
  Specifies a second RSA public key, used for key rotation.

- **USE_PRIVATELINK_FOR_AUTHORIZATION_ENDPOINT = { TRUE | FALSE }**
  Specifies whether to use a private link for the OAuth authorization endpoint.
  Default: `FALSE`

### External OAuth optional parameters

- **EXTERNAL_OAUTH_JWS_KEYS_URL = { '<string_literal>' | ('<string_literal>' [ , '<string_literal>' , ... ] ) }**
  Specifies the URL(s) where the authorization server publishes its JSON Web Key Set (JWKS) for token verification. Azure supports up to 3 URLs; all other types support 1 URL.

- **EXTERNAL_OAUTH_BLOCKED_ROLES_LIST = ( '<role_name>' [ , '<role_name>' , ... ] )**
  Specifies a list of Snowflake roles that cannot be used in external OAuth sessions. By default, ACCOUNTADMIN, ORGADMIN, GLOBALORGADMIN, and SECURITYADMIN are blocked.

- **EXTERNAL_OAUTH_ALLOWED_ROLES_LIST = ( '<role_name>' [ , '<role_name>' , ... ] )**
  Specifies a list of Snowflake roles that can be explicitly used in external OAuth sessions.

- **EXTERNAL_OAUTH_RSA_PUBLIC_KEY = <public_key1>**
  Specifies the RSA public key used to verify the external OAuth access token. Base64-encoded, without PEM headers (no `-----BEGIN PUBLIC KEY-----` or `-----END PUBLIC KEY-----` markers).

- **EXTERNAL_OAUTH_RSA_PUBLIC_KEY_2 = <public_key2>**
  Specifies a second RSA public key, used for key rotation.

- **EXTERNAL_OAUTH_AUDIENCE_LIST = { '<string_literal>' | ('<string_literal>' [ , '<string_literal>' , ... ] ) }**
  Specifies additional audience values for access token validation beyond the Snowflake account URL. Multiple URLs are supported only when EXTERNAL_OAUTH_TYPE = CUSTOM.

- **EXTERNAL_OAUTH_ANY_ROLE_MODE = { DISABLE | ENABLE | ENABLE_FOR_PRIVILEGE }**
  Specifies whether the OAuth client or user can use any role beyond the roles defined in the token:
  - `DISABLE`: The client can only use roles defined in the token.
  - `ENABLE`: The client can use any role granted to the user.
  - `ENABLE_FOR_PRIVILEGE`: The client can use any role granted to the user, but only if the user has been granted the USE_ANY_ROLE privilege on the integration.
  Default: `DISABLE`

- **EXTERNAL_OAUTH_SCOPE_DELIMITER = '<string_literal>'**
  Specifies the delimiter character used to separate scopes in the token. Default: comma (`,`). Available only when EXTERNAL_OAUTH_TYPE = CUSTOM.

- **EXTERNAL_OAUTH_SCOPE_MAPPING_ATTRIBUTE = '<string_literal>'**
  Specifies the token claim name that contains the scope values. Only valid values: `'scp'` or `'scope'`. Available only when EXTERNAL_OAUTH_TYPE = CUSTOM.

- **NETWORK_POLICY = '<network_policy>'**
  Specifies the name of an existing network policy to apply to external OAuth sessions.

### External API Authentication (OAuth2) optional parameters

- **OAUTH_TOKEN_ENDPOINT = '<string_literal>'**
  Specifies the token endpoint URL of the external OAuth server.

- **OAUTH_AUTHORIZATION_ENDPOINT = '<string_literal>'**
  Specifies the authorization endpoint URL. Used with authorization code grant and JWT bearer flows.

- **OAUTH_CLIENT_AUTH_METHOD = { CLIENT_SECRET_BASIC | CLIENT_SECRET_POST }**
  Specifies how the client authenticates with the token endpoint:
  - `CLIENT_SECRET_BASIC`: Client credentials are sent in the HTTP Authorization header.
  - `CLIENT_SECRET_POST`: Client credentials are sent in the request body.
  Default: `CLIENT_SECRET_BASIC`

- **OAUTH_CLIENT_ID = '<string_literal>'**
  Specifies the client ID issued by the external OAuth server.

- **OAUTH_CLIENT_SECRET = '<string_literal>'**
  Specifies the client secret issued by the external OAuth server.

- **OAUTH_GRANT = { 'CLIENT_CREDENTIALS' | 'AUTHORIZATION_CODE' | 'JWT_BEARER' }**
  Specifies the OAuth grant type:
  - `'CLIENT_CREDENTIALS'`: Client credentials flow.
  - `'AUTHORIZATION_CODE'`: Authorization code grant flow.
  - `'JWT_BEARER'`: JWT bearer token flow.

- **OAUTH_ACCESS_TOKEN_VALIDITY = <integer>**
  Specifies the lifetime (in seconds) of the access token.

- **OAUTH_REFRESH_TOKEN_VALIDITY = <integer>**
  Specifies the lifetime (in seconds) of the refresh token. Available for authorization code grant and JWT bearer flows.

- **OAUTH_ALLOWED_SCOPES = ( '<scope_1>' [ , '<scope_2>' ... ] )**
  Specifies the OAuth scopes to request from the authorization server. Available only for client credentials flow.

## Access control requirements

A role used to execute this operation must have the following privileges at a minimum:

| Privilege | Object | Notes |
|---|---|---|
| CREATE INTEGRATION | Account | Only the ACCOUNTADMIN role has this privilege by default. The privilege can be granted to additional roles as needed. |

For External API Authentication (TYPE = API_AUTHENTICATION) only, the `CREATE SECURITY INTEGRATION` privilege on Account can also be used. This grants the ability to create API_AUTHENTICATION type security integrations only, without full CREATE INTEGRATION access.

## Usage notes

- The OR REPLACE and IF NOT EXISTS clauses are mutually exclusive. They cannot both be used in the same statement.

- CREATE OR REPLACE <object> statements are atomic. That is, when an object is replaced, the old object is deleted and the new object is created in a single transaction.

- For SCIM integrations, the RUN_AS_ROLE value is case-sensitive. Use the predefined role that matches your SCIM_CLIENT setting.

- For SAML2 integrations, you must specify either METADATA_URL or the full set of IdP parameters (SAML2_ISSUER, SAML2_SSO_URL, SAML2_PROVIDER, SAML2_X509_CERT). METADATA_URL is only supported for Okta and Microsoft Entra ID.

- For SAML2 integrations, the SAML2_X509_CERT value must be on a single line without the leading `-----BEGIN CERTIFICATE-----` and ending `-----END CERTIFICATE-----` markers.

- For Snowflake OAuth partner integrations, OAUTH_REDIRECT_URI is required for Looker. For Tableau Desktop and Tableau Server, this parameter is typically set by the application.

- For Snowflake OAuth custom integrations, the redirect URI must use TLS (HTTPS) unless OAUTH_ALLOW_NON_TLS_REDIRECT_URI is set to TRUE. Non-TLS redirect URIs should only be used in development or testing environments.

- For Snowflake OAuth integrations, the roles ACCOUNTADMIN, ORGADMIN, GLOBALORGADMIN, and SECURITYADMIN are included in the blocked roles list by default.

- For External OAuth integrations, Azure supports up to 3 JWS keys URLs while other provider types support 1 URL.

- For External API Authentication with AWS IAM, the integration stores a reference to the specified IAM role ARN. Snowflake assumes this role when making API calls.

- SYNC_PASSWORD is supported for Okta and Custom SCIM integrations. Microsoft Entra ID SCIM integrations are not supported because Microsoft Entra ID does not support password synchronization.

Regarding metadata:

Attention

Customers should ensure that no personal data (other than for a User object), sensitive data, export-controlled data, or other regulated data is entered as metadata when using the Snowflake service. For more information, see Metadata fields in Snowflake.

## Examples

**SCIM (Azure):**

```sql
CREATE SECURITY INTEGRATION azure_scim_int
  TYPE = SCIM
  ENABLED = TRUE
  SCIM_CLIENT = 'AZURE'
  RUN_AS_ROLE = 'AAD_PROVISIONER';
```

**SCIM (Okta with network policy and password sync):**

```sql
CREATE SECURITY INTEGRATION okta_scim_int
  TYPE = SCIM
  ENABLED = TRUE
  SCIM_CLIENT = 'OKTA'
  RUN_AS_ROLE = 'OKTA_PROVISIONER'
  NETWORK_POLICY = 'okta_network_policy'
  SYNC_PASSWORD = TRUE;
```

**SAML2 (using metadata URL):**

```sql
CREATE SECURITY INTEGRATION my_idp
  TYPE = SAML2
  ENABLED = TRUE
  METADATA_URL = 'https://integrator-26580.okta.com/app/ex2kbcS30N697/sso/saml/metadata'
  SAML2_SNOWFLAKE_ISSUER_URL = 'https://myorg-acct1.privatelink.snowflakecomputing.com'
  SAML2_SNOWFLAKE_ACS_URL = 'https://myorg-acct1.privatelink.snowflakecomputing.com/fed/login';
```

**SAML2 (using IdP parameters):**

```sql
CREATE SECURITY INTEGRATION my_adfs_idp
  TYPE = SAML2
  ENABLED = TRUE
  SAML2_ISSUER = 'http://adfs.example.com/adfs/services/trust'
  SAML2_SSO_URL = 'https://adfs.example.com/adfs/ls/'
  SAML2_PROVIDER = 'ADFS'
  SAML2_X509_CERT = 'MIICrzCCAZegAwIBAgIQN6p...'
  SAML2_SP_INITIATED_LOGIN_PAGE_LABEL = 'ADFS SSO'
  SAML2_ENABLE_SP_INITIATED = TRUE;
```

**Snowflake OAuth (Tableau Desktop):**

```sql
CREATE SECURITY INTEGRATION tableau_desktop_int
  TYPE = OAUTH
  OAUTH_CLIENT = TABLEAU_DESKTOP
  ENABLED = TRUE;
```

**Snowflake OAuth (Tableau Cloud):**

```sql
CREATE SECURITY INTEGRATION tableau_server_int
  TYPE = OAUTH
  OAUTH_CLIENT = TABLEAU_SERVER
  ENABLED = TRUE;
```

**Snowflake OAuth (Custom Confidential Client):**

```sql
CREATE SECURITY INTEGRATION custom_oauth_int
  TYPE = OAUTH
  OAUTH_CLIENT = CUSTOM
  OAUTH_CLIENT_TYPE = 'CONFIDENTIAL'
  OAUTH_REDIRECT_URI = 'https://localhost.com'
  ENABLED = TRUE
  PRE_AUTHORIZED_ROLES_LIST = ('MYROLE');
```

**External OAuth (Azure):**

```sql
CREATE SECURITY INTEGRATION azure_ext_oauth_int
  TYPE = EXTERNAL_OAUTH
  ENABLED = TRUE
  EXTERNAL_OAUTH_TYPE = AZURE
  EXTERNAL_OAUTH_ISSUER = 'https://sts.windows.net/a123b4c5-1234-123a-a12b-1a23b45678c9/'
  EXTERNAL_OAUTH_JWS_KEYS_URL = 'https://login.microsoftonline.com/a123b4c5-1234-123a-a12b-1a23b45678c9/discovery/v2.0/keys'
  EXTERNAL_OAUTH_TOKEN_USER_MAPPING_CLAIM = 'upn'
  EXTERNAL_OAUTH_SNOWFLAKE_USER_MAPPING_ATTRIBUTE = 'LOGIN_NAME'
  EXTERNAL_OAUTH_AUDIENCE_LIST = ('https://analysis.windows.net/powerbi/connector/Snowflake');
```

**External OAuth (Okta):**

```sql
CREATE SECURITY INTEGRATION okta_ext_oauth_int
  TYPE = EXTERNAL_OAUTH
  ENABLED = TRUE
  EXTERNAL_OAUTH_TYPE = OKTA
  EXTERNAL_OAUTH_ISSUER = 'https://myorg.okta.com/oauth2/ausp0erevvpnOIR3l5d7'
  EXTERNAL_OAUTH_JWS_KEYS_URL = 'https://myorg.okta.com/oauth2/ausp0erevvpnOIR3l5d7/v1/keys'
  EXTERNAL_OAUTH_TOKEN_USER_MAPPING_CLAIM = 'sub'
  EXTERNAL_OAUTH_SNOWFLAKE_USER_MAPPING_ATTRIBUTE = 'LOGIN_NAME';
```

**External API Authentication (Client Credentials - ServiceNow):**

```sql
CREATE SECURITY INTEGRATION servicenow_oauth_int
  TYPE = API_AUTHENTICATION
  AUTH_TYPE = OAUTH2
  ENABLED = TRUE
  OAUTH_TOKEN_ENDPOINT = 'https://myinstance.service-now.com/oauth_token.do'
  OAUTH_CLIENT_AUTH_METHOD = CLIENT_SECRET_POST
  OAUTH_CLIENT_ID = '1234567890abcdef'
  OAUTH_CLIENT_SECRET = 'mysecretvalue'
  OAUTH_GRANT = 'CLIENT_CREDENTIALS'
  OAUTH_ALLOWED_SCOPES = ('useraccount');
```

**External API Authentication (Authorization Code Grant):**

```sql
CREATE SECURITY INTEGRATION authcode_oauth_int
  TYPE = API_AUTHENTICATION
  AUTH_TYPE = OAUTH2
  ENABLED = TRUE
  OAUTH_AUTHORIZATION_ENDPOINT = 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize'
  OAUTH_TOKEN_ENDPOINT = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'
  OAUTH_CLIENT_AUTH_METHOD = CLIENT_SECRET_POST
  OAUTH_CLIENT_ID = '1234567890abcdef'
  OAUTH_CLIENT_SECRET = 'mysecretvalue'
  OAUTH_GRANT = 'AUTHORIZATION_CODE';
```

**External API Authentication (AWS IAM):**

```sql
CREATE SECURITY INTEGRATION aws_iam_int
  TYPE = API_AUTHENTICATION
  AUTH_TYPE = AWS_IAM
  AWS_ROLE_ARN = 'arn:aws:iam::001234567890:role/myrole'
  ENABLED = TRUE;
```

**Using OR REPLACE:**

```sql
CREATE OR REPLACE SECURITY INTEGRATION okta_scim_int
  TYPE = SCIM
  ENABLED = TRUE
  SCIM_CLIENT = 'OKTA'
  RUN_AS_ROLE = 'OKTA_PROVISIONER';
```

**Using IF NOT EXISTS:**

```sql
CREATE SECURITY INTEGRATION IF NOT EXISTS azure_scim_int
  TYPE = SCIM
  ENABLED = TRUE
  SCIM_CLIENT = 'AZURE'
  RUN_AS_ROLE = 'AAD_PROVISIONER';
```
