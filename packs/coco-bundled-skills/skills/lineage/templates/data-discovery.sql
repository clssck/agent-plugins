-- Data Discovery: Find Relevant Datasets with Trust Scoring
-- Search for tables matching keywords and rank by trustworthiness
-- Replace <search_term> with topic/keyword to search

WITH matching_tables AS (
    -- Find tables matching search criteria
    SELECT
        t.table_catalog AS database_name,
        t.table_schema AS schema_name,
        t.table_name,
        t.table_type,
        t.row_count,
        t.bytes,
        t.created,
        t.last_altered,
        t.table_owner,
        t.comment
    FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES t
    WHERE t.deleted IS NULL
      AND (
          LOWER(t.table_name) LIKE LOWER('%<search_term>%')
          OR LOWER(t.table_schema) LIKE LOWER('%<search_term>%')
          OR LOWER(t.comment) LIKE LOWER('%<search_term>%')
      )
      -- Exclude system and staging schemas by default
      AND t.table_schema NOT IN ('INFORMATION_SCHEMA', 'ACCOUNT_USAGE')
),
usage_stats AS (
    -- Get usage statistics
    SELECT
        base.value:objectName::STRING AS object_name,
        COUNT(DISTINCT ah.query_id) AS query_count_30d,
        COUNT(DISTINCT ah.user_name) AS unique_users_30d,
        MAX(ah.query_start_time) AS last_accessed
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
    LATERAL FLATTEN(input => ah.base_objects_accessed) AS base
    WHERE ah.query_start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
    GROUP BY 1
),
trust_scores AS (
    SELECT
        m.database_name || '.' || m.schema_name || '.' || m.table_name AS full_name,
        m.*,
        u.query_count_30d,
        u.unique_users_30d,
        u.last_accessed,
        
        -- Freshness score (0-100)
        CASE
            WHEN m.last_altered > DATEADD(hour, -1, CURRENT_TIMESTAMP()) THEN 100
            WHEN m.last_altered > DATEADD(day, -1, CURRENT_TIMESTAMP()) THEN 80
            WHEN m.last_altered > DATEADD(day, -7, CURRENT_TIMESTAMP()) THEN 60
            WHEN m.last_altered > DATEADD(day, -30, CURRENT_TIMESTAMP()) THEN 40
            ELSE 20
        END AS freshness_score,
        
        -- Usage score (0-100)
        CASE
            WHEN COALESCE(u.unique_users_30d, 0) > 50 THEN 100
            WHEN COALESCE(u.unique_users_30d, 0) > 20 THEN 80
            WHEN COALESCE(u.unique_users_30d, 0) > 10 THEN 60
            WHEN COALESCE(u.unique_users_30d, 0) > 0 THEN 40
            ELSE 20
        END AS usage_score,
        
        -- Domain score (0-100) based on schema naming patterns
        -- Generated dynamically from config/schema-patterns.yaml
        /* SCHEMA_TRUST_SCORING:m.schema_name */ AS domain_score
        
    FROM matching_tables m
    LEFT JOIN usage_stats u 
        ON u.object_name = m.database_name || '.' || m.schema_name || '.' || m.table_name
)
SELECT
    full_name AS table_name,
    table_type,
    row_count,
    ROUND(bytes / 1024 / 1024, 2) AS size_mb,
    table_owner AS owner,
    comment AS description,
    query_count_30d AS queries_30d,
    unique_users_30d AS users_30d,
    last_accessed,
    last_altered,
    
    -- Overall trust score
    ROUND((freshness_score + usage_score + domain_score) / 3.0, 0) AS trust_score,
    
    -- Individual components
    freshness_score,
    usage_score,
    domain_score,
    
    -- Recommendation tier
    CASE
        WHEN (freshness_score + usage_score + domain_score) / 3.0 >= 80 THEN 'RECOMMENDED'
        WHEN (freshness_score + usage_score + domain_score) / 3.0 >= 50 THEN 'ACCEPTABLE'
        ELSE 'NOT_RECOMMENDED'
    END AS recommendation
    
FROM trust_scores
ORDER BY trust_score DESC, query_count_30d DESC NULLS LAST
LIMIT 20;
