# Data Modeling and DBSQL Best Practices

## Data Modeling Best Practices

### Star Schema vs Denormalization in the Lakehouse

| Approach | Avg Query Time | Storage | Maintainability | Best For |
|---|---|---|---|---|
| Dimensional (Star Schema) | ~2.6s | Lower (normalized) | High (clear contracts) | BI dashboards, governed reporting |
| One Big Table (OBT) | ~3.5s | Higher (duplicated) | Low (wide, brittle) | Ad-hoc exploration, prototyping |
| OBT + Liquid Clustering | ~1.13s | Higher | Low | Read-heavy analytics with known filter patterns |

**Key finding:** OBT with Liquid Clustering outperforms both alternatives on read queries due to data co-location, but at the cost of storage duplication and update complexity. Star Schema remains the best balance of performance, governance, and maintainability for production workloads.

### Recommended Hybrid Medallion Approach

```
Bronze (raw)  -->  Silver (conformed)  -->  Gold (business-ready)
                   OBT or Data Vault         Star Schema
```

- **Silver layer:** Use OBT (One Big Table) or Data Vault for flexible integration. OBTs work well when sources are stable and joins are expensive. Data Vault is better when auditability and source-system traceability matter.
- **Gold layer:** Use Star Schema for governed, performant consumption. Fact and dimension tables with declared keys and constraints enable BI tool compatibility and query optimization.

### When to Normalize vs Denormalize

| Use Case | Recommendation | Rationale |
|---|---|---|
| BI dashboards with many dimensions | Normalize (Star Schema) | BI tools generate star-join queries natively |
| ML feature tables | Denormalize (OBT) | Models need flat, wide inputs; joins add training overhead |
| Ad-hoc data exploration | Denormalize (OBT) | Analysts avoid complex joins; speed matters over governance |
| Governed reporting / regulatory | Normalize (Star Schema) | Clear lineage, constrained keys, auditable dimensions |
| High-write / streaming ingest | Normalize | Narrow tables reduce write amplification |
| Read-heavy aggregations with known filters | Denormalize + Liquid Clustering | Co-located data skips I/O; filter patterns are predictable |
| Multi-team / shared data products | Normalize (Star Schema) | Contracts via keys/comments prevent coupling |

### Kimball-Style Modeling in Databricks

**Step 1: Identify the business process and grain**

Define the grain (one row = one what?) before writing any DDL. Document it in the table `COMMENT`.

**Step 2: Declare keys and constraints in Unity Catalog**

Unity Catalog supports informational constraints that BI tools and the query optimizer can leverage:

```sql
CREATE TABLE analytics.sales.fact_orders (
  order_key BIGINT GENERATED ALWAYS AS IDENTITY,
  customer_key BIGINT NOT NULL,
  product_key BIGINT NOT NULL,
  order_date DATE NOT NULL,
  quantity INT,
  unit_price DECIMAL(12,2),
  total_amount DECIMAL(14,2),
  CONSTRAINT pk_fact_orders PRIMARY KEY (order_key),
  CONSTRAINT fk_customer FOREIGN KEY (customer_key) REFERENCES analytics.sales.dim_customer(customer_key),
  CONSTRAINT fk_product FOREIGN KEY (product_key) REFERENCES analytics.sales.dim_product(product_key)
)
CLUSTER BY (order_date, customer_key)
COMMENT 'Grain: one row per order line item. Source: bronze.erp.orders joined with bronze.erp.order_lines.'
TBLPROPERTIES ('quality' = 'gold');
```

**Step 3: Tag tables and columns for governance**

```sql
ALTER TABLE analytics.sales.fact_orders SET TAGS ('domain' = 'sales', 'layer' = 'gold', 'pii' = 'false');
ALTER TABLE analytics.sales.fact_orders ALTER COLUMN total_amount SET TAGS ('metric' = 'revenue');
```

**Step 4: Compute statistics for the optimizer**

```sql
ANALYZE TABLE analytics.sales.fact_orders COMPUTE STATISTICS FOR ALL COLUMNS;
```

Run `ANALYZE TABLE` after initial load and after large batch updates. The optimizer uses these statistics for join ordering, broadcast decisions, and predicate selectivity.

### Fact Table Patterns

**Transaction Fact Table**

One row per event at the lowest grain. Most common pattern.

```sql
CREATE TABLE analytics.sales.fact_transactions (
  transaction_key BIGINT GENERATED ALWAYS AS IDENTITY,
  transaction_id STRING NOT NULL,
  customer_key BIGINT NOT NULL,
  store_key BIGINT NOT NULL,
  transaction_date DATE NOT NULL,
  transaction_timestamp TIMESTAMP NOT NULL,
  product_key BIGINT NOT NULL,
  quantity INT,
  unit_price DECIMAL(12,2),
  discount_amount DECIMAL(12,2) DEFAULT 0,
  net_amount DECIMAL(14,2),
  CONSTRAINT pk_txn PRIMARY KEY (transaction_key),
  CONSTRAINT fk_txn_customer FOREIGN KEY (customer_key) REFERENCES analytics.sales.dim_customer(customer_key),
  CONSTRAINT fk_txn_store FOREIGN KEY (store_key) REFERENCES analytics.sales.dim_store(store_key),
  CONSTRAINT fk_txn_product FOREIGN KEY (product_key) REFERENCES analytics.sales.dim_product(product_key)
)
CLUSTER BY (transaction_date, store_key)
COMMENT 'Grain: one row per product per transaction. Source: bronze.pos.transactions.';
```

**Periodic Snapshot Fact Table**

One row per entity per time period. Use for balances, inventory levels, pipeline states.

```sql
CREATE TABLE analytics.finance.fact_account_daily_balance (
  snapshot_date DATE NOT NULL,
  account_key BIGINT NOT NULL,
  balance DECIMAL(18,2),
  deposits_amount DECIMAL(18,2),
  withdrawals_amount DECIMAL(18,2),
  transaction_count INT,
  CONSTRAINT pk_balance PRIMARY KEY (snapshot_date, account_key)
)
CLUSTER BY (snapshot_date)
COMMENT 'Grain: one row per account per day. Snapshot taken at end of business day.';
```

**Accumulating Snapshot Fact Table**

One row per entity lifecycle, updated as milestones are reached. Use for pipelines, order fulfillment, claims processing.

```sql
CREATE TABLE analytics.ops.fact_order_fulfillment (
  order_key BIGINT NOT NULL,
  order_date DATE,
  payment_date DATE,
  ship_date DATE,
  delivery_date DATE,
  return_date DATE,
  days_to_ship INT,
  days_to_deliver INT,
  current_status STRING,
  CONSTRAINT pk_fulfillment PRIMARY KEY (order_key)
)
CLUSTER BY (order_date, current_status)
COMMENT 'Grain: one row per order. Updated as each fulfillment milestone is reached.';
```

**Liquid Clustering strategy for fact tables:** Cluster on the primary date column first, then on the most common filter/join key (typically a high-cardinality dimension key like `customer_key` or `store_key`). Limit to 1-4 clustering keys.

### Dimension Table Patterns

**Surrogate keys:** Use `GENERATED ALWAYS AS IDENTITY` for surrogate keys. Keep the natural/business key as a separate `NOT NULL` column for lookups and SCD tracking.

**Denormalization rules for dimensions:**
- Flatten hierarchies into the dimension (e.g., `product_category`, `product_subcategory`, `product_name` in one table).
- Embed low-cardinality reference data (e.g., status descriptions) directly.
- Use complex types (`STRUCT`, `ARRAY`, `MAP`) for nested attributes that are always accessed together.

```sql
CREATE TABLE analytics.sales.dim_customer (
  customer_key BIGINT GENERATED ALWAYS AS IDENTITY,
  customer_id STRING NOT NULL,
  full_name STRING,
  email STRING,
  phone STRING,
  address STRUCT<
    street: STRING,
    city: STRING,
    state: STRING,
    postal_code: STRING,
    country: STRING
  >,
  segment STRING,
  loyalty_tier STRING,
  first_purchase_date DATE,
  is_active BOOLEAN DEFAULT true,
  effective_date DATE NOT NULL,
  end_date DATE,
  is_current BOOLEAN NOT NULL DEFAULT true,
  CONSTRAINT pk_dim_customer PRIMARY KEY (customer_key)
)
CLUSTER BY (is_current, segment)
COMMENT 'SCD Type 2 customer dimension. Business key: customer_id. One current row per customer.';
```

### SCD Type 1 (Overwrite)

Use when history is not needed. Simpler to maintain.

```sql
MERGE INTO analytics.sales.dim_customer AS target
USING silver.crm.customers_latest AS source
  ON target.customer_id = source.customer_id AND target.is_current = true
WHEN MATCHED AND (
  target.full_name != source.full_name OR
  target.email != source.email OR
  target.segment != source.segment
) THEN UPDATE SET
  target.full_name = source.full_name,
  target.email = source.email,
  target.segment = source.segment,
  target.effective_date = current_date()
WHEN NOT MATCHED THEN INSERT (
  customer_id, full_name, email, phone, segment, loyalty_tier,
  first_purchase_date, is_active, effective_date, end_date, is_current
) VALUES (
  source.customer_id, source.full_name, source.email, source.phone,
  source.segment, source.loyalty_tier, current_date(), true,
  current_date(), NULL, true
);
```

### SCD Type 2 (History Tracking)

Use when you need to track attribute changes over time. Expire the old row and insert a new current row.

```sql
-- Step 1: Expire existing current rows where attributes have changed
MERGE INTO analytics.sales.dim_customer AS target
USING silver.crm.customers_latest AS source
  ON target.customer_id = source.customer_id AND target.is_current = true
WHEN MATCHED AND (
  target.full_name != source.full_name OR
  target.email != source.email OR
  target.segment != source.segment
) THEN UPDATE SET
  target.is_current = false,
  target.end_date = current_date();

-- Step 2: Insert new current rows for changed records
INSERT INTO analytics.sales.dim_customer (
  customer_id, full_name, email, phone, segment, loyalty_tier,
  first_purchase_date, is_active, effective_date, end_date, is_current
)
SELECT
  source.customer_id,
  source.full_name,
  source.email,
  source.phone,
  source.segment,
  source.loyalty_tier,
  source.first_purchase_date,
  true,
  current_date(),
  NULL,
  true
FROM silver.crm.customers_latest AS source
INNER JOIN analytics.sales.dim_customer AS existing
  ON source.customer_id = existing.customer_id
  AND existing.is_current = false
  AND existing.end_date = current_date()
WHERE NOT EXISTS (
  SELECT 1 FROM analytics.sales.dim_customer AS current_row
  WHERE current_row.customer_id = source.customer_id
    AND current_row.is_current = true
);

-- Step 3: Insert net-new customers
INSERT INTO analytics.sales.dim_customer (
  customer_id, full_name, email, phone, segment, loyalty_tier,
  first_purchase_date, is_active, effective_date, end_date, is_current
)
SELECT
  source.customer_id,
  source.full_name,
  source.email,
  source.phone,
  source.segment,
  source.loyalty_tier,
  current_date(),
  true,
  current_date(),
  NULL,
  true
FROM silver.crm.customers_latest AS source
WHERE NOT EXISTS (
  SELECT 1 FROM analytics.sales.dim_customer AS existing
  WHERE existing.customer_id = source.customer_id
);
```

> **Note:** The 3-step pattern above is the most explicit approach. In newer Databricks runtimes, a single `MERGE` with `WHEN MATCHED ... THEN INSERT` (insert-from-matched) can handle SCD2 in one statement. Prefer the simpler approach when your runtime supports it.

### Partitioning Strategies

**Liquid Clustering is the recommended approach.** Traditional Hive-style partitioning (`PARTITIONED BY`) still works but has significant limitations that Liquid Clustering addresses.

#### Liquid Clustering vs Traditional Partitioning

| Aspect | Traditional Partitioning | Liquid Clustering |
|---|---|---|
| Definition | `PARTITIONED BY (col)` at table creation | `CLUSTER BY (col1, col2)` at or after table creation |
| Column changes | Requires full table rewrite | `ALTER TABLE ... CLUSTER BY (new_cols)` -- no rewrite |
| Cardinality limit | Low cardinality only (date, region) | Handles high cardinality (user_id, timestamp) |
| Small file problem | Common with high-cardinality or streaming | Automatic compaction resolves small files |
| Partition pruning | Explicit partition filters required | Automatic data skipping via min/max stats |
| Write overhead | Sorting at write time, partition discovery | Background optimization via `OPTIMIZE` |
| Best for | Legacy tables, very stable schemas | New tables, evolving query patterns |

**Rules of thumb for traditional partitioning (if used):**
- Partition column should have < 10,000 distinct values.
- Each partition should be at least 1 GB.
- Do not partition if total table size is < 1 TB.

### Liquid Clustering Key Selection Best Practices

**General rules:**
- Use 1-4 clustering keys. More keys dilute effectiveness.
- Order keys from most-filtered to least-filtered in common queries.
- Prefer columns that appear in `WHERE`, `JOIN ON`, and `GROUP BY` clauses.

**Fact table strategy:**
1. Primary date/timestamp column (almost always the first key).
2. Most common join key or filter dimension (e.g., `customer_key`, `region`).
3. Optional: secondary filter column if queries consistently filter on it.

```sql
-- Fact table: date-first, then common filter
CLUSTER BY (order_date, store_key)

-- High-cardinality fact: date + status for pipeline queries
CLUSTER BY (event_timestamp, status)
```

**Dimension table strategy:**
1. `is_current` flag (for SCD Type 2 dimensions -- most queries filter on current rows).
2. Most common filter attribute (e.g., `segment`, `region`, `category`).

```sql
-- SCD2 dimension: current-flag first, then common filter
CLUSTER BY (is_current, segment)

-- Type 1 dimension: common filter only
CLUSTER BY (category, brand)
```

**Re-evaluate clustering keys when:**
- Query patterns shift (new dashboards, new teams querying differently).
- Table grows beyond 1 TB and scan times increase.
- `DESCRIBE DETAIL` shows poor clustering ratios.

---

## DBSQL Performance Best Practices

### SQL Warehouse Sizing and Auto-Scaling

**Sizing guidelines:**

| Warehouse Size | vCPUs | Typical Use Case |
|---|---|---|
| 2X-Small | 8 | Development, testing, light ad-hoc |
| X-Small | 16 | Small dashboards, single-user exploration |
| Small | 32 | Team dashboards, moderate concurrency |
| Medium | 64 | Production dashboards, moderate data volumes |
| Large | 128 | Heavy ETL, large aggregations |
| X-Large+ | 256+ | Complex joins on very large tables |

**Auto-scaling guidelines:**
- Set **min clusters = 1** for always-on workloads (dashboards with consistent traffic).
- Set **min clusters = 0** (Serverless) for intermittent workloads to save costs.
- Set **max clusters** based on peak concurrent query load. Each cluster handles approximately 10 concurrent queries effectively.
- Use **scaling policy = "Queue"** for cost optimization (queries queue before scaling up).
- Use **scaling policy = "Optimized"** for latency-sensitive dashboards (pre-warms clusters).
- **Auto-stop timeout:** 10 minutes for interactive workloads, 5 minutes for scheduled jobs.

**Serverless SQL Warehouses** are recommended for most workloads. They eliminate cold-start delays and handle auto-scaling automatically.

### Liquid Clustering Optimization

- Run `OPTIMIZE` on tables after large writes to trigger Liquid Clustering compaction:

```sql
OPTIMIZE analytics.sales.fact_orders;
```

- For incremental workloads, `OPTIMIZE` only processes files that need compaction (not the full table).
- Schedule `OPTIMIZE` as a post-load step in ETL jobs, not as a standalone cron. This ensures data is compacted before downstream queries run.
- Monitor clustering effectiveness:

```sql
DESCRIBE DETAIL analytics.sales.fact_orders;
-- Check: numFiles, sizeInBytes, clusteringColumns
```

### Query Optimization Tips

**Predicate pushdown:** Filters on clustering or partition columns push down to the file level, skipping irrelevant data.

```sql
-- Good: filter on clustered column pushes down
SELECT * FROM analytics.sales.fact_orders
WHERE order_date BETWEEN '2025-01-01' AND '2025-03-31';

-- Bad: wrapping clustered column in a function defeats pushdown
SELECT * FROM analytics.sales.fact_orders
WHERE YEAR(order_date) = 2025;
```

**Column pruning:** Select only the columns you need. Delta reads are columnar; fewer columns = less I/O.

```sql
-- Good: only reads 3 columns from storage
SELECT order_date, customer_key, total_amount
FROM analytics.sales.fact_orders
WHERE order_date = '2025-06-01';

-- Bad: reads all columns, most discarded
SELECT * FROM analytics.sales.fact_orders
WHERE order_date = '2025-06-01';
```

**Broadcast join hints:** When joining a large fact table with a small dimension (< 1 GB), hint the optimizer to broadcast the dimension:

```sql
SELECT /*+ BROADCAST(d) */
  f.order_date,
  d.segment,
  SUM(f.total_amount) AS revenue
FROM analytics.sales.fact_orders f
JOIN analytics.sales.dim_customer d ON f.customer_key = d.customer_key
WHERE f.order_date >= '2025-01-01'
GROUP BY f.order_date, d.segment;
```

The optimizer often chooses broadcast automatically when statistics are available (`ANALYZE TABLE`). Use hints only when the optimizer makes a suboptimal choice.

### Caching Behavior

**Result cache:**
- DBSQL caches query results for identical SQL text against unchanged data.
- Cache is invalidated when underlying table data changes (Delta transaction log).
- Effective for dashboards where many users run the same queries.
- No configuration required -- enabled by default.

**Disk cache (SSD cache):**
- Warm clusters cache remote data on local SSDs after first read.
- Subsequent queries on the same data read from local disk (faster than cloud storage).
- Cache is per-cluster and lost on scale-down or restart.
- Benefit increases with repeated queries on the same tables.

**Maximizing cache effectiveness:**
- Use consistent SQL text for dashboard queries (parameterized queries cache better than string-concatenated ones).
- Avoid unnecessary `ORDER BY` on cached aggregation queries (different ordering = different cache entry).
- Schedule `OPTIMIZE` during off-peak hours so cache remains warm during peak.

### ANALYZE TABLE for Statistics

```sql
-- Compute statistics for all columns (recommended after large loads)
ANALYZE TABLE analytics.sales.fact_orders COMPUTE STATISTICS FOR ALL COLUMNS;

-- Compute statistics for specific columns (faster, use for targeted optimization)
ANALYZE TABLE analytics.sales.fact_orders COMPUTE STATISTICS FOR COLUMNS order_date, customer_key;

-- Check existing statistics
DESCRIBE EXTENDED analytics.sales.fact_orders;
```

Statistics enable the optimizer to:
- Choose between broadcast and shuffle joins.
- Estimate predicate selectivity for scan ordering.
- Optimize aggregation strategies.

**When to run:**
- After initial table load.
- After large batch MERGE or INSERT operations (> 10% of table size).
- After `OPTIMIZE` (clustering changes data layout, statistics should reflect it).
- Not needed after every small incremental write.

### Anti-Patterns to Avoid

**`SELECT *` on wide tables:**
Delta is columnar. `SELECT *` on a 200-column table reads all columns from storage even if you only need 3. Always project explicitly.

**Unnecessary `DISTINCT`:**
`DISTINCT` forces a global shuffle and sort. If your query already guarantees uniqueness (e.g., joining on primary keys, using `GROUP BY`), remove `DISTINCT`.

```sql
-- Bad: DISTINCT is redundant when GROUP BY already deduplicates
SELECT DISTINCT customer_key, segment, SUM(total_amount)
FROM analytics.sales.fact_orders f
JOIN analytics.sales.dim_customer d ON f.customer_key = d.customer_key
GROUP BY customer_key, segment;

-- Good: GROUP BY already produces unique rows
SELECT customer_key, segment, SUM(total_amount)
FROM analytics.sales.fact_orders f
JOIN analytics.sales.dim_customer d ON f.customer_key = d.customer_key
GROUP BY customer_key, segment;
```

**Correlated subqueries on large tables:**
Correlated subqueries execute once per row of the outer query. On large tables, this is catastrophically slow. Rewrite as joins or window functions.

```sql
-- Bad: correlated subquery runs for every row in fact_orders
SELECT order_key, total_amount,
  (SELECT MAX(total_amount) FROM analytics.sales.fact_orders f2
   WHERE f2.customer_key = f1.customer_key) AS customer_max
FROM analytics.sales.fact_orders f1;

-- Good: window function computes in a single pass
SELECT order_key, total_amount,
  MAX(total_amount) OVER (PARTITION BY customer_key) AS customer_max
FROM analytics.sales.fact_orders;
```

**Skipping `ANALYZE TABLE`:**
Without statistics, the optimizer falls back to heuristics. This commonly leads to shuffle joins where broadcast joins would be faster, and suboptimal scan ordering.

**Over-clustering:**
Using more than 4 Liquid Clustering keys, or clustering on columns that are never filtered on, adds compaction overhead without query benefit. Review query patterns before choosing keys.

**Not running `OPTIMIZE`:**
Liquid Clustering only takes effect when `OPTIMIZE` runs. Without it, data remains in the layout it was written in, and clustering keys have no impact on query performance.
