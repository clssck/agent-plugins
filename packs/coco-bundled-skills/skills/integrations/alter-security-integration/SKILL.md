---
name: alter-security-integration
description: >
  Modify properties of an existing security integration (SCIM, SAML2, Snowflake OAuth, External OAuth, External API Authentication, or AWS IAM Authentication)
---

# ALTER SECURITY INTEGRATION

Modifies the properties for an existing security integration. The settable properties depend on the type of security integration.

## Syntax

**SCIM:**

```sql
ALTER [ SECURITY ] INTEGRATION [ IF EXISTS ] <name> SET
  [ ENABLED = { TRUE | FALSE } ]
  [ NETWORK_POLICY = '<network_policy>' ]
  [ REJECT_TOKENS_ISSUED_BEFORE = '<datetime_string>' ]
  [ SYNC_PASSWORD = { TRUE | FALSE } ]
  [ COMMENT = '<string_literal>' ]
```

```sql
ALTER [ SECURITY ] INTEGRATION [ IF EXISTS ] <name> UNSET {
                                                            NETWORK_POLICY                |
                                                            REJECT_TOKENS_ISSUED_BEFORE   |
                                                            SYNC_PASSWORD                 |
                                                            COMMENT
                                                            }
                                                            [ , ... ]
```

```sql
ALTER [ SECURITY ] INTEGRATION <name> SET TAG <tag_name> = '<tag_value>' [ , <tag_name> = '<tag_value>' ... ]
```

```sql
ALTER [ SECURITY ] INTEGRATION <name> UNSET TAG <tag_name> [ , <tag_name> ... ]
```

**SAML2:**

```sql
ALTER [ SECURITY ] INTEGRATION [ IF EXISTS ] <name> SET
  [ TYPE = SAML2 ]
  [ ENABLED = { TRUE | FALSE } ]
  [ METADATA_URL = '<string_literal>' ]
  [ SAML2_ISSUER = '<string_literal>' ]
  [ SAML2_SSO_URL = '<string_literal>' ]
  [ SAML2_PROVIDER = '<string_literal>' ]
  [ SAML2_X509_CERT = '<string_literal>' ]
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

```sql
ALTER [ SECURITY ] INTEGRATION [ IF EXISTS ] <name> UNSET {
                                                            ENABLED |
                                                            [ , ... ]
                                                            }
```

```sql
ALTER [ SECURITY ] INTEGRATION <name> REFRESH
  [ SAML2_SNOWFLAKE_PRIVATE_KEY ]
  [ METADATA_URL ]
```

```sql
ALTER [ SECURITY ] INTEGRATION <name> SET TAG <tag_name> = '<tag_value>' [ , <tag_name> = '<tag_value>' ... ]
```

```sql
ALTER [ SECURITY ] INTEGRATION <name> UNSET TAG <tag_name> [ , <tag_name> ... ]
```

**Snowflake OAuth (Partner Applications):**

```sql
ALTER [ SECURITY ] INTEGRATION [ IF EXISTS ] <name> SET
  [ ENABLED = { TRUE | FALSE } ]
  [ OAUTH_ISSUE_REFRESH_TOKENS = { TRUE | FALSE } ]
  [ OAUTH_REDIRECT_URI = '<uri>' ]
  [ OAUTH_REFRESH_TOKEN_VALIDITY = <integer> ]
  [ OAUTH_SINGLE_USE_REFRESH_TOKENS_REQUIRED = { TRUE | FALSE } ]
  [ OAUTH_USE_SECONDARY_ROLES = { IMPLICIT | NONE } ]
  [ BLOCKED_ROLES_LIST = ( '<role_name>' [ , '<role_name>' , ... ] ) ]
  [ NETWORK_POLICY = '<network_policy>' ]
  [ USE_PRIVATELINK_FOR_AUTHORIZATION_ENDPOINT = { TRUE | FALSE } ]
  [ COMMENT = '<string_literal>' ]
```

```sql
ALTER [ SECURITY ] INTEGRATION [ IF EXISTS ] <name> UNSET {
                                                            ENABLED   |
                                                            COMMENT
                                                            }
                                                            [ , ... ]
```

```sql
ALTER [ SECURITY ] INTEGRATION [ IF EXISTS ] <name> REFRESH { OAUTH_CLIENT_SECRET | OAUTH_CLIENT_SECRET_2 }
```

```sql
ALTER [ SECURITY ] INTEGRATION <name> SET TAG <tag_name> = '<tag_value>' [ , <tag_name> = '<tag_value>' ... ]
```

```sql
ALTER [ SECURITY ] INTEGRATION <name> UNSET TAG <tag_name> [ , <tag_name> ... ]
```

**Snowflake OAuth (Custom Clients):**

```sql
ALTER [ SECURITY ] INTEGRATION [ IF EXISTS ] <name> SET
  [ ENABLED = { TRUE | FALSE } ]
  [ OAUTH_REDIRECT_URI = '<uri>' ]
  [ OAUTH_ALLOW_NON_TLS_REDIRECT_URI = { TRUE | FALSE } ]
  [ OAUTH_ENFORCE_PKCE = { TRUE | FALSE } ]
  [ PRE_AUTHORIZED_ROLES_LIST = ( '<role_name>' [ , '<role_name>' , ... ] ) ]
  [ BLOCKED_ROLES_LIST = ( '<role_name>' [ , '<role_name>' , ... ] ) ]
  [ OAUTH_ISSUE_REFRESH_TOKENS = { TRUE | FALSE } ]
  [ OAUTH_REFRESH_TOKEN_VALIDITY = <integer> ]
  [ OAUTH_SINGLE_USE_REFRESH_TOKENS_REQUIRED = { TRUE | FALSE } ]
  [ OAUTH_USE_SECONDARY_ROLES = { IMPLICIT | NONE } ]
  [ NETWORK_POLICY = '<network_policy>' ]
  [ OAUTH_CLIENT_RSA_PUBLIC_KEY = <public_key1> ]
  [ OAUTH_CLIENT_RSA_PUBLIC_KEY_2 = <public_key2> ]
  [ USE_PRIVATELINK_FOR_AUTHORIZATION_ENDPOINT = { TRUE | FALSE } ]
  [ COMMENT = '<string_literal>' ]
```

```sql
ALTER [ SECURITY ] INTEGRATION [ IF EXISTS ] <name> UNSET {
                                                            ENABLED                        |
                                                            NETWORK_POLICY                 |
                                                            OAUTH_CLIENT_RSA_PUBLIC_KEY    |
                                                            OAUTH_CLIENT_RSA_PUBLIC_KEY_2  |
                                                            OAUTH_USE_SECONDARY_ROLES = IMPLICIT | NONE |
                                                            COMMENT
                                                            }
                                                            [ , ... ]
```

```sql
ALTER [ SECURITY ] INTEGRATION [ IF EXISTS ] <name> REFRESH { OAUTH_CLIENT_SECRET | OAUTH_CLIENT_SECRET_2 }
```

```sql
ALTER [ SECURITY ] INTEGRATION <name> SET TAG <tag_name> = '<tag_value>' [ , <tag_name> = '<tag_value>' ... ]
```

```sql
ALTER [ SECURITY ] INTEGRATION <name> UNSET TAG <tag_name> [ , <tag_name> ... ]
```

**External OAuth:**

```sql
ALTER [ SECURITY ] INTEGRATION [ IF EXISTS ] <name> SET
  [ TYPE = EXTERNAL_OAUTH ]
  [ ENABLED = { TRUE | FALSE } ]
  [ EXTERNAL_OAUTH_TYPE = { OKTA | AZURE | PING_FEDERATE | CUSTOM } ]
  [ EXTERNAL_OAUTH_ISSUER = '<string_literal>' ]
  [ EXTERNAL_OAUTH_TOKEN_USER_MAPPING_CLAIM = '<string_literal>' | ('<string_literal>', '<string_literal>' [ , ... ] ) ]
  [ EXTERNAL_OAUTH_SNOWFLAKE_USER_MAPPING_ATTRIBUTE = 'LOGIN_NAME | EMAIL_ADDRESS' ]
  [ EXTERNAL_OAUTH_JWS_KEYS_URL = '<string_literal>' ]
  -- For AZURE type, multiple URLs supported (up to 3):
  -- [ EXTERNAL_OAUTH_JWS_KEYS_URL = ('<string_literal>' [ , '<string_literal>' ... ] ) ]
  [ EXTERNAL_OAUTH_RSA_PUBLIC_KEY = <public_key1> ]
  [ EXTERNAL_OAUTH_RSA_PUBLIC_KEY_2 = <public_key2> ]
  [ EXTERNAL_OAUTH_BLOCKED_ROLES_LIST = ( '<role_name>' [ , '<role_name>' , ... ] ) ]
  [ EXTERNAL_OAUTH_ALLOWED_ROLES_LIST = ( '<role_name>' [ , '<role_name>' , ... ] ) ]
  [ EXTERNAL_OAUTH_AUDIENCE_LIST = ('<string_literal>') ]
  [ EXTERNAL_OAUTH_ANY_ROLE_MODE = { DISABLE | ENABLE | ENABLE_FOR_PRIVILEGE } ]
  [ EXTERNAL_OAUTH_SCOPE_DELIMITER = '<string_literal>' ]
  [ NETWORK_POLICY = '<network_policy>' ]
  [ COMMENT = '<string_literal>' ]
```

```sql
ALTER [ SECURITY ] INTEGRATION [ IF EXISTS ] <name> UNSET {
                                                            ENABLED                        |
                                                            EXTERNAL_OAUTH_AUDIENCE_LIST
                                                            }
                                                            [ , ... ]
```

```sql
ALTER [ SECURITY ] INTEGRATION <name> SET TAG <tag_name> = '<tag_value>' [ , <tag_name> = '<tag_value>' ... ]
```

```sql
ALTER [ SECURITY ] INTEGRATION <name> UNSET TAG <tag_name> [ , <tag_name> ... ]
```

**External API Authentication (Client Credentials):**

```sql
ALTER SECURITY INTEGRATION <name> SET
  [ ENABLED = { TRUE | FALSE } ]
  [ OAUTH_TOKEN_ENDPOINT = '<string_literal>' ]
  [ OAUTH_CLIENT_AUTH_METHOD = { CLIENT_SECRET_BASIC | CLIENT_SECRET_POST } ]
  [ OAUTH_CLIENT_ID = '<string_literal>' ]
  [ OAUTH_CLIENT_SECRET = '<string_literal>' ]
  [ OAUTH_GRANT = 'CLIENT_CREDENTIALS' ]
  [ OAUTH_ACCESS_TOKEN_VALIDITY = <integer> ]
  [ OAUTH_ALLOWED_SCOPES = ( '<scope_1>' [ , '<scope_2>' ... ] ) ]
  [ COMMENT = '<string_literal>' ]
```

**External API Authentication (Authorization Code Grant):**

```sql
ALTER SECURITY INTEGRATION <name> SET
  [ ENABLED = { TRUE | FALSE } ]
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

**External API Authentication (JWT Bearer):**

```sql
ALTER SECURITY INTEGRATION <name> SET
  [ ENABLED = { TRUE | FALSE } ]
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

```sql
ALTER [ SECURITY ] INTEGRATION [ IF EXISTS ] <name> UNSET {
  ENABLED | [ , ... ]
}
```

```sql
ALTER [ SECURITY ] INTEGRATION <name> SET TAG <tag_name> = '<tag_value>' [ , <tag_name> = '<tag_value>' ... ]
```

```sql
ALTER [ SECURITY ] INTEGRATION <name> UNSET TAG <tag_name> [ , <tag_name> ... ]
```

**AWS IAM Authentication:**

```sql
ALTER [ SECURITY ] INTEGRATION [ IF EXISTS ] <name> SET
  [ TYPE = AWS_IAM ]
  [ AWS_ROLE_ARN = '<iam_role_arn>' ]
  [ ENABLED = { TRUE | FALSE } ]
  [ COMMENT = '<string_literal>' ]
```

```sql
ALTER [ SECURITY ] INTEGRATION <name> SET TAG <tag_name> = '<tag_value>' [ , <tag_name> = '<tag_value>' ... ]
```

```sql
ALTER [ SECURITY ] INTEGRATION <name> UNSET TAG <tag_name> [ , <tag_name> ... ]
```

## Parameters

- **`<name>`**

    Identifier for the integration to alter. If the identifier contains spaces or special characters, the entire string must be enclosed in double quotes. Identifiers enclosed in double quotes are also case-sensitive.

- **SET ...**

    Specifies one or more properties/parameters to set for the integration (separated by blank spaces, commas, or new lines):

  - **ENABLED = { TRUE | FALSE }**

    Specifies whether this security integration is available for usage.

    - `TRUE` activates the integration for immediate operation.

    - `FALSE` suspends the integration for maintenance. When disabled, integration with third-party services fails.

  - **TAG <tag_name> = '<tag_value>' [ , <tag_name> = '<tag_value>' , ... ]**

    Specifies the tag name and the tag string value.

    The tag value is always a string, and the maximum number of characters for the tag value is 256.

  - **COMMENT = '<string_literal>'**

    String (literal) that specifies a comment for the integration.

### SCIM settable parameters

  - **NETWORK_POLICY = '<network_policy>'**

    Specifies an existing network policy that controls SCIM network traffic.

  - **REJECT_TOKENS_ISSUED_BEFORE = '<datetime_string>'**

    Specifies a cutoff datetime; tokens issued before this value are rejected. Accepts any valid Snowflake timestamp format, with optional timezone. Examples: `'Tue, 30 Sep 2025 12:30:00 -0700'`, `'2025-09-30 12:30:00'`. This parameter cannot be set during creation - it can only be set post-creation via ALTER. Default: no earliest issue date (all tokens accepted regardless of issue time).

  - **SYNC_PASSWORD = { TRUE | FALSE }**

    Specifies whether to synchronize passwords from the identity provider. Supported for Okta and Custom SCIM integrations. Microsoft Entra ID does not support password synchronization.

    - `TRUE` enables password sync from the identity provider.

    - `FALSE` disables password sync.

### SAML2 settable parameters

  - **METADATA_URL = '<string_literal>'**

    Specifies a metadata URL pointing to the identity provider configuration. This parameter is only supported for Okta and Microsoft Entra ID. When METADATA_URL is specified, you cannot use SAML2_ISSUER, SAML2_SSO_URL, SAML2_PROVIDER, or SAML2_X509_CERT - these values are read from the metadata URL instead.

  - **SAML2_ISSUER = '<string_literal>'**

    Specifies the entity ID / issuer for the SAML identity provider. Cannot be used when METADATA_URL is set.

  - **SAML2_SSO_URL = '<string_literal>'**

    Specifies the SSO URL of the identity provider where Snowflake sends SAML authentication requests. Cannot be used when METADATA_URL is set.

  - **SAML2_PROVIDER = '<string_literal>'**

    Specifies the SAML identity provider (e.g., `'ADFS'`, `'OKTA'`, `'CUSTOM'`). Cannot be used when METADATA_URL is set.

  - **SAML2_X509_CERT = '<string_literal>'**

    Specifies the Base64-encoded X.509 certificate of the identity provider used to verify SAML assertions. Cannot be used when METADATA_URL is set.

  - **ALLOWED_USER_DOMAINS = ( '<string_literal>' [ , '<string_literal>' , ... ] )**

    Specifies the list of email domains that are allowed to authenticate using this SAML integration.

  - **ALLOWED_EMAIL_PATTERNS = ( '<string_literal>' [ , '<string_literal>' , ... ] )**

    Specifies a list of regular expression patterns for email addresses allowed to authenticate via this SAML integration.

  - **SAML2_SP_INITIATED_LOGIN_PAGE_LABEL = '<string_literal>'**

    Specifies the label displayed for the SP-initiated login option on the Snowflake login page.

  - **SAML2_ENABLE_SP_INITIATED = TRUE | FALSE**

    Specifies whether to enable SP-initiated login for the integration.

    - `TRUE` enables the SP-initiated login flow.

    - `FALSE` disables SP-initiated login.

  - **SAML2_SNOWFLAKE_X509_CERT = '<string_literal>'**

    Specifies the Base64-encoded self-signed X.509 certificate generated by Snowflake for use with Encrypted Assertions and Signed Requests. Upload this certificate to the identity provider.

  - **SAML2_SIGN_REQUEST = TRUE | FALSE**

    Specifies whether Snowflake signs SAML authentication requests sent to the identity provider.

    - `TRUE` enables signed requests.

    - `FALSE` disables signed requests.

  - **SAML2_REQUESTED_NAMEID_FORMAT = '<string_literal>'**

    Specifies the NameID format requested in SAML authentication requests (e.g., `'urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress'`).

  - **SAML2_POST_LOGOUT_REDIRECT_URL = '<string_literal>'**

    Specifies the URL to redirect users to after SAML logout.

  - **SAML2_FORCE_AUTHN = TRUE | FALSE**

    Specifies whether to force re-authentication at the identity provider, even if the user has an active session.

    - `TRUE` forces re-authentication.

    - `FALSE` allows the existing IdP session to be used.

  - **SAML2_SNOWFLAKE_ISSUER_URL = '<string_literal>'**

    Specifies the Snowflake issuer URL used in SAML requests.

  - **SAML2_SNOWFLAKE_ACS_URL = '<string_literal>'**

    Specifies the Snowflake Assertion Consumer Service (ACS) URL where the identity provider sends SAML responses.

### Snowflake OAuth settable parameters (Partner Applications)

  - **OAUTH_ISSUE_REFRESH_TOKENS = { TRUE | FALSE }**

    Specifies whether to issue refresh tokens when the user authenticates.

    - `TRUE` issues refresh tokens.

    - `FALSE` does not issue refresh tokens; the user must re-authenticate when the access token expires.

  - **OAUTH_REDIRECT_URI = '<uri>'**

    Specifies the redirect URI for the client application. The URI must match the redirect URI registered with the partner application.

  - **OAUTH_REFRESH_TOKEN_VALIDITY = <integer>**

    Specifies the number of seconds the refresh token is valid. Valid range: 86400 (1 day) to 7776000 (90 days). Default: 7776000.

  - **OAUTH_SINGLE_USE_REFRESH_TOKENS_REQUIRED = { TRUE | FALSE }**

    Specifies whether the client exchanges a refresh token for a new one with each use.

    - `TRUE` requires a new refresh token on each exchange (rotation).

    - `FALSE` allows the same refresh token to be used repeatedly.

  - **OAUTH_USE_SECONDARY_ROLES = { IMPLICIT | NONE }**

    Specifies the secondary roles scope for the integration.

    - `IMPLICIT` allows secondary roles to be used.

    - `NONE` does not use secondary roles.

  - **BLOCKED_ROLES_LIST = ( '<role_name>' [ , '<role_name>' , ... ] )**

    Specifies a comma-separated list of Snowflake roles that users cannot consent to use with this integration. The ACCOUNTADMIN, ORGADMIN, GLOBALORGADMIN, and SECURITYADMIN roles are included in this list by default.

  - **NETWORK_POLICY = '<network_policy>'**

    Specifies an existing network policy to apply to OAuth traffic for this integration.

  - **USE_PRIVATELINK_FOR_AUTHORIZATION_ENDPOINT = { TRUE | FALSE }**

    Specifies whether to use a PrivateLink endpoint for the OAuth authorization endpoint.

### Snowflake OAuth settable parameters (Custom Clients)

  - **OAUTH_REDIRECT_URI = '<uri>'**

    Specifies the redirect URI registered for the client.

  - **OAUTH_ALLOW_NON_TLS_REDIRECT_URI = { TRUE | FALSE }**

    Specifies whether the redirect URI can use HTTP instead of HTTPS. For testing only; not recommended for production.

  - **OAUTH_ENFORCE_PKCE = { TRUE | FALSE }**

    Specifies whether Proof Key for Code Exchange (PKCE) is required for the authorization code grant flow.

    - `TRUE` enforces PKCE.

    - `FALSE` makes PKCE optional.

  - **PRE_AUTHORIZED_ROLES_LIST = ( '<role_name>' [ , '<role_name>' , ... ] )**

    Specifies a comma-separated list of Snowflake roles that a user does not need to explicitly consent to use. Available for confidential clients only. Cannot include ACCOUNTADMIN, ORGADMIN, GLOBALORGADMIN, or SECURITYADMIN.

  - **BLOCKED_ROLES_LIST = ( '<role_name>' [ , '<role_name>' , ... ] )**

    Specifies a comma-separated list of Snowflake roles that users cannot consent to use with this integration. The ACCOUNTADMIN, ORGADMIN, GLOBALORGADMIN, and SECURITYADMIN roles are included in this list by default.

  - **OAUTH_ISSUE_REFRESH_TOKENS = { TRUE | FALSE }**

    Specifies whether to issue refresh tokens.

  - **OAUTH_REFRESH_TOKEN_VALIDITY = <integer>**

    Specifies the number of seconds the refresh token is valid. Valid ranges depend on the client type:

    - Tableau Desktop: 60-36000 seconds (default 36000)

    - Tableau Cloud: 60-7776000 seconds (default 7776000)

    - Custom client: 86400-7776000 seconds (default 7776000)

  - **OAUTH_SINGLE_USE_REFRESH_TOKENS_REQUIRED = { TRUE | FALSE }**

    Specifies whether the client must exchange a refresh token for a new one with each use.

  - **OAUTH_USE_SECONDARY_ROLES = { IMPLICIT | NONE }**

    Specifies the secondary roles scope for the integration.

  - **NETWORK_POLICY = '<network_policy>'**

    Specifies an existing network policy to apply to OAuth traffic for this integration.

  - **OAUTH_CLIENT_RSA_PUBLIC_KEY = <public_key1>**

    Specifies the RSA public key for key-pair authentication with the client. Only the key value (without the PEM header/footer) is needed.

  - **OAUTH_CLIENT_RSA_PUBLIC_KEY_2 = <public_key2>**

    Specifies a second RSA public key for key rotation. During key rotation, both keys are accepted until the old one is unset.

  - **USE_PRIVATELINK_FOR_AUTHORIZATION_ENDPOINT = { TRUE | FALSE }**

    Specifies whether to use a PrivateLink endpoint for the OAuth authorization endpoint.

### External OAuth settable parameters

  - **EXTERNAL_OAUTH_TYPE = { OKTA | AZURE | PING_FEDERATE | CUSTOM }**

    Specifies the external OAuth provider type.

  - **EXTERNAL_OAUTH_ISSUER = '<string_literal>'**

    Specifies the URL that uniquely identifies the external OAuth authorization server (issuer).

  - **EXTERNAL_OAUTH_TOKEN_USER_MAPPING_CLAIM = '<string_literal>' | ('<string_literal>', '<string_literal>' [ , ... ] )**

    Specifies the access token claim(s) that map to the Snowflake user. Can be a single string or a list of strings.

  - **EXTERNAL_OAUTH_SNOWFLAKE_USER_MAPPING_ATTRIBUTE = 'LOGIN_NAME | EMAIL_ADDRESS'**

    Specifies the Snowflake user attribute used to map the token claim to a Snowflake user.

    - `LOGIN_NAME` maps to the user's login name.

    - `EMAIL_ADDRESS` maps to the user's email address.

  - **EXTERNAL_OAUTH_JWS_KEYS_URL = '<string_literal>' | ('<string_literal>' [ , '<string_literal>' ... ] )**

    Specifies the URL(s) for the JSON Web Key Set (JWKS) used to verify access token signatures. Azure supports up to 3 URLs; all other providers support 1 URL.

  - **EXTERNAL_OAUTH_RSA_PUBLIC_KEY = <public_key1>**

    Specifies the Base64-encoded RSA public key for verifying access tokens. Used as an alternative to EXTERNAL_OAUTH_JWS_KEYS_URL.

  - **EXTERNAL_OAUTH_RSA_PUBLIC_KEY_2 = <public_key2>**

    Specifies a second RSA public key for key rotation.

  - **EXTERNAL_OAUTH_BLOCKED_ROLES_LIST = ( '<role_name>' [ , '<role_name>' , ... ] )**

    Specifies a comma-separated list of Snowflake roles that external OAuth tokens cannot be used to assume.

  - **EXTERNAL_OAUTH_ALLOWED_ROLES_LIST = ( '<role_name>' [ , '<role_name>' , ... ] )**

    Specifies a comma-separated list of Snowflake roles that external OAuth tokens are allowed to assume.

  - **EXTERNAL_OAUTH_AUDIENCE_LIST = ('<string_literal>')**

    Specifies the audience (aud) value(s) that the access token must contain.

  - **EXTERNAL_OAUTH_ANY_ROLE_MODE = { DISABLE | ENABLE | ENABLE_FOR_PRIVILEGE }**

    Specifies whether the OAuth client or user can use a role that is not defined in the access token.

    - `DISABLE` (default) does not allow roles outside the access token.

    - `ENABLE` allows any role the user has been granted.

    - `ENABLE_FOR_PRIVILEGE` allows any role for users granted the USE_ANY_ROLE privilege on the integration.

  - **EXTERNAL_OAUTH_SCOPE_DELIMITER = '<string_literal>'**

    Specifies the delimiter used to separate scopes in the access token. Available only for CUSTOM type integrations and requires enablement by the Snowflake support team.

  - **NETWORK_POLICY = '<network_policy>'**

    Specifies an existing network policy to apply to external OAuth traffic for this integration.

### External API Authentication settable parameters

  - **OAUTH_TOKEN_ENDPOINT = '<string_literal>'**

    Specifies the token endpoint URL of the external authorization server.

  - **OAUTH_AUTHORIZATION_ENDPOINT = '<string_literal>'**

    Specifies the authorization endpoint URL of the external authorization server. Used with Authorization Code Grant and JWT Bearer flows.

  - **OAUTH_CLIENT_AUTH_METHOD = { CLIENT_SECRET_BASIC | CLIENT_SECRET_POST }**

    Specifies how the client authenticates to the token endpoint.

    - `CLIENT_SECRET_BASIC` sends credentials in the Authorization header.

    - `CLIENT_SECRET_POST` sends credentials in the request body.

  - **OAUTH_CLIENT_ID = '<string_literal>'**

    Specifies the client identifier issued by the authorization server.

  - **OAUTH_CLIENT_SECRET = '<string_literal>'**

    Specifies the client secret issued by the authorization server.

  - **OAUTH_GRANT = 'CLIENT_CREDENTIALS' | 'AUTHORIZATION_CODE' | 'JWT_BEARER'**

    Specifies the OAuth grant type for the integration.

  - **OAUTH_ACCESS_TOKEN_VALIDITY = <integer>**

    Specifies the validity period in seconds for the access token.

  - **OAUTH_REFRESH_TOKEN_VALIDITY = <integer>**

    Specifies the validity period in seconds for the refresh token. Used with Authorization Code Grant and JWT Bearer flows.

  - **OAUTH_ALLOWED_SCOPES = ( '<scope_1>' [ , '<scope_2>' ... ] )**

    Specifies the list of allowed OAuth scopes. Used with Client Credentials flow.

### AWS IAM Authentication settable parameters

  - **AWS_ROLE_ARN = '<iam_role_arn>'**

    Specifies the Amazon Resource Name (ARN) of the AWS IAM role to use for authentication.

- **UNSET ...**

    Specifies one or more properties/parameters to unset for the integration, which resets them back to their defaults.

    **For SCIM:**

    - `NETWORK_POLICY`

    - `REJECT_TOKENS_ISSUED_BEFORE`

    - `SYNC_PASSWORD`

    - `COMMENT`

    - `TAG` <tag_name> [ , <tag_name> ... ]

    **For SAML2:**

    - `ENABLED`

    - `TAG` <tag_name> [ , <tag_name> ... ]

    **For Snowflake OAuth (Partner Applications):**

    - `ENABLED`

    - `COMMENT`

    - `TAG` <tag_name> [ , <tag_name> ... ]

    **For Snowflake OAuth (Custom Clients):**

    - `ENABLED`

    - `NETWORK_POLICY`

    - `OAUTH_CLIENT_RSA_PUBLIC_KEY`

    - `OAUTH_CLIENT_RSA_PUBLIC_KEY_2`

    - `OAUTH_USE_SECONDARY_ROLES`

    - `COMMENT`

    - `TAG` <tag_name> [ , <tag_name> ... ]

    **For External OAuth:**

    - `ENABLED`

    - `EXTERNAL_OAUTH_AUDIENCE_LIST`

    - `TAG` <tag_name> [ , <tag_name> ... ]

    **For External API Authentication:**

    - `ENABLED`

    **For AWS IAM Authentication:**

    - `TAG` <tag_name> [ , <tag_name> ... ]

- **REFRESH ...**

    Regenerates or updates specific properties.

    **For SAML2:**

    - `REFRESH SAML2_SNOWFLAKE_PRIVATE_KEY` - Generates a new private key and self-signed certificate for the integration. The old private key and certificate are overwritten. After refreshing, you must upload the new SAML2_SNOWFLAKE_X509_CERT to the identity provider or SAML authentication will stop working.

    - `REFRESH METADATA_URL` - Updates the integration with the current identity provider configuration settings from the metadata URL.

    **For Snowflake OAuth (Partner and Custom Clients):**

    - `REFRESH OAUTH_CLIENT_SECRET` - Generates a new client secret for the integration.

    - `REFRESH OAUTH_CLIENT_SECRET_2` - Generates a second client secret for secret rotation.

## Access control requirements

A role used to execute this operation must have the following privileges at a minimum:

| Privilege | Object | Notes |
|---|---|---|
| OWNERSHIP | Integration | Required for all ALTER operations. The OWNERSHIP privilege on the integration is automatically granted to the role that created it and can be transferred via GRANT OWNERSHIP. |

## Usage notes

- SAML2: If METADATA_URL is specified, you cannot use SAML2_ISSUER, SAML2_SSO_URL, SAML2_PROVIDER, or SAML2_X509_CERT. These values are read from the metadata URL instead.

- SAML2: After refreshing the Snowflake private key (REFRESH SAML2_SNOWFLAKE_PRIVATE_KEY), you must upload the new SAML2_SNOWFLAKE_X509_CERT to the identity provider. Failing to do so will break SAML authentication.

- SCIM: The REJECT_TOKENS_ISSUED_BEFORE parameter cannot be set during integration creation. It can only be set after creation via ALTER.

- SCIM: The SYNC_PASSWORD parameter is supported for Okta and Custom SCIM integrations. Microsoft Entra ID does not support password synchronization.

- External OAuth: The EXTERNAL_OAUTH_SCOPE_DELIMITER parameter is available only for CUSTOM type integrations and requires enablement by the Snowflake support team.

- External OAuth: When using EXTERNAL_OAUTH_ANY_ROLE_MODE = ENABLE_FOR_PRIVILEGE, you must also grant the USE_ANY_ROLE privilege on the integration to the appropriate role.

- External OAuth: For Azure integrations, EXTERNAL_OAUTH_JWS_KEYS_URL supports up to 3 URLs. All other providers support 1 URL.

- Snowflake OAuth: OAUTH_REFRESH_TOKEN_VALIDITY valid ranges - Partner applications: 86400-7776000 (default 7776000). Custom clients: Tableau Desktop 60-36000 (default 36000), Tableau Cloud 60-7776000 (default 7776000), other custom clients 86400-7776000 (default 7776000).

- Snowflake OAuth: PRE_AUTHORIZED_ROLES_LIST is available for confidential custom clients only. ACCOUNTADMIN, ORGADMIN, GLOBALORGADMIN, and SECURITYADMIN cannot be included.

Regarding metadata:

Attention

Customers should ensure that no personal data (other than for a User object), sensitive data, export-controlled data, or other regulated data is entered as metadata when using the Snowflake service. For more information, see Metadata fields in Snowflake.

## Examples

**Enable a suspended SCIM integration:**

```sql
ALTER SECURITY INTEGRATION my_scim_int SET ENABLED = TRUE;
```

**Set a token rejection cutoff for a SCIM integration:**

```sql
ALTER SECURITY INTEGRATION my_scim_int SET
  REJECT_TOKENS_ISSUED_BEFORE = '2025-09-30 12:30:00';
```

**Apply a network policy to a SCIM integration:**

```sql
ALTER SECURITY INTEGRATION my_scim_int SET
  NETWORK_POLICY = 'scim_network_policy';
```

**Enable password sync for an Okta SCIM integration:**

```sql
ALTER SECURITY INTEGRATION my_okta_scim_int SET SYNC_PASSWORD = TRUE;
```

**Unset SCIM optional parameters:**

```sql
ALTER SECURITY INTEGRATION my_scim_int UNSET
  NETWORK_POLICY,
  REJECT_TOKENS_ISSUED_BEFORE,
  SYNC_PASSWORD;
```

**Update SAML2 identity provider settings:**

```sql
ALTER SECURITY INTEGRATION my_saml2_int SET
  SAML2_ISSUER = 'https://idp.example.com/saml/metadata'
  SAML2_SSO_URL = 'https://idp.example.com/saml/sso'
  SAML2_X509_CERT = 'MIICrjCCAZYCCQC...base64cert...==';
```

**Update SAML2 integration to use a metadata URL:**

```sql
ALTER SECURITY INTEGRATION my_saml2_int SET
  METADATA_URL = 'https://idp.example.com/saml/metadata.xml';
```

**Enable SP-initiated login for a SAML2 integration:**

```sql
ALTER SECURITY INTEGRATION my_saml2_int SET
  SAML2_ENABLE_SP_INITIATED = TRUE
  SAML2_SP_INITIATED_LOGIN_PAGE_LABEL = 'My Company SSO';
```

**Configure SAML2 request signing and NameID format:**

```sql
ALTER SECURITY INTEGRATION my_saml2_int SET
  SAML2_SIGN_REQUEST = TRUE
  SAML2_REQUESTED_NAMEID_FORMAT = 'urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress';
```

**Set allowed user domains for SAML2:**

```sql
ALTER SECURITY INTEGRATION my_saml2_int SET
  ALLOWED_USER_DOMAINS = ('example.com', 'corp.example.com')
  ALLOWED_EMAIL_PATTERNS = ('.*@example\\.com');
```

**Refresh the Snowflake private key for a SAML2 integration:**

```sql
ALTER SECURITY INTEGRATION my_saml2_int REFRESH SAML2_SNOWFLAKE_PRIVATE_KEY;
```

**Refresh SAML2 configuration from metadata URL:**

```sql
ALTER SECURITY INTEGRATION my_saml2_int REFRESH METADATA_URL;
```

**Update Snowflake OAuth partner application settings:**

```sql
ALTER SECURITY INTEGRATION my_tableau_int SET
  OAUTH_REFRESH_TOKEN_VALIDITY = 86400
  OAUTH_SINGLE_USE_REFRESH_TOKENS_REQUIRED = TRUE
  BLOCKED_ROLES_LIST = ('ACCOUNTADMIN', 'SECURITYADMIN', 'SYSADMIN');
```

**Enable secondary roles for a Snowflake OAuth partner integration:**

```sql
ALTER SECURITY INTEGRATION my_partner_int SET
  OAUTH_USE_SECONDARY_ROLES = IMPLICIT;
```

**Refresh the client secret for a Snowflake OAuth integration:**

```sql
ALTER SECURITY INTEGRATION my_oauth_int REFRESH OAUTH_CLIENT_SECRET;
```

**Update Snowflake OAuth custom client settings:**

```sql
ALTER SECURITY INTEGRATION my_custom_oauth_int SET
  OAUTH_REDIRECT_URI = 'https://myapp.example.com/callback'
  OAUTH_ENFORCE_PKCE = TRUE
  OAUTH_REFRESH_TOKEN_VALIDITY = 604800;
```

**Set pre-authorized roles for a confidential custom OAuth client:**

```sql
ALTER SECURITY INTEGRATION my_custom_oauth_int SET
  PRE_AUTHORIZED_ROLES_LIST = ('DATA_ANALYST', 'DATA_ENGINEER');
```

**Set RSA public keys for a custom OAuth client:**

```sql
ALTER SECURITY INTEGRATION my_custom_oauth_int SET
  OAUTH_CLIENT_RSA_PUBLIC_KEY = 'MIIBIjANBgkq...publickey1...'
  OAUTH_CLIENT_RSA_PUBLIC_KEY_2 = 'MIIBIjANBgkq...publickey2...';
```

**Unset RSA public keys for key rotation cleanup:**

```sql
ALTER SECURITY INTEGRATION my_custom_oauth_int UNSET
  OAUTH_CLIENT_RSA_PUBLIC_KEY,
  OAUTH_CLIENT_RSA_PUBLIC_KEY_2;
```

**Apply a network policy and PrivateLink to a custom OAuth integration:**

```sql
ALTER SECURITY INTEGRATION my_custom_oauth_int SET
  NETWORK_POLICY = 'oauth_network_policy'
  USE_PRIVATELINK_FOR_AUTHORIZATION_ENDPOINT = TRUE;
```

**Update External OAuth integration for Okta:**

```sql
ALTER SECURITY INTEGRATION my_ext_oauth_int SET
  EXTERNAL_OAUTH_TYPE = OKTA
  EXTERNAL_OAUTH_ISSUER = 'https://dev-12345678.okta.com/oauth2/default'
  EXTERNAL_OAUTH_JWS_KEYS_URL = 'https://dev-12345678.okta.com/oauth2/default/v1/keys'
  EXTERNAL_OAUTH_TOKEN_USER_MAPPING_CLAIM = 'sub'
  EXTERNAL_OAUTH_SNOWFLAKE_USER_MAPPING_ATTRIBUTE = 'LOGIN_NAME';
```

**Update External OAuth integration for Azure with multiple JWKS URLs:**

```sql
ALTER SECURITY INTEGRATION my_azure_ext_oauth_int SET
  EXTERNAL_OAUTH_TYPE = AZURE
  EXTERNAL_OAUTH_JWS_KEYS_URL = (
    'https://login.microsoftonline.com/common/discovery/v2.0/keys',
    'https://login.microsoftonline.com/<tenant_id>/discovery/v2.0/keys'
  );
```

**Enable any-role mode with privilege for External OAuth:**

```sql
ALTER SECURITY INTEGRATION my_ext_oauth_int SET
  EXTERNAL_OAUTH_ANY_ROLE_MODE = ENABLE_FOR_PRIVILEGE;
```

**Set blocked and allowed roles for External OAuth:**

```sql
ALTER SECURITY INTEGRATION my_ext_oauth_int SET
  EXTERNAL_OAUTH_BLOCKED_ROLES_LIST = ('ACCOUNTADMIN', 'SECURITYADMIN')
  EXTERNAL_OAUTH_ALLOWED_ROLES_LIST = ('DATA_ANALYST', 'DATA_ENGINEER', 'PUBLIC');
```

**Set audience list for External OAuth:**

```sql
ALTER SECURITY INTEGRATION my_ext_oauth_int SET
  EXTERNAL_OAUTH_AUDIENCE_LIST = ('https://myaccount.snowflakecomputing.com');
```

**Unset External OAuth audience list:**

```sql
ALTER SECURITY INTEGRATION my_ext_oauth_int UNSET EXTERNAL_OAUTH_AUDIENCE_LIST;
```

**Update External API Authentication integration (Client Credentials):**

```sql
ALTER SECURITY INTEGRATION my_api_auth_int SET
  OAUTH_TOKEN_ENDPOINT = 'https://auth.example.com/oauth/token'
  OAUTH_CLIENT_ID = 'new_client_id'
  OAUTH_CLIENT_SECRET = 'new_client_secret'
  OAUTH_ACCESS_TOKEN_VALIDITY = 3600
  OAUTH_ALLOWED_SCOPES = ('read', 'write');
```

**Update External API Authentication integration (Authorization Code Grant):**

```sql
ALTER SECURITY INTEGRATION my_auth_code_int SET
  OAUTH_AUTHORIZATION_ENDPOINT = 'https://auth.example.com/authorize'
  OAUTH_TOKEN_ENDPOINT = 'https://auth.example.com/oauth/token'
  OAUTH_CLIENT_AUTH_METHOD = CLIENT_SECRET_POST
  OAUTH_REFRESH_TOKEN_VALIDITY = 7200;
```

**Update External API Authentication integration (JWT Bearer):**

```sql
ALTER SECURITY INTEGRATION my_jwt_int SET
  OAUTH_GRANT = 'JWT_BEARER'
  OAUTH_AUTHORIZATION_ENDPOINT = 'https://auth.example.com/authorize'
  OAUTH_TOKEN_ENDPOINT = 'https://auth.example.com/oauth/token'
  OAUTH_ACCESS_TOKEN_VALIDITY = 1800;
```

**Update AWS IAM Authentication integration:**

```sql
ALTER SECURITY INTEGRATION my_aws_iam_int SET
  AWS_ROLE_ARN = 'arn:aws:iam::123456789012:role/my-new-snowflake-role'
  ENABLED = TRUE;
```

**Disable an AWS IAM Authentication integration:**

```sql
ALTER SECURITY INTEGRATION my_aws_iam_int SET ENABLED = FALSE;
```

**Set a tag on a security integration:**

```sql
ALTER SECURITY INTEGRATION my_scim_int SET TAG cost_center = 'engineering';
```

**Set multiple tags:**

```sql
ALTER SECURITY INTEGRATION my_saml2_int SET TAG
  cost_center = 'engineering',
  environment = 'production';
```

**Unset a tag:**

```sql
ALTER SECURITY INTEGRATION my_ext_oauth_int UNSET TAG cost_center;
```

**Add a comment:**

```sql
ALTER SECURITY INTEGRATION my_scim_int SET COMMENT = 'SCIM integration for Okta user provisioning';
```

**Remove a comment:**

```sql
ALTER SECURITY INTEGRATION my_scim_int UNSET COMMENT;
```

**Using IF EXISTS:**

```sql
ALTER SECURITY INTEGRATION IF EXISTS my_old_integration SET ENABLED = FALSE;
```
