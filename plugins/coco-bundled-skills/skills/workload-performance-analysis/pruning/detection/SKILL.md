# Pruning Detection

**This is a Phase 2 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Perform deeper pruning analysis including query-level pruning efficiency, search optimization candidates, and root cause insights.

## Prerequisites

- Pruning summary data already presented by `pruning/summary/SKILL.md`

## Scope-Aware Mode (when invoked from QUERY_SET)

If the caller passed scope params (`<HASH_LIST>`, `<SCOPE_START>`, `<SCOPE_END>`), operate in **scope-aware mode** — restrict every pruning query to that scope:
- Replace `Pruning opportunity, sorted by the potential to avoid partitions` with `Pruning opportunity, sorted by the potential to avoid partitions — scoped to query set`.
- Replace `Identification of columns that have opportunities to improve pruning rate` with `Identification of columns that have opportunities to improve pruning rate — scoped to query set`.
- Note: `TABLE_QUERY_PRUNING_HISTORY` and `COLUMN_QUERY_PRUNING_HISTORY` lack `query_id`, so the scoped variants match on `query_parameterized_hash IN (<HASH_LIST>)` plus the scope time window. The scoped variants pad the upper bound by 4 hours to absorb pruning-view ingestion lag.

**In scope-aware mode:**
- The "summary already presented" prerequisite is **relaxed** — the QUERY_SET scope card replaces this sub-skill's own Phase-1 summary. Do NOT require `pruning/summary/SKILL.md` to have run first.
- **Suppress the per-step `[STOP]`** — orchestration belongs to QUERY_SET.
- Skip re-presenting table-level Phase-1 totals; focus on per-table opportunity ranking and column-level insights within the set.

When invoked outside QUERY_SET (no scope params), behave exactly as before.

## Workflow

**Step 1 (query-level pruning) and Step 2 (search optimization candidates) use independent queries — execute them in parallel.** Then process results sequentially for Steps 1B, 1C, and 3.

### Step 1: Query-Level Pruning (if relevant)

If user asked about specific queries or pruning efficiency, run the verified query: `Which queries have the worst pruning efficiency?`

Present results:

```
## Queries with Worst Pruning

| Query ID | User | Warehouse | Size | Partitions Scanned | Total | % Scanned | Pruning Efficiency | GB Scanned | Execution (s) |
```

### Step 1B: Clustering Health Check (for flagged tables)

For tables that appear in the worst-pruning results, first check table metadata:

```sql
SHOW TABLES LIKE '<TABLE_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>;
```

Check the `cluster_by` and `automatic_clustering` columns:

- **If `cluster_by` is empty**: Note "No clustering key defined" — this is itself a finding for the recommendation phase. **Do NOT run `SYSTEM$CLUSTERING_INFORMATION`** — skip to Step 1C or Step 2.
- **If `cluster_by` has a value but `automatic_clustering` is OFF**: The table has a clustering key but automatic reclustering is suspended. Note this — clustering may have degraded since it was last maintained.
- **If `cluster_by` has a value and `automatic_clustering` is ON**: The table is actively clustered.

For tables that **have a clustering key** (regardless of automatic_clustering status), run:

```sql
SELECT SYSTEM$CLUSTERING_INFORMATION('<DATABASE.SCHEMA.TABLE>', '(<EXISTING_CLUSTER_KEY>)');
```

**Also note for the recommendation phase:** Even if the existing key's health looks acceptable, record which columns are most frequently used in query predicates (from Step 1 and Step 2 results). If these differ from the existing clustering key columns, flag this as a finding — the current key may not be aligned with the actual workload, and the recommendation phase should offer re-evaluation.

Present:
```
### Clustering Health: <TABLE>

| Metric | Value |
|---|---|
| Clustering Key | <cluster_by_keys> |
| Automatic Clustering | ON / OFF |
| Total Partitions | <total_partition_count> |
| Constant Partitions | <total_constant_partition_count> |
| Average Depth | <average_depth> |
| Average Overlaps | <average_overlaps> |
```

**Load** `references/clustering_concepts.md` for metric interpretation.

### Step 1C: Operator-Level Pruning Drill-Down (optional)

If a specific query ID is in scope, offer operator-level pruning analysis via `GET_QUERY_OPERATOR_STATS` (14-day retention):

```sql
SELECT
    operator_id,
    operator_type,
    operator_statistics:output_rows::NUMBER AS output_rows,
    operator_statistics:io.bytes_scanned::NUMBER AS bytes_scanned,
    operator_statistics:io.percentage_scanned_from_cache::NUMBER AS cache_pct,
    operator_statistics:pruning.partitions_scanned::NUMBER AS partitions_scanned,
    operator_statistics:pruning.partitions_total::NUMBER AS partitions_total,
    operator_attributes:table_name::STRING AS table_name,
    operator_attributes:filter_condition::STRING AS filter_condition
FROM TABLE(GET_QUERY_OPERATOR_STATS('<QUERY_ID>'))
WHERE operator_type = 'TableScan'
ORDER BY operator_id;
```

This shows per-table-scan pruning: which tables were scanned, how many partitions, and whether a filter was pushed down.

If `filter_condition` is NULL on a TableScan that scans many partitions, the filter was not pushed down. **Load** `references/pruning_troubleshooting.md` for common causes (filter/key mismatch, functions on clustered columns, multi-column key order).

### Step 2: Search Optimization Candidates

**[MANDATORY]** Fetch and execute the exact SQL from verified query: `Identification of columns that could benefit from search to reduce scan volume` in the semantic model. Do NOT rewrite or regenerate this query.

**When presenting search optimization candidates, for EACH column provide:**

1. **Exact column**: `database.schema.table.column_name`
2. **Why this column is suggested**:
   - How many queries use this column in filters (`query_count`)
   - How many rows are being scanned (`total_rows_scanned`)
   - What expressions are supported (`search_optimization_supported_expressions`)
3. **Expected benefit**: High row scan count with low match ratio = high potential benefit

### Step 3: Insights

After presenting data, provide:

1. **Key patterns** — which tables/columns have the most wasted scans
2. **Common causes:**
   - Missing or ineffective clustering keys
   - Queries not filtering on clustered columns
   - High-cardinality columns used in equality predicates (search opt candidate)

### Step 4: Offer Drill-Down

If a specific table stands out:
- Offer to run `SYSTEM$CLUSTERING_INFORMATION` on additional column expressions (if not already checked in Step 1B)
- Offer to analyze a specific query's operator-level pruning (if not already done in Step 1C)

**[STOP]** Wait for user direction or continue to recommendations if depth = RECOMMENDATION.
