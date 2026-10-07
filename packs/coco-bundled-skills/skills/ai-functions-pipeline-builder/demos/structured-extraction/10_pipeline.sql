/* =====================================================================================
   Structured Extraction demo -- 10 - Processing chain (incremental dynamic tables)
   classify-route -> extract -> vision -> assemble -> decide -> triage

     DEMO_CLM_FILE_LOG
       -> DT_DEMO_CLM_CLASSIFIED  AI_CLASSIFY(TO_FILE) over pdf+jpg -> DOC_TYPE   [the traffic controller]
                                   in {fnol_form, repair_estimate, police_report, damage_photo, other}
       -> DT_DEMO_CLM_PARSED      AI_PARSE_DOCUMENT(LAYOUT) for textual types only
       -> routed extraction (each reads its DOC_TYPE slice):
            DT_DEMO_CLM_FNOL      AI_EXTRACT(scores=>TRUE) -> fields + per-field confidence
            DT_DEMO_CLM_ESTIMATE  AI_EXTRACT               -> shop, total
            DT_DEMO_CLM_POLICE    AI_EXTRACT               -> report_no, fault, narrative
            DT_DEMO_CLM_PHOTO     AI_COMPLETE(vision+JSON) -> severity, parts, fraud cues
       -> DT_DEMO_CLM_CLAIM       LEFT JOIN the four on CLAIM_NO -> one record per claim
       -> DT_DEMO_CLM_DECISION    AI_COMPLETE(json) -> recommended_action, fraud_risk,
                                   settlement_estimate, rationale
       -> DT_DEMO_CLM_TRIAGED     confidence + decision -> ROUTE in {auto_settle,        [terminal, 1h]
                                   needs_review, reject}
       -> views DEMO_CLM_AUTO_SETTLE / _NEEDS_REVIEW / _REJECTED / _CLAIM_INTELLIGENCE

   Conventions: AI_* funcs unprefixed; TO_FILE is 2-arg; AI calls inline (never inside LATERAL);
   intermediate DTs TARGET_LAG = DOWNSTREAM, terminal takes the user lag (1 hour).
   NULLIF(x,'None') every extracted string; TRY_CAST numerics.

   CLAIM_NO is derived from the staged path (incoming/<claim_no>__<type>.<ext>) -- robust, and the
   photo carries no claim number. Classification is honest AI (it never reads the __<type> token).

   AI_EXTRACT scores=>TRUE return shape:
     RAW:response:<field>              -> value
     RAW:scoring:scores:<field>:score  -> 0..1 confidence (powers the review queue)

   ZERO-SPEND SCAFFOLD: every DT is INITIALIZE = ON_SCHEDULE (CREATE compiles + plans + fixes
   refresh_mode WITHOUT running AI). The terminal is left SUSPENDED so no scheduled refresh fires.
   AI runs later, explicitly -- see 20_triage.sql section A.

   Substitute {database} / {schema} / {warehouse} before running. Model default: claude-4-sonnet.
   ===================================================================================== */

USE DATABASE {database};
USE SCHEMA {database}.{schema};
USE WAREHOUSE {warehouse};

-- ---------------------------------------------------------------------------------------
-- Root - one classifier DT over every file (PDFs + photos), uniform TO_FILE input.
-- CLAIM_NO parsed from the path; classification is genuine AI over the file bytes.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_CLM_CLASSIFIED
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = {warehouse}  REFRESH_MODE = INCREMENTAL
  INITIALIZE = ON_SCHEDULE
AS
  SELECT
    fl.RELATIVE_PATH,
    SPLIT_PART(SPLIT_PART(fl.RELATIVE_PATH,'/',-1),'__',1) AS CLAIM_NO,
    fl.INGESTED_AT,
    AI_CLASSIFY(
      TO_FILE('@DEMO_CLM_DOCS_STAGE', fl.RELATIVE_PATH),
      ['fnol_form','repair_estimate','police_report','damage_photo','other'],
      {'task_description':'Classify the auto-insurance claim document by its type. fnol_form = first notice of loss / claim intake form; repair_estimate = body-shop repair cost estimate; police_report = police traffic collision report; damage_photo = a photograph of a damaged vehicle; other = anything not part of an auto-insurance claim.'}
    ):labels[0]::STRING AS DOC_TYPE
  FROM DEMO_CLM_FILE_LOG fl;

-- ---------------------------------------------------------------------------------------
-- Parse textual types only (skip photos + gated 'other'). LAYOUT preserves form structure
-- so AI_EXTRACT sees labeled fields and tables.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_CLM_PARSED
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = {warehouse}  REFRESH_MODE = INCREMENTAL
  INITIALIZE = ON_SCHEDULE
AS
  SELECT
    c.RELATIVE_PATH, c.CLAIM_NO, c.DOC_TYPE,
    AI_PARSE_DOCUMENT(
      TO_FILE('@DEMO_CLM_DOCS_STAGE', c.RELATIVE_PATH),
      {'mode':'LAYOUT'}
    ):content::STRING AS CONTENT
  FROM DT_DEMO_CLM_CLASSIFIED c
  WHERE c.DOC_TYPE IN ('fnol_form','repair_estimate','police_report');

-- ---------------------------------------------------------------------------------------
-- Fan-out - FNOL fields + per-field confidence. The MIN field score is the review-queue
-- signal (low confidence -> human review, regardless of the decision).
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_CLM_FNOL
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = {warehouse}  REFRESH_MODE = INCREMENTAL
  INITIALIZE = ON_SCHEDULE
AS
  SELECT
    CLAIM_NO,
    NULLIF(RAW:response:claimant::STRING,'None')      AS CLAIMANT,
    NULLIF(RAW:response:policy_no::STRING,'None')     AS POLICY_NO,
    NULLIF(RAW:response:date_of_loss::STRING,'None')  AS DATE_OF_LOSS,
    NULLIF(RAW:response:vehicle::STRING,'None')       AS VEHICLE,
    NULLIF(RAW:response:location::STRING,'None')      AS LOCATION,
    TRY_CAST(REPLACE(REPLACE(RAW:response:amount_claimed::STRING,'$',''),',','') AS NUMBER(12,2)) AS AMOUNT_CLAIMED,
    LEAST(
      COALESCE(RAW:scoring:scores:claimant:score::FLOAT, 1),
      COALESCE(RAW:scoring:scores:policy_no:score::FLOAT, 1),
      COALESCE(RAW:scoring:scores:date_of_loss:score::FLOAT, 1),
      COALESCE(RAW:scoring:scores:amount_claimed:score::FLOAT, 1)
    ) AS MIN_CONFIDENCE
  FROM (
    SELECT CLAIM_NO,
      AI_EXTRACT(text => CONTENT, scores => TRUE, responseFormat => {
        'claimant':'full name of the insured / claimant',
        'policy_no':'the insurance policy number',
        'date_of_loss':'the date of loss / accident (YYYY-MM-DD)',
        'vehicle':'the insured vehicle (year make model)',
        'location':'where the loss occurred',
        'amount_claimed':'the estimated amount claimed (number)'
      }) AS RAW
    FROM DT_DEMO_CLM_PARSED WHERE DOC_TYPE='fnol_form'
  );

CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_CLM_ESTIMATE
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = {warehouse}  REFRESH_MODE = INCREMENTAL
  INITIALIZE = ON_SCHEDULE
AS
  SELECT
    CLAIM_NO,
    NULLIF(RAW:response:shop::STRING,'None') AS SHOP,
    TRY_CAST(REPLACE(REPLACE(RAW:response:total::STRING,'$',''),',','') AS NUMBER(12,2)) AS ESTIMATE_TOTAL
  FROM (
    SELECT CLAIM_NO,
      AI_EXTRACT(text => CONTENT, responseFormat => {
        'shop':'the repair shop / body shop name',
        'total':'the grand total repair cost (number)'
      }) AS RAW
    FROM DT_DEMO_CLM_PARSED WHERE DOC_TYPE='repair_estimate'
  );

CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_CLM_POLICE
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = {warehouse}  REFRESH_MODE = INCREMENTAL
  INITIALIZE = ON_SCHEDULE
AS
  SELECT
    CLAIM_NO,
    NULLIF(RAW:response:report_no::STRING,'None') AS REPORT_NO,
    NULLIF(RAW:response:fault::STRING,'None')     AS FAULT,
    NULLIF(RAW:response:narrative::STRING,'None') AS NARRATIVE
  FROM (
    SELECT CLAIM_NO,
      AI_EXTRACT(text => CONTENT, responseFormat => {
        'report_no':'the police report number',
        'fault':'which party was assigned fault (e.g. Party 1 / insured, Party 2, or undetermined)',
        'narrative':'one-sentence summary of the collision narrative'
      }) AS RAW
    FROM DT_DEMO_CLM_PARSED WHERE DOC_TYPE='police_report'
  );

-- ---------------------------------------------------------------------------------------
-- Vision damage assessment (structured JSON via AI_COMPLETE file + response_format).
-- Reads the photo, not the forms.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_CLM_PHOTO
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = {warehouse}  REFRESH_MODE = INCREMENTAL
  INITIALIZE = ON_SCHEDULE
AS
  SELECT
    CLAIM_NO,
    NULLIF(RAW:severity::STRING,'None')        AS SEVERITY,
    NULLIF(RAW:parts_affected::STRING,'None')  AS PARTS_AFFECTED,
    NULLIF(RAW:repair_vs_total::STRING,'None') AS REPAIR_VS_TOTAL,
    NULLIF(RAW:fraud_cues::STRING,'None')      AS FRAUD_CUES
  FROM (
    SELECT
      CLAIM_NO,
      AI_COMPLETE(
        'claude-4-sonnet',
        'You are an auto-insurance damage assessor. Assess the vehicle damage in this photo and return JSON only with keys: "severity" (one of: minor, moderate, severe, total_loss), "parts_affected" (short comma list of damaged parts), "repair_vs_total" (one of: repairable, likely_total), "fraud_cues" (any visual inconsistency suggesting staged or pre-existing damage; else "none").',
        TO_FILE('@DEMO_CLM_DOCS_STAGE', RELATIVE_PATH),
        response_format => {
          'type':'json',
          'schema':{'type':'object','properties':{
            'severity':{'type':'string'},
            'parts_affected':{'type':'string'},
            'repair_vs_total':{'type':'string'},
            'fraud_cues':{'type':'string'}
          },'required':['severity','parts_affected','repair_vs_total','fraud_cues']}
        }
      ) AS RAW
    FROM DT_DEMO_CLM_CLASSIFIED
    WHERE DOC_TYPE='damage_photo'
  );

-- ---------------------------------------------------------------------------------------
-- Assemble one record per claim across the four per-type DTs (LEFT JOIN on CLAIM_NO).
-- Driven from FNOL (the claim's anchor doc); estimate/police/photo attach when present.
-- HAS_POLICE / HAS_PHOTO flags + MIN_CONFIDENCE feed the decision + triage.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_CLM_CLAIM
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = {warehouse}  REFRESH_MODE = INCREMENTAL
  INITIALIZE = ON_SCHEDULE
AS
  SELECT
    f.CLAIM_NO, f.CLAIMANT, f.POLICY_NO, f.DATE_OF_LOSS, f.VEHICLE, f.LOCATION, f.AMOUNT_CLAIMED,
    e.SHOP, e.ESTIMATE_TOTAL,
    p.REPORT_NO, p.FAULT, p.NARRATIVE,
    ph.SEVERITY, ph.PARTS_AFFECTED, ph.REPAIR_VS_TOTAL, ph.FRAUD_CUES AS PHOTO_FRAUD_CUES,
    f.MIN_CONFIDENCE,
    (p.REPORT_NO IS NOT NULL) AS HAS_POLICE,
    (ph.SEVERITY IS NOT NULL) AS HAS_PHOTO
  FROM DT_DEMO_CLM_FNOL f
  LEFT JOIN DT_DEMO_CLM_ESTIMATE e ON e.CLAIM_NO = f.CLAIM_NO
  LEFT JOIN DT_DEMO_CLM_POLICE   p ON p.CLAIM_NO = f.CLAIM_NO
  LEFT JOIN DT_DEMO_CLM_PHOTO   ph ON ph.CLAIM_NO = f.CLAIM_NO;

-- ---------------------------------------------------------------------------------------
-- Decision: AI_COMPLETE reasons over the assembled record (a judgment the documents don't
-- state) -> recommended_action, fraud_risk, settlement_estimate, rationale. It weighs
-- cross-document inconsistencies (claimed vs estimate, fault, photo vs estimate, missing
-- evidence) -- exactly where the planted fraud cues surface.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_CLM_DECISION
  TARGET_LAG = DOWNSTREAM  WAREHOUSE = {warehouse}  REFRESH_MODE = INCREMENTAL
  INITIALIZE = ON_SCHEDULE
AS
  SELECT
    CLAIM_NO,
    AI_COMPLETE(
      'claude-4-sonnet',
      'You are an auto-insurance claims adjuster. Based ONLY on the assembled claim record below, '
      || 'return a JSON object with keys "recommended_action" (auto_settle | review | deny), '
      || '"fraud_risk" (low | medium | high), "settlement_estimate" (a USD number, anchored on the '
      || 'repair estimate -- not the claimed amount), and "rationale" (one sentence). Guidance:\n'
      || '- fraud_risk = high (and usually deny) ONLY for a clear red flag: the claimed amount is far '
      || 'above the repair estimate, OR the damage photo shows little/no damage while the claim or '
      || 'estimate is large, OR there are explicit photo fraud cues.\n'
      || '- fraud_risk = medium (and usually review) for a single moderate concern, an estimate that '
      || 'looks inflated relative to the visible damage, or a high-value claim that is otherwise consistent.\n'
      || '- fraud_risk = low (and auto_settle) when the documents are consistent and the value is modest.\n'
      || '- IMPORTANT: the insured being at fault is NORMAL and is NOT fraud -- do not penalize at-fault '
      || 'claims. Judge only on internal consistency, the photo-vs-estimate match, and documentation.\n'
      || 'Claim record:\n'
      || 'amount_claimed=' || COALESCE(AMOUNT_CLAIMED::STRING,'n/a')
      || '; estimate_total=' || COALESCE(ESTIMATE_TOTAL::STRING,'n/a')
      || '; police_fault=' || COALESCE(FAULT,'n/a')
      || '; has_police_report=' || HAS_POLICE::STRING
      || '; photo_severity=' || COALESCE(SEVERITY,'no photo')
      || '; photo_repair_vs_total=' || COALESCE(REPAIR_VS_TOTAL,'n/a')
      || '; photo_fraud_cues=' || COALESCE(PHOTO_FRAUD_CUES,'n/a')
      || '; loss_narrative=' || COALESCE(NARRATIVE,'n/a'),
      response_format => {
        'type':'json',
        'schema':{'type':'object','properties':{
          'recommended_action':{'type':'string'},
          'fraud_risk':{'type':'string'},
          'settlement_estimate':{'type':'number'},
          'rationale':{'type':'string'}
        },'required':['recommended_action','fraud_risk','settlement_estimate','rationale']}
      }
    ) AS RAW
  FROM DT_DEMO_CLM_CLAIM;

-- ---------------------------------------------------------------------------------------
-- Triage (terminal, user lag 1h). Pure SQL lanes combining the model's judgment with hard
-- business rules. AI_EXTRACT field scores on these forms run ~0.5-0.8, so the review gate is
-- set at 0.58 to flag only the genuinely weak extractions -- plus a high-value / missing-
-- evidence backstop.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE DYNAMIC TABLE DT_DEMO_CLM_TRIAGED
  TARGET_LAG = '1 hour'  WAREHOUSE = {warehouse}  REFRESH_MODE = INCREMENTAL
  INITIALIZE = ON_SCHEDULE
AS
  WITH d AS (
    SELECT
      c.*,
      LOWER(NULLIF(TRY_PARSE_JSON(dec.RAW::STRING):recommended_action::STRING,'None'))  AS RECOMMENDED_ACTION,
      LOWER(NULLIF(TRY_PARSE_JSON(dec.RAW::STRING):fraud_risk::STRING,'None'))           AS FRAUD_RISK,
      TRY_CAST(TRY_PARSE_JSON(dec.RAW::STRING):settlement_estimate::STRING AS NUMBER(12,2)) AS SETTLEMENT_ESTIMATE,
      NULLIF(TRY_PARSE_JSON(dec.RAW::STRING):rationale::STRING,'None')                   AS RATIONALE
    FROM DT_DEMO_CLM_CLAIM c
    JOIN DT_DEMO_CLM_DECISION dec ON dec.CLAIM_NO = c.CLAIM_NO
  )
  SELECT
    d.*,
    CASE
      WHEN FRAUD_RISK = 'high' OR RECOMMENDED_ACTION = 'deny' THEN 'reject'
      WHEN FRAUD_RISK = 'medium'
        OR RECOMMENDED_ACTION = 'review'
        OR MIN_CONFIDENCE < 0.58
        OR COALESCE(SETTLEMENT_ESTIMATE, 0) >= 12000
        OR (NOT HAS_PHOTO  AND COALESCE(SETTLEMENT_ESTIMATE,0) >= 7000)   -- missing visual evidence on a big claim
        OR (NOT HAS_POLICE AND COALESCE(SETTLEMENT_ESTIMATE,0) >= 9000)   -- missing police report on a big claim
        THEN 'needs_review'
      ELSE 'auto_settle'
    END AS ROUTE
  FROM d;

-- ---------------------------------------------------------------------------------------
-- User-facing views over the terminal DT.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE VIEW DEMO_CLM_CLAIM_INTELLIGENCE AS
  SELECT * FROM DT_DEMO_CLM_TRIAGED;
CREATE OR REPLACE VIEW DEMO_CLM_AUTO_SETTLE AS
  SELECT * FROM DT_DEMO_CLM_TRIAGED WHERE ROUTE = 'auto_settle';
CREATE OR REPLACE VIEW DEMO_CLM_NEEDS_REVIEW AS
  SELECT * FROM DT_DEMO_CLM_TRIAGED WHERE ROUTE = 'needs_review'
  ORDER BY COALESCE(SETTLEMENT_ESTIMATE,0) DESC;
CREATE OR REPLACE VIEW DEMO_CLM_REJECTED AS
  SELECT * FROM DT_DEMO_CLM_TRIAGED WHERE ROUTE = 'reject';

-- ---------------------------------------------------------------------------------------
-- Keep the terminal SUSPENDED after create so its scheduled (1h) refresh cannot fire -- and
-- spend on AI -- before the cost gate. Resume in 20_triage.sql section A.
-- ---------------------------------------------------------------------------------------
ALTER DYNAMIC TABLE DT_DEMO_CLM_TRIAGED SUSPEND;
