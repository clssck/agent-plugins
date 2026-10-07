-- Check ACCESS_HISTORY Availability
-- Verify ACCESS_HISTORY has data for the target object
-- Replace <database>, <schema>, <table> with actual values BEFORE executing

-- Check if there's any access history for this object
SELECT 
    COUNT(*) AS total_access_records,
    MIN(query_start_time) AS earliest_access,
    MAX(query_start_time) AS latest_access,
    COUNT(DISTINCT query_id) AS unique_queries,
    COUNT(DISTINCT user_name) AS unique_users
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY,
LATERAL FLATTEN(input => base_objects_accessed) AS base
WHERE base.value:objectName::STRING = '<database>.<schema>.<table>'
  AND query_start_time >= DATEADD(day, -365, CURRENT_TIMESTAMP());
