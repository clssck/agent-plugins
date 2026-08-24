-- Check Object Exists
-- Verify that an object exists before running lineage queries
-- Replace <database>, <schema>, <table> with actual values BEFORE executing

SELECT 
    table_catalog AS database_name,
    table_schema AS schema_name,
    table_name,
    table_type AS object_type,
    row_count,
    bytes AS size_bytes,
    created AS created_at,
    last_altered AS last_modified
FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
WHERE table_catalog = '<database>'
  AND table_schema = '<schema>'
  AND table_name = '<table>'
  AND deleted IS NULL;
