/* =====================================================================================
   Enterprise Search demo -- 10 - Processing chain (incremental dynamic tables) + Cortex Search

     DEMO_ESR_FILE_LOG
       -> DT_DEMO_ESR_PARSED     AI_PARSE_DOCUMENT(LAYOUT, page_split)   PDFs -> per-page markdown
       -> DT_DEMO_ESR_PAGES      FLATTEN :pages array                    one row per (company, page)
       -> DT_DEMO_ESR_FIGURES    AI_COMPLETE(vision) over page PNGs       chart/figure narrative per page
       -> DT_DEMO_ESR_ENRICHED   page text + chart narrative              merged searchable content
       -> DT_DEMO_ESR_CHUNK_ARR  SPLIT_TEXT_RECURSIVE_CHARACTER           chunk array (materialized)
       -> DT_DEMO_ESR_CHUNKS     FLATTEN chunk array                      one row per chunk
       -> DEMO_ESR_SEARCH        CREATE CORTEX SEARCH SERVICE             auto-refreshing index

   All DTs are INCREMENTAL: each AI function runs once per new file, not once per refresh.
   Conventions: AI_* funcs unprefixed; TO_FILE is 2-arg; AI calls inline (never inside LATERAL);
   LATERAL FLATTEN only over already-materialized array columns; intermediate DTs
   TARGET_LAG = DOWNSTREAM. Compile-validate before executing; then verify every DT is
   INCREMENTAL via SHOW DYNAMIC TABLES (see 20_rag.sql, Step 6).

   Substitute {database} / {schema} / {warehouse} before running.
   ===================================================================================== */

USE DATABASE {database};
USE SCHEMA {database}.{schema};
USE WAREHOUSE {warehouse};

-- ---------------------------------------------------------------------------------------
-- Layer 2 - Parse PDFs -> per-page markdown (LAYOUT preserves tables/headings; page_split
--           keeps long reports under the per-call token limit and yields a page index).
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_ESR_PARSED
  TARGET_LAG = DOWNSTREAM
  WAREHOUSE = {warehouse}
  REFRESH_MODE = INCREMENTAL
AS
  SELECT
    fl.RELATIVE_PATH,
    SPLIT_PART(SPLIT_PART(fl.RELATIVE_PATH, '/', -1), '.', 1) AS COMPANY,   -- reports/<slug>.pdf
    fl.INGESTED_AT,
    AI_PARSE_DOCUMENT(
      TO_FILE('@DEMO_ESR_DOCS_STAGE', fl.RELATIVE_PATH),
      {'mode': 'LAYOUT', 'page_split': TRUE}
    ) AS RAW_PARSE
  FROM DEMO_ESR_FILE_LOG fl
  WHERE fl.RELATIVE_PATH ILIKE 'reports/%' AND fl.RELATIVE_PATH ILIKE '%.pdf';

-- Layer 2b - Flatten the materialized :pages array -> one row per page (1-based PAGE).
CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_ESR_PAGES
  TARGET_LAG = DOWNSTREAM
  WAREHOUSE = {warehouse}
  REFRESH_MODE = INCREMENTAL
AS
  SELECT
    p.RELATIVE_PATH,
    p.COMPANY,
    f.value:index::INT + 1        AS PAGE,
    f.value:content::STRING       AS CONTENT
  FROM DT_DEMO_ESR_PARSED p,
       LATERAL FLATTEN(input => p.RAW_PARSE:pages) f;

-- ---------------------------------------------------------------------------------------
-- Layer 3 - Chart/figure vision over per-page PNGs. Inline AI_COMPLETE single-image call
--           returns a prose narrative of every chart on the page, so chart CONTENT becomes
--           searchable text. Page PNGs staged at pages/<slug>/<n>.png.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_ESR_FIGURES
  TARGET_LAG = DOWNSTREAM
  WAREHOUSE = {warehouse}
  REFRESH_MODE = INCREMENTAL
AS
  SELECT
    fl.RELATIVE_PATH,
    SPLIT_PART(fl.RELATIVE_PATH, '/', 2)                                       AS COMPANY,  -- pages/<slug>/<n>.png
    TRY_CAST(SPLIT_PART(SPLIT_PART(fl.RELATIVE_PATH, '/', -1), '.', 1) AS INT) AS PAGE,
    AI_COMPLETE(
      'claude-4-sonnet',
      'This image is one page of a company annual report. Describe any charts, graphs, or '
      || 'figures on the page: for each, state its title, the chart type, what the axes/'
      || 'segments represent, the overall trend, and the key numbers or percentages shown. '
      || 'Also capture any financial-highlight callouts (e.g. net sales, growth, margin). '
      || 'Write a concise, self-contained prose description (no markdown, no preamble). '
      || 'If the page has no charts or figures, reply exactly: NO_CHART.',
      TO_FILE('@DEMO_ESR_DOCS_STAGE', fl.RELATIVE_PATH)
    ) AS CHART_NARRATIVE
  FROM DEMO_ESR_FILE_LOG fl
  WHERE fl.RELATIVE_PATH ILIKE 'pages/%'
    AND ( fl.RELATIVE_PATH ILIKE '%.png'
       OR fl.RELATIVE_PATH ILIKE '%.jpg'
       OR fl.RELATIVE_PATH ILIKE '%.jpeg' );

-- ---------------------------------------------------------------------------------------
-- Layer 4 - Enrich: merge page text with the chart narrative for that page (join over two
--           materialized DTs -> stays incremental). Pages with no rendered image (or no
--           chart) flow through with body text only.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_ESR_ENRICHED
  TARGET_LAG = DOWNSTREAM
  WAREHOUSE = {warehouse}
  REFRESH_MODE = INCREMENTAL
AS
  SELECT
    pg.RELATIVE_PATH,
    pg.COMPANY,
    pg.PAGE,
    pg.CONTENT
      || CASE
           WHEN fig.CHART_NARRATIVE IS NOT NULL
            AND fig.CHART_NARRATIVE NOT ILIKE 'NO_CHART%'
           THEN '\n\n[Charts and figures on this page]\n' || fig.CHART_NARRATIVE
           ELSE ''
         END AS CONTENT
  FROM DT_DEMO_ESR_PAGES pg
  LEFT JOIN DT_DEMO_ESR_FIGURES fig
    ON pg.COMPANY = fig.COMPANY AND pg.PAGE = fig.PAGE;

-- ---------------------------------------------------------------------------------------
-- Layer 5 - Chunking: materialize the split array, then flatten it.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_ESR_CHUNK_ARR
  TARGET_LAG = DOWNSTREAM
  WAREHOUSE = {warehouse}
  REFRESH_MODE = INCREMENTAL
AS
  SELECT
    e.RELATIVE_PATH, e.COMPANY, e.PAGE,
    SNOWFLAKE.CORTEX.SPLIT_TEXT_RECURSIVE_CHARACTER(e.CONTENT, 'markdown', 1500, 200) AS CHUNKS
  FROM DT_DEMO_ESR_ENRICHED e
  WHERE e.CONTENT IS NOT NULL AND LENGTH(e.CONTENT) > 0;

CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_ESR_CHUNKS
  TARGET_LAG = DOWNSTREAM
  WAREHOUSE = {warehouse}
  REFRESH_MODE = INCREMENTAL
AS
  SELECT
    a.RELATIVE_PATH,
    a.COMPANY,
    a.PAGE,
    f.index           AS CHUNK_NO,
    f.value::STRING   AS CHUNK
  FROM DT_DEMO_ESR_CHUNK_ARR a,
       LATERAL FLATTEN(input => a.CHUNKS) f;

-- ---------------------------------------------------------------------------------------
-- Layer 6 - Cortex Search sink. Self-refreshes from DT_DEMO_ESR_CHUNKS within TARGET_LAG.
--           ATTRIBUTES are filterable (e.g. by COMPANY) and must all appear in the query.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE CORTEX SEARCH SERVICE DEMO_ESR_SEARCH
  ON CHUNK
  ATTRIBUTES COMPANY, FILE_PATH, PAGE
  WAREHOUSE = {warehouse}
  TARGET_LAG = '1 hour'
  EMBEDDING_MODEL = 'snowflake-arctic-embed-l-v2.0'
AS (
  SELECT
    c.CHUNK,
    c.COMPANY,
    c.RELATIVE_PATH AS FILE_PATH,
    c.PAGE
  FROM DT_DEMO_ESR_CHUNKS c
);
