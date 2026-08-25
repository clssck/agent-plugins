# Pipes in DCM

DCM manages Snowpipe pipes with `DEFINE PIPE`. All pipe properties supported by
`CREATE PIPE` are available, and DCM manages the pipe lifecycle (create, alter, drop)
across environments with Jinja templating.

## Syntax

```sql
DEFINE PIPE database_name.schema_name.pipe_name
    [AUTO_INGEST = TRUE | FALSE]
    [ERROR_INTEGRATION = integration_name]
    [AWS_SNS_TOPIC = 'sns_topic_arn']
    [INTEGRATION = 'notification_integration_name']
    [COMMENT = 'description']
AS
    COPY INTO database_name.schema_name.table_name
    FROM @database_name.schema_name.stage_name
    [FILE_FORMAT = (FORMAT_NAME = 'database_name.schema_name.format_name')];
```

## Properties

| Property | Description |
|----------|-------------|
| `AUTO_INGEST` | `TRUE` loads files automatically on cloud event notifications. See the warning below |
| `ERROR_INTEGRATION` | Notification integration for error notifications |
| `AWS_SNS_TOPIC` | SNS topic ARN for S3 auto-ingest |
| `INTEGRATION` | Notification integration name for Azure/GCS auto-ingest |
| `COMMENT` | Descriptive text |
| `AS <copy_statement>` | The `COPY INTO` that defines what the pipe loads |

## Supported Changes

- `COMMENT` — and nothing else.

## Immutable / Unsupported

**The `COPY INTO` body and every other pipe property are immutable.** Only `COMMENT` can
be changed after creation. To change the target table, source stage, file format, or any
`AUTO_INGEST`/integration setting, the pipe must be dropped and recreated: remove the
`DEFINE PIPE`, deploy, then redefine it.

Warn the user before recreating a pipe. Snowpipe tracks which files it has already
loaded, and a recreated pipe starts with fresh load history — files already in the stage
may be reloaded, duplicating rows.

## ⚠️ AUTO_INGEST Requires Configuration Outside DCM

`AUTO_INGEST = TRUE` depends on an S3/Azure/GCS event notification pointing at the pipe's
notification channel. **DCM creates the pipe but does not configure the cloud-side
notification** — the pipe will exist and load nothing until that is set up.

This is the same shape as the storage integration behind an external stage: the DCM-managed
object is declarative, the cloud-side prerequisite is not. After deploying, the channel ARN
is read with `DESCRIBE PIPE` and used to create the notification in the cloud provider.

Tell the user this explicitly when they ask for an auto-ingest pipe, rather than leaving
them with a pipe that silently never fires. The notification integration itself (Azure/GCS)
is **not** supported by `DEFINE` — put it in `pre_deploy.sql`, since the pipe references it
by name and the planner validates that reference. See `primitives/unsupported_objects.md`.

## Examples

### Basic Pipe

```sql
DEFINE PIPE ETL_DB.RAW.ORDERS_PIPE
    COMMENT = 'Loads order CSVs from the landing stage'
AS
    COPY INTO ETL_DB.RAW.ORDERS
    FROM @ETL_DB.RAW.CSV_LANDING
    FILE_FORMAT = (FORMAT_NAME = 'ETL_DB.RAW.CSV_FORMAT');
```

### Full Ingestion Slice

A pipe is rarely defined alone. The realistic unit is format + stage + table + pipe, all
in one project so DCM orders them:

```sql
DEFINE FILE FORMAT ETL_DB.RAW.CSV_FORMAT
    TYPE = 'CSV'
    SKIP_HEADER = 1
    FIELD_OPTIONALLY_ENCLOSED_BY = '"';

DEFINE STAGE ETL_DB.RAW.CSV_LANDING
    DIRECTORY = (ENABLE = TRUE)
    FILE_FORMAT = (FORMAT_NAME = 'ETL_DB.RAW.CSV_FORMAT');

DEFINE TABLE ETL_DB.RAW.ORDERS (
    ORDER_ID NUMBER,
    CUSTOMER_ID NUMBER,
    AMOUNT NUMBER(12,2),
    ORDER_TS TIMESTAMP_NTZ
);

DEFINE PIPE ETL_DB.RAW.ORDERS_PIPE
    COMMENT = 'Loads order CSVs into RAW.ORDERS'
AS
    COPY INTO ETL_DB.RAW.ORDERS
    FROM @ETL_DB.RAW.CSV_LANDING
    FILE_FORMAT = (FORMAT_NAME = 'ETL_DB.RAW.CSV_FORMAT');
```

### Auto-Ingest Pipe on S3

```sql
DEFINE PIPE ETL_DB.RAW.S3_ORDERS_PIPE
    AUTO_INGEST = TRUE
    COMMENT = 'Auto-ingest from S3; SNS notification configured outside DCM'
AS
    COPY INTO ETL_DB.RAW.ORDERS
    FROM @ETL_DB.RAW.S3_LANDING
    FILE_FORMAT = (FORMAT_NAME = 'ETL_DB.RAW.CSV_FORMAT');
```

After deploy, wire up the cloud side:

```sql
DESCRIBE PIPE ETL_DB.RAW.S3_ORDERS_PIPE;  -- read notification_channel, then
                                          -- create the S3 event notification for it
```

### With Jinja Templating

```sql
DEFINE PIPE ETL_DB{{env_suffix}}.RAW.ORDERS_PIPE
    AUTO_INGEST = {{ 'TRUE' if auto_ingest else 'FALSE' }}
    COMMENT = 'Order ingestion for {{env_suffix}} environment'
AS
    COPY INTO ETL_DB{{env_suffix}}.RAW.ORDERS
    FROM @ETL_DB{{env_suffix}}.RAW.CSV_LANDING
    FILE_FORMAT = (FORMAT_NAME = 'ETL_DB{{env_suffix}}.RAW.CSV_FORMAT');
```

Templating `AUTO_INGEST` off in DEV is the common pattern — it avoids needing a cloud
notification per environment.
