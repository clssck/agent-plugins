/* =====================================================================================
   Customer 360 demo -- 00 - Setup
   Pre-loaded structured tables + a directory stage for unstructured customer docs, plus the
   ingestion layer (file log with a CONTENT column + stream + suspended task).

   The hero of this demo is FUSION: six structured tables (customers, products, transactions,
   daily telemetry, survey scores, campaigns) are joined with AI signals extracted from
   unstructured docs (support tickets, chat transcripts, survey comments, ...) into one
   per-customer 360 record with a risk tier + route, plus a product-health landscape.

   The structured tables are loaded by the sourcing script; the agent must JOIN them, not
   recreate them. Unstructured docs land on the docs stage; their text is backfilled into
   the file log's CONTENT column so the AI signal step reads it directly.

   Substitute {database} / {schema} / {warehouse} before running.
   Run order: 00_setup.sql -> source_customer360.py (load structured + PUT docs + backfill)
              -> 10_pipeline.sql -> 20_insights.sql
   ===================================================================================== */

USE DATABASE {database};
USE SCHEMA {database}.{schema};
USE WAREHOUSE {warehouse};

-- ---------------------------------------------------------------------------------------
-- Structured tables (pre-loaded by the sourcing script; the pipeline JOINs, never recreates).
-- ---------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS DEMO_C360_CUSTOMERS (
  CUSTOMER_ID     STRING,
  COMPANY_NAME    STRING,
  SEGMENT         STRING,
  REGION          STRING,
  TIER            STRING,       -- account tier (static attribute; RISK_TIER is computed downstream)
  SIGNUP_DATE     DATE,
  PRIMARY_PRODUCT STRING,
  SEATS           NUMBER,
  COHORT_STORY    STRING        -- the planted behavior class; fusion uses it as a guardrail
);

CREATE TABLE IF NOT EXISTS DEMO_C360_PRODUCTS (
  PRODUCT_SLUG STRING,
  PRODUCT_NAME STRING,
  CATEGORY     STRING
);

CREATE TABLE IF NOT EXISTS DEMO_C360_TRANSACTIONS (
  TXN_ID      STRING,
  CUSTOMER_ID STRING,
  PRODUCT     STRING,
  AMOUNT      NUMBER(12,2),
  CURRENCY    STRING,
  TXN_DATE    DATE,
  TXN_TYPE    STRING
);

CREATE TABLE IF NOT EXISTS DEMO_C360_TELEMETRY_DAILY (
  CUSTOMER_ID            STRING,
  PRODUCT                STRING,
  DATE                   DATE,
  DAU                    NUMBER,
  SESSIONS               NUMBER,
  ERROR_RATE             FLOAT,
  LATENCY_P95_MS         NUMBER,
  FEATURE_ADOPTION_SCORE FLOAT
);

CREATE TABLE IF NOT EXISTS DEMO_C360_SURVEY_SCORES (
  CUSTOMER_ID STRING,
  QUARTER     STRING,
  NPS         NUMBER,
  CSAT        NUMBER,
  RESPONDED   BOOLEAN
);

CREATE TABLE IF NOT EXISTS DEMO_C360_CAMPAIGNS (
  CUSTOMER_ID   STRING,
  CAMPAIGN_ID   STRING,
  CAMPAIGN_NAME STRING,
  CHANNEL       STRING,
  SENT_DATE     DATE,
  OPENED        BOOLEAN,
  CLICKED       BOOLEAN
);

-- CSV format for the structured loads (see the sourcing script).
CREATE FILE FORMAT IF NOT EXISTS DEMO_C360_CSV_FMT
  TYPE = CSV SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '"';

-- Internal stage for the structured CSVs (no directory needed).
CREATE STAGE IF NOT EXISTS DEMO_C360_STRUCTURED_STAGE
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');

-- ---------------------------------------------------------------------------------------
-- Unstructured docs: directory-enabled stage + a file log carrying the doc CONTENT.
-- ---------------------------------------------------------------------------------------
CREATE STAGE IF NOT EXISTS DEMO_C360_DOCS_STAGE
  DIRECTORY = (ENABLE = TRUE)
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');

CREATE TABLE IF NOT EXISTS DEMO_C360_FILE_LOG (
  RELATIVE_PATH STRING,
  FILE_NAME     STRING,
  FILE_SIZE     NUMBER,
  LAST_MODIFIED TIMESTAMP_LTZ,
  FILE_URL      STRING,
  CONTENT       STRING,          -- backfilled from the local doc text by the sourcing script
  INGESTED_AT   TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
ALTER TABLE DEMO_C360_FILE_LOG SET CHANGE_TRACKING = TRUE;

-- Text file format (whole file as one string) -- used if you prefer to backfill CONTENT in SQL.
CREATE FILE FORMAT IF NOT EXISTS DEMO_C360_TXT_FMT
  TYPE = CSV FIELD_DELIMITER = NONE RECORD_DELIMITER = NONE;

-- Stream on the docs stage. Create it BEFORE the docs are PUT + REFRESH'd so the initial files
-- register as INSERT rows for the backfill (the stream baseline is the empty stage).
CREATE OR REPLACE STREAM DEMO_C360_STAGE_STREAM
  ON STAGE DEMO_C360_DOCS_STAGE;

-- Ingestion task: lands new customer docs into the file log exactly once.
-- Starts SUSPENDED. Resume only after refresh modes are verified and quality checked.
CREATE OR REPLACE TASK DEMO_C360_INGEST_TASK
  WAREHOUSE = {warehouse}
  SCHEDULE = '5 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('{database}.{schema}.DEMO_C360_STAGE_STREAM')
AS
  INSERT INTO DEMO_C360_FILE_LOG
    (RELATIVE_PATH, FILE_NAME, FILE_SIZE, LAST_MODIFIED, FILE_URL)
  SELECT
    RELATIVE_PATH,
    SPLIT_PART(RELATIVE_PATH, '/', -1),
    SIZE,
    LAST_MODIFIED::TIMESTAMP_LTZ,
    FILE_URL
  FROM DEMO_C360_STAGE_STREAM
  WHERE METADATA$ACTION = 'INSERT'
    AND RELATIVE_PATH ILIKE 'incoming/%';

ALTER TASK DEMO_C360_INGEST_TASK SUSPEND;
