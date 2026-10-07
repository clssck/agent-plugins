/* =====================================================================================
   Customer 360 demo -- 10 - Fusion pipeline (incremental dynamic tables)
   classify docs -> extract signals -> JOIN the warehouse -> risk/route -> search + landscape

     DEMO_C360_FILE_LOG  (unstructured docs)      DEMO_C360_* structured tables (pre-loaded)
       -> DT_DEMO_C360_CLASSIFIED    AI_CLASSIFY(TO_FILE) -> DOC_TYPE            [doc traffic control]
            in {support_ticket, chat_transcript, survey_comment, call_transcript,
                error_report, other}
       -> DT_DEMO_C360_CUSTOMER_DOCS attach CONTENT, drop 'other', key by CUSTOMER_ID
       -> DT_DEMO_C360_DOC_SIGNALS   AI_COMPLETE(json) -> sentiment + issue_type per doc
       -> DT_DEMO_C360_CUSTOMER_RECORD   the FUSION step: LEFT JOIN doc signals onto the six  [1h]
                                   structured tables (customers, products, telemetry, surveys,
                                   txns, campaigns) -> one row per customer with RISK_TIER + ROUTE
       -> DT_DEMO_C360_SEARCH_CHUNKS     doc text ready to index (DEMO_C360_SEARCH built in 20 A)
       -> DT_DEMO_C360_HEALTH_LANDSCAPE  AI_COMPLETE exec briefing per product              [1h]
       -> views DEMO_C360_HIGH_RISK / _NEEDS_REVIEW / _AUTO_ACT / _CUSTOMER_360

   THE POINT: risk is not readable from any single source. A customer with clean telemetry can
   still be high-risk because their support tickets read 'negative' (AI signal), and a low NPS is
   downgraded to 'needs_review' rather than 'high' unless a negative doc corroborates it. Fusion =
   structured facts + AI-extracted signals, reconciled by SQL rules with per-cohort guardrails.

   Conventions: AI_* funcs unprefixed; TO_FILE is 2-arg; AI calls inline (never inside LATERAL);
   intermediate DTs TARGET_LAG = DOWNSTREAM, deliverable DTs take the user lag (1 hour).
   CUSTOMER_ID is parsed from the staged path (incoming/<customer_id>__<type>.txt); junk docs
   classify as 'other' and drop out. Structured tables are JOINed, never recreated here.

   ZERO-SPEND SCAFFOLD: every DT is INITIALIZE = ON_SCHEDULE (CREATE compiles + plans + fixes
   refresh_mode WITHOUT running AI). The two deliverable DTs are left SUSPENDED so no scheduled
   refresh fires. AI runs later, explicitly -- see 20_insights.sql section A.

   Substitute {database} / {schema} / {warehouse} before running. Model default: claude-4-sonnet.
   ===================================================================================== */

USE DATABASE {database};
USE SCHEMA {database}.{schema};
USE WAREHOUSE {warehouse};

-- ---------------------------------------------------------------------------------------
-- Root - classify every doc on its content (never the path token). CUSTOMER_ID is parsed
-- from the path so junk docs (no customer prefix) still get a value but classify as 'other'.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_C360_CLASSIFIED
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = {warehouse}  REFRESH_MODE = INCREMENTAL
  INITIALIZE = ON_SCHEDULE
AS
  SELECT
    fl.RELATIVE_PATH,
    SPLIT_PART(SPLIT_PART(fl.RELATIVE_PATH,'/',-1),'__',1) AS CUSTOMER_ID,
    fl.INGESTED_AT,
    AI_CLASSIFY(
      TO_FILE('@DEMO_C360_DOCS_STAGE', fl.RELATIVE_PATH),
      ['support_ticket','chat_transcript','survey_comment','call_transcript','error_report','other'],
      {'task_description':'Classify the customer document by type. support_ticket = a written support case; chat_transcript = a live chat / messaging session; survey_comment = a free-text survey response; call_transcript = a transcribed phone call; error_report = an automated system error / incident report; other = anything not tied to a specific customer interaction.'}
    ):labels[0]::STRING AS DOC_TYPE
  FROM DEMO_C360_FILE_LOG fl
  WHERE fl.RELATIVE_PATH ILIKE 'incoming/%';

-- ---------------------------------------------------------------------------------------
-- Per-doc rows keyed by CUSTOMER_ID with the doc text attached from the file log. Drop 'other'
-- (junk) AND rows whose CONTENT hasn't been loaded yet -- a doc can only be scored/searched once
-- its text is in the file log, so a metadata-only row must not reach the signal or search step.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_C360_CUSTOMER_DOCS
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = {warehouse}  REFRESH_MODE = INCREMENTAL
  INITIALIZE = ON_SCHEDULE
AS
  SELECT
    c.CUSTOMER_ID,
    c.RELATIVE_PATH,
    c.DOC_TYPE,
    c.INGESTED_AT,
    fl.CONTENT AS TEXT_BODY
  FROM DT_DEMO_C360_CLASSIFIED c
  JOIN DEMO_C360_FILE_LOG fl ON fl.RELATIVE_PATH = c.RELATIVE_PATH
  WHERE c.DOC_TYPE <> 'other'
    AND fl.CONTENT IS NOT NULL;

-- ---------------------------------------------------------------------------------------
-- Extract a structured signal (sentiment + issue_type) from each doc. This is the AI
-- evidence that structured telemetry / surveys alone cannot produce.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_C360_DOC_SIGNALS
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = {warehouse}  REFRESH_MODE = INCREMENTAL
  INITIALIZE = ON_SCHEDULE
AS
  SELECT
    d.CUSTOMER_ID,
    d.RELATIVE_PATH,
    d.DOC_TYPE,
    AI_COMPLETE(
      'claude-4-sonnet',
      'Return JSON only with keys "sentiment" (one of: positive, negative, neutral) and '
      || '"issue_type" (a short snake_case label for the customer''s core issue, e.g. '
      || 'billing_dispute, outage, feature_request, praise, cancellation_threat). Document:\n'
      || d.TEXT_BODY,
      response_format => {
        'type':'json',
        'schema':{'type':'object','properties':{
          'sentiment':{'type':'string','enum':['positive','negative','neutral']},
          'issue_type':{'type':'string'}
        },'required':['sentiment','issue_type']}
      }
    ) AS RAW
  FROM DT_DEMO_C360_CUSTOMER_DOCS d;

-- ---------------------------------------------------------------------------------------
-- FUSION (deliverable, user lag 1h). One row per customer: the six structured tables LEFT
-- JOINed to the AI doc signals, reconciled into RISK_TIER + ROUTE by SQL rules. COHORT_STORY
-- is a guardrail (e.g. a billing dispute's negative doc must not, alone, force 'high').
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_C360_CUSTOMER_RECORD
  TARGET_LAG = '1 hour'  WAREHOUSE = {warehouse}  REFRESH_MODE = INCREMENTAL
  INITIALIZE = ON_SCHEDULE
AS
  WITH doc_agg AS (
    SELECT
      CUSTOMER_ID,
      COUNT(*) AS DOC_COUNT,
      MAX(IFF(DOC_TYPE = 'support_ticket', 1, 0)) AS HAS_TICKET,
      LISTAGG(DISTINCT DOC_TYPE, ',') AS DOC_TYPES
    FROM DT_DEMO_C360_CUSTOMER_DOCS
    GROUP BY CUSTOMER_ID
  ),
  sig_agg AS (
    SELECT
      CUSTOMER_ID,
      COUNT(*) AS SIGNAL_ROWS,
      SUM(IFF(LOWER(TRIM(RAW:sentiment::STRING)) = 'negative', 1, 0)) AS NEG_DOC_COUNT
    FROM DT_DEMO_C360_DOC_SIGNALS
    GROUP BY CUSTOMER_ID
  ),
  tel AS (
    WITH daily AS (
      SELECT
        CUSTOMER_ID,
        DAU,
        ERROR_RATE,
        ROW_NUMBER() OVER (PARTITION BY CUSTOMER_ID ORDER BY DATE) AS rn,
        COUNT(*) OVER (PARTITION BY CUSTOMER_ID) AS n
      FROM DEMO_C360_TELEMETRY_DAILY
    )
    SELECT
      CUSTOMER_ID,
      MAX(ERROR_RATE) AS MAX_ERROR_RATE,
      AVG(DAU) AS AVG_DAU,
      (
        AVG(IFF(rn > n - 14, DAU, NULL)) - AVG(IFF(rn <= 14, DAU, NULL))
      ) / NULLIF(AVG(IFF(rn <= 14, DAU, NULL)), 0) AS DAU_DECLINE_PCT
    FROM daily
    GROUP BY CUSTOMER_ID
  ),
  nps AS (
    SELECT CUSTOMER_ID, MAX(IFF(QUARTER = '2026-Q2', NPS, NULL)) AS NPS_Q2
    FROM DEMO_C360_SURVEY_SCORES
    GROUP BY CUSTOMER_ID
  ),
  txn AS (
    SELECT CUSTOMER_ID, SUM(AMOUNT) AS TOTAL_CHARGED
    FROM DEMO_C360_TRANSACTIONS
    WHERE TXN_TYPE = 'charge'
    GROUP BY CUSTOMER_ID
  ),
  camp AS (
    SELECT CUSTOMER_ID, MAX(IFF(OPENED, 1, 0)) AS CAMPAIGN_EXPOSED
    FROM DEMO_C360_CAMPAIGNS
    GROUP BY CUSTOMER_ID
  )
  SELECT
    cu.CUSTOMER_ID,
    cu.COMPANY_NAME,
    cu.PRIMARY_PRODUCT,
    p.CATEGORY AS PRODUCT_CATEGORY,
    cu.SEATS,
    COALESCE(d.DOC_COUNT, 0) AS DOC_COUNT,
    COALESCE(s.NEG_DOC_COUNT, 0) AS NEG_DOC_COUNT,
    t.MAX_ERROR_RATE,
    t.AVG_DAU,
    t.DAU_DECLINE_PCT,
    n.NPS_Q2,
    x.TOTAL_CHARGED,
    COALESCE(cp.CAMPAIGN_EXPOSED, 0) AS CAMPAIGN_EXPOSED,
    CASE
      WHEN t.MAX_ERROR_RATE > 0.05
        OR (
          COALESCE(s.NEG_DOC_COUNT, 0) >= 2
          AND cu.COHORT_STORY NOT IN ('billing_dispute', 'campaign_backlash')
        )
        OR t.DAU_DECLINE_PCT <= -0.15
        OR (COALESCE(n.NPS_Q2, 10) <= 4 AND COALESCE(s.NEG_DOC_COUNT, 0) >= 1)
        OR (
          cu.COHORT_STORY = 'vocal_churn'
          AND COALESCE(n.NPS_Q2, 10) <= 6
          AND COALESCE(s.NEG_DOC_COUNT, 0) >= 1
        )
        THEN 'high'
      WHEN COALESCE(n.NPS_Q2, 10) <= 8 OR COALESCE(s.NEG_DOC_COUNT, 0) >= 1
        THEN 'medium'
      ELSE 'low'
    END AS RISK_TIER,
    CASE
      WHEN t.MAX_ERROR_RATE > 0.05 THEN 'escalate'
      WHEN COALESCE(s.NEG_DOC_COUNT, 0) >= 2
        OR t.DAU_DECLINE_PCT <= -0.15
        OR (COALESCE(n.NPS_Q2, 10) <= 4 AND COALESCE(s.NEG_DOC_COUNT, 0) >= 1)
        OR (
          cu.COHORT_STORY = 'vocal_churn'
          AND COALESCE(n.NPS_Q2, 10) <= 6
          AND COALESCE(s.NEG_DOC_COUNT, 0) >= 1
        )
        OR COALESCE(n.NPS_Q2, 10) <= 8
        OR COALESCE(s.NEG_DOC_COUNT, 0) >= 1
        THEN 'needs_review'
      ELSE 'auto_act'
    END AS ROUTE
  FROM DEMO_C360_CUSTOMERS cu
  LEFT JOIN DEMO_C360_PRODUCTS p ON p.PRODUCT_NAME = cu.PRIMARY_PRODUCT
  LEFT JOIN doc_agg d ON d.CUSTOMER_ID = cu.CUSTOMER_ID
  LEFT JOIN sig_agg s ON s.CUSTOMER_ID = cu.CUSTOMER_ID
  LEFT JOIN tel t ON t.CUSTOMER_ID = cu.CUSTOMER_ID
  LEFT JOIN nps n ON n.CUSTOMER_ID = cu.CUSTOMER_ID
  LEFT JOIN txn x ON x.CUSTOMER_ID = cu.CUSTOMER_ID
  LEFT JOIN camp cp ON cp.CUSTOMER_ID = cu.CUSTOMER_ID;

-- ---------------------------------------------------------------------------------------
-- Search chunks (the enterprise-search head of the 360): the doc text, ready to index. The
-- CORTEX SEARCH SERVICE over this DT is created in 20_insights.sql section A -- a search service
-- is active on creation (it indexes + serves), so it belongs behind the cost gate, not here.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_C360_SEARCH_CHUNKS
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = {warehouse}  REFRESH_MODE = INCREMENTAL
  INITIALIZE = ON_SCHEDULE
AS
  SELECT
    CUSTOMER_ID,
    RELATIVE_PATH,
    DOC_TYPE,
    TEXT_BODY AS CHUNK_TEXT
  FROM DT_DEMO_C360_CUSTOMER_DOCS
  WHERE TEXT_BODY IS NOT NULL;

-- ---------------------------------------------------------------------------------------
-- Product health landscape (deliverable, user lag 1h): a per-product rollup with an AI-written
-- executive briefing (the corpus-intelligence head of the 360).
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_C360_HEALTH_LANDSCAPE
  TARGET_LAG = '1 hour'  WAREHOUSE = {warehouse}  REFRESH_MODE = INCREMENTAL
  INITIALIZE = ON_SCHEDULE
AS
  SELECT
    cu.PRIMARY_PRODUCT AS PRODUCT,
    COUNT(*) AS CUSTOMER_COUNT,
    AVG(r.NPS_Q2) AS AVG_NPS_Q2,
    AVG(t.MAX_ERROR_RATE) AS AVG_MAX_ERROR_RATE,
    SUM(r.CAMPAIGN_EXPOSED) AS CAMPAIGN_EXPOSED_COUNT,
    SUM(IFF(r.RISK_TIER = 'high', 1, 0)) AS HIGH_RISK_COUNT,
    AI_COMPLETE(
      'claude-4-sonnet',
      'Write a 3-sentence executive briefing on product health given: product=' || cu.PRIMARY_PRODUCT
      || ', customers=' || COUNT(*)
      || ', avg_nps=' || COALESCE(TO_VARCHAR(ROUND(AVG(r.NPS_Q2), 1)), 'n/a')
      || ', high_risk=' || SUM(IFF(r.RISK_TIER = 'high', 1, 0))
    ) AS EXEC_BRIEFING
  FROM DEMO_C360_CUSTOMERS cu
  JOIN DT_DEMO_C360_CUSTOMER_RECORD r ON r.CUSTOMER_ID = cu.CUSTOMER_ID
  LEFT JOIN (
    SELECT CUSTOMER_ID, MAX(ERROR_RATE) AS MAX_ERROR_RATE
    FROM DEMO_C360_TELEMETRY_DAILY GROUP BY CUSTOMER_ID
  ) t ON t.CUSTOMER_ID = cu.CUSTOMER_ID
  GROUP BY cu.PRIMARY_PRODUCT;

-- ---------------------------------------------------------------------------------------
-- User-facing views over the customer record.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW DEMO_C360_CUSTOMER_360 AS
  SELECT * FROM DT_DEMO_C360_CUSTOMER_RECORD;
CREATE OR REPLACE VIEW DEMO_C360_HIGH_RISK AS
  SELECT * FROM DT_DEMO_C360_CUSTOMER_RECORD WHERE RISK_TIER = 'high'
  ORDER BY COALESCE(TOTAL_CHARGED, 0) DESC;
CREATE OR REPLACE VIEW DEMO_C360_NEEDS_REVIEW AS
  SELECT * FROM DT_DEMO_C360_CUSTOMER_RECORD WHERE ROUTE = 'needs_review'
  ORDER BY COALESCE(TOTAL_CHARGED, 0) DESC;
CREATE OR REPLACE VIEW DEMO_C360_AUTO_ACT AS
  SELECT * FROM DT_DEMO_C360_CUSTOMER_RECORD WHERE ROUTE = 'auto_act';

-- ---------------------------------------------------------------------------------------
-- Keep the two deliverable DTs SUSPENDED after create so their scheduled (1h) refresh cannot
-- fire -- and spend on AI -- before the cost gate. Resume/refresh in 20_insights.sql section A.
-- ---------------------------------------------------------------------------------------
ALTER DYNAMIC TABLE DT_DEMO_C360_CUSTOMER_RECORD SUSPEND;
ALTER DYNAMIC TABLE DT_DEMO_C360_HEALTH_LANDSCAPE SUSPEND;
