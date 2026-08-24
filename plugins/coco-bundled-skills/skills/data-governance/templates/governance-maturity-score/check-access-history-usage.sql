-- ============================================================
-- CHECK 1: Has ACCESS_HISTORY been queried recently?
-- ============================================================
-- Looks for queries against ACCESS_HISTORY in the last 90 days.
-- Regular querying indicates the account is actively auditing access.

SELECT
    USER_NAME,
    COUNT(*) AS QUERY_COUNT,
    MAX(START_TIME) AS LAST_QUERIED,
    MIN(START_TIME) AS FIRST_QUERIED
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME >= DATEADD('day', -90, CURRENT_TIMESTAMP())
  AND QUERY_TEXT ILIKE '%ACCESS_HISTORY%'
  AND EXECUTION_STATUS = 'SUCCESS'
GROUP BY USER_NAME
ORDER BY LAST_QUERIED DESC
LIMIT 20;


-- ============================================================
-- CHECK 2: Frequency of ACCESS_HISTORY queries by week
-- ============================================================
-- Shows how consistently ACCESS_HISTORY is being audited.

SELECT
    DATE_TRUNC('week', START_TIME) AS WEEK_START,
    COUNT(*) AS QUERY_COUNT,
    COUNT(DISTINCT USER_NAME) AS DISTINCT_USERS
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
  AND QUERY_TEXT ILIKE '%ACCESS_HISTORY%'
  AND EXECUTION_STATUS = 'SUCCESS'
GROUP BY DATE_TRUNC('week', START_TIME)
ORDER BY WEEK_START DESC
LIMIT 10;
