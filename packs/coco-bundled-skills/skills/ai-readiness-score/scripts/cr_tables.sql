-- Overview: Per-table "consumption readiness" from Snowflake usage over ~7 days.
-- Flow:
-- (1) flatten access_history to one row per (query_id, base table);
-- (2) join query_history and apply a layered filter stack to keep only genuine
--     analytical reads (SELECT, no error, execution_time > 0, warehouse-backed,
--     not client-generated, not Snowflake-internal);
-- (3) aggregate reads / distinct users / p50 latency per table;
-- (4) attach DDL freshness from account_usage.tables;
-- (5) percentile-rank activity and audience within the scored population;
-- (6) Cobb–Douglas blend → consumption_readiness_score
--     (Activity 35%, Consumption 30%, Speed 20%, Freshness 15%).
--
-- Placeholder: {sample_predicate} — "AND MOD(ABS(HASH(ah.query_id) % 100), 100) < N" or ""


-- One row per (query_id, base table) for read-only queries in the 7-day window.
WITH ah_base AS (
    SELECT
        f.value:objectName::string                               AS full_table_name,
        UPPER(SPLIT_PART(f.value:objectName::string, '.', 1))    AS database_name,
        UPPER(SPLIT_PART(f.value:objectName::string, '.', 2))    AS schema_name,
        UPPER(SPLIT_PART(f.value:objectName::string, '.', 3))    AS table_name,
        ah.query_id,
        ah.user_name
    FROM snowflake.account_usage.access_history ah,
         LATERAL FLATTEN(input => ah.base_objects_accessed) f  -- one row per accessed table
    WHERE ah.query_start_time::DATE BETWEEN '{start_ts}'::DATE AND '{end_ts}'::DATE
      AND ARRAY_SIZE(ah.objects_modified) = 0          -- read-only queries (no writes)
      AND f.value:objectDomain::string = 'Table'       -- only base tables, not views/stages
      AND SPLIT_PART(f.value:objectName::string, '.', 2) != ''
      AND SPLIT_PART(f.value:objectName::string, '.', 3) != ''
      {sample_predicate} -- deterministic sampling 
),
-- Join query_history + sessions; keep only genuine analytical SELECTs and BI tools
reads_joined AS (
    SELECT
        ab.database_name,
        ab.schema_name,
        ab.table_name,
        ab.full_table_name,
        ab.user_name,
        qh.execution_time AS execution_time_ms,
        TRY_PARSE_JSON(s.CLIENT_ENVIRONMENT):APPLICATION::string AS application_name, -- client app name
        -- based on: https://github.com/snowflake-eng/datascience-airflow/blob/38c3ba7751d6d0609cd07990ea7a015fc3245ced/product/udfs/snowhouse/product/parse_session_tool.sql
        CASE WHEN application_name
                  ILIKE ANY ('%looker%', '%googledatastudio%', '%tabproto%',
                             '%tableauserver%', '%tableau%prep%', '%tableaudesktop%',
                             '%tableaubridge%', '%tableaucloud%',
                             '%Power%BI%', '%data gateway%', '%MashupEngine%',
                             '%Onpremisesdatagateway%',
                             '%thoughtspot%', '%microstrategy%', '%sisense%',
                             '%metabase%', '%cognos%', '%spotfire%', '%qlik%',
                             '%atscale%', '%cluvio%', '%gooddata%', '%sisu_data%',
                             '%SAP%BusinessObjects%', '%bobjenterprise%', '%domo%',
                             '%periscope%', '%abinitio%', '%birst%', '%chartio%',
                             '%zoomdata%', '%datavaultbuilder%', '%adverity%',
                             '%astrato%')
             OR application_name = 'Sigma Σ'
             OR application_name = 'M'
             OR application_name = 'modeanalytics'
             OR application_name ILIKE 'Snowflake Web App (snowsight\\_streamlit)'
             OR application_name ILIKE 'Snowflake Web App (snowsight\\_dashboard)'
             OR application_name = 'streamlit'
             OR application_name ILIKE 'SNOWCLI.STREAMLIT%'
             THEN 1 ELSE NULL END AS is_bi_or_dashboard -- 1 if BI tool, else NULL
    FROM ah_base ab
    JOIN snowflake.account_usage.query_history qh -- query metadata
        ON ab.query_id = qh.query_id
    LEFT JOIN snowflake.account_usage.sessions s -- session client info
        ON qh.session_id = s.session_id
    WHERE qh.query_type = 'SELECT'                                                 
      AND qh.error_code IS NULL                                         -- no failed queries
      AND qh.execution_time > 0                                         -- actually ran
      AND qh.warehouse_id IS NOT NULL                                   -- warehouse-backed
      AND qh.is_client_generated_statement = FALSE                      -- not auto-generated
      AND (qh.user_type IS NULL OR qh.user_type != 'SNOWFLAKE_SERVICE') -- not internal service
      AND qh.start_time::DATE BETWEEN '{start_ts}'::DATE AND '{end_ts}'::DATE
),
-- Aggregate read counts, user counts, BI tool usage, and median latency per table.
reads_agg AS (
    SELECT
        database_name,
        schema_name,
        table_name,
        full_table_name,
        COUNT(*)                  AS analytical_reads,
        COUNT(DISTINCT user_name) AS distinct_users,        
        COUNT(is_bi_or_dashboard) AS app_reads,  
        COUNT(DISTINCT CASE WHEN is_bi_or_dashboard = 1
            THEN application_name END) AS distinct_app_tools, -- how many different BI tools use it
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY execution_time_ms) AS p50_execution_ms -- median query latency
    FROM reads_joined
    GROUP BY database_name, schema_name, table_name, full_table_name
    HAVING COUNT(*) >= 5 -- ignore tables with <5 reads (noise)
),
-- DDL freshness: days since last ALTER/DML per table (60-day lookback).
table_meta AS (
    SELECT
        UPPER(table_catalog) AS database_name,
        UPPER(table_schema)  AS schema_name,
        UPPER(table_name)    AS table_name,
        DATEDIFF('day', last_altered, CURRENT_TIMESTAMP()) AS days_since_update  -- staleness in days
    FROM snowflake.account_usage.tables
    WHERE deleted IS NULL                                                        -- live tables only
      AND table_type = 'BASE TABLE'                                              -- skip views/temp
      AND last_altered >= '{freshness_start_ts}'::TIMESTAMP_LTZ                  -- 60-day ceiling
),
-- Attach freshness to read stats; default 60 days if no DDL metadata found.
reads_with_freshness AS (
    SELECT
        r.database_name, r.schema_name, r.table_name, r.full_table_name,
        r.analytical_reads, r.distinct_users, r.app_reads, r.distinct_app_tools,
        r.p50_execution_ms,
        COALESCE(m.days_since_update, 60) AS days_since_update -- 60 = worst case
    FROM reads_agg r
    LEFT JOIN table_meta m
        ON r.database_name = m.database_name
       AND r.schema_name   = m.schema_name
       AND r.table_name    = m.table_name
),
-- Percentile-rank each table within the scored population.
pct_ranked AS (
    SELECT *,
        PERCENT_RANK() OVER (ORDER BY analytical_reads) AS activity_pctile,      -- read volume rank
        PERCENT_RANK() OVER (ORDER BY distinct_users)   AS user_pctile,          -- audience breadth rank
        PERCENT_RANK() OVER (ORDER BY app_reads)        AS app_pctile            -- BI tool adoption rank
    FROM reads_with_freshness
)
-- Final output: individual scores + Cobb-Douglas composite.
SELECT
    database_name, schema_name, table_name, full_table_name,
    analytical_reads, distinct_users, app_reads, distinct_app_tools,
    ROUND(activity_pctile, 4)                                         AS activity_score,      -- 35% weight
    ROUND(GREATEST(user_pctile, app_pctile), 4)                       AS consumption_score,   -- 30% weight
    ROUND(1.0 / (1.0 + POW(p50_execution_ms / 5000.0, 3)), 4)         AS speed_score,         -- 20% weight
    ROUND(EXP(-LN(2) / 30.0 * days_since_update), 4)                  AS freshness_score,     -- 15% weight
    ROUND(
        POW(GREATEST(activity_pctile, 0.001), 0.35)                                           -- activity
      * POW(GREATEST(GREATEST(user_pctile, app_pctile), 0.001), 0.30)                         -- consumption
      * POW(GREATEST(1.0 / (1.0 + POW(p50_execution_ms / 5000.0, 3)), 0.001), 0.20)           -- speed
      * POW(GREATEST(EXP(-LN(2) / 30.0 * days_since_update), 0.001), 0.15)                    -- freshness
    , 4) AS consumption_readiness_score
FROM pct_ranked
ORDER BY consumption_readiness_score DESC;
