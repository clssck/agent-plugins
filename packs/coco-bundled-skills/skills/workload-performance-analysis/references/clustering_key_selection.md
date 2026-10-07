# Clustering Key Selection — Interactive Workflow

Reference for interactively guiding the user through selecting the optimal clustering key for a table. Load this when the user opts into clustering key analysis from the recommendation phase.

## Prerequisites

Before starting the interactive workflow, verify using data already gathered in Steps 1-2:

1. **Small table guard**: If the table is < 1GB or has very few micro-partitions (< 50), advise that clustering is generally not cost-effective. Auto-clustering has ongoing credit cost — the table must be large enough to justify it. Ask the user if they still want to proceed.
2. **Hybrid / external table**: Not supported for clustering. Stop and explain. (This should already be caught by `table/summary/SKILL.md`.)
3. **Already-clustered table**: If the table already has a clustering key, include the existing key as one of the candidates. The workflow should evaluate it alongside new candidates so the user can see whether the current key is still optimal or if a different key would perform better. Present `SYSTEM$CLUSTERING_INFORMATION` results for the existing key as the baseline to compare against.
4. **Candidate columns**: Use the columns already identified from Step 1-2 findings (column usage from pruning summary, SOS candidates from detection, existing clustering key from table metadata). These are your starting candidates.

---

## Step 1: Pruning Killer Check (Static Query Analysis)

Before running any exploratory queries, analyze the query text(s) that access this table. For each candidate column, check which operators are applied to it.

### Operators That Prevent Pruning (BAD)

| Operator | Why It Kills Pruning |
|---|---|
| `ILIKE` | Case-insensitive — can't use partition min/max |
| `LIKE '%abc'` | Leading wildcard — no prefix match possible |
| `SUBSTR(col, >1, ...)` | Skips first bytes — Snowflake clusters on first ~5 bytes |
| `TO_CHAR(date_col)` | Converts to string — destroys date ordering |
| `MOD(col, N)` | Scatters values — no locality |

**Caveat — constant-per-file columns:** If a column is the first key in a compound clustering key and has low cardinality (e.g., `metric_name` in `CLUSTER BY (metric_name, date)`), many files will have a constant value for that column. In that case, the pruner evaluates the predicate against the single value in the file and can still prune — even with `ILIKE` or leading-wildcard `LIKE`. These operators only prevent pruning when the column has multiple distinct values per file.

### Operators That Allow Pruning (GOOD)

| Operator | Why It Works |
|---|---|
| `=`, `IN` | Exact match — partition min/max can eliminate ranges |
| `BETWEEN`, `>=`, `<=` | Range filter — works with sorted partitions |
| `LIKE 'abc%'` | Prefix match — aligns with first-5-byte clustering |
| `DATE_TRUNC()`, `TRUNC()` | Reduces granularity while preserving order |
| `LEFT(col, N)` | Prefix extraction — aligns with clustering byte limit |

### Predicate Classification

Classify how each candidate column is used:

| Predicate Type | Clustering Benefit |
|---|---|
| **Local predicate** (`WHERE col = 'x'`) | Best — enables static partition pruning |
| **Join predicate** (`ON t1.col = t2.col`) | Good — bloom filter dynamic pruning benefits from clustering |
| **MERGE ON clause** | Good — improves scanback efficiency |
| **GROUP BY / ORDER BY only** | Moderate — can improve memory usage and sort performance |

**Action**: If ALL uses of a candidate column involve BAD operators, warn the user that clustering on this column won't help unless the queries are rewritten. Remove it from candidates.

---

## Step 2: Selectivity Analysis (Interactive)

For each surviving candidate column, check how selective the typical predicates are.

### Exploratory Query

Propose to the user:

```sql
-- Check selectivity of a predicate
SELECT
    COUNT_IF(<predicate>) AS matching_rows,
    COUNT(*) AS total_rows,
    ROUND(COUNT_IF(<predicate>) / COUNT(*), 4) AS selectivity
FROM <table>;
```

Replace `<predicate>` with the actual filter condition from the workload queries (e.g., `region = 'US-EAST'`, `event_date >= '2025-01-01'`).

**[IMPORTANT]** Show the query to the user and ask for confirmation before executing. Explain what it checks.

### Interpretation

| Selectivity | Assessment |
|---|---|
| < 0.01 (1%) | Excellent — highly selective, strong clustering candidate |
| 0.01 - 0.1 | Good — meaningful data reduction |
| 0.1 - 0.3 | Moderate — some benefit, weigh against clustering cost |
| 0.3 - 0.5 | Poor — filters too little data for the clustering cost |
| > 0.5 (50%) | Useless for clustering — almost no data eliminated |

**Note:** The ideal selectivity threshold depends on the trade-off between query performance SLA and clustering cost. Stricter SLAs (e.g., interactive dashboards) warrant lower thresholds; batch workloads may tolerate higher selectivity.

**Composite selectivity rules:**
- `AND` multiplies selectivity (good — combined filter is more selective)
- `OR` adds selectivity (bad — combined filter is less selective)

---

## Step 3: NDV Rule — Cardinality & Cost (Interactive)

High cardinality (many distinct values) gives good uniqueness but is **expensive** for auto-clustering. The ideal clustering key has moderate cardinality.

### Exploratory Query

Propose to the user:

```sql
-- Check approximate number of distinct values
SELECT APPROX_COUNT_DISTINCT(<column>) AS approx_ndv
FROM <table>;
```

**[IMPORTANT]** Show the query to the user and ask for confirmation before executing. Use `APPROX_COUNT_DISTINCT` (not exact COUNT DISTINCT) to minimize cost on large tables.

### Target NDV

The core formulas for clustering key pruning are:

```
prune_ratio  = 1 / CLUSTER_KEY_NDV
scanned_partitions = total_partitions × prune_ratio
```

First, check the table's partition count so you can reason about the impact:

```sql
-- Check table partition count
SELECT PARSE_JSON(SYSTEM$CLUSTERING_INFORMATION('<database>.<schema>.<table>')):"total_partition_count"::INT AS total_partitions;
```

**[IMPORTANT]** Show the query to the user and ask for confirmation before executing.

#### General Rule: Target NDV ≤ 100 for Leading Columns

For typical OLAP workloads with 2-3 predicates, target NDV ≤ 100 per clustering column (especially the leading column). This gives each predicate a selectivity of ~0.01. With 3 such predicates combined, overall selectivity reaches ~0.000001, which is sufficient for effective pruning across tables from 1k to 10M partitions.

**Benchmark reference** (single equality predicate on a well-clustered table):

| Total Partitions | NDV | Scanned Partitions | Prune Ratio |
|---|---|---|---|
| 10k | 100 | 100 | 0.01 |
| 10k | 1,000 | 10 | 0.001 |
| 100k | 100 | 1,000 | 0.01 |
| 100k | 1,000 | 100 | 0.001 |
| 1M | 100 | 10,000 | 0.01 |
| 1M | 1,000 | 1,000 | 0.001 |

Lower NDV also reduces auto-clustering costs significantly and helps maintain better clustering order for remaining columns in composite keys. Higher NDV (>1,000) improves pruning but increases auto-clustering credit consumption — only pursue higher NDV for critical workloads where every second matters, and monitor costs closely.

For batch workloads without strict SLAs, NDV lower than 100 is acceptable — it trades pruning granularity for reduced clustering cost.

### Truncation Strategies for High-Cardinality Columns

When a candidate column has too-high cardinality, apply expression-based clustering:

#### Timestamps

Raw timestamps (nanosecond/millisecond precision) have extremely high NDV. Truncate:

```sql
-- Check NDV of truncated expression
SELECT APPROX_COUNT_DISTINCT(DATE_TRUNC('hour', <ts_col>)) AS ndv_hourly,
       APPROX_COUNT_DISTINCT(DATE(<ts_col>)) AS ndv_daily
FROM <table>;
```

- Use `DATE_TRUNC('hour', col)` for recent data with high ingest rate
- Use `DATE(col)` for historical data spanning months/years
- Cluster as: `ALTER TABLE ... CLUSTER BY (DATE_TRUNC('hour', <col>))`

**Align truncation with query access patterns:** Choose the `DATE_TRUNC` granularity that matches how queries filter the data. If queries filter by day (e.g., `WHERE event_date = '2025-01-15'`), use `DATE(col)`. If queries filter by hour windows, use `DATE_TRUNC('hour', col)`. Misaligned truncation (e.g., truncating to hour when queries filter by day) wastes clustering effort.

#### UUIDs and Hashes

Random UUIDs (UUID4) and hex hashes have near-unique NDV and no natural ordering. Do NOT cluster on the raw column.

**If UUIDs are used in equality point lookups** (`WHERE id = '...'`), **recommend Search Optimization Service (SOS) instead of clustering**. This is an OLTP-like access pattern on an OLAP table — SOS is purpose-built for it. Consider Unistore (hybrid tables) if the workload is heavily point-lookup driven.

**If UUIDs are join keys** (e.g., surrogate keys in MERGE/SCD2 pipelines), clustering with a `LEFT()` truncation can still help. Use the minimum `LEFT(N)` that gives an acceptable prune ratio for the table size — going higher adds auto-clustering cost without improving pruning:

| Row Count | Partitions (~250 byte rows) | Recommended Expression | NDV | Scanned Partitions |
|---|---|---|---|---|
| 100M | ~1k | `LEFT(col, 2)` | 256 | ~7 |
| 1B | ~10k | `LEFT(col, 3)` | 4,096 | ~3 |
| 10B | ~100k | `LEFT(col, 4)` | 65,536 | ~2 |
| 100B | ~1M | `LEFT(col, 4)` | 65,536 | ~17 |

**Note:** These benchmarks assume ~250 byte row size. Smaller rows produce fewer partitions for the same row count (better pruning at the same NDV); larger rows produce more partitions (may need higher `LEFT(N)`).

For numeric IDs, apply `TRUNC(col, -N)` to achieve similar NDV reduction (e.g., `TRUNC(id, -6)` on an 8-digit ID gives NDV ~100).

#### Strings with Common Prefixes

Snowflake uses the first ~5 bytes of a string for clustering. If column values share a long common prefix (e.g., URLs starting with `https://www.`), clustering on the raw column is ineffective.

**Note:** Interactive tables are out of scope for this workflow (they use a different storage engine) — see `interactive-clustering-key-recommendation` for interactive table clustering guidance.

```sql
-- Check if the first 5 bytes have low diversity
SELECT APPROX_COUNT_DISTINCT(SUBSTR(<col>, 1, 5)) AS ndv_first_5_bytes,
       APPROX_COUNT_DISTINCT(<col>) AS ndv_full
FROM <table>;
```

If `ndv_first_5_bytes` is much lower than `ndv_full`, the prefix is redundant. Recommend clustering on `SUBSTR(<col>, N, M)` where N skips the common prefix. Ask the user to confirm the common prefix pattern.

#### Variant Paths

Snowflake supports clustering on variant paths (e.g., `src:event_time`). While it works, performance is often better with a physical column.

**Recommendation**: If a variant path is the best candidate, suggest materializing it:
```sql
ALTER TABLE <table> ADD COLUMN <col_name> <TYPE> AS (<variant_col>:<path>::<TYPE>);
```
Then cluster on the materialized column.

---

## Step 4: Composite Key Ordering

If multiple columns survive as good clustering candidates, order them in the clustering key definition by:

1. **Query frequency**: Column that appears in the most queries comes first
2. **Selectivity**: More selective columns (lower selectivity ratio) come first
3. **Lower NDV first**: Put lower cardinality columns before higher ones to improve "clustering depth" — this ensures broader partitioning at the first level
4. **Ingestion alignment**: If a candidate column is naturally ordered by ingestion (e.g., a log timestamp on a log landing table), placing it first significantly reduces clustering cost — the data is already mostly sorted on that column, so auto-clustering does less work. To check ingestion alignment, run `SYSTEM$CLUSTERING_INFORMATION('<table>', '(<candidate_col>)')` *before* enabling clustering. Low `average_overlap` indicates the column is already well-aligned with the physical file layout.

**Example**: If `region` (NDV ~50, appears in 80% of queries) and `event_date` (NDV ~365, appears in 60% of queries):
```sql
ALTER TABLE ... CLUSTER BY (region, DATE(event_date));
```

If `event_date` aligns with ingestion order (data is loaded chronologically), putting it first reduces clustering cost: `ALTER TABLE ... CLUSTER BY (DATE(event_date), region);` — but this trades off pruning efficiency for queries that filter only on `region`. Balance based on workload priority.

**Maximum key width**: Keep composite keys to 3-4 columns. Beyond that, clustering effectiveness diminishes and cost increases.

---

## SOS vs Clustering Decision Summary

Use this when deciding between recommending clustering vs Search Optimization:

| Pattern | Recommendation |
|---|---|
| Range filters on low-to-medium cardinality column | **Clustering** |
| Equality point lookups on high-cardinality column (IDs, UUIDs, emails) | **SOS** (Search Optimization) |
| Sorted/ordered scans (ORDER BY, window functions) | **Clustering** |
| LIKE with leading wildcard on specific column | **SOS** with `SUBSTRING` expression |
| Multiple access patterns on same table | **Both** — clustering on range-filter columns, SOS on point-lookup columns |
| Table < 1GB | **Neither** — overhead not justified |

---

## Output Format

Present the final recommendation as:

```
### Clustering Key Recommendation: <DATABASE>.<SCHEMA>.<TABLE>

1. **Recommended Key**: `ALTER TABLE <table> CLUSTER BY (<key_expression>)`

2. **Rationale**: Why these columns — which queries benefit, which predicates align

3. **Key Strategy**: Any truncation or expression used and why
   (e.g., "DATE_TRUNC('hour', event_time) reduces NDV from 8.5M to ~12k, keeping auto-clustering cost manageable")

4. **Expected Outcome**: How this improves the specific workload
   (e.g., "Enables partition pruning for the 15 queries filtering on event_time, reducing average partitions scanned from 85% to estimated ~10%")

5. **Cost Estimation**: Suggest running before committing:
   `SELECT SYSTEM$ESTIMATE_AUTOMATIC_CLUSTERING_COSTS('<table>', '(<key_expression>)')`

6. **SOS Additions** (if applicable): Any columns that should get SOS instead of or in addition to clustering
```

**[STOP]** Present the recommendation and wait for user feedback.

---

## Reference

- [Clustering Keys & Clustered Tables](https://docs.snowflake.com/en/user-guide/tables-clustering-keys)
- [Automatic Clustering](https://docs.snowflake.com/en/user-guide/tables-auto-reclustering)
- [Search Optimization Service](https://docs.snowflake.com/en/user-guide/search-optimization-service)
- [SYSTEM$ESTIMATE_AUTOMATIC_CLUSTERING_COSTS](https://docs.snowflake.com/en/sql-reference/functions/system_estimate_automatic_clustering_costs)
