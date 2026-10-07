-- ============================================================
-- REMEDIATION IMPACT SCORE
-- ============================================================
-- Joins gap candidates with ACCESS_HISTORY column access counts
-- to compute an impact score:
--
--   impact_score = sensitivity_weight * queries_last_30d
--
-- Sensitivity weights:
--   IDENTIFIER       = 3.0  (direct PII: SSN, email, passport)
--   QUASI_IDENTIFIER = 2.0  (linkable: user ID, zip, DOB)
--   SENSITIVE        = 1.0  (internal confidential: salary, diagnosis)
--   HEURISTIC        = 0.5  (column name pattern, not yet confirmed)
--
-- Use this output to rank the remediation list in Steps 4 and 5.

WITH gap_columns AS (
    -- Classified sensitive columns without a masking or projection policy.
    -- Anti-join (LEFT JOIN ... IS NULL) rather than EXCEPT: EXCEPT would compare all
    -- columns, and the classification columns (SEMANTIC_CATEGORY, etc.) never match the
    -- policy side, so nothing would ever be excluded.
    SELECT
        c.DATABASE_NAME,
        c.SCHEMA_NAME,
        c.TABLE_NAME,
        c.COLUMN_NAME,
        c.SEMANTIC_CATEGORY,
        c.PRIVACY_CATEGORY,
        c.CONFIDENCE,
        'CLASSIFICATION'                                  AS DETECTION_METHOD
    FROM (
        SELECT
            dcl.DATABASE_NAME,
            dcl.SCHEMA_NAME,
            dcl.TABLE_NAME,
            f.KEY                                             AS COLUMN_NAME,
            f.VALUE:recommendation:semantic_category::STRING AS SEMANTIC_CATEGORY,
            f.VALUE:recommendation:privacy_category::STRING  AS PRIVACY_CATEGORY,
            f.VALUE:recommendation:confidence::STRING        AS CONFIDENCE
        FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST dcl,
             LATERAL FLATTEN(INPUT => dcl.RESULT) f
        WHERE f.VALUE:recommendation:privacy_category::STRING
              IN ('IDENTIFIER', 'QUASI_IDENTIFIER', 'SENSITIVE')
          AND dcl.DATABASE_NAME IN (<ASSESSED_DATABASES>)  -- Replace with user-confirmed database list
    ) c
    LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES pr
        ON  c.DATABASE_NAME = pr.REF_DATABASE_NAME
        AND c.SCHEMA_NAME   = pr.REF_SCHEMA_NAME
        AND c.TABLE_NAME    = pr.REF_ENTITY_NAME
        AND c.COLUMN_NAME   = pr.REF_COLUMN_NAME
        AND pr.POLICY_KIND  IN ('MASKING_POLICY', 'PROJECTION_POLICY')
    WHERE pr.REF_COLUMN_NAME IS NULL   -- keep only columns with no masking/projection policy
),
column_access_volume AS (
    SELECT
        SPLIT_PART(col.value:objectName::STRING, '.', 1)  AS DATABASE_NAME,
        SPLIT_PART(col.value:objectName::STRING, '.', 2)  AS SCHEMA_NAME,
        SPLIT_PART(col.value:objectName::STRING, '.', 3)  AS TABLE_NAME,
        cols.value:columnName::STRING                      AS COLUMN_NAME,
        COUNT(DISTINCT ah.QUERY_ID)                        AS QUERIES_LAST_30D,
        COUNT(DISTINCT ah.USER_NAME)                       AS DISTINCT_USERS
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
         LATERAL FLATTEN(INPUT => ah.DIRECT_OBJECTS_ACCESSED)        col,
         LATERAL FLATTEN(INPUT => col.value:columns, OUTER => TRUE)  cols
    WHERE ah.QUERY_START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
      AND col.value:objectDomain::STRING IN ('Table', 'View')
      AND SPLIT_PART(col.value:objectName::STRING, '.', 1)
          IN (<ASSESSED_DATABASES>)  -- Replace with user-confirmed database list
      AND cols.value:columnName IS NOT NULL
    GROUP BY DATABASE_NAME, SCHEMA_NAME, TABLE_NAME, COLUMN_NAME
),
reusable_policies AS (
    -- Best existing policy per semantic category (most recently created)
    -- These are candidates to reuse on gap columns (lowest-effort fix)
    SELECT
        pr.POLICY_DB || '.' || pr.POLICY_SCHEMA || '.' || pr.POLICY_NAME AS POLICY_FQN,
        pr.POLICY_KIND,
        f.VALUE:recommendation:semantic_category::STRING                  AS SEMANTIC_CATEGORY
    FROM SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES pr
    JOIN SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST dcl
        ON  pr.REF_DATABASE_NAME = dcl.DATABASE_NAME
        AND pr.REF_SCHEMA_NAME   = dcl.SCHEMA_NAME
        AND pr.REF_ENTITY_NAME   = dcl.TABLE_NAME,
    LATERAL FLATTEN(INPUT => dcl.RESULT) f
    WHERE pr.POLICY_KIND = 'MASKING_POLICY'
      AND f.KEY          = pr.REF_COLUMN_NAME
      AND f.VALUE:recommendation:semantic_category IS NOT NULL
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY f.VALUE:recommendation:semantic_category::STRING
        ORDER BY pr.CREATED DESC
    ) = 1
)
SELECT
    gc.DATABASE_NAME,
    gc.SCHEMA_NAME,
    gc.TABLE_NAME,
    gc.COLUMN_NAME,
    gc.SEMANTIC_CATEGORY,
    gc.PRIVACY_CATEGORY,
    gc.CONFIDENCE,
    gc.DETECTION_METHOD,
    COALESCE(cav.QUERIES_LAST_30D, 0)                           AS QUERIES_LAST_30D,
    COALESCE(cav.DISTINCT_USERS, 0)                             AS DISTINCT_USERS,
    CASE gc.PRIVACY_CATEGORY
        WHEN 'IDENTIFIER'       THEN 3.0
        WHEN 'QUASI_IDENTIFIER' THEN 2.0
        WHEN 'SENSITIVE'        THEN 1.0
        ELSE 0.5
    END                                                          AS SENSITIVITY_WEIGHT,
    CASE gc.PRIVACY_CATEGORY
        WHEN 'IDENTIFIER'       THEN 3.0
        WHEN 'QUASI_IDENTIFIER' THEN 2.0
        WHEN 'SENSITIVE'        THEN 1.0
        ELSE 0.5
    END * COALESCE(cav.QUERIES_LAST_30D, 0)                    AS IMPACT_SCORE,
    rp.POLICY_FQN                                               AS REUSABLE_POLICY,
    CASE
        WHEN rp.POLICY_FQN IS NOT NULL THEN 'Low'    -- Reuse existing policy
        ELSE                                'Medium'  -- New policy needed
    END                                                          AS REMEDIATION_EFFORT
FROM gap_columns gc
LEFT JOIN column_access_volume cav
    ON  gc.DATABASE_NAME = cav.DATABASE_NAME
    AND gc.SCHEMA_NAME   = cav.SCHEMA_NAME
    AND gc.TABLE_NAME    = cav.TABLE_NAME
    AND gc.COLUMN_NAME   = cav.COLUMN_NAME
LEFT JOIN reusable_policies rp
    ON gc.SEMANTIC_CATEGORY = rp.SEMANTIC_CATEGORY
ORDER BY IMPACT_SCORE DESC, gc.PRIVACY_CATEGORY, QUERIES_LAST_30D DESC
LIMIT 50;
