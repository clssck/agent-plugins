-- Provenance Verification Fallback: OBJECT_DEPENDENCIES (when GET_LINEAGE returns no rows or privilege error)
-- Uses recursive OBJECT_DEPENDENCIES for full upstream chain. Replace <database>, <schema>, <table> before executing.

WITH RECURSIVE full_lineage AS (
    SELECT
        '<database>' AS obj_database,
        '<schema>' AS obj_schema,
        '<table>' AS obj_name,
        'TARGET' AS obj_type,
        0 AS level,
        'DOWNSTREAM' AS direction

    UNION ALL

    SELECT
        od.referenced_database,
        od.referenced_schema,
        od.referenced_object_name,
        od.referenced_object_domain,
        fl.level + 1,
        'UPSTREAM'
    FROM full_lineage fl
    JOIN SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES od
        ON od.referencing_database = fl.obj_database
        AND od.referencing_schema = fl.obj_schema
        AND od.referencing_object_name = fl.obj_name
    WHERE fl.level < 3
      AND fl.direction IN ('DOWNSTREAM', 'UPSTREAM')
      AND od.referenced_object_domain IN ('TABLE', 'VIEW', 'DYNAMIC TABLE', 'MATERIALIZED VIEW', 'STAGE')
),
object_metadata AS (
    SELECT
        table_catalog || '.' || table_schema || '.' || table_name AS object_name,
        table_type,
        table_schema,
        row_count,
        bytes,
        created,
        last_altered,
        table_owner
    FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
    WHERE deleted IS NULL
),
usage_stats AS (
    SELECT
        base.value:objectName::STRING AS object_name,
        COUNT(DISTINCT ah.user_name) AS unique_users_30d,
        COUNT(DISTINCT ah.query_id) AS query_count_30d
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
    LATERAL FLATTEN(input => ah.base_objects_accessed) AS base
    WHERE ah.query_start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
    GROUP BY 1
),
lineage_with_metadata AS (
    SELECT
        fl.level,
        fl.direction,
        fl.obj_database || '.' || fl.obj_schema || '.' || fl.obj_name AS object_name,
        fl.obj_type AS object_type,
        om.table_owner AS owner,
        om.last_altered,
        om.row_count,
        u.unique_users_30d,
        u.query_count_30d,
        /* SCHEMA_TRUST_TIER:fl.obj_schema */ AS trust_tier,
        CASE
            WHEN om.last_altered > DATEADD(day, -1, CURRENT_TIMESTAMP()) THEN 'FRESH'
            WHEN om.last_altered > DATEADD(day, -7, CURRENT_TIMESTAMP()) THEN 'RECENT'
            WHEN om.last_altered > DATEADD(day, -30, CURRENT_TIMESTAMP()) THEN 'STALE'
            ELSE 'VERY_STALE'
        END AS freshness_status,
        CASE
            WHEN COALESCE(u.unique_users_30d, 0) > 10 THEN 'HIGH_USAGE'
            WHEN COALESCE(u.unique_users_30d, 0) > 0 THEN 'ACTIVE'
            ELSE 'UNUSED'
        END AS usage_status
    FROM full_lineage fl
    LEFT JOIN object_metadata om ON om.object_name = fl.obj_database || '.' || fl.obj_schema || '.' || fl.obj_name
    LEFT JOIN usage_stats u ON u.object_name = fl.obj_database || '.' || fl.obj_schema || '.' || fl.obj_name
)
SELECT
    level,
    object_name,
    object_type,
    owner,
    trust_tier,
    freshness_status,
    usage_status,
    last_altered,
    row_count,
    unique_users_30d,
    query_count_30d,
    CASE
        WHEN trust_tier = 'PRODUCTION' AND freshness_status IN ('FRESH', 'RECENT') THEN '✅ VERIFIED'
        WHEN trust_tier = 'PRODUCTION' THEN '⚠️ VERIFY_FRESHNESS'
        WHEN trust_tier IN ('STAGING', 'RAW') THEN '⚠️ NON_PRODUCTION'
        WHEN trust_tier = 'DEVELOPMENT' THEN '❌ NOT_TRUSTED'
        ELSE '❓ UNKNOWN'
    END AS trust_status
FROM lineage_with_metadata
ORDER BY level, object_name;
