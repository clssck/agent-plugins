# Tag Attribution: Resource-Level Query

Shows cost breakdown per resource for a specific tag + value, with inheritance resolution (direct > schema > database).

**Semantic keywords:** resource cost by tag, dedicated resource attribution, warehouse cost by tag, tag value cost breakdown

---

### Resource-Level Cost for a Specific Tag + Value

**Triggered by:** "What resources are attributed to this tag value?", "Show me the cost breakdown for tag X = Y", "Which warehouses belong to this cost center?"

**Parameters:**
- `<TAG_ID>`: The TAG_ID of the selected tag
- `<TAG_VALUE>`: The specific tag value to filter on
- `<START_TIME>`: Beginning of time window
- `<END_TIME>`: End of time window

```sql
WITH resource_credits AS (
    SELECT
        mh.ENTITY_TYPE,
        mh.ENTITY_ID,
        mh.NAME,
        mh.SERVICE_TYPE,
        mh.DATABASE_ID,
        mh.SCHEMA_ID,
        SUM(mh.CREDITS_USED) AS CREDITS,
        SUM(mh.CREDITS_USED_COMPUTE) AS CREDITS_COMPUTE,
        SUM(mh.CREDITS_USED_CLOUD_SERVICES) AS CREDITS_CLOUD
    FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY mh
    WHERE mh.START_TIME >= <START_TIME>
        AND mh.START_TIME < <END_TIME>
        -- Exclude rows with NULL ENTITY_TYPE (legacy/unclassified service types) since they are not taggable.
        AND mh.ENTITY_TYPE IS NOT NULL
    GROUP BY mh.ENTITY_TYPE, mh.ENTITY_ID, mh.NAME, mh.SERVICE_TYPE, mh.DATABASE_ID, mh.SCHEMA_ID
),

direct_tags AS (
    SELECT tr.DOMAIN, tr.OBJECT_ID, tr.TAG_VALUE
    FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES tr
    WHERE tr.TAG_ID = <TAG_ID>
        AND (
            UPPER(tr.DOMAIN) IN (SELECT DISTINCT UPPER(ENTITY_TYPE) FROM resource_credits)
            -- Include DATABASE and SCHEMA domains for tag inheritance resolution.
            OR UPPER(tr.DOMAIN) IN ('DATABASE', 'SCHEMA')
        )
),

-- Tag inheritance resolution: direct tag (priority 1) > schema tag (priority 2) > database tag (priority 3).
candidate_tags AS (
    -- Priority 1: Direct tag on the resource
    SELECT rc.ENTITY_ID, 1 AS TAG_PRIORITY, dt.TAG_VALUE
    FROM resource_credits rc
    JOIN direct_tags dt
        ON rc.ENTITY_ID = dt.OBJECT_ID
        AND UPPER(rc.ENTITY_TYPE) = UPPER(dt.DOMAIN)

    UNION ALL

    -- Priority 2: Tag on parent schema
    SELECT rc.ENTITY_ID, 2 AS TAG_PRIORITY, dt.TAG_VALUE
    FROM resource_credits rc
    JOIN direct_tags dt
        ON rc.SCHEMA_ID = dt.OBJECT_ID
        AND UPPER(dt.DOMAIN) = 'SCHEMA'

    UNION ALL

    -- Priority 3: Tag on parent database
    SELECT rc.ENTITY_ID, 3 AS TAG_PRIORITY, dt.TAG_VALUE
    FROM resource_credits rc
    JOIN direct_tags dt
        ON rc.DATABASE_ID = dt.OBJECT_ID
        AND UPPER(dt.DOMAIN) = 'DATABASE'
),

resolved_tags AS (
    SELECT ENTITY_ID, TAG_VALUE
    FROM candidate_tags
    -- Keep only the highest-priority tag per entity (direct wins over schema, schema wins over database).
    QUALIFY ROW_NUMBER() OVER (PARTITION BY ENTITY_ID ORDER BY TAG_PRIORITY) = 1
)

SELECT
    rc.ENTITY_TYPE,
    rc.NAME,
    rc.SERVICE_TYPE,
    ROUND(SUM(rc.CREDITS), 2) AS TOTAL_CREDITS,
    ROUND(SUM(rc.CREDITS_COMPUTE), 2) AS COMPUTE_CREDITS,
    ROUND(SUM(rc.CREDITS_CLOUD), 2) AS CLOUD_SERVICES_CREDITS
FROM resource_credits rc
JOIN resolved_tags rt
    ON rc.ENTITY_ID = rt.ENTITY_ID
WHERE rt.TAG_VALUE = '<TAG_VALUE>'
GROUP BY rc.ENTITY_TYPE, rc.NAME, rc.SERVICE_TYPE
ORDER BY TOTAL_CREDITS DESC;
```

---

### Resource-Level Cost for All Values of a Tag

**Triggered by:** "Show me cost for all values of this tag", "Break down all cost centers by resource", "Full tag breakdown by resource"

**Parameters:**
- `<TAG_ID>`: The TAG_ID of the selected tag
- `<START_TIME>`: Beginning of time window
- `<END_TIME>`: End of time window

To show all tag values (not filtered to one), use the same query above but remove the `WHERE rt.TAG_VALUE = '<TAG_VALUE>'` clause and add `rt.TAG_VALUE` to the SELECT and GROUP BY:

```sql
WITH resource_credits AS (
    SELECT
        mh.ENTITY_TYPE,
        mh.ENTITY_ID,
        mh.NAME,
        mh.SERVICE_TYPE,
        mh.DATABASE_ID,
        mh.SCHEMA_ID,
        SUM(mh.CREDITS_USED) AS CREDITS,
        SUM(mh.CREDITS_USED_COMPUTE) AS CREDITS_COMPUTE,
        SUM(mh.CREDITS_USED_CLOUD_SERVICES) AS CREDITS_CLOUD
    FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY mh
    WHERE mh.START_TIME >= <START_TIME>
        AND mh.START_TIME < <END_TIME>
        -- Exclude rows with NULL ENTITY_TYPE (legacy/unclassified service types) since they are not taggable.
        AND mh.ENTITY_TYPE IS NOT NULL
    GROUP BY mh.ENTITY_TYPE, mh.ENTITY_ID, mh.NAME, mh.SERVICE_TYPE, mh.DATABASE_ID, mh.SCHEMA_ID
),

direct_tags AS (
    SELECT tr.DOMAIN, tr.OBJECT_ID, tr.TAG_VALUE
    FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES tr
    WHERE tr.TAG_ID = <TAG_ID>
        AND (
            UPPER(tr.DOMAIN) IN (SELECT DISTINCT UPPER(ENTITY_TYPE) FROM resource_credits)
            -- Include DATABASE and SCHEMA domains for tag inheritance resolution.
            OR UPPER(tr.DOMAIN) IN ('DATABASE', 'SCHEMA')
        )
),

-- Tag inheritance resolution: direct tag (priority 1) > schema tag (priority 2) > database tag (priority 3).
candidate_tags AS (
    SELECT rc.ENTITY_ID, 1 AS TAG_PRIORITY, dt.TAG_VALUE
    FROM resource_credits rc
    JOIN direct_tags dt
        ON rc.ENTITY_ID = dt.OBJECT_ID
        AND UPPER(rc.ENTITY_TYPE) = UPPER(dt.DOMAIN)

    UNION ALL

    SELECT rc.ENTITY_ID, 2 AS TAG_PRIORITY, dt.TAG_VALUE
    FROM resource_credits rc
    JOIN direct_tags dt
        ON rc.SCHEMA_ID = dt.OBJECT_ID
        AND UPPER(dt.DOMAIN) = 'SCHEMA'

    UNION ALL

    SELECT rc.ENTITY_ID, 3 AS TAG_PRIORITY, dt.TAG_VALUE
    FROM resource_credits rc
    JOIN direct_tags dt
        ON rc.DATABASE_ID = dt.OBJECT_ID
        AND UPPER(dt.DOMAIN) = 'DATABASE'
),

resolved_tags AS (
    SELECT ENTITY_ID, TAG_VALUE
    FROM candidate_tags
    -- Keep only the highest-priority tag per entity (direct wins over schema, schema wins over database).
    QUALIFY ROW_NUMBER() OVER (PARTITION BY ENTITY_ID ORDER BY TAG_PRIORITY) = 1
)

SELECT
    rt.TAG_VALUE,
    rc.ENTITY_TYPE,
    rc.NAME,
    rc.SERVICE_TYPE,
    ROUND(SUM(rc.CREDITS), 2) AS TOTAL_CREDITS,
    ROUND(SUM(rc.CREDITS_COMPUTE), 2) AS COMPUTE_CREDITS,
    ROUND(SUM(rc.CREDITS_CLOUD), 2) AS CLOUD_SERVICES_CREDITS
FROM resource_credits rc
JOIN resolved_tags rt
    ON rc.ENTITY_ID = rt.ENTITY_ID
GROUP BY rt.TAG_VALUE, rc.ENTITY_TYPE, rc.NAME, rc.SERVICE_TYPE
ORDER BY rt.TAG_VALUE, TOTAL_CREDITS DESC;
```

---

### Notes

- **Filtered by TAG_ID early:** Both variants filter `TAG_REFERENCES` to a single `TAG_ID` in the `direct_tags` CTE, reducing intermediate result size.
- **Inheritance:** Same direct > schema > database precedence as the discovery query.
- **Single TAG_ID partition:** Since we filter to one TAG_ID, the `QUALIFY` only needs to partition by `ENTITY_ID` (not `ENTITY_ID, TAG_ID`).
- **TAG_VALUE filter in final SELECT:** Applied after inheritance resolution so that inherited values are correctly included.
- **Performance:** Typically completes in a few seconds for a 1-month window.
