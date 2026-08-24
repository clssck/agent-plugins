# Pruning Summary

**This is a Phase 1 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Present a high-level overview of pruning efficiency across tables and columns. Also covers clustering analysis and search optimization candidates (CLUSTERING and SEARCH_OPT entities route here).

## Workflow

### Step 1: Table-Level Pruning

**[MANDATORY]** Fetch and execute the exact SQL from verified query: `Pruning opportunity, sorted by the potential to avoid partitions` in the semantic model. Do NOT rewrite or regenerate this query.

Present results:

```
## Tables with Worst Pruning (Last 7 Days)

| Table | Query Count | Partitions Scanned | Partitions Pruned | Pruning % | Excess Rows Scanned |
```

### Step 2: Column-Level Pruning

**[MANDATORY]** Fetch and execute the exact SQL from verified query: `Identification of columns that have opportunities to improve pruning rate` in the semantic model. Do NOT rewrite or regenerate this query.

Present results:

```
## Columns with Pruning Opportunity

| Table | Column | Usage Count | Unused Rows % | Excess Rows Scanned |
```

### Step 3: Clustering vs Search Optimization Explainer

**When to include:** If Steps 1 and 2 returned results (i.e., tables/columns with poor pruning were found), include this comparison to help the user understand the two main optimization paths.

Present:

```
## Clustering Keys vs Search Optimization Service (SOS)

| Aspect | Clustering Keys | Search Optimization (SOS) |
|---|---|---|
| **Best for** | Range filters, sorted scans, low-to-medium cardinality columns | Point lookups, equality filters, high-cardinality columns (IDs, UUIDs) |
| **How it works** | Physically reorganizes micro-partitions so similar values are co-located — improves partition pruning | Builds a search access path (index-like structure) — skips partitions without reorganizing data |
| **Scope** | Affects ALL queries on the table (can help some, hurt others) | Targets specific columns/expressions — no impact on other queries |
| **Maintenance** | Automatic Reclustering runs continuously (credit cost) | Maintenance runs automatically (serverless credit cost) |
| **Setup** | `ALTER TABLE ... CLUSTER BY (col)` | `ALTER TABLE ... ADD SEARCH OPTIMIZATION ON EQUALITY(col)` |
| **Cost estimation** | `SYSTEM$ESTIMATE_AUTOMATIC_CLUSTERING_COSTS` | `SYSTEM$ESTIMATE_SEARCH_OPTIMIZATION_COSTS` |
| **Zero-cost alternative** | — | Snowflake Optima (Gen2 standard warehouses, best-effort automatic optimization) |

### When to Choose Which

| Access Pattern | Recommendation |
|---|---|
| **Range filters** (`BETWEEN`, `>=`, `<=`) on dates, numbers | Clustering — partitions are sorted for range elimination |
| **Equality point lookups** (`WHERE id = '...'`) on UUIDs, emails, IDs | SOS — clustering on random values is expensive and yields diminishing returns |
| **Timestamps** used in range filters | Clustering with `DATE_TRUNC` expression — raw timestamps have too-high cardinality for auto-clustering. Align the truncation granularity with query access patterns (e.g., `DATE_TRUNC('day', ...)` if queries filter by day, `DATE_TRUNC('hour', ...)` if by hour) |
| **Strings with common prefixes** (URLs, paths) | Clustering with `SUBSTR` expression to skip redundant prefix bytes |
| **Mixed patterns** on same table | Both — clustering on range-filter columns, SOS on point-lookup columns |
| **Small tables** (< 1GB) | Neither — overhead of auto-clustering/SOS not justified for small data |

**Note:** Very high cardinality columns (NDV > 100k) make auto-clustering expensive. For such columns, consider expression-based clustering (e.g., `LEFT(uuid, 4)`, `DATE(ts)`) to reduce cardinality, or use SOS instead.

**Ingestion alignment:** Clustering cost is heavily influenced by how well the first clustering key aligns with the data's ingestion order. For example, on a log landing table, `CLUSTER BY (date, metric)` is significantly cheaper than `CLUSTER BY (metric, date)` because rows are naturally loaded in date order — the data is already mostly sorted on `date`, reducing the amount of physical reorganization needed.
```

**[IMPORTANT]:** Fetch the latest trade-off details from official Snowflake docs at runtime:
- Clustering: https://docs.snowflake.com/en/user-guide/tables-clustering-keys
- Search Optimization: https://docs.snowflake.com/en/user-guide/search-optimization/cost-estimation
- Snowflake Optima: https://docs.snowflake.com/en/user-guide/snowflake-optima

**[STOP]** Present all three sections. Ask: "Want me to analyze clustering health and search optimization candidates in detail, or provide specific recommendations for the tables above?"
