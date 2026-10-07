-- Impact Analysis Multi-Level Fallback: OBJECT_DEPENDENCIES (when GET_LINEAGE returns no rows or privilege error)
-- Replace <database>, <schema>, <table> with actual values BEFORE executing.

WITH RECURSIVE dependency_tree AS (
    SELECT
        '<database>' AS dep_database,
        '<schema>' AS dep_schema,
        '<table>' AS dep_object,
        'SOURCE' AS dep_type,
        0 AS level,
        '<database>.<schema>.<table>' AS lineage_path

    UNION ALL

    SELECT
        od.referencing_database,
        od.referencing_schema,
        od.referencing_object_name,
        od.referencing_object_domain,
        dt.level + 1,
        dt.lineage_path || ' → ' || od.referencing_database || '.' || od.referencing_schema || '.' || od.referencing_object_name
    FROM dependency_tree dt
    JOIN SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES od
        ON od.referenced_database = dt.dep_database
        AND od.referenced_schema = dt.dep_schema
        AND od.referenced_object_name = dt.dep_object
    WHERE dt.level < 2
      AND od.referencing_object_domain IN ('TABLE', 'VIEW', 'DYNAMIC TABLE', 'MATERIALIZED VIEW', 'PROCEDURE', 'TASK')
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
    dt.dep_database || '.' || dt.dep_schema || '.' || dt.dep_object AS dependent_object,
    dt.dep_type AS object_type,
    COALESCE(u.query_count_7d, 0) AS queries_last_7_days,
    COALESCE(u.unique_users_7d, 0) AS unique_users_7_days,
    u.last_accessed,
    CASE
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
ORDER BY dt.level, risk_level, COALESCE(u.query_count_7d, 0) DESC;
