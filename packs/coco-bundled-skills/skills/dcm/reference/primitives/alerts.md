# DCM Primitive Reference: Alerts

## Syntax

```sql
DEFINE ALERT database_name.schema_name.alert_name
    WAREHOUSE = warehouse_name
    SCHEDULE = { 'num MINUTES' | 'USING CRON cron_expr timezone' }
    IF (EXISTS (
        condition_query
    ))
    THEN
        action_statement;
```

## Minimal Example

```sql
DEFINE ALERT my_db.my_schema.alert_stale_records
    WAREHOUSE = my_warehouse
    SCHEDULE = '5 MINUTES'
    IF (EXISTS (
        SELECT 1 FROM my_db.my_schema.orders
        WHERE status = 'PENDING'
          AND created_at < DATEADD('hour', -1, CURRENT_TIMESTAMP())
    ))
    THEN
        CALL SYSTEM$SEND_EMAIL(
            'my_notification_integration',
            'oncall@example.com',
            'Stale records detected',
            'Orders stuck in PENDING for over 1 hour.'
        );
```

## Schedule Options

| Format | Example | Description |
|--------|---------|-------------|
| Interval (minutes) | `'15 MINUTES'` | Every 15 minutes |
| Cron expression | `'USING CRON 0 * * * * UTC'` | Every hour on the hour (UTC) |

Cron format: `minute hour day-of-month month day-of-week timezone`

```sql
-- Every day at 8am UTC
SCHEDULE = 'USING CRON 0 8 * * * UTC'

-- Every 30 minutes
SCHEDULE = '30 MINUTES'

-- Weekdays at 9am US/Eastern
SCHEDULE = 'USING CRON 0 9 * * 1-5 America/New_York'
```

## Supported Changes

After creation, DCM can apply changes to:

| Property | Notes |
|----------|-------|
| `SCHEDULE` | Interval or cron expression |
| `WAREHOUSE` | Compute resource for condition evaluation |
| `COMMENT` | Descriptive text |

## No Notable Immutable Properties

Unlike sequences (START) or file formats (TYPE), alerts have no commonly-encountered immutable properties. The condition query and action can be changed freely.

## Common Actions

**Email notification** (requires a notification integration):
```sql
THEN
    CALL SYSTEM$SEND_EMAIL(
        'my_email_integration',
        'team@example.com',
        'Alert: condition detected',
        'Description of what was found.'
    );
```

**Insert into an audit table**:
```sql
THEN
    INSERT INTO my_db.my_schema.alert_log (alert_name, fired_at)
    VALUES ('alert_stale_records', CURRENT_TIMESTAMP());
```

**Call a stored procedure**:
```sql
THEN
    CALL my_db.my_schema.handle_stale_records();
```

## File Organization

Place alert definitions alongside tasks in a dedicated file:

```
sources/definitions/
  alerts.sql      ← DEFINE ALERT statements
  tasks.sql       ← DEFINE TASK statements
  tables.sql
```

Or combine with tasks if both are few:

```
sources/definitions/
  scheduled.sql   ← tasks and alerts together
```

## Jinja Templating

Use Jinja variables for environment-specific databases, schemas, and warehouses:

```sql
DEFINE ALERT {{ database }}.{{ schema }}.alert_stale_orders
    WAREHOUSE = {{ warehouse }}
    SCHEDULE = 'USING CRON 0 * * * * UTC'
    IF (EXISTS (
        SELECT 1 FROM {{ database }}.{{ schema }}.orders
        WHERE status = 'PENDING'
          AND created_at < DATEADD('hour', -2, CURRENT_TIMESTAMP())
    ))
    THEN
        CALL SYSTEM$SEND_EMAIL(
            'email_integration',
            'oncall@example.com',
            'Stale orders in {{ database }}',
            'Orders stuck in PENDING for over 2 hours.'
        );
```

Use Jinja loops to create per-environment or per-region alerts:

```sql
{% for env in ['dev', 'prod'] %}
DEFINE ALERT {{ env }}_db.analytics.alert_data_freshness
    WAREHOUSE = {{ env }}_warehouse
    SCHEDULE = '60 MINUTES'
    IF (EXISTS (
        SELECT 1 FROM {{ env }}_db.analytics.summary
        WHERE MAX(updated_at) < DATEADD('hour', -2, CURRENT_TIMESTAMP())
    ))
    THEN
        INSERT INTO {{ env }}_db.analytics.alert_log (env, fired_at)
        VALUES ('{{ env }}', CURRENT_TIMESTAMP());
{% endfor %}
```

## Notes

- DCM automatically suspends alerts before deployment and resumes them after, preventing spurious firings during schema changes.
- The condition query must be a `SELECT` statement that returns rows when the condition is true. The alert fires if the query returns one or more rows.
- The `WAREHOUSE` clause is required; serverless compute for alerts requires additional account-level configuration.
- Alerts replaced the `CREATE ALERT` imperative approach. If your project previously used `CREATE OR REPLACE ALERT` in `post_deploy.sql`, migrate it to `DEFINE ALERT` in `alerts.sql`.
