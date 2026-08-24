-- ============================================================
-- CHECK 1: Masking policies in the account
-- ============================================================
-- Lists all masking policies defined in the account.

SELECT
    POLICY_NAME,
    POLICY_CATALOG AS DATABASE_NAME,
    POLICY_SCHEMA AS SCHEMA_NAME,
    CREATED,
    LAST_ALTERED
FROM SNOWFLAKE.ACCOUNT_USAGE.MASKING_POLICIES
WHERE DELETED IS NULL
ORDER BY CREATED DESC
LIMIT 20;


-- ============================================================
-- CHECK 2: Masking policy attachments by database
-- ============================================================
-- Counts columns with masking policies attached, grouped by database.
-- Scoped to assessed databases only.

SELECT
    REF_DATABASE_NAME AS DATABASE_NAME,
    COUNT(DISTINCT REF_SCHEMA_NAME || '.' || REF_ENTITY_NAME || '.' || REF_COLUMN_NAME) AS MASKED_COLUMNS
FROM SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES
WHERE POLICY_KIND = 'MASKING_POLICY'
  AND REF_DATABASE_NAME IN (<ASSESSED_DATABASES>)  -- Replace with user-confirmed database list
GROUP BY REF_DATABASE_NAME
ORDER BY MASKED_COLUMNS DESC;


-- ============================================================
-- CHECK 3: Sensitive columns WITHOUT masking policies
-- ============================================================
-- Cross-references classified sensitive columns (parsed from the RESULT
-- VARIANT column via LATERAL FLATTEN) with policy attachments to find
-- gaps — sensitive data that is NOT protected.
-- Scoped to assessed databases (user-confirmed list from Step 2).

WITH classified_columns AS (
    SELECT
        dcl.DATABASE_NAME,
        dcl.SCHEMA_NAME,
        dcl.TABLE_NAME,
        f.KEY AS COLUMN_NAME,
        f.VALUE:recommendation:semantic_category::STRING AS SEMANTIC_CATEGORY,
        f.VALUE:recommendation:privacy_category::STRING AS PRIVACY_CATEGORY,
        f.VALUE:recommendation:confidence::STRING AS CONFIDENCE
    FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST dcl,
         LATERAL FLATTEN(INPUT => dcl.RESULT) f
    WHERE f.VALUE:recommendation:privacy_category::STRING
          IN ('IDENTIFIER', 'QUASI_IDENTIFIER', 'SENSITIVE')
      AND dcl.DATABASE_NAME IN (<ASSESSED_DATABASES>)  -- Replace with user-confirmed database list
)
SELECT
    c.DATABASE_NAME,
    c.SCHEMA_NAME,
    c.TABLE_NAME,
    c.COLUMN_NAME,
    c.SEMANTIC_CATEGORY,
    c.PRIVACY_CATEGORY,
    c.CONFIDENCE,
    CASE WHEN p.POLICY_NAME IS NOT NULL THEN 'MASKED' ELSE 'UNMASKED' END AS MASKING_STATUS
FROM classified_columns c
LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES p
    ON c.DATABASE_NAME = p.REF_DATABASE_NAME
    AND c.SCHEMA_NAME = p.REF_SCHEMA_NAME
    AND c.TABLE_NAME = p.REF_ENTITY_NAME
    AND c.COLUMN_NAME = p.REF_COLUMN_NAME
    AND p.POLICY_KIND = 'MASKING_POLICY'
ORDER BY c.DATABASE_NAME, c.SCHEMA_NAME, c.TABLE_NAME
LIMIT 200;


-- ============================================================
-- CHECK 4: Per-database masking summary for 4-tier scoring
-- ============================================================
-- For each assessed database, computes the counts needed to determine
-- the masking tier:
--   - total_sensitive_columns: sensitive columns found by classification
--   - masked_sensitive_columns: sensitive columns with a masking policy
--   - total_masked_columns: all columns with masking policies (including non-sensitive)
--
-- Masking tier logic (applied by the agent):
--   sensitive > 0 AND masked_sensitive = 0            → 0%   (Unprotected)
--   sensitive > 0 AND 0 < masked_sensitive < sensitive → 25%  (Partial)
--   sensitive = 0 AND total_masked > 0                → 75%  (Proactive)
--   sensitive > 0 AND masked_sensitive = sensitive     → 100% (Full)

WITH sensitive AS (
    SELECT
        dcl.DATABASE_NAME,
        dcl.SCHEMA_NAME,
        dcl.TABLE_NAME,
        f.KEY AS COLUMN_NAME
    FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST dcl,
         LATERAL FLATTEN(INPUT => dcl.RESULT) f
    WHERE f.VALUE:recommendation:privacy_category::STRING
          IN ('IDENTIFIER', 'QUASI_IDENTIFIER', 'SENSITIVE')
      AND dcl.DATABASE_NAME IN (<ASSESSED_DATABASES>)  -- Replace with user-confirmed database list
),
sensitive_per_db AS (
    SELECT
        DATABASE_NAME,
        COUNT(*) AS TOTAL_SENSITIVE_COLUMNS
    FROM sensitive
    GROUP BY DATABASE_NAME
),
masked_sensitive_per_db AS (
    SELECT
        s.DATABASE_NAME,
        COUNT(*) AS MASKED_SENSITIVE_COLUMNS
    FROM sensitive s
    INNER JOIN SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES p
        ON s.DATABASE_NAME = p.REF_DATABASE_NAME
        AND s.SCHEMA_NAME = p.REF_SCHEMA_NAME
        AND s.TABLE_NAME = p.REF_ENTITY_NAME
        AND s.COLUMN_NAME = p.REF_COLUMN_NAME
        AND p.POLICY_KIND = 'MASKING_POLICY'
    GROUP BY s.DATABASE_NAME
),
all_masked_per_db AS (
    SELECT
        REF_DATABASE_NAME AS DATABASE_NAME,
        COUNT(DISTINCT REF_SCHEMA_NAME || '.' || REF_ENTITY_NAME || '.' || REF_COLUMN_NAME) AS TOTAL_MASKED_COLUMNS
    FROM SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES
    WHERE POLICY_KIND = 'MASKING_POLICY'
      AND REF_DATABASE_NAME IN (<ASSESSED_DATABASES>)  -- Replace with user-confirmed database list
    GROUP BY REF_DATABASE_NAME
)
SELECT
    COALESCE(s.DATABASE_NAME, m.DATABASE_NAME) AS DATABASE_NAME,
    COALESCE(s.TOTAL_SENSITIVE_COLUMNS, 0) AS TOTAL_SENSITIVE_COLUMNS,
    COALESCE(ms.MASKED_SENSITIVE_COLUMNS, 0) AS MASKED_SENSITIVE_COLUMNS,
    COALESCE(m.TOTAL_MASKED_COLUMNS, 0) AS TOTAL_MASKED_COLUMNS
FROM sensitive_per_db s
FULL OUTER JOIN all_masked_per_db m
    ON s.DATABASE_NAME = m.DATABASE_NAME
LEFT JOIN masked_sensitive_per_db ms
    ON COALESCE(s.DATABASE_NAME, m.DATABASE_NAME) = ms.DATABASE_NAME
ORDER BY DATABASE_NAME;
