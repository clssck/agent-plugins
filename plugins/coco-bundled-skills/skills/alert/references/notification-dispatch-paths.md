# Notification Dispatch Paths for Alerts

This reference defines the two supported notification dispatch paths for Snowflake alerts.
Use it to decide whether notification behavior is template-managed or manual/custom.

## Path A - Template-Managed Dispatch

Use this path when an alert is created from `SYSTEM$RENDER_ALERT_TEMPLATE(...)` and the action remains template-managed.

- Dispatch function: `SYSTEM$SEND_NOTIFICATION_FROM_ALERT`
- Integration selection: resolved from alert runtime config via `SYSTEM$GET_ALERT_CONFIG(...)`
- Condition-result context: passed via `SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID()`

Common runtime config keys:

- `NOTIFICATION.notification_value.active`
- `NOTIFICATION.EMAIL.value`
- `NOTIFICATION.WEBHOOK.value`
- `NOTIFICATION.EMAIL.recipients`

Operational guidance:

- Do not require a literal integration name in action SQL.
- Use alert config + `NOTIFICATION_HISTORY` as runtime evidence.

## Path B - Manual/Custom Dispatch

Use this path when notification calls are hand-authored in action SQL.

- Dispatch function: `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION`
- Integration wiring: encoded directly in the send-call JSON argument
- Email overrides: explicitly set using properties like `subject` and `toAddress`

Operational guidance:

- Validate wrapper type, argument order, and allowed JSON properties.
- Integration names are typically parseable directly from action SQL.
- `notification-send` and `notification-content` skills are authoritative for this path.

## Path Selection Rules

Select Path A when any of the following are true:

1. Alert is generated from `SYSTEM$RENDER_ALERT_TEMPLATE(...)` and action logic remains template-managed.
2. Action behavior is config-driven and does not require manual send-call construction.

Select Path B when any of the following are true:

1. Alert action explicitly calls `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION(...)`.
2. Team intentionally uses a custom action block for notification dispatch.

If uncertain, state both paths briefly and ask one clarifying question before applying notification-specific fixes.
