---
name: notification
description: "Router for Snowflake notification skills. Routes to integration creation/management, content formatting, or sending. Triggers: notification, notification integration, email notification, webhook, slack, teams, pagerduty, send notification, notification content."
---

# Snowflake Notifications

Router for notification-related tasks. Routes to the appropriate sub-skill based on user intent.

## Workflow

### Step 1: Detect Intent

| Intent | Triggers | Action |
|--------|----------|--------|
| Create or manage integration | "create notification integration", "email integration", "webhook integration", "alter integration", "drop integration", "show integrations" | **Load** [notification-integration/SKILL.md](notification-integration/SKILL.md) |
| Format notification content | "notification content", "format notification", "email content", "webhook content", "slack message", "teams message" | **Load** [notification-content/SKILL.md](notification-content/SKILL.md) |
| Send notification | "send notification", "send email", "send slack", "send teams", "send pagerduty", "SYSTEM$SEND_SNOWFLAKE_NOTIFICATION" | **Load** [notification-send/SKILL.md](notification-send/SKILL.md) |

### Step 2: Route to Specialized Skill

**Mandatory:** Load one of the sub-skills below. This router does not contain enough detail to handle any task directly.

**If request involves creating, altering, describing, or dropping notification integrations:**
- **-> Load**: [notification-integration/SKILL.md](notification-integration/SKILL.md)
- Handles email and webhook (Slack, Teams, PagerDuty) integrations, secret creation, grants

**If request involves formatting notification content (HTML email, Slack Block Kit, Teams Adaptive Cards, PagerDuty):**
- **-> Load**: [notification-content/SKILL.md](notification-content/SKILL.md)
- Takes query_id or message body, generates SQL content block for `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION`

**If request involves sending a notification:**
- **-> Load**: [notification-send/SKILL.md](notification-send/SKILL.md)
- Takes content and integration, wraps and executes `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION`

**If request involves alert notification muting/throttling (for example "send at most once per hour"):**
- **-> Load reference**: [references/alert-muting.md](references/alert-muting.md)
- Use action-level mute logic with a tracking table; keep detection logic in alert condition.

## Related Skills

- [notification-integration/SKILL.md](notification-integration/SKILL.md) - Create and manage notification integrations
- [notification-content/SKILL.md](notification-content/SKILL.md) - Format query results as notification content
- [notification-send/SKILL.md](notification-send/SKILL.md) - Send notifications via `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION`
- [references/alert-muting.md](references/alert-muting.md) - Action-level muting/throttle pattern for alerts

## Stopping Points

- After routing: Sub-skill handles its own stopping points
