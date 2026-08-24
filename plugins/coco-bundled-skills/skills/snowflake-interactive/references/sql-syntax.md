# SQL Syntax Reference

Quick reference for interactive table and warehouse SQL commands.

---

## Interactive Table Commands

### CREATE INTERACTIVE TABLE (Static)

```sql
CREATE INTERACTIVE TABLE [IF NOT EXISTS] <database>.<schema>.<table_name>
CLUSTER BY (<column1> [, <column2>, ...])
AS <select_query>;
```

### CREATE INTERACTIVE TABLE (Dynamic with TARGET_LAG)

```sql
CREATE INTERACTIVE TABLE <database>.<schema>.<table_name>
CLUSTER BY (<column1> [, <column2>, ...])
TARGET_LAG = '<num> { seconds | minutes | hours | days }'
WAREHOUSE = <warehouse_name>
AS <select_query>;
```

**TARGET_LAG minimum:** 60 seconds or 1 minute

### CREATE INTERACTIVE TABLE (Streaming)

**Simple form:**
```sql
CREATE INTERACTIVE TABLE <database>.<schema>.<table_name> (
  <column_definitions>
) CLUSTER BY (<cluster_expression>);
```

**With Kafka field mapping:**
```sql
CREATE OR REPLACE INTERACTIVE TABLE <database>.<schema>.<table_name> (
  <column_definitions>
) CLUSTER BY (<cluster_expression>)
AS (
  SELECT 
    $1:RECORD_CONTENT.<field1>,
    $1:RECORD_CONTENT.<field2>,
    $1:RECORD_METADATA.topic,
    SYSDATE() as streaming_event_time
  FROM TABLE(DATA_SOURCE(TYPE => 'STREAMING'))
);
```

### INSERT OVERWRITE

```sql
INSERT OVERWRITE INTO <table_name>
<select_query>;
```

**Note:** `INTO` keyword is required.

### DROP TABLE

```sql
DROP TABLE [IF EXISTS] <database>.<schema>.<table_name>;
```

### RENAME TABLE

```sql
ALTER TABLE <old_name> RENAME TO <new_name>;
```

**Note:** Only RENAME is supported. ADD COLUMN and other ALTER operations fail.

---

## Interactive Warehouse Commands

### CREATE INTERACTIVE WAREHOUSE

**With tables:**
```sql
CREATE [OR REPLACE] INTERACTIVE WAREHOUSE <warehouse_name>
TABLES (<table_list>)
WAREHOUSE_SIZE = '<size>';
```

**Without tables:**
```sql
CREATE [OR REPLACE] INTERACTIVE WAREHOUSE <warehouse_name>
WAREHOUSE_SIZE = '<size>';
```

**Sizes:** XSMALL, SMALL, MEDIUM, LARGE, XLARGE, 2XLARGE, 3XLARGE, 4XLARGE

### ADD TABLES

```sql
ALTER WAREHOUSE <warehouse_name>
ADD TABLES (<fully.qualified.table_name> [, ...]);
```

**Important:** Use fully qualified names: `DATABASE.SCHEMA.TABLE`

### DROP TABLES (Remove Association)

```sql
ALTER WAREHOUSE <warehouse_name>
DROP TABLES (<fully.qualified.table_name> [, ...]);
```

**Note:** Use `DROP TABLES` not `REMOVE TABLES`.

### RESUME WAREHOUSE

```sql
ALTER WAREHOUSE <warehouse_name> RESUME;
```

**Idempotent:**
```sql
ALTER WAREHOUSE <warehouse_name> RESUME IF SUSPENDED;
```

### SUSPEND WAREHOUSE

```sql
ALTER WAREHOUSE <warehouse_name> SUSPEND;
```

### SET FALLBACK WAREHOUSE

```sql
ALTER WAREHOUSE <interactive_warehouse_name>
SET FALLBACK_WAREHOUSE = <fallback_warehouse_name>;
```

**Note:** Fallback warehouse must be a non-interactive warehouse (standard, snowpark-optimized, etc.)

### REMOVE FALLBACK WAREHOUSE

```sql
ALTER WAREHOUSE <interactive_warehouse_name> UNSET FALLBACK_WAREHOUSE;
```

---

## Query Commands

### USE WAREHOUSE

```sql
USE WAREHOUSE <interactive_warehouse_name>;
```

**Required before querying interactive tables.**

### SHOW Commands

```sql
-- Show warehouses
SHOW WAREHOUSES;
SHOW WAREHOUSES LIKE '<pattern>';

-- Show tables
SHOW TABLES;
SHOW TABLES LIKE '<pattern>';

-- Show pipes
SHOW PIPES IN SCHEMA <schema_name>;

-- Show tables in warehouse (may not work in all accounts)
SHOW INTERACTIVE TABLES IN INTERACTIVE WAREHOUSE <warehouse_name>;
```

### DESCRIBE Commands

```sql
DESC TABLE <table_name>;
DESC PIPE <pipe_name>;
```

---

## Streaming Privileges

### Grant Required Privileges

```sql
CREATE ROLE IF NOT EXISTS <role_name>;
CREATE USER IF NOT EXISTS <user_name>;
GRANT ROLE <role_name> TO USER <user_name>;
GRANT USAGE ON SCHEMA <schema_name> TO ROLE <role_name>;
GRANT ALL ON TABLE <table_name> TO ROLE <role_name>;
GRANT ALL ON PIPE <table_name> TO ROLE <role_name>;
```

### Key-Pair Authentication Setup

```bash
# Generate keys
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out rsa_key.p8 -nocrypt
openssl rsa -in rsa_key.p8 -pubout -out rsa_key.pub
```

```sql
-- Associate public key with user
ALTER USER <user_name> SET RSA_PUBLIC_KEY='<formatted_public_key>';
```

### Kafka Connector Configuration

**Critical settings for interactive tables with Snowpipe Streaming:**

```json
{
  "snowflake.streaming.v2.enabled": "true",
  "snowflake.streaming.enable.altering.target.pipes.tables": "false",
  "snowflake.enable.schematization": "false",
  "snowflake.ingestion.method": "SNOWPIPE_STREAMING",
  "snowflake.topic2table.map": "<kafka_topic>: <table_name>",
  "topics": "<kafka_topic>",
  "buffer.flush.time": "1",
  "snowflake.private.key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
}
```

**Note**: These settings are required for interactive tables. See [references/kafka-quickstart.md](kafka-quickstart.md) for complete config.

### Monitoring Streaming Ingestion

```sql
-- View streaming file migration history
SELECT * 
FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWPIPE_STREAMING_FILE_MIGRATION_HISTORY
WHERE table_name = '<table_name>'
ORDER BY start_time DESC
LIMIT 100;
```

---

## Quick Reference

| Operation | Command |
|-----------|---------|
| Create static table | `CREATE INTERACTIVE TABLE ... CLUSTER BY ... AS SELECT` |
| Create dynamic table | `CREATE INTERACTIVE TABLE ... TARGET_LAG ... WAREHOUSE ...` |
| Create streaming table | `CREATE INTERACTIVE TABLE (...) CLUSTER BY (...)` |
| Create warehouse | `CREATE INTERACTIVE WAREHOUSE ... WAREHOUSE_SIZE` |
| Add tables to warehouse | `ALTER WAREHOUSE ... ADD TABLES (...)` |
| Remove tables from warehouse | `ALTER WAREHOUSE ... DROP TABLES (...)` |
| Resume warehouse | `ALTER WAREHOUSE ... RESUME` |
| Suspend warehouse | `ALTER WAREHOUSE ... SUSPEND` |
| Set fallback warehouse | `ALTER WAREHOUSE ... SET FALLBACK_WAREHOUSE = ...` |
| Remove fallback warehouse | `ALTER WAREHOUSE ... UNSET FALLBACK_WAREHOUSE` |
| Replace all data | `INSERT OVERWRITE INTO ... SELECT` |
