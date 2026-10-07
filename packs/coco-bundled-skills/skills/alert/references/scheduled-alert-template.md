# Scheduled Alert Template

Default serverless scheduled alert.

## Dependencies

Before using this template:

1. **→ Load `../../notification/notification-content/SKILL.md`** to generate formatted notification content
2. **⛔ MANDATORY → Load `notification-dispatch-paths.md`** to determine dispatch path:
   - **Path A (template-managed):** dispatch is handled by template logic (`SYSTEM$SEND_NOTIFICATION_FROM_ALERT`).
   - **Path B (manual/custom):** use `../../notification/notification-send/SKILL.md` for exact `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION` syntax.

## Template

```sql
CREATE OR REPLACE ALERT <alert_name>
  SCHEDULE = '10 MINUTE'
  <optional_config_clause>
  IF (EXISTS (
    <condition_query>
    AND timestamp >= GREATEST(
      TIMESTAMPADD('second', -60, COALESCE(
        CONVERT_TIMEZONE('UTC', SNOWFLAKE.ALERT.LAST_SUCCESSFUL_SCHEDULED_TIME())::TIMESTAMP_NTZ,
        TIMESTAMPADD('minute', -30, CONVERT_TIMEZONE('UTC', SNOWFLAKE.ALERT.SCHEDULED_TIME())::TIMESTAMP_NTZ)
      )),
      TIMESTAMPADD('minute', -30, CONVERT_TIMEZONE('UTC', SNOWFLAKE.ALERT.SCHEDULED_TIME())::TIMESTAMP_NTZ)
    )
    AND timestamp < TIMESTAMPADD('second', -60, CONVERT_TIMEZONE('UTC', SNOWFLAKE.ALERT.SCHEDULED_TIME())::TIMESTAMP_NTZ)
  ))
  THEN
    BEGIN
      <action_block>
    END
```

## Parameters

| Parameter | Description | Source |
|-----------|-------------|--------|
| `<alert_name>` | Alert name | e.g., `alert_dynamic_table_failures` |
| `<condition_query>` | SELECT returning rows when alert triggers | See telemetry-format skills |
| `<action_block>` | Notification logic with content formatting | See below |
| `<optional_config_clause>` | Optional runtime JSON config clause | See `runtime-config.md` for canonical syntax |

## Optional Runtime Config (`CONFIG`)

Use `CONFIG` when you want thresholds or routing values to be editable without rewriting alert SQL.

For CONFIG syntax examples (CREATE and ALTER), **load** `runtime-config.md`.

Use keys that match the alert's own condition/action logic. These are placeholders, not required fields.

If runtime config requirements are missing, ask the user to clarify:
- which values should be configurable
- what each value controls
- expected type/default for each key
- allowed ranges/options (if any)

For `SYSTEM$GET_ALERT_CONFIG` usage examples, **load** `runtime-config.md`.

## Action Block

Follow the dispatch path determined in the Dependencies step above.

1. Build notification content using patterns from **`../../notification/notification-content/SKILL.md`**
2. If Path B applies, send using **`../../notification/notification-send/SKILL.md`**

### Email Example (Path B - Manual/Custom)

```sql
BEGIN
  LET html_content VARCHAR := <generated_by_notification_content_skill>;
  
  CALL SYSTEM$SEND_SNOWFLAKE_NOTIFICATION(
    SNOWFLAKE.NOTIFICATION.TEXT_HTML(:html_content),
    '{"<email_integration>": {"subject": "<subject>", "toAddress": ["<recipient_email>"]}}'
  );
END
```

**CRITICAL:** Email integrations require `toAddress` with at least one recipient email. Omitting `toAddress` causes: *"No recipients specified and the notification integration does not specifi default recipients."*

### Webhook Example (Path B - Manual/Custom)

```sql
BEGIN
  LET webhook_content VARCHAR := <generated_by_notification_content_skill>;
  
  CALL SYSTEM$SEND_SNOWFLAKE_NOTIFICATION(
    SNOWFLAKE.NOTIFICATION.APPLICATION_JSON(:webhook_content),
    '{"<webhook_integration>": {}}'
  );
END
```

## Time Window

See `time-window.md` for detailed explanation of the time filter.

## Related Skills

- **`../../notification/notification-content/SKILL.md`** - Generate formatted content (HTML, Slack Block Kit, Teams Adaptive Cards, PagerDuty)
- **`notification-dispatch-paths.md`** - Path A vs Path B dispatch decision
- **`../../notification/notification-send/SKILL.md`** - Path B (manual/custom) `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION` parameters and integration setup
- **`time-window.md`** - Time window filter explanation
