# File Formats in DCM

## Syntax

```sql
DEFINE FILE FORMAT database_name.schema_name.format_name
    TYPE = 'format_type'
    [format-specific-options]
    [COMMENT = 'description'];
```

`TYPE` is required and must be one of: `CSV`, `JSON`, `AVRO`, `ORC`, `PARQUET`, `XML`.

### CSV Options

```sql
DEFINE FILE FORMAT database_name.schema_name.format_name
    TYPE = 'CSV'
    [COMPRESSION = 'AUTO' | 'GZIP' | 'BZ2' | 'BROTLI' | 'ZSTD' | 'DEFLATE' | 'RAW_DEFLATE' | 'NONE']
    [RECORD_DELIMITER = 'character']
    [FIELD_DELIMITER = 'character']
    [SKIP_HEADER = integer]
    [SKIP_BLANK_LINES = TRUE | FALSE]
    [FIELD_OPTIONALLY_ENCLOSED_BY = 'NONE' | '"' | "'"]
    [NULL_IF = ('string1', 'string2', ...)]
    [DATE_FORMAT = 'format_string' | 'AUTO']
    [TIME_FORMAT = 'format_string' | 'AUTO']
    [TIMESTAMP_FORMAT = 'format_string' | 'AUTO']
    [TRIM_SPACE = TRUE | FALSE]
    [EMPTY_FIELD_AS_NULL = TRUE | FALSE]
    [ENCODING = 'charset']
    [ERROR_ON_COLUMN_COUNT_MISMATCH = TRUE | FALSE]
    [REPLACE_INVALID_CHARACTERS = TRUE | FALSE]
    [COMMENT = 'description'];
```

### JSON Options

```sql
DEFINE FILE FORMAT database_name.schema_name.format_name
    TYPE = 'JSON'
    [COMPRESSION = 'AUTO' | 'GZIP' | 'BZ2' | 'BROTLI' | 'ZSTD' | 'DEFLATE' | 'RAW_DEFLATE' | 'NONE']
    [DATE_FORMAT = 'format_string' | 'AUTO']
    [TIME_FORMAT = 'format_string' | 'AUTO']
    [TIMESTAMP_FORMAT = 'format_string' | 'AUTO']
    [STRIP_OUTER_ARRAY = TRUE | FALSE]
    [STRIP_NULL_VALUES = TRUE | FALSE]
    [ALLOW_DUPLICATE = TRUE | FALSE]
    [IGNORE_UTF8_ERRORS = TRUE | FALSE]
    [REPLACE_INVALID_CHARACTERS = TRUE | FALSE]
    [COMMENT = 'description'];
```

### PARQUET Options

```sql
DEFINE FILE FORMAT database_name.schema_name.format_name
    TYPE = 'PARQUET'
    [COMPRESSION = 'AUTO' | 'LZO' | 'SNAPPY' | 'NONE']
    [BINARY_AS_TEXT = TRUE | FALSE]
    [USE_LOGICAL_TYPE = TRUE | FALSE]
    [USE_VECTORIZED_SCANNER = TRUE | FALSE]
    [REPLACE_INVALID_CHARACTERS = TRUE | FALSE]
    [NULL_IF = ('string1', 'string2', ...)]
    [COMMENT = 'description'];
```

### AVRO Options

```sql
DEFINE FILE FORMAT database_name.schema_name.format_name
    TYPE = 'AVRO'
    [COMPRESSION = 'AUTO' | 'GZIP' | 'BROTLI' | 'ZSTD' | 'DEFLATE' | 'RAW_DEFLATE' | 'NONE']
    [TRIM_SPACE = TRUE | FALSE]
    [REPLACE_INVALID_CHARACTERS = TRUE | FALSE]
    [NULL_IF = ('string1', 'string2', ...)]
    [COMMENT = 'description'];
```

### ORC Options

```sql
DEFINE FILE FORMAT database_name.schema_name.format_name
    TYPE = 'ORC'
    [TRIM_SPACE = TRUE | FALSE]
    [REPLACE_INVALID_CHARACTERS = TRUE | FALSE]
    [NULL_IF = ('string1', 'string2', ...)]
    [COMMENT = 'description'];
```

### XML Options

```sql
DEFINE FILE FORMAT database_name.schema_name.format_name
    TYPE = 'XML'
    [COMPRESSION = 'AUTO' | 'GZIP' | 'BZ2' | 'BROTLI' | 'ZSTD' | 'DEFLATE' | 'RAW_DEFLATE' | 'NONE']
    [IGNORE_UTF8_ERRORS = TRUE | FALSE]
    [PRESERVE_SPACE = TRUE | FALSE]
    [STRIP_OUTER_ELEMENT = TRUE | FALSE]
    [DISABLE_AUTO_CONVERT = TRUE | FALSE]
    [REPLACE_INVALID_CHARACTERS = TRUE | FALSE]
    [COMMENT = 'description'];
```

## Supported Changes

All format-specific options can be altered without dropping the format:
- Compression settings
- Delimiter characters, enclosure characters, null strings
- Date/time/timestamp format strings
- Boolean parsing flags (STRIP_OUTER_ARRAY, SKIP_BLANK_LINES, etc.)
- `COMMENT`

## Immutable

- `TYPE` cannot be changed after creation. To change a format's type, the format must be dropped and recreated.

## Using File Formats with Stages

A DEFINE'd file format can be referenced by name in a stage definition:

```sql
-- Reference by fully-qualified name in the stage's FILE_FORMAT clause
DEFINE STAGE database_name.schema_name.stage_name
    FILE_FORMAT = (FORMAT_NAME = 'database_name.schema_name.format_name');
```

When a stage uses `FORMAT_NAME`, the file format must be defined in the same DCM project or already exist in Snowflake before the stage is created. DCM resolves the dependency automatically when both objects are in the same project.

## Examples

### Basic CSV Format

```sql
DEFINE FILE FORMAT SALES_DB.RAW.CSV_FORMAT
    TYPE = 'CSV'
    SKIP_HEADER = 1
    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    NULL_IF = ('', 'NULL', 'N/A')
    COMMENT = 'Standard CSV ingest format';
```

### JSON Format

```sql
DEFINE FILE FORMAT SALES_DB.RAW.JSON_FORMAT
    TYPE = 'JSON'
    STRIP_OUTER_ARRAY = TRUE
    STRIP_NULL_VALUES = TRUE
    COMMENT = 'JSON array ingest format';
```

### Parquet Format

```sql
DEFINE FILE FORMAT ANALYTICS_DB.STAGING.PARQUET_FORMAT
    TYPE = 'PARQUET'
    COMPRESSION = 'SNAPPY'
    BINARY_AS_TEXT = FALSE
    COMMENT = 'Parquet format for analytics staging';
```

### With Jinja Templating

```sql
DEFINE FILE FORMAT ETL_DB{{env_suffix}}.STAGING.CSV_FORMAT
    TYPE = 'CSV'
    SKIP_HEADER = {{ skip_header_rows | default(1) }}
    FIELD_DELIMITER = '{{ field_delimiter | default(",") }}'
    NULL_IF = ('', 'NULL')
    COMMENT = 'CSV format for {{ env_suffix }} environment';
```

### Combined: File Format + Stage

```sql
-- Define the format first (DCM handles dependency ordering automatically)
DEFINE FILE FORMAT FINANCE_DB.RAW.CSV_INGEST_FORMAT
    TYPE = 'CSV'
    SKIP_HEADER = 1
    FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    TRIM_SPACE = TRUE
    NULL_IF = ('', 'NULL');

-- Stage references the format by fully-qualified name
DEFINE STAGE FINANCE_DB.RAW.UPLOAD_STAGE
    DIRECTORY = (ENABLE = TRUE)
    FILE_FORMAT = (FORMAT_NAME = 'FINANCE_DB.RAW.CSV_INGEST_FORMAT')
    COMMENT = 'Upload stage for CSV files';
```
