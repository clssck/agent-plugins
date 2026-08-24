# Alert on New Data Template

For tables/views with infrequent inserts. Triggers only when new rows are inserted.

## Dependencies

Before using this template:

1. **→ Load `../../notification/notification-content/SKILL.md`** to generate formatted notification content
2. **⛔ MANDATORY → Load `notification-dispatch-paths.md`** to determine dispatch path:
   - **Path A (template-managed):** dispatch is handled by template logic (`SYSTEM$SEND_NOTIFICATION_FROM_ALERT`).
   - **Path B (manual/custom):** use `../../notification/notification-send/SKILL.md` for exact `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION` syntax.

## Constraints

**From [Snowflake Documentation](https://docs.snowflake.com/en/user-guide/alerts#label-alerts-type-streaming):**

| Constraint | Description |
|------------|-------------|
| **Single source** | FROM clause can specify only **one** regular table, view, or event table |
| **Change tracking** | Must be enabled on the table or view |
| **No CTEs** | Common table expressions not allowed |
| **No DML** | No INSERT, UPDATE, DELETE, MERGE |
| **No stored procedures** | Cannot call stored procedures |
| **No joins** | Cannot join multiple tables |
| **No EXECUTE ALERT** | Cannot manually execute with `EXECUTE ALERT` command |

## Template

```sql
CREATE OR REPLACE ALERT <alert_name>
  <optional_config_clause>
  IF (EXISTS (
    SELECT <columns>
    FROM <single_table_or_view>
    WHERE <filter_conditions>
  ))
  THEN
    BEGIN
      <action_block>
    END
```

## Parameters

| Parameter | Description | Source |
|-----------|-------------|--------|
| `<alert_name>` | Alert name | e.g., `alert_new_errors` |
| `<single_table_or_view>` | **One table/view/event table only** | `my_db.my_schema.my_table` |
| `<columns>` | Columns to select | `id, status, error_message` |
| `<filter_conditions>` | WHERE clause filters | `status = 'ERROR'` |
| `<action_block>` | Notification logic with content formatting | See below |
| `<optional_config_clause>` | Optional runtime JSON config clause | See `runtime-config.md` for canonical syntax |

## Optional Runtime Config (`CONFIG`)

Use `CONFIG` when the alert should read tunable values at runtime (for example enable flag, thresholds, routing targets).

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
  -- Build content (see notification-content skill for formatting)
  LET webhook_content VARCHAR := <generated_by_notification_content_skill>;
  
  -- Send notification (see notification skill for parameters)
  CALL SYSTEM$SEND_SNOWFLAKE_NOTIFICATION(
    SNOWFLAKE.NOTIFICATION.APPLICATION_JSON(:webhook_content),
    '{"<webhook_integration>": {}}'
  );
END
```

## Valid vs Invalid Queries

```sql
-- VALID: Single table
SELECT id, status FROM my_table WHERE status = 'ERROR'

-- VALID: Single view
SELECT id, status FROM my_view WHERE status = 'ERROR'

-- VALID: Event table
SELECT * FROM my_event_table WHERE value:level::STRING = 'ERROR'

-- INVALID: Join
SELECT a.id, b.name FROM table_a a JOIN table_b b ON a.id = b.id

-- INVALID: CTE
WITH cte AS (SELECT * FROM my_table) SELECT * FROM cte

-- INVALID: Subquery from another table
SELECT * FROM my_table WHERE id IN (SELECT id FROM other_table)

-- INVALID: Stored procedure call
CALL my_procedure()
```

## Prerequisites

1. **Enable change tracking** on the table or view:
   ```sql
   ALTER TABLE <table> SET CHANGE_TRACKING = TRUE;
   -- or
   ALTER VIEW <view> SET CHANGE_TRACKING = TRUE;
   ```

2. **Required privileges:**
   - `EXECUTE ALERT` on account
   - `EXECUTE MANAGED ALERT` on account (for serverless)
   - `SELECT` on the table or view
   - `CREATE ALERT` and `USAGE` on schema

## Key Differences from Scheduled Alerts

| Aspect | Alert on New Data | Scheduled Alert |
|--------|-------------------|-----------------|
| SCHEDULE | None | Required (e.g., '10 MINUTE') |
| Trigger | On new rows (change tracking) | On schedule |
| Data evaluated | Only new rows | All data |
| Manual execution | Not supported (`EXECUTE ALERT` fails) | Supported |
| Joins/CTEs | Not allowed | Allowed |

## When to Use

- Tables/views with sporadic inserts
- Real-time alerting on new data
- More cost-effective for infrequent events
- Monitoring event tables for errors

## When NOT to Use

- Need to join multiple tables → use Scheduled Alert
- Need CTEs or complex queries → use Scheduled Alert
- Need to manually test with `EXECUTE ALERT` → use Scheduled Alert

## Related Skills

- **`../../notification/notification-content/SKILL.md`** - Generate formatted content (HTML, Slack Block Kit, Teams Adaptive Cards, PagerDuty)
- **`notification-dispatch-paths.md`** - Path A vs Path B dispatch decision
- **`../../notification/notification-send/SKILL.md`** - Path B (manual/custom) `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION` parameters and integration setup
