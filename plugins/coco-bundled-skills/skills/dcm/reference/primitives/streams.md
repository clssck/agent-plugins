# Streams in DCM

DCM manages streams with `DEFINE STREAM`. All stream variants supported by
`CREATE OR ALTER STREAM` are available — streams on tables, views, directory tables,
external tables, event tables, and dynamic tables.

## Syntax

The clause after `ON` depends on the source object:

```sql
-- Table
DEFINE STREAM database_name.schema_name.stream_name
    ON TABLE database_name.schema_name.table_name
    [APPEND_ONLY = TRUE | FALSE]
    [SHOW_INITIAL_ROWS = TRUE | FALSE]
    [COMMENT = 'description'];

-- View
DEFINE STREAM database_name.schema_name.stream_name
    ON VIEW database_name.schema_name.view_name
    [APPEND_ONLY = TRUE | FALSE]
    [SHOW_INITIAL_ROWS = TRUE | FALSE]
    [COMMENT = 'description'];

-- Directory table (a stage)
DEFINE STREAM database_name.schema_name.stream_name
    ON STAGE database_name.schema_name.stage_name
    [COMMENT = 'description'];

-- External table
DEFINE STREAM database_name.schema_name.stream_name
    ON EXTERNAL TABLE database_name.schema_name.external_table_name
    [INSERT_ONLY = TRUE]
    [COMMENT = 'description'];

-- Dynamic table
DEFINE STREAM database_name.schema_name.stream_name
    ON DYNAMIC TABLE database_name.schema_name.table_name
    [COMMENT = 'description'];

-- Event table
DEFINE STREAM database_name.schema_name.stream_name
    ON EVENT TABLE database_name.schema_name.table_name
    [COMMENT = 'description'];
```

## Properties

| Property | Applies to | Description |
|----------|-----------|-------------|
| `APPEND_ONLY` | Table, view streams | `TRUE` tracks inserts only — no updates or deletes. Cheaper for insert-only pipelines |
| `SHOW_INITIAL_ROWS` | Table, view streams | `TRUE` returns existing rows on first consumption instead of only later changes |
| `INSERT_ONLY` | External table streams | Only supported value is `TRUE` |
| `COMMENT` | All | Descriptive text |

## Supported Changes

- `COMMENT` — and nothing else.

## Immutable / Unsupported

**Streams are effectively immutable after creation.** Only `COMMENT` can be changed. To
change the source object, `APPEND_ONLY`, `SHOW_INITIAL_ROWS`, or anything else, the stream
must be dropped and recreated.

In DCM terms: remove the `DEFINE STREAM`, deploy, then redefine it with the new
properties. Warn the user before doing this — recreating a stream **resets its offset**, so
unconsumed changes are lost and the next read starts from the new stream's creation point.

Also unsupported: the `AT`/`BEFORE` time-travel clause and `SHOW_INITIAL_ROWS` are
creation-time only by nature, so they cannot be used to "rewind" an existing stream.

## Source Table Requirements

A stream on a table requires change tracking on that table. Set it explicitly in the
same project so DCM orders them correctly:

```sql
DEFINE TABLE ETL_DB.RAW.ORDERS (
    ORDER_ID NUMBER,
    AMOUNT NUMBER(12,2),
    UPDATED_AT TIMESTAMP_NTZ
)
CHANGE_TRACKING = TRUE;

DEFINE STREAM ETL_DB.RAW.ORDERS_STREAM
    ON TABLE ETL_DB.RAW.ORDERS
    COMMENT = 'Change feed for the orders table';
```

DCM resolves the dependency automatically — the table is created before the stream.

## Examples

### Append-Only Stream for an Insert-Only Pipeline

```sql
DEFINE STREAM ETL_DB.RAW.EVENTS_STREAM
    ON TABLE ETL_DB.RAW.EVENTS
    APPEND_ONLY = TRUE
    COMMENT = 'Insert-only change feed; ignores updates and deletes';
```

### Stream Consumed by a Task

The common pipeline shape: a stream feeds a task that merges changes downstream. The
task's `WHEN` clause keeps it from running on an empty stream.

```sql
DEFINE STREAM ETL_DB.RAW.ORDERS_STREAM
    ON TABLE ETL_DB.RAW.ORDERS;

DEFINE TASK ETL_DB.PIPELINE.TSK_PROCESS_ORDERS
    WAREHOUSE = 'ETL_WH'
    SCHEDULE = '5 MINUTE'
    WHEN SYSTEM$STREAM_HAS_DATA('ETL_DB.RAW.ORDERS_STREAM')
AS
    MERGE INTO ETL_DB.ANALYTICS.ORDERS_SUMMARY t
    USING ETL_DB.RAW.ORDERS_STREAM s
        ON t.ORDER_ID = s.ORDER_ID
    WHEN MATCHED THEN UPDATE SET t.AMOUNT = s.AMOUNT
    WHEN NOT MATCHED THEN INSERT (ORDER_ID, AMOUNT) VALUES (s.ORDER_ID, s.AMOUNT);
```

### Directory Table Stream on a Stage

```sql
DEFINE STAGE ETL_DB.RAW.FILE_LANDING
    DIRECTORY = (ENABLE = TRUE);

DEFINE STREAM ETL_DB.RAW.FILE_LANDING_STREAM
    ON STAGE ETL_DB.RAW.FILE_LANDING
    COMMENT = 'Tracks files arriving in the landing stage';
```

The stage must have `DIRECTORY = (ENABLE = TRUE)` — a stream on a stage reads its
directory table.

### With Jinja Templating

```sql
DEFINE STREAM ETL_DB{{env_suffix}}.RAW.ORDERS_STREAM
    ON TABLE ETL_DB{{env_suffix}}.RAW.ORDERS
    APPEND_ONLY = {{ 'TRUE' if append_only else 'FALSE' }}
    COMMENT = 'Orders change feed for {{env_suffix}} environment';
```
