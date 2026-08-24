-- Root Cause Analysis Fallback: OBJECT_DEPENDENCIES (when GET_LINEAGE returns no rows or privilege error)
-- Uses SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES for recursive upstream (object dependency only; requires account admin).
-- Replace <database>, <schema>, <table> with actual values BEFORE executing.

WITH RECURSIVE upstream_lineage AS (
    SELECT
        '<database>' AS src_database,
        '<schema>' AS src_schema,
        '<table>' AS src_object,
        'TARGET' AS src_type,
        0 AS level,
        '<database>.<schema>.<table>' AS lineage_path

    UNION ALL

    SELECT
        od.referenced_database,
        od.referenced_schema,
        od.referenced_object_name,
        od.referenced_object_domain,
        ul.level + 1,
        od.referenced_database || '.' || od.referenced_schema || '.' || od.referenced_object_name || ' → ' || ul.lineage_path
    FROM upstream_lineage ul
    JOIN SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES od
        ON od.referencing_database = ul.src_database
        AND od.referencing_schema = ul.src_schema
        AND od.referencing_object_name = ul.src_object
    WHERE ul.level < 3
      AND od.referenced_object_domain IN ('TABLE', 'VIEW', 'DYNAMIC TABLE', 'MATERIALIZED VIEW', 'STAGE', 'STREAM')
),
object_metadata AS (
    SELECT
        table_catalog || '.' || table_schema || '.' || table_name AS object_name,
        table_type,
        row_count,
        bytes,
        created,
        last_altered,
        table_owner
    FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
    WHERE deleted IS NULL
)
SELECT
    ul.level,
    ul.src_database || '.' || ul.src_schema || '.' || ul.src_object AS source_object,
    ul.src_type AS object_type,
    om.row_count,
    om.last_altered,
    om.table_owner AS owner,
    DATEDIFF(hour, om.last_altered, CURRENT_TIMESTAMP()) AS hours_since_modified,
    ul.lineage_path
FROM upstream_lineage ul
LEFT JOIN object_metadata om
    ON om.object_name = ul.src_database || '.' || ul.src_schema || '.' || ul.src_object
WHERE ul.level > 0
ORDER BY ul.level, ul.src_database, ul.src_schema, ul.src_object;
