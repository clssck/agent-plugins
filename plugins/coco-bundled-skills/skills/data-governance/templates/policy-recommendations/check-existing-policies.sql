-- ============================================================
-- CHECK 1: Policy kinds in use and attachment counts
-- ============================================================
-- Returns one row per policy kind showing how many policies
-- exist and how many table/column attachments they have.
-- Scoped to assessed databases only.

SELECT
    POLICY_KIND,
    COUNT(DISTINCT POLICY_NAME)               AS POLICY_COUNT,
    COUNT(*)                                  AS ATTACHMENT_COUNT,
    COUNT(DISTINCT REF_DATABASE_NAME)         AS DATABASES_COVERED
FROM SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES
WHERE POLICY_KIND IN (
        'MASKING_POLICY',
        'ROW_ACCESS_POLICY',
        'PROJECTION_POLICY',
        'AGGREGATION_POLICY',
        'JOIN_POLICY'
    )
  AND REF_DATABASE_NAME IN (<ASSESSED_DATABASES>)  -- Replace with user-confirmed database list
GROUP BY POLICY_KIND
ORDER BY POLICY_KIND;


-- ============================================================
-- CHECK 2: Detailed policy attachment inventory
-- ============================================================
-- Full list of every policy attachment in assessed databases:
-- policy kind, name, location, and what object/column it protects.

SELECT
    pr.POLICY_KIND,
    pr.POLICY_NAME,
    pr.POLICY_DB        AS POLICY_DATABASE,
    pr.POLICY_SCHEMA,
    pr.REF_DATABASE_NAME,
    pr.REF_SCHEMA_NAME,
    pr.REF_ENTITY_NAME  AS REF_TABLE_OR_VIEW,
    pr.REF_COLUMN_NAME,
    pr.REF_ENTITY_DOMAIN
FROM SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES pr
WHERE pr.POLICY_KIND IN (
        'MASKING_POLICY',
        'ROW_ACCESS_POLICY',
        'PROJECTION_POLICY',
        'AGGREGATION_POLICY',
        'JOIN_POLICY'
    )
  AND pr.REF_DATABASE_NAME IN (<ASSESSED_DATABASES>)  -- Replace with user-confirmed database list
ORDER BY pr.POLICY_KIND, pr.REF_DATABASE_NAME, pr.REF_ENTITY_NAME, pr.REF_COLUMN_NAME;


-- ============================================================
-- CHECK 3: Policy intent — sensitive categories currently protected
-- ============================================================
-- For each masking policy in use, shows which sensitivity categories
-- the attached columns carry. Used to infer the policy's intent
-- (e.g., this masking policy covers IDENTIFIER columns like SSN/EMAIL).

WITH masked_columns AS (
    SELECT
        pr.POLICY_KIND,
        pr.POLICY_NAME,
        pr.REF_DATABASE_NAME,
        pr.REF_SCHEMA_NAME,
        pr.REF_ENTITY_NAME,
        pr.REF_COLUMN_NAME
    FROM SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES pr
    WHERE pr.POLICY_KIND = 'MASKING_POLICY'
      AND pr.REF_DATABASE_NAME IN (<ASSESSED_DATABASES>)  -- Replace with user-confirmed database list
)
SELECT
    mc.POLICY_NAME,
    mc.POLICY_KIND,
    f.VALUE:recommendation:semantic_category::STRING  AS SEMANTIC_CATEGORY,
    f.VALUE:recommendation:privacy_category::STRING   AS PRIVACY_CATEGORY,
    COUNT(*)                                          AS COLUMN_COUNT
FROM masked_columns mc
JOIN SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST dcl
    ON  mc.REF_DATABASE_NAME = dcl.DATABASE_NAME
    AND mc.REF_SCHEMA_NAME   = dcl.SCHEMA_NAME
    AND mc.REF_ENTITY_NAME   = dcl.TABLE_NAME,
LATERAL FLATTEN(INPUT => dcl.RESULT) f
WHERE f.KEY = mc.REF_COLUMN_NAME
  AND f.VALUE:recommendation:privacy_category IS NOT NULL
GROUP BY mc.POLICY_NAME, mc.POLICY_KIND, SEMANTIC_CATEGORY, PRIVACY_CATEGORY
ORDER BY mc.POLICY_NAME, COLUMN_COUNT DESC;
