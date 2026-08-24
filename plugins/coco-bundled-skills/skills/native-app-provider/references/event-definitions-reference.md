# Telemetry Configuration Reference

## Telemetry Levels

These settings control what telemetry the app emits into the consumer's event table. All are set under `configuration:` in `manifest.yml`.

| Field | Values | Controls |
|-------|--------|----------|
| `log_level` | `OFF` \| `TRACE` \| `DEBUG` \| `INFO` \| `WARN` \| `ERROR` \| `FATAL` | Log messages (`RECORD_TYPE = 'LOG'`) |
| `log_event_level` | `OFF` \| `TRACE` \| `DEBUG` \| `INFO` \| `WARN` \| `ERROR` \| `FATAL` | Telemetry events (`RECORD_TYPE = 'EVENT'`), including lifecycle events. Requires BCR 2026_02. |
| `trace_level` | `OFF` \| `ALWAYS` \| `ON_EVENT` | Trace spans |
| `metric_level` | `NONE` \| `ALL` | CPU and memory metrics |

**Recommendation**: Start with `log_level: INFO`, `log_event_level: INFO`, `trace_level: OFF`, `metric_level: NONE`. Always set both `log_level` and `log_event_level` for forward compatibility — before BCR 2026_02, `log_event_level` is ignored and `log_level` governs everything. Higher levels increase consumer storage costs.

## Event Definitions

Event definitions specify what telemetry consumers share **back to the provider** via event sharing. They are added under the `configuration:` block in `manifest.yml` as `telemetry_event_definitions`.

## Supported Event Definitions

| Type | Name | Filter | What it shares |
|------|------|--------|----------------|
| `ALL` | SNOWFLAKE$ALL | `*` | All log messages, traces, metrics, and events |
| `ALL_EVENTS` | SNOWFLAKE$ALL_EVENTS | `RECORD_TYPE='EVENT'` | All events (lifecycle events, platform events) |
| `ERRORS_AND_WARNINGS` | SNOWFLAKE$ERRORS_AND_WARNINGS | `RECORD_TYPE='LOG' AND RECORD:severity_text IN ('FATAL','ERROR','WARN')` | Error and warning logs only |
| `TRACES` | SNOWFLAKE$TRACES | `RECORD_TYPE IN ('SPAN','SPAN_EVENT')` | Trace spans and span events |
| `USAGE_LOGS` | SNOWFLAKE$USAGE_LOGS | `RECORD_TYPE='LOG' AND RECORD:severity_text='INFO'` | INFO-level usage logs |
| `DEBUG_LOGS` | SNOWFLAKE$DEBUG_LOGS | `RECORD_TYPE='LOG' AND RECORD:severity_text IN ('DEBUG','TRACE')` | Debug and trace-level logs |
| `METRICS` | SNOWFLAKE$METRICS | `RECORD_TYPE IN ('METRIC')` | CPU and memory metrics |

## Sharing Modes

| Mode | Behavior |
|------|----------|
| `MANDATORY` | Enabled automatically at install. Consumer cannot disable. Requires consumer to have an active event table, otherwise events are discarded. Once enabled, cannot be disabled by the consumer. |
| `OPTIONAL` | Consumer can enable/disable via Snowsight or SQL. Not enabled by default. |

## Recommendations

- Use `MANDATORY` for `ERRORS_AND_WARNINGS` — gives you baseline visibility into app failures across all consumers.
- Use `OPTIONAL` for verbose definitions like `ALL` or `DEBUG_LOGS` — respect consumer control over telemetry costs.
- If you only need lifecycle events (health status changes, upgrades), use `ALL_EVENTS` with `MANDATORY`.

## SPCS Limitation

Native Apps with Snowpark Container Services currently only support the `ALL` event definition. Granular event definitions (e.g., `ERRORS_AND_WARNINGS`, `TRACES`) are not yet supported for SPCS apps.

## Migration Note

Apps published before event definitions existed behave as if they have `OPTIONAL ALL`. Adding explicit event definitions to the manifest applies to new versions/patches only. No other actions are required for providers — just add the definitions to the manifest.
