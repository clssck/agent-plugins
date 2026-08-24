---
name: alter-notification-integration
description: >
  Modify properties of an existing notification integration (cloud messaging, email, or webhook)
---

# ALTER NOTIFICATION INTEGRATION


Modifies the properties for an existing notification integration. The properties that you can set depend on the type of the messaging service and whether the message is inbound or outbound.

## Syntax

**Inbound from Azure Event Grid:**

```sql
ALTER [ NOTIFICATION ] INTEGRATION [ IF EXISTS ] <name> SET
  [ ENABLED = { TRUE | FALSE } ]
  [ COMMENT = '<string_literal>' ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION <name> SET TAG <tag_name> = '<tag_value>' [ , <tag_name> = '<tag_value>' ... ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION <name> UNSET TAG <tag_name> [ , <tag_name> ... ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION [ IF EXISTS ] <name> UNSET COMMENT
```

**Inbound from Google Pub/Sub:**

```sql
ALTER [ NOTIFICATION ] INTEGRATION [ IF EXISTS ] <name> SET
  [ ENABLED = { TRUE | FALSE } ]
  [ COMMENT = '<string_literal>' ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION <name> SET TAG <tag_name> = '<tag_value>' [ , <tag_name> = '<tag_value>' ... ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION <name> UNSET TAG <tag_name> [ , <tag_name> ... ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION [ IF EXISTS ] <name> UNSET COMMENT
```

**Outbound to Amazon SNS:**

```sql
ALTER [ NOTIFICATION ] INTEGRATION [ IF EXISTS ] <name> SET
  [ ENABLED = { TRUE | FALSE } ]
  [ AWS_SNS_TOPIC_ARN = '<topic_arn>' ]
  [ AWS_SNS_ROLE_ARN = '<iam_role_arn>' ]
  [ COMMENT = '<string_literal>' ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION <name> SET TAG <tag_name> = '<tag_value>' [ , <tag_name> = '<tag_value>' ... ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION <name> UNSET TAG <tag_name> [ , <tag_name> ... ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION [ IF EXISTS ] <name> UNSET COMMENT
```

**Outbound to Azure Event Grid:**

```sql
ALTER [ NOTIFICATION ] INTEGRATION [ IF EXISTS ] <name> SET
  [ ENABLED = { TRUE | FALSE } ]
  [ AZURE_EVENT_GRID_TOPIC_ENDPOINT = '<event_grid_topic_endpoint>' ]
  [ AZURE_TENANT_ID = '<ad_directory_id>' ]
  [ COMMENT = '<string_literal>' ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION <name> SET TAG <tag_name> = '<tag_value>' [ , <tag_name> = '<tag_value>' ... ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION <name> UNSET TAG <tag_name> [ , <tag_name> ... ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION [ IF EXISTS ] <name> UNSET COMMENT
```

**Outbound to Google Pub/Sub:**

```sql
ALTER [ NOTIFICATION ] INTEGRATION [ IF EXISTS ] <name> SET
  [ ENABLED = { TRUE | FALSE } ]
  [ GCP_PUBSUB_TOPIC_NAME = '<topic_id>' ]
  [ COMMENT = '<string_literal>' ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION <name> SET TAG <tag_name> = '<tag_value>' [ , <tag_name> = '<tag_value>' ... ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION <name> UNSET TAG <tag_name> [ , <tag_name> ... ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION [ IF EXISTS ] <name> UNSET COMMENT
```

**Email:**

```sql
ALTER [ NOTIFICATION ] INTEGRATION [ IF EXISTS ] <name> SET
  [ ENABLED = { TRUE | FALSE } ]
  [ ALLOWED_RECIPIENTS = ( '<email_address>' [ , ... '<email_address>' ] ) ]
  [ DEFAULT_RECIPIENTS = ( '<email_address>' [ , ... '<email_address>' ] ) ]
  [ DEFAULT_SUBJECT = '<subject_line>' ]
  [ COMMENT = '<string_literal>' ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION <name> SET TAG <tag_name> = '<tag_value>' [ , <tag_name> = '<tag_value>' ... ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION <name> UNSET TAG <tag_name> [ , <tag_name> ... ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION [ IF EXISTS ] <name> UNSET {
                                                                ENABLED              |
                                                                ALLOWED_RECIPIENTS   |
                                                                DEFAULT_RECIPIENTS   |
                                                                DEFAULT_SUBJECT      |
                                                                COMMENT
                                                                }
                                                                [ , ... ]
```

**Webhooks:**

```sql
ALTER [ NOTIFICATION ] INTEGRATION [ IF EXISTS ] <name> SET
  [ ENABLED = { TRUE | FALSE } ]
  [ WEBHOOK_URL = '<url>' ]
  [ WEBHOOK_SECRET = <secret_name> ]
  [ WEBHOOK_BODY_TEMPLATE = '<template_for_http_request_body>' ]
  [ WEBHOOK_HEADERS = ( '<header_1>'='<value_1>' [ , '<header_N>'='<value_N>', ... ] ) ]
  [ COMMENT = '<string_literal>' ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION <name> SET TAG <tag_name> = '<tag_value>' [ , <tag_name> = '<tag_value>' ... ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION <name> UNSET TAG <tag_name> [ , <tag_name> ... ]
```

```sql
ALTER [ NOTIFICATION ] INTEGRATION [ IF EXISTS ] <name> UNSET {
                                                                ENABLED               |
                                                                WEBHOOK_SECRET        |
                                                                WEBHOOK_BODY_TEMPLATE |
                                                                WEBHOOK_HEADERS       |
                                                                COMMENT
                                                                }
                                                                [ , ... ]
```

## Parameters

- **`<name>`**

    Identifier for the integration to alter. If the identifier contains spaces or special characters, the entire string must be enclosed in double quotes. Identifiers enclosed in double quotes are also case-sensitive.

- **SET ...**

    Specifies one or more properties/parameters to set for the integration (separated by blank spaces, commas, or new lines):

  - **ENABLED = { TRUE | FALSE }**

    Specifies whether this notification integration is available for usage.

    - `TRUE` activates the integration for immediate operation.

    - `FALSE` suspends the integration for maintenance. When disabled, integration with third-party services fails.

  - **TAG <tag_name> = '<tag_value>' [ , <tag_name> = '<tag_value>' , ... ]**

    Specifies the tag name and the tag string value.

    The tag value is always a string, and the maximum number of characters for the tag value is 256.

    For information about specifying tags in a statement, see Tag quotas.

  - **COMMENT = '<string_literal>'**

    String (literal) that specifies a comment for the integration.

### Outbound Amazon SNS settable parameters

  - **AWS_SNS_TOPIC_ARN = '<topic_arn>'**

    Specifies the Amazon Resource Name (ARN) of the SNS topic that receives notifications from Snowflake.

  - **AWS_SNS_ROLE_ARN = '<iam_role_arn>'**

    Specifies the ARN of the IAM role that has permissions to publish messages to the SNS topic. The value of AWS_SNS_ROLE_ARN is case-sensitive. Use the exact value from your AWS account.

### Outbound Azure Event Grid settable parameters

  - **AZURE_EVENT_GRID_TOPIC_ENDPOINT = '<event_grid_topic_endpoint>'**

    Specifies the Event Grid topic endpoint URL where Snowflake pushes notifications.

  - **AZURE_TENANT_ID = '<ad_directory_id>'**

    Specifies the Azure Active Directory tenant identifier. Used for identity management and to generate the consent URL granting Snowflake access.

### Outbound Google Pub/Sub settable parameters

  - **GCP_PUBSUB_TOPIC_NAME = '<topic_id>'**

    Specifies the Pub/Sub topic identifier where Snowflake directs outbound notifications.

### Email settable parameters

  - **ALLOWED_RECIPIENTS = ( '<email_address>' [ , ... '<email_address>' ] )**

    Comma-separated list of email addresses authorized to receive notifications through this integration. Addresses must belong to current account users who have verified their email addresses. Maximum 50 email addresses allowed. Omitting this parameter allows sending to any verified email address in the account.

  - **DEFAULT_RECIPIENTS = ( '<email_address>' [ , ... '<email_address>' ] )**

    Specifies default message recipients as a comma-separated list of email addresses. Must reference verified current account users. Can be overridden via the `EMAIL_INTEGRATION_CONFIG` helper function with the `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION` stored procedure.

  - **DEFAULT_SUBJECT = '<subject_line>'**

    Sets the default subject line for email messages. Maximum 256 characters.
    Default: `'Snowflake Email Notification'`
    Can be overridden via the `EMAIL_INTEGRATION_CONFIG` helper function.

### Webhook settable parameters

  - **WEBHOOK_URL = '<url>'**

    Specifies the webhook endpoint URL. Must use HTTPS protocol. Supported URL patterns:
    - Slack: must start with `https://hooks.slack.com/services/`
    - Microsoft Teams: `https://<hostname>.<region>.logic.azure.com/workflows/<secret>` or the newer Power Automate format `https://default<hostname>.environment.api.powerplatform.com/powerautomate/automations/direct/workflows/<secret>/triggers/manual/paths/invoke`
    - PagerDuty: must be `https://events.pagerduty.com/v2/enqueue`
    - You must omit the port number (`:443`) from Microsoft Teams webhook URLs.
    - If you created a secret object, replace the secret portion of the URL with the `SNOWFLAKE_WEBHOOK_SECRET` placeholder.

  - **WEBHOOK_SECRET = <secret_name>**

    References a secret object containing sensitive credential data. The `SNOWFLAKE_WEBHOOK_SECRET` placeholder in the URL, body template, or headers is replaced with this secret value when notifications are sent. If the secret's database and schema will not be active during notification sending, use a fully qualified name: `database.schema.secret_name`. Requires USAGE privilege on the secret and its containing database and schema.

  - **WEBHOOK_BODY_TEMPLATE = '<template_for_http_request_body>'**

    Custom template for the HTTP request body (e.g., JSON format). Use the `SNOWFLAKE_WEBHOOK_MESSAGE` placeholder where the notification message content should appear. Use the `SNOWFLAKE_WEBHOOK_SECRET` placeholder where secret values should be inserted. When this parameter is set, you must also configure WEBHOOK_HEADERS with an appropriate `Content-Type` header.

  - **WEBHOOK_HEADERS = ( '<header_1>'='<value_1>' [ , '<header_N>'='<value_N>', ... ] )**

    Specifies HTTP headers to include in webhook requests. Use the `SNOWFLAKE_WEBHOOK_SECRET` placeholder in header values for credentials (e.g., Authorization headers).

- **UNSET ...**

    Specifies one or more properties/parameters to unset for the integration, which resets them back to their defaults.

    **For inbound queue types (Azure Event Grid, Google Pub/Sub) and outbound queue types (Amazon SNS, Azure Event Grid, Google Pub/Sub):**

    - `COMMENT`

    - `TAG` <tag_name> [ , <tag_name> ... ]

    **For email:**

    - `ENABLED`

    - `ALLOWED_RECIPIENTS`

    - `DEFAULT_RECIPIENTS`

    - `DEFAULT_SUBJECT`

    - `COMMENT`

    - `TAG` <tag_name> [ , <tag_name> ... ]

    **For webhooks:**

    - `ENABLED`

    - `WEBHOOK_SECRET`

    - `WEBHOOK_BODY_TEMPLATE`

    - `WEBHOOK_HEADERS`

    - `COMMENT`

    - `TAG` <tag_name> [ , <tag_name> ... ]

## Access control requirements

A role used to execute this operation must have the following privileges at a minimum:

| Privilege | Object | Notes |
|---|---|---|
| OWNERSHIP | Integration | The OWNERSHIP privilege on the integration is automatically granted to the role that created it and can be transferred via GRANT OWNERSHIP. |
| USAGE | Secret | Required when WEBHOOK_SECRET is specified. Also requires USAGE on the containing database and schema. |

## Usage notes

- Disabling or dropping an integration might not take effect immediately because the integration might be cached. To expedite the removal process, remove the integration privilege from the cloud provider.

- For inbound queue-type integrations (Azure Event Grid and Google Pub/Sub), the queue URL and subscription name cannot be changed via ALTER. To change these, you must drop and recreate the integration.

- For outbound queue-type integrations, the provider-specific endpoint parameters (AWS_SNS_TOPIC_ARN, AWS_SNS_ROLE_ARN, AZURE_EVENT_GRID_TOPIC_ENDPOINT, AZURE_TENANT_ID, GCP_PUBSUB_TOPIC_NAME) can be modified via SET.

Regarding metadata:

Attention

Customers should ensure that no personal data (other than for a User object), sensitive data, export-controlled data, or other regulated data is entered as metadata when using the Snowflake service. For more information, see Metadata fields in Snowflake.

## Examples

**Enable a suspended notification integration:**

```sql
ALTER NOTIFICATION INTEGRATION my_notification_int SET ENABLED = TRUE;
```

**Disable a notification integration:**

```sql
ALTER NOTIFICATION INTEGRATION my_notification_int SET ENABLED = FALSE;
```

**Update the SNS topic and role ARN for an outbound Amazon SNS integration:**

```sql
ALTER NOTIFICATION INTEGRATION my_sns_int SET
  AWS_SNS_TOPIC_ARN = 'arn:aws:sns:us-west-2:001234567890:new-topic'
  AWS_SNS_ROLE_ARN = 'arn:aws:iam::001234567890:role/new-sns-role';
```

**Update the Event Grid endpoint for an outbound Azure Event Grid integration:**

```sql
ALTER NOTIFICATION INTEGRATION my_azure_outbound_int SET
  AZURE_EVENT_GRID_TOPIC_ENDPOINT = 'https://new-topic.westus2-1.eventgrid.azure.net/api/events'
  AZURE_TENANT_ID = 'b456c7d8-5678-456b-b34c-2b34c56789d0';
```

**Update the Pub/Sub topic for an outbound Google Pub/Sub integration:**

```sql
ALTER NOTIFICATION INTEGRATION my_gcp_outbound_int SET
  GCP_PUBSUB_TOPIC_NAME = 'projects/my-project/topics/new-topic';
```

**Update email integration recipients and subject:**

```sql
ALTER NOTIFICATION INTEGRATION my_email_int SET
  ALLOWED_RECIPIENTS = ('user1@example.com', 'user2@example.com', 'user3@example.com')
  DEFAULT_RECIPIENTS = ('user1@example.com')
  DEFAULT_SUBJECT = 'Production Alert';
```

**Reset email integration optional parameters to defaults:**

```sql
ALTER NOTIFICATION INTEGRATION my_email_int UNSET
  ALLOWED_RECIPIENTS,
  DEFAULT_RECIPIENTS,
  DEFAULT_SUBJECT;
```

**Update webhook URL and headers:**

```sql
ALTER NOTIFICATION INTEGRATION my_webhook_int SET
  WEBHOOK_URL = 'https://hooks.example.com/services/NEW_TOKEN/NEW_TOKEN/NEW_SECRET'
  WEBHOOK_HEADERS = ('Content-Type'='application/json');
```

**Update webhook body template and secret:**

```sql
ALTER NOTIFICATION INTEGRATION my_pagerduty_int SET
  WEBHOOK_SECRET = my_new_pagerduty_secret
  WEBHOOK_BODY_TEMPLATE = '{"routing_key": "SNOWFLAKE_WEBHOOK_SECRET", "event_action": "trigger", "payload": {"summary": "SNOWFLAKE_WEBHOOK_MESSAGE", "source": "Snowflake", "severity": "warning"}}'
  WEBHOOK_HEADERS = ('Content-Type'='application/json');
```

**Unset webhook optional parameters:**

```sql
ALTER NOTIFICATION INTEGRATION my_webhook_int UNSET
  WEBHOOK_SECRET,
  WEBHOOK_BODY_TEMPLATE,
  WEBHOOK_HEADERS;
```

**Set a tag on a notification integration:**

```sql
ALTER NOTIFICATION INTEGRATION my_notification_int SET TAG cost_center = 'engineering';
```

**Set multiple tags:**

```sql
ALTER NOTIFICATION INTEGRATION my_notification_int SET TAG
  cost_center = 'engineering',
  environment = 'production';
```

**Unset a tag:**

```sql
ALTER NOTIFICATION INTEGRATION my_notification_int UNSET TAG cost_center;
```

**Add a comment:**

```sql
ALTER NOTIFICATION INTEGRATION my_notification_int SET COMMENT = 'Production SNS integration for pipeline alerts';
```

**Remove a comment:**

```sql
ALTER NOTIFICATION INTEGRATION my_notification_int UNSET COMMENT;
```

**Using IF EXISTS:**

```sql
ALTER NOTIFICATION INTEGRATION IF EXISTS my_notification_int SET ENABLED = FALSE;
```
