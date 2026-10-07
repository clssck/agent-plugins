-- Combined semantic view quality query: binary signals + comment depth → quality_score.
-- Sources correct logic from sv_binary.sql (binary signals) and sv_comment.sql (comment length).
-- Output: one row per (semantic view FQN × base table) with all signals and composite quality_score.
--         Multiple rows per SV when it references more than one base table.
--
-- Optimized: each ACCOUNT_USAGE table is scanned exactly once.

-- Latest live semantic view per FQN with view-level comment.
WITH sv AS (
    SELECT
        SEMANTIC_VIEW_ID,
        SEMANTIC_VIEW_DATABASE_NAME || '.' || SEMANTIC_VIEW_SCHEMA_NAME || '.' || SEMANTIC_VIEW_NAME AS sv_fqn,
        comment AS view_comment
    FROM SNOWFLAKE.ACCOUNT_USAGE.SEMANTIC_VIEWS
    WHERE DELETED IS NULL
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY SEMANTIC_VIEW_DATABASE_NAME, SEMANTIC_VIEW_SCHEMA_NAME, SEMANTIC_VIEW_NAME
        ORDER BY LAST_ALTERED DESC NULLS LAST
    ) = 1
),

-- ═══════════════════════════════════════════════════════════════════════════════
-- SEMANTIC_TABLES: single scan for both binary signals and comments
-- ═══════════════════════════════════════════════════════════════════════════════

-- Deduplicate semantic tables to latest version per (view, table) pair.
st_deduped AS (
    SELECT SEMANTIC_VIEW_ID, SEMANTIC_TABLE_NAME,
           UPPER(BASE_TABLE_DATABASE_NAME) AS base_database,
           UPPER(BASE_TABLE_SCHEMA_NAME)   AS base_schema,
           UPPER(BASE_TABLE_NAME)          AS base_table,
           PRIMARY_KEYS, UNIQUE_KEYS, DISTINCT_RANGES, SYNONYMS,
           comment, last_altered
    FROM SNOWFLAKE.ACCOUNT_USAGE.SEMANTIC_TABLES
    WHERE DELETED IS NULL
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY SEMANTIC_VIEW_ID, SEMANTIC_TABLE_NAME
        ORDER BY LAST_ALTERED DESC NULLS LAST
    ) = 1
),

-- Distinct (SV, base table) mapping for joining CR scores.
st_base_tables AS (
    SELECT DISTINCT
        SEMANTIC_VIEW_ID,
        base_database,
        base_schema,
        base_table
    FROM st_deduped
    WHERE base_database IS NOT NULL AND base_table IS NOT NULL
),

-- Per-view binary signals: has PK, unique keys, distinct ranges, synonyms.
tbl_signals AS (
    SELECT
        SEMANTIC_VIEW_ID,
        COALESCE(BOOLOR_AGG(ARRAY_SIZE(PRIMARY_KEYS)    > 0), FALSE) AS has_pk,
        COALESCE(BOOLOR_AGG(ARRAY_SIZE(UNIQUE_KEYS)     > 0), FALSE) AS has_unique_keys,
        COALESCE(BOOLOR_AGG(ARRAY_SIZE(DISTINCT_RANGES) > 0), FALSE) AS has_distinct_ranges,
        COALESCE(BOOLOR_AGG(ARRAY_SIZE(SYNONYMS)        > 0), FALSE) AS tbl_has_synonyms
    FROM st_deduped
    GROUP BY 1
),

-- Collect all table-level comments per SV.
st_comments AS (
    SELECT
        SEMANTIC_VIEW_ID,
        ARRAY_AGG(comment) WITHIN GROUP (ORDER BY last_altered DESC) AS table_comments
    FROM st_deduped
    WHERE comment IS NOT NULL
    GROUP BY 1
),

-- ═══════════════════════════════════════════════════════════════════════════════
-- SEMANTIC_DIMENSIONS: single scan for synonyms and comments
-- ═══════════════════════════════════════════════════════════════════════════════

-- Deduplicate semantic dimensions to latest version per (view, dimension).
sd_deduped AS (
    SELECT SEMANTIC_VIEW_ID, SYNONYMS, comment, last_altered
    FROM SNOWFLAKE.ACCOUNT_USAGE.SEMANTIC_DIMENSIONS
    WHERE DELETED IS NULL
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY SEMANTIC_VIEW_ID, SEMANTIC_DIMENSION_NAME
        ORDER BY LAST_ALTERED DESC NULLS LAST
    ) = 1
),

-- TRUE if any dimension has synonyms.
sd_synonyms AS (
    SELECT SEMANTIC_VIEW_ID,
           COALESCE(BOOLOR_AGG(ARRAY_SIZE(SYNONYMS) > 0), FALSE) AS has_synonyms
    FROM sd_deduped
    GROUP BY 1
),

-- Collect all dimension-level comments per SV.
sd_comments AS (
    SELECT
        SEMANTIC_VIEW_ID,
        ARRAY_AGG(comment) WITHIN GROUP (ORDER BY last_altered DESC) AS dimension_comments
    FROM sd_deduped
    WHERE comment IS NOT NULL
    GROUP BY 1
),

-- ═══════════════════════════════════════════════════════════════════════════════
-- SEMANTIC_FACTS: single scan for synonyms and comments
-- ═══════════════════════════════════════════════════════════════════════════════

-- Deduplicate semantic facts to latest version per (view, fact).
sf_deduped AS (
    SELECT SEMANTIC_VIEW_ID, SYNONYMS, comment, last_altered
    FROM SNOWFLAKE.ACCOUNT_USAGE.SEMANTIC_FACTS
    WHERE DELETED IS NULL
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY SEMANTIC_VIEW_ID, SEMANTIC_FACT_NAME
        ORDER BY LAST_ALTERED DESC NULLS LAST
    ) = 1
),

-- TRUE if any fact has synonyms.
sf_synonyms AS (
    SELECT SEMANTIC_VIEW_ID,
           COALESCE(BOOLOR_AGG(ARRAY_SIZE(SYNONYMS) > 0), FALSE) AS has_synonyms
    FROM sf_deduped
    GROUP BY 1
),

-- Collect all fact-level comments per SV.
sf_comments AS (
    SELECT
        SEMANTIC_VIEW_ID,
        ARRAY_AGG(comment) WITHIN GROUP (ORDER BY last_altered DESC) AS fact_comments
    FROM sf_deduped
    WHERE comment IS NOT NULL
    GROUP BY 1
),

-- ═══════════════════════════════════════════════════════════════════════════════
-- SEMANTIC_METRICS: single scan for synonyms, metric existence, and comments
-- ═══════════════════════════════════════════════════════════════════════════════

-- Deduplicate semantic metrics to latest version per (view, metric).
sm_deduped AS (
    SELECT SEMANTIC_VIEW_ID, SYNONYMS, comment, last_altered
    FROM SNOWFLAKE.ACCOUNT_USAGE.SEMANTIC_METRICS
    WHERE DELETED IS NULL
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY SEMANTIC_VIEW_ID, SEMANTIC_METRIC_NAME
        ORDER BY LAST_ALTERED DESC NULLS LAST
    ) = 1
),

-- TRUE if any metric has synonyms.
sm_synonyms AS (
    SELECT SEMANTIC_VIEW_ID,
           COALESCE(BOOLOR_AGG(ARRAY_SIZE(SYNONYMS) > 0), FALSE) AS has_synonyms
    FROM sm_deduped
    GROUP BY 1
),

-- SVs that have at least one metric defined.
metric_signals AS (
    SELECT DISTINCT SEMANTIC_VIEW_ID
    FROM sm_deduped
),

-- Collect all metric-level comments per SV.
sm_comments AS (
    SELECT
        SEMANTIC_VIEW_ID,
        ARRAY_AGG(comment) WITHIN GROUP (ORDER BY last_altered DESC) AS metric_comments
    FROM sm_deduped
    WHERE comment IS NOT NULL
    GROUP BY 1
),

-- ═══════════════════════════════════════════════════════════════════════════════
-- SEMANTIC_RELATIONSHIPS: single scan
-- ═══════════════════════════════════════════════════════════════════════════════

-- SVs that have at least one relationship defined.
rel_signals AS (
    SELECT DISTINCT SEMANTIC_VIEW_ID
    FROM SNOWFLAKE.ACCOUNT_USAGE.SEMANTIC_RELATIONSHIPS
    WHERE DELETED IS NULL
),

-- ═══════════════════════════════════════════════════════════════════════════════
-- COMBINE: binary signals + comment depth + VQR count → quality_score
-- ═══════════════════════════════════════════════════════════════════════════════

-- Merge all comments across object types; compute avg comment length per SV.
comment_agg AS (
    SELECT
        sv.SEMANTIC_VIEW_ID,
        ARRAY_COMPACT(
            ARRAY_FLATTEN(ARRAY_CONSTRUCT(
                ARRAY_CONSTRUCT(sv.view_comment),
                COALESCE(stc.table_comments,     ARRAY_CONSTRUCT()),
                COALESCE(sdc.dimension_comments, ARRAY_CONSTRUCT()),
                COALESCE(sfc.fact_comments,      ARRAY_CONSTRUCT()),
                COALESCE(smc.metric_comments,    ARRAY_CONSTRUCT())
            ))
        ) AS all_comments,
        ROUND(LEN(ARRAY_TO_STRING(all_comments, '')) / NULLIF(ARRAY_SIZE(all_comments), 0), 1) AS avg_comment_length
    FROM sv
    LEFT JOIN st_comments stc ON sv.SEMANTIC_VIEW_ID = stc.SEMANTIC_VIEW_ID
    LEFT JOIN sd_comments sdc ON sv.SEMANTIC_VIEW_ID = sdc.SEMANTIC_VIEW_ID
    LEFT JOIN sf_comments sfc ON sv.SEMANTIC_VIEW_ID = sfc.SEMANTIC_VIEW_ID
    LEFT JOIN sm_comments smc ON sv.SEMANTIC_VIEW_ID = smc.SEMANTIC_VIEW_ID
),

-- Verified query counts per SV (injected by Python).
vqr_counts AS (
    {vqr_source}
)
-- Final output: binary signals + comment depth + VQR count → quality_score.
SELECT
    sv.sv_fqn,
    bt.base_database,
    bt.base_schema,
    bt.base_table,
    COALESCE(ts.has_pk, FALSE)                                                          AS has_pk,
    COALESCE(ts.tbl_has_synonyms OR sds.has_synonyms OR sfs.has_synonyms OR sms.has_synonyms, FALSE) AS has_synonyms,
    COALESCE(ts.has_unique_keys, FALSE)                                                 AS has_unique_keys,
    COALESCE(ts.has_distinct_ranges, FALSE)                                             AS has_distinct_ranges,
    (rs.SEMANTIC_VIEW_ID IS NOT NULL)                                                   AS has_relationships,
    (mets.SEMANTIC_VIEW_ID IS NOT NULL)                                                 AS has_metrics,
    COALESCE(c.avg_comment_length, 0.0)                                                 AS avg_comment_length,
    COALESCE(vq.n_verified_queries, 0)                                                  AS n_verified_queries,
    ROUND((
        COALESCE(ts.has_pk, FALSE)::INT
        + COALESCE(ts.tbl_has_synonyms OR sds.has_synonyms OR sfs.has_synonyms OR sms.has_synonyms, FALSE)::INT
        + COALESCE(ts.has_unique_keys, FALSE)::INT
        + COALESCE(ts.has_distinct_ranges, FALSE)::INT
        + (rs.SEMANTIC_VIEW_ID IS NOT NULL)::INT
        + (mets.SEMANTIC_VIEW_ID IS NOT NULL)::INT
        + 2 * (1 - EXP(-(LN(10) / 10) * COALESCE(vq.n_verified_queries, 0)))
        + 1 * (1 - EXP(-(LN(100) / 100) * COALESCE(c.avg_comment_length, 0.0)))
    ) / 9.0, 4) AS quality_score
FROM sv
LEFT JOIN st_base_tables bt   ON bt.SEMANTIC_VIEW_ID   = sv.SEMANTIC_VIEW_ID
LEFT JOIN tbl_signals    ts   ON ts.SEMANTIC_VIEW_ID   = sv.SEMANTIC_VIEW_ID
LEFT JOIN sd_synonyms    sds  ON sds.SEMANTIC_VIEW_ID  = sv.SEMANTIC_VIEW_ID
LEFT JOIN sf_synonyms    sfs  ON sfs.SEMANTIC_VIEW_ID  = sv.SEMANTIC_VIEW_ID
LEFT JOIN sm_synonyms    sms  ON sms.SEMANTIC_VIEW_ID  = sv.SEMANTIC_VIEW_ID
LEFT JOIN rel_signals    rs   ON rs.SEMANTIC_VIEW_ID   = sv.SEMANTIC_VIEW_ID
LEFT JOIN metric_signals mets ON mets.SEMANTIC_VIEW_ID = sv.SEMANTIC_VIEW_ID
LEFT JOIN comment_agg    c    ON c.SEMANTIC_VIEW_ID    = sv.SEMANTIC_VIEW_ID
LEFT JOIN vqr_counts     vq   ON vq.sv_fqn            = sv.sv_fqn
ORDER BY quality_score DESC;