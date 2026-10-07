# Event-Table Sweep Around Alert Incident Time

Used by [`../SKILL.md`](../SKILL.md) Step 3. Pulls structured telemetry (logs, metrics, spans) from the event table around the alert's incident time so that downstream classification and product-skill delegation start with the richest possible context.

The sweep runs for **every** troubleshooting session — including `TRIGGERED` cases where the user wants to know "why did this fire?" — because the event table often contains causal context that the alert's own narrow condition query cannot surface.

---

## Inputs

| Input | Source |
|-------|--------|
| `{incident_time}` | Most recent failure-or-firing `SCHEDULED_TIME` from `INFORMATION_SCHEMA.ALERT_HISTORY` (Step 2 of the parent SKILL). |
| `{event_table}` | Discovered by loading [`../../../event-table/event-table-get-setup/SKILL.md`](../../../event-table/event-table-get-setup/SKILL.md). May differ from the account default if the alert's database scope has an override. |
| `{database_filter}` | Object scope extracted from the alert's condition query — see "Object-Scope Extraction" below. |
| `{schema_filter}` | Same. |
| `{object_name_filter}` | Same — the specific table/task/DT/connector being monitored, if discoverable. |

---

## Object-Scope Extraction

Walk the alert's `condition` body and harvest the first match from each row of this table:

| Filter | Patterns to Search For |
|--------|------------------------|
| Database | `resource_attributes:"snow.database.name" = '<X>'`, `resource_attributes:"snow.database.name" IN (...)`, fully-qualified references like `<X>.<schema>.<object>` in `FROM`/`JOIN`, `INFORMATION_SCHEMA.X(NAME => '<db>.<schema>.<obj>')`. |
| Schema | `resource_attributes:"snow.schema.name" = '<X>'`, fully-qualified refs as above. |
| Object name | `resource_attributes:"snow.executable.name"`, `resource_attributes:"snow.task.name"`, `resource_attributes:"flow.identifier"` (Openflow), `INFORMATION_SCHEMA.<X>(NAME => …)` argument, or `name` column predicates (`WHERE name = '<X>'`). |
| Object type | `resource_attributes:"snow.executable.type"` (`'DYNAMIC_TABLE'`, `'TASK'`, `'PROCEDURE'`, etc.). |
| Trace ID | `record:trace_id`, `trace_id` column predicates. Rare but useful when the alert correlates spans. |
| Openflow runtime | `resource_attributes:"k8s.namespace.name"` (the namespace is `runtime-<lowercased-dashed-runtime-name>`). |

If a filter cannot be derived, leave it as `NULL` and drop the corresponding `WHERE` clause from the queries below — do **not** substitute a wildcard like `'%'`, which would broaden the sweep beyond the alert's scope.

---

## Time Window

Default: `[{incident_time} - 5 minutes, {incident_time} + 5 minutes]`.

Expand to `[-15min, +5min]` if the initial sweep returns zero rows. The asymmetry reflects that root-cause events typically precede the alert firing.

The event-table `TIMESTAMP` column is `TIMESTAMP_NTZ` in UTC. Always wrap `{incident_time}` with `CONVERT_TIMEZONE('UTC', …)::TIMESTAMP_NTZ` if it came from a session-timezone source.

---

## Query Templates

### Q1 — Recent error / warn log records

```sql
SELECT
  TIMESTAMP,
  resource_attributes:"snow.database.name"::STRING       AS database_name,
  resource_attributes:"snow.schema.name"::STRING         AS schema_name,
  resource_attributes:"snow.executable.name"::STRING     AS object_name,
  resource_attributes:"snow.executable.type"::STRING     AS object_type,
  resource_attributes:"k8s.namespace.name"::STRING       AS k8s_namespace,
  COALESCE(record:severity_text::STRING,
           record_attributes:"severity"::STRING)         AS severity,
  COALESCE(record:name::STRING,
           record_attributes:"event.name"::STRING)       AS event_name,
  value:state::STRING                                    AS state,
  value:message::STRING                                  AS message,
  record:trace_id::STRING                                AS trace_id,
  record:span_id::STRING                                 AS span_id
FROM {event_table}
WHERE TIMESTAMP BETWEEN
        DATEADD('minute', -5, '{incident_time}'::TIMESTAMP_NTZ)
    AND DATEADD('minute',  5, '{incident_time}'::TIMESTAMP_NTZ)
  AND record_type = 'LOG'
  AND COALESCE(record:severity_text::STRING,
               record_attributes:"severity"::STRING) IN ('WARN', 'ERROR', 'FATAL')
  -- Object-scope filters (drop any line where the value is NULL):
  AND resource_attributes:"snow.database.name"::STRING = '{database_filter}'
  AND resource_attributes:"snow.schema.name"::STRING   = '{schema_filter}'
  AND resource_attributes:"snow.executable.name"::STRING = '{object_name_filter}'
ORDER BY TIMESTAMP
LIMIT 100;
```

### Q2 — Span / trace records with non-OK status

```sql
SELECT
  TIMESTAMP,
  resource_attributes:"snow.database.name"::STRING   AS database_name,
  resource_attributes:"snow.executable.name"::STRING AS object_name,
  record:name::STRING                                AS span_name,
  record:trace_id::STRING                            AS trace_id,
  record:span_id::STRING                             AS span_id,
  record:parent_span_id::STRING                      AS parent_span_id,
  record:status:code::INT                            AS status_code,
  record:status:message::STRING                      AS status_message,
  DATEDIFF('millisecond',
           record:start_timestamp::TIMESTAMP_NTZ,
           TIMESTAMP)                                AS duration_ms
FROM {event_table}
WHERE TIMESTAMP BETWEEN
        DATEADD('minute', -5, '{incident_time}'::TIMESTAMP_NTZ)
    AND DATEADD('minute',  5, '{incident_time}'::TIMESTAMP_NTZ)
  AND record_type = 'SPAN'
  AND record:status:code::INT <> 0    -- non-OK
  AND resource_attributes:"snow.database.name"::STRING = '{database_filter}'
ORDER BY TIMESTAMP
LIMIT 50;
```

### Q3 — Metric anomalies

Metric semantics differ per product (see [`../../../event-table/references/`](../../../event-table/references) for per-product schemas). The generic sweep below pulls all metrics in the window scoped to the alert's object — interpret the names against the relevant product reference.

```sql
SELECT
  TIMESTAMP,
  resource_attributes:"snow.executable.name"::STRING AS object_name,
  resource_attributes:"k8s.namespace.name"::STRING   AS k8s_namespace,
  record:metric:name::STRING                         AS metric_name,
  record:metric:unit::STRING                         AS metric_unit,
  value::FLOAT                                       AS metric_value
FROM {event_table}
WHERE TIMESTAMP BETWEEN
        DATEADD('minute', -5, '{incident_time}'::TIMESTAMP_NTZ)
    AND DATEADD('minute',  5, '{incident_time}'::TIMESTAMP_NTZ)
  AND record_type = 'METRIC'
  AND resource_attributes:"snow.database.name"::STRING = '{database_filter}'
ORDER BY metric_name, TIMESTAMP
LIMIT 200;
```

### Q4 — Span events (e.g., exceptions)

```sql
SELECT
  TIMESTAMP,
  record:name::STRING                                AS event_name,
  record:trace_id::STRING                            AS trace_id,
  record:span_id::STRING                             AS span_id,
  record_attributes                                  AS attributes,
  resource_attributes:"snow.executable.name"::STRING AS object_name
FROM {event_table}
WHERE TIMESTAMP BETWEEN
        DATEADD('minute', -5, '{incident_time}'::TIMESTAMP_NTZ)
    AND DATEADD('minute',  5, '{incident_time}'::TIMESTAMP_NTZ)
  AND record_type = 'SPAN_EVENT'
  AND resource_attributes:"snow.database.name"::STRING = '{database_filter}'
ORDER BY TIMESTAMP
LIMIT 50;
```

---

## Openflow-Specific Sweep

When [`product-detection.md`](product-detection.md) priority 2 matches (Openflow), prefer this scoped variant — Openflow telemetry is keyed by Kubernetes namespace, not `snow.*` resource attributes:

```sql
SELECT
  TIMESTAMP,
  resource_attributes:"k8s.namespace.name"::STRING  AS namespace,
  resource_attributes:"k8s.pod.name"::STRING        AS pod,
  COALESCE(record:severity_text::STRING,
           record_attributes:"severity"::STRING)    AS severity,
  COALESCE(record:body::STRING, value::STRING)      AS log_body,
  record_attributes:"logger"::STRING                AS logger,
  record:trace_id::STRING                           AS trace_id
FROM {event_table}
WHERE TIMESTAMP BETWEEN
        DATEADD('minute', -5, '{incident_time}'::TIMESTAMP_NTZ)
    AND DATEADD('minute',  5, '{incident_time}'::TIMESTAMP_NTZ)
  AND record_type = 'LOG'
  AND resource_attributes:"k8s.namespace.name"::STRING = '{runtime_namespace}'
  AND COALESCE(record:severity_text::STRING,
               record_attributes:"severity"::STRING) IN ('WARN', 'ERROR', 'FATAL')
ORDER BY TIMESTAMP
LIMIT 100;
```

When delegating to `openflow-observability`, pass these rows through as the seed evidence for its Discovery Sequence — it short-circuits the skill's own Recent Error Logs / Error Pattern Summary queries.

---

## Empty-Result Handling

If all four queries return zero rows in `[-5min, +5min]`:

1. Re-check the object-scope filters — a too-narrow filter (e.g., wrong schema case) is the most common cause.
2. Expand the window to `[-15min, +5min]` and re-run.
3. If still empty, run a diagnostic query to confirm the event table is receiving any data at all in that window:
   ```sql
   SELECT COUNT(*) AS row_count, MIN(TIMESTAMP) AS earliest, MAX(TIMESTAMP) AS latest
   FROM {event_table}
   WHERE TIMESTAMP BETWEEN
           DATEADD('minute', -15, '{incident_time}'::TIMESTAMP_NTZ)
       AND DATEADD('minute',   5, '{incident_time}'::TIMESTAMP_NTZ);
   ```
4. If the event table has data but none for the alert's scope, surface this in the findings — the alert may be misconfigured (wrong database/schema in its condition) or the monitored object may not be emitting telemetry (LOG_LEVEL too restrictive — see [`../../../../data-engineering/dynamic-tables/dt-alerting/SKILL.md`](../../../dynamic-tables/dt-alerting/SKILL.md) Step 2 for the LOG_LEVEL setup).

---

## Output to Pass Forward

Structured findings to forward to Step 4 (classification) and Step 5 (product-skill delegation):

```yaml
incident_time: "2026-04-18T14:32:00Z"
event_table: "MY_DB.OBSERVABILITY.EVENTS"
window: "[-5min, +5min]"
object_scope:
  database: "SALES_PROD"
  schema: "REPORTING"
  object_name: "DAILY_ORDERS_DT"
  object_type: "DYNAMIC_TABLE"
findings:
  log_records_count: 12
  span_errors_count: 1
  metric_rows_count: 47
  notable:
    - severity: "ERROR"
      event_name: "refresh.status"
      message: "Insufficient privileges to operate on table 'STAGING.RAW_ORDERS'"
      timestamp: "2026-04-18T14:31:42Z"
    - span_status: "ERROR"
      span_name: "DT_REFRESH"
      status_message: "QUERY_FAILED"
      duration_ms: 2341
empty_result: false
```

The downstream product skill can then skip its own initial discovery queries and jump straight to root-cause analysis.
