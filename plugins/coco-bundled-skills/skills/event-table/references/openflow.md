
# OpenFlow Telemetry Format

Full telemetry schema reference: https://docs.snowflake.com/en/user-guide/data-integration/openflow/monitor

## Event Table Schema

### Common Columns

| Column | Path | Description |
|--------|------|-------------|
| `timestamp` | - | When the event/metric was recorded |
| `record_type` | - | `'METRIC'` for metrics, `'LOG'` for log messages |
| `value` | - | Metric value (number) or log message (JSON string) |

### Resource Attributes

**Important:** OpenFlow does NOT use any `snow.*` resource attribute keys. There is no `snow.executable.type`, `snow.executable.name`, `snow.database.name`, `snow.schema.name`, or `snow.query.id` in OpenFlow telemetry. Unlike other Snowflake products (Tasks, Dynamic Tables, Stored Procedures), OpenFlow events are identified by Kubernetes-level and OpenFlow-specific attributes instead.

| Path | Description |
|------|-------------|
| `:'k8s.namespace.name'` | Kubernetes namespace (e.g., `'runtime-xxx'`) |
| `:'k8s.pod.name'` | Kubernetes pod name |
| `:'k8s.container.name'` | Kubernetes container name (e.g., `'xxx-server'`) |
| `:'openflow.dataplane.id'` | Data plane ID |

### Record Attributes (for METRIC type)

| Path | Description |
|------|-------------|
| `:id` | Connection/component ID |
| `:"group.id"` | Group ID |
| `:type` | Component type (e.g., `'process-group'`) |
| `:'tree.level'` | Tree level (integer, 1 = top level) |
| `:"flow.identifier"` | Flow/connector identifier |

### Metric Path

Metric name is at: `record:metric:name`

### Openflow Metrics

**Connection Metrics:**

| Metric Name | Value Unit | Description |
|-------------|------------|-------------|
| `connection.backpressure.threshold.object` | Count | Backpressure threshold by object count |
| `connection.backpressure.threshold.bytes` | Bytes | Backpressure threshold by bytes |
| `connection.queued.count` | Count | Number of queued objects |
| `connection.queued.bytes` | Bytes | Size of queued data |

**Container/Resource Metrics:**

| Metric Name | Value Unit | Description |
|-------------|------------|-------------|
| `container.cpu.usage` | Ratio | CPU usage |
| `cores.available` | Count | Available CPU cores |

**Process Group Metrics:**

| Metric Name | Value Unit | Description |
|-------------|------------|-------------|
| `processgroup.time.processing` | Time | Processing time |
| `processgroup.bytes.received` | Bytes | Bytes received by process group |
| `processgroup.bytes.sent` | Bytes | Bytes sent by process group |

### LOG Type Structure

For `record_type = 'LOG'`, `value` contains a JSON string. Parse with `TRY_PARSE_JSON(value)`:

| Path | Description |
|------|-------------|
| `:"level"` | Log level (`'ERROR'`, `'WARN'`, `'INFO'`) |
| `:loggerName` | Logger name |
| `:formattedMessage` | Log message content |
| `:"mdc":"processGroupIdPath"` | Process group ID path |

## Query Templates

Use `<EVENT_TABLE>` as placeholder — the parent skill resolves the actual event table.

**Connection queue metrics:**
```sql
SELECT 
    timestamp,
    record_attributes:id::VARCHAR AS connection_id,
    record_attributes:"group.id"::VARCHAR AS group_id,
    record:metric:name::VARCHAR AS metric_name,
    value AS metric_value
FROM <EVENT_TABLE>
WHERE record_type = 'METRIC'
  AND record:metric:name IN ('connection.queued.count', 'connection.queued.bytes')
ORDER BY timestamp DESC;
```

**Backpressure threshold metrics:**
```sql
SELECT 
    timestamp,
    record_attributes:id::VARCHAR AS connection_id,
    record:metric:name::VARCHAR AS metric_name,
    value AS threshold_value
FROM <EVENT_TABLE>
WHERE record_type = 'METRIC'
  AND record:metric:name IN ('connection.backpressure.threshold.object', 'connection.backpressure.threshold.bytes')
ORDER BY timestamp DESC;
```

**Container CPU metrics:**
```sql
SELECT 
    timestamp,
    resource_attributes:'k8s.namespace.name'::VARCHAR AS namespace,
    resource_attributes:'k8s.pod.name'::VARCHAR AS pod,
    record:metric:name::VARCHAR AS metric_name,
    value AS metric_value
FROM <EVENT_TABLE>
WHERE record_type = 'METRIC'
  AND resource_attributes:'k8s.namespace.name' LIKE 'runtime-%'
  AND record:metric:name IN ('container.cpu.usage', 'cores.available')
ORDER BY timestamp DESC;
```

**Process group metrics:**
```sql
SELECT 
    timestamp,
    record_attributes:id::VARCHAR AS id,
    record_attributes:"flow.identifier"::VARCHAR AS connector,
    record:metric:name::VARCHAR AS metric_name,
    value AS metric_value
FROM <EVENT_TABLE>
WHERE record_type = 'METRIC'
  AND record_attributes:type = 'process-group'
  AND record_attributes:'tree.level'::INT = 1
ORDER BY timestamp DESC;
```

**Error logs:**
```sql
SELECT 
    timestamp,
    resource_attributes:'openflow.dataplane.id'::VARCHAR AS data_plane_id,
    resource_attributes:'k8s.namespace.name'::VARCHAR AS namespace,
    TRY_PARSE_JSON(value):"level"::VARCHAR AS log_level,
    TRY_PARSE_JSON(value):loggerName::VARCHAR AS logger,
    TRY_PARSE_JSON(value):formattedMessage::VARCHAR AS message
FROM <EVENT_TABLE>
WHERE record_type = 'LOG'
  AND resource_attributes:'k8s.namespace.name' LIKE 'runtime-%'
  AND TRY_PARSE_JSON(value):"level" = 'ERROR'
ORDER BY timestamp DESC;
```

## Common Filters

```sql
-- Filter by namespace:
  AND resource_attributes:'k8s.namespace.name' = '<namespace>'
-- Filter by data plane:
  AND resource_attributes:'openflow.dataplane.id' = '<data_plane_id>'
-- Filter by time range:
  AND timestamp > DATEADD('hour', -24, CURRENT_TIMESTAMP())
```

## Common Use Cases

| Use Case | Key Filters |
|----------|-------------|
| Queue metrics | `record:metric:name IN ('connection.queued.count', 'connection.queued.bytes')` |
| Backpressure thresholds | `record:metric:name LIKE 'connection.backpressure.threshold.%'` |
| CPU metrics | `record:metric:name IN ('container.cpu.usage', 'cores.available')` |
| Process group metrics | `record_attributes:type = 'process-group'` |
| Error logs | `record_type = 'LOG' AND TRY_PARSE_JSON(value):"level" = 'ERROR'` |
| Specific data plane | `resource_attributes:'openflow.dataplane.id' = 'X'` |
| Runtime namespace | `resource_attributes:'k8s.namespace.name' LIKE 'runtime-%'` |
