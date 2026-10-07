/* =====================================================================================
   Customer 360 demo -- 20 - preflight + AI refresh (cost-gated) + verify + deliverables

   RUN ORDER: Section 0 (preflight, zero-spend) FIRST, then -- only after the cost gate is
   approved -- Section A (spends). Section 0 verifies refresh modes BEFORE any AI runs, because a
   FULL per-document/per-record DT would re-run every AI function on every refresh. Everything up
   to Section A (00_setup, source_customer360.py, 10_pipeline) is zero-spend: the dynamic tables
   were created INITIALIZE = ON_SCHEDULE and the deliverable DTs left suspended.

   Sections 0, B (verify), C (health), D (deliverables) are read-only -- safe to re-run anytime.

   Substitute {database} / {schema} / {warehouse} before running.
   ===================================================================================== */

USE DATABASE {database};
USE SCHEMA {database}.{schema};
USE WAREHOUSE {warehouse};

/* =======================================================================================
   SECTION 0 - PREFLIGHT (zero-spend).  Run immediately after 10_pipeline.sql, BEFORE Section A.
   MANDATORY: every DT must report refresh_mode = INCREMENTAL. A FULL per-document / per-record DT
   would re-run every AI function on every refresh -- stop and fix before spending a cent.
   =======================================================================================*/
SHOW DYNAMIC TABLES LIKE 'DT_DEMO_C360%';
SELECT "name", "refresh_mode", "refresh_mode_reason", "scheduling_state"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
ORDER BY "name";

/* =======================================================================================
   SECTION A - AI EXECUTION.  ***THIS SPENDS.***  Do not run before Section 0 passes + the cost gate.

   Cost drivers (default: claude-4-sonnet), default ~40-customer corpus (~48 docs):
     AI_CLASSIFY           ~48  (per-document: every doc, including junk)
     AI_COMPLETE sentiment ~44  (per-document: every non-'other' doc)
     AI_COMPLETE briefing   ~5  (per-product, once per health-landscape refresh -- NOT per doc)
     CORTEX SEARCH          --  a separate indexing + serving surface over the doc text
   Only the two per-document counts scale with new docs / --customers; the briefing scales with
   products (fixed at 5 here) and search is its own surface. See the demo SKILL.md for the
   current-rates pricing note.
   =======================================================================================*/

-- A1 - Optional cheap smoke FIRST (interactive): re-confirm the classifier on a couple of real
--      staged paths before the full sweep.
--
--   SELECT RELATIVE_PATH,
--     AI_CLASSIFY(TO_FILE('@DEMO_C360_DOCS_STAGE', RELATIVE_PATH),
--       ['support_ticket','chat_transcript','survey_comment','call_transcript','error_report','other']
--     ):labels[0]::STRING AS DOC_TYPE
--   FROM DEMO_C360_FILE_LOG
--   WHERE RELATIVE_PATH ILIKE 'incoming/%'
--   ORDER BY RELATIVE_PATH
--   LIMIT 4;

-- A2 - Full refresh, in dependency order, ONE pass. Each ALTER blocks until that layer finishes.
ALTER DYNAMIC TABLE DT_DEMO_C360_CLASSIFIED       REFRESH;   -- ~48 x AI_CLASSIFY
ALTER DYNAMIC TABLE DT_DEMO_C360_CUSTOMER_DOCS    REFRESH;
ALTER DYNAMIC TABLE DT_DEMO_C360_DOC_SIGNALS      REFRESH;   -- ~44 x AI_COMPLETE (sentiment)
ALTER DYNAMIC TABLE DT_DEMO_C360_CUSTOMER_RECORD  REFRESH;   -- the fusion JOIN (no AI)
ALTER DYNAMIC TABLE DT_DEMO_C360_SEARCH_CHUNKS    REFRESH;
ALTER DYNAMIC TABLE DT_DEMO_C360_HEALTH_LANDSCAPE REFRESH;   -- ~5 x AI_COMPLETE (briefing)

-- Cortex Search: created here (not in 10_pipeline) because a search service is active on
-- creation -- it indexes + serves, which spends. This is the enterprise-search head of the 360.
CREATE OR REPLACE CORTEX SEARCH SERVICE DEMO_C360_SEARCH
  ON CHUNK_TEXT
  ATTRIBUTES CUSTOMER_ID, DOC_TYPE, RELATIVE_PATH
  WAREHOUSE = {warehouse}
  TARGET_LAG = '1 hour'
AS (
  SELECT CUSTOMER_ID, RELATIVE_PATH, DOC_TYPE, CHUNK_TEXT
  FROM DT_DEMO_C360_SEARCH_CHUNKS
);

-- Keep the deliverable DTs live so they re-refresh on their 1h lag if the corpus changes. NOTE:
-- the ingest task only lands file METADATA; a new text doc also needs its CONTENT loaded (the
-- sourcing script does this) before it can be scored/searched. For a static demo, leave the task
-- suspended and treat this as a one-shot build.
ALTER DYNAMIC TABLE DT_DEMO_C360_CUSTOMER_RECORD  RESUME;
ALTER DYNAMIC TABLE DT_DEMO_C360_HEALTH_LANDSCAPE RESUME;
-- ALTER TASK DEMO_C360_INGEST_TASK RESUME;   -- continuous ingestion only; also requires CONTENT loads

/* =======================================================================================
   SECTION B - Post-refresh state: confirm the deliverable DTs are RESUMED (tracking their lag)
   and the search service exists. (Refresh modes were the pre-spend gate -- see Section 0.)
   =======================================================================================*/
SHOW DYNAMIC TABLES LIKE 'DT_DEMO_C360%';
SELECT "name", "refresh_mode", "scheduling_state", "target_lag"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
ORDER BY "name";

SHOW CORTEX SEARCH SERVICES LIKE 'DEMO_C360%';

/* =======================================================================================
   SECTION C - Pipeline health: classification distribution + per-layer row counts.
   =======================================================================================*/
-- Classification: every doc got a type; junk -> 'other' (the gate).
SELECT DOC_TYPE, COUNT(*) AS n FROM DT_DEMO_C360_CLASSIFIED GROUP BY DOC_TYPE ORDER BY n DESC;

SELECT 'file_log'        AS layer, COUNT(*) AS n FROM DEMO_C360_FILE_LOG
UNION ALL SELECT 'classified',      COUNT(*) FROM DT_DEMO_C360_CLASSIFIED
UNION ALL SELECT 'customer_docs',   COUNT(*) FROM DT_DEMO_C360_CUSTOMER_DOCS
UNION ALL SELECT 'doc_signals',     COUNT(*) FROM DT_DEMO_C360_DOC_SIGNALS
UNION ALL SELECT 'customer_record', COUNT(*) FROM DT_DEMO_C360_CUSTOMER_RECORD
UNION ALL SELECT 'search_chunks',   COUNT(*) FROM DT_DEMO_C360_SEARCH_CHUNKS
UNION ALL SELECT 'health_landscape',COUNT(*) FROM DT_DEMO_C360_HEALTH_LANDSCAPE
ORDER BY layer;

/* =======================================================================================
   SECTION D - Deliverables: the fusion payoff.
   =======================================================================================*/

-- D1 - Risk tier + route distribution across ALL customers (the headline: every customer is
--      scored, not just the ones who filed a ticket).
SELECT
  RISK_TIER,
  ROUTE,
  COUNT(*)                                          AS customers,
  ROUND(100 * RATIO_TO_REPORT(COUNT(*)) OVER (), 1) AS pct
FROM DT_DEMO_C360_CUSTOMER_RECORD
GROUP BY RISK_TIER, ROUTE
ORDER BY customers DESC;

-- D2 - High-risk customers with the fused evidence (structured facts + AI doc signal side by
--      side). This is the row a CSM acts on -- and the reason for the tier is legible.
SELECT
  CUSTOMER_ID,
  COMPANY_NAME,
  PRIMARY_PRODUCT,
  ROUND(TOTAL_CHARGED)          AS total_charged,
  NPS_Q2,
  ROUND(MAX_ERROR_RATE, 3)      AS max_error_rate,
  ROUND(DAU_DECLINE_PCT, 2)     AS dau_decline_pct,
  DOC_COUNT,
  NEG_DOC_COUNT,
  ROUTE
FROM DEMO_C360_HIGH_RISK
LIMIT 25;

-- D3 - The fusion proof: customers who look FINE on EVERY structured signal (no error spike, no
--      DAU decline, a healthy NPS > 8) but are still flagged risk purely because their docs read
--      negative. Structured-only monitoring would miss these entirely (the 'hidden_detractor'
--      cohort is planted to make this real). The NPS > 8 filter rules out survey-driven risk, so
--      the negative document is the only thing lifting them above 'low'.
SELECT
  CUSTOMER_ID, COMPANY_NAME, PRIMARY_PRODUCT, RISK_TIER, NPS_Q2,
  ROUND(MAX_ERROR_RATE, 3) AS max_error_rate, NEG_DOC_COUNT
FROM DT_DEMO_C360_CUSTOMER_RECORD
WHERE NEG_DOC_COUNT >= 1
  AND COALESCE(MAX_ERROR_RATE, 0) <= 0.05
  AND COALESCE(DAU_DECLINE_PCT, 0) > -0.15
  AND COALESCE(NPS_Q2, 10) > 8
  AND RISK_TIER <> 'low'
ORDER BY NEG_DOC_COUNT DESC, CUSTOMER_ID
LIMIT 20;

-- D4 - Product health landscape with the AI-written executive briefing.
SELECT
  PRODUCT,
  CUSTOMER_COUNT,
  ROUND(AVG_NPS_Q2, 1)        AS avg_nps_q2,
  ROUND(AVG_MAX_ERROR_RATE,3) AS avg_max_error_rate,
  HIGH_RISK_COUNT,
  EXEC_BRIEFING
FROM DT_DEMO_C360_HEALTH_LANDSCAPE
ORDER BY HIGH_RISK_COUNT DESC;

-- D5 - Cortex Search over the doc text: pull the exact evidence behind a risk tier.
--      Swap the query string for any theme (outage, cancel, billing, ...).
SELECT PARSE_JSON(
  SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
    'DEMO_C360_SEARCH',
    '{"query":"threatening to cancel the contract","columns":["CUSTOMER_ID","DOC_TYPE","CHUNK_TEXT"],"limit":5}'
  )
):results AS hits;

-- D6 - Fusion vs the planted cohort (COHORT_STORY, set at synthesis; the pipeline never keyed on
--      it except as a guardrail). Does the computed RISK_TIER line up with each cohort's intent?
SELECT
  cu.COHORT_STORY,
  COUNT(*)                              AS customers,
  COUNT_IF(r.RISK_TIER = 'high')        AS high,
  COUNT_IF(r.RISK_TIER = 'medium')      AS medium,
  COUNT_IF(r.RISK_TIER = 'low')         AS low
FROM DEMO_C360_CUSTOMERS cu
JOIN DT_DEMO_C360_CUSTOMER_RECORD r ON r.CUSTOMER_ID = cu.CUSTOMER_ID
GROUP BY cu.COHORT_STORY
ORDER BY high DESC;
