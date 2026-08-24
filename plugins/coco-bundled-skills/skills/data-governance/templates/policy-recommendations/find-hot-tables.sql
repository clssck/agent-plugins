-- ============================================================
-- HOT TABLES: table-level query volume (last 30 days)
-- ============================================================
-- Identifies the schemas with the highest query activity.
-- Scoped to assessed databases.

SELECT
    DATABASE_NAME,
    SCHEMA_NAME,
    COUNT(*)                        AS QUERY_COUNT,
    COUNT(DISTINCT USER_NAME)       AS DISTINCT_USERS,
    MAX(START_TIME)                 AS MOST_RECENT_QUERY
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME        >= DATEADD('day', -30, CURRENT_TIMESTAMP())
  AND DATABASE_NAME     IS NOT NULL
  AND SCHEMA_NAME       IS NOT NULL
  AND DATABASE_NAME     IN (<ASSESSED_DATABASES>)  -- Replace with user-confirmed database list
  AND EXECUTION_STATUS  = 'SUCCESS'
  AND QUERY_TYPE        NOT IN ('SHOW', 'DESCRIBE')
GROUP BY DATABASE_NAME, SCHEMA_NAME
ORDER BY QUERY_COUNT DESC
LIMIT 50;


-- ============================================================
-- HOT COLUMNS: column-level direct access (last 30 days)
-- ============================================================
-- Uses ACCESS_HISTORY.DIRECT_OBJECTS_ACCESSED to find the columns
-- accessed most often. Columns with high direct access and no policy
-- are the highest-priority targets.

WITH column_accesses AS (
    SELECT
        col.value:objectDomain::STRING                    AS OBJECT_DOMAIN,
        col.value:objectName::STRING                      AS FULL_OBJECT_NAME,
        cols.value:columnName::STRING                     AS COLUMN_NAME,
        ah.QUERY_ID,
        ah.USER_NAME,
        ah.QUERY_START_TIME
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
         LATERAL FLATTEN(INPUT => ah.DIRECT_OBJECTS_ACCESSED)        col,
         LATERAL FLATTEN(INPUT => col.value:columns, OUTER => TRUE)  cols
    WHERE ah.QUERY_START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
      AND col.value:objectDomain::STRING IN ('Table', 'View')
      AND SPLIT_PART(col.value:objectName::STRING, '.', 1)
          IN (<ASSESSED_DATABASES>)  -- Replace with user-confirmed database list
),
column_volume AS (
    SELECT
        SPLIT_PART(FULL_OBJECT_NAME, '.', 1)  AS DATABASE_NAME,
        SPLIT_PART(FULL_OBJECT_NAME, '.', 2)  AS SCHEMA_NAME,
        SPLIT_PART(FULL_OBJECT_NAME, '.', 3)  AS TABLE_NAME,
        COLUMN_NAME,
        COUNT(DISTINCT QUERY_ID)              AS QUERY_COUNT,
        COUNT(DISTINCT USER_NAME)             AS DISTINCT_USERS
    FROM column_accesses
    WHERE COLUMN_NAME IS NOT NULL
    GROUP BY DATABASE_NAME, SCHEMA_NAME, TABLE_NAME, COLUMN_NAME
)
SELECT
    cv.DATABASE_NAME,
    cv.SCHEMA_NAME,
    cv.TABLE_NAME,
    cv.COLUMN_NAME,
    cv.QUERY_COUNT,
    cv.DISTINCT_USERS,
    CASE WHEN pr.POLICY_NAME IS NOT NULL THEN 'PROTECTED' ELSE 'UNPROTECTED' END AS POLICY_STATUS,
    pr.POLICY_KIND
FROM column_volume cv
LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES pr
    ON  cv.DATABASE_NAME = pr.REF_DATABASE_NAME
    AND cv.SCHEMA_NAME   = pr.REF_SCHEMA_NAME
    AND cv.TABLE_NAME    = pr.REF_ENTITY_NAME
    AND cv.COLUMN_NAME   = pr.REF_COLUMN_NAME
    AND pr.POLICY_KIND   IN ('MASKING_POLICY', 'PROJECTION_POLICY')  -- column-level kinds
-- One row per column: a column protected by more than one policy kind would otherwise duplicate.
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY cv.DATABASE_NAME, cv.SCHEMA_NAME, cv.TABLE_NAME, cv.COLUMN_NAME
    ORDER BY pr.POLICY_KIND NULLS LAST
) = 1
ORDER BY cv.QUERY_COUNT DESC
LIMIT 100;
