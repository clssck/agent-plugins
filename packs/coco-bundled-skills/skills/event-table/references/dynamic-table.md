
# Dynamic Table Telemetry Format

## Event Table Schema

| Column | Path | Description |
|--------|------|-------------|
| `timestamp` | - | When the event occurred |
| `resource_attributes` | `:"snow.executable.type"` | `'DYNAMIC_TABLE'` for DT events |
| `resource_attributes` | `:"snow.executable.name"` | Dynamic table name |
| `resource_attributes` | `:"snow.database.name"` | Database name |
| `resource_attributes` | `:"snow.schema.name"` | Schema name |
| `resource_attributes` | `:"snow.query.id"` | Query ID of the refresh |
| `record` | `:"severity_text"` | `ERROR`, `WARN`, or `INFO` |
| `record` | `:"name"` | `'refresh.status'` for refresh events |
| `value` | `:state` | `FAILED`, `UPSTREAM_FAILURE`, `SUCCEEDED` |
| `value` | `:message` | Error message (for failures) |

## Key Concepts

| Concept | Description |
|---------|-------------|
| **LOG_LEVEL** | Controls which events are captured: ERROR, WARN, INFO |
| **Refresh States** | `FAILED` (DT error), `UPSTREAM_FAILURE` (upstream DT failed), `SUCCEEDED` |

## Query Templates

Use `<EVENT_TABLE>` as placeholder — the parent skill resolves the actual event table.

**Refresh history (all DTs):**
```sql
SELECT 
    timestamp,
    resource_attributes:"snow.executable.name"::VARCHAR AS dt_name,
    resource_attributes:"snow.database.name"::VARCHAR AS database_name,
    resource_attributes:"snow.schema.name"::VARCHAR AS schema_name,
    value:state::VARCHAR AS state,
    record:"severity_text"::VARCHAR AS severity,
    value:message::VARCHAR AS message
FROM <EVENT_TABLE>
WHERE resource_attributes:"snow.executable.type" = 'DYNAMIC_TABLE'
  AND record:"name" = 'refresh.status'
ORDER BY timestamp DESC;
```

**Failed refreshes:**
```sql
SELECT 
    timestamp,
    resource_attributes:"snow.executable.name"::VARCHAR AS dt_name,
    resource_attributes:"snow.database.name"::VARCHAR AS database_name,
    resource_attributes:"snow.schema.name"::VARCHAR AS schema_name,
    resource_attributes:"snow.query.id"::VARCHAR AS query_id,
    value:message::VARCHAR AS error_message
FROM <EVENT_TABLE>
WHERE resource_attributes:"snow.executable.type" = 'DYNAMIC_TABLE'
  AND record:"name" = 'refresh.status'
  AND value:state = 'FAILED'
ORDER BY timestamp DESC;
```

**Successful refreshes (requires LOG_LEVEL = INFO):**
```sql
SELECT 
    timestamp,
    resource_attributes:"snow.executable.name"::VARCHAR AS dt_name,
    resource_attributes:"snow.database.name"::VARCHAR AS database_name,
    resource_attributes:"snow.schema.name"::VARCHAR AS schema_name,
    resource_attributes:"snow.query.id"::VARCHAR AS query_id
FROM <EVENT_TABLE>
WHERE resource_attributes:"snow.executable.type" = 'DYNAMIC_TABLE'
  AND record:"name" = 'refresh.status'
  AND value:state = 'SUCCEEDED'
ORDER BY timestamp DESC;
```

**Upstream failures:**
```sql
SELECT 
    timestamp,
    resource_attributes:"snow.executable.name"::VARCHAR AS dt_name,
    value:state::VARCHAR AS state
FROM <EVENT_TABLE>
WHERE resource_attributes:"snow.executable.type" = 'DYNAMIC_TABLE'
  AND record:"name" = 'refresh.status'
  AND value:state = 'UPSTREAM_FAILURE'
ORDER BY timestamp DESC;
```

**All refresh events (requires LOG_LEVEL = INFO):**
```sql
SELECT 
    timestamp,
    resource_attributes:"snow.executable.name"::VARCHAR AS dt_name,
    value:state::VARCHAR AS state,
    record:"severity_text"::VARCHAR AS severity
FROM <EVENT_TABLE>
WHERE resource_attributes:"snow.executable.type" = 'DYNAMIC_TABLE'
  AND record:"name" = 'refresh.status'
ORDER BY timestamp DESC;
```

## Common Filters

```sql
-- Filter by specific dynamic table:
  AND resource_attributes:"snow.executable.name" = '<dynamic_table_name>'
-- Filter by database:
  AND resource_attributes:"snow.database.name" = '<database_name>'
-- Filter by time range:
  AND timestamp > DATEADD('hour', -24, CURRENT_TIMESTAMP())
```

## Common Use Cases

| Use Case | Key Filters |
|----------|-------------|
| Recent refresh successes | `value:state = 'SUCCEEDED'` |
| Recent refresh failures | `value:state = 'FAILED'` |
| Upstream failures | `value:state = 'UPSTREAM_FAILURE'` |
| All events for specific DT | `resource_attributes:"snow.executable.name" = 'X'` |
| Error messages only | `record:"severity_text" = 'ERROR'` |
