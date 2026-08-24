# Clustering Concepts

Reference for interpreting `SYSTEM$CLUSTERING_INFORMATION` output.

## How to Call

```sql
SELECT SYSTEM$CLUSTERING_INFORMATION('<DATABASE.SCHEMA.TABLE>', '(<COLUMN_EXPRESSION>)');
```

Returns JSON with clustering health metrics for the specified column(s).

## Key Metrics

### average_depth

Number of overlapping micro-partitions for a given value of the clustering key. **Lower is better** for pruning.

- If `average_depth` is close to `total_partition_count`: No effective pruning is possible on this column — partitions overlap heavily.
- If `average_depth` is much less than `total_partition_count`: Good pruning potential — Snowflake can skip many partitions.

### average_overlaps

Number of micro-partitions with overlapping value ranges. **Lower indicates better clustering.**

### total_constant_partition_count

Number of micro-partitions where the clustering key has a single distinct value. Higher means more partitions are perfectly clustered for that key.

### partition_depth_histogram

Distribution of micro-partitions across depth buckets (0–16 with increments of 1, then 32, 64, 128, ...). Partitions in **lower numbered buckets** indicate better clustering.

## Interpreting Results

1. Compare `average_depth` to `total_partition_count`:
   - depth ≈ total partitions → No effective pruning possible
   - depth << total partitions → Good pruning potential

2. Check `partition_depth_histogram`:
   - Most partitions at depth 1-2 → Well clustered
   - Most partitions at depth 64-128 → Poorly clustered

3. `total_constant_partition_count` / `total_partition_count`:
   - Higher ratio → More partitions can be definitively skipped during pruning

## Reference

- [Clustering Information](https://docs.snowflake.com/en/sql-reference/functions/system_clustering_information)
- [Clustering Keys & Clustered Tables](https://docs.snowflake.com/en/user-guide/tables-clustering-keys)
- [Automatic Clustering](https://docs.snowflake.com/en/user-guide/tables-auto-reclustering)
