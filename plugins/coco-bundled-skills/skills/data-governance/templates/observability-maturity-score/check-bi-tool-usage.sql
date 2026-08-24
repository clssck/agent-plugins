-- ============================================================
-- CHECK BI TOOL USAGE
-- Detect BI tool queries and assess quality monitoring on
-- tables/views consumed by dashboards (PowerBI, Tableau, etc.)
-- ============================================================

-- Check 1: Detect BI tools from QUERY_HISTORY (last 90 days)
-- Uses query_tag, user_name, warehouse_name, and role_name patterns
SELECT
    CASE
        WHEN UPPER(query_tag) LIKE '%POWERBI%' OR UPPER(query_tag) LIKE '%POWER BI%'
             OR UPPER(user_name) LIKE '%POWERBI%' OR UPPER(user_name) LIKE '%PBI%'
             OR UPPER(warehouse_name) LIKE '%POWERBI%' OR UPPER(warehouse_name) LIKE '%PBI%'
             OR UPPER(role_name) LIKE '%POWERBI%' OR UPPER(role_name) LIKE '%PBI%'
            THEN 'PowerBI'
        WHEN UPPER(query_tag) LIKE '%TABLEAU%'
             OR UPPER(user_name) LIKE '%TABLEAU%'
             OR UPPER(warehouse_name) LIKE '%TABLEAU%'
             OR UPPER(role_name) LIKE '%TABLEAU%'
            THEN 'Tableau'
        WHEN UPPER(query_tag) LIKE '%LOOKER%'
             OR UPPER(user_name) LIKE '%LOOKER%'
             OR UPPER(warehouse_name) LIKE '%LOOKER%'
             OR UPPER(role_name) LIKE '%LOOKER%'
            THEN 'Looker'
        WHEN TRY_PARSE_JSON(query_tag):dbt_version IS NOT NULL
            THEN 'dbt'
        ELSE 'Unknown'
    END AS bi_tool,
    COUNT(*) AS query_count,
    COUNT(DISTINCT user_name) AS distinct_users,
    COUNT(DISTINCT database_name) AS distinct_databases
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE start_time >= DATEADD('day', -90, CURRENT_TIMESTAMP())
  AND execution_status = 'SUCCESS'
  AND (
      -- PowerBI patterns
      UPPER(query_tag) LIKE '%POWERBI%' OR UPPER(query_tag) LIKE '%POWER BI%'
      OR UPPER(user_name) LIKE '%POWERBI%' OR UPPER(user_name) LIKE '%PBI%'
      OR UPPER(warehouse_name) LIKE '%POWERBI%' OR UPPER(warehouse_name) LIKE '%PBI%'
      OR UPPER(role_name) LIKE '%POWERBI%' OR UPPER(role_name) LIKE '%PBI%'
      -- Tableau patterns
      OR UPPER(query_tag) LIKE '%TABLEAU%'
      OR UPPER(user_name) LIKE '%TABLEAU%'
      OR UPPER(warehouse_name) LIKE '%TABLEAU%'
      OR UPPER(role_name) LIKE '%TABLEAU%'
      -- Looker patterns
      OR UPPER(query_tag) LIKE '%LOOKER%'
      OR UPPER(user_name) LIKE '%LOOKER%'
      OR UPPER(warehouse_name) LIKE '%LOOKER%'
      OR UPPER(role_name) LIKE '%LOOKER%'
      -- dbt patterns (JSON query tag with dbt_version)
      OR TRY_PARSE_JSON(query_tag):dbt_version IS NOT NULL
  )
GROUP BY 1
ORDER BY query_count DESC;

-- Check 2: Databases consumed by BI tools
-- Shows which databases are queried by BI tools
SELECT
    database_name,
    CASE
        WHEN UPPER(query_tag) LIKE '%POWERBI%' OR UPPER(query_tag) LIKE '%POWER BI%'
             OR UPPER(user_name) LIKE '%POWERBI%' OR UPPER(user_name) LIKE '%PBI%'
             OR UPPER(warehouse_name) LIKE '%POWERBI%' OR UPPER(warehouse_name) LIKE '%PBI%'
             OR UPPER(role_name) LIKE '%POWERBI%' OR UPPER(role_name) LIKE '%PBI%'
            THEN 'PowerBI'
        WHEN UPPER(query_tag) LIKE '%TABLEAU%'
             OR UPPER(user_name) LIKE '%TABLEAU%'
             OR UPPER(warehouse_name) LIKE '%TABLEAU%'
             OR UPPER(role_name) LIKE '%TABLEAU%'
            THEN 'Tableau'
        WHEN UPPER(query_tag) LIKE '%LOOKER%'
             OR UPPER(user_name) LIKE '%LOOKER%'
             OR UPPER(warehouse_name) LIKE '%LOOKER%'
             OR UPPER(role_name) LIKE '%LOOKER%'
            THEN 'Looker'
        ELSE 'Other BI'
    END AS bi_tool,
    COUNT(*) AS query_count
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE start_time >= DATEADD('day', -90, CURRENT_TIMESTAMP())
  AND execution_status = 'SUCCESS'
  AND database_name IS NOT NULL
  AND database_name NOT IN ('SNOWFLAKE', 'SNOWFLAKE_SAMPLE_DATA')
  AND (
      UPPER(query_tag) LIKE '%POWERBI%' OR UPPER(query_tag) LIKE '%POWER BI%'
      OR UPPER(user_name) LIKE '%POWERBI%' OR UPPER(user_name) LIKE '%PBI%'
      OR UPPER(warehouse_name) LIKE '%POWERBI%' OR UPPER(warehouse_name) LIKE '%PBI%'
      OR UPPER(role_name) LIKE '%POWERBI%' OR UPPER(role_name) LIKE '%PBI%'
      OR UPPER(query_tag) LIKE '%TABLEAU%'
      OR UPPER(user_name) LIKE '%TABLEAU%'
      OR UPPER(warehouse_name) LIKE '%TABLEAU%'
      OR UPPER(role_name) LIKE '%TABLEAU%'
      OR UPPER(query_tag) LIKE '%LOOKER%'
      OR UPPER(user_name) LIKE '%LOOKER%'
      OR UPPER(warehouse_name) LIKE '%LOOKER%'
      OR UPPER(role_name) LIKE '%LOOKER%'
  )
GROUP BY 1, 2
ORDER BY query_count DESC;

-- Check 3: Cross-reference BI-consumed databases with DMF coverage
-- Identifies BI databases that lack quality monitoring
WITH bi_databases AS (
    SELECT DISTINCT database_name
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    WHERE start_time >= DATEADD('day', -90, CURRENT_TIMESTAMP())
      AND execution_status = 'SUCCESS'
      AND database_name IS NOT NULL
      AND database_name NOT IN ('SNOWFLAKE', 'SNOWFLAKE_SAMPLE_DATA')
      AND (
          UPPER(query_tag) LIKE '%POWERBI%' OR UPPER(query_tag) LIKE '%POWER BI%'
          OR UPPER(user_name) LIKE '%POWERBI%' OR UPPER(user_name) LIKE '%PBI%'
          OR UPPER(warehouse_name) LIKE '%POWERBI%' OR UPPER(warehouse_name) LIKE '%PBI%'
          OR UPPER(role_name) LIKE '%POWERBI%' OR UPPER(role_name) LIKE '%PBI%'
          OR UPPER(query_tag) LIKE '%TABLEAU%'
          OR UPPER(user_name) LIKE '%TABLEAU%'
          OR UPPER(warehouse_name) LIKE '%TABLEAU%'
          OR UPPER(role_name) LIKE '%TABLEAU%'
          OR UPPER(query_tag) LIKE '%LOOKER%'
          OR UPPER(user_name) LIKE '%LOOKER%'
          OR UPPER(warehouse_name) LIKE '%LOOKER%'
          OR UPPER(role_name) LIKE '%LOOKER%'
      )
),
dmf_databases AS (
    SELECT DISTINCT ref_database_name AS database_name
    FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_METRIC_FUNCTION_REFERENCES
    WHERE deleted IS NULL
)
SELECT
    b.database_name,
    CASE WHEN d.database_name IS NOT NULL THEN 'YES' ELSE 'NO' END AS has_dmf_coverage
FROM bi_databases b
LEFT JOIN dmf_databases d ON b.database_name = d.database_name
ORDER BY has_dmf_coverage, b.database_name;
