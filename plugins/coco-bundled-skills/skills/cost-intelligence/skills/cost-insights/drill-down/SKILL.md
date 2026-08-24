# Cost Insights Drill-Down

Show specific objects (tables, warehouses, materialized views) that have a particular cost optimization insight, ranked by credit impact.

> **Prerequisites:** The parent router (`../SKILL.md`) has verified `APP_USAGE_VIEWER` access.

---

## Step 1: Resolve Insight Type ID

Use the keyword-to-type-ID mapping table in `../../../references/cost-insights/insight-types.md` to map the user's request to the correct insight type ID.

If the user's request doesn't clearly match one type, **ask them** which type they mean by presenting the options relevant to their domain (Table vs Warehouse).

If the user came here from the overview skill and picked a specific insight type, use that type ID directly.

---

## Step 2: Fetch Object-Level Insights

Call the drill-down procedure with the resolved type ID. Default to `topk = 10` unless the user requests a different count.

```sql
CALL SNOWFLAKE.LOCAL.COST_INSIGHTS!GET_TOP_TABLE_WAREHOUSE_INSIGHTS_BY_INSIGHT_TYPE_PROCEDURE(<topk>, '<INSIGHT_TYPE_ID>');
```

Examples:
```sql
-- Top 10 warehouses with large query gaps
CALL SNOWFLAKE.LOCAL.COST_INSIGHTS!GET_TOP_TABLE_WAREHOUSE_INSIGHTS_BY_INSIGHT_TYPE_PROCEDURE(10, 'WAREHOUSE_LARGE_QUERY_GAPS');

-- All tables never queried (no limit)
CALL SNOWFLAKE.LOCAL.COST_INSIGHTS!GET_TOP_TABLE_WAREHOUSE_INSIGHTS_BY_INSIGHT_TYPE_PROCEDURE(NULL, 'LARGE_TABLE_NEVER_QUERIED');
```

### Return Columns

| Column | Description |
|--------|-------------|
| `INSIGHT_TIMESTAMP` | When the insight was generated |
| `INSIGHT_ID` | Unique identifier for this insight instance |
| `TARGET_DOMAIN` | "Warehouse", "Table", or "Materialized View" |
| `TARGET_OBJECT_NAME` | Fully qualified object name (db.schema.object) |
| `CONTENT` | VARIANT with insight-specific details |
| `IMPACT` | Estimated credit savings for this object |
| `IMPACT_UNIT` | Unit (credits) |
| `JOBS_USING_OBJECT` | Number of jobs that reference this object |
| `PROPORTION_OF_TOTAL_FEATURE_SPEND` | Fraction of total feature spend (0.0–1.0) |
| `OBJECT_LOCATION` | Database.schema path |
| `OBJECT_NAME` | Short object name (last segment) |

---

## Step 3: Present Results

If the result set is **empty**, inform the user:
> "No objects found for this insight type. This means the system hasn't detected this pattern in your account recently."

**Do NOT** fall back to ad-hoc queries against `ACCOUNT_USAGE` views when the procedure returns no data. The procedure is the authoritative source for cost insights.

Otherwise, present a ranked table. Use the `IMPACT_UNIT` column value (e.g., "credits" or "GB") for labels — do not hardcode "credits":

```
Cost Insights: <INSIGHT_TYPE_DESCRIPTION>
============================================
Objects found: <count>
Total potential savings: <sum of IMPACT> <IMPACT_UNIT>

| # | Object | Location | Impact (<IMPACT_UNIT>) | Jobs Using | % of Feature Spend |
|---|--------|----------|------------------|------------|-------------------|
| 1 | <OBJECT_NAME> | <OBJECT_LOCATION> | <IMPACT> | <JOBS_USING_OBJECT> | <PROPORTION * 100>% |
| ... | ... | ... | ... | ... | ... |
```

---

## Step 4: Contextual Recommendations

Use the "Recommendations by Insight Type" table in `../../../references/cost-insights/insight-types.md` to provide actionable guidance based on the insight type.

---

## Step 5: Offer Next Steps

After presenting results:
> "Would you like to see a different insight type, go back to the overview, or investigate a specific object further?"

If the user wants a different type, return to Step 1. If they want the overview, load `../overview/SKILL.md`.
