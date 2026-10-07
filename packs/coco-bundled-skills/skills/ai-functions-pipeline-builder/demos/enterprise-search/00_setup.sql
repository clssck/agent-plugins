/* =====================================================================================
   Enterprise Search demo -- 00 - Setup
   Schema context, directory stage, ingestion layer (file log + stream + suspended task),
   and a small company dimension for friendly display names.

   Substitute {database} / {schema} / {warehouse} before running.
   Run order: 00_setup.sql -> source_enterprise_search.py (PUT + REFRESH)
              -> EXECUTE TASK DEMO_ESR_INGEST_TASK -> 10_pipeline.sql -> 20_rag.sql
   ===================================================================================== */

USE DATABASE {database};
USE SCHEMA {database}.{schema};
USE WAREHOUSE {warehouse};

-- ---------------------------------------------------------------------------------------
-- Directory-enabled stage. Server-side encryption is REQUIRED for TO_FILE + AI functions.
-- ---------------------------------------------------------------------------------------
CREATE STAGE IF NOT EXISTS DEMO_ESR_DOCS_STAGE
  DIRECTORY = (ENABLE = TRUE)
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');

-- ---------------------------------------------------------------------------------------
-- Ingestion bridge: a change-tracked table so downstream dynamic tables can be INCREMENTAL.
-- ---------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS DEMO_ESR_FILE_LOG (
  RELATIVE_PATH STRING,
  FILE_NAME     STRING,
  FILE_SIZE     NUMBER,
  LAST_MODIFIED TIMESTAMP_LTZ,
  FILE_URL      STRING,
  INGESTED_AT   TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);
ALTER TABLE DEMO_ESR_FILE_LOG SET CHANGE_TRACKING = TRUE;

-- Stream on the stage. Create it BEFORE the corpus is PUT + REFRESH'd so the initial files
-- register as INSERT rows for the backfill (the stream baseline is the empty stage).
CREATE OR REPLACE STREAM DEMO_ESR_STAGE_STREAM
  ON STAGE DEMO_ESR_DOCS_STAGE;

-- Ingestion task: lands new report PDFs and page PNGs into the file log exactly once.
-- Starts SUSPENDED (default). Resume only after refresh modes are verified and quality checked.
CREATE OR REPLACE TASK DEMO_ESR_INGEST_TASK
  WAREHOUSE = {warehouse}
  SCHEDULE = '5 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('{database}.{schema}.DEMO_ESR_STAGE_STREAM')
AS
  INSERT INTO DEMO_ESR_FILE_LOG
    (RELATIVE_PATH, FILE_NAME, FILE_SIZE, LAST_MODIFIED, FILE_URL)
  SELECT
    RELATIVE_PATH,
    SPLIT_PART(RELATIVE_PATH, '/', -1),
    SIZE,
    LAST_MODIFIED::TIMESTAMP_LTZ,
    FILE_URL
  FROM DEMO_ESR_STAGE_STREAM
  WHERE METADATA$ACTION = 'INSERT'
    AND ( RELATIVE_PATH ILIKE '%.pdf'
       OR RELATIVE_PATH ILIKE '%.png'
       OR RELATIVE_PATH ILIKE '%.jpg'
       OR RELATIVE_PATH ILIKE '%.jpeg' );

-- ---------------------------------------------------------------------------------------
-- Small company dimension (friendly display names in results). Mirrors the corpus manifest.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE TABLE DEMO_ESR_COMPANIES (
  SLUG STRING, COMPANY STRING, TICKER STRING, KIND STRING
);
INSERT INTO DEMO_ESR_COMPANIES (SLUG, COMPANY, TICKER, KIND) VALUES
  ('unilever', 'Unilever',              'ULVR', 'glossy'),
  ('nestle',   'Nestlé',                'NESN', 'glossy'),
  ('pg',       'Procter & Gamble',      'PG',   'glossy'),
  ('pepsico',  'PepsiCo',               'PEP',  'glossy'),
  ('cocacola', 'The Coca-Cola Company', 'KO',   '10k');
