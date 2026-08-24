-- Check Existing Custom Classifiers
-- Lists all custom classifiers in the account
-- Reference: https://docs.snowflake.com/en/sql-reference/classes/custom_classifier

-- =============================================================================
-- LIST CUSTOM CLASSIFIERS
-- =============================================================================

-- Show all custom classifiers in current schema
SHOW SNOWFLAKE.DATA_PRIVACY.CUSTOM_CLASSIFIER IN ACCOUNT;

-- Show custom classifiers in a specific schema
SHOW SNOWFLAKE.DATA_PRIVACY.CUSTOM_CLASSIFIER IN SCHEMA <database>.<schema>;

-- Show custom classifiers in a specific database (all schemas)
SHOW SNOWFLAKE.DATA_PRIVACY.CUSTOM_CLASSIFIER IN DATABASE <database>;

-- =============================================================================
-- DESCRIBE A CLASSIFIER
-- Custom Classifier doesn't support DESCRIBE command, use list() instead.
-- Custom Classifier is a Bundle which is very special.
-- =============================================================================

-- Describe a specific classifier to see its regex patterns
-- Fully qualified name is a must.
SELECT <database>.<schema>.<classifier_name>!LIST();

-- =============================================================================
-- TEST REGEX PATTERNS
-- =============================================================================

-- Test a regex pattern against a sample value
SELECT 
    '<sample_value>' AS test_value,
    '<sample_value>' REGEXP '<regex_pattern>' AS matches;

-- Test multiple values
SELECT 
    value AS test_value,
    value REGEXP '<regex_pattern>' AS matches
FROM TABLE(FLATTEN(SPLIT('<value1>,<value2>,<value3>', ',')));

-- Test with expected results
WITH test_data AS (
    SELECT column1 AS test_value, column2 AS expected_match
    FROM VALUES 
        ('<positive_sample_1>', TRUE),
        ('<positive_sample_2>', TRUE),
        ('<negative_sample_1>', FALSE),
        ('<negative_sample_2>', FALSE)
)
SELECT 
    test_value,
    expected_match,
    test_value REGEXP '<regex_pattern>' AS actual_match,
    CASE 
        WHEN expected_match = (test_value REGEXP '<regex_pattern>') THEN '✅ PASS'
        ELSE '❌ FAIL'
    END AS result
FROM test_data;

-- =============================================================================
-- DROP A CLASSIFIER
-- Always confirm with the user before dropping a classifier.
-- =============================================================================

-- Drop a classifier
DROP SNOWFLAKE.DATA_PRIVACY.CUSTOM_CLASSIFIER <classifier_name>;

-- Drop with fully qualified name
DROP SNOWFLAKE.DATA_PRIVACY.CUSTOM_CLASSIFIER <database>.<schema>.<classifier_name>;

