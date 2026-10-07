# Column Lineage Workflow

## Purpose
Trace data lineage at the column level to understand how specific fields flow through your data pipeline.

## When to Use
- **Column Impact Analysis**: Before modifying a column's data type, renaming, or removing
- **Column Root Cause**: Debugging incorrect values in a specific column
- **Column Discovery**: Understanding where a column's data originates

> **Out of scope:** *"Has column X changed recently?"* is a **metadata** question, not lineage. Use `SNOWFLAKE.ACCOUNT_USAGE.COLUMNS.LAST_ALTERED` and `QUERY_HISTORY` directly — see the change-detection notes in `root-cause-analysis.md`.

## Templates

| Template | Use Case | Direction | Notes |
|----------|----------|-----------|-------|
| `column-lineage-get-lineage.sql` | **Primary** for column lineage (upstream or downstream) | Both | Uses `SNOWFLAKE.CORE.GET_LINEAGE(..., 'COLUMN', ...)`; no latency, no account admin |
| `column-lineage-full.sql` | Complete column path (both directions) | Both | Uses `SNOWFLAKE.CORE.GET_LINEAGE(..., 'COLUMN', ...)`; run UPSTREAM then DOWNSTREAM |
| `column-lineage-downstream.sql` | What uses this column? | Downstream | ACCESS_HISTORY-based fallback when GET_LINEAGE returns empty |
| `column-lineage-upstream.sql` | Where does this column come from? | Upstream | ACCESS_HISTORY-based fallback when GET_LINEAGE returns empty |
| `root-cause-column.sql` | Debug column issues | Upstream | — |

> Output columns from `SNOWFLAKE.CORE.GET_LINEAGE` are `SOURCE_OBJECT_*`, `SOURCE_COLUMN_NAME`, `TARGET_OBJECT_*`, `TARGET_COLUMN_NAME`, `DISTANCE`, `PROCESS` — see [`reference/snowflake-apis.md`](../reference/snowflake-apis.md) for the full canonical list and the `DOWNSTREAM_*`/`UPSTREAM_*` warning.

## Required Information
- **Database**: The database containing the table
- **Schema**: The schema containing the table
- **Table**: The table name
- **Column**: The specific column to trace

## Trigger Phrases

**Downstream (Impact):**
- "What uses the [column] column?"
- "What depends on [table].[column]?"
- "Impact analysis for [column]"
- "If I change [column], what breaks?"

**Upstream (Source):**
- "Where does [column] come from?"
- "What is the source of [table].[column]?"
- "Trace [column] upstream"
- "Column lineage for [column]"

**Full Path:**
- "Full lineage for [column]"
- "Complete path for [table].[column]"
- "End-to-end lineage for [column]"

## Example Interactions

> **Note:** The database/schema/table names below (e.g., `RAW_DB.SALES.ORDERS`) are illustrative examples. The actual output will reflect your specific Snowflake objects.

### Example 1: Column Impact Analysis
**User:** "What will break if I change the AMOUNT column in RAW_DB.SALES.ORDERS?"

**Agent Response:**
```
Column Impact Analysis: RAW_DB.SALES.ORDERS.AMOUNT

═══════════════════════════════════════════════════════════════
DOWNSTREAM DEPENDENCIES (distance 1–2)
═══════════════════════════════════════════════════════════════

Distance 1:
1. ANALYTICS_DB.FINANCE.REVENUE_SUMMARY.TOTAL_REVENUE  (Table)
2. ANALYTICS_DB.REPORTING.DAILY_SALES.NET_AMOUNT  (View)

Distance 2:
3. STAGING_DB.TRANSFORM.ORDERS_ENRICHED.AMOUNT  (Table)

Summary: 3 downstream columns affected across 2 levels
```

### Example 2: Column Source Tracing
**User:** "Where does ANALYTICS_DB.REPORTS.REVENUE.TOTAL_SALES come from?"

**Agent Response:**
```
Column Source Analysis: ANALYTICS_DB.REPORTS.REVENUE.TOTAL_SALES

═══════════════════════════════════════════════════════════════
UPSTREAM SOURCES (distance 1–3)
═══════════════════════════════════════════════════════════════

Distance 1:
  STAGING_DB.TRANSFORM.ORDERS_AGG.REVENUE_SUM → ANALYTICS_DB.REPORTS.REVENUE.TOTAL_SALES

Distance 2:
  RAW_DB.INGEST.ORDERS.AMOUNT → STAGING_DB.TRANSFORM.ORDERS_AGG.REVENUE_SUM

Distance 3:
  @RAW_DB.STAGES.S3_ORDERS → RAW_DB.INGEST.ORDERS.AMOUNT

Complete Path:
S3_ORDERS → ORDERS.AMOUNT → ORDERS_AGG.REVENUE_SUM → REVENUE.TOTAL_SALES

Summary: 3 upstream sources across 3 levels
```

### Example 3: Column Change Detection

*Out of scope — see "Out of scope" note at the top of this file. Use `SNOWFLAKE.ACCOUNT_USAGE.COLUMNS.LAST_ALTERED` + `QUERY_HISTORY` directly.*

## Output Format

### For Downstream Analysis (GET_LINEAGE)
- List affected downstream columns with distance levels
- Show source and target object/column pairs
- Summarize total impact

### For Upstream Analysis (GET_LINEAGE)
- Show source columns by distance level (depth)
- Indicate source tier (RAW, STAGING, EXTERNAL)
- Display complete lineage path

### When Using the ACCESS_HISTORY Fallback
When `GET_LINEAGE` returns empty and you fall back to `column-lineage-upstream.sql` / `column-lineage-downstream.sql`:
- List source/target objects with schema and object type (ACCESS_HISTORY does not return a `DISTANCE` column)
- Note that results may be incomplete — not all query patterns expose column-level detail
- State the lookback window used (e.g., "last 90 days") so users know the coverage period
- Summarize the number of edges found and flag if the result set is empty after fallback

### External rows

When the result includes rows where `SOURCE_OBJECT_DATABASE IS NULL` or `TARGET_OBJECT_DATABASE IS NULL` and the corresponding `*_NAMESPACE` is populated (only on accounts meeting one of the two external-lineage gates — see [`../reference/external-row-output.md`](../reference/external-row-output.md)), those represent columns inside external entities, correctly tagged `*_OBJECT_DOMAIN = 'EXTERNAL_COLUMN'` (distinct from the parent object's `'EXTERNAL'`). Identify them as `<DATASET_TYPE> <PARENT_NAME>.<COLUMN_NAME>` (e.g. `Power BI Report Q3 Revenue.total_sales`). Don't try to construct a `db.schema.table.column` form for them. ACCESS_HISTORY-based fallbacks do **not** cover external columns. See [`../reference/external-row-output.md`](../reference/external-row-output.md).

## Technical Notes

### Fallback: ACCESS_HISTORY
When `GET_LINEAGE` returns empty and lineage is expected, fall back to the ACCESS_HISTORY-based templates (`column-lineage-upstream.sql`, `column-lineage-downstream.sql`). Note that ACCESS_HISTORY has a 45-min–3-hr ingestion latency and a 365-day retention limit. Not all query patterns expose column-level detail, so coverage may be incomplete.

### Best Practices
1. Use fully qualified names: DATABASE.SCHEMA.TABLE.COLUMN
2. For complex transformations, verify with actual query review
