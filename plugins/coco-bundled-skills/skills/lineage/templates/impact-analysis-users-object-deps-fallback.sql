-- Impact Analysis Users Fallback: OBJECT_DEPENDENCIES (when GET_LINEAGE returns no rows or privilege error)
-- Replace <database>, <schema>, <table> with actual values BEFORE executing.

WITH downstream_deps AS (
    SELECT
        od.referencing_database || '.' || od.referencing_schema || '.' || od.referencing_object_name AS dependent_object,
        od.referencing_object_domain AS object_type
    FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES od
    WHERE od.referenced_database = '<database>'
      AND od.referenced_schema = '<schema>'
      AND od.referenced_object_name = '<table>'
),
affected_users AS (
    SELECT
        ah.user_name,
        base.value:objectName::STRING AS accessed_object,
        COUNT(DISTINCT ah.query_id) AS query_count,
        MAX(ah.query_start_time) AS last_access
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
    LATERAL FLATTEN(input => ah.base_objects_accessed) AS base
    WHERE ah.query_start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
      AND base.value:objectName::STRING IN (SELECT dependent_object FROM downstream_deps)
    GROUP BY 1, 2
)
SELECT
    user_name,
    accessed_object,
    query_count AS queries_last_7_days,
    last_access,
    d.object_type
FROM affected_users au
JOIN downstream_deps d ON au.accessed_object = d.dependent_object
ORDER BY query_count DESC, last_access DESC;
