/* =====================================================================================
   Corpus Intelligence demo -- 00 - Setup
   Schema context, directory stage, JSON file format, ingestion layer (file log + stream +
   suspended task), and the paper / drug dimension tables.

   Domain: GLP-1 receptor-agonist literature (semaglutide, tirzepatide, liraglutide,
   dulaglutide, orforglipron) -- open-access papers discovered via the Europe PMC REST API.
   The pipeline reads across the whole corpus: per-paper significance + trial fields (numbers
   read off figures as well as text), then cross-document trends and an AI-written
   competitive-landscape briefing per drug.

   Substitute {database} / {schema} / {warehouse} before running.
   Run order: 00_setup.sql -> source_corpus_intelligence.py (PUT + REFRESH + backfill + load dim)
              -> 10_pipeline.sql -> 20_analytics.sql
   ===================================================================================== */

USE DATABASE {database};
USE SCHEMA {database}.{schema};
USE WAREHOUSE {warehouse};

-- ---------------------------------------------------------------------------------------
-- Directory-enabled stage. Server-side encryption is REQUIRED for TO_FILE + AI functions.
-- ---------------------------------------------------------------------------------------
CREATE STAGE IF NOT EXISTS DEMO_RES_DOCS_STAGE
  DIRECTORY = (ENABLE = TRUE)
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');

-- JSON format for loading the corpus manifest into the paper dimension (see the script).
CREATE FILE FORMAT IF NOT EXISTS DEMO_RES_JSON_FMT TYPE = JSON;

-- ---------------------------------------------------------------------------------------
-- Ingestion bridge: a change-tracked table so downstream dynamic tables can be INCREMENTAL.
-- ---------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS DEMO_RES_FILE_LOG (
  RELATIVE_PATH STRING,
  FILE_NAME     STRING,
  FILE_SIZE     NUMBER,
  LAST_MODIFIED TIMESTAMP_LTZ,
  FILE_URL      STRING,
  INGESTED_AT   TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
ALTER TABLE DEMO_RES_FILE_LOG SET CHANGE_TRACKING = TRUE;

-- Stream on the stage. Create it BEFORE the corpus is PUT + REFRESH'd so the initial files
-- register as INSERT rows for the backfill (the stream baseline is the empty stage).
CREATE OR REPLACE STREAM DEMO_RES_STAGE_STREAM
  ON STAGE DEMO_RES_DOCS_STAGE;

-- Ingestion task: lands new paper PDFs and page PNGs into the file log exactly once.
-- Starts SUSPENDED (default). Resume only after refresh modes are verified and quality checked.
CREATE OR REPLACE TASK DEMO_RES_INGEST_TASK
  WAREHOUSE = {warehouse}
  SCHEDULE = '5 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('{database}.{schema}.DEMO_RES_STAGE_STREAM')
AS
  INSERT INTO DEMO_RES_FILE_LOG
    (RELATIVE_PATH, FILE_NAME, FILE_SIZE, LAST_MODIFIED, FILE_URL)
  SELECT
    RELATIVE_PATH,
    SPLIT_PART(RELATIVE_PATH, '/', -1),
    SIZE,
    LAST_MODIFIED::TIMESTAMP_LTZ,
    FILE_URL
  FROM DEMO_RES_STAGE_STREAM
  WHERE METADATA$ACTION = 'INSERT'
    AND ( RELATIVE_PATH ILIKE 'papers/%.pdf'
       OR RELATIVE_PATH ILIKE 'pages/%.png'
       OR RELATIVE_PATH ILIKE 'pages/%.jpg'
       OR RELATIVE_PATH ILIKE 'pages/%.jpeg' );

-- ---------------------------------------------------------------------------------------
-- Paper dimension (loaded from the corpus manifest by the sourcing script). DRUG is the
-- sourcing bucket and the cross-document grouping key for the landscape -- reliable provenance.
-- Clinical fields (phase, sample size, endpoint, sponsor, ...) are NOT stored here; they are
-- AI-extracted from the documents.
-- ---------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS DEMO_RES_PAPERS (
  PAPER_ID STRING,
  DRUG     STRING,   -- bucket slug: semaglutide | tirzepatide | liraglutide | dulaglutide | orforglipron
  TITLE    STRING,
  JOURNAL  STRING,
  YEAR     NUMBER,
  PMCID    STRING,
  DOI      STRING
);

-- Drug display names (friendly labels for the landscape / trend output).
CREATE OR REPLACE TABLE DEMO_RES_DRUGS (
  SLUG STRING, DISPLAY STRING
);
INSERT INTO DEMO_RES_DRUGS (SLUG, DISPLAY) VALUES
  ('semaglutide',  'Semaglutide'),
  ('tirzepatide',  'Tirzepatide'),
  ('liraglutide',  'Liraglutide'),
  ('dulaglutide',  'Dulaglutide'),
  ('orforglipron', 'Orforglipron');
