-- Column Lineage via GET_LINEAGE (Primary for column-level lineage)
-- Uses SNOWFLAKE.CORE.GET_LINEAGE() with the 'COLUMN' domain. Works for upstream and downstream
-- and does not depend on ACCESS_HISTORY (no 45min-3h latency). Requires only VIEW LINEAGE (PUBLIC).
--
-- Replace <database>, <schema>, <table>, <column>, <direction> BEFORE executing.
-- <direction> must be 'DOWNSTREAM' or 'UPSTREAM'.
--
-- Output columns (verbatim from SNOWFLAKE.CORE.GET_LINEAGE; do NOT alias as DOWNSTREAM_*/UPSTREAM_*):
--   SOURCE_OBJECT_DATABASE / SOURCE_OBJECT_SCHEMA / SOURCE_OBJECT_NAME / SOURCE_OBJECT_DOMAIN
--   SOURCE_COLUMN_NAME
--   TARGET_OBJECT_DATABASE / TARGET_OBJECT_SCHEMA / TARGET_OBJECT_NAME / TARGET_OBJECT_DOMAIN
--   TARGET_COLUMN_NAME
--   DISTANCE  (1 = direct, up to 5)
--   PROCESS   (VARIANT — query id / process that produced the edge)
--
-- Falls back to column-lineage-downstream.sql / column-lineage-upstream.sql (ACCESS_HISTORY based)
-- if GET_LINEAGE returns no rows or your role lacks VIEW LINEAGE.

SELECT
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
    '<direction>',
    1
))
ORDER BY DISTANCE, target_object, target_column;
