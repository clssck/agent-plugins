-- Pipeline Context for Monitor Recommendations
-- Gathers UPSTREAM + DOWNSTREAM dependency signals for a target table so the agent
-- can recommend/prioritize DMFs by pipeline position, not just column type or
-- access frequency.
--
-- Primary source: SNOWFLAKE.CORE.GET_LINEAGE (object + data-movement lineage; no
-- account admin required). Falls back to ACCOUNT_USAGE.OBJECT_DEPENDENCIES when
-- GET_LINEAGE returns no rows or is not permitted (see fallback block at bottom).
--
-- GET_LINEAGE contract (see lineage/reference/snowflake-apis.md):
--   - Lives in SNOWFLAKE.CORE, NOT ACCOUNT_USAGE.
--   - Positional args only: GET_LINEAGE('<db>.<sch>.<obj>', 'TABLE', '<DIRECTION>', <distance 1-5>).
--   - Output columns are SOURCE_* / TARGET_* (there are NO UPSTREAM_*/DOWNSTREAM_* columns).
--
-- Replace <database>, <schema>, <table> with actual values BEFORE executing.
-- Run this once per candidate table identified in Step 2 (top-N by access/coverage).
--
-- NOTE: this template intentionally does NOT query ACCOUNT_USAGE.TABLES for row
-- count / last-altered metadata. ACCOUNT_USAGE views can take minutes to return on
-- large accounts; pipeline position + blast radius come from GET_LINEAGE alone.

WITH upstream_edges AS (
    -- What this table is built FROM (its feeders). DISTANCE 1 = direct parents.
    -- Domain filter is intentionally permissive (exclude only non-dataset domains)
    -- so new object types are counted automatically and nothing is silently dropped.
    SELECT
        gl.SOURCE_OBJECT_DATABASE || '.' || gl.SOURCE_OBJECT_SCHEMA || '.' || gl.SOURCE_OBJECT_NAME AS object_name,
        gl.SOURCE_OBJECT_DOMAIN AS object_type,
        gl.DISTANCE AS distance
    FROM TABLE(SNOWFLAKE.CORE.GET_LINEAGE('<database>.<schema>.<table>', 'TABLE', 'UPSTREAM', 5)) gl
    WHERE gl.SOURCE_OBJECT_DOMAIN NOT IN ('FUNCTION', 'PROCEDURE', 'PIPE')
),
downstream_edges AS (
    -- What depends on / is built FROM this table (its blast radius). DISTANCE 1 = direct children.
    SELECT
        gl.TARGET_OBJECT_DATABASE || '.' || gl.TARGET_OBJECT_SCHEMA || '.' || gl.TARGET_OBJECT_NAME AS object_name,
        gl.TARGET_OBJECT_DOMAIN AS object_type,
        gl.DISTANCE AS distance
    FROM TABLE(SNOWFLAKE.CORE.GET_LINEAGE('<database>.<schema>.<table>', 'TABLE', 'DOWNSTREAM', 5)) gl
    WHERE gl.TARGET_OBJECT_DOMAIN NOT IN ('FUNCTION', 'PROCEDURE', 'PIPE')
),
counts AS (
    SELECT
        (SELECT COUNT(DISTINCT object_name) FROM upstream_edges)                      AS upstream_count,
        (SELECT COUNT(DISTINCT object_name) FROM upstream_edges WHERE distance = 1)   AS direct_upstream_count,
        (SELECT COUNT(DISTINCT object_name) FROM downstream_edges)                    AS downstream_count,
        (SELECT COUNT(DISTINCT object_name) FROM downstream_edges WHERE distance = 1) AS direct_downstream_count
)
SELECT
    '<database>.<schema>.<table>' AS table_name,
    c.upstream_count,
    c.direct_upstream_count,
    c.downstream_count,
    c.direct_downstream_count,
    -- Pipeline position drives which table-level DMFs matter most.
    CASE
        WHEN c.upstream_count = 0 AND c.downstream_count > 0 THEN 'SOURCE'        -- ingestion / entry point
        WHEN c.upstream_count > 0 AND c.downstream_count = 0 THEN 'SINK'          -- leaf / consumption table
        WHEN c.upstream_count > 0 AND c.downstream_count > 0 THEN 'INTERMEDIATE'  -- transformation in the middle
        ELSE 'ISOLATED'                                                          -- no detected lineage
    END AS pipeline_position,
    -- High blast radius => failures propagate widely => escalate criticality.
    CASE WHEN c.downstream_count >= 5 THEN TRUE ELSE FALSE END AS high_blast_radius
FROM counts c;

/*
Columns returned (one row per target table):
  TABLE_NAME              — fully-qualified target table
  UPSTREAM_COUNT          — distinct upstream objects within 5 levels (0 => SOURCE / ingestion)
  DIRECT_UPSTREAM_COUNT   — distinct direct (distance 1) feeders
  DOWNSTREAM_COUNT        — distinct downstream objects within 5 levels (blast radius)
  DIRECT_DOWNSTREAM_COUNT — distinct direct (distance 1) dependents
  PIPELINE_POSITION       — SOURCE | INTERMEDIATE | SINK | ISOLATED
  HIGH_BLAST_RADIUS       — TRUE when downstream_count >= 5

Step 4 of monitor-recommendations.md describes how these signals re-weight the
column-type DMF mapping; see that workflow for the full action table.

Fallback (run ONLY if the query above errors or returns no lineage but the table
should have dependencies). OBJECT_DEPENDENCIES requires IMPORTED PRIVILEGES on
SNOWFLAKE and captures object dependency only (not data movement). It is schema-wide,
so it ranks every table in one shot:

  WITH downstream AS (
      SELECT
          REFERENCED_OBJECT_NAME AS table_name,
          COUNT(DISTINCT REFERENCING_DATABASE || '.' || REFERENCING_SCHEMA || '.' || REFERENCING_OBJECT_NAME) AS downstream_count
      FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES
      WHERE REFERENCED_DATABASE = '<database>'
        AND REFERENCED_SCHEMA = '<schema>'
        AND REFERENCED_OBJECT_DOMAIN = 'Table'
      GROUP BY 1
  ),
  upstream AS (
      SELECT
          REFERENCING_OBJECT_NAME AS table_name,
          COUNT(DISTINCT REFERENCED_DATABASE || '.' || REFERENCED_SCHEMA || '.' || REFERENCED_OBJECT_NAME) AS upstream_count
      FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES
      WHERE REFERENCING_DATABASE = '<database>'
        AND REFERENCING_SCHEMA = '<schema>'
        AND REFERENCING_OBJECT_DOMAIN = 'Table'
      GROUP BY 1
  )
  SELECT
      COALESCE(d.table_name, u.table_name) AS table_name,
      COALESCE(u.upstream_count, 0) AS upstream_count,
      COALESCE(d.downstream_count, 0) AS downstream_count,
      CASE
          WHEN COALESCE(u.upstream_count, 0) = 0 AND COALESCE(d.downstream_count, 0) > 0 THEN 'SOURCE'
          WHEN COALESCE(u.upstream_count, 0) > 0 AND COALESCE(d.downstream_count, 0) = 0 THEN 'SINK'
          WHEN COALESCE(u.upstream_count, 0) > 0 AND COALESCE(d.downstream_count, 0) > 0 THEN 'INTERMEDIATE'
          ELSE 'ISOLATED'
      END AS pipeline_position,
      CASE WHEN COALESCE(d.downstream_count, 0) >= 5 THEN TRUE ELSE FALSE END AS high_blast_radius
  FROM downstream d
  FULL OUTER JOIN upstream u ON d.table_name = u.table_name
  ORDER BY downstream_count DESC, upstream_count DESC;

If both GET_LINEAGE and OBJECT_DEPENDENCIES are unavailable, skip pipeline context
and fall back to access-frequency-only criticality (Step 2 / monitor-recommendations.sql).
*/
