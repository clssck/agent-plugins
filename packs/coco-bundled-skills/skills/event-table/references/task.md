
# Task Telemetry Format

## Event Table Schema

| Column | Path | Description |
|--------|------|-------------|
| `timestamp` | - | When the event occurred |
| `record_type` | - | `'EVENT'` for task execution events |
| `resource_attributes` | `:"snow.executable.type"` | `'TASK'` for task events |
| `resource_attributes` | `:"snow.executable.name"` | Task name |
| `resource_attributes` | `:"snow.database.name"` | Database name |
| `resource_attributes` | `:"snow.schema.name"` | Schema name |
| `resource_attributes` | `:"snow.owner.name"` | Role that owns the task (may have quotes) |
| `record` | `:"name"` | `'execution.status'` for task run status |
| `value` | `:state` | `'FAILED'`, `'SUCCEEDED'` |

## Key Concepts

| Concept | Description |
|---------|-------------|
| **record_type** | `'EVENT'` for task execution events |
| **record:"name"** | `'execution.status'` for task run status events |
| **State Values** | `'FAILED'` (task error), `'SUCCEEDED'` (task completed) |

## Query Templates

Use `<EVENT_TABLE>` as placeholder — the parent skill resolves the actual event table.

**Task execution history (all tasks):**
```sql
SELECT 
    timestamp,
    resource_attributes:"snow.database.name"::VARCHAR
        || '.' || resource_attributes:"snow.schema.name"::VARCHAR
        || '.' || resource_attributes:"snow.executable.name"::VARCHAR AS task_name,
    value:state::VARCHAR AS state
FROM <EVENT_TABLE>
WHERE record_type = 'EVENT'
  AND resource_attributes:"snow.executable.type" = 'TASK'
  AND record:"name" = 'execution.status'
ORDER BY timestamp DESC;
```

**Failed task runs:**
```sql
SELECT 
    timestamp,
    resource_attributes:"snow.database.name"::VARCHAR
        || '.' || resource_attributes:"snow.schema.name"::VARCHAR
        || '.' || resource_attributes:"snow.executable.name"::VARCHAR AS task_name,
    value:state::VARCHAR AS state
FROM <EVENT_TABLE>
WHERE record_type = 'EVENT'
  AND resource_attributes:"snow.executable.type" = 'TASK'
  AND record:"name" = 'execution.status'
  AND value:state = 'FAILED'
ORDER BY timestamp DESC;
```

## Common Filters

```sql
-- Filter by specific task:
  AND resource_attributes:"snow.executable.name" = '<task_name>'
-- Filter by database:
  AND resource_attributes:"snow.database.name" = '<database_name>'
-- Filter by time range:
  AND timestamp > DATEADD('hour', -24, CURRENT_TIMESTAMP())
```

## Common Use Cases

| Use Case | Key Filters |
|----------|-------------|
| Task failures | `value:state = 'FAILED'` |
| Task successes | `value:state = 'SUCCEEDED'` |
| Specific task events | `resource_attributes:"snow.executable.name" = 'X'` |
| Tasks in database | `resource_attributes:"snow.database.name" = 'X'` |
