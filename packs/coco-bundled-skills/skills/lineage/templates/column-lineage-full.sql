-- Column Lineage: Full Path Tracing (Upstream + Downstream)
-- Uses SNOWFLAKE.CORE.GET_LINEAGE() with the 'COLUMN' domain.
-- No ACCESS_HISTORY latency. Requires only VIEW LINEAGE (PUBLIC).
--
-- Replace <database>, <schema>, <table>, <column> BEFORE executing.
--
-- Selected output columns (see reference/snowflake-apis.md for the full GET_LINEAGE schema):
--   direction (added), DISTANCE,
--   source_object (concatenated), source_object_type, source_column,
--   target_object (concatenated), target_object_type, target_column
-- Note: PROCESS (VARIANT — query id / edge source) is available from GET_LINEAGE but omitted here.

SELECT
    'UPSTREAM' AS direction,
    DISTANCE,
    SOURCE_OBJECT_DATABASE || '.' || SOURCE_OBJECT_SCHEMA || '.' || SOURCE_OBJECT_NAME AS source_object,
    SOURCE_OBJECT_DOMAIN AS source_object_type,
    SOURCE_COLUMN_NAME   AS source_column,
    TARGET_OBJECT_DATABASE || '.' || TARGET_OBJECT_SCHEMA || '.' || TARGET_OBJECT_NAME AS target_object,
    TARGET_OBJECT_DOMAIN AS target_object_type,
    TARGET_COLUMN_NAME   AS target_column
FROM TABLE(SNOWFLAKE.CORE.GET_LINEAGE(
    '<database>.<schema>.<table>.<column>',
    'COLUMN',
    'UPSTREAM',
    1
))

UNION ALL

SELECT
    'DOWNSTREAM' AS direction,
    DISTANCE,
    SOURCE_OBJECT_DATABASE || '.' || SOURCE_OBJECT_SCHEMA || '.' || SOURCE_OBJECT_NAME AS source_object,
    SOURCE_OBJECT_DOMAIN AS source_object_type,
    SOURCE_COLUMN_NAME   AS source_column,
    TARGET_OBJECT_DATABASE || '.' || TARGET_OBJECT_SCHEMA || '.' || TARGET_OBJECT_NAME AS target_object,
    TARGET_OBJECT_DOMAIN AS target_object_type,
    TARGET_COLUMN_NAME   AS target_column
FROM TABLE(SNOWFLAKE.CORE.GET_LINEAGE(
    '<database>.<schema>.<table>.<column>',
    'COLUMN',
    'DOWNSTREAM',
    1
))

ORDER BY direction, DISTANCE, target_object, target_column;
