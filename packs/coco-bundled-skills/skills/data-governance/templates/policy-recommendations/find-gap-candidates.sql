-- ============================================================
-- GAP 1: Classified sensitive columns without any policy
-- ============================================================
-- Finds columns that data classification has flagged as sensitive
-- but that have no masking or projection policy attached.
-- Scoped to assessed databases.

WITH classified_sensitive AS (
    SELECT
        dcl.DATABASE_NAME,
        dcl.SCHEMA_NAME,
        dcl.TABLE_NAME,
        f.KEY                                                     AS COLUMN_NAME,
        f.VALUE:recommendation:semantic_category::STRING          AS SEMANTIC_CATEGORY,
        f.VALUE:recommendation:privacy_category::STRING           AS PRIVACY_CATEGORY,
        f.VALUE:recommendation:confidence::STRING                 AS CONFIDENCE
    FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST dcl,
         LATERAL FLATTEN(INPUT => dcl.RESULT) f
    WHERE f.VALUE:recommendation:privacy_category::STRING
          IN ('IDENTIFIER', 'QUASI_IDENTIFIER', 'SENSITIVE')
      AND dcl.DATABASE_NAME IN (<ASSESSED_DATABASES>)  -- Replace with user-confirmed database list
),
protected_columns AS (
    SELECT DISTINCT
        REF_DATABASE_NAME  AS DATABASE_NAME,
        REF_SCHEMA_NAME    AS SCHEMA_NAME,
        REF_ENTITY_NAME    AS TABLE_NAME,
        REF_COLUMN_NAME    AS COLUMN_NAME
    FROM SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES
    WHERE POLICY_KIND IN ('MASKING_POLICY', 'PROJECTION_POLICY')
      AND REF_DATABASE_NAME IN (<ASSESSED_DATABASES>)  -- Replace with user-confirmed database list
)
SELECT
    cs.DATABASE_NAME,
    cs.SCHEMA_NAME,
    cs.TABLE_NAME,
    cs.COLUMN_NAME,
    cs.SEMANTIC_CATEGORY,
    cs.PRIVACY_CATEGORY,
    cs.CONFIDENCE,
    'CLASSIFICATION'      AS DETECTION_METHOD
FROM classified_sensitive cs
LEFT JOIN protected_columns pc
    ON  cs.DATABASE_NAME = pc.DATABASE_NAME
    AND cs.SCHEMA_NAME   = pc.SCHEMA_NAME
    AND cs.TABLE_NAME    = pc.TABLE_NAME
    AND cs.COLUMN_NAME   = pc.COLUMN_NAME
WHERE pc.DATABASE_NAME IS NULL  -- No policy attached
ORDER BY cs.DATABASE_NAME, cs.SCHEMA_NAME, cs.TABLE_NAME, cs.COLUMN_NAME;


-- ============================================================
-- GAP 2: Column-name heuristic gaps (unclassified databases)
-- ============================================================
-- Finds columns matching common sensitive-data naming patterns
-- in databases that have not been classified yet.

WITH heuristic_columns AS (
    SELECT
        c.TABLE_CATALOG  AS DATABASE_NAME,
        c.TABLE_SCHEMA   AS SCHEMA_NAME,
        c.TABLE_NAME,
        c.COLUMN_NAME,
        CASE
            WHEN c.COLUMN_NAME ILIKE '%SSN%'
              OR c.COLUMN_NAME ILIKE '%SOCIAL_SECURITY%'    THEN 'SSN'
            WHEN c.COLUMN_NAME ILIKE '%EMAIL%'              THEN 'EMAIL'
            WHEN c.COLUMN_NAME ILIKE '%PHONE%'              THEN 'PHONE'
            WHEN c.COLUMN_NAME ILIKE '%CREDIT_CARD%'
              OR c.COLUMN_NAME ILIKE '%CARD_NUMBER%'
              OR c.COLUMN_NAME ILIKE '%CC_NUM%'             THEN 'CREDIT_CARD'
            WHEN c.COLUMN_NAME ILIKE '%PASSPORT%'           THEN 'PASSPORT'
            WHEN c.COLUMN_NAME ILIKE '%DATE_OF_BIRTH%'
              OR c.COLUMN_NAME ILIKE '%DOB%'                THEN 'DATE_OF_BIRTH'
            WHEN c.COLUMN_NAME ILIKE '%SALARY%'
              OR c.COLUMN_NAME ILIKE '%COMPENSATION%'       THEN 'SALARY'
            WHEN c.COLUMN_NAME ILIKE '%TAX_ID%'
              OR c.COLUMN_NAME ILIKE '%EIN%'
              OR c.COLUMN_NAME ILIKE '%TIN%'                THEN 'TAX_ID'
            WHEN c.COLUMN_NAME ILIKE '%IP_ADDRESS%'
              OR c.COLUMN_NAME ILIKE '%IP_ADDR%'            THEN 'IP_ADDRESS'
            WHEN c.COLUMN_NAME ILIKE '%NATIONAL_ID%'
              OR c.COLUMN_NAME ILIKE '%GOV_ID%'             THEN 'NATIONAL_ID'
        END                                                 AS HEURISTIC_CATEGORY
    FROM SNOWFLAKE.ACCOUNT_USAGE.COLUMNS c   -- account-wide; INFORMATION_SCHEMA.COLUMNS only covers the session's current database
    WHERE c.TABLE_CATALOG IN (<ASSESSED_DATABASES>)  -- Replace with user-confirmed database list
      AND c.TABLE_SCHEMA NOT IN ('INFORMATION_SCHEMA')
      AND c.DELETED IS NULL
),
classified_dbs AS (
    SELECT DISTINCT DATABASE_NAME
    FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST
),
protected_columns AS (
    SELECT DISTINCT
        REF_DATABASE_NAME  AS DATABASE_NAME,
        REF_SCHEMA_NAME    AS SCHEMA_NAME,
        REF_ENTITY_NAME    AS TABLE_NAME,
        REF_COLUMN_NAME    AS COLUMN_NAME
    FROM SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES
    WHERE POLICY_KIND IN ('MASKING_POLICY', 'PROJECTION_POLICY')
      AND REF_DATABASE_NAME IN (<ASSESSED_DATABASES>)
)
SELECT
    hc.DATABASE_NAME,
    hc.SCHEMA_NAME,
    hc.TABLE_NAME,
    hc.COLUMN_NAME,
    hc.HEURISTIC_CATEGORY  AS SEMANTIC_CATEGORY,
    'IDENTIFIER'            AS PRIVACY_CATEGORY,
    'HEURISTIC'             AS CONFIDENCE,
    'COLUMN_NAME_HEURISTIC' AS DETECTION_METHOD
FROM heuristic_columns hc
LEFT JOIN classified_dbs cd
    ON hc.DATABASE_NAME = cd.DATABASE_NAME
LEFT JOIN protected_columns pc
    ON  hc.DATABASE_NAME = pc.DATABASE_NAME
    AND hc.SCHEMA_NAME   = pc.SCHEMA_NAME
    AND hc.TABLE_NAME    = pc.TABLE_NAME
    AND hc.COLUMN_NAME   = pc.COLUMN_NAME
WHERE hc.HEURISTIC_CATEGORY IS NOT NULL
  AND cd.DATABASE_NAME IS NULL    -- Database not yet classified
  AND pc.DATABASE_NAME IS NULL    -- Column not yet protected
ORDER BY hc.DATABASE_NAME, hc.TABLE_NAME, hc.COLUMN_NAME;


-- ============================================================
-- GAP 3: Tables with quasi-identifiers but no aggregation policy
-- ============================================================
-- Surfaces tables containing individual-level quasi-identifiers
-- (user IDs, patient IDs, customer IDs) with no aggregation policy.
-- Analytics queries on these tables can surface individual records.

WITH tables_with_quasi_ids AS (
    SELECT
        dcl.DATABASE_NAME,
        dcl.SCHEMA_NAME,
        dcl.TABLE_NAME,
        COUNT(DISTINCT f.KEY)  AS QUASI_ID_COLUMN_COUNT
    FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST dcl,
         LATERAL FLATTEN(INPUT => dcl.RESULT) f
    WHERE f.VALUE:recommendation:privacy_category::STRING = 'QUASI_IDENTIFIER'
      AND dcl.DATABASE_NAME IN (<ASSESSED_DATABASES>)  -- Replace with user-confirmed database list
    GROUP BY dcl.DATABASE_NAME, dcl.SCHEMA_NAME, dcl.TABLE_NAME
),
tables_with_agg_policy AS (
    SELECT DISTINCT
        REF_DATABASE_NAME  AS DATABASE_NAME,
        REF_SCHEMA_NAME    AS SCHEMA_NAME,
        REF_ENTITY_NAME    AS TABLE_NAME
    FROM SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES
    WHERE POLICY_KIND = 'AGGREGATION_POLICY'
      AND REF_DATABASE_NAME IN (<ASSESSED_DATABASES>)
)
SELECT
    tq.DATABASE_NAME,
    tq.SCHEMA_NAME,
    tq.TABLE_NAME,
    tq.QUASI_ID_COLUMN_COUNT,
    'AGGREGATION'           AS SUGGESTED_POLICY_KIND,
    'No aggregation policy on table with individual-level IDs' AS GAP_DESCRIPTION
FROM tables_with_quasi_ids tq
LEFT JOIN tables_with_agg_policy ap
    ON  tq.DATABASE_NAME = ap.DATABASE_NAME
    AND tq.SCHEMA_NAME   = ap.SCHEMA_NAME
    AND tq.TABLE_NAME    = ap.TABLE_NAME
WHERE ap.DATABASE_NAME IS NULL
ORDER BY tq.QUASI_ID_COLUMN_COUNT DESC;
