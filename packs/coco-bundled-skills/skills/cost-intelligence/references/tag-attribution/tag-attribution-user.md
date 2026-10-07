# Tag Attribution: User-Level Query

Shows proportional (fractional) compute cost attribution for users tagged with a specific tag + value. Used when multiple teams share the same warehouses and you need to attribute costs based on who ran the queries.

**Semantic keywords:** user attribution, shared warehouse cost, fractional cost, query attribution, user tag cost, shared resource cost

---

### User-Level Cost for a Specific Tag + Value

**Triggered by:** "How much did users in this cost center spend on shared warehouses?", "Show me fractional attribution for tagged users", "Break down shared resource costs by user tag"

**Parameters:**
- `<TAG_ID>`: The TAG_ID of the selected tag
- `<TAG_VALUE>`: The specific tag value to filter on
- `<START_TIME>`: Beginning of time window
- `<END_TIME>`: End of time window

```sql
SELECT
    qah.USER_NAME,
    qah.WAREHOUSE_NAME,
    ROUND(SUM(qah.CREDITS_ATTRIBUTED_COMPUTE), 4) AS ATTRIBUTED_COMPUTE_CREDITS,
    COUNT(*) AS QUERY_COUNT
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY qah
JOIN SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES tr
    ON tr.DOMAIN = 'USER'
    AND tr.OBJECT_NAME = qah.USER_NAME
WHERE tr.TAG_ID = <TAG_ID>
    AND tr.TAG_VALUE = '<TAG_VALUE>'
    AND qah.START_TIME >= <START_TIME>
    AND qah.START_TIME < <END_TIME>
GROUP BY qah.USER_NAME, qah.WAREHOUSE_NAME
ORDER BY ATTRIBUTED_COMPUTE_CREDITS DESC;
```

---

### User-Level Cost for All Values of a Tag

**Triggered by:** "Show me cost for all tag values by user", "Break down all cost centers by user", "Full user attribution across all tag values"

**Parameters:**
- `<TAG_ID>`: The TAG_ID of the selected tag
- `<START_TIME>`: Beginning of time window
- `<END_TIME>`: End of time window

```sql
SELECT
    tr.TAG_VALUE,
    qah.USER_NAME,
    ROUND(SUM(qah.CREDITS_ATTRIBUTED_COMPUTE), 4) AS ATTRIBUTED_COMPUTE_CREDITS,
    COUNT(*) AS QUERY_COUNT,
    COUNT(DISTINCT qah.WAREHOUSE_NAME) AS WAREHOUSES_USED
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY qah
JOIN SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES tr
    ON tr.DOMAIN = 'USER'
    AND tr.OBJECT_NAME = qah.USER_NAME
WHERE tr.TAG_ID = <TAG_ID>
    AND qah.START_TIME >= <START_TIME>
    AND qah.START_TIME < <END_TIME>
GROUP BY tr.TAG_VALUE, qah.USER_NAME
ORDER BY tr.TAG_VALUE, ATTRIBUTED_COMPUTE_CREDITS DESC;
```

---

### Caveats: QUERY_ATTRIBUTION_HISTORY Limitations

Always present these caveats to the user when showing user-level attribution results:

| Limitation | Impact |
|-----------|--------|
| **Excludes warehouse idle time** | Only query execution credits are counted; time between queries is not attributed |
| **Excludes short queries (≤100ms)** | Very fast queries are too short for per-query attribution |
| **Up to 8-hour data latency** | Recent queries may not yet appear |
| **Compute-only** | Does NOT include serverless, storage, AI services, data transfer, or cloud services credits |
| **No adaptive warehouse jobs** | Jobs executed by adaptive warehouses are excluded |

**What this means:** User-level attribution shows proportional compute usage only. It is useful for understanding relative consumption patterns on shared warehouses, but does NOT represent total cost. For total cost of dedicated resources, use resource-level attribution instead.

---

### Notes

- **No inheritance needed:** Users are flat objects — they don't exist in a database/schema hierarchy. Tags on users are always direct.
- **Join key:** `TAG_REFERENCES.OBJECT_NAME = QUERY_ATTRIBUTION_HISTORY.USER_NAME` (name-based join for USER domain, since USER objects don't have ENTITY_ID in QUERY_ATTRIBUTION_HISTORY).
- **Fractional attribution:** `CREDITS_ATTRIBUTED_COMPUTE` already contains the proportional share — if 3 queries ran concurrently, each gets a weighted fraction of the warehouse's credits for that interval.
- **Non-additive with resource-level:** These credits should NOT be summed with resource-level attribution results. They represent different perspectives on cost.
