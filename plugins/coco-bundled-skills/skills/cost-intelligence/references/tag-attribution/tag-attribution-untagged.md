# Tag Attribution: Untagged Resources Query

Shows the top credit-consuming resources that have no tag applied at any level (direct, schema, or database). Useful for identifying what to tag next to improve attribution coverage.

**Semantic keywords:** untagged resources, missing tags, no attribution, tag coverage gap, what to tag next

---

### Top Untagged Resources by Credits

**Triggered by:** "Which resources have no tags?", "What's consuming credits without attribution?", "Show me untagged spend", "What should I tag next?"

**Parameters:**
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
        SUM(mh.CREDITS_USED) AS CREDITS
    FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY mh
    WHERE mh.START_TIME >= <START_TIME>
        AND mh.START_TIME < <END_TIME>
        -- Exclude rows with NULL ENTITY_TYPE (legacy/unclassified service types) since they are not taggable.
        AND mh.ENTITY_TYPE IS NOT NULL
    GROUP BY mh.ENTITY_TYPE, mh.ENTITY_ID, mh.NAME, mh.SERVICE_TYPE, mh.DATABASE_ID, mh.SCHEMA_ID
),

direct_tags AS (
    SELECT
        tr.DOMAIN,
        tr.OBJECT_ID,
        tr.TAG_ID
    FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES tr
    WHERE (
            UPPER(tr.DOMAIN) IN (SELECT DISTINCT UPPER(ENTITY_TYPE) FROM resource_credits)
            -- Include DATABASE and SCHEMA domains for tag inheritance resolution.
            OR UPPER(tr.DOMAIN) IN ('DATABASE', 'SCHEMA')
        )
),

-- Tag inheritance resolution: a resource is only "untagged" if it has no tag at any level
-- (direct, schema, or database).
tagged_entities AS (
    -- Entities with a direct tag
    SELECT DISTINCT rc.ENTITY_ID
    FROM resource_credits rc
    JOIN direct_tags dt
        ON rc.ENTITY_ID = dt.OBJECT_ID
        AND UPPER(rc.ENTITY_TYPE) = UPPER(dt.DOMAIN)

    UNION

    -- Entities inheriting a tag from their schema
    SELECT DISTINCT rc.ENTITY_ID
    FROM resource_credits rc
    JOIN direct_tags dt
        ON rc.SCHEMA_ID = dt.OBJECT_ID
        AND UPPER(dt.DOMAIN) = 'SCHEMA'

    UNION

    -- Entities inheriting a tag from their database
    SELECT DISTINCT rc.ENTITY_ID
    FROM resource_credits rc
    JOIN direct_tags dt
        ON rc.DATABASE_ID = dt.OBJECT_ID
        AND UPPER(dt.DOMAIN) = 'DATABASE'
)

SELECT
    rc.ENTITY_TYPE,
    rc.NAME,
    rc.SERVICE_TYPE,
    ROUND(SUM(rc.CREDITS), 2) AS CREDITS_USED
FROM resource_credits rc
LEFT JOIN tagged_entities te
    ON rc.ENTITY_ID = te.ENTITY_ID
WHERE TRUE
    -- Filter for METERING_HISTORY entries that are not tagged at any level (direct, schema, or database)
    AND te.ENTITY_ID IS NULL
    -- Exclude non-taggable entities (CORTEX CODE, SNOWWORK) which have NULL ENTITY_ID
    -- and can never be tagged. Only show resources the user can actually act on.
    AND rc.ENTITY_ID IS NOT NULL
GROUP BY rc.ENTITY_TYPE, rc.NAME, rc.SERVICE_TYPE
ORDER BY CREDITS_USED DESC
LIMIT 25;
```

---

### Notes

- **Untagged means no tag at any level:** A resource is untagged only if it has no direct tag AND no inherited tag from its parent schema or database.
- **Actionable output:** The results show exactly which resources to tag next for maximum attribution coverage improvement. Prioritize by credits — tagging the top few resources will close the biggest coverage gaps.
- **ENTITY_ID IS NOT NULL filter:** Excludes non-taggable entity types (CORTEX CODE, SNOWWORK) which have NULL ENTITY_ID in METERING_HISTORY and cannot have tags applied.
