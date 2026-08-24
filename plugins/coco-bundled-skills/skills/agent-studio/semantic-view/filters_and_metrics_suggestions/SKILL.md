---
name: semantic-view-filters-and-metrics-suggestions
description: "Suggest filters, metrics, and facts for a semantic view by analyzing query history. Use this skill whenever the user wants to enrich a semantic view with metrics/measures, named filters, or computed facts. This includes requests like 'suggest metrics', 'suggest filters', 'add metrics to my view', 'what metrics should I add', 'enrich my semantic view', 'recommend filters', 'suggest facts', 'what measures should I define', or any mention of auto-generating, recommending, or populating metrics and filters."
parent_skill: semantic-view
---

# Filters & Metrics Suggestions

A semantic view starts with raw columns, but users quickly need aggregations ("total revenue"), reusable filters ("only VIP customers"), and derived facts ("is SLA compliant?"). Defining these by hand means guessing what matters. The `filters_and_metrics_suggestions` tool (via `SYSTEM$CORTEX_ANALYST_SVA_TOOL`) solves this by mining actual Snowflake query history to surface the metrics, filters, and facts people already use in practice — so the view reflects real needs, not guesswork.

## Prerequisites

- A semantic view (or stage-based semantic model file) already created
- A warehouse available for the function to use

## Workflow

### Phase 1: Gather Context

Collect from user:

| Field | Required | Notes |
|-------|----------|-------|
| **Semantic view** | Yes | `DATABASE.SCHEMA.VIEW_NAME` or stage path `@DATABASE.SCHEMA.STAGE/model.yaml` |
| **Warehouse** | No | Check with `SELECT CURRENT_WAREHOUSE()` if not provided |

### Phase 2: Execute the Function

Use `snowflake_sql_execute` with `SYSTEM$CORTEX_ANALYST_SVA_TOOL`. The call wraps the tool name and parameters in a `$$`-quoted JSON.

> **IMPORTANT — Always use `PARSE_JSON` + `LATERAL FLATTEN`.** The raw function returns a large JSON string that gets truncated when displayed. Always use the full query pattern below to get structured, per-suggestion rows. Do NOT run the bare `SELECT SYSTEM$CORTEX_ANALYST_SVA_TOOL(...)` — the result will be unreadable. Also do NOT use `CREATE TABLE ... AS SELECT SYSTEM$CORTEX_ANALYST_SVA_TOOL(...)` — it fails because the function has side effects.

```sql
WITH raw AS (
    SELECT PARSE_JSON(PARSE_JSON(SYSTEM$CORTEX_ANALYST_SVA_TOOL($${
        "tool": "filters_and_metrics_suggestions",
        "parameters": {
            "semantic_view": "DATABASE.SCHEMA.VIEW_NAME",
            "warehouse": "WAREHOUSE_NAME"
        }
    }$$)):result) AS result
)
SELECT
    f.index + 1 AS suggestion_num,
    f.value AS suggestion
FROM raw, LATERAL FLATTEN(input => raw.result:suggestions) f
ORDER BY f.index;
```

For a stage-based model file, use `"semantic_model_file": "@DATABASE.SCHEMA.STAGE/model.yaml"` instead of `"semantic_view"`.

> **Note:** If the `LATERAL FLATTEN` returns 0 rows, the function returned no suggestions.

### Phase 3: Present Results

The query returns one row per suggestion. Each row's `suggestion` column is a JSON object — read its keys directly (field names may vary between API versions). Expected structure per suggestion:

```json
{
    "changes": [
        {
            "operation": "SEMANTIC_MODEL_CHANGE_OPERATION_APPEND",
            "path": "tables/name:ticket_sales/metrics",
            "value": {
                "metric": {
                    "name": "total_revenue",
                    "description": "Calculates total revenue by summing all prices.",
                    "expr": "SUM(price)"
                }
            }
        }
    ],
    "metadata": {
        "frequency": 38,
        "justification": "This metric is used in 38 verified queries.",
        "source": "verified queries"
    },
    "version": 2
}
```

**Suggestion types — identify by the key inside `value`:**

| Value key | Type | Path pattern | Fields |
|-----------|------|-------------|--------|
| `metric` | Metric/Measure | `tables/name:<table>/metrics` | `name`, `description`, `expr` |
| `named_filter` | Named Filter | `tables/name:<table>/filters` | `name`, `description`, `expr` |
| `fact` | Computed Fact | `tables/name:<table>/facts` | `name`, `data_type`, `description`, `expr` |
| `primary_key` | Primary Key | `tables.<table>.primary_key` | `columns` (array) |

**Key fields to surface:**
- `changes[].path` — encodes the type and target table (e.g. `tables/name:ticket_sales/metrics`)
- `changes[].value` — contains the suggested metric/filter/fact with `name`, `expr`, `description`
- `metadata.frequency` — how many queries/VQRs use this pattern (higher = more common)
- `metadata.source` — origin of the suggestion (e.g. `"verified queries"`, `"query history"`)

**Present results grouped by type:**

```
Filters & Metrics Suggestions for DATABASE.SCHEMA.VIEW_NAME (22 results)

── Metrics (10) ─────────────────────────────────
1. ⭐ [ticket_sales] unique_customers
   COUNT(DISTINCT customer_id)
   Calculates the count of distinct customer IDs...

2. ⭐ [ticket_sales] ticket_revenue
   SUM(price)
   Calculates total revenue from ticket sales...

3. [ticket_sales] total_tickets_sold
   COUNT(ticket_id)
   Total number of ticket records...

── Named Filters (7) ────────────────────────────
4. ⭐ [customers] region_europe
   region = 'Europe'
   Filters customers to the Europe region...

5. [customers] customer_chris_evans
   customer_name = 'Chris Evans'
   Filters to a specific customer...

── Facts (5) ────────────────────────────────────
6. ⭐ [support_tickets] is_fast_resolved (NUMBER(1,0))
   CASE WHEN resolution_time_days <= 2 THEN 1 ELSE 0 END
   Whether a ticket was resolved within 2 days...

⭐ = recommended (broadly useful)
```

If `warnings` is non-empty, display them to the user.

### Phase 4: Offer Next Steps

After presenting suggestions, ask:

> "Would you like to:
> 1. Add any of these to the semantic view (tell me which numbers)
> 2. Get more suggestions
> 3. See the full details of specific suggestions"

If the user wants to add suggestions, route to `edit/SKILL.md` to apply them via `sv-edit`. Each suggestion's `changes` array contains the exact `operation`/`path`/`value` triples needed for the edit — pass them directly.

## Error Handling

| Error | Fix |
|-------|-----|
| Semantic view not found | Verify `DATABASE.SCHEMA.VIEW_NAME` with `SHOW SEMANTIC VIEWS IN <database>.<schema>` |
| Permission denied | Check role: `SELECT CURRENT_ROLE()` |
| No suggestions / "No expressions extracted" | The model may lack sufficient query history — suggest adding more tables or running some queries first |
| Warehouse not specified | Provide `"warehouse"` or set one: `USE WAREHOUSE <name>` |

## Stopping Points

- ✋ Phase 1: If semantic view identity is unclear
- ✋ Phase 4: Before adding suggestions to the semantic view

## Success Criteria

- ✅ Semantic view identified
- ✅ Function executed successfully
- ✅ Suggestions parsed and presented clearly, grouped by type (metrics, filters, facts)
- ✅ Next steps offered to user
