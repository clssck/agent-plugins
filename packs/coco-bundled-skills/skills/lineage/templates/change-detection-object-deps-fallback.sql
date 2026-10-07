-- Change Detection Fallback: OBJECT_DEPENDENCIES for upstream list (when GET_LINEAGE returns no rows or privilege error)
-- Replace <database>, <schema>, <table> with actual values BEFORE executing.

WITH upstream_objects AS (
    SELECT
        od.referenced_database AS src_database,
        od.referenced_schema AS src_schema,
        od.referenced_object_name AS src_object,
        od.referenced_object_domain AS src_type
    FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES od
    WHERE od.referencing_database = '<database>'
      AND od.referencing_schema = '<schema>'
      AND od.referencing_object_name = '<table>'

    UNION

    SELECT '<database>', '<schema>', '<table>', 'TARGET'
),

schema_changes AS (
    SELECT
        t.table_catalog || '.' || t.table_schema || '.' || t.table_name AS object_name,
        'SCHEMA_CHANGE' AS change_type,
        t.last_altered AS change_time,
        'Table structure modified' AS change_detail,
        t.table_owner AS changed_by
    FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES t
    JOIN upstream_objects u
        ON t.table_catalog = u.src_database
        AND t.table_schema = u.src_schema
        AND t.table_name = u.src_object
    WHERE t.last_altered > DATEADD(day, -7, CURRENT_TIMESTAMP())
      AND t.deleted IS NULL
),

column_changes AS (
    SELECT
        c.table_catalog || '.' || c.table_schema || '.' || c.table_name AS object_name,
        'COLUMN_CHANGE' AS change_type,
        c.deleted AS change_time,
        'Column: ' || c.column_name || ' (' || c.data_type || ')' AS change_detail,
        NULL AS changed_by
    FROM SNOWFLAKE.ACCOUNT_USAGE.COLUMNS c
    JOIN upstream_objects u
        ON c.table_catalog = u.src_database
        AND c.table_schema = u.src_schema
        AND c.table_name = u.src_object
    WHERE c.deleted > DATEADD(day, -7, CURRENT_TIMESTAMP())
),

data_modifications AS (
    SELECT
        modified.value:objectName::STRING AS object_name,
        'DATA_MODIFICATION' AS change_type,
        ah.query_start_time AS change_time,
        qh.query_type || ' by ' || ah.user_name AS change_detail,
        ah.user_name AS changed_by
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah
    JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY qh ON ah.query_id = qh.query_id,
    LATERAL FLATTEN(input => ah.objects_modified) AS modified
    WHERE ah.query_start_time > DATEADD(day, -7, CURRENT_TIMESTAMP())
      AND modified.value:objectName::STRING IN (
          SELECT src_database || '.' || src_schema || '.' || src_object FROM upstream_objects
      )
      AND qh.query_type IN ('INSERT', 'UPDATE', 'DELETE', 'MERGE', 'COPY')
)

SELECT
    object_name,
    change_type,
    change_time,
    change_detail,
    changed_by,
    DATEDIFF(hour, change_time, CURRENT_TIMESTAMP()) AS hours_ago
FROM (
    SELECT * FROM schema_changes
    UNION ALL
    SELECT * FROM column_changes WHERE change_time IS NOT NULL
    UNION ALL
    SELECT * FROM data_modifications
)
ORDER BY change_time DESC
LIMIT 20;
