-- Data Classification in Snowflake
-- Two approaches for classifying sensitive data:
--   1. Manual Classification - Use SYSTEM$CLASSIFY to analyze and tag tables on demand
--   2. Automatic Classification - Set up a classification profile and link to schema/database

-- =============================================================================
-- MANUAL CLASSIFICATION: SYSTEM$CLASSIFY
-- =============================================================================
-- SYSTEM$CLASSIFY is a stored procedure with exactly 2 positional arguments:
--   1. object_name  (VARCHAR, required) — fully qualified table/view name
--   2. profile_or_options — one of:
--        • NULL or {}                              — use Snowflake defaults
--        • '<profile_db>.<schema>.<profile>'       — use a classification profile (VARCHAR)
--        • {'sample_count': N}                     — custom row sampling (OBJECT)
--        • {'auto_tag': true}                      — auto-apply tags (OBJECT)
--        • {'sample_count': N, 'auto_tag': true}   — both (OBJECT)
--        • {'custom_classifiers': ['db.sch.name']} — custom classifiers (OBJECT)
--        • {'use_all_custom_classifiers': true}    — all accessible classifiers (OBJECT)
--
-- ⚠️ The 2nd arg is EITHER a profile string OR an options object — never both.
--    There is no 3-argument form; named parameters (TABLE_NAME =>, OPTIONS =>) do NOT exist.
-- ⚠️ Always use CALL, not SELECT (SELECT gives "Unknown function SYSTEM$CLASSIFY" error)

-- ── Basic: classify with Snowflake defaults ───────────────────────────────────
CALL SYSTEM$CLASSIFY('<database>.<schema>.<table>', null);

-- ── Specify number of rows to sample ─────────────────────────────────────────
CALL SYSTEM$CLASSIFY('<database>.<schema>.<table>', {'sample_count': 1000});

-- ── Auto-apply classification tags after classification ───────────────────────
CALL SYSTEM$CLASSIFY('<database>.<schema>.<table>', {'auto_tag': true});

-- ── Sample rows AND auto-apply tags ──────────────────────────────────────────
CALL SYSTEM$CLASSIFY('<database>.<schema>.<table>', {'sample_count': 1000, 'auto_tag': true});

-- ── Classify using a classification profile (profile replaces options) ────────
CALL SYSTEM$CLASSIFY('<database>.<schema>.<table>', '<profile_db>.<profile_schema>.<profile_name>');

-- ── Use specific custom classifiers ──────────────────────────────────────────
CALL SYSTEM$CLASSIFY('<database>.<schema>.<table>', {'custom_classifiers': ['<classifier_db>.<classifier_schema>.<classifier_name>']});

-- ── Use all accessible custom classifiers automatically ──────────────────────
CALL SYSTEM$CLASSIFY('<database>.<schema>.<table>', {'use_all_custom_classifiers': true});

-- =============================================================================
-- RETRIEVING CLASSIFICATION RESULTS
-- =============================================================================

-- After running SYSTEM$CLASSIFY, retrieve results using SYSTEM$GET_CLASSIFICATION_RESULT
-- This fetches the current classification state for any previously classified object.

SELECT SYSTEM$GET_CLASSIFICATION_RESULT('<database>.<schema>.<table>');

-- Parse the results into a readable format
SELECT 
    f.key AS column_name,
    f.value:recommendation:semantic_category::STRING AS semantic_category,
    f.value:recommendation:privacy_category::STRING AS privacy_category,
    f.value:recommendation:confidence::STRING AS confidence,
    f.value:valid_value_ratio::FLOAT AS valid_value_ratio
FROM 
    TABLE(FLATTEN(PARSE_JSON(
        SYSTEM$GET_CLASSIFICATION_RESULT('<database>.<schema>.<table>')
    ))) f;

-- =============================================================================
-- AUTOMATIC CLASSIFICATION: Classification Profiles
-- =============================================================================
-- Set up automatic classification to continuously monitor and tag new data

-- Step 1: Create a classification profile
CREATE OR REPLACE SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE <database>.<schema>.<profile_name>();

-- Step 2: Link the profile to a database (monitors all tables in the database)
ALTER DATABASE <database> SET CLASSIFICATION_PROFILE = '<database>.<schema>.<profile_name>';

-- Or link to a specific schema
ALTER SCHEMA <database>.<schema> SET CLASSIFICATION_PROFILE = '<database>.<schema>.<profile_name>';

-- Check which databases/schemas are monitored
SELECT SYSTEM$SHOW_SENSITIVE_DATA_MONITORED_ENTITIES('DATABASE');
SELECT SYSTEM$SHOW_SENSITIVE_DATA_MONITORED_ENTITIES('SCHEMA');

-- Remove automatic classification from a database
ALTER DATABASE <database> UNSET CLASSIFICATION_PROFILE;

-- =============================================================================
-- TROUBLESHOOTING
-- =============================================================================

-- "Unknown function SYSTEM$CLASSIFY" error:
--   You used SELECT instead of CALL.
--   Fix: CALL SYSTEM$CLASSIFY(...), never SELECT SYSTEM$CLASSIFY(...)

-- "Insufficient privileges" error:
--   Your role lacks required grants. Check with:
--   SHOW GRANTS TO ROLE <current_role>;

-- =============================================================================
-- FALLBACK: Manual column inspection (when you just need column names)
-- =============================================================================

-- Option 1: Use DESCRIBE TABLE
DESCRIBE TABLE <database>.<schema>.<table>;

-- Option 2: Use INFORMATION_SCHEMA for multiple tables
SELECT 
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE
FROM <database>.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = '<schema>'
ORDER BY TABLE_NAME, ORDINAL_POSITION;
