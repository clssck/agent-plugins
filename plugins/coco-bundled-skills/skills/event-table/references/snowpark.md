
# Snowpark Telemetry Format

## Event Table Schema

| Column | Path | Description |
|--------|------|-------------|
| `timestamp` | - | When the event/metric was recorded |
| `start_timestamp` | - | When the function execution started (for duration tracking) |
| `resource_attributes` | `:"snow.executable.type"` | `'PROCEDURE'` or `'FUNCTION'` |
| `resource_attributes` | `:"snow.executable.name"` | Procedure/UDF name with signature (e.g., `MY_PROC(VARCHAR):VARCHAR`) |
| `resource_attributes` | `:"snow.database.name"` | Database name |
| `resource_attributes` | `:"snow.schema.name"` | Schema name |
| `resource_attributes` | `:"snow.query.id"` | Query ID of the execution |
| `resource_attributes` | `:"snow.warehouse.name"` | Warehouse used for execution |
| `resource_attributes` | `:"snow.session.id"` | Session ID |
| `resource_attributes` | `:"snow.owner.name"` | Role that owns the executable (may have quotes) |
| `resource_attributes` | `:"db.user"` | User who executed the procedure |
| `resource_attributes` | `:"telemetry.sdk.language"` | Language: `sql`, `javascript`, `external`, `java`, `python`, `scala` |
| `record_type` | - | `LOG` for log events, `SPAN` for trace spans, `METRIC` for metrics |
| `record` | `:"severity_text"` | For LOG: `FATAL`, `ERROR`, `WARN`, `INFO`, `DEBUG` |
| `record` | `:"severity_number"` | Numeric severity (17=ERROR, 13=WARN, 9=INFO, 5=DEBUG) |
| `record` | `:"metric":"name"` | For METRIC: metric name (e.g., `process.cpu.utilization`) |
| `record_attributes` | - | Custom attributes added via logging |
| `value` | - | Log message (for LOG) or metric value (for METRIC) |
| `trace` | `:"trace_id"` | Trace ID for distributed tracing |
| `trace` | `:"span_id"` | Span ID for distributed tracing |

## Metrics

Metrics are emitted periodically during function/procedure execution. Use `record_type = 'METRIC'` to filter.

| Metric Name | Value Unit | Description |
|-------------|------------|-------------|
| `process.cpu.utilization` | Ratio (0.0 - 1.0) | CPU utilization (0.9 = 90%) |
| `process.memory.usage` | Bytes | Memory consumption (1000000000 = 1 GB) |

**Metric Emission Pattern:** Metrics are emitted periodically during execution:
- `start_timestamp` = execution start (constant per query_id)
- `timestamp` = when each metric sample was recorded
- Duration = `max(timestamp) - min(start_timestamp)`

## Key Concepts

| Concept | Description |
|---------|-------------|
| **LOG_LEVEL** | Controls which log messages are generated: ERROR, WARN, INFO, DEBUG |
| **TRACE_LEVEL** | Controls trace span capture: OFF, ON_EVENT, ALWAYS |
| **SDK Languages** | `sql`, `javascript`, `external`, `java`, `python`, `scala` |

## Query Templates

Use `<EVENT_TABLE>` as placeholder — the parent skill resolves the actual event table.

**All Snowpark logs:**
```sql
SELECT 
    timestamp,
    resource_attributes:"snow.executable.name"::VARCHAR AS procedure_name,
    resource_attributes:"snow.database.name"::VARCHAR AS database_name,
    resource_attributes:"snow.schema.name"::VARCHAR AS schema_name,
    resource_attributes:"telemetry.sdk.language"::VARCHAR AS language,
    record:"severity_text"::VARCHAR AS severity,
    value::VARCHAR AS log_message,
    record_attributes AS custom_attributes
FROM <EVENT_TABLE>
WHERE resource_attributes:"snow.executable.type" = 'PROCEDURE'
ORDER BY timestamp DESC;
```

**Errors only (use FATAL for exceptions):**
```sql
SELECT 
    timestamp,
    resource_attributes:"snow.executable.name"::VARCHAR AS procedure_name,
    resource_attributes:"snow.database.name"::VARCHAR AS database_name,
    resource_attributes:"snow.schema.name"::VARCHAR AS schema_name,
    resource_attributes:"snow.query.id"::VARCHAR AS query_id,
    resource_attributes:"db.user"::VARCHAR AS executed_by,
    value::VARCHAR AS error_message,
    record_attributes AS custom_attributes
FROM <EVENT_TABLE>
WHERE resource_attributes:"snow.executable.type" IN ('PROCEDURE', 'FUNCTION')
  AND record:"severity_text" IN ('ERROR', 'FATAL')
ORDER BY timestamp DESC;
```

**Python Snowpark procedures:**
```sql
SELECT 
    timestamp,
    resource_attributes:"snow.executable.name"::VARCHAR AS procedure_name,
    resource_attributes:"snow.database.name"::VARCHAR AS database_name,
    record:"severity_text"::VARCHAR AS severity,
    value::VARCHAR AS log_message
FROM <EVENT_TABLE>
WHERE resource_attributes:"snow.executable.type" = 'PROCEDURE'
  AND resource_attributes:"telemetry.sdk.language" = 'python'
ORDER BY timestamp DESC;
```

**JavaScript procedures:**
```sql
SELECT 
    timestamp,
    resource_attributes:"snow.executable.name"::VARCHAR AS procedure_name,
    resource_attributes:"snow.database.name"::VARCHAR AS database_name,
    record:"severity_text"::VARCHAR AS severity,
    value::VARCHAR AS log_message
FROM <EVENT_TABLE>
WHERE resource_attributes:"snow.executable.type" = 'PROCEDURE'
  AND resource_attributes:"telemetry.sdk.language" = 'javascript'
ORDER BY timestamp DESC;
```

**Trace spans (execution flow):**
```sql
SELECT 
    timestamp,
    start_timestamp,
    resource_attributes:"snow.executable.name"::VARCHAR AS procedure_name,
    trace:"trace_id"::VARCHAR AS trace_id,
    trace:"span_id"::VARCHAR AS span_id,
    scope:"name"::VARCHAR AS span_name,
    record_attributes
FROM <EVENT_TABLE>
WHERE resource_attributes:"snow.executable.type" = 'PROCEDURE'
  AND record_type = 'SPAN'
ORDER BY timestamp DESC;
```

**CPU utilization metrics:**
```sql
SELECT 
    timestamp,
    resource_attributes:"snow.database.name"::VARCHAR
        || '.' || resource_attributes:"snow.schema.name"::VARCHAR
        || '.' || resource_attributes:"snow.executable.name"::VARCHAR AS function_name,
    record:"metric":"name"::VARCHAR AS metric_name,
    value AS cpu_utilization
FROM <EVENT_TABLE>
WHERE resource_attributes:"snow.executable.type" IN ('FUNCTION', 'PROCEDURE')
  AND record_type = 'METRIC'
  AND record:"metric":"name" = 'process.cpu.utilization'
ORDER BY timestamp DESC;
```

**Memory usage metrics:**
```sql
SELECT 
    timestamp,
    resource_attributes:"snow.database.name"::VARCHAR
        || '.' || resource_attributes:"snow.schema.name"::VARCHAR
        || '.' || resource_attributes:"snow.executable.name"::VARCHAR AS function_name,
    record:"metric":"name"::VARCHAR AS metric_name,
    value AS memory_bytes,
    ROUND(value / 1000000000, 2) AS memory_gb
FROM <EVENT_TABLE>
WHERE resource_attributes:"snow.executable.type" IN ('FUNCTION', 'PROCEDURE')
  AND record_type = 'METRIC'
  AND record:"metric":"name" = 'process.memory.usage'
ORDER BY timestamp DESC;
```

**Long-running functions (by execution duration):**
```sql
SELECT 
    MIN(start_timestamp) AS start_time,
    MAX(timestamp) AS end_time,
    TIMESTAMPDIFF('second', MIN(start_timestamp), MAX(timestamp)) AS duration_seconds,
    resource_attributes:"snow.database.name"::VARCHAR
        || '.' || resource_attributes:"snow.schema.name"::VARCHAR
        || '.' || resource_attributes:"snow.executable.name"::VARCHAR AS function_name,
    resource_attributes:"snow.query.id"::VARCHAR AS query_id
FROM <EVENT_TABLE>
WHERE resource_attributes:"snow.executable.type" IN ('FUNCTION', 'PROCEDURE')
  AND record_type = 'METRIC'
GROUP BY function_name, query_id
HAVING duration_seconds > 120
ORDER BY end_time DESC;
```

## Common Filters

```sql
-- Filter by specific procedure:
  AND resource_attributes:"snow.executable.name" LIKE '%<procedure_name>%'
-- Filter by database:
  AND resource_attributes:"snow.database.name" = '<database_name>'
-- Filter by user who executed:
  AND resource_attributes:"db.user" = '<username>'
-- Filter by time range:
  AND timestamp > DATEADD('hour', -24, CURRENT_TIMESTAMP())
```

## Common Use Cases

| Use Case | Key Filters |
|----------|-------------|
| Procedure/UDF errors | `record:"severity_text" IN ('ERROR', 'FATAL')` |
| Python Snowpark logs | `resource_attributes:"telemetry.sdk.language" = 'python'` |
| JavaScript procedure logs | `resource_attributes:"telemetry.sdk.language" = 'javascript'` |
| Specific procedure | `resource_attributes:"snow.executable.name" LIKE '%X%'` |
| Execution by specific user | `resource_attributes:"db.user" = 'USERNAME'` |
| Debug-level logs | `record:"severity_text" = 'DEBUG'` |
| High CPU utilization | `record_type = 'METRIC' AND record:'metric':'name' = 'process.cpu.utilization'` |
| High memory usage | `record_type = 'METRIC' AND record:'metric':'name' = 'process.memory.usage'` |
| Long-running functions | Group by query_id, check `timestampdiff(start_timestamp, timestamp)` |
