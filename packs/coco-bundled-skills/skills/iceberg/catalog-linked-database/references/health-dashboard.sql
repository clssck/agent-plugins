-- ============================================================================
-- Catalog-Linked Database Health Dashboard
-- ============================================================================
-- Purpose: Comprehensive health check across all catalog-linked databases
-- Usage: Run this query to get a single-view health status of all CLDs
-- ============================================================================

-- Step 1: Get all catalog-linked databases
-- Tip: From the DATABASES view, check the TYPE column - CLDs show 'CATALOG-LINKED DATABASE'
--      (KIND column in SHOW DATABASES also shows 'CATALOG-LINKED DATABASE')

WITH cld_databases AS (
    SELECT 
        database_name,
        created,
        owner
    FROM SNOWFLAKE.INFORMATION_SCHEMA.DATABASES
    WHERE database_name IN (
        -- Filter by TYPE column to identify CLDs
        SELECT database_name 
        FROM SNOWFLAKE.INFORMATION_SCHEMA.DATABASES
        WHERE type = 'CATALOG-LINKED DATABASE'
    )
),

-- Step 2: Get table counts and auto-refresh status per database
-- Run SHOW ICEBERG TABLES for each database and aggregate

iceberg_table_status AS (
    SELECT
        database_name,
        schema_name,
        name AS table_name,
        auto_refresh_status,
        PARSE_JSON(auto_refresh_status):executionState::STRING AS execution_state,
        created_on
    FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
    -- Note: This CTE assumes you've run SHOW ICEBERG TABLES previously
    -- See alternative approach below
)

-- ============================================================================
-- ALTERNATIVE: Standalone Health Check Query
-- ============================================================================
-- Run this for a specific catalog-linked database:

-- Step A: Check catalog link status
SELECT 
    '<DATABASE_NAME>' AS database_name,
    SYSTEM$CATALOG_LINK_STATUS('<DATABASE_NAME>') AS link_status;

-- Step B: Get table health summary
SHOW ICEBERG TABLES IN DATABASE <DATABASE_NAME>;

-- Note: For CLD auto-discovered tables, empty auto_refresh_status is normal (healthy).
-- Auto-refresh is enabled by default; refresh frequency is controlled by
-- REFRESH_INTERVAL_SECONDS on the catalog integration.
SELECT
    '<DATABASE_NAME>' AS database_name,
    COUNT(*) AS total_tables,
    COUNT_IF("auto_refresh_status" IS NULL OR "auto_refresh_status" = '' 
             OR PARSE_JSON("auto_refresh_status"):executionState::STRING = 'RUNNING') AS healthy_tables,
    COUNT_IF(PARSE_JSON("auto_refresh_status"):executionState::STRING = 'STALLED') AS stalled_tables,
    COUNT_IF(PARSE_JSON("auto_refresh_status"):executionState::STRING = 'STOPPED') AS stopped_tables,
    COUNT_IF(PARSE_JSON("auto_refresh_status"):executionState::STRING = 'ICEBERG_TABLE_NOT_INITIALIZED') AS uninitialized_tables
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));

-- ============================================================================
-- COMPREHENSIVE HEALTH CHECK PROCEDURE
-- ============================================================================
-- For multiple CLDs, create a stored procedure:

/*
CREATE OR REPLACE PROCEDURE CHECK_CLD_HEALTH()
RETURNS TABLE (
    database_name STRING,
    sync_status STRING,
    last_sync TIMESTAMP,
    total_schemas INT,
    total_tables INT,
    healthy_tables INT,
    problem_tables INT
)
LANGUAGE SQL
AS
$$
DECLARE
    result RESULTSET;
BEGIN
    -- Implementation would iterate through CLDs
    -- and aggregate health metrics
    RETURN result;
END;
$$;
*/

-- ============================================================================
-- QUICK HEALTH CHECK QUERIES
-- ============================================================================

-- 1. Check sync status for a specific CLD
SELECT SYSTEM$CATALOG_LINK_STATUS('<DATABASE_NAME>');

-- 2. List all schemas in CLD
SHOW SCHEMAS IN DATABASE <DATABASE_NAME>;

-- 3. Find tables with auto-refresh issues
-- Note: Empty auto_refresh_status is normal for healthy CLD tables
SHOW ICEBERG TABLES IN DATABASE <DATABASE_NAME>;
SELECT 
    "database_name",
    "schema_name", 
    "name" AS table_name,
    PARSE_JSON("auto_refresh_status"):executionState::STRING AS status,
    PARSE_JSON("auto_refresh_status"):lastRefreshTimestamp::TIMESTAMP AS last_refresh
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "auto_refresh_status" IS NOT NULL 
  AND "auto_refresh_status" != ''
  AND PARSE_JSON("auto_refresh_status"):executionState::STRING NOT IN ('RUNNING')
ORDER BY last_refresh ASC;

-- 4. Find stale tables (not refreshed in last hour)
SHOW ICEBERG TABLES IN DATABASE <DATABASE_NAME>;
SELECT 
    "database_name",
    "schema_name",
    "name" AS table_name,
    PARSE_JSON("auto_refresh_status"):lastRefreshTimestamp::TIMESTAMP AS last_refresh,
    DATEDIFF('minute', last_refresh, CURRENT_TIMESTAMP()) AS minutes_since_refresh
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE PARSE_JSON("auto_refresh_status"):lastRefreshTimestamp::TIMESTAMP < DATEADD('hour', -1, CURRENT_TIMESTAMP())
ORDER BY last_refresh ASC;

-- 5. Detailed status for a specific table
SELECT SYSTEM$AUTO_REFRESH_STATUS('<DATABASE>.<SCHEMA>.<TABLE>');

-- ============================================================================
-- MONITORING QUERIES (Event Table - if configured)
-- ============================================================================

-- Find recent auto-refresh errors (requires event table)
/*
SELECT 
    timestamp,
    resource_attributes:"snow.database.name"::STRING AS database_name,
    resource_attributes:"snow.schema.name"::STRING AS schema_name,
    resource_attributes:"snow.table.name"::STRING AS table_name,
    record:"severity_text"::STRING AS severity,
    PARSE_JSON(value):snapshot_state::STRING AS snapshot_state,
    PARSE_JSON(value):error_message::STRING AS error_message
FROM <YOUR_EVENT_TABLE>
WHERE record:"name" = 'iceberg_auto_refresh_snapshot_lifecycle'
  AND record:"severity_text" IN ('ERROR', 'WARN')
  AND timestamp > DATEADD('day', -1, CURRENT_TIMESTAMP())
ORDER BY timestamp DESC
LIMIT 100;
*/

-- ============================================================================
-- USAGE NOTES
-- ============================================================================
-- 
-- 1. Replace <DATABASE_NAME> with your actual CLD name
-- 2. Replace <YOUR_EVENT_TABLE> with your account's event table
-- 3. For production monitoring, consider:
--    - Creating a scheduled task to run health checks
--    - Setting up alerts for FAILING or STALLED tables
--    - Using the CATALOG_LINKED_DATABASE_USAGE_HISTORY view for cost tracking
--
-- Documentation:
-- - https://docs.snowflake.com/en/user-guide/tables-iceberg-catalog-linked-database
-- - https://docs.snowflake.com/en/user-guide/tables-iceberg-auto-refresh
-- ============================================================================
