-- Root Cause Analysis: Upstream Lineage (Primary: GET_LINEAGE)
-- Uses SNOWFLAKE.CORE.GET_LINEAGE() for object + data-movement lineage (no account admin).
-- Replace <database>, <schema>, <table> with actual values BEFORE executing.
-- Use root-cause-analysis-object-deps-fallback.sql only if this query fails or object should have upstream sources but returned 0 rows.

WITH upstream_raw AS (
    -- OBJECT_CONSTRUCT(*) wraps each row as a VARIANT so we can reference v7-only columns
    -- without breaking on accounts where GET_LINEAGE returns the v3 schema. Missing keys
    -- yield NULL on extraction; works on any account version.
    SELECT OBJECT_CONSTRUCT(*) AS row_data
    FROM TABLE(SNOWFLAKE.CORE.GET_LINEAGE('<database>.<schema>.<table>', 'TABLE', 'UPSTREAM', 3))
),
upstream_edges AS (
    SELECT
        row_data:SOURCE_OBJECT_DATABASE::string AS src_database,
        row_data:SOURCE_OBJECT_SCHEMA::string   AS src_schema,
        row_data:SOURCE_OBJECT_NAME::string     AS src_object,
        row_data:SOURCE_OBJECT_DOMAIN::string   AS src_type,
        -- v7-only fields. NULL on v3, populated when Horizon Catalog connectors (Private Preview) are enabled.
        row_data:SOURCE_NAMESPACE::string       AS src_namespace,
        row_data:SOURCE_DATASET_TYPE::string    AS src_dataset_type,
        row_data:SOURCE_EXTERNAL_ID::string     AS src_external_id,
        row_data:DISTANCE::number               AS level
    FROM upstream_raw
    -- 'EXTERNAL' surfaces Horizon Catalog connectors (Private Preview) rows when the account has the feature enabled.
    WHERE row_data:SOURCE_OBJECT_DOMAIN::string IN (
        'TABLE', 'VIEW', 'DYNAMIC TABLE', 'MATERIALIZED VIEW', 'STAGE', 'STREAM', 'SEMANTIC_VIEW', 'EXTERNAL'
    )
),
upstream_lineage AS (
    SELECT
        src_database,
        src_schema,
        src_object,
        src_type,
        src_namespace,
        src_dataset_type,
        src_external_id,
        level,
        -- Native rows: 'DB.SCH.OBJ → target'. External rows: '[external] OBJ → target'.
        IFF(src_database IS NULL,
            '[external] ' || COALESCE(src_object, '<unnamed>'),
            src_database || '.' || src_schema || '.' || src_object
        ) || ' → <database>.<schema>.<table>' AS lineage_path
    FROM upstream_edges
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
    IFF(ul.src_database IS NULL, ul.src_object, ul.src_database || '.' || ul.src_schema || '.' || ul.src_object) AS source_object,
    ul.src_type AS object_type,
    -- External-row identifying fields. NULL for native rows; populated for external rows on PrPr accounts.
    ul.src_namespace,
    ul.src_dataset_type,
    ul.src_external_id,
    -- Native-only metadata; external rows return NULL via the LEFT JOIN.
    om.row_count,
    om.last_altered,
    om.table_owner AS owner,
    DATEDIFF(hour, om.last_altered, CURRENT_TIMESTAMP()) AS hours_since_modified,
    ul.lineage_path
FROM upstream_lineage ul
LEFT JOIN object_metadata om
    ON om.object_name = ul.src_database || '.' || ul.src_schema || '.' || ul.src_object
ORDER BY ul.level, CASE WHEN ul.src_type = 'EXTERNAL' THEN 2 ELSE 1 END, ul.src_database, ul.src_schema, ul.src_object;
