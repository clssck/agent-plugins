# Best Practices for Snowflake Interactive Tables and Warehouses

## Table of Contents
1. [Clustering Strategy](#clustering-strategy)
2. [TARGET_LAG Selection](#target_lag-selection)
3. [Warehouse Sizing](#warehouse-sizing)
4. [Query Optimization](#query-optimization)
5. [Cost Management](#cost-management)
6. [Data Ingestion Patterns](#data-ingestion-patterns)
7. [UPDATE/DELETE Operations](#updatedelete-operations)
8. [Monitoring and Maintenance](#monitoring-and-maintenance)

---

## Clustering Strategy

### Match Your Query Patterns
**Rule**: Cluster on columns used in WHERE clauses of your most frequent queries.

**For detailed clustering guidance**, **Load** [../clustering/SKILL.md](../clustering/SKILL.md).

```sql
-- ❌ BAD: Random clustering
CREATE INTERACTIVE TABLE orders
CLUSTER BY (created_timestamp)  -- But you query by customer_id!
AS SELECT * FROM orders_source;

-- ✅ GOOD: Clustering matches query pattern
CREATE INTERACTIVE TABLE orders
CLUSTER BY (customer_id, TO_DATE(order_date))
AS SELECT * FROM orders_source;

-- Query benefits from clustering
SELECT * FROM orders 
WHERE customer_id = 12345 
  AND order_date >= '2024-01-01';
```

### Use Expressions for Time-Based Data
```sql
-- ✅ GOOD: Cluster by day for daily queries
CREATE INTERACTIVE TABLE events
CLUSTER BY (TRUNC(event_timestamp, 'day'))
AS SELECT * FROM events_source;

-- ✅ GOOD: Multi-level clustering
CREATE INTERACTIVE TABLE sales
CLUSTER BY (DATE_TRUNC('month', sale_date), region)
AS SELECT * FROM sales_source;
```

### Cardinality Considerations
- **Low cardinality first**: Put lower-cardinality columns first in CLUSTER BY
- **High cardinality second**: Higher-cardinality columns second

```sql
-- ✅ GOOD: region (low cardinality) before customer_id (high cardinality)
CLUSTER BY (region, customer_id)

-- ⚠️ LESS OPTIMAL: customer_id first
CLUSTER BY (customer_id, region)
```

### Guidelines
1. **Limit cluster columns**: 2-4 columns is usually optimal
2. **Match selectivity**: Cluster on columns that filter to small result sets
3. **Test performance**: Try different clustering strategies and measure
4. **Consider data distribution**: Avoid clustering on columns with extreme skew

---

## TARGET_LAG Selection

### Balance Freshness vs. Cost

| Use Case | Recommended TARGET_LAG | Rationale |
|----------|----------------------|-----------|
| Real-time dashboards | 1-5 minutes | Fresh data critical |
| Hourly reports | 30-60 minutes | Balance cost and freshness |
| Daily summaries | 4-12 hours | Cost-effective |
| Reference data | 1-24 hours | Changes infrequent |

### Example Scenarios

#### High-Frequency Updates
```sql
-- Source changes frequently (every minute)
-- Need near real-time sync
CREATE INTERACTIVE TABLE live_metrics
CLUSTER BY (metric_timestamp)
TARGET_LAG = '1 minute'  -- Minimum allowed
WAREHOUSE = small_standard_wh
AS SELECT * FROM metrics_stream;
```

#### Moderate Updates
```sql
-- Source changes every few hours
-- 20-minute lag acceptable
CREATE INTERACTIVE TABLE sales_summary
CLUSTER BY (sale_date, region)
TARGET_LAG = '20 minutes'
WAREHOUSE = small_standard_wh
AS SELECT 
  sale_date,
  region,
  SUM(amount) AS total_sales
FROM sales_source
GROUP BY sale_date, region;
```

#### Low-Frequency Updates
```sql
-- Source changes once daily
-- Can tolerate longer lag
CREATE INTERACTIVE TABLE customer_summary
CLUSTER BY (customer_id)
TARGET_LAG = '6 hours'
WAREHOUSE = xsmall_standard_wh
AS SELECT 
  customer_id,
  SUM(lifetime_value) AS total_value
FROM customer_transactions
GROUP BY customer_id;
```

### Cost Considerations
- **Shorter lag = Higher cost**: More frequent refreshes consume more compute
- **Warehouse size matters**: Refresh warehouse affects cost
- **Data volume**: Large datasets with short lag = expensive

### Monitoring Refresh Performance
```sql
-- Check if refreshes complete within TARGET_LAG
-- Add monitoring query here when available
```

---

## Warehouse Sizing

### Starting Point
**Recommendation**: Start with **XSMALL**, monitor, and scale up if needed.

### Sizing Guidelines

Based on working data set size (the portion of data frequently queried)

When computing data and warehouse size, normalize everything to GB. Always verify units (MB, GB, TB) when making sizing calculation

| Working Set Size | Recommended Warehouse Size |
|------------------|----------------------------|
| Less than 500 GB | XSMALL |
| 500 GB to 1 TB | SMALL |
| 1 TB to 2 TB | MEDIUM |
| 2 TB to 4 TB | LARGE |
| 4 TB to 8 TB | XLARGE |
| 8 TB to 16 TB | 2XLARGE |
| Greater than 16 TB | 3XLARGE |

**Note**: The working set is the portion of the table that is frequently queried (e.g., last 7 days of data), not the entire table size.

### When to Scale Up
1. **Queries timing out**: Consistently hitting 5-second limit
2. **High concurrency**: Many users experiencing slow response
3. **Large result sets**: Scanning significant data volumes
4. **Complex JOINs**: Multiple table joins or aggregations

### When to Scale Down
1. **Underutilized**: Queries complete in < 1 second
2. **Low concurrency**: Few concurrent users
3. **Cost concerns**: Unnecessary expense

### Multi-Warehouse Strategy
```sql
-- Separate warehouses for different workloads
CREATE INTERACTIVE WAREHOUSE iwh_dashboards
TABLES (metrics, sales, customers)
WAREHOUSE_SIZE = 'SMALL';

CREATE INTERACTIVE WAREHOUSE iwh_api
TABLES (products, inventory)
WAREHOUSE_SIZE = 'XSMALL';

-- Isolates workloads and allows independent scaling
```

---

## Query Optimization

### Write Efficient Queries

#### ✅ DO: Simple, Selective Queries
```sql
-- GOOD: Selective WHERE on clustered column
SELECT * 
FROM orders
WHERE customer_id = 12345  -- Uses clustering
  AND order_date >= '2024-01-01'
LIMIT 100;

-- GOOD: Aggregation with few groups
SELECT 
  region,
  COUNT(*) AS order_count,
  SUM(amount) AS total
FROM orders
WHERE order_date >= '2024-01-01'
GROUP BY region;
```

#### ❌ DON'T: Expensive Operations
```sql
-- BAD: Cartesian product
SELECT * 
FROM orders o1 
CROSS JOIN orders o2
WHERE o1.customer_id != o2.customer_id;

-- BAD: Full table scan without WHERE
SELECT * FROM large_table;

-- BAD: Complex subqueries
SELECT *
FROM orders
WHERE customer_id IN (
  SELECT customer_id 
  FROM customers 
  WHERE region IN (
    SELECT region FROM regions WHERE ...
  )
);
```

### Use Clustering to Your Advantage
```sql
-- Query uses clustering
SELECT * FROM events
WHERE TRUNC(event_timestamp, 'day') = '2024-01-15'  -- Matches CLUSTER BY
  AND event_type = 'click';
```

### Limit Result Sets
```sql
-- Always use LIMIT for large result sets
SELECT * FROM orders
WHERE order_date >= '2024-01-01'
ORDER BY order_id
LIMIT 1000;  -- Prevents timeout on large results
```

### Avoid Window Functions
- Performance varies significantly
- Test carefully before using in production
- Consider alternatives (GROUP BY, subqueries)

### Optimize Concurrency Settings
For short, simple queries with high concurrency needs:
```sql
-- Increase max concurrency level for warehouse
ALTER WAREHOUSE iwh_name SET MAX_CONCURRENCY_LEVEL = 16;
```
This allows more queries to run in parallel on the warehouse.

---

## Mixed Workload Strategy

### The Problem

Production workloads are rarely uniform. A retail analytics platform might serve thousands of dashboard queries per second, while occasionally an analyst fires a complex ad-hoc query. A fintech platform might serve sub-second dashboards alongside periodic reconciliation queries that scan much larger ranges of data.

### The Solution: Fallback Warehouse

After optimizing your queries, configure a fallback warehouse as a safety net for the residual outliers that can't be optimized further.

```sql
-- Interactive warehouse for fast dashboard queries
CREATE INTERACTIVE WAREHOUSE dashboard_iwh
WAREHOUSE_SIZE = 'SMALL';

-- Standard warehouse as fallback for occasional heavy queries
-- Fallback MUST be a non-interactive warehouse
CREATE WAREHOUSE fallback_wh
WAREHOUSE_SIZE = 'MEDIUM'
AUTO_SUSPEND = 60
AUTO_RESUME = TRUE;

-- Link them
ALTER WAREHOUSE dashboard_iwh SET FALLBACK_WAREHOUSE = fallback_wh;
```

When a query running on `dashboard_iwh` exceeds 5 seconds, instead of returning an error, Snowflake transparently retries that query on `fallback_wh`. The client sees a result — no error handling, no retry logic, no application changes.

### Key Constraints

- Fallback warehouse must be a **non-interactive** warehouse (standard, snowpark-optimized, etc.)
- The fallback warehouse gets its own fresh timeout budget
- Zero overhead for queries that complete within the primary 5-second timeout
- Self-reference (fallback = primary) is rejected

### Sizing the Fallback Warehouse

- Must be **equal or larger** size than the interactive warehouse (a smaller fallback would perform worse)
- Size based on the expected complexity of outlier queries
- Consider MEDIUM or LARGE for ad-hoc analytics
- Use AUTO_SUSPEND + AUTO_RESUME — the fallback only needs to be active when triggered

### Cost Considerations

- Zero cost when not triggered (no overhead for normal queries)
- Fallback warehouse only spins up when a query actually exceeds timeout
- AUTO_SUSPEND keeps idle costs minimal

### Anti-Patterns

```
❌ Don't use fallback as the primary execution path
   → If >10% of queries hit fallback, fix clustering/sizing first

❌ Don't set fallback = interactive warehouse
   → Interactive warehouses cannot be used as fallback (must be non-interactive)

❌ Don't skip query optimization because fallback exists
   → Optimize first: filtering, LIMIT, clustering, warehouse sizing
   → Fallback handles the residual outliers
```

### When to Use Fallback vs. Other Solutions

| Situation | Recommended Action |
|-----------|-------------------|
| Most queries timing out | Fix clustering or scale up warehouse |
| Queries slow (2-4s) but not timing out | Optimize clustering, add filters |
| 95%+ queries fast, 5% occasional outliers | Configure fallback warehouse |
| Ad-hoc analytics mixed with dashboards | Configure fallback warehouse |

---

## Cost Management

### Interactive Warehouse Cost Management
**Key Point**: Interactive warehouses support auto-suspend. Configure it to avoid paying for idle time.

### Cost Control Strategies

#### 1. Auto-Suspend (Recommended)
```sql
-- Configure auto-suspend (minimum 86400 seconds = 24 hours)
ALTER WAREHOUSE iwh_name SET AUTO_SUSPEND = 86400;

-- Configure auto-resume so it starts automatically on query
ALTER WAREHOUSE iwh_name SET AUTO_RESUME = TRUE;
```

#### 2. Manual Suspension
```sql
-- Suspend when not in use (e.g., overnight, weekends)
ALTER WAREHOUSE iwh_name SUSPEND;

-- Resume when needed
ALTER WAREHOUSE iwh_name RESUME;
```

#### 2. Right-Sized Warehouses
- Don't over-provision
- Start small, scale as needed
- Monitor usage patterns

#### 3. Consolidate Workloads
```sql
-- BETTER: One warehouse for multiple related tables
CREATE INTERACTIVE WAREHOUSE iwh_analytics
TABLES (sales, customers, products)
WAREHOUSE_SIZE = 'SMALL';

-- vs. multiple small warehouses
```

#### 4. Use Standard + Dynamic Pattern for Low-Frequency Queries
```sql
-- If queries are infrequent, use standard warehouse + dynamic table
-- Only pay for refreshes, not continuous running warehouse
CREATE INTERACTIVE TABLE reports
TARGET_LAG = '1 hour'
WAREHOUSE = standard_wh  -- Only runs during refresh
AS SELECT * FROM source;
```

### Cost Monitoring
```sql
-- Monitor warehouse usage
SHOW WAREHOUSES;

-- Check warehouse history (Account Usage)
SELECT 
  warehouse_name,
  start_time,
  end_time,
  credits_used
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE warehouse_name LIKE 'IWH_%'
  AND start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

---

## Data Ingestion Patterns

### Choose the Right Pattern

| Pattern | Use When | Pros | Cons |
|---------|----------|------|------|
| **Static (CTAS)** | One-time load, infrequent updates | Simple, fast initial load | Manual updates via INSERT OVERWRITE |
| **INSERT OVERWRITE** | Periodic full refreshes | Complete data replacement | Must reload all data |
| **Dynamic (TARGET_LAG)** | Source changes frequently | Auto-sync, supports DML | Refresh lag, warehouse cost |
| **Streaming** | Real-time ingestion | Near real-time data | Complex setup, external system |

### Pattern Examples

#### Static for Reference Data
```sql
-- Product catalog (changes rarely)
CREATE INTERACTIVE TABLE products
CLUSTER BY (product_id)
AS SELECT * FROM products_source;

-- Update when needed
INSERT OVERWRITE products
SELECT * FROM products_source;
```

#### Dynamic for Operational Data
```sql
-- Orders table (changes frequently, 100 GB)
-- Use LARGE standard warehouse for 100 GB table
CREATE INTERACTIVE TABLE orders
CLUSTER BY (order_id)
TARGET_LAG = '5 minutes'
WAREHOUSE = large_standard_wh  -- LARGE for 100 GB source
AS SELECT * FROM orders_source;

-- Auto-syncs every 5 minutes
```

**Standard warehouse sizing for ingestion:**
- Match warehouse size to source table size for fast loading
- < 1 GB: XSMALL, 1-10 GB: SMALL, 10-100 GB: MEDIUM, 100-500 GB: LARGE, > 500 GB: XLARGE+

#### Streaming for Real-Time Data
```sql
-- Event stream (continuous ingestion)
CREATE INTERACTIVE TABLE events
CLUSTER BY (event_id)
AS (
  SELECT 
    $1:RECORD_CONTENT.event_id,
    $1:RECORD_CONTENT.event_type,
    $1:RECORD_CONTENT.timestamp
  FROM TABLE(DATA_SOURCE(TYPE => 'STREAMING'))
);

-- Kafka connector streams data continuously
```

---

## UPDATE/DELETE Operations

### Recommended Pattern: Standard + Dynamic

#### Why This Pattern?
- Interactive tables don't support UPDATE/DELETE
- Standard tables support all DML
- Dynamic sync keeps interactive table fresh

#### Implementation
```sql
-- 1. Standard table for DML
CREATE TABLE orders_standard (
  order_id INT,
  customer_id INT,
  status VARCHAR(20),
  amount DECIMAL(10,2)
);

-- 2. Perform all DML on standard table
UPDATE orders_standard 
SET status = 'SHIPPED' 
WHERE order_id = 12345;

DELETE FROM orders_standard 
WHERE status = 'CANCELLED';

INSERT INTO orders_standard VALUES (...);

-- 3. Dynamic interactive table syncs changes
CREATE INTERACTIVE TABLE orders_interactive
CLUSTER BY (order_id)
TARGET_LAG = '1 minute'
WAREHOUSE = standard_wh
AS SELECT * FROM orders_standard;

-- 4. Query interactive table from interactive warehouse
USE WAREHOUSE iwh_name;
SELECT * FROM orders_interactive WHERE customer_id = 100;
```

#### TARGET_LAG Selection for DML
- **Frequent updates**: 1-5 minutes
- **Moderate updates**: 10-30 minutes
- **Infrequent updates**: 1 hour+

---

## Monitoring and Maintenance

### Health Checks

#### Warehouse Status
```sql
-- Check warehouse state
SHOW WAREHOUSES LIKE 'iwh_%';

-- Look for: state, size, started/suspended time
```

#### Table Association
```sql
-- Verify tables in warehouse
SHOW INTERACTIVE TABLES IN INTERACTIVE WAREHOUSE iwh_name;
```

#### Query Performance
```sql
-- Check for timeout issues
-- Monitor query execution times
-- Identify slow queries
```

### Regular Maintenance

#### Daily
- Check warehouse states (ensure running during business hours)
- Monitor query timeout rates

#### Weekly
- Review warehouse credit usage
- Analyze slow queries
- Verify dynamic table refresh performance

#### Monthly
- Assess clustering effectiveness
- Review warehouse sizing
- Optimize costs (suspend unused warehouses)

### Troubleshooting Checklist
1. ✓ Warehouse running?
2. ✓ Table associated with warehouse?
3. ✓ Clustering matches query pattern?
4. ✓ Query uses WHERE clauses on clustered columns?
5. ✓ Result set limited (LIMIT clause)?
6. ✓ Avoiding expensive operations (cartesian products, etc.)?

---

## Benchmarking Best Practices

When testing or comparing performance of interactive tables, follow these guidelines for accurate, reproducible results.

### 1. Run Multiple Iterations (5-10 minimum)

**Never trust a single query run:**
```sql
-- Disable result caching
ALTER SESSION SET USE_CACHED_RESULT = FALSE;

-- Run same query 10 times
-- Use comments to track runs
SELECT /* run_1 */ ... FROM interactive_table WHERE ...;
SELECT /* run_2 */ ... FROM interactive_table WHERE ...;
-- ... runs 3-10
```

**Why?** First runs may hit cold cache, and performance varies. Multiple runs capture typical performance.

### 2. Measure Percentiles, Not Averages

**Focus on p50 (median) and p90 (90th percentile) latency:**

```sql
-- Analyze benchmark run times
WITH benchmark_times AS (
  SELECT 
    total_elapsed_time,
    ROW_NUMBER() OVER (ORDER BY total_elapsed_time) AS rn,
    COUNT(*) OVER () AS total
  FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
  WHERE query_text LIKE '%benchmark%'
    AND start_time >= DATEADD(minute, -10, CURRENT_TIMESTAMP())
)
SELECT 
  MIN(total_elapsed_time) AS min_ms,
  MAX(CASE WHEN rn = CEIL(total * 0.50) THEN total_elapsed_time END) AS p50_ms,
  MAX(CASE WHEN rn = CEIL(total * 0.90) THEN total_elapsed_time END) AS p90_ms,
  MAX(total_elapsed_time) AS max_ms
FROM benchmark_times;
```

**p50** = typical query latency  
**p90** = worst-case for 90% of queries  
**p99** = tail latency (for very high-scale systems)

### 3. Turn Off Result Caching

**Always disable `USE_CACHED_RESULT` for benchmarks:**
```sql
ALTER SESSION SET USE_CACHED_RESULT = FALSE;
```

**Why?** Result cache makes subsequent identical queries instant, skipping table reads entirely. This hides true interactive table performance.

**Turn result cache back on in production** - caching is beneficial for real workloads.

### 4. Wait for Cache Warm-Up

**After warehouse resume or table addition, wait 5-10 minutes before benchmarking:**

```sql
-- Resume warehouse and add table
ALTER WAREHOUSE iwh_name RESUME;
ALTER WAREHOUSE iwh_name ADD TABLES (my_table);

-- ⚠️ Wait 5-10 minutes here
-- Snowflake automatically warms table data cache

-- Then start benchmarking
```

**Cache warm-up is automatic and optimized** - don't try to warm manually by running queries. Let Snowflake complete its warming process.

### 5. Don't Interleave Table Types

**Complete all interactive benchmarks, then all standard benchmarks (or vice versa):**

```sql
-- ✅ GOOD: Batch by table type
USE WAREHOUSE interactive_wh;
-- Run all 10 iterations on interactive_table_1
-- Run all 10 iterations on interactive_table_2

USE WAREHOUSE standard_wh;
-- Run all 10 iterations on standard_table_1

-- ❌ BAD: Alternating
USE WAREHOUSE interactive_wh;
SELECT ... FROM interactive_table_1;  -- Run 1
USE WAREHOUSE standard_wh;
SELECT ... FROM standard_table_1;     -- Run 1
-- Cache state constantly changes
```

### 6. Match Clustering to Query Predicates

**Ensure benchmark queries use clustered columns in WHERE clauses:**

```sql
-- Check table clustering
SHOW TABLES LIKE 'orders_interactive';
-- Clustering: customer_id, order_date

-- ✅ Good benchmark: Uses clustering
SELECT * FROM orders_interactive
WHERE customer_id = 12345 AND order_date >= '2024-01-01'
LIMIT 100;

-- ❌ Bad benchmark: Doesn't use clustering
SELECT * FROM orders_interactive
WHERE product_id = 999  -- Not in clustering key
LIMIT 100;
```

**Why?** Mis-matched clustering makes queries artificially slow and doesn't reflect optimized performance.

### 7. Test Concurrency with MAX_CONCURRENCY_LEVEL

**For short, simple queries, increase concurrency:**

```sql
-- Increase max concurrent queries
ALTER WAREHOUSE iwh_name SET MAX_CONCURRENCY_LEVEL = 16;

-- Run multiple queries simultaneously
-- Measure throughput and latency under load
```

### 8. Document Benchmark Conditions

**Record all relevant details:**
- Warehouse size (XSMALL, SMALL, etc.)
- Working data set size (portion of data typically queried)
- Total table size
- Clustering key
- Number of runs per query
- Cache state (warm vs. cold)
- Query patterns tested

### Complete Benchmark Template

```sql
-- ========================================
-- Benchmark Setup
-- ========================================
-- Table: orders_interactive
-- Size: 2.5 TB total, 700 GB working set (last 30 days)
-- Warehouse: SMALL
-- Clustering: customer_id, TO_DATE(order_date)
-- ========================================

-- 1. Disable result caching
ALTER SESSION SET USE_CACHED_RESULT = FALSE;

-- 2. Ensure warehouse is warmed (wait 10 min after resume/add)
-- (Already done - warehouse has been running for 15 minutes)

-- 3. Run test query 10 times
SELECT /* bench_run_1 */
  customer_id,
  COUNT(*) AS order_count,
  SUM(total_amount) AS total_sales
FROM orders_interactive
WHERE order_date >= CURRENT_DATE() - 30
GROUP BY customer_id
LIMIT 100;

-- ... repeat with bench_run_2 through bench_run_10

-- 4. Analyze results
WITH benchmark_times AS (
  SELECT 
    total_elapsed_time,
    ROW_NUMBER() OVER (ORDER BY total_elapsed_time) AS rn,
    COUNT(*) OVER () AS total
  FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
  WHERE query_text LIKE '%bench_run_%'
    AND warehouse_name = 'MY_SMALL_IWH'
    AND start_time >= DATEADD(minute, -5, CURRENT_TIMESTAMP())
)
SELECT 
  MIN(total_elapsed_time) AS min_ms,
  MAX(CASE WHEN rn = CEIL(total * 0.50) THEN total_elapsed_time END) AS p50_ms,
  MAX(CASE WHEN rn = CEIL(total * 0.90) THEN total_elapsed_time END) AS p90_ms,
  MAX(total_elapsed_time) AS max_ms,
  AVG(total_elapsed_time) AS avg_ms
FROM benchmark_times;

-- 5. Document results
-- p50: 850ms, p90: 1200ms, p99: 1500ms
-- Conclusion: Well within 5-second timeout, good performance
```

### When Benchmarking Shows Problems

**If p90 latency > 3 seconds:**
1. Check clustering matches query WHERE clauses
2. Verify warehouse size appropriate for working data set
3. Add LIMIT clause if result sets are large
4. Simplify query (reduce JOINs, aggregations)
5. Scale up warehouse

**If high variance (p90 >> p50):**
- May indicate cache thrashing
- Consider larger warehouse for better cache coverage
- Check for concurrent heavy queries

---

## Troubleshooting Checklist

## Quick Decision Trees

### Which Ingestion Pattern?
```
Data changes frequently (< 1 hour)?
├─ YES: Need real-time (< 1 minute)?
│   ├─ YES: Use Streaming
│   └─ NO: Use Dynamic (TARGET_LAG)
└─ NO: Changes infrequent (daily+)?
    └─ Use Static (INSERT OVERWRITE periodically)
```

### Which Warehouse Size?
```
Query complexity?
├─ Simple SELECT with WHERE?
│   └─ XSMALL
├─ Aggregations or moderate JOINs?
│   └─ SMALL
├─ Complex JOINs or high concurrency?
│   └─ MEDIUM
└─ Very complex queries or many concurrent users?
    └─ LARGE+
```

### Need UPDATE/DELETE?
```
Interactive table needs DML?
└─ YES: Use Standard + Dynamic pattern
    1. Standard table for DML
    2. Dynamic interactive table (TARGET_LAG)
    3. Query interactive table via interactive warehouse
```

---

*This document will be updated based on actual test results and observations.*
