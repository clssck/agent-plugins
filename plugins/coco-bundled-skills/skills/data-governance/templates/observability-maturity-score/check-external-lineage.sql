-- ============================================================
-- CHECK EXTERNAL LINEAGE
-- Assess whether lineage from upstream tools (dbt, Airflow,
-- Spark) is being ingested into Snowflake via OpenLineage
-- Uses ACCOUNT_USAGE only (no SHOW GRANTS) for automation compatibility.
-- ============================================================

-- Check 1: Check if INGEST LINEAGE privilege is granted to any role
-- Query ACCOUNT_USAGE.GRANTS_TO_ROLES (avoids SHOW GRANTS; single-statement, lower privilege)
SELECT
    grantee_name AS role_name,
    privilege,
    granted_on,
    granted_by,
    created_on
FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
WHERE privilege = 'INGEST LINEAGE'
  AND deleted_on IS NULL;

-- Check 2: Check for external lineage API usage in QUERY_HISTORY
-- Look for REST API calls or references to external lineage
-- Note: External lineage is ingested via REST API, not SQL, so we
-- check for indirect signals: queries mentioning lineage endpoints,
-- or the presence of external nodes in lineage metadata
SELECT
    COUNT(*) AS lineage_related_queries,
    COUNT(DISTINCT user_name) AS distinct_users,
    MIN(start_time) AS first_seen,
    MAX(start_time) AS last_seen
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE start_time >= DATEADD('day', -90, CURRENT_TIMESTAMP())
  AND execution_status = 'SUCCESS'
  AND (
      LOWER(query_text) LIKE '%external%lineage%'
      OR LOWER(query_text) LIKE '%openlineage%'
      OR LOWER(query_text) LIKE '%ingest lineage%'
      OR LOWER(query_text) LIKE '%ingest_lineage%'
  );

-- Check 3: Detect dbt usage patterns
-- dbt sets structured JSON query tags with dbt_version, node_id, etc.
SELECT
    'dbt' AS tool,
    COUNT(*) AS query_count,
    COUNT(DISTINCT user_name) AS distinct_users,
    COUNT(DISTINCT database_name) AS databases_touched,
    MIN(start_time) AS first_seen,
    MAX(start_time) AS last_seen
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE start_time >= DATEADD('day', -90, CURRENT_TIMESTAMP())
  AND execution_status = 'SUCCESS'
  AND TRY_PARSE_JSON(query_tag):dbt_version IS NOT NULL;

-- Check 4: Detect Airflow usage patterns
-- Airflow typically uses dedicated users, warehouses, or query tags
SELECT
    'Airflow' AS tool,
    COUNT(*) AS query_count,
    COUNT(DISTINCT user_name) AS distinct_users,
    COUNT(DISTINCT database_name) AS databases_touched,
    MIN(start_time) AS first_seen,
    MAX(start_time) AS last_seen
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE start_time >= DATEADD('day', -90, CURRENT_TIMESTAMP())
  AND execution_status = 'SUCCESS'
  AND (
      UPPER(user_name) LIKE '%AIRFLOW%'
      OR UPPER(warehouse_name) LIKE '%AIRFLOW%'
      OR UPPER(role_name) LIKE '%AIRFLOW%'
      OR UPPER(query_tag) LIKE '%AIRFLOW%'
      OR UPPER(query_tag) LIKE '%DAG%'
  );

-- Check 5: Check for DELETE LINEAGE privilege (indicates active lineage management)
SELECT
    grantee_name AS role_name,
    privilege,
    granted_on,
    granted_by,
    created_on
FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
WHERE privilege = 'DELETE LINEAGE'
  AND deleted_on IS NULL;
