-- Impact Analysis: Downstream Dependencies with Risk Scoring (Primary: GET_LINEAGE)
-- Uses SNOWFLAKE.CORE.GET_LINEAGE() for object + data-movement lineage (no account admin).
-- Replace <database>, <schema>, <table> with actual values BEFORE executing.
-- Use impact-analysis-object-deps-fallback.sql only if this query fails (e.g. privilege error) or object should have dependents but returned 0 rows.

WITH lineage_raw AS (
    -- OBJECT_CONSTRUCT(*) wraps each row as a VARIANT so we can reference v7-only columns
    -- (TARGET_NAMESPACE, TARGET_DATASET_TYPE, TARGET_EXTERNAL_ID) without breaking on accounts
    -- where GET_LINEAGE returns the v3 schema (those keys simply don't exist in the variant;
    -- extraction yields NULL gracefully). This makes the template version-agnostic.
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
        row_data:DISTANCE::number               AS distance
    FROM lineage_raw
    -- 'EXTERNAL' surfaces Horizon Catalog connectors (Private Preview) rows when the account has the feature enabled.
    -- Without the feature, no 'EXTERNAL' rows are produced and this filter is a no-op for those accounts.
    WHERE row_data:TARGET_OBJECT_DOMAIN::string IN (
        'TABLE', 'VIEW', 'DYNAMIC TABLE', 'MATERIALIZED VIEW', 'SEMANTIC_VIEW', 'STAGE', 'EXTERNAL'
    )
),
downstream_deps AS (
    -- One row per distinct dependent (native or external) with min distance.
    -- Group by external fields too so distinct external entities (e.g. two Power BI reports
    -- with the same name in different connectors) don't collapse.
    SELECT
        dep_database,
        dep_schema,
        dep_object,
        dep_type,
        dep_namespace,
        dep_dataset_type,
        dep_external_id,
        MIN(distance) AS distance
    FROM parsed
    GROUP BY dep_database, dep_schema, dep_object, dep_type, dep_namespace, dep_dataset_type, dep_external_id
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
    -- For native rows: 'DB.SCHEMA.OBJECT'. For external rows (NULL db/schema): just the object name.
    IFF(d.dep_database IS NULL, d.dep_object, d.dep_database || '.' || d.dep_schema || '.' || d.dep_object) AS dependent_object,
    d.dep_type AS object_type,
    -- External-row identifying fields. NULL for native rows; populated for external rows on PrPr accounts.
    -- Per reference/external-row-output.md, present external entities under a separate header
    -- using dep_dataset_type (e.g. 'Power BI Report') and dep_namespace as the connector hint.
    d.dep_namespace,
    d.dep_dataset_type,
    d.dep_external_id,
    COALESCE(u.query_count_7d, 0) AS queries_last_7_days,
    COALESCE(u.unique_users_7d, 0) AS unique_users_7_days,
    u.last_accessed,
    0 AS downstream_dependents,
    CASE
        -- Don't apply Snowflake schema-pattern risk scoring to external rows; their schema is null.
        WHEN d.dep_type = 'EXTERNAL' THEN 'EXTERNAL'
        WHEN COALESCE(u.query_count_7d, 0) > 50 THEN 'CRITICAL'
        WHEN /* SCHEMA_RISK_SCORING:d.dep_schema */ IS NOT NULL THEN 'CRITICAL'
        WHEN d.dep_type = 'DYNAMIC TABLE' THEN 'CRITICAL'
        WHEN COALESCE(u.query_count_7d, 0) BETWEEN 10 AND 50 THEN 'MODERATE'
        ELSE 'LOW'
    END AS risk_level,
    d.distance,
    NULL AS dependency_type
FROM downstream_deps d
LEFT JOIN usage_stats u
    ON u.object_name = d.dep_database || '.' || d.dep_schema || '.' || d.dep_object
ORDER BY
    -- External rows last so they don't push native dependents off the screen.
    CASE WHEN d.dep_type = 'EXTERNAL' THEN 2 ELSE 1 END,
    CASE
        WHEN COALESCE(u.query_count_7d, 0) > 50 THEN 1
        WHEN COALESCE(u.query_count_7d, 0) BETWEEN 10 AND 50 THEN 2
        ELSE 3
    END,
    COALESCE(u.query_count_7d, 0) DESC;
