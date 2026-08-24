-- Create Custom Classifier
-- Creates a regex-based classifier for domain-specific sensitive data
-- Reference: https://docs.snowflake.com/en/sql-reference/classes/custom_classifier

-- CORRECT SYNTAX (three-step process):
-- 0. Set database, then schema context (classifier is created in current schema)
-- 1. Create the classifier instance
-- 2. Add regex patterns using ADD_REGEX method

-- Parameters for CREATE:
--   <database>: Database where classifier will be created
--   <schema>: Schema where classifier will be created
--   <classifier_name>: Name for the custom classifier

-- Parameters for ADD_REGEX:
--   <semantic_category>: Name for this category (e.g., 'EMPLOYEE_ID', 'PROJECT_CODE')
--   <privacy_category>: One of 'IDENTIFIER', 'QUASI_IDENTIFIER', or 'SENSITIVE'
--   <value_regex>: Regular expression pattern to match column values
--   <description>: Human-readable description

-- =============================================================================
-- STEP 0: Set database, then schema context (REQUIRED)
-- =============================================================================
-- The classifier is created in the CURRENT schema context.
-- You MUST set the target database first, then the target schema immediately after.
-- Do NOT run USE DATABASE again after USE SCHEMA; that can reset the current schema
-- and create the classifier in a default schema such as PUBLIC.

USE DATABASE <database>;
USE SCHEMA <database>.<schema>;

-- Optional sanity check before CREATE: CURRENT_SCHEMA() must equal <schema>.
SELECT CURRENT_DATABASE(), CURRENT_SCHEMA();

-- =============================================================================
-- STEP 1: Create the classifier instance
-- =============================================================================
-- NOTE: Do NOT try to specify location in CREATE statement
-- WRONG: CREATE ... <classifier_name>() IN <schema>
-- WRONG: CREATE ... <database>.<schema>.<classifier_name>()
-- CORRECT: Set schema context first, then use just the name

CREATE OR REPLACE SNOWFLAKE.DATA_PRIVACY.CUSTOM_CLASSIFIER <classifier_name>();

-- =============================================================================
-- STEP 2: Add regex pattern(s) to the classifier
-- =============================================================================

-- Syntax:
CALL <database>.<schema>.<classifier_name>!ADD_REGEX(
  semantic_category => '<semantic category name>',
  privacy_category => '< IDENTIFIER /  QUASI_IDENTIFIER / SENSITIVE>',
  value_regex => '<Regular Expression to match the data>',
  col_name_regex => '<Optional - regular expression to match the column name>',
  description => '<User friendly description>',
  threshold => '<Optional threshold for the data match. Default is 0.8>'
);


-- Full syntax (6 parameters, with column name regex and threshold):
-- CALL <classifier_name>!ADD_REGEX(
--   '<semantic_category>',
--   '<privacy_category>',
--   '<value_regex>',
--   '<column_name_regex>',  -- Optional: regex to match column names (NULL to skip)
--   '<description>',
--   <threshold>             -- Confidence threshold (0.0 to 1.0)
-- );

-- =============================================================================
-- EXAMPLES
-- =============================================================================

-- Example 1: Employee ID classifier
-- CREATE OR REPLACE SNOWFLAKE.DATA_PRIVACY.CUSTOM_CLASSIFIER employee_id_classifier();
-- CALL employee_id_classifier!ADD_REGEX(
--   semantic_category => 'EMPLOYEE_ID',
--   privacy_category => 'IDENTIFIER',
--   value_regex => '^EMP-[0-9]{5}$',
--   col_name_regex => '',
--   description => 'Detects employee IDs in format EMP-XXXXX',
--   threshold => 0.8
-- );

-- Example 2: Project code classifier  
-- CREATE OR REPLACE SNOWFLAKE.DATA_PRIVACY.CUSTOM_CLASSIFIER project_code_classifier();
-- CALL project_code_classifier!ADD_REGEX(
--   'PROJECT_CODE',
--   'QUASI_IDENTIFIER',
--   '^PRJ-[A-Z]{3}-[0-9]{3}$',
--   ''
-- );

-- =============================================================================
-- MANAGEMENT COMMANDS
-- =============================================================================

-- List all custom classifiers in current schema:
SHOW SNOWFLAKE.DATA_PRIVACY.CUSTOM_CLASSIFIER;

-- List classifiers in a specific location:
SHOW SNOWFLAKE.DATA_PRIVACY.CUSTOM_CLASSIFIER IN SCHEMA <database>.<schema>;

-- Describe a classifier (show its regex patterns):
SELECT <database>.<schema>.<classifier_name>!LIST();

-- Drop a classifier:
DROP SNOWFLAKE.DATA_PRIVACY.CUSTOM_CLASSIFIER <classifier_name>;

-- Drop with fully qualified name:
DROP SNOWFLAKE.DATA_PRIVACY.CUSTOM_CLASSIFIER <database>.<schema>.<classifier_name>;
