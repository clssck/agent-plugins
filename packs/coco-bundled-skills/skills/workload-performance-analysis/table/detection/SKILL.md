# Table Detection

**This is a Phase 2 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Perform deeper analysis on a specific table by routing to pruning and search optimization detection.

## Prerequisites

- Table summary data already presented by `table/summary/SKILL.md`
- Table confirmed as non-hybrid

## Workflow

### Step 1: Clustering Health Check

If the table has a clustering key (from `cluster_by` in table/summary), check clustering health directly:

```sql
SELECT SYSTEM$CLUSTERING_INFORMATION('<DATABASE.SCHEMA.TABLE>', '(<CLUSTERING_KEY_COLUMNS>)');
```

Present:
```
### Clustering Health: <TABLE>

| Metric | Value |
|---|---|
| Clustering Key | <cluster_by_keys> |
| Total Partitions | <total_partition_count> |
| Constant Partitions | <total_constant_partition_count> |
| Average Depth | <average_depth> |
| Average Overlaps | <average_overlaps> |
```

**Load** `references/clustering_concepts.md` for metric interpretation.

If the table has **no** clustering key, skip the `SYSTEM$CLUSTERING_INFORMATION` call (there's no key to evaluate) and note "No clustering key defined" as a finding for the recommendation phase.

**For tables that already have a clustering key:** After checking clustering health, also note the candidate columns identified from query filter usage (from pruning detection). Compare these candidates against the existing key — if frequently filtered columns differ from the clustering key columns, this is a finding even if the current key's health metrics look acceptable. Workload changes over time can make an existing key suboptimal.

### Step 2: Route to Pruning Detection

Load `pruning/detection/SKILL.md` scoped to this specific table (add `WHERE table_name ILIKE '<name>'` or use the fully qualified table name in filters).

This provides:
- Query-level pruning analysis for queries accessing this table
- Search optimization candidates for this table's columns
- Column co-occurrence analysis

### Step 3: Table-Specific Insights

After pruning detection, provide table-specific insights:

1. **Clustering assessment** — Is the table clustered? If so, on which columns? Do the frequently filtered columns align with the clustering key?
2. **Query pattern** — What types of queries access this table most? (Point lookups vs. range scans vs. full scans)
3. **Search optimization fit** — Does this table have point lookup patterns that would benefit from SOS?

**[STOP]** Wait for user direction or continue to recommendations if depth = RECOMMENDATION.
