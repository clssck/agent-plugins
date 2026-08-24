# Error Tables — SQL Queries Reference

## Discover: Find error-logging-enabled tables

### Stored procedure (create once per schema)

```sql
CREATE OR REPLACE PROCEDURE {DATABASE}.{SCHEMA}._find_error_logging_tables(db_name STRING, schema_name STRING)
RETURNS TABLE(table_catalog STRING, table_schema STRING, table_name STRING)
LANGUAGE SQL
AS
$$
DECLARE
    fqn VARCHAR;
    ddl VARCHAR;
    v_catalog VARCHAR;
    v_schema VARCHAR;
    v_table VARCHAR;
    res RESULTSET;
    info_schema_query VARCHAR;
    rs RESULTSET;
BEGIN
    CREATE OR REPLACE TEMPORARY TABLE _et_discovery
        (table_catalog STRING, table_schema STRING, table_name STRING);

    info_schema_query := 'SELECT table_catalog, table_schema, table_name FROM '
        || db_name || '.INFORMATION_SCHEMA.TABLES WHERE table_schema = '''
        || schema_name || ''' AND table_type = ''BASE TABLE''';
    rs := (EXECUTE IMMEDIATE info_schema_query);
    LET c1 CURSOR FOR rs;
    FOR rec IN c1 DO
        v_catalog := rec.table_catalog;
        v_schema := rec.table_schema;
        v_table := rec.table_name;
        fqn := v_catalog || '.' || v_schema || '.' || v_table;
        ddl := (SELECT GET_DDL('TABLE', :fqn));
        IF (ddl ILIKE '%ERROR_LOGGING%true%') THEN
            INSERT INTO _et_discovery VALUES (:v_catalog, :v_schema, :v_table);
        END IF;
    END FOR;
    res := (SELECT * FROM _et_discovery);
    RETURN TABLE(res);
END;
$$;
```

Call it:

```sql
CALL {DATABASE}.{SCHEMA}._find_error_logging_tables('{DATABASE}', '{SCHEMA}');
```

### Check error table row counts for discovered tables

After discovering enabled tables, run this for each one:

```sql
SELECT
    '{TABLE_NAME}' AS base_table,
    COUNT(*) AS error_rows,
    MIN(TIMESTAMP) AS oldest_error,
    MAX(TIMESTAMP) AS newest_error,
    COUNT(DISTINCT QUERY_ID) AS distinct_queries,
    COUNT(DISTINCT ERROR_CODE) AS distinct_error_types
FROM ERROR_TABLE({DATABASE}.{SCHEMA}.{TABLE_NAME});
```

## Monitor: Alert DDL

```sql
-- Create notification integration (one-time, requires ACCOUNTADMIN)
CREATE OR REPLACE NOTIFICATION INTEGRATION error_table_email
  TYPE = EMAIL
  ENABLED = TRUE
  ALLOWED_RECIPIENTS = ('{EMAIL}');

-- Create alert
CREATE OR REPLACE ALERT {DATABASE}.{SCHEMA}.error_table_alert_{TABLE_NAME}
  WAREHOUSE = {WAREHOUSE}
  SCHEDULE = '{INTERVAL_MINUTES} MINUTE'
  IF (EXISTS (
    SELECT 1
    FROM ERROR_TABLE({DATABASE}.{SCHEMA}.{TABLE_NAME})
    WHERE TIMESTAMP > DATEADD('minute', -{INTERVAL_MINUTES}, CURRENT_TIMESTAMP())
    HAVING COUNT(*) > {THRESHOLD}
  ))
  THEN
    CALL SYSTEM$SEND_SNOWFLAKE_NOTIFICATION(
      SNOWFLAKE.NOTIFICATION.TEXT_PLAIN(
        'Error Tables Alert: ' || {THRESHOLD} || '+ errors detected on {DATABASE}.{SCHEMA}.{TABLE_NAME} in the last {INTERVAL_MINUTES} minutes.'
      ),
      SNOWFLAKE.NOTIFICATION.EMAIL_INTEGRATION_CONFIG(
        'error_table_email',
        '{EMAIL}',
        'Error Tables Alert — {TABLE_NAME}'
      )
    );

ALTER ALERT {DATABASE}.{SCHEMA}.error_table_alert_{TABLE_NAME} RESUME;
```

## Manage: Archive and cleanup DDL

### Archive table (one-time)

```sql
CREATE TABLE IF NOT EXISTS {ARCHIVE_TABLE} (
    ARCHIVED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    SOURCE_TABLE VARCHAR,
    TIMESTAMP TIMESTAMP_LTZ,
    QUERY_ID VARCHAR,
    ERROR_CODE NUMBER,
    ERROR_METADATA VARIANT,
    ERROR_DATA VARIANT
);
```

### Cleanup task

```sql
CREATE OR REPLACE TASK {DATABASE}.{SCHEMA}.error_table_cleanup_{TABLE_NAME}
  WAREHOUSE = {WAREHOUSE}
  SCHEDULE = 'USING CRON 0 2 * * 0 America/New_York'  -- weekly Sunday 2am
AS
BEGIN
    -- Archive everything
    INSERT INTO {ARCHIVE_TABLE}
    SELECT
        CURRENT_TIMESTAMP(),
        '{DATABASE}.{SCHEMA}.{TABLE_NAME}',
        TIMESTAMP, QUERY_ID, ERROR_CODE, ERROR_METADATA, ERROR_DATA
    FROM ERROR_TABLE({DATABASE}.{SCHEMA}.{TABLE_NAME});

    -- Truncate
    TRUNCATE TABLE ERROR_TABLE({DATABASE}.{SCHEMA}.{TABLE_NAME});
END;

ALTER TASK {DATABASE}.{SCHEMA}.error_table_cleanup_{TABLE_NAME} RESUME;
```

### Simple truncate (no archive)

```sql
TRUNCATE TABLE ERROR_TABLE({DATABASE}.{SCHEMA}.{TABLE_NAME});
```

## Storage: Estimation query

### Estimate error table payload size

```sql
SELECT
    '{DATABASE}.{SCHEMA}.{TABLE_NAME}' AS base_table,
    COUNT(*) AS error_rows,
    ROUND(AVG(
        52 +  -- fixed: TIMESTAMP(8) + QUERY_ID(~36) + ERROR_CODE(8)
        LENGTH(TO_VARCHAR(ERROR_METADATA)) +
        LENGTH(TO_VARCHAR(ERROR_DATA))
    ), 0) AS avg_bytes_per_row,
    ROUND(SUM(
        52 +
        LENGTH(TO_VARCHAR(ERROR_METADATA)) +
        LENGTH(TO_VARCHAR(ERROR_DATA))
    ) / (1024*1024), 2) AS estimated_raw_mb,
    ROUND(SUM(
        52 +
        LENGTH(TO_VARCHAR(ERROR_METADATA)) +
        LENGTH(TO_VARCHAR(ERROR_DATA))
    ) * 0.6 / (1024*1024), 2) AS estimated_compressed_mb
FROM ERROR_TABLE({DATABASE}.{SCHEMA}.{TABLE_NAME});
```
