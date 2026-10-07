-- ============================================================
-- TAG-BASED OPPORTUNITIES: tagged columns without a policy
-- ============================================================
-- Finds governance tags applied to columns in assessed databases
-- where those columns have no masking policy attached.
-- Grouped by tag: one ALTER TAG ... SET MASKING POLICY statement
-- covers all N unprotected columns at once.

WITH tagged_columns AS (
    SELECT
        tr.TAG_DATABASE,
        tr.TAG_SCHEMA,
        tr.TAG_NAME,
        tr.TAG_DATABASE || '.' || tr.TAG_SCHEMA || '.' || tr.TAG_NAME
            AS TAG_FULLY_QUALIFIED,
        tr.OBJECT_DATABASE   AS DATABASE_NAME,
        tr.OBJECT_SCHEMA     AS SCHEMA_NAME,
        tr.OBJECT_NAME       AS TABLE_NAME,
        tr.COLUMN_NAME
    FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES tr
    WHERE tr.DOMAIN = 'COLUMN'
      AND tr.OBJECT_DATABASE IN (<ASSESSED_DATABASES>)  -- Replace with user-confirmed database list
      AND tr.TAG_DELETED IS NULL
      AND tr.TAG_DATABASE NOT ILIKE 'SNOWFLAKE'  -- system tags are read-only; ALTER TAG fails on them
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
),
unprotected_tagged AS (
    SELECT
        tc.TAG_FULLY_QUALIFIED,
        tc.TAG_DATABASE,
        tc.TAG_SCHEMA,
        tc.TAG_NAME,
        tc.DATABASE_NAME,
        tc.SCHEMA_NAME,
        tc.TABLE_NAME,
        tc.COLUMN_NAME
    FROM tagged_columns tc
    LEFT JOIN protected_columns pc
        ON  tc.DATABASE_NAME = pc.DATABASE_NAME
        AND tc.SCHEMA_NAME   = pc.SCHEMA_NAME
        AND tc.TABLE_NAME    = pc.TABLE_NAME
        AND tc.COLUMN_NAME   = pc.COLUMN_NAME
    WHERE pc.DATABASE_NAME IS NULL  -- Column has tag but no policy
)
SELECT
    ut.TAG_FULLY_QUALIFIED,
    ut.TAG_DATABASE,
    ut.TAG_SCHEMA,
    ut.TAG_NAME,
    COUNT(*)                          AS UNPROTECTED_COLUMN_COUNT,
    COUNT(DISTINCT ut.DATABASE_NAME)  AS DATABASES_AFFECTED,
    COUNT(DISTINCT ut.DATABASE_NAME || '.' || ut.SCHEMA_NAME || '.' || ut.TABLE_NAME) AS TABLES_AFFECTED
FROM unprotected_tagged ut
GROUP BY
    ut.TAG_FULLY_QUALIFIED,
    ut.TAG_DATABASE,
    ut.TAG_SCHEMA,
    ut.TAG_NAME
ORDER BY UNPROTECTED_COLUMN_COUNT DESC;


-- ============================================================
-- REUSABLE POLICIES by semantic category for tag attachment
-- ============================================================
-- For each tag with unprotected columns, finds existing masking
-- policies that already protect columns of the same semantic category.
-- These are the best candidates to reuse in an ALTER TAG statement.

WITH tag_categories AS (
    SELECT
        tr.TAG_DATABASE || '.' || tr.TAG_SCHEMA || '.' || tr.TAG_NAME
            AS TAG_FQN,
        f.VALUE:recommendation:semantic_category::STRING   AS SEMANTIC_CATEGORY,
        f.VALUE:recommendation:privacy_category::STRING    AS PRIVACY_CATEGORY,
        COUNT(*)                                            AS COL_COUNT
    FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES tr
    JOIN SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST dcl
        ON  tr.OBJECT_DATABASE = dcl.DATABASE_NAME
        AND tr.OBJECT_SCHEMA   = dcl.SCHEMA_NAME
        AND tr.OBJECT_NAME     = dcl.TABLE_NAME,
    LATERAL FLATTEN(INPUT => dcl.RESULT) f
    WHERE tr.DOMAIN            = 'COLUMN'
      AND f.KEY                = tr.COLUMN_NAME
      AND tr.OBJECT_DATABASE   IN (<ASSESSED_DATABASES>)
      AND tr.TAG_DELETED       IS NULL
      AND tr.TAG_DATABASE      NOT ILIKE 'SNOWFLAKE'  -- system tags are read-only; ALTER TAG fails on them
      AND f.VALUE:recommendation:privacy_category IS NOT NULL
    GROUP BY TAG_FQN, SEMANTIC_CATEGORY, PRIVACY_CATEGORY
),
policies_by_category AS (
    SELECT
        pr.POLICY_DB || '.' || pr.POLICY_SCHEMA || '.' || pr.POLICY_NAME
            AS POLICY_FQN,
        pr.POLICY_KIND,
        f.VALUE:recommendation:semantic_category::STRING   AS SEMANTIC_CATEGORY,
        COUNT(*)                                            AS PROTECTED_COL_COUNT
    FROM SNOWFLAKE.ACCOUNT_USAGE.POLICY_REFERENCES pr
    JOIN SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST dcl
        ON  pr.REF_DATABASE_NAME = dcl.DATABASE_NAME
        AND pr.REF_SCHEMA_NAME   = dcl.SCHEMA_NAME
        AND pr.REF_ENTITY_NAME   = dcl.TABLE_NAME,
    LATERAL FLATTEN(INPUT => dcl.RESULT) f
    WHERE pr.POLICY_KIND = 'MASKING_POLICY'
      AND f.KEY          = pr.REF_COLUMN_NAME
    GROUP BY POLICY_FQN, pr.POLICY_KIND, SEMANTIC_CATEGORY
    -- Keep one reusable policy per semantic category (the one protecting the most columns)
    -- so the LEFT JOIN below doesn't fan out when several policies cover the same category.
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY SEMANTIC_CATEGORY ORDER BY PROTECTED_COL_COUNT DESC
    ) = 1
)
SELECT
    tc.TAG_FQN,
    tc.SEMANTIC_CATEGORY,
    tc.PRIVACY_CATEGORY,
    tc.COL_COUNT             AS UNPROTECTED_COLUMNS_WITH_TAG,
    pbc.POLICY_FQN           AS REUSABLE_POLICY,
    pbc.PROTECTED_COL_COUNT  AS POLICY_ALREADY_PROTECTS_N_COLS
FROM tag_categories tc
LEFT JOIN policies_by_category pbc
    ON tc.SEMANTIC_CATEGORY = pbc.SEMANTIC_CATEGORY
ORDER BY tc.COL_COUNT DESC;
