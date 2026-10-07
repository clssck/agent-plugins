# Pruning Troubleshooting

Common issues that cause poor partition pruning, and how to diagnose them.

## Common Issues

### 1. Filter on Column has Poor Pruning

Snowflake micro-partitions store min/max metadata per column. Snowflake checks filter predicates against each partition's [min, max] range and skips partitions where no matching rows can exist.

Pruning effectiveness depends on physical data ordering. Columns whose values are naturally ordered across partitions (e.g., chronologically inserted timestamps) produce narrow, non-overlapping ranges — most partitions get eliminated. Randomly distributed columns span the full value range in every partition, preventing pruning.

See `references/clustering_concepts.md` for more cluster key analysis.

### 2. Function Applied to Clustered Column

Applying a function to a clustered column — in WHERE clauses or JOIN conditions — can prevent the query optimizer from pruning effectively. Assume any function on column data will prevent pruning unless tests prove otherwise.

```sql
-- May NOT prune effectively
WHERE LOWER(region) = 'us-east'

-- Better: store pre-transformed values or use direct comparison
WHERE region = 'US-EAST'

-- Functions on static values are okay
WHERE event_date >= TO_DATE('2025-01-01')
```

### 3. Multi-Column Clustering Key Order

Clustering key column order matters. Lower cardinality columns should come first in the cluster column order. Filtering on the **first** column in the key provides better pruning than filtering on subsequent columns alone.

Example: If clustering key is `(region, event_date)`:
- `WHERE region = 'US'` → Good pruning (first column)
- `WHERE event_date = '2025-01-01'` → Poor pruning (second column only)
- `WHERE region = 'US' AND event_date = '2025-01-01'` → Best pruning (both columns)

## Diagnostic Query

Check if a filter was pushed down to the TableScan operator:

```sql
SELECT
    operator_type,
    operator_statistics:pruning.partitions_scanned::NUMBER AS partitions_scanned,
    operator_statistics:pruning.partitions_total::NUMBER AS partitions_total,
    operator_attributes:filter_condition::STRING AS pushed_filter,
    operator_attributes:table_name::STRING AS table_name
FROM TABLE(GET_QUERY_OPERATOR_STATS('<QUERY_ID>'))
WHERE operator_type IN ('TableScan', 'Filter');
```

If `pushed_filter` is NULL on a TableScan that scans many partitions, the filter was not pushed down — likely one of the issues above.

## Reference

- [Clustering Keys & Clustered Tables](https://docs.snowflake.com/en/user-guide/tables-clustering-keys)
- [GET_QUERY_OPERATOR_STATS](https://docs.snowflake.com/en/sql-reference/functions/get_query_operator_stats)
