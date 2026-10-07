/* =====================================================================================
   Enterprise Search demo -- 20 - Verify (Step 6) + retrieval preview + cited RAG answers

   Run AFTER 10_pipeline.sql has executed and the DTs + search service have refreshed.
   Substitute {database} / {schema} / {warehouse} before running.
   ===================================================================================== */

USE DATABASE {database};
USE SCHEMA {database}.{schema};
USE WAREHOUSE {warehouse};

-- ---------------------------------------------------------------------------------------
-- Step 6 - MANDATORY: every DT must be INCREMENTAL (FULL re-runs AI on every file/refresh).
-- ---------------------------------------------------------------------------------------
SHOW DYNAMIC TABLES LIKE 'DT_DEMO_ESR%' IN SCHEMA {database}.{schema};
SELECT "name", "refresh_mode", "refresh_mode_reason"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
ORDER BY "name";

-- Pipeline health + row counts (run once refreshes complete).
SELECT 'file_log' AS layer, COUNT(*) AS n FROM DEMO_ESR_FILE_LOG
UNION ALL SELECT 'parsed',   COUNT(*) FROM DT_DEMO_ESR_PARSED
UNION ALL SELECT 'pages',    COUNT(*) FROM DT_DEMO_ESR_PAGES
UNION ALL SELECT 'figures',  COUNT(*) FROM DT_DEMO_ESR_FIGURES
UNION ALL SELECT 'enriched', COUNT(*) FROM DT_DEMO_ESR_ENRICHED
UNION ALL SELECT 'chunks',   COUNT(*) FROM DT_DEMO_ESR_CHUNKS
ORDER BY layer;

-- Spot-check that chart vision produced narratives (and how many pages had charts).
SELECT COMPANY,
       COUNT(*)                                        AS pages_with_image,
       COUNT_IF(CHART_NARRATIVE NOT ILIKE 'NO_CHART%') AS pages_with_charts
FROM DT_DEMO_ESR_FIGURES
GROUP BY COMPANY
ORDER BY COMPANY;

-- ---------------------------------------------------------------------------------------
-- Raw retrieval preview (no LLM) - confirms the index serves relevant chunks.
-- ---------------------------------------------------------------------------------------
SELECT v.value:COMPANY::STRING AS COMPANY, v.value:PAGE::INT AS PAGE,
       LEFT(v.value:CHUNK::STRING, 240) AS CHUNK_PREVIEW
FROM TABLE(FLATTEN(input => PARSE_JSON(
      SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
        '{database}.{schema}.DEMO_ESR_SEARCH',
        '{"query":"foreign exchange currency risk exposure","columns":["CHUNK","COMPANY","PAGE"],"limit":6}'
      ))['results'])) v;

-- ---------------------------------------------------------------------------------------
-- RAG Q1 - Cross-filing risk search: which companies flag FX / currency risk?
-- ---------------------------------------------------------------------------------------
WITH hits AS (
  SELECT v.value:CHUNK::STRING AS CHUNK, v.value:COMPANY::STRING AS SLUG, v.value:PAGE::INT AS PAGE
  FROM TABLE(FLATTEN(input => PARSE_JSON(
        SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
          '{database}.{schema}.DEMO_ESR_SEARCH',
          '{"query":"Which companies flag foreign-exchange or currency risk as a major exposure?","columns":["CHUNK","COMPANY","PAGE"],"limit":10}'
        ))['results'])) v
),
ctx AS (
  SELECT h.CHUNK, h.PAGE, COALESCE(co.COMPANY, h.SLUG) AS COMPANY
  FROM hits h LEFT JOIN DEMO_ESR_COMPANIES co ON co.SLUG = h.SLUG
)
SELECT AI_COMPLETE('claude-4-sonnet',
  'Answer the question using ONLY the provided context from company annual reports. '
  || 'Cite the company and page for every claim, like (Company, p.N). If the context is '
  || 'insufficient, say so.\n\nQuestion: Which companies flag foreign-exchange or currency '
  || 'risk as a major exposure, and how do they describe it?\n\nContext:\n'
  || LISTAGG(COMPANY || ' (p.' || PAGE || '): ' || CHUNK, '\n---\n')
       WITHIN GROUP (ORDER BY COMPANY, PAGE)
) AS ANSWER
FROM ctx;

-- ---------------------------------------------------------------------------------------
-- RAG Q2 - Comparative theme: AI / R&D / productivity investment across filings.
-- ---------------------------------------------------------------------------------------
WITH hits AS (
  SELECT v.value:CHUNK::STRING AS CHUNK, v.value:COMPANY::STRING AS SLUG, v.value:PAGE::INT AS PAGE
  FROM TABLE(FLATTEN(input => PARSE_JSON(
        SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
          '{database}.{schema}.DEMO_ESR_SEARCH',
          '{"query":"investment in AI, technology, R&D, digital and productivity","columns":["CHUNK","COMPANY","PAGE"],"limit":12}'
        ))['results'])) v
),
ctx AS (
  SELECT h.CHUNK, h.PAGE, COALESCE(co.COMPANY, h.SLUG) AS COMPANY
  FROM hits h LEFT JOIN DEMO_ESR_COMPANIES co ON co.SLUG = h.SLUG
)
SELECT AI_COMPLETE('claude-4-sonnet',
  'Using ONLY the context from these company annual reports, compare what each company says '
  || 'about investment in AI, technology, R&D, and productivity. Give one short paragraph per '
  || 'company and cite (Company, p.N).\n\nContext:\n'
  || LISTAGG(COMPANY || ' (p.' || PAGE || '): ' || CHUNK, '\n---\n')
       WITHIN GROUP (ORDER BY COMPANY, PAGE)
) AS ANSWER
FROM ctx;

-- ---------------------------------------------------------------------------------------
-- RAG Q3 - CHART SEARCHABILITY hero: read a chart that exists only as an image.
--          Filter to P&G via the COMPANY attribute; the answer should reflect the
--          net-sales-by-segment / by-geography charts surfaced by DT_DEMO_ESR_FIGURES.
-- ---------------------------------------------------------------------------------------
WITH hits AS (
  SELECT v.value:CHUNK::STRING AS CHUNK, v.value:COMPANY::STRING AS SLUG, v.value:PAGE::INT AS PAGE
  FROM TABLE(FLATTEN(input => PARSE_JSON(
        SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
          '{database}.{schema}.DEMO_ESR_SEARCH',
          '{"query":"net sales by business segment and by geographic region chart breakdown percentages","columns":["CHUNK","COMPANY","PAGE"],"filter":{"@eq":{"COMPANY":"pg"}},"limit":8}'
        ))['results'])) v
),
ctx AS (
  SELECT h.CHUNK, h.PAGE, COALESCE(co.COMPANY, h.SLUG) AS COMPANY
  FROM hits h LEFT JOIN DEMO_ESR_COMPANIES co ON co.SLUG = h.SLUG
)
SELECT AI_COMPLETE('claude-4-sonnet',
  'Using ONLY the context, describe what Procter and Gamble net-sales-by-segment and '
  || 'net-sales-by-geography charts show, including the segment and region percentages. '
  || 'Cite the page(s).\n\nContext:\n'
  || LISTAGG(COMPANY || ' (p.' || PAGE || '): ' || CHUNK, '\n---\n')
       WITHIN GROUP (ORDER BY COMPANY, PAGE)
) AS ANSWER
FROM ctx;
