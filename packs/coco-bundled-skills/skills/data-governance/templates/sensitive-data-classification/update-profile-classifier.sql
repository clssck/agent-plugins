-- Update Classification Profile with Custom Classifier
-- Adds or removes custom classifiers from a profile
-- Reference: https://docs.snowflake.com/en/sql-reference/classes/classification_profile

-- Parameters:
--   <profile_name>: Name of the classification profile to update
--   <classifier_database>: Database containing the custom classifier
--   <classifier_schema>: Schema containing the custom classifier
--   <classifier_name>: Name of the custom classifier

-- =============================================================================
-- ADD CUSTOM CLASSIFIER TO PROFILE
-- =============================================================================

ALTER SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE <profile_name>
    ADD CUSTOM_CLASSIFIER <classifier_database>.<classifier_schema>.<classifier_name>;

CALL <my_classification_profile>!set_custom_classifiers(
  {
    '<classifier_name1>': <classifier_name1>!list(),
    '<classifier_name2>': <classifier_name2>!list()
  });

-- =============================================================================
-- REMOVE CUSTOM CLASSIFIER FROM PROFILE
-- =============================================================================

ALTER SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE <profile_name>
    DROP CUSTOM_CLASSIFIER <classifier_database>.<classifier_schema>.<classifier_name>;

-- =============================================================================
-- VIEW PROFILE DETAILS
-- =============================================================================

-- Describe profile to see all settings including custom classifiers
SELECT <database>.<schema>.<profile_name>!DESCRIBE();

-- =============================================================================
-- EXAMPLES
-- =============================================================================

-- Example: Add employee_id_classifier to pii_classifier profile
-- ALTER SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE pii_classifier
--     ADD CUSTOM_CLASSIFIER GOVERNANCE_DB.CLASSIFIERS.employee_id_classifier;

-- Example: Remove a classifier from a profile
-- ALTER SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE pii_classifier
--     DROP CUSTOM_CLASSIFIER GOVERNANCE_DB.CLASSIFIERS.old_classifier;

