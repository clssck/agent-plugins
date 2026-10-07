# Cost Insights Overview

Show a summary of all active cost optimization insights for the account, including insight counts, total credit impact, and actionable recommendations.

> **Prerequisites:** The parent router (`../SKILL.md`) has verified `APP_USAGE_VIEWER` access.

---

## Step 1: Fetch Insights Overview

Call the overview procedure. Use `topk = NULL` to return all insight types. Use `show_all = TRUE` to include insight types that currently have zero findings (so the user can see the full scope of what's monitored).

```sql
CALL SNOWFLAKE.LOCAL.COST_INSIGHTS!GET_TOP_INSIGHTS_OVERVIEW_PROCEDURE(NULL, TRUE);
```

If the user requests only the top N insight types (e.g., "show me the top 3"):

```sql
CALL SNOWFLAKE.LOCAL.COST_INSIGHTS!GET_TOP_INSIGHTS_OVERVIEW_PROCEDURE(<N>, TRUE);
```

### Return Columns

| Column | Description |
|--------|-------------|
| `INSIGHT_TYPE_ID` | Internal identifier (e.g. `WAREHOUSE_LARGE_QUERY_GAPS`) |
| `INSIGHT_TYPE_DESCRIPTION` | Human-readable name |
| `INSIGHT_COUNT` | Number of objects with this insight |
| `CATEGORY` | Always "Waste reduction" for cost insights |
| `DOMAIN` | "Warehouse", "Table", or "Materialized View" |
| `IMPACT` | Total estimated credit savings |
| `IMPACT_UNIT` | Unit for impact (credits) |
| `MESSAGE` | Explanation of what the insight means |
| `RECOMMENDATION` | Suggested action to reduce waste |
| `IMPACT_MESSAGE` | Formatted impact summary |

---

## Step 2: Present the Summary

Present all results in a table, sorted by impact descending (the procedure already returns them in this order).

```
Cost Insights Overview
======================
Total insight types monitored: <count of all rows>
Types with active findings:    <count where INSIGHT_COUNT > 0>
Total potential savings:        <sum of IMPACT> credits

| Insight | Domain | Objects | Impact (credits) | Recommendation |
|---------|--------|---------|------------------|----------------|
| <INSIGHT_TYPE_DESCRIPTION> | <DOMAIN> | <INSIGHT_COUNT> | <IMPACT> | <RECOMMENDATION> |
| ... | ... | ... | ... | ... |
```

For rows where `INSIGHT_COUNT = 0`, show them at the bottom with a note: "No findings currently — this area is actively monitored."

**Highlight** the insight type with the highest impact as the biggest savings opportunity.

---

## Step 3: Offer Drill-Down

After presenting the overview, offer to drill into specific insight types:

> "I can show you the specific objects (tables or warehouses) for any of these insight types. Which one would you like to investigate?"

If the user picks one, load `../drill-down/SKILL.md` with the selected insight type.

---

## Reference Files

| Topic | File |
|-------|------|
| Insight type IDs and recommendations | `../../../references/cost-insights/insight-types.md` |
