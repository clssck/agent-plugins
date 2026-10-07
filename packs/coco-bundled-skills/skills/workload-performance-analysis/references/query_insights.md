# Query Insights Reference

How to fetch and interpret Snowflake Query Insights for SQL-level optimization.

## Fetching Query Insights

```sql
SELECT 
    qi.INSIGHT_TYPE_ID, qi.INSIGHT_TOPIC, qi.MESSAGE, qi.SUGGESTIONS,
    qh.QUERY_TEXT, qh.USER_NAME, qh.WAREHOUSE_NAME,
    qh.DATABASE_NAME, qh.SCHEMA_NAME,
    qh.START_TIME, qh.TOTAL_ELAPSED_TIME
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_INSIGHTS qi
JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY qh ON qi.QUERY_ID = qh.QUERY_ID
WHERE qi.QUERY_ID = '<QUERY_ID>'
  AND qi.START_TIME >= DATEADD('day', -14, CURRENT_DATE())
  AND qh.START_TIME >= DATEADD('day', -14, CURRENT_DATE())
```

**Requires:** `GOVERNANCE_VIEWER` database role on SNOWFLAKE database.

## Branching Logic

| Condition | Action |
|-----------|--------|
| Insights exist with SQL-actionable types | Primary path: SQL optimization using insight-specific fix strategies |
| Insights exist but ONLY resource types (REMOTE_SPILLAGE, QUEUED_OVERLOAD) | Infrastructure recommendations only (DO NOT modify SQL) |
| No insights, query < 2 hours old | Insights may not be processed yet. Offer general suggestions from operator stats. |
| No insights, query > 14 days old | `GET_QUERY_OPERATOR_STATS` expired. Fall back to infrastructure recommendations. |
| No insights, 2h-14d old | Query likely efficient (no issues detected). Fall back to infrastructure recommendations. Ask user before proceeding. |

**[IMPORTANT]** DO NOT mix Query Insight tags and General Suggestion tags. Use one mode or the other.

## Insight Types Quick Reference

| Insight Type | Category | Action |
|--------------|----------|--------|
| `NO_FILTER_ON_TOP_OF_TABLE_SCAN` | Table Scan | Add WHERE clause |
| `INAPPLICABLE_FILTER_ON_TABLE_SCAN` | Table Scan | Add effective filter |
| `UNSELECTIVE_FILTER` | Table Scan | Add more selective filter |
| `LIKE_WITH_LEADING_WILDCARD` | Table Scan | Remove leading wildcard or enable search optimization |
| `FILTER_WITH_CLUSTERING_KEY` | Table Scan | Positive — no change needed |
| `SEARCH_OPTIMIZATION_USED` | Table Scan | Positive — no change needed |
| `SNOWFLAKE_OPTIMA` | Table Scan | Positive — no change needed |
| `INEFFICIENT_AGGREGATE` | Aggregation | Remove redundant GROUP BY / DISTINCT |
| `EXPLODING_JOIN` | Join | Add filter, refine granularity, or pre-aggregate |
| `NESTED_EXPLODING_JOIN` | Join | Fix innermost join first, then outer |
| `INEFFICIENT_JOIN_CONDITION` | Join | Simplify condition or pre-compute keys |
| `JOIN_WITH_NO_JOIN_CONDITION` | Join | Add explicit join condition |
| `UNNECESSARY_UNION_DISTINCT` | Union | Change UNION to UNION ALL |
| `REMOTE_SPILLAGE` | Resource | DO NOT modify SQL — use larger warehouse |
| `QUEUED_OVERLOAD` | Resource | DO NOT modify SQL — use different warehouse or schedule off-peak |

## Mapping Insights to SQL Location

Use `GET_QUERY_OPERATOR_STATS` to tie each insight to a specific operator in the query plan:

```sql
SELECT 
    OPERATOR_ID, OPERATOR_TYPE, OPERATOR_ATTRIBUTES, OPERATOR_STATISTICS
FROM TABLE(GET_QUERY_OPERATOR_STATS('<QUERY_ID>'))
ORDER BY OPERATOR_ID
```

| Insight Category | MESSAGE Field | Maps To |
|------------------|---------------|---------|
| `*TABLE_SCAN` | `table` | TableScan operator |
| `*_JOIN*` | `join_id` | Join operator |
| `INEFFICIENT_AGGREGATE` | `logical_node_id` | Aggregate operator |
| `REMOTE_SPILLAGE` | `logical_node_id` | Operator where spillage occurred |

## Co-Located Spillage Detection

When `REMOTE_SPILLAGE` insight exists, check if another insight shares the same `logical_node_id`:

- **Match found** (e.g., `EXPLODING_JOIN` on same node): The SQL issue is the **root cause** of spillage. Fix the SQL issue first — spillage may resolve without upsizing.
- **No match**: Spillage is a pure resource problem. Recommend larger warehouse.

## Positive Insights

These indicate the query is already optimized. Present as informational — no changes needed:
- `FILTER_WITH_CLUSTERING_KEY` — Effective partition pruning via clustering key
- `SEARCH_OPTIMIZATION_USED` — Benefiting from Search Optimization
- `SNOWFLAKE_OPTIMA` — Benefiting from Snowflake Optima
- `SEARCH_OPTIMIZATION_AND_SNOWFLAKE_OPTIMA` — Both active
