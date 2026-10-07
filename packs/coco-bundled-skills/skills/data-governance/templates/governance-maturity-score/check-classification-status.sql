-- ============================================================
-- CHECK 1: Classification profiles in the account
-- ============================================================
-- Lists all classification profiles. If no results, auto-classification
-- has not been configured.

SHOW SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE IN ACCOUNT;


-- ============================================================
-- CHECK 2: Databases actively monitored by auto-classification
-- ============================================================
-- Returns a JSON array of databases with a classification profile attached.
-- This is the definitive check for which databases are being auto-classified.

SELECT SYSTEM$SHOW_SENSITIVE_DATA_MONITORED_ENTITIES('DATABASE');


-- ============================================================
-- CHECK 3: Databases with classification results
-- ============================================================
-- Shows which databases have been classified (manually or automatically).
-- Uses SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST.

SELECT
    DATABASE_NAME,
    COUNT(DISTINCT TABLE_NAME) AS TABLES_CLASSIFIED,
    MAX(LAST_CLASSIFIED_ON) AS MOST_RECENT_CLASSIFICATION
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST
GROUP BY DATABASE_NAME
ORDER BY TABLES_CLASSIFIED DESC;


-- ============================================================
-- CHECK 4: Sensitive data categories detected
-- ============================================================
-- Parse the RESULT VARIANT column to extract per-column classifications
-- and summarize the types of sensitive data found across the account.

SELECT
    f.VALUE:recommendation:semantic_category::STRING AS SEMANTIC_CATEGORY,
    f.VALUE:recommendation:privacy_category::STRING AS PRIVACY_CATEGORY,
    f.VALUE:recommendation:confidence::STRING AS CONFIDENCE,
    COUNT(*) AS COLUMN_COUNT
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST,
     LATERAL FLATTEN(INPUT => RESULT) f
WHERE f.VALUE:recommendation:semantic_category IS NOT NULL
GROUP BY SEMANTIC_CATEGORY, PRIVACY_CATEGORY, CONFIDENCE
ORDER BY COLUMN_COUNT DESC
LIMIT 20;
