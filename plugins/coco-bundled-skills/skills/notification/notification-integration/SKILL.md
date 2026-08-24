---
name: notification-integration
description: "Create and manage Snowflake notification integrations for email and webhooks (Slack, Teams, PagerDuty). Handles secret creation, grants, and integration lifecycle. Triggers: create notification integration, email integration, webhook integration, slack integration, teams integration, pagerduty integration, manage integration, alter integration, drop integration."
---

# Notification Integration

Create and manage Snowflake notification integrations for email and webhooks (Slack, Microsoft Teams, PagerDuty). Handles secret creation, grants, and integration lifecycle.

## Supported Integration Types

| Type | Use Case |
|------|----------|
| EMAIL | Send email notifications to allowed addresses |
| WEBHOOK | Send to Slack, Microsoft Teams, PagerDuty |

## Workflow

### Step 1: Pre-flight Check

**Before creating or altering any integration, always check existing integrations first:**

```sql
-- List all notification integrations
SHOW NOTIFICATION INTEGRATIONS;

-- If integration exists, describe it
DESCRIBE NOTIFICATION INTEGRATION <integration_name>;
```

### Step 2: Detect Intent

| Intent | Action |
|--------|--------|
| Create email integration | → Section: Create Email Integration |
| Create webhook integration | → Section: Create Webhook Integration |
| View/describe integration | → Section: Manage Integrations |
| Alter/drop integration | → Section: Manage Integrations |

## Create Email Integration

```sql
CREATE OR REPLACE NOTIFICATION INTEGRATION <integration_name>
  TYPE = EMAIL
  ENABLED = TRUE;
```

**Important**: Do not add allowed recipients in the notification integration by default. Omitting `ALLOWED_RECIPIENTS` means the integration can send to any verified email address in the account.

**Grant access (default: PUBLIC):**

```sql
GRANT USAGE ON INTEGRATION <integration_name> TO ROLE PUBLIC;
```

**Optional:** Set default recipients and subject if required:

```sql
ALTER NOTIFICATION INTEGRATION <integration_name> SET
  DEFAULT_RECIPIENTS = ('<default_email>')
  DEFAULT_SUBJECT = 'Snowflake Notification';
```

## Create Webhook Integration

**Only input required:** The secret token from the webhook URL. 

When creating the secret, do not echo the secret on the terminal or write it in any log file. 
While showing the SQL for creating secrets, mask the secret value

| Service | Secret Format | Example |
|---------|---------------|---------|
| Slack | `T.../B.../xxx` from `https://hooks.slack.com/services/<secret>` | `T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX` |
| Teams | `xxx` from `https://*.logic.azure.com:443/workflows/<secret>` | `xxxxxxxx` |
| PagerDuty | Integration key (for `routing_key` field) | `xxxxxxxx` |

### Slack

```sql
-- Step 1: Create secret
CREATE OR REPLACE SECRET <database>.<schema>.<secret_name>
  TYPE = GENERIC_STRING
  SECRET_STRING = '<secret>';

-- Step 2: Grant access to secret (default: PUBLIC)
GRANT READ ON SECRET <database>.<schema>.<secret_name> TO ROLE PUBLIC;
GRANT USAGE ON SCHEMA <database>.<schema> TO ROLE PUBLIC;

-- Step 3: Create integration
CREATE OR REPLACE NOTIFICATION INTEGRATION <integration_name>
  TYPE = WEBHOOK
  ENABLED = TRUE
  WEBHOOK_URL = 'https://hooks.slack.com/services/SNOWFLAKE_WEBHOOK_SECRET'
  WEBHOOK_SECRET = <database>.<schema>.<secret_name>
  WEBHOOK_BODY_TEMPLATE = 'SNOWFLAKE_WEBHOOK_MESSAGE'
  WEBHOOK_HEADERS = ('Content-Type' = 'application/json');

-- Step 4: Grant access to integration (default: PUBLIC)
GRANT USAGE ON INTEGRATION <integration_name> TO ROLE PUBLIC;
```

### Microsoft Teams

```sql
-- Step 1: Create secret
CREATE OR REPLACE SECRET <database>.<schema>.<secret_name>
  TYPE = GENERIC_STRING
  SECRET_STRING = '<secret>';

-- Step 2: Grant access to secret (default: PUBLIC)
GRANT READ ON SECRET <database>.<schema>.<secret_name> TO ROLE PUBLIC;
GRANT USAGE ON SCHEMA <database>.<schema> TO ROLE PUBLIC;

-- Step 3: Create integration (omit :443 port from URL)
CREATE OR REPLACE NOTIFICATION INTEGRATION <integration_name>
  TYPE = WEBHOOK
  ENABLED = TRUE
  WEBHOOK_URL = 'https://<hostname>.<region>.logic.azure.com/workflows/SNOWFLAKE_WEBHOOK_SECRET'
  WEBHOOK_SECRET = <database>.<schema>.<secret_name>
  WEBHOOK_BODY_TEMPLATE = 'SNOWFLAKE_WEBHOOK_MESSAGE'
  WEBHOOK_HEADERS = ('Content-Type' = 'application/json');

-- Step 4: Grant access to integration (default: PUBLIC)
GRANT USAGE ON INTEGRATION <integration_name> TO ROLE PUBLIC;
```

### PagerDuty

```sql
-- Step 1: Create secret (integration key)
CREATE OR REPLACE SECRET <database>.<schema>.<secret_name>
  TYPE = GENERIC_STRING
  SECRET_STRING = '<integration_key>';

-- Step 2: Grant access to secret (default: PUBLIC)
GRANT READ ON SECRET <database>.<schema>.<secret_name> TO ROLE PUBLIC;
GRANT USAGE ON SCHEMA <database>.<schema> TO ROLE PUBLIC;

-- Step 3: Create integration
CREATE OR REPLACE NOTIFICATION INTEGRATION <integration_name>
  TYPE = WEBHOOK
  ENABLED = TRUE
  WEBHOOK_URL = 'https://events.pagerduty.com/v2/enqueue'
  WEBHOOK_SECRET = <database>.<schema>.<secret_name>
  WEBHOOK_BODY_TEMPLATE = 'SNOWFLAKE_WEBHOOK_MESSAGE'
  WEBHOOK_HEADERS = ('Content-Type' = 'application/json');

-- Step 4: Grant access to integration (default: PUBLIC)
GRANT USAGE ON INTEGRATION <integration_name> TO ROLE PUBLIC;
```

### Step 3: Summarize & Confirm

**MANDATORY CHECKPOINT**: Before creating or altering, present a summary and get user confirmation:

```
Summary of changes:
- Action: CREATE / ALTER
- Integration name: <name>
- Type: EMAIL / WEBHOOK (Slack/Teams/PagerDuty)
- Secret: <database.schema.secret_name> (if webhook)
- Grants: PUBLIC (default)

Proceed? (Yes/No)
```

**Note:** Grants default to the PUBLIC role for ease of use. If more granular access control is needed, replace PUBLIC with a specific role in the summary above.

**NEVER execute CREATE or ALTER without explicit user approval.**

## Manage Integrations

**List all notification integrations:**

```sql
SHOW NOTIFICATION INTEGRATIONS;
```

**Describe integration:**

```sql
DESCRIBE NOTIFICATION INTEGRATION <integration_name>;
```

**Alter integration:**

```sql
ALTER NOTIFICATION INTEGRATION <integration_name> SET ENABLED = FALSE;
ALTER NOTIFICATION INTEGRATION <integration_name> SET ENABLED = TRUE;
```

**Drop integration:**

```sql
DROP NOTIFICATION INTEGRATION <integration_name>;
```

## Stopping Points

- ✋ After creating secret: Confirm secret created before creating integration
- ✋ After creating integration: Verify with DESCRIBE before granting access

## Output

- Notification integration created and configured
- Secrets securely stored for webhook tokens
