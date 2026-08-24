-- Test Custom Classifier
-- Validates a custom classifier against an existing table
--
-- WORKFLOW:
--   1. Ask user for a table and column to test against
--   2. Run SYSTEM$CLASSIFY with the custom classifier
--   3. Fetch results using SYSTEM$GET_CLASSIFICATION_RESULT
--
-- Parameters (ask user for these):
--   <database>: Database containing the test table
--   <schema>: Schema containing the test table
--   <table>: Table to test against
--   <column>: Column expected to match the classifier
--   <classifier_db>: Database containing the classifier
--   <classifier_schema>: Schema containing the classifier
--   <classifier_name>: Name of the classifier being tested

-- =============================================================================
-- Step 1: Run classification with custom classifier
-- =============================================================================
-- SYSTEM$CLASSIFY takes exactly 2 positional args: object_name and options/profile.
-- Pass the custom classifier in the options object as the 2nd arg.

CALL SYSTEM$CLASSIFY(
    '<database>.<schema>.<table>',
    {'custom_classifiers': ['<classifier_db>.<classifier_schema>.<classifier_name>']}
);

-- =============================================================================
-- Step 2: Fetch classification results
-- =============================================================================

SELECT SYSTEM$GET_CLASSIFICATION_RESULT('<database>.<schema>.<table>');

-- =============================================================================
-- Step 3: Parse results to check specific column
-- =============================================================================

SELECT
    f.key AS column_name,
    f.value:recommendation:semantic_category::STRING AS semantic_category,
    f.value:recommendation:privacy_category::STRING AS privacy_category,
    f.value:recommendation:confidence::STRING AS confidence,
    f.value:valid_value_ratio::FLOAT AS valid_value_ratio
FROM 
    TABLE(FLATTEN(PARSE_JSON(
        SYSTEM$GET_CLASSIFICATION_RESULT('<database>.<schema>.<table>')
    ):classification_result)) f
WHERE f.key = '<column>';

-- =============================================================================
-- Step 4: View all classified columns (optional)
-- =============================================================================

SELECT
    f.key AS column_name,
    f.value:recommendation:semantic_category::STRING AS semantic_category,
    f.value:recommendation:privacy_category::STRING AS privacy_category,
    f.value:recommendation:confidence::STRING AS confidence
FROM 
    TABLE(FLATTEN(PARSE_JSON(
        SYSTEM$GET_CLASSIFICATION_RESULT('<database>.<schema>.<table>')
    ):classification_result)) f
WHERE f.value:recommendation:semantic_category IS NOT NULL
ORDER BY confidence DESC;
