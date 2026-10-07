# Budget Notifications Reference

Budgets send notifications when spending is projected to exceed the spending limit.

---

## Notification Destinations

| Type | Description | Max per Budget |
|------|-------------|----------------|
| Email | Direct email to verified addresses | No limit |
| Queue | AWS SNS, Azure Event Grid, Google PubSub | 10 |
| Webhook | Slack, Teams, PagerDuty, custom endpoints | 10 |

---

## Email Notifications

### Set Email Recipients

```sql
-- Emails must be verified in Snowsight first
CALL my_budget!SET_EMAIL_NOTIFICATIONS('admin@company.com, finops@company.com');
```

**Verify email**: Snowsight → User menu → My Profile → Email → Verify

### Get Email Configuration

```sql
-- Get email recipients
CALL my_budget!GET_NOTIFICATION_EMAIL();

-- Get the name of the email notification integration (if configured)
CALL my_budget!GET_NOTIFICATION_INTEGRATION_NAME();
```

### With Notification Integration (Optional)

You can optionally use a notification integration to control allowed recipients via the `ALLOWED_RECIPIENTS` parameter:

```sql
USE ROLE ACCOUNTADMIN;

CREATE NOTIFICATION INTEGRATION budgets_notification_integration
    TYPE = EMAIL
    ENABLED = TRUE
    ALLOWED_RECIPIENTS = ('admin@company.com', 'finops@company.com');

-- Grant to Snowflake application
GRANT USAGE ON INTEGRATION budgets_notification_integration TO APPLICATION SNOWFLAKE;

-- Set recipients using integration
CALL my_budget!SET_EMAIL_NOTIFICATIONS(
    'budgets_notification_integration',
    'admin@company.com, finops@company.com'
);
```

---

## Queue Notifications (SNS, Event Grid, PubSub)

### AWS SNS Example

```sql
-- Create SNS integration
CREATE NOTIFICATION INTEGRATION budget_sns_integration
    TYPE = QUEUE
    NOTIFICATION_PROVIDER = AWS_SNS
    ENABLED = TRUE
    AWS_SNS_TOPIC_ARN = 'arn:aws:sns:us-west-2:123456789:budget-alerts'
    AWS_SNS_ROLE_ARN = 'arn:aws:iam::123456789:role/snowflake-sns-role';

GRANT USAGE ON INTEGRATION budget_sns_integration TO APPLICATION SNOWFLAKE;

-- Add to budget
CALL my_budget!ADD_NOTIFICATION_INTEGRATION('budget_sns_integration');
```

### Azure Event Grid Example

```sql
CREATE NOTIFICATION INTEGRATION budget_eventgrid_integration
    TYPE = QUEUE
    NOTIFICATION_PROVIDER = AZURE_EVENT_GRID
    ENABLED = TRUE
    AZURE_EVENT_GRID_TOPIC_ENDPOINT = 'https://myaccount.westus2-1.eventgrid.azure.net/api/events'
    AZURE_TENANT_ID = 'your-tenant-id';

GRANT USAGE ON INTEGRATION budget_eventgrid_integration TO APPLICATION SNOWFLAKE;
CALL my_budget!ADD_NOTIFICATION_INTEGRATION('budget_eventgrid_integration');
```

### Google PubSub Example

```sql
CREATE NOTIFICATION INTEGRATION budget_pubsub_integration
    TYPE = QUEUE
    NOTIFICATION_PROVIDER = GCP_PUBSUB
    ENABLED = TRUE
    GCP_PUBSUB_TOPIC_NAME = 'projects/myproject/topics/budget-alerts';

GRANT USAGE ON INTEGRATION budget_pubsub_integration TO APPLICATION SNOWFLAKE;
CALL my_budget!ADD_NOTIFICATION_INTEGRATION('budget_pubsub_integration');
```

---

## Webhook Notifications (Slack, Teams, PagerDuty)

### Slack Webhook

```sql
CREATE NOTIFICATION INTEGRATION budget_slack_integration
    TYPE = WEBHOOK
    ENABLED = TRUE
    WEBHOOK_URL = 'https://hooks.slack.com/services/T00/B00/XXXX'
    WEBHOOK_SECRET = snowflake.notification_integration.budget_slack_secret
    WEBHOOK_BODY_TEMPLATE = '{
        "text": "Budget Alert: {{budget_name}} - Spending: {{current_spending}} / {{spending_limit}} credits"
    }';

GRANT USAGE ON INTEGRATION budget_slack_integration TO APPLICATION SNOWFLAKE;
CALL my_budget!ADD_NOTIFICATION_INTEGRATION('budget_slack_integration');
```

### Microsoft Teams Webhook

```sql
CREATE NOTIFICATION INTEGRATION budget_teams_integration
    TYPE = WEBHOOK
    ENABLED = TRUE
    WEBHOOK_URL = 'https://outlook.office.com/webhook/xxx'
    WEBHOOK_BODY_TEMPLATE = '{
        "@type": "MessageCard",
        "text": "Budget Alert: {{budget_name}}"
    }';

GRANT USAGE ON INTEGRATION budget_teams_integration TO APPLICATION SNOWFLAKE;
CALL my_budget!ADD_NOTIFICATION_INTEGRATION('budget_teams_integration');
```

### PagerDuty Webhook

```sql
CREATE NOTIFICATION INTEGRATION budget_pagerduty_integration
    TYPE = WEBHOOK
    ENABLED = TRUE
    WEBHOOK_URL = 'https://events.pagerduty.com/v2/enqueue'
    WEBHOOK_HEADERS = ('Authorization' = 'Token token=xxx')
    WEBHOOK_BODY_TEMPLATE = '{
        "routing_key": "xxx",
        "event_action": "trigger",
        "payload": {
            "summary": "Budget {{budget_name}} exceeded",
            "severity": "warning"
        }
    }';

GRANT USAGE ON INTEGRATION budget_pagerduty_integration TO APPLICATION SNOWFLAKE;
CALL my_budget!ADD_NOTIFICATION_INTEGRATION('budget_pagerduty_integration');
```

---

## Manage Notification Integrations

```sql
-- Add integration (up to 10 queue/webhook per budget)
CALL my_budget!ADD_NOTIFICATION_INTEGRATION('my_integration');

-- Remove integration
CALL my_budget!REMOVE_NOTIFICATION_INTEGRATION('my_integration');

-- List all integrations on budget
CALL my_budget!GET_NOTIFICATION_INTEGRATIONS();
```

---

## Notification Threshold

By default, notifications fire when spending is projected to exceed **110%** of the limit.

```sql
-- Change threshold to 90% (alert earlier)
CALL my_budget!SET_NOTIFICATION_THRESHOLD(90);

-- Reset to default (110%)
CALL my_budget!SET_NOTIFICATION_THRESHOLD(110);
```

---

## Mute Notifications

Temporarily stop notifications without removing configuration:

```sql
-- Mute
CALL my_budget!SET_NOTIFICATION_MUTE_FLAG(TRUE);

-- Unmute
CALL my_budget!SET_NOTIFICATION_MUTE_FLAG(FALSE);

-- Check mute status
CALL my_budget!GET_NOTIFICATION_MUTE_FLAG();
-- Returns TRUE if muted, FALSE if notifications are enabled
```

---

## Notification Payload Format

Notifications include JSON payload with:

```json
{
    "budget_name": "my_project_budget",
    "budget_database": "BUDGETS_DB",
    "budget_schema": "BUDGETS_SCHEMA",
    "limit": 500,
    "spending": 450.25,
    "trend": 550.00,
    "time_percent": 0.75,
    "notification_time": "2024-01-15T10:30:00Z"
}
```

| Field | Description |
|-------|-------------|
| `limit` | Spending limit in credits |
| `spending` | Current-month spending |
| `trend` | Projected end-of-month spending |
| `time_percent` | Fraction of month elapsed (0.0 - 1.0) |

---

## View Notification History

```sql
SELECT *
FROM TABLE(INFORMATION_SCHEMA.NOTIFICATION_HISTORY(
    INTEGRATION_NAME => 'budget_sns_integration',
    START_TIME => DATEADD('day', -7, CURRENT_TIMESTAMP())
))
ORDER BY CREATED DESC;
```

---

> **Common Errors**: See `references/budget/troubleshooting.md` for notification-related error messages and solutions.
