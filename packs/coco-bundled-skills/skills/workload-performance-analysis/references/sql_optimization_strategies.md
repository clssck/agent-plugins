# SQL Optimization Strategies Reference

Fix strategies, column inference, and view expansion handling for SQL-level query optimization.

## Fix Strategies by Insight Category

### Table Scan Insights

| Insight Type | Fix Strategy |
|---|---|
| `NO_FILTER_ON_TOP_OF_TABLE_SCAN` | Add WHERE clause on clustering key, date range, or high-cardinality column. |
| `INAPPLICABLE_FILTER_ON_TABLE_SCAN` | Replace ineffective filter with one that matches partition boundaries or clustering key. |
| `UNSELECTIVE_FILTER` | Add more selective condition, combine with another filter, or remove if purposeless. |
| `LIKE_WITH_LEADING_WILDCARD` | (1) Remove leading wildcard if business logic allows. (2) Enable Search Optimization on the column (`ALTER TABLE ... ADD SEARCH OPTIMIZATION ON SUBSTRING(col)`). (3) Add additional selective filter to reduce scan first. |

### Aggregation Insights

| Insight Type | Fix Strategy |
|---|---|
| `INEFFICIENT_AGGREGATE` | Remove redundant GROUP BY columns (e.g., grouping by unique key). Remove DISTINCT if results are already unique. Check if aggregation is needed at all. |

### Join Insights

| Insight Type | Fix Strategy |
|---|---|
| `EXPLODING_JOIN` | (1) Add filter before join to reduce input rows. (2) Change join granularity (e.g., DATE → HOUR). (3) Pre-aggregate one side before joining. (4) Add more specific join condition. |
| `NESTED_EXPLODING_JOIN` | **Fix innermost join first** — the earliest explosion causes the cascade. Then address outer joins if still problematic. |
| `INEFFICIENT_JOIN_CONDITION` | Simplify join condition. Move complex expressions to WHERE clause. Pre-compute join keys in CTE. |
| `JOIN_WITH_NO_JOIN_CONDITION` | Add explicit join condition. Check for matching column names or FK relationships. |

### Union Insights

| Insight Type | Fix Strategy |
|---|---|
| `UNNECESSARY_UNION_DISTINCT` | Change `UNION` to `UNION ALL` if sources are already distinct. Verify data sources don't have overlapping rows. |

### Resource Insights (DO NOT Modify SQL)

| Insight Type | Action |
|---|---|
| `REMOTE_SPILLAGE` | Check for co-located SQL insight first (see `references/query_insights.md`). If co-located → fix SQL issue first. If standalone → recommend larger warehouse. |
| `QUEUED_OVERLOAD` | Use dedicated/less-utilized warehouse, schedule off-peak, consider multi-cluster. |

---

## Column and Value Inference

When an insight indicates a missing or ineffective filter, infer the column and value using this priority order:

| Priority | Source | Confidence | Action |
|---|---|---|---|
| 1 | Existing patterns in SQL (same column/date range in other clauses) | 90-100 | Auto-apply with `[INFERRED]` tag |
| 2 | Clustering key on the table | 70-85 | Auto-apply with `[INFERRED]` + `[ACTION REQUIRED]` |
| 3 | Search optimization enabled on column | 65-80 | Apply with `[INFERRED]` + `[ACTION REQUIRED]` |
| 4 | Indexes (hybrid tables only — verify with `IS_HYBRID = 'YES'`) | 60-75 | Apply with `[INFERRED]` + `[ACTION REQUIRED]` |
| 5 | FK relationships (`REFERENTIAL_CONSTRAINTS`) | 55-70 | Suggest, ask for confirmation |
| 6 | Column name matching (`*_id`, `*_date` patterns) | 40-60 | Suggest, ask for confirmation |
| 7 | Column type heuristics (DATE/TIMESTAMP → date range) | 20-40 | Suggest, ask for confirmation |
| 8 | GROUP BY / SELECT columns already in query | 30-45 | Suggest, ask for confirmation |
| 9 | Ask user | 0 | Must ask before applying |

**Clustering key extraction:** Strip wrapping functions to find base column names:
- `LINEAR(trunc(col,-1))` → `col`
- `(DATE_TRUNC('DAY', event_time))` → `event_time`
- `(YEAR(created_at), MONTH(created_at))` → `created_at`

**Get clustering key:** `SHOW TABLES LIKE '<TABLE_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>` — check `cluster_by` column.

**Validate inferred column:** Verify column exists via `INFORMATION_SCHEMA.COLUMNS` before suggesting.

---

## View Expansion Detection

When Query Insights reference a table not present in the SQL text, a view is being expanded.

### Detection

1. Extract table names from SQL text (FROM/JOIN clauses)
2. Get table names from operator stats:
   ```sql
   SELECT OPERATOR_ATTRIBUTES:table_name::STRING AS table_name
   FROM TABLE(GET_QUERY_OPERATOR_STATS('<QUERY_ID>'))
   WHERE OPERATOR_TYPE = 'TableScan'
   ```
3. If insight's table is NOT in SQL text → view expansion

### Resolution

```sql
-- Find which view references the underlying table
SELECT 
    REFERENCING_DATABASE || '.' || REFERENCING_SCHEMA || '.' || REFERENCING_OBJECT_NAME AS view_name,
    REFERENCED_DATABASE || '.' || REFERENCED_SCHEMA || '.' || REFERENCED_OBJECT_NAME AS underlying_table
FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES
WHERE REFERENCED_OBJECT_NAME = '<INSIGHT_TABLE_NAME>'
  AND REFERENCED_OBJECT_DOMAIN = 'TABLE'
  AND REFERENCING_OBJECT_DOMAIN = 'VIEW'
```

**Note:** `OBJECT_DEPENDENCIES` has up to 3-hour latency. Use `GET_DDL('VIEW', '<view_name>')` for exact view definition when needed.

### Nested Views

Views can reference other views. Use recursive CTE on `OBJECT_DEPENDENCIES` with depth limit of 10 to trace full chain. Match the top-level view with the view in the SQL text.

### Comment Guidelines

- Always note the underlying table: `FROM my_view -- issue in underlying table: raw_orders`
- Add `[NOTE]` about view DDL changes only when: filter logically belongs in view, issue affects all view users, and high confidence
- DO NOT suggest view changes for: query-specific filters, system views, shared views, or uncertain cases

---

## General Suggestions (No-Insights Fallback)

When Query Insights returns 0 rows and query is < 2 hours old, use operator stats pattern detection:

| Pattern | Detection | Suggestion |
|---------|-----------|-----------|
| Large Join Output | Join operator `output_rows >> input_rows` | Add filter or refine join |
| Large Table Scan | TableScan with high `output_rows`, no filter | Add WHERE clause |
| Many-to-Many Join | Join where both sides have high row counts | Filter or pre-aggregate |
| Redundant Aggregate | Aggregate where `input_rows ≈ output_rows` | Remove redundant GROUP BY / DISTINCT |
| Cross Join | Join with no equality condition | Add join condition |
| Late Filter | Filter after large intermediate results | Push filter earlier |

Use `[GENERAL SUGGESTION]` tags instead of `[QUERY_INSIGHT_*]` tags.

### Filter Pushdown Detection

```sql
WITH ops AS (
    SELECT OPERATOR_ID, OPERATOR_TYPE,
        OPERATOR_STATISTICS:input_rows::NUMBER AS input_rows,
        OPERATOR_STATISTICS:output_rows::NUMBER AS output_rows
    FROM TABLE(GET_QUERY_OPERATOR_STATS('<QUERY_ID>'))
)
SELECT f.OPERATOR_ID AS filter_id, j.OPERATOR_ID AS join_id,
    f.input_rows AS filter_input, f.output_rows AS filter_output,
    (f.input_rows - f.output_rows) / NULLIF(f.input_rows, 0) AS filter_reduction
FROM ops f
JOIN ops j ON f.OPERATOR_ID > j.OPERATOR_ID
WHERE f.OPERATOR_TYPE = 'Filter'
  AND j.OPERATOR_TYPE IN ('Join', 'Aggregate')
  AND (f.input_rows - f.output_rows) / NULLIF(f.input_rows, 0) > 0.5
```

If a filter removes >50% of rows AFTER a join, suggest pushing the filter earlier (before the join).
