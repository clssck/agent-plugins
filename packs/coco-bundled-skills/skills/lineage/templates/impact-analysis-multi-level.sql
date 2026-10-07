-- Impact Analysis: Multi-Level Downstream (Primary: GET_LINEAGE)
-- Uses SNOWFLAKE.CORE.GET_LINEAGE() with distance for cascade. Replace <database>, <schema>, <table> before executing.
-- Use impact-analysis-multi-level-object-deps-fallback.sql only if this query fails or object should have dependents but returned 0 rows.

WITH lineage_raw AS (
    -- OBJECT_CONSTRUCT(*) wraps each row as a VARIANT so we can reference v7-only columns
    -- without breaking on accounts where GET_LINEAGE returns the v3 schema. Missing keys
    -- yield NULL on extraction; works on any account version.
    SELECT OBJECT_CONSTRUCT(*) AS row_data
    FROM TABLE(SNOWFLAKE.CORE.GET_LINEAGE('<database>.<schema>.<table>', 'TABLE', 'DOWNSTREAM', 3))
),
parsed AS (
    SELECT
        row_data:TARGET_OBJECT_DATABASE::string AS dep_database,
        row_data:TARGET_OBJECT_SCHEMA::string   AS dep_schema,
        row_data:TARGET_OBJECT_NAME::string     AS dep_object,
        row_data:TARGET_OBJECT_DOMAIN::string   AS dep_type,
        -- v7-only fields. NULL on v3, populated when Horizon Catalog connectors (Private Preview) are enabled.
        row_data:TARGET_NAMESPACE::string       AS dep_namespace,
        row_data:TARGET_DATASET_TYPE::string    AS dep_dataset_type,
        row_data:TARGET_EXTERNAL_ID::string     AS dep_external_id,
        row_data:DISTANCE::number               AS level
    FROM lineage_raw
    -- 'EXTERNAL' surfaces Horizon Catalog connectors (Private Preview) rows when the account has the feature enabled.
    WHERE row_data:TARGET_OBJECT_DOMAIN::string IN (
        'TABLE', 'VIEW', 'DYNAMIC TABLE', 'MATERIALIZED VIEW', 'SEMANTIC_VIEW', 'STAGE', 'EXTERNAL'
    )
),
dependency_tree AS (
    SELECT
        dep_database,
        dep_schema,
        dep_object,
        dep_type,
        dep_namespace,
        dep_dataset_type,
        dep_external_id,
        level,
        '<database>.<schema>.<table>'
            || REPEAT(' → ... ', level - 1)
            || ' → '
            -- Native rows show 'DB.SCH.OBJ'; external rows (NULL db/schema) show '[external] OBJ'
            || IFF(dep_database IS NULL,
                   '[external] ' || COALESCE(dep_object, '<unnamed>'),
                   dep_database || '.' || dep_schema || '.' || dep_object) AS lineage_path
    FROM parsed
    WHERE level BETWEEN 1 AND 2
),
usage_stats AS (
    SELECT
        base.value:objectName::STRING AS object_name,
        COUNT(DISTINCT ah.query_id) AS query_count_7d,
        COUNT(DISTINCT ah.user_name) AS unique_users_7d,
        MAX(ah.query_start_time) AS last_accessed
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
    LATERAL FLATTEN(input => ah.base_objects_accessed) AS base
    WHERE ah.query_start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
    GROUP BY 1
)
SELECT
    dt.level,
    IFF(dt.dep_database IS NULL, dt.dep_object, dt.dep_database || '.' || dt.dep_schema || '.' || dt.dep_object) AS dependent_object,
    dt.dep_type AS object_type,
    -- External-row identifying fields.
    dt.dep_namespace,
    dt.dep_dataset_type,
    dt.dep_external_id,
    COALESCE(u.query_count_7d, 0) AS queries_last_7_days,
    COALESCE(u.unique_users_7d, 0) AS unique_users_7_days,
    u.last_accessed,
    CASE
        WHEN dt.dep_type = 'EXTERNAL' THEN 'EXTERNAL'
        WHEN COALESCE(u.query_count_7d, 0) > 50 THEN 'CRITICAL'
        WHEN /* SCHEMA_RISK_SCORING:dt.dep_schema */ IS NOT NULL THEN 'CRITICAL'
        WHEN dt.dep_type = 'DYNAMIC TABLE' THEN 'CRITICAL'
        WHEN COALESCE(u.query_count_7d, 0) BETWEEN 10 AND 50 THEN 'MODERATE'
        ELSE 'LOW'
    END AS risk_level,
    dt.lineage_path
FROM dependency_tree dt
LEFT JOIN usage_stats u ON u.object_name = dt.dep_database || '.' || dt.dep_schema || '.' || dt.dep_object
WHERE dt.level > 0
ORDER BY dt.level, CASE WHEN dt.dep_type = 'EXTERNAL' THEN 2 ELSE 1 END, risk_level, COALESCE(u.query_count_7d, 0) DESC;
