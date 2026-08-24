-- ============================================
-- PACKAGE CREATION & RELEASE
-- ============================================
-- After creating all objects and writing the manifest, create and release the package.

-- ============================================
-- COMMON MISTAKES — DO NOT DO THESE
-- ============================================
-- CREATE DATABASE <PKG>                               -- WRONG: databases and app packages share the same namespace; this blocks CREATE APPLICATION PACKAGE <PKG>
-- CREATE APPLICATION PACKAGE <PKG> DATA = TRUE        -- WRONG: correct syntax is TYPE = DATA
-- CREATE APPLICATION PACKAGE <PKG> TYPE=SHARE         -- WRONG: TYPE=DATA, not TYPE=SHARE
-- CREATE OR REPLACE APPLICATION PACKAGE ...           -- WRONG: no OR REPLACE for APPLICATION PACKAGES
-- CREATE OR REPLACE APPLICATION ...                   -- WRONG: no OR REPLACE for APPLICATIONS (use DROP + CREATE)
-- ALTER APPLICATION PACKAGE <PKG> ADD LIVE VERSION    -- WRONG: LIVE version is auto-created, NEVER run this
-- ALTER APPLICATION PACKAGE <PKG> BUILD               -- NOTE: BUILD validates the manifest but does NOT commit or publish. Use it to check for errors before releasing.
-- PUT 'snow://workspace/...'                          -- WRONG: PUT only accepts local file:// URLs
-- SELECT $1 FROM snow://...                            -- WRONG: "Domain APPLICATION_PACKAGE not supported by SnowURL"
--
-- For declarative sharing with LIVE version: use RELEASE LIVE VERSION to publish.
-- BUILD is optional — use it to validate the manifest before releasing.
-- Upload method depends on environment (see below).

-- ============================================
-- ENVIRONMENT DETECTION
-- ============================================
-- Your system prompt tells you which environment you're in:
--   "You are in a Workspace"       → CoCo Web (Workspaces) — has write/read/edit tools
--   "You are NOT in a Workspace"   → CoCo Web (Non-Workspaces) — NO file tools, use stage method
--   CLI / terminal                 → CoCo CLI — has write/read/edit tools, local filesystem

-- ============================================
-- CORRECT SEQUENCE
-- ============================================
-- CRITICAL: Run these steps ONE AT A TIME in EXACT order.
-- NOTE: Snowflake uppercases unquoted identifiers. Use MY_PKG not my_pkg in snow:// URLs.

-- Step 1: Create package (TYPE=DATA required) — LIVE version is auto-created
CREATE APPLICATION PACKAGE <PKG> TYPE = DATA;

-- Step 2: Write and upload manifest.yml.
--         ALWAYS name the manifest file manifest.yml, NOT manifest-example.yml.
--         For workspaces: upload workspace files AFTER the manifest (Step 2b below).
--         Legacy notebooks (DEPRECATED): CLI only. Do NOT create legacy notebooks
--         from CoCo Web (any tab).

-- CoCo Web (Workspaces): write manifest via write tool, then:
COPY FILES INTO snow://package/<PKG>/versions/LIVE/
  FROM 'snow://workspace/USER$.PUBLIC.DEFAULT$/versions/live/'
  FILES = ('manifest.yml');

-- CoCo Web (Non-Workspaces): NO write tool available.
-- Recommend user open a Workspace for the best experience.
-- If they decline, use the stage method with dollar-quoted YAML:
--
-- CREATE OR REPLACE TEMPORARY STAGE manifest_stage;
-- COPY INTO @manifest_stage/manifest.yml FROM (
--   SELECT $$<entire manifest YAML here>$$
-- )
-- FILE_FORMAT = (TYPE = CSV COMPRESSION = NONE FIELD_OPTIONALLY_ENCLOSED_BY = NONE ESCAPE = NONE ESCAPE_UNENCLOSED_FIELD = NONE)
-- SINGLE = TRUE OVERWRITE = TRUE;
--
-- COPY FILES INTO snow://package/<PKG>/versions/LIVE/
--   FROM @manifest_stage
--   FILES = ('manifest.yml');
--
-- The four FILE_FORMAT params are ALL required — without them Snowflake adds
-- compression, backslash escaping, or quoting that corrupt the YAML.
-- Use $$ dollar-quoting (not single quotes) to avoid YAML escaping issues.

-- CoCo CLI: write manifest via write tool, then:
-- PUT file:///workspace/manifest.yml snow://package/<PKG>/versions/LIVE/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;

-- Step 2b (optional): Upload workspace files.
-- If the manifest includes application_content.workspaces, upload each file to its source path:
-- PUT file:///path/to/workspaces/<dir>/<file> snow://package/<PKG>/versions/LIVE/workspaces/<dir>/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
-- Repeat for each file in each workspace directory.

-- Step 2c (DEPRECATED, CLI only): Upload a legacy notebook .ipynb.
-- Only applies when the manifest uses the deprecated application_content.notebooks.
-- Prefer workspaces (Step 2b). If you did write a legacy notebook, add a second PUT
-- for the .ipynb file:
-- PUT file:///workspace/<notebook>.ipynb snow://package/<PKG>/versions/LIVE/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;

-- After upload, ALWAYS verify before releasing:
LIST snow://package/<PKG>/versions/LIVE/;
-- If 0 rows: do NOT release. Debug the upload path first.

-- Step 3: Release AFTER LIST confirms files are present
ALTER APPLICATION PACKAGE <PKG> RELEASE LIVE VERSION;

-- ============================================
-- PROVIDER-SIDE DEV/TEST CYCLE (optional)
-- ============================================
-- Use this to iterate on the LIVE version before releasing.
-- The app MUST be created with USING VERSION LIVE for this to work.

-- 1. Install test app from LIVE version (first time only):
CREATE APPLICATION <APP> FROM APPLICATION PACKAGE <PKG> USING VERSION LIVE;

-- 2. After updating files, build to pick up changes:
ALTER APPLICATION PACKAGE <PKG> BUILD;

-- 3. Upgrade the test app to the latest built LIVE version:
ALTER APPLICATION <APP> UPGRADE USING VERSION LIVE;

-- Repeat steps 2-3 as needed. When satisfied, release:
ALTER APPLICATION PACKAGE <PKG> RELEASE LIVE VERSION;

-- NOTE: UPGRADE USING VERSION LIVE only works on apps created with USING VERSION LIVE.
-- For apps created from a released version, use ALTER APPLICATION <APP> UPGRADE instead.

-- ============================================
-- READING / MODIFYING AN EXISTING PACKAGE
-- ============================================

-- List files in the package:
LIST snow://package/<PKG>/versions/LIVE/;

-- Download files for editing:
--
-- CoCo Web (Workspaces):
COPY FILES INTO 'snow://workspace/USER$.PUBLIC.DEFAULT$/versions/live/'
  FROM snow://package/<PKG>/versions/LIVE/
  FILES = ('manifest.yml');
-- Then read/edit via workspace tools.
--
-- CoCo Web (Non-Workspaces): Recommend Workspaces. If user declines, download to a stage:
-- CREATE OR REPLACE STAGE download_stage;
-- COPY FILES INTO @download_stage/ FROM snow://package/<PKG>/versions/LIVE/ FILES = ('manifest.yml');
-- CREATE OR REPLACE FILE FORMAT raw_text_fmt TYPE = CSV FIELD_DELIMITER = NONE RECORD_DELIMITER = NONE COMPRESSION = NONE ESCAPE = NONE ESCAPE_UNENCLOSED_FIELD = NONE;
-- SELECT $1 AS content FROM @download_stage/manifest.yml (FILE_FORMAT => 'raw_text_fmt');
-- Edit the YAML, then re-upload using the stage method above.
--
-- CoCo CLI:
-- GET snow://package/<PKG>/versions/LIVE/manifest.yml file:///tmp/;
-- Ask user for preferred download path. /tmp/ is a safe default.

-- Re-upload modified files (same upload commands as Step 2 for your environment).
-- Verify with LIST before releasing.

-- Remove a file from the package (e.g. stale legacy notebooks after migrating to workspaces).
-- Use RM (REMOVE is not accepted for snow:// package URLs).
--
-- ██████████████████████████████████████████████████████████████████████████████
-- ██  RM REQUIRES LOWERCASE 'live' IN THE PATH — uppercase LIVE SILENTLY FAILS ██
-- ██████████████████████████████████████████████████████████████████████████████
-- CORRECT (file is actually deleted; returns a row with result = removed):
RM snow://package/<PKG>/versions/live/<file>;
--
-- WRONG (returns "0 rows affected", deletes NOTHING, and raises NO error):
--   RM snow://package/<PKG>/versions/LIVE/<file>;
--
-- This is inconsistent with PUT / GET / LIST, which all accept uppercase LIVE.
-- ALWAYS LIST afterwards to confirm the file is really gone:
LIST snow://package/<PKG>/versions/LIVE/;

-- Release updated version:
ALTER APPLICATION PACKAGE <PKG> RELEASE LIVE VERSION;

-- ============================================
-- LISTINGS (Private Sharing)
-- ============================================
-- Do NOT guess this syntax — use exactly as shown.

-- Check org name first:
SELECT CURRENT_ORGANIZATION_NAME();

-- Check provider region (useful before creating cross-region listings):
SELECT CURRENT_REGION();
-- See all available regions:
SHOW REGIONS;

-- Check if auto-fulfillment (LAF) is enabled (requires ORGADMIN role):
SELECT SYSTEM$IS_GLOBAL_DATA_SHARING_ENABLED_FOR_ACCOUNT('<ACCOUNT_NAME>');
-- Returns TRUE or FALSE. If FALSE, ORGADMIN must enable it:
-- SELECT SYSTEM$ENABLE_GLOBAL_DATA_SHARING_FOR_ACCOUNT('<ACCOUNT_NAME>');

-- HALLUCINATED FUNCTIONS — NONE OF THESE EXIST:
-- SYSTEM$SHOW_ACTIVE_REGION_LIST()              -- does NOT exist
-- SYSTEM$SHOW_ACTIVE_REGION_GROUP()             -- does NOT exist
-- SYSTEM$GLOBAL_ACCOUNT_SET_PARAMETER(...)      -- does NOT exist
-- Do NOT use SHOW ORGANIZATION ACCOUNTS, SHOW SHARES, or SNOWFLAKE.ORGANIZATION_USAGE.ACCOUNTS
-- to discover consumer regions. Just ask the user.

-- Create private listing for specific consumers (SAME region)
CREATE EXTERNAL LISTING <LISTING_NAME>
APPLICATION PACKAGE <PKG> AS
$$
title: "Listing Title"
subtitle: "Short description"
description: "Detailed description of what the app does."
listing_terms:
  type: "OFFLINE"
targets:
  accounts: ["<ORG_NAME>.<ACCOUNT_NAME>"]
$$
PUBLISH = FALSE
REVIEW = FALSE;

-- Create private listing for CROSS-REGION consumers
-- Required when target account is in a different region/cloud than provider.
-- All application packages (including TYPE=DATA) MUST use SUB_DATABASE_WITH_REFERENCE_USAGE.
-- (SUB_DATABASE only works for shares, not application packages.)
CREATE EXTERNAL LISTING <LISTING_NAME>
APPLICATION PACKAGE <PKG> AS
$$
title: "Listing Title"
subtitle: "Short description"
description: "Detailed description of what the app does."
listing_terms:
  type: "OFFLINE"
targets:
  accounts: ["<ORG_NAME>.<ACCOUNT_NAME>"]
auto_fulfillment:
  refresh_type: "SUB_DATABASE_WITH_REFERENCE_USAGE"
$$
PUBLISH = FALSE
REVIEW = FALSE;

-- Publish the listing after creation
ALTER LISTING <LISTING_NAME> PUBLISH;

-- View all listings
SHOW LISTINGS;

-- For paid listings, marketplace publishing, or other advanced scenarios,
-- invoke the internal-marketplace-org-listing skill.

-- ============================================
-- CONSUMER INSTALL WORKFLOW
-- ============================================
-- IMPORTANT: There is NO "CREATE OR REPLACE APPLICATION" syntax!
-- To reinstall, you must DROP first, then CREATE.

-- PREREQUISITES (check BEFORE installing)

-- 1. User profile must be configured (required for listing installs):
ALTER USER <USERNAME> SET
    first_name = '<FIRST_NAME>',
    last_name = '<LAST_NAME>',
    email = '<EMAIL>';
-- Error if missing: "090655 (P0002): Please add your first/last name and email..."

-- 2. Default warehouse MUST exist for tools to work (UDFs, procedures, agents, search):
SHOW PARAMETERS LIKE 'WAREHOUSE' IN USER;
-- If empty or NULL, tools will FAIL silently or error out!

-- Create warehouse if needed:
CREATE WAREHOUSE IF NOT EXISTS <WH_NAME>
    WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE;

-- Set as default for current user:
ALTER USER <USERNAME> SET DEFAULT_WAREHOUSE = '<WH_NAME>';

-- INSTALL

-- Install from an application package (same account)
CREATE APPLICATION <APP_NAME> FROM APPLICATION PACKAGE <PKG>;

-- Install from a listing (cross-account)
CREATE APPLICATION <APP_NAME> FROM LISTING '<LISTING_ID>';

-- To reinstall / replace an existing app:
DROP APPLICATION IF EXISTS <APP_NAME>;
CREATE APPLICATION <APP_NAME> FROM APPLICATION PACKAGE <PKG>;

-- Upgrade an existing app to the latest released version (no reinstall needed):
-- Works for both provider-side test apps and consumer-installed apps.
ALTER APPLICATION <APP_NAME> UPGRADE;

-- POST-INSTALL VERIFICATION

-- Check schemas are accessible:
SHOW SCHEMAS IN APPLICATION <APP_NAME>;

-- Check tables/views:
SHOW TABLES IN <APP_NAME>.<SCHEMA_NAME>;
SHOW VIEWS IN <APP_NAME>.<SCHEMA_NAME>;

-- Check functions/procedures:
SHOW USER FUNCTIONS IN <APP_NAME>.<SCHEMA_NAME>;
SHOW PROCEDURES IN <APP_NAME>.<SCHEMA_NAME>;

-- Check Cortex Search services:
SHOW CORTEX SEARCH SERVICES IN <APP_NAME>.<SCHEMA_NAME>;

-- Test a UDF (requires warehouse):
SELECT <APP_NAME>.<SCHEMA>.<FUNCTION_NAME>('<PARAM>');

-- Test a procedure (requires warehouse):
CALL <APP_NAME>.<SCHEMA>.<PROCEDURE_NAME>(<PARAMS>);

-- (Reading/modifying an existing package is covered in the section above.)

