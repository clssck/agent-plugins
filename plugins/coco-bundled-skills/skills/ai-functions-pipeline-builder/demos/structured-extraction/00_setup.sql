/* =====================================================================================
   Structured Extraction demo -- 00 - Setup
   Schema context, directory stage, JSON file format, ingestion layer (file log + stream +
   suspended task), and a ground-truth table for the "AI vs truth" accuracy view.

   Domain: auto-insurance claims intake. Mixed document types land in one stage folder
   (FNOL forms, repair estimates, police reports, damage photos) plus junk. The pipeline
   classifies each doc, routes it to a type-specific extractor, assesses photos with vision,
   assembles one record per CLAIM_NO, then decides + triages into lanes.

   Substitute {database} / {schema} / {warehouse} before running.
   Run order: 00_setup.sql -> source_structured_extraction.py (PUT + REFRESH + backfill + load truth)
              -> 10_pipeline.sql -> 20_triage.sql
   ===================================================================================== */

USE DATABASE {database};
USE SCHEMA {database}.{schema};
USE WAREHOUSE {warehouse};

-- ---------------------------------------------------------------------------------------
-- Directory-enabled stage. Server-side encryption is REQUIRED for TO_FILE + AI functions.
-- ---------------------------------------------------------------------------------------
CREATE STAGE IF NOT EXISTS DEMO_CLM_DOCS_STAGE
  DIRECTORY = (ENABLE = TRUE)
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');

-- JSON format for loading the corpus manifest into the ground-truth table (see the script).
CREATE FILE FORMAT IF NOT EXISTS DEMO_CLM_JSON_FMT TYPE = JSON;

-- ---------------------------------------------------------------------------------------
-- Ingestion bridge: a change-tracked table so downstream dynamic tables can be INCREMENTAL.
-- ---------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS DEMO_CLM_FILE_LOG (
  RELATIVE_PATH STRING,
  FILE_NAME     STRING,
  FILE_SIZE     NUMBER,
  LAST_MODIFIED TIMESTAMP_LTZ,
  FILE_URL      STRING,
  INGESTED_AT   TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
ALTER TABLE DEMO_CLM_FILE_LOG SET CHANGE_TRACKING = TRUE;

-- Stream on the stage. Create it BEFORE the corpus is PUT + REFRESH'd so the initial files
-- register as INSERT rows for the backfill (the stream baseline is the empty stage).
CREATE OR REPLACE STREAM DEMO_CLM_STAGE_STREAM
  ON STAGE DEMO_CLM_DOCS_STAGE;

-- Ingestion task: lands new claim docs (PDFs + photos) into the file log exactly once.
-- Starts SUSPENDED (default). Resume only after refresh modes are verified and quality checked.
CREATE OR REPLACE TASK DEMO_CLM_INGEST_TASK
  WAREHOUSE = {warehouse}
  SCHEDULE = '5 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('{database}.{schema}.DEMO_CLM_STAGE_STREAM')
AS
  INSERT INTO DEMO_CLM_FILE_LOG
    (RELATIVE_PATH, FILE_NAME, FILE_SIZE, LAST_MODIFIED, FILE_URL)
  SELECT
    RELATIVE_PATH,
    SPLIT_PART(RELATIVE_PATH, '/', -1),
    SIZE,
    LAST_MODIFIED::TIMESTAMP_LTZ,
    FILE_URL
  FROM DEMO_CLM_STAGE_STREAM
  WHERE METADATA$ACTION = 'INSERT'
    AND ( RELATIVE_PATH ILIKE 'incoming/%.pdf'
       OR RELATIVE_PATH ILIKE 'incoming/%.jpg'
       OR RELATIVE_PATH ILIKE 'incoming/%.jpeg'
       OR RELATIVE_PATH ILIKE 'incoming/%.png' );

-- ---------------------------------------------------------------------------------------
-- Ground-truth table (loaded from the synthesis manifest by the sourcing script). NOT used by
-- the pipeline -- only for the demo's "AI vs truth" accuracy view (20_triage.sql, section D).
-- Synthesis planted these values + fraud cues; the pipeline never sees them.
-- ---------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS DEMO_CLM_GROUND_TRUTH (
  CLAIM_NO        STRING,
  CLAIMANT        STRING,
  DATE_OF_LOSS    STRING,
  AMOUNT_CLAIMED  NUMBER(12,2),
  ESTIMATE_TOTAL  NUMBER(12,2),
  SEVERITY        STRING,
  FAULT_PARTY     STRING,
  PLANTED_FRAUD   STRING,
  BRAND           STRING,
  SCENARIO        STRING
);
