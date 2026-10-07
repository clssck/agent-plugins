-- Create Classification Profile
-- Reference: https://docs.snowflake.com/en/sql-reference/classes/classification_profile
-- Replace placeholders with actual values

-- Parameters:
--   <profile_name>: Name for the classification profile (e.g., pii_classifier)
--   <database>: Database where profile will be stored
--   <schema>: Schema where profile will be stored
--   <min_object_age>: Days to wait before classifying new objects (default: 1)
--   <max_classification_validity>: Days before re-classification (default: 90)
--   <auto_tag>: Whether to automatically apply tags (TRUE or FALSE)
--   <classify_views>: Whether to classify views (TRUE or FALSE; default FALSE)

-- =============================================================================
-- STEP 0: Set schema context FIRST (REQUIRED)
-- =============================================================================
-- The profile is created in the CURRENT schema context.
-- You MUST set the schema before creating the profile.

USE DATABASE <database>;
USE SCHEMA <database>.<schema>;

-- =============================================================================
-- STEP 1: Create the classification profile
-- =============================================================================
-- NOTE: Do NOT try to specify location in CREATE statement - set schema context first

CREATE OR REPLACE SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE <profile_name>(
  {
    'minimum_object_age_for_classification_days': <min_object_age>,
    'maximum_classification_validity_days': <max_classification_validity>,
    'auto_tag': <auto_tag>,       -- TRUE or FALSE
    'classify_views': <classify_views>  -- TRUE or FALSE; default FALSE
  }
);

-- =============================================================================
-- VERIFY CREATION
-- =============================================================================

SHOW SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE LIKE '<profile_name>';
SELECT <profile_name>!DESCRIBE();

-- =============================================================================
-- EXAMPLES
-- =============================================================================

-- Example 1: Basic PII classifier with auto-tagging
-- CREATE OR REPLACE SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE pii_classifier(
--   'minimum_object_age_for_classification_days': 1,
--   'maximum_classification_validity_days': 90,
--   'auto_tag': TRUE,
--   'classify_views': FALSE
-- );

-- Example 2: Conservative profile without auto-tagging
-- CREATE OR REPLACE SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE manual_review(
--   'minimum_object_age_for_classification_days': 7,
--   'maximum_classification_validity_days': 30,
--   'auto_tag': FALSE,
--   'classify_views': FALSE
-- );

-- =============================================================================
-- ENABLE AUTO-CLASSIFICATION ON A DATABASE
-- =============================================================================

-- After creating the profile, enable it on a database:
-- ALTER DATABASE <target_database> SET CLASSIFICATION_PROFILE = '<database>.<schema>.<profile_name>';
