# Snowpark Python — Observability

Add logging, tracing, and profiling to Snowpark Python UDFs and stored procedures.

> **Event Table setup, alerts, and notifications** are handled by dedicated skills (`event-table`, `alert`, `notification`). This reference covers only Snowpark-specific instrumentation and profiling. If the user needs to create an event table, set telemetry levels, or configure alerts, route to those skills instead.

## When to Route Here

Route here when user wants to:
- Add logging or tracing instrumentation to Python handler code
- Profile UDFs or stored procedures for CPU/memory performance
- Know which packages to include for telemetry (`snowflake-telemetry-python`)
- Understand SP profiler vs UDF profiler differences

**Route to `event-table` skill instead for:** Event table creation, association, telemetry level configuration, querying logs/traces.

**Route to `alert` skill instead for:** Creating, altering, suspending/resuming alerts.

---

## 1. Instrument Code

Add logging and tracing to Snowpark Python code using standard Python `logging` and the `snowflake-telemetry-python` package.

### Add Logging

```python
import logging

# Use a named logger for filtering in event table queries
logger = logging.getLogger("my_procedure")

def main(session, input_param):
    logger.info(f"Starting procedure with input: {input_param}")

    try:
        df = session.table('MY_TABLE').filter(col('ID') == input_param)
        count = df.count()
        logger.info(f"Found {count} records", extra={'record_count': count})

        logger.info("Procedure completed successfully")
        return f"Processed {count} records"

    except Exception as e:
        logger.error(f"Procedure failed: {str(e)}", exc_info=True)
        raise
```

**Tip:** Use a named logger (e.g., `"my_procedure"`) instead of `__name__` to make filtering easier via `SCOPE['name']` in the Event Table.

**Logging Levels:**

| Python Level | Snowflake Level | When to Use |
|--------------|-----------------|-------------|
| `logger.debug()` | DEBUG | Detailed diagnostic info |
| `logger.info()` | INFO | Normal operation milestones |
| `logger.warning()` | WARN | Something unexpected but recoverable |
| `logger.error()` | ERROR | Errors that need attention |
| `logger.critical()` | FATAL | Critical failures |

**Custom attributes** via `extra`:

```python
logger.info("Processing batch", extra={
    'batch_id': batch_id,
    'record_count': count,
    'source_table': 'ORDERS'
})
```

**Override log levels in Python:**

```python
my_logger = logging.getLogger('my_module')
my_logger.setLevel(logging.DEBUG)

# Reduce noise from Snowpark internals
snowpark_logger = logging.getLogger('snowflake.snowpark')
snowpark_logger.setLevel(logging.WARNING)
```

### Add Trace Events and Span Attributes

The `snowflake.telemetry` package provides:
- `telemetry.add_event(name, attributes)` — emit named trace events
- `telemetry.set_span_attribute(key, value)` — set attributes on the current span

```python
import logging
from snowflake import telemetry

logger = logging.getLogger(__name__)

def main(session, batch_date):
    telemetry.set_span_attribute("batch_date", str(batch_date))
    telemetry.set_span_attribute("pipeline", "etl_pipeline")

    telemetry.add_event("extract_start")
    df = session.table('SOURCE').filter(col('DATE') == batch_date)
    record_count = df.count()
    telemetry.add_event("extract_complete", {"record_count": record_count})

    telemetry.add_event("transform_start")
    transformed = df.with_column('PROCESSED_AT', current_timestamp())
    telemetry.add_event("transform_complete")

    telemetry.add_event("load_start")
    transformed.write.mode('append').save_as_table('TARGET')
    telemetry.add_event("load_complete", {"rows_loaded": record_count})

    return f"Loaded {record_count} rows"
```

**Best practices:** Use descriptive event names (verb_noun: `extract_start`, `load_complete`). Add attributes for key context. Keep attribute cardinality low.

### Custom Spans (Optional)

For fine-grained timing using OpenTelemetry. Requires `opentelemetry-api` in addition to `snowflake-telemetry-python`.

```python
from opentelemetry import trace

tracer = trace.get_tracer("my.pipeline")

def main(session):
    with tracer.start_as_current_span("heavy_computation") as span:
        span.set_attribute("operation", "data_transform")
        result = expensive_operation(session)
        span.add_event("computation_complete", {"result_size": len(result)})

    with tracer.start_as_current_span("data_load") as span:
        load_data(session, result)

    return "Success"
```

**Custom spans MUST close before the handler completes**, or their data won't be captured. Always use `with` statements.

### UDF Instrumentation

**Warning:** For UDFs, trace events are emitted **per row processed**. Be careful with high-volume tables.

```python
from snowflake import telemetry

def process(input_val):
    telemetry.set_span_attribute("function", "process_value")
    # Only emit events for errors/anomalies, not every row
    if input_val is None:
        telemetry.add_event("null_input_detected")
    return transform(input_val)
```

### Required Packages

| Capability | Required Package |
|------------|------------------|
| Logging | `snowflake-telemetry-python` |
| Trace events & span attributes | `snowflake-telemetry-python` |
| Custom spans | `snowflake-telemetry-python` + `opentelemetry-api` |

### Instrumentation Limits

- Maximum **128 trace events** per span
- Maximum **128 span attributes** per span
- Custom spans must close before handler completes

### What NOT to Log

- Passwords, API keys, tokens
- PII (Personal Identifiable Information)
- Full data payloads (log counts/summaries instead)
- High-frequency debug logs in production
- Events for every row in high-volume UDFs

---

## 2. Profile Performance

Use the Python profiler to identify CPU and memory hotspots in UDFs and stored procedures.

Both stored procedures and UDFs use the same profiler session parameters. The only differences are retrieval function and invocation method (CALL vs SELECT).

### Profiler Setup

```sql
-- 1. Set up output stage
CREATE TEMPORARY STAGE profiler_output;
ALTER SESSION SET PYTHON_PROFILER_TARGET_STAGE = '<db>.<schema>.profiler_output';

-- 2. Enable profiling (LINE for CPU, MEMORY for memory)
ALTER SESSION SET ACTIVE_PYTHON_PROFILER = 'LINE';

-- 3. Execute the object to profile
-- For stored procedures:
CALL <db>.<schema>.<procedure>(<args>);
-- For UDFs:
SELECT <db>.<schema>.<func>(col) FROM <table> LIMIT 100;

-- 4. Retrieve results
-- For stored procedures:
SELECT SNOWFLAKE.CORE.GET_PYTHON_PROFILER_OUTPUT(LAST_QUERY_ID());
-- For UDFs (wait 15-20 seconds first):
SELECT * FROM TABLE(SNOWFLAKE.LOCAL.GET_PYTHON_UDF_PROFILER_OUTPUT('<query_id>'));

-- 5. Disable
ALTER SESSION SET ACTIVE_PYTHON_PROFILER = '';
ALTER SESSION UNSET PYTHON_PROFILER_TARGET_STAGE;
```

**UDF profiler note:** Results have a 15-20 second delay. The UDF retrieval function requires the `SNOWFLAKE.PROFILER_USER` application role:

```sql
GRANT APPLICATION ROLE SNOWFLAKE.PROFILER_USER TO ROLE <role>;
```

### Profile Additional Modules

```sql
-- For stored procedures
ALTER SESSION SET PYTHON_PROFILER_MODULES = 'my_module, other_module';

-- For UDFs
ALTER SESSION SET PYTHON_UDF_PROFILER_MODULES = 'my_module, other_module';
```

### Interpret LINE Profiler Results

```
Line #      Hits        Time  Per Hit   % Time  Line Contents
==============================================================
     8         2       7248.4   3624.2     80.9      session.sql('''...''').collect()
    20         1       1528.4   1528.4     17.1      pandas_df = df.to_pandas()
```

Focus on lines with highest `% Time` values.

### Interpret MEMORY Profiler Results

```
Line #   Mem usage    Increment  Occurrences  Line Contents
=============================================================
     4    245.3 MiB    245.3 MiB           1   def main(session):
    20    327.9 MiB     82.1 MiB           1       pandas_df = df.to_pandas()
```

Focus on lines with large positive `Increment` values.

### Common Optimizations

| Pattern | Symptom | Fix |
|---------|---------|-----|
| SQL in loop | `.collect()` high % time | Batch operations |
| `to_pandas()` | Large memory increment | Process in chunks |
| Import inside function | Import shows high % time | Move to module level |
| String concatenation | `+=` in loop | Use `''.join()` |

### Profiler Limitations

- If the UDF/stored procedure fails, no profiler output is produced
- Recursive profiling not supported (only top-level functions)
- SPROCs/UDFs created via `Session.sproc.register` / `Session.udf.register` not supported
- Functions running in parallel through `joblib` not profiled
- UDF profiler: 15-20s delay, no third-party module profiling

---

## Troubleshooting

**Profiler shows no output:**
1. Verify `ACTIVE_PYTHON_PROFILER` is set (`SHOW PARAMETERS LIKE 'ACTIVE_PYTHON_PROFILER' IN SESSION`)
2. For SP profiler: check `PYTHON_PROFILER_TARGET_STAGE` is set
3. For UDF profiler: wait 15-20 seconds, check access roles
4. SPROCs/UDFs registered via Python API are not supported

**No events appearing in Event Table:**
1. Verify Event Table is set at account/database level (use `event-table` skill)
2. Check LOG_LEVEL is not OFF on the target object
3. Verify `snowflake-telemetry-python` is in PACKAGES clause
4. Wait a few seconds — events may be delayed
