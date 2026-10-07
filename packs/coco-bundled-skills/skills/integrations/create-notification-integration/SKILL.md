---
name: create-notification-integration
description: >
  Create a new notification integration for cloud message queuing services (Azure Event Grid, Google Pub/Sub, Amazon SNS), email services, or webhooks
---

# CREATE NOTIFICATION INTEGRATION


Creates a new notification integration in the account or replaces an existing integration. A notification integration is a Snowflake object that provides an interface between Snowflake and third-party messaging services (cloud message queuing services, email services, or webhooks).

The syntax depends on the type of messaging service and whether the message is inbound or outbound. Seven subtypes are supported: inbound Azure Event Grid, inbound Google Pub/Sub, outbound Amazon SNS, outbound Azure Event Grid, outbound Google Pub/Sub, email, and webhooks.

## Syntax

**Inbound from Azure Event Grid:**

```sql
CREATE [ OR REPLACE ] NOTIFICATION INTEGRATION [ IF NOT EXISTS ]
  <name>
  ENABLED = { TRUE | FALSE }
  TYPE = QUEUE
  NOTIFICATION_PROVIDER = AZURE_STORAGE_QUEUE
  AZURE_STORAGE_QUEUE_PRIMARY_URI = '<queue_url>'
  AZURE_TENANT_ID = '<ad_directory_id>'
  [ USE_PRIVATELINK_ENDPOINT = { TRUE | FALSE } ]
  [ COMMENT = '<string_literal>' ]
```

**Inbound from Google Pub/Sub:**

```sql
CREATE [ OR REPLACE ] NOTIFICATION INTEGRATION [ IF NOT EXISTS ]
  <name>
  ENABLED = { TRUE | FALSE }
  TYPE = QUEUE
  NOTIFICATION_PROVIDER = GCP_PUBSUB
  GCP_PUBSUB_SUBSCRIPTION_NAME = '<subscription_id>'
  [ COMMENT = '<string_literal>' ]
```

**Outbound to Amazon SNS:**

```sql
CREATE [ OR REPLACE ] NOTIFICATION INTEGRATION [ IF NOT EXISTS ]
  <name>
  ENABLED = { TRUE | FALSE }
  TYPE = QUEUE
  DIRECTION = OUTBOUND
  NOTIFICATION_PROVIDER = AWS_SNS
  AWS_SNS_TOPIC_ARN = '<topic_arn>'
  AWS_SNS_ROLE_ARN = '<iam_role_arn>'
  [ COMMENT = '<string_literal>' ]
```

**Outbound to Azure Event Grid:**

```sql
CREATE [ OR REPLACE ] NOTIFICATION INTEGRATION [ IF NOT EXISTS ]
  <name>
  ENABLED = { TRUE | FALSE }
  TYPE = QUEUE
  DIRECTION = OUTBOUND
  NOTIFICATION_PROVIDER = AZURE_EVENT_GRID
  AZURE_EVENT_GRID_TOPIC_ENDPOINT = '<event_grid_topic_endpoint>'
  AZURE_TENANT_ID = '<ad_directory_id>'
  [ COMMENT = '<string_literal>' ]
```

**Outbound to Google Pub/Sub:**

```sql
CREATE [ OR REPLACE ] NOTIFICATION INTEGRATION [ IF NOT EXISTS ]
  <name>
  ENABLED = { TRUE | FALSE }
  TYPE = QUEUE
  DIRECTION = OUTBOUND
  NOTIFICATION_PROVIDER = GCP_PUBSUB
  GCP_PUBSUB_TOPIC_NAME = '<topic_id>'
  [ COMMENT = '<string_literal>' ]
```

**Email:**

```sql
CREATE [ OR REPLACE ] NOTIFICATION INTEGRATION [ IF NOT EXISTS ]
  <name>
  TYPE = EMAIL
  ENABLED = { TRUE | FALSE }
  [ ALLOWED_RECIPIENTS = ( '<email_address>' [ , ... '<email_address>' ] ) ]
  [ DEFAULT_RECIPIENTS = ( '<email_address>' [ , ... '<email_address>' ] ) ]
  [ DEFAULT_SUBJECT = '<subject_line>' ]
  [ COMMENT = '<string_literal>' ]
```

**Webhooks:**

```sql
CREATE [ OR REPLACE ] NOTIFICATION INTEGRATION [ IF NOT EXISTS ]
  <name>
  TYPE = WEBHOOK
  ENABLED = { TRUE | FALSE }
  WEBHOOK_URL = '<url>'
  [ WEBHOOK_SECRET = <secret_name> ]
  [ WEBHOOK_BODY_TEMPLATE = '<template_for_http_request_body>' ]
  [ WEBHOOK_HEADERS = ( '<header_1>'='<value_1>' [ , '<header_N>'='<value_N>', ... ] ) ]
  [ COMMENT = '<string_literal>' ]
```

## Required parameters

- **<name>**
  String that specifies the identifier (i.e. name) for the integration; must be unique in your account.
  In addition, the identifier must start with an alphabetic character and cannot contain spaces or special characters unless the entire identifier string is enclosed in double quotes (e.g. `"My object"`). Identifiers enclosed in double quotes are also case-sensitive.

- **ENABLED = { TRUE | FALSE }**
  Specifies whether this notification integration is available for usage.
  - `TRUE` activates the integration for immediate operation.
  - `FALSE` suspends the integration for maintenance. When disabled, integration with third-party services fails.

- **TYPE = { QUEUE | EMAIL | WEBHOOK }**
  Specifies the type of notification integration:
  - `QUEUE`: Creates an interface between Snowflake and a third-party cloud message queuing service (Azure Event Grid, Google Pub/Sub, or Amazon SNS).
  - `EMAIL`: Creates an interface between Snowflake and an email service.
  - `WEBHOOK`: Creates an interface between Snowflake and a webhook endpoint.

## Queue-type required parameters

- **NOTIFICATION_PROVIDER = { AZURE_STORAGE_QUEUE | GCP_PUBSUB | AWS_SNS | AZURE_EVENT_GRID }**
  Specifies the cloud messaging provider:
  - `AZURE_STORAGE_QUEUE`: Microsoft Azure Event Grid (inbound).
  - `GCP_PUBSUB`: Google Cloud Pub/Sub (inbound or outbound).
  - `AWS_SNS`: Amazon Simple Notification Service (outbound only).
  - `AZURE_EVENT_GRID`: Microsoft Azure Event Grid (outbound).

- **DIRECTION = OUTBOUND**
  Required for outbound integrations (AWS_SNS, AZURE_EVENT_GRID, outbound GCP_PUBSUB). Specifies that Snowflake initiates notifications sent to the cloud messaging service.

### Inbound Azure Event Grid parameters

- **AZURE_STORAGE_QUEUE_PRIMARY_URI = '<queue_url>'**
  Specifies the queue URL for the Azure Storage Queue in the format: `https://<storage_queue_account>.queue.core.windows.net/<storage_queue_name>`. A single notification integration supports a single Azure Storage Queue. Providing queue URLs that are in use by another notification integration results in an error during pipe creation.

- **AZURE_TENANT_ID = '<ad_directory_id>'**
  Specifies the Azure Active Directory tenant identifier. Used to generate the consent URL that grants Snowflake access to the Event Grid topic subscriptions.

### Inbound Google Pub/Sub parameters

- **GCP_PUBSUB_SUBSCRIPTION_NAME = '<subscription_id>'**
  Specifies the Pub/Sub subscription identifier that allows Snowflake to access event notifications. A single notification integration supports a single Google Cloud Pub/Sub subscription. Reusing the same subscription across multiple integrations causes data loss because messages are split between integrations.

### Outbound Amazon SNS parameters

- **AWS_SNS_TOPIC_ARN = '<topic_arn>'**
  Specifies the Amazon Resource Name (ARN) of the SNS topic that receives notifications from Snowflake.

- **AWS_SNS_ROLE_ARN = '<iam_role_arn>'**
  Specifies the ARN of the IAM role that has permissions to publish messages to the SNS topic. The value of AWS_SNS_ROLE_ARN is case-sensitive.

### Outbound Azure Event Grid parameters

- **AZURE_EVENT_GRID_TOPIC_ENDPOINT = '<event_grid_topic_endpoint>'**
  Specifies the Event Grid topic endpoint URL where Snowflake pushes notifications.

- **AZURE_TENANT_ID = '<ad_directory_id>'**
  Specifies the Azure Active Directory tenant identifier. Used for identity management and to generate the consent URL granting Snowflake access.

### Outbound Google Pub/Sub parameters

- **GCP_PUBSUB_TOPIC_NAME = '<topic_id>'**
  Specifies the Pub/Sub topic identifier where Snowflake directs outbound notifications.

## Optional parameters

### Common optional parameters

- **COMMENT = '<string_literal>'**
  String (literal) that specifies a comment for the integration.
  Default: No value

### Inbound Azure Event Grid optional parameters

- **USE_PRIVATELINK_ENDPOINT = { TRUE | FALSE }**
  Specifies whether to use outbound private connectivity to harden your security posture. See Azure private connectivity documentation for usage details.

### Email optional parameters

- **ALLOWED_RECIPIENTS = ( '<email_address>' [ , ... '<email_address>' ] )**
  Comma-separated list of email addresses authorized to receive notifications through this integration. Addresses must belong to current account users who have verified their email addresses. Maximum 50 email addresses allowed. Omitting this parameter allows sending to any verified email address in the account.

- **DEFAULT_RECIPIENTS = ( '<email_address>' [ , ... '<email_address>' ] )**
  Specifies default message recipients as a comma-separated list of email addresses. Must reference verified current account users. Can be overridden via the `EMAIL_INTEGRATION_CONFIG` helper function with the `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION` stored procedure.

- **DEFAULT_SUBJECT = '<subject_line>'**
  Sets the default subject line for email messages. Maximum 256 characters.
  Default: `'Snowflake Email Notification'`
  Can be overridden via the `EMAIL_INTEGRATION_CONFIG` helper function.

### Webhook optional parameters

- **WEBHOOK_SECRET = <secret_name>**
  References a secret object containing sensitive credential data. The `SNOWFLAKE_WEBHOOK_SECRET` placeholder in the URL, body template, or headers is replaced with this secret value when notifications are sent. If the secret's database and schema will not be active during notification sending, use a fully qualified name: `database.schema.secret_name`. Requires USAGE privilege on the secret and its containing database and schema.

- **WEBHOOK_BODY_TEMPLATE = '<template_for_http_request_body>'**
  Custom template for the HTTP request body (e.g., JSON format). Use the `SNOWFLAKE_WEBHOOK_MESSAGE` placeholder where the notification message content should appear. Use the `SNOWFLAKE_WEBHOOK_SECRET` placeholder where secret values should be inserted. When this parameter is set, you must also configure WEBHOOK_HEADERS with an appropriate `Content-Type` header.

- **WEBHOOK_HEADERS = ( '<header_1>'='<value_1>' [ , '<header_N>'='<value_N>', ... ] )**
  Specifies HTTP headers to include in webhook requests. Use the `SNOWFLAKE_WEBHOOK_SECRET` placeholder in header values for credentials (e.g., Authorization headers).

## Access control requirements

A role used to execute this operation must have the following privileges at a minimum:

| Privilege | Object | Notes |
|---|---|---|
| CREATE INTEGRATION | Account | Only the ACCOUNTADMIN role has this privilege by default. The privilege can be granted to additional roles as needed. |
| USAGE | Secret | Required when WEBHOOK_SECRET is specified. Also requires USAGE on the containing database and schema. |

## Usage notes

- The OR REPLACE and IF NOT EXISTS clauses are mutually exclusive. They cannot both be used in the same statement.

- CREATE OR REPLACE <object> statements are atomic. That is, when an object is replaced, the old object is deleted and the new object is created in a single transaction.

- A single inbound notification integration supports only one cloud message queue (one Azure Storage Queue or one Google Pub/Sub subscription). Providing queue URLs or subscriptions that are already in use by another notification integration results in errors.

- Multiple inbound notification integrations sharing the same queue or subscription are unsupported for automated loads or metadata refreshes, as messages are split between integrations.

- Multiple pipes may share the same outbound notification integration for push notifications.

- Outbound Amazon SNS integrations are limited to Snowflake accounts hosted on AWS.

- Outbound Azure Event Grid integrations are limited to Snowflake accounts hosted on Microsoft Azure.

- Outbound Google Pub/Sub integrations are limited to Snowflake accounts hosted on Google Cloud.

- Government cloud regions prohibit event notifications crossing into commercial regions.

- For webhook integrations, the WEBHOOK_URL must use HTTPS protocol. Supported URL patterns:
  - Slack: must start with `https://hooks.slack.com/services/`
  - Microsoft Teams: `https://<hostname>.<region>.logic.azure.com/workflows/<secret>` or the newer Power Automate format `https://default<hostname>.environment.api.powerplatform.com/powerautomate/automations/direct/workflows/<secret>/triggers/manual/paths/invoke`
  - PagerDuty: must be `https://events.pagerduty.com/v2/enqueue`
  - You must omit the port number (`:443`) from Microsoft Teams webhook URLs.
  - If you created a secret object, replace the secret portion of the URL with the `SNOWFLAKE_WEBHOOK_SECRET` placeholder.

Regarding metadata:

Attention

Customers should ensure that no personal data (other than for a User object), sensitive data, export-controlled data, or other regulated data is entered as metadata when using the Snowflake service. For more information, see Metadata fields in Snowflake.

## Examples

**Inbound Azure Event Grid:**

```sql
CREATE NOTIFICATION INTEGRATION my_azure_inbound_int
  ENABLED = TRUE
  TYPE = QUEUE
  NOTIFICATION_PROVIDER = AZURE_STORAGE_QUEUE
  AZURE_STORAGE_QUEUE_PRIMARY_URI = 'https://myaccount.queue.core.windows.net/myqueue'
  AZURE_TENANT_ID = 'a123b4c5-1234-123a-a12b-1a23b45678c9';
```

**Inbound Google Pub/Sub:**

```sql
CREATE NOTIFICATION INTEGRATION my_gcp_inbound_int
  ENABLED = TRUE
  TYPE = QUEUE
  NOTIFICATION_PROVIDER = GCP_PUBSUB
  GCP_PUBSUB_SUBSCRIPTION_NAME = 'projects/my-project/subscriptions/my-subscription';
```

**Outbound Amazon SNS:**

```sql
CREATE NOTIFICATION INTEGRATION my_sns_int
  ENABLED = TRUE
  TYPE = QUEUE
  DIRECTION = OUTBOUND
  NOTIFICATION_PROVIDER = AWS_SNS
  AWS_SNS_TOPIC_ARN = 'arn:aws:sns:us-east-1:001234567890:my-topic'
  AWS_SNS_ROLE_ARN = 'arn:aws:iam::001234567890:role/my-sns-role';
```

**Outbound Azure Event Grid:**

```sql
CREATE NOTIFICATION INTEGRATION my_azure_outbound_int
  ENABLED = TRUE
  TYPE = QUEUE
  DIRECTION = OUTBOUND
  NOTIFICATION_PROVIDER = AZURE_EVENT_GRID
  AZURE_EVENT_GRID_TOPIC_ENDPOINT = 'https://my-topic.westus2-1.eventgrid.azure.net/api/events'
  AZURE_TENANT_ID = 'a123b4c5-1234-123a-a12b-1a23b45678c9';
```

**Outbound Google Pub/Sub:**

```sql
CREATE NOTIFICATION INTEGRATION my_gcp_outbound_int
  ENABLED = TRUE
  TYPE = QUEUE
  DIRECTION = OUTBOUND
  NOTIFICATION_PROVIDER = GCP_PUBSUB
  GCP_PUBSUB_TOPIC_NAME = 'projects/my-project/topics/my-topic';
```

**Email (with all optional parameters):**

```sql
CREATE NOTIFICATION INTEGRATION my_email_int
  TYPE = EMAIL
  ENABLED = TRUE
  ALLOWED_RECIPIENTS = ('first.last@example.com', 'admin@example.com')
  DEFAULT_RECIPIENTS = ('first.last@example.com')
  DEFAULT_SUBJECT = 'Snowflake Alert Notification';
```

**Email (basic, allowing any verified recipients):**

```sql
CREATE NOTIFICATION INTEGRATION my_email_int
  TYPE = EMAIL
  ENABLED = TRUE;
```

**Webhook to Slack:**

```sql
CREATE NOTIFICATION INTEGRATION my_slack_int
  TYPE = WEBHOOK
  ENABLED = TRUE
  WEBHOOK_URL = 'https://hooks.example.com/services/TXXXXXXXXX/BXXXXXXXXX/XXXXXXXXXXXXXXXXXXXXXXXX';
```

**Webhook to PagerDuty (with secret and body template):**

```sql
CREATE NOTIFICATION INTEGRATION my_pagerduty_int
  TYPE = WEBHOOK
  ENABLED = TRUE
  WEBHOOK_URL = 'https://events.pagerduty.com/v2/enqueue'
  WEBHOOK_SECRET = my_pagerduty_secret
  WEBHOOK_BODY_TEMPLATE = '{"routing_key": "SNOWFLAKE_WEBHOOK_SECRET", "event_action": "trigger", "payload": {"summary": "SNOWFLAKE_WEBHOOK_MESSAGE", "source": "Snowflake", "severity": "critical"}}'
  WEBHOOK_HEADERS = ('Content-Type'='application/json');
```

**Webhook to Microsoft Teams (with secret in headers):**

```sql
CREATE NOTIFICATION INTEGRATION my_teams_int
  TYPE = WEBHOOK
  ENABLED = TRUE
  WEBHOOK_URL = 'https://defaultmyorg.environment.api.powerplatform.com/powerautomate/automations/direct/workflows/SNOWFLAKE_WEBHOOK_SECRET/triggers/manual/paths/invoke'
  WEBHOOK_SECRET = my_teams_secret
  WEBHOOK_BODY_TEMPLATE = '{"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": {"type": "AdaptiveCard", "body": [{"type": "TextBlock", "text": "SNOWFLAKE_WEBHOOK_MESSAGE"}], "$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "version": "1.0"}}]}'
  WEBHOOK_HEADERS = ('Content-Type'='application/json');
```

**Using OR REPLACE:**

```sql
CREATE OR REPLACE NOTIFICATION INTEGRATION my_azure_inbound_int
  ENABLED = TRUE
  TYPE = QUEUE
  NOTIFICATION_PROVIDER = AZURE_STORAGE_QUEUE
  AZURE_STORAGE_QUEUE_PRIMARY_URI = 'https://myaccount.queue.core.windows.net/myqueue'
  AZURE_TENANT_ID = 'a123b4c5-1234-123a-a12b-1a23b45678c9';
```

**Using IF NOT EXISTS:**

```sql
CREATE NOTIFICATION INTEGRATION IF NOT EXISTS my_gcp_inbound_int
  ENABLED = TRUE
  TYPE = QUEUE
  NOTIFICATION_PROVIDER = GCP_PUBSUB
  GCP_PUBSUB_SUBSCRIPTION_NAME = 'projects/my-project/subscriptions/my-subscription';
```

**Inbound Azure Event Grid with private connectivity:**

```sql
CREATE NOTIFICATION INTEGRATION my_azure_private_int
  ENABLED = TRUE
  TYPE = QUEUE
  NOTIFICATION_PROVIDER = AZURE_STORAGE_QUEUE
  AZURE_STORAGE_QUEUE_PRIMARY_URI = 'https://myaccount.queue.core.windows.net/myqueue'
  AZURE_TENANT_ID = 'a123b4c5-1234-123a-a12b-1a23b45678c9'
  USE_PRIVATELINK_ENDPOINT = TRUE;
```
