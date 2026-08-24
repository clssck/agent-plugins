-- Check Existing Classification Profiles
-- Lists all classification profiles in the account
-- Reference: https://docs.snowflake.com/en/sql-reference/classes/classification_profile

-- =============================================================================
-- LIST CLASSIFICATION PROFILES
-- =============================================================================

-- Show all classification profiles
SHOW SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE IN ACCOUNT;

-- Show profiles in a specific schema
SHOW SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE IN SCHEMA <database>.<schema>;

-- Show profiles in a specific database
SHOW SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE IN DATABASE <database>;

-- =============================================================================
-- DESCRIBE A PROFILE
-- =============================================================================

-- See details of a specific profile (settings, custom classifiers, etc.)
SELECT <profile_name>!DESCRIBE();

-- With fully qualified name
SELECT <database>.<schema>.<profile_name>!DESCRIBE();

-- =============================================================================
-- CHECK DATABASE CONFIGURATION
-- =============================================================================

-- To see which databases are using a profile:
SHOW PARAMETERS LIKE 'CLASSIFICATION_PROFILE' IN DATABASE <database_name>;

