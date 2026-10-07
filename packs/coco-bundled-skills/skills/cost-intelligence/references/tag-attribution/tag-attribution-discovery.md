# Tag Attribution Discovery Query

Discovers all tags applied to credit-consuming resources, resolves tag inheritance (direct > schema > database), and shows total credits attributed to each tag + value combination.

**Semantic keywords:** discover tags, available tags, tag cost overview, attribution coverage, what tags exist, untagged resources, cost by tag

---

### Discover All Tags and Their Attributed Costs

**Triggered by:** "What tags exist and how much is attributed to each?", "Show me my tag attribution coverage", "Which tags have the most cost?", "What percentage of spend is untagged?"

**Parameters:**
- `<START_TIME>`: Beginning of time window (e.g., `DATEADD(MONTH, -1, CURRENT_DATE())`)
- `<END_TIME>`: End of time window (e.g., `CURRENT_DATE()`)

```sql
WITH resource_credits AS (
    SELECT
        mh.ENTITY_TYPE,
        mh.ENTITY_ID,
        mh.NAME,
        mh.DATABASE_ID,
        mh.SCHEMA_ID,
        SUM(mh.CREDITS_USED) AS CREDITS
    FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY mh
    WHERE mh.START_TIME >= <START_TIME>
        AND mh.START_TIME < <END_TIME>
        -- Exclude rows with NULL ENTITY_TYPE (legacy/unclassified service types
        -- like HYBRID_TABLE_REQUESTS, POSTGRES_COMPUTE, etc.) since they are not taggable.
        AND mh.ENTITY_TYPE IS NOT NULL
    GROUP BY mh.ENTITY_TYPE, mh.ENTITY_ID, mh.NAME, mh.DATABASE_ID, mh.SCHEMA_ID
),

direct_tags AS (
    SELECT
        tr.DOMAIN,
        tr.OBJECT_ID,
        tr.TAG_ID,
        tr.TAG_DATABASE,
        tr.TAG_SCHEMA,
        tr.TAG_NAME,
        tr.TAG_VALUE
    FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES tr
    WHERE (
            UPPER(tr.DOMAIN) IN (SELECT DISTINCT UPPER(ENTITY_TYPE) FROM resource_credits)
            -- Include DATABASE and SCHEMA domains for tag inheritance resolution
            -- (a tag on a database/schema is inherited by resources within it).
            OR UPPER(tr.DOMAIN) IN ('DATABASE', 'SCHEMA')
        )
),

-- Tag inheritance resolution: direct tag (priority 1) > schema tag (priority 2) > database tag (priority 3).
-- A resource inherits a tag from its parent schema or database if it doesn't have the tag directly.
candidate_tags AS (
    -- Priority 1: Direct tag on the resource itself
    SELECT
        rc.ENTITY_ID,
        1 AS TAG_PRIORITY,
        dt.TAG_ID,
        dt.TAG_DATABASE,
        dt.TAG_SCHEMA,
        dt.TAG_NAME,
        dt.TAG_VALUE
    FROM resource_credits rc
    JOIN direct_tags dt
        ON rc.ENTITY_ID = dt.OBJECT_ID
        AND UPPER(rc.ENTITY_TYPE) = UPPER(dt.DOMAIN)

    UNION ALL

    -- Priority 2: Tag on the parent schema (inheritance)
    SELECT
        rc.ENTITY_ID,
        2 AS TAG_PRIORITY,
        dt.TAG_ID,
        dt.TAG_DATABASE,
        dt.TAG_SCHEMA,
        dt.TAG_NAME,
        dt.TAG_VALUE
    FROM resource_credits rc
    JOIN direct_tags dt
        ON rc.SCHEMA_ID = dt.OBJECT_ID
        AND UPPER(dt.DOMAIN) = 'SCHEMA'

    UNION ALL

    -- Priority 3: Tag on the parent database (inheritance)
    SELECT
        rc.ENTITY_ID,
        3 AS TAG_PRIORITY,
        dt.TAG_ID,
        dt.TAG_DATABASE,
        dt.TAG_SCHEMA,
        dt.TAG_NAME,
        dt.TAG_VALUE
    FROM resource_credits rc
    JOIN direct_tags dt
        ON rc.DATABASE_ID = dt.OBJECT_ID
        AND UPPER(dt.DOMAIN) = 'DATABASE'
),

resolved_tags AS (
    SELECT
        ENTITY_ID,
        TAG_ID,
        TAG_DATABASE,
        TAG_SCHEMA,
        TAG_NAME,
        TAG_VALUE
    FROM candidate_tags
    -- Keep only the highest-priority tag per entity+tag_id (direct wins over schema, schema wins over database).
    -- Entities with no tag at any level won't appear here and will fall into the "(untagged)" bucket via LEFT JOIN.
    QUALIFY ROW_NUMBER() OVER (PARTITION BY ENTITY_ID, TAG_ID ORDER BY TAG_PRIORITY) = 1
),

total_credits_cte AS (
    SELECT SUM(CREDITS) AS TOTAL_CREDITS FROM resource_credits
),

-- Denominator for PCT_WITHIN_ENTITY_TYPE. Computed before the LEFT JOIN to avoid
-- fan-out inflation (a single entity can resolve to multiple tags, which would
-- inflate a post-join SUM). This matches the Snowsight "Cost by tag" tile behavior,
-- which uses total credits per entity type as the denominator.
entity_type_totals AS (
    SELECT ENTITY_TYPE, SUM(CREDITS) AS ENTITY_TYPE_TOTAL
    FROM resource_credits
    GROUP BY ENTITY_TYPE
)

SELECT
    rc.ENTITY_TYPE,
    rt.TAG_ID,
    rt.TAG_DATABASE || '.' || rt.TAG_SCHEMA || '.' || rt.TAG_NAME AS FULLY_QUALIFIED_TAG,
    rt.TAG_NAME,
    COALESCE(rt.TAG_VALUE, '(untagged)') AS TAG_VALUE,
    CASE WHEN rt.TAG_ID IS NULL THEN TRUE ELSE FALSE END AS IS_UNATTRIBUTED,
    ROUND(SUM(rc.CREDITS), 2) AS CREDITS_USED,
    COUNT(DISTINCT rc.ENTITY_ID) AS RESOURCE_COUNT,
    -- PCT_WITHIN_ENTITY_TYPE: matches Snowsight's percentage on the "Cost by tag" tile.
    -- Denominator is all credits for this entity type (tagged + untagged).
    ROUND(100.0 * SUM(rc.CREDITS) / MAX(ett.ENTITY_TYPE_TOTAL), 1) AS PCT_WITHIN_ENTITY_TYPE,
    ROUND(100.0 * SUM(rc.CREDITS) / MAX(tc.TOTAL_CREDITS), 1) AS PCT_OF_TOTAL
FROM resource_credits rc
LEFT JOIN resolved_tags rt
    ON rc.ENTITY_ID = rt.ENTITY_ID
CROSS JOIN total_credits_cte tc
JOIN entity_type_totals ett ON rc.ENTITY_TYPE = ett.ENTITY_TYPE
GROUP BY rc.ENTITY_TYPE, rt.TAG_ID, rt.TAG_DATABASE, rt.TAG_SCHEMA, rt.TAG_NAME, COALESCE(rt.TAG_VALUE, '(untagged)')
ORDER BY rc.ENTITY_TYPE, CREDITS_USED DESC;
```

---

### Notes

- **Inheritance resolution:** The query resolves tags with direct > schema > database precedence. A tag applied directly to a warehouse takes priority over a tag inherited from its parent schema or database.
- **ENTITY_ID join:** Uses `METERING_HISTORY.ENTITY_ID = TAG_REFERENCES.OBJECT_ID` (ID-based join, not name-based).
- **All taggable entity types included:** The query includes all non-NULL entity types from METERING_HISTORY (WAREHOUSE, COMPUTE POOL, TABLE, TASK, PIPE, SCHEMA, REPLICATION GROUP, CORTEX AGENT, SNOWFLAKE INTELLIGENCE, STAGE, etc.). NULL entity types (legacy/unclassified rows) are excluded since they are not taggable.
- **TAG_ID partitioning:** The `QUALIFY ROW_NUMBER()` partitions by `(ENTITY_ID, TAG_ID)` so that each entity resolves independently per tag definition. If the same tag name exists in multiple schemas (different TAG_IDs), both are shown.
- **Untagged bucket:** Resources with no tag at any level (direct, schema, or database) appear in a "(untagged)" row per entity type with `IS_UNATTRIBUTED = TRUE`.
- **PCT_WITHIN_ENTITY_TYPE:** Matches the percentage shown on Snowsight's "Cost by tag" tile. The denominator is total credits for that entity type (computed pre-join to avoid fan-out from multi-tag entities).
- **Performance:** Typically completes in a few seconds for a 1-month window.
