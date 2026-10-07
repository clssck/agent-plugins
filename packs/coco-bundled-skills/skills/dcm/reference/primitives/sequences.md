# Sequences in DCM

## Syntax

```sql
DEFINE SEQUENCE database_name.schema_name.sequence_name
    [START = integer]
    [INCREMENT = integer]
    [ORDER | NOORDER]
    [COMMENT = 'description'];
```

## Supported Changes

- `INCREMENT` value
- `ORDER` / `NOORDER` flag
- `COMMENT`

## Immutable

- `START` value cannot be changed after creation. To change the starting value, the sequence must be dropped and recreated.

## Using Sequences in Table Defaults

Reference a sequence in a `DEFINE TABLE` column default using `sequence_name.NEXTVAL`:

```sql
DEFINE TABLE MY_DB.MY_SCHEMA.EVENTS (
    EVENT_ID NUMBER DEFAULT MY_DB.MY_SCHEMA.EVENT_ID_SEQ.NEXTVAL,
    EVENT_TYPE VARCHAR,
    CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
```

DCM resolves the dependency automatically when both the sequence and the table are defined in the same project.

## Examples

### Basic Sequence

```sql
DEFINE SEQUENCE SALES_DB.RAW.ORDER_ID_SEQ
    START = 1
    INCREMENT = 1
    COMMENT = 'Primary key sequence for orders';
```

### High-Increment Sequence

```sql
DEFINE SEQUENCE SALES_DB.RAW.BATCH_ID_SEQ
    START = 1000
    INCREMENT = 100
    ORDER
    COMMENT = 'Ordered batch ID sequence';
```

### With Jinja Templating

```sql
DEFINE SEQUENCE ETL_DB{{env_suffix}}.RAW.EVENT_ID_SEQ
    START = 1
    INCREMENT = 1
    COMMENT = 'Event ID sequence for {{env_suffix}} environment';

DEFINE TABLE ETL_DB{{env_suffix}}.RAW.EVENTS (
    EVENT_ID NUMBER DEFAULT ETL_DB{{env_suffix}}.RAW.EVENT_ID_SEQ.NEXTVAL,
    EVENT_TYPE VARCHAR,
    PAYLOAD VARIANT
);
```
