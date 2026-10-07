/* =====================================================================================
   Structured Extraction demo -- 20 - AI refresh (cost-gated) + verify + deliverables

   Section A runs the AI -- it SPENDS. Everything before it (00_setup, source_structured_extraction.py,
   10_pipeline) is zero-spend: the dynamic tables were created INITIALIZE = ON_SCHEDULE and the
   terminal left suspended, so no AI function has run yet. Do NOT run section A until the demo's
   cost gate has been shown and approved. Optional smoke (A1) first, then the full refresh (A2).

   Section B (verify), C (health), D (deliverables) are read-only -- safe to re-run anytime.

   Substitute {database} / {schema} / {warehouse} before running.
   ===================================================================================== */

USE DATABASE {database};
USE SCHEMA {database}.{schema};
USE WAREHOUSE {warehouse};

/* =======================================================================================
   SECTION A - AI EXECUTION.  ***THIS SPENDS.***  Do not run before the cost gate.

   Cost drivers (defaults: claude-4-sonnet + arctic_extract), full 40-claim / ~146-file corpus:
     AI_CLASSIFY          ~146  (every file, including junk)
     AI_PARSE_DOCUMENT    ~112  (fnol + estimate + police)
     AI_EXTRACT           ~112  (40 fnol w/ scores + 40 estimate + 32 police)
     AI_COMPLETE  vision   ~30  (damage photos)
     AI_COMPLETE  decision ~40  (one per claim)
   See the demo SKILL.md for the current-rates pricing note.
   =======================================================================================*/

-- A1 - Optional cheap smoke FIRST (interactive): re-confirm the call shapes on the real corpus
--      before the full sweep. Pick a couple of real paths from the file log.
--
--   SELECT RELATIVE_PATH,
--     AI_CLASSIFY(TO_FILE('@DEMO_CLM_DOCS_STAGE', RELATIVE_PATH),
--       ['fnol_form','repair_estimate','police_report','damage_photo','other']):labels[0]::STRING AS DOC_TYPE
--   FROM DEMO_CLM_FILE_LOG
--   ORDER BY RELATIVE_PATH
--   LIMIT 4;

-- A2 - Full refresh, in dependency order, ONE pass. Each ALTER blocks until that layer finishes.
ALTER DYNAMIC TABLE DT_DEMO_CLM_CLASSIFIED REFRESH;   -- ~146 x AI_CLASSIFY
ALTER DYNAMIC TABLE DT_DEMO_CLM_PARSED     REFRESH;   -- ~112 x AI_PARSE_DOCUMENT
ALTER DYNAMIC TABLE DT_DEMO_CLM_FNOL       REFRESH;   --  40 x AI_EXTRACT (scores)
ALTER DYNAMIC TABLE DT_DEMO_CLM_ESTIMATE   REFRESH;   --  40 x AI_EXTRACT
ALTER DYNAMIC TABLE DT_DEMO_CLM_POLICE     REFRESH;   --  32 x AI_EXTRACT
ALTER DYNAMIC TABLE DT_DEMO_CLM_PHOTO      REFRESH;   --  30 x AI_COMPLETE vision
ALTER DYNAMIC TABLE DT_DEMO_CLM_CLAIM      REFRESH;
ALTER DYNAMIC TABLE DT_DEMO_CLM_DECISION   REFRESH;   --  40 x AI_COMPLETE (decision)
ALTER DYNAMIC TABLE DT_DEMO_CLM_TRIAGED    REFRESH;
-- Keep the terminal fresh as new docs land (safe: upstream is INCREMENTAL, re-runs only new rows):
ALTER DYNAMIC TABLE DT_DEMO_CLM_TRIAGED    RESUME;
-- Resume the ingest task only after Section B + a quality spot-check (optional for a static demo):
-- ALTER TASK DEMO_CLM_INGEST_TASK RESUME;

/* =======================================================================================
   SECTION B - VERIFY refresh modes.  MANDATORY: every per-document DT must be INCREMENTAL
   (a FULL per-document DT would re-run every AI function on every refresh).
   =======================================================================================*/
SHOW DYNAMIC TABLES LIKE 'DT_DEMO_CLM%';
SELECT "name", "refresh_mode", "refresh_mode_reason", "scheduling_state"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
ORDER BY "name";

/* =======================================================================================
   SECTION C - Pipeline health: classification distribution + per-layer row counts.
   =======================================================================================*/
-- Classification: every file got a type; junk -> 'other' (the gate).
SELECT DOC_TYPE, COUNT(*) AS n FROM DT_DEMO_CLM_CLASSIFIED GROUP BY DOC_TYPE ORDER BY n DESC;

SELECT 'file_log' AS layer, COUNT(*) AS n FROM DEMO_CLM_FILE_LOG
UNION ALL SELECT 'classified', COUNT(*) FROM DT_DEMO_CLM_CLASSIFIED
UNION ALL SELECT 'parsed',     COUNT(*) FROM DT_DEMO_CLM_PARSED
UNION ALL SELECT 'fnol',       COUNT(*) FROM DT_DEMO_CLM_FNOL
UNION ALL SELECT 'estimate',   COUNT(*) FROM DT_DEMO_CLM_ESTIMATE
UNION ALL SELECT 'police',     COUNT(*) FROM DT_DEMO_CLM_POLICE
UNION ALL SELECT 'photo',      COUNT(*) FROM DT_DEMO_CLM_PHOTO
UNION ALL SELECT 'claim',      COUNT(*) FROM DT_DEMO_CLM_CLAIM
UNION ALL SELECT 'triaged',    COUNT(*) FROM DT_DEMO_CLM_TRIAGED
ORDER BY layer;

/* =======================================================================================
   SECTION D - Deliverables: the operational payoff.
   =======================================================================================*/

-- D1 - Triage lanes: count + dollar value + auto-settle rate (the headline metric).
SELECT
  ROUTE,
  COUNT(*)                                          AS claims,
  ROUND(SUM(SETTLEMENT_ESTIMATE))                   AS total_settlement_usd,
  ROUND(AVG(SETTLEMENT_ESTIMATE))                   AS avg_settlement_usd,
  ROUND(100 * RATIO_TO_REPORT(COUNT(*)) OVER (), 1) AS pct_of_claims
FROM DT_DEMO_CLM_TRIAGED
GROUP BY ROUTE ORDER BY claims DESC;

-- D2 - The needs-review queue, highest settlement first (what an adjuster works through).
SELECT CLAIM_NO, CLAIMANT, ROUND(SETTLEMENT_ESTIMATE) AS settlement, FRAUD_RISK,
       ROUND(MIN_CONFIDENCE,2) AS min_conf, RECOMMENDED_ACTION, RATIONALE
FROM DEMO_CLM_NEEDS_REVIEW LIMIT 20;

-- D3 - Rejected (high fraud-risk / deny) with the model's reasoning + photo cues.
SELECT CLAIM_NO, CLAIMANT, ROUND(AMOUNT_CLAIMED) AS claimed, ROUND(ESTIMATE_TOTAL) AS estimate,
       FRAUD_RISK, PHOTO_FRAUD_CUES, RATIONALE
FROM DEMO_CLM_REJECTED;

-- D4 - AI vs ground truth (planted at synthesis; the pipeline never saw it).
--      Did the planted fraud cues get caught (land in reject / needs_review)?
SELECT
  gt.PLANTED_FRAUD,
  COUNT(*)                                       AS planted,
  COUNT_IF(t.ROUTE IN ('reject','needs_review')) AS escalated,
  COUNT_IF(t.ROUTE = 'auto_settle')              AS slipped_to_auto
FROM DEMO_CLM_GROUND_TRUTH gt
JOIN DT_DEMO_CLM_TRIAGED t ON t.CLAIM_NO = gt.CLAIM_NO
WHERE gt.PLANTED_FRAUD IS NOT NULL
GROUP BY gt.PLANTED_FRAUD ORDER BY planted DESC;

-- D5 - Extraction accuracy: AI-extracted amount_claimed vs the planted truth (within $1),
--      plus exact claimant-name match.
SELECT
  COUNT(*)                                                            AS claims,
  COUNT_IF(ABS(t.AMOUNT_CLAIMED - gt.AMOUNT_CLAIMED) < 1)             AS amount_exact,
  COUNT_IF(LOWER(TRIM(t.CLAIMANT)) = LOWER(TRIM(gt.CLAIMANT)))        AS claimant_exact,
  ROUND(100 * COUNT_IF(ABS(t.AMOUNT_CLAIMED - gt.AMOUNT_CLAIMED) < 1) / COUNT(*), 1) AS amount_pct
FROM DT_DEMO_CLM_TRIAGED t
JOIN DEMO_CLM_GROUND_TRUTH gt ON gt.CLAIM_NO = t.CLAIM_NO;

-- D6 - Vision's INDEPENDENT severity read vs the claim's stated band. Not a strict accuracy
--      metric: vision assesses the actual photo, and a divergence (a "severe" claim whose photo
--      reads "minor") is exactly the fraud signal we want, not an error.
SELECT gt.SEVERITY AS claimed_band, t.SEVERITY AS vision_read, COUNT(*) AS n
FROM DT_DEMO_CLM_TRIAGED t
JOIN DEMO_CLM_GROUND_TRUTH gt ON gt.CLAIM_NO = t.CLAIM_NO
WHERE t.HAS_PHOTO
GROUP BY 1,2 ORDER BY 1,2;
