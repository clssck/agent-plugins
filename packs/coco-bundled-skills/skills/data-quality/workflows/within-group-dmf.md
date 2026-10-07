---
parent_skill: data-quality
---

# Workflow: Within Group DMF (Grouped Monitoring)

Compute per-group quality metrics via the `WITHIN GROUP` clause on DMF associations. Instead of a single aggregate value for the entire table, get separate metric results for each distinct value of a grouping column (e.g., null count per region, duplicates per department).

**Feature parameter:** `FEATURE_DATA_QUALITY_WITHIN_GROUP` (must be enabled on the account).

## Trigger Phrases

**Explicit:** "within group", "WITHIN GROUP", "group by DMF", "GROUP LIMIT", "per-group metrics", "grouped monitoring"

**Implicit — ALWAYS route here when the user says any of:**
- "broken down by <column>", "separately for each <column>"
- "per region", "per category", "per department", "per segment"
- "for each <X> separately", "which <groups> have the worst"
- "null count per region", "duplicates by department"
- "quality metrics broken down by", "track <metric> for each <group>"
- "monitor by region", "monitor by category"
- "quality by segment", "per-category data quality"

## When to Load
- User wants per-group quality metrics (not whole-table aggregate)
- User mentions WITHIN GROUP, GROUP BY, or per-segment monitoring
- User wants DMF results broken down by a categorical column
- **User describes wanting a metric computed "separately for each" value of a column — even if they do NOT mention WITHIN GROUP by name**

## CRITICAL: Do NOT Use Alternative Approaches

When this workflow applies, you MUST use `ALTER TABLE ... ADD DATA METRIC FUNCTION ... WITHIN GROUP (...)`. Do NOT:
- Create dynamic tables with manual `GROUP BY` SQL
- Write manual `SELECT ... GROUP BY` queries
- Create separate DMF associations per group value (one DMF per region, etc.)
- Create custom DMFs that embed GROUP BY logic
- Suggest any non-DMF approach for continuous per-group monitoring

The WITHIN GROUP clause is the native Snowflake feature for this exact use case. It is always the correct answer when the user wants a DMF metric computed per-group.

---

## Execution Steps

### Step 1: Establish Scope

Extract from the user's request:
- **Target table**: `DATABASE.SCHEMA.TABLE`
- **Metric column**: the column to measure (e.g., `customer_email` for NULL_COUNT)
- **Grouping column(s)**: the column(s) to group by (e.g., `region`, `category`)

Grouping columns are **mandatory** — the user must specify them. If not provided, ask:
> Which column(s) do you want to group by? For example, if you want null counts broken down by region, the grouping column is `region`.

### Step 2: Validate DMF Compatibility

Check the chosen DMF against restrictions. If the user hasn't specified a DMF, recommend from the compatible list.

**Compatible system DMFs:**

| Use Case | Recommended DMF |
|---|---|
| Null monitoring per group | `SNOWFLAKE.CORE.NULL_COUNT` |
| Duplicate monitoring per group | `SNOWFLAKE.CORE.DUPLICATE_COUNT` |
| Value validation per group | `SNOWFLAKE.CORE.ACCEPTED_VALUES` |
| Volume monitoring per group | `SNOWFLAKE.CORE.ROW_COUNT` |

**NOT compatible — reject and explain:**

| Request | Why It Fails | Suggested Alternative |
|---|---|---|
| FRESHNESS with WITHIN GROUP | Not meaningful per-group (freshness is table-level) | Use ROW_COUNT per group, or FRESHNESS without grouping |
| ANOMALY_DETECTION = TRUE | Incompatible with grouped evaluation | Use WITHIN GROUP without anomaly detection |
| REFERENTIAL_INTEGRITY_COUNT | Multi-table join based, incompatible with GROUP BY | Use without WITHIN GROUP, or custom validation |
| Schema-level (ALTER SCHEMA) | Schema-level associations cannot use WITHIN GROUP | Use per-table ALTER TABLE with WITHIN GROUP |

**Custom DMF body compatibility:**
- **Supported:** single-table queries, subqueries, FLATTEN
- **NOT supported:** CTEs (WITH clauses), JOINs, UNION/UNION ALL, DISTINCT, window functions

If the body contains unsupported patterns, warn the user that the ALTER TABLE will fail.

**Immutable configuration:** Grouping columns and GROUP LIMIT cannot be modified after creation. To change them, the user must DROP and recreate the association.

---

### Step 3: Determine GROUP LIMIT (Optional)

Ask if the user wants to cap the number of groups evaluated per measurement:
> Do you want to set a GROUP LIMIT? This caps how many distinct group values are evaluated (range 1–1000, default 1000). Recommended when the grouping column has high cardinality.

- If cardinality is low (< 100 distinct values): GROUP LIMIT is unnecessary
- If cardinality is high: recommend setting GROUP LIMIT — exceeding the limit causes evaluation failure
- GROUP LIMIT is immutable after creation; must drop and recreate to change it

### Step 4: Determine EXPECTATION (Optional)

Ask if the user wants per-group pass/fail thresholds:
> Do you want to set an expectation (per-group threshold)? For example, "each region must have zero nulls" → `EXPECTATION zero_nulls (value = 0)`.

Note: `SYSTEM$EVALUATE_DATA_QUALITY_EXPECTATIONS` will return one row per (expectation, group_value) combination.

---

### Step 5: Generate DDL

Read `templates/within-group-dmf.sql` and substitute placeholders to build the ALTER TABLE statement.

### Step 6: Present DDL for Approval

**MANDATORY STOPPING POINT** — Show the exact DDL and explain:
- Which DMF, on which column, grouped by which column(s)
- GROUP LIMIT if set
- EXPECTATION if set
- That results will contain per-group values (GROUP_BY_INFO column)

Await explicit user approval before executing.

### Step 7: Execute

Run the ALTER TABLE statement. On success, confirm and show how to query results:

```sql
-- Verify the association was created (PROPERTIES shows within_group info)
SELECT METRIC_NAME, ARGUMENT_NAMES,
       PROPERTIES:within_group AS within_group_cols,
       PROPERTIES:group_limit  AS group_limit
FROM TABLE(INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES(
    REF_ENTITY_NAME => '<database>.<schema>.<table_name>',
    REF_ENTITY_DOMAIN => 'table'
))
WHERE PROPERTIES:within_group IS NOT NULL;
```

### Step 8: STOP

After successful execution, offer next steps but **do NOT continue unprompted**:
- "View per-group results after the next measurement cycle"
- "Set or tune per-group expectations" → load `workflows/expectations-management.md`
- "Add another grouped DMF on a different column"

**STOP HERE.** Do not proceed to additional operations unless the user explicitly asks.

---

## Error Handling

| Error | Cause | Resolution |
|---|---|---|
| `WITHIN GROUP is not supported for this metric` | FRESHNESS or incompatible DMF | Use a compatible DMF (NULL_COUNT, DUPLICATE_COUNT, ACCEPTED_VALUES, ROW_COUNT) |
| `ANOMALY_DETECTION cannot be used with WITHIN GROUP` | Combined grouped + anomaly | Remove ANOMALY_DETECTION or remove WITHIN GROUP |
| `Schema-level associations do not support WITHIN GROUP` | ALTER SCHEMA with WITHIN GROUP | Use per-table ALTER TABLE instead |
| Error 510189: DMF body incompatible | Custom DMF uses CTE/JOIN/UNION/DISTINCT/window | Rewrite the custom DMF body to a simple single-table aggregate |
| `Invalid column` in WITHIN GROUP | Column doesn't exist or wrong type | Verify column name and that it's a scalar column in the target table |

---

## Notes

- Results appear after the next scheduled measurement cycle (governed by DATA_METRIC_SCHEDULE)
- NULL values in grouping columns form their own distinct group
- Per-group EXPECTATION evaluation produces one EXPECTATION_VIOLATION_STATUS record per group
- SYSTEM$DATA_METRIC_SCAN supports `WITHIN_GROUP_VALUES` parameter to filter results by specific group value
