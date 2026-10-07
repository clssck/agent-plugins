# Snowflake App Logs Reference

## Structured logs from event table

When an event table is configured (`ALTER ACCOUNT SET EVENT_TABLE = <fqn>`), use this function to query structured log, metric, and event records:

```sql
-- LOG records (container stdout/stderr)
SELECT SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA(
    '<database>.<schema>.<app_name>',
    'LOG'
);

-- With time window
SELECT SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA(
    '<database>.<schema>.<app_name>',
    'LOG',
    '<start_timestamp>',
    '<end_timestamp>'
);

-- METRIC records (CPU, memory, custom metrics)
SELECT SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA(
    '<database>.<schema>.<app_name>',
    'METRIC'
);

-- EVENT records (container lifecycle events)
SELECT SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA(
    '<database>.<schema>.<app_name>',
    'EVENT'
);
```

Returns a JSON array-of-arrays. Column order per record type:

| Type | Columns |
|------|---------|
| `LOG` | `TIMESTAMP, INSTANCE_ID, CONTAINER_NAME, LOG, RECORD_ATTRIBUTES` |
| `METRIC` | `TIMESTAMP, METRIC_NAME, VALUE, UNIT, INSTANCE_ID, CONTAINER_NAME, RESOURCE, RECORD, RECORD_ATTRIBUTES` |
| `EVENT` | `TIMESTAMP, SEVERITY, EVENT_NAME, EVENT_DETAILS, INSTANCE_ID, CONTAINER_NAME, RECORD, RECORD_ATTRIBUTES` |

For large result sets, pass `'true'` as the fifth argument to get a query UUID instead of inline data, then retrieve the full results with `RESULT_SCAN`:

```sql
SELECT SYSTEM$GET_APPLICATION_SERVICE_EVENT_TABLE_DATA(
    '<database>.<schema>.<app_name>', 'LOG',
    '1970-01-01 00:00:00', '2999-12-31 23:59:59', 'true'
);
-- Returns a UUID string; retrieve full results:
SELECT * FROM TABLE(RESULT_SCAN('<uuid>'));
```

Requires `MONITOR` privilege on the application service. The function queries the event table via the service's internal owner role; callers do not need direct access to the event table itself.

For CPU/memory metrics and resource health monitoring, see `monitoring.md`.
