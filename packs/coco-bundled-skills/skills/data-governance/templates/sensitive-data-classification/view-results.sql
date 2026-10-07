-- View Classification Results
-- Query the ACCOUNT_USAGE views for classification data
--
-- This template provides SQL queries to analyze classification results stored in
-- SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST

-- =============================================================================
-- DATA_CLASSIFICATION_LATEST Schema Reference
-- =============================================================================
-- This view contains the latest classification results for all tables.
-- 
-- Columns:
--   DATABASE_NAME       - Database containing the classified table
--   SCHEMA_NAME         - Schema containing the classified table
--   TABLE_NAME          - Name of the classified table
--   TABLE_ID            - Internal identifier for the table
--   STATUS              - Classification status (CLASSIFIED, REVIEWED)
--   TRIGGER_TYPE        - How classification was triggered (MANUAL)
--   LAST_CLASSIFIED_ON  - Timestamp when classification was last run
--   RESULT              - JSON containing classification details per column:
--                         {
--                           "COLUMN_NAME": {
--                             "alternates": [],
--                             "recommendation": {
--                               "confidence": "HIGH|MEDIUM|LOW",
--                               "coverage": 0.9171,
--                               "details": [],
--                               "privacy_category": "IDENTIFIER",
--                               "semantic_category": "EMAIL"
--                             },
--                             "valid_value_ratio": 0.9171
--                           },
--                           "ANOTHER_COLUMN": { ... }
--                         }
--
-- =============================================================================

-- =============================================================================
-- BASIC QUERIES
-- =============================================================================

-- Latest classification results for a specific database
SELECT 
    DATABASE_NAME,
    SCHEMA_NAME,
    TABLE_NAME,
    STATUS,
    RESULT,
    LAST_CLASSIFIED_ON
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST
WHERE DATABASE_NAME = '<database>'
ORDER BY LAST_CLASSIFIED_ON DESC;

-- Count tables by classification status
SELECT
    STATUS,
    COUNT(DISTINCT TABLE_ID) AS table_count
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST
GROUP BY STATUS
ORDER BY table_count DESC;

-- Recently classified tables (last 30 days)
SELECT
    DATABASE_NAME,
    SCHEMA_NAME,
    TABLE_NAME,
    LAST_CLASSIFIED_ON
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST
WHERE LAST_CLASSIFIED_ON >= DATEADD(DAY, -30, CURRENT_TIMESTAMP())
ORDER BY LAST_CLASSIFIED_ON DESC;

-- Database with most classified tables
SELECT
    DATABASE_NAME,
    COUNT(DISTINCT TABLE_ID) AS table_count
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST
GROUP BY DATABASE_NAME
ORDER BY table_count DESC
LIMIT 10;

-- Tables that need re-classification (>90 days old)
SELECT
    DATABASE_NAME,
    SCHEMA_NAME,
    TABLE_NAME,
    LAST_CLASSIFIED_ON,
    DATEDIFF(DAY, LAST_CLASSIFIED_ON, CURRENT_TIMESTAMP()) AS days_since_classification
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST
WHERE DATEDIFF(DAY, LAST_CLASSIFIED_ON, CURRENT_TIMESTAMP()) > 90
ORDER BY days_since_classification DESC;

-- =============================================================================
-- PARSING CLASSIFICATION RESULTS (using LATERAL FLATTEN)
-- =============================================================================

-- Extract and count semantic categories across all tables
WITH base_classification AS (
    SELECT
        DATABASE_NAME,
        SCHEMA_NAME,
        TABLE_NAME,
        RESULT
    FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST
),
column_categories AS (
    SELECT
        f.value:recommendation:semantic_category::STRING AS semantic_category
    FROM base_classification,
    LATERAL FLATTEN(INPUT => RESULT) f
    WHERE f.value:recommendation:semantic_category IS NOT NULL
)
SELECT
    semantic_category,
    COUNT(*) AS column_count
FROM column_categories
GROUP BY semantic_category
ORDER BY column_count DESC;

-- Extract columns with HIGH confidence classifications
WITH base_classification AS (
    SELECT
        DATABASE_NAME,
        SCHEMA_NAME,
        TABLE_NAME,
        RESULT
    FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST
)
SELECT
    DATABASE_NAME,
    SCHEMA_NAME,
    TABLE_NAME,
    f.KEY AS column_name,
    f.VALUE:recommendation:semantic_category::STRING AS semantic_category,
    f.VALUE:recommendation:privacy_category::STRING AS privacy_category,
    f.VALUE:recommendation:confidence::STRING AS confidence
FROM base_classification,
LATERAL FLATTEN(INPUT => RESULT) f
WHERE f.VALUE:recommendation:confidence::STRING = 'HIGH'
ORDER BY DATABASE_NAME, SCHEMA_NAME, TABLE_NAME, column_name;

-- Extract individual column classifications for a specific database
SELECT 
    DATABASE_NAME,
    SCHEMA_NAME,
    TABLE_NAME,
    f.KEY AS column_name,
    f.VALUE:recommendation:semantic_category::STRING AS semantic_category,
    f.VALUE:recommendation:privacy_category::STRING AS privacy_category,
    f.VALUE:recommendation:confidence::STRING AS confidence,
    f.VALUE:valid_value_ratio::FLOAT AS valid_value_ratio,
    LAST_CLASSIFIED_ON
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST,
     LATERAL FLATTEN(INPUT => RESULT) f
WHERE DATABASE_NAME = '<database>'
  AND f.VALUE:recommendation:semantic_category IS NOT NULL
ORDER BY TABLE_NAME, column_name;

-- High-confidence PII columns (coverage > 80%)
SELECT 
    DATABASE_NAME,
    SCHEMA_NAME,
    TABLE_NAME,
    f.KEY AS column_name,
    f.VALUE:recommendation:semantic_category::STRING AS semantic_category,
    f.VALUE:recommendation:privacy_category::STRING AS privacy_category,
    f.VALUE:recommendation:coverage::FLOAT AS coverage
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST,
     LATERAL FLATTEN(INPUT => RESULT) f
WHERE DATABASE_NAME = '<database>'
  AND f.VALUE:recommendation:coverage::FLOAT > 0.8
ORDER BY coverage DESC;

-- Summary: Count of sensitive columns by category for a database
SELECT 
    f.VALUE:recommendation:semantic_category::STRING AS semantic_category,
    f.VALUE:recommendation:privacy_category::STRING AS privacy_category,
    COUNT(*) AS column_count
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST,
     LATERAL FLATTEN(INPUT => RESULT) f
WHERE DATABASE_NAME = '<database>'
  AND f.VALUE:recommendation:semantic_category IS NOT NULL
GROUP BY semantic_category, privacy_category
ORDER BY column_count DESC;

-- Tables with the most sensitive columns
SELECT 
    DATABASE_NAME,
    SCHEMA_NAME,
    TABLE_NAME,
    COUNT(*) AS sensitive_column_count
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST,
     LATERAL FLATTEN(INPUT => RESULT) f
WHERE DATABASE_NAME = '<database>'
  AND f.VALUE:recommendation:semantic_category IS NOT NULL
GROUP BY DATABASE_NAME, SCHEMA_NAME, TABLE_NAME
ORDER BY sensitive_column_count DESC;
