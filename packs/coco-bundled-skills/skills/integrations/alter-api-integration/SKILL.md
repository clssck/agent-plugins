---
name: alter-api-integration
description: >
  Modify properties of an existing API integration (AWS API Gateway, Azure API Management, Google Cloud API Gateway, or Git repository)
---

# ALTER API INTEGRATION


Modifies the properties of an existing API integration.

## Syntax

```sql
ALTER API INTEGRATION [ IF EXISTS ] <name> SET
  [ API_AWS_ROLE_ARN = '<iam_role>' ]
  [ AZURE_AD_APPLICATION_ID = '<azure_application_id>' ]
  [ API_KEY = '<api_key>' ]
  [ ENABLED = { TRUE | FALSE } ]
  [ API_ALLOWED_PREFIXES = ('<...>') ]
  [ API_BLOCKED_PREFIXES = ('<...>') ]
  [ ALLOWED_AUTHENTICATION_SECRETS = ( { <secret_name> [, <secret_name>, ... ] } ) | all | none ]
  [ COMMENT = '<string_literal>' ]
```

```sql
ALTER API INTEGRATION <name> SET TAG <tag_name> = '<tag_value>' [ , <tag_name> = '<tag_value>' ... ]
```

```sql
ALTER API INTEGRATION <name> UNSET TAG <tag_name> [ , <tag_name> ... ]
```

```sql
ALTER API INTEGRATION [ IF EXISTS ] <name>  UNSET {
                                                      API_KEY              |
                                                      ENABLED              |
                                                      API_BLOCKED_PREFIXES |
                                                      COMMENT
                                                      }
                                                      [ , ... ]
```

## Parameters

- **`<name>`**

  The identifier of the integration to alter. If the identifier contains spaces or special characters, the entire string must be enclosed in double quotes. Identifiers enclosed in double quotes are also case-sensitive.

- **`SET ...`**

  Specifies one or more properties/parameters to set for API integration (separated by blank spaces, commas, or new lines):

  - **`ENABLED = < TRUE | FALSE >`**

    Specifies whether to initiate operation of the integration or suspend it.

    - `TRUE` allows the integration to run.
    - `FALSE` suspends the integration for maintenance. Any integration between Snowflake and a third-party service fails to work.

  - **`ALLOWED_AUTHENTICATION_SECRETS = < <secret_name> [, <secret_name> ... ] | all | none >`**

    Specifies the secrets that UDF or procedure handler code can use when accessing the Git repository at the API_ALLOWED_PREFIXES value. You specify a secret from this list when specifying Git credentials with the GIT_CREDENTIALS parameter.

    This parameter's value must be one of the following:

    - One or more fully-qualified Snowflake secret names to allow any of the listed secrets.
    - (Default) `all` to allow any secret.
    - `none` to allow no secrets.

  - **`API_AWS_ROLE_ARN = '<iam_role>'`**

    The iam_role is the ARN (Amazon resource name) of a cloud platform role.

    This parameter applies only if the API_PROVIDER is set to `aws_api_gateway`.

  - **`API_BLOCKED_PREFIXES = ('<...>')`**

    Lists the endpoints and resources in the HTTPS proxy service that are not allowed to be called from Snowflake.

    The possible values for locations follow the same rules as for API_ALLOWED_PREFIXES above.

    API_BLOCKED_PREFIXES takes precedence over API_ALLOWED_PREFIXES. If a prefix matches both, then it is blocked.

    In other words, Snowflake allows all values that match API_ALLOWED_PREFIXES except values that also match API_BLOCKED_PREFIXES.

    If a value is outside API_ALLOWED_PREFIXES, you do not need to explicitly block it.

  - **`API_ALLOWED_PREFIXES = ('<...>')`**

    Explicitly limits external functions that use the integration to reference one or more HTTPS proxy service endpoints (e.g. Amazon AWS API Gateway) and resources within those proxies. Supports a comma-separated list of URLs, which are treated as prefixes (for details, see below).

    Each URL in `API_ALLOWED_PREFIXES = (...)` is treated as a prefix. For example, if you specify:

    `https://xyz.amazonaws.com/production/`

    that means all resources under

    `https://xyz.amazonaws.com/production/`

    are allowed. For example the following is allowed:

    `https://xyz.amazonaws.com/production/ml1`

    To maximize security, you should restrict allowed locations as narrowly as practical.

  - **`AZURE_AD_APPLICATION_ID = '<azure_application_id>'`**

    The "Application (client) id" of the Azure AD (Active Directory) app for your remote service.

    This parameter applies only if the API_PROVIDER is set to `azure_api_management`.

  - **`API_KEY = '<api_key>'`**

    The API key (also called a "subscription key").

  - **`COMMENT = '<string_literal>'`**

    String (literal) that specifies a comment for the integration.

  - **`TAG <tag_name> = '<tag_value>' [ , <tag_name> = '<tag_value>' ... ]`**

    Specifies the tag name and the tag string value.

    The tag value is always a string, and the maximum number of characters for the tag value is 256.

- **`UNSET ...`**

  Specifies one or more properties/parameters to unset for the API integration, which resets them back to their defaults:

  - `ENABLED`
  - `API_BLOCKED_PREFIXES`
  - `TAG <tag_name> [ , <tag_name> ... ]`
  - `COMMENT`

## Usage notes

Regarding metadata:

**Attention**

Customers should ensure that no personal data (other than for a User object), sensitive data, export-controlled data, or other regulated data is entered as metadata when using the Snowflake service.

## Examples

The following example initiates operation of a suspended integration:

```sql
ALTER API INTEGRATION myint SET ENABLED = TRUE;
```
