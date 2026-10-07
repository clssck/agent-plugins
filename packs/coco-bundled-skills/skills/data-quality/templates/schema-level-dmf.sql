-- Schema-Level DMF Operations
-- Enterprise Edition feature (GA).
--
-- This file is a REFERENCE MENU of variant statements — do NOT execute every
-- statement in order. Pick the section(s) that match the user's request,
-- substitute placeholders, and execute only the chosen statements.
--
-- Replace <database> and <schema> with target database and schema names.
-- Replace placeholders in each section with the user's chosen options.
--
-- Supported DMFs at schema level: SNOWFLAKE.CORE.ROW_COUNT, SNOWFLAKE.CORE.FRESHNESS
-- Column-level DMFs (NULL_COUNT, DUPLICATE_COUNT, etc.) still require per-table ALTER TABLE.

-- =============================================================================
-- 1. ADD DMF AT SCHEMA LEVEL
-- =============================================================================

-- Add ROW_COUNT to all objects in schema (no anomaly detection)
ALTER SCHEMA <database>.<schema>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.ROW_COUNT ON ();

-- Add ROW_COUNT with anomaly detection enabled
-- Snowflake trains per-object and flags unusual volume changes automatically
ALTER SCHEMA <database>.<schema>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.ROW_COUNT ON ()
    ANOMALY_DETECTION = TRUE;

-- Add FRESHNESS to all objects in schema
-- NOTE: Views and external tables are automatically skipped (they require a column argument)
ALTER SCHEMA <database>.<schema>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.FRESHNESS ON ();

-- Add FRESHNESS with anomaly detection
ALTER SCHEMA <database>.<schema>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.FRESHNESS ON ()
    ANOMALY_DETECTION = TRUE;

-- Add ROW_COUNT but exclude dynamic tables and views
-- Possible EXCLUDE_TABLE_TYPES values:
--   'DYNAMIC_TABLE', 'EVENT_TABLE', 'EXTERNAL_TABLE',
--   'ICEBERG_TABLE', 'MATERIALIZED_VIEW', 'TABLE', 'VIEW'
ALTER SCHEMA <database>.<schema>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.ROW_COUNT ON ()
    EXCLUDE_TABLE_TYPES = ('DYNAMIC_TABLE', 'VIEW');

-- Add both ROW_COUNT and FRESHNESS with anomaly detection (run separately)
ALTER SCHEMA <database>.<schema>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.ROW_COUNT ON ()
    ANOMALY_DETECTION = TRUE;

ALTER SCHEMA <database>.<schema>
  ADD DATA METRIC FUNCTION SNOWFLAKE.CORE.FRESHNESS ON ()
    ANOMALY_DETECTION = TRUE;


-- =============================================================================
-- 2. ADJUST SCHEDULE FOR ALL OBJECTS IN SCHEMA
-- =============================================================================
-- Default: 60 minutes. Can be overridden per-object with ALTER TABLE.
ALTER SCHEMA <database>.<schema>
  SET DATA_METRIC_SCHEDULE = '60 MINUTE';

-- Run every 5 minutes (for high-frequency pipelines)
ALTER SCHEMA <database>.<schema>
  SET DATA_METRIC_SCHEDULE = '5 MINUTE';


-- =============================================================================
-- 3. SUSPEND / RESUME SCHEMA-LEVEL DMF
-- =============================================================================

-- Suspend ROW_COUNT for all objects in the schema
ALTER SCHEMA <database>.<schema>
  MODIFY DATA METRIC FUNCTION SNOWFLAKE.CORE.ROW_COUNT ON ()
    SUSPEND;

-- Resume ROW_COUNT for all objects in the schema
ALTER SCHEMA <database>.<schema>
  MODIFY DATA METRIC FUNCTION SNOWFLAKE.CORE.ROW_COUNT ON ()
    RESUME;


-- =============================================================================
-- 4. OVERRIDE SETTINGS AT THE OBJECT LEVEL
-- =============================================================================

-- Disable anomaly detection for a specific table (while keeping schema-level association)
ALTER TABLE <database>.<schema>.<table_name>
  MODIFY DATA METRIC FUNCTION SNOWFLAKE.CORE.ROW_COUNT ON ()
    SET ANOMALY_DETECTION = FALSE;

-- Remove the DMF from one specific object. The schema-level configuration on
-- the schema is unchanged; this only detaches the DMF from this single object.
ALTER TABLE <database>.<schema>.<table_name>
  DROP DATA METRIC FUNCTION SNOWFLAKE.CORE.ROW_COUNT ON ();

-- Override schedule for a specific table only
ALTER TABLE <database>.<schema>.<table_name>
  SET DATA_METRIC_SCHEDULE = '5 MINUTE';


-- =============================================================================
-- 5. CHECK WHICH DMFs WERE ADDED AT THE SCHEMA LEVEL
-- =============================================================================
-- Uses DATA_METRIC_FUNCTION_REFERENCES with REF_ENTITY_DOMAIN => 'schema'
-- New columns: LEVEL ('TABLE' or 'SCHEMA'), EXCLUDE_TABLE_TYPES
SELECT
    REF_ENTITY_NAME       AS schema_name,
    REF_ENTITY_DOMAIN     AS domain,
    METRIC_NAME,
    SCHEDULE,
    SCHEDULE_STATUS,
    LEVEL,
    EXCLUDE_TABLE_TYPES
FROM TABLE(
    INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES(
        REF_ENTITY_NAME   => '<database>.<schema>',
        REF_ENTITY_DOMAIN => 'schema'
    )
);


-- =============================================================================
-- 6. CHECK ALL OBJECT-LEVEL ASSOCIATIONS CREATED BY SCHEMA-LEVEL DMF
-- =============================================================================
-- LEVEL = 'SCHEMA' means the association was inherited from the schema-level config.
-- LEVEL = 'TABLE'  means the association was set directly on the object.
SELECT
    REF_ENTITY_NAME       AS object_name,
    REF_ENTITY_DOMAIN     AS object_type,
    METRIC_NAME,
    SCHEDULE_STATUS,
    LEVEL,
    EXCLUDE_TABLE_TYPES
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_METRIC_FUNCTION_REFERENCES
WHERE REF_DATABASE_NAME = '<database>'
  AND REF_SCHEMA_NAME   = '<schema>'
ORDER BY LEVEL, REF_ENTITY_NAME;


-- =============================================================================
-- 7. DROP SCHEMA-LEVEL DMF ASSOCIATION
-- =============================================================================
ALTER SCHEMA <database>.<schema>
  DROP DATA METRIC FUNCTION SNOWFLAKE.CORE.ROW_COUNT ON ();

ALTER SCHEMA <database>.<schema>
  DROP DATA METRIC FUNCTION SNOWFLAKE.CORE.FRESHNESS ON ();


/*
Access control requirements for schema-level DMF operations:
  - OWNERSHIP on the schema
  - MANAGE DATA QUALITY privilege on the account
  - EXECUTE DATA METRIC FUNCTION privilege on the account
  - SNOWFLAKE.DATA_METRIC_USER database role

Limitations:
  - Only SNOWFLAKE.CORE.ROW_COUNT and SNOWFLAKE.CORE.FRESHNESS are supported at schema level
  - FRESHNESS automatically skips views and external tables (they require a column argument)
  - Schema-level DMF associations (created via ALTER SCHEMA ... ADD DATA METRIC FUNCTION)
    do NOT support TRIGGER_ON_CHANGES — they run on the time-based DATA_METRIC_SCHEDULE
    set on the schema (default 60 MINUTE). For TRIGGER_ON_CHANGES behavior on a specific
    object, attach the DMF directly with ALTER TABLE ... ADD DATA METRIC FUNCTION instead.
    Note: ALTER SCHEMA ... SET DATA_METRIC_SCHEDULE = 'TRIGGER_ON_CHANGES' (which sets the
    default schedule used by per-table DMFs attached via ALTER TABLE) is unaffected by this
    limitation and remains supported.
  - Column-level DMFs (NULL_COUNT, DUPLICATE_COUNT, etc.) still require per-table ALTER TABLE

LEVEL column values (in DATA_METRIC_FUNCTION_REFERENCES):
  'TABLE'  — DMF was associated directly on the object
  'SCHEMA' — DMF was inherited from a schema-level association
*/
