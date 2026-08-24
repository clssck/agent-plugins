---
name: interactive-query
description: "Query patterns, JOINs, and benchmarking for Snowflake interactive tables. Triggers: query interactive, SELECT from interactive, join interactive tables, dashboard query, optimize interactive query, benchmark interactive, measure performance, compare performance, test latency."
parent_skill: snowflake-interactive
---

# Query Interactive Tables

Guidance for querying interactive tables with optimal performance.

## When to Load

Main skill routes here when user wants to:
- Query interactive tables
- JOIN multiple interactive tables
- Optimize query performance
- Understand query patterns for dashboards
- **Benchmark interactive table performance**
- **Compare interactive vs standard table latency**
- **Measure query response times**

---

## Key Rules

1. **Use interactive warehouse**: Interactive tables must be queried from an interactive warehouse
2. **5-second timeout**: Queries timeout after 5 seconds (cannot be increased)
3. **JOINs work**: Multiple interactive tables can be JOINed if all are associated with the same warehouse
4. **No standard tables**: Cannot mix interactive and standard tables in queries

---

## Workflow

### Step 1: Set Warehouse

**Always use interactive warehouse for queries:**
```sql
USE WAREHOUSE {{interactive_warehouse_name}};
```

### Step 2: Execute Minimal Task Path

**Load** [references/best-practices.md](../references/best-practices.md) for optimization tips.

For eval-style JOIN tasks, prefer the shortest successful path:
1. ensure required source interactive tables exist
2. run the JOIN query once
3. save output table exactly as requested
4. stop

Do not spend cycles on broad warehouse administration unless the user explicitly asks.

---

## Query Patterns

### Single Table Query

```sql
USE WAREHOUSE {{warehouse_name}};

SELECT {{select_columns}}
FROM {{database}}.{{schema}}.{{table_name}}
WHERE {{filter_conditions}}
ORDER BY {{order_columns}}
LIMIT {{limit}};
```

**Example:**
```sql
USE WAREHOUSE dashboard_iwh;

SELECT customer_id, order_date, total_amount, status
FROM mydb.myschema.orders_interactive
WHERE customer_id = 12345
  AND order_date >= '2024-01-01'
ORDER BY order_date DESC
LIMIT 100;
```

### Multi-Table JOIN

**Requirements:**
- ✅ All tables must be interactive tables
- ✅ All tables must be associated with the same warehouse
- ❌ Cannot JOIN with standard tables

```sql
USE WAREHOUSE {{warehouse_name}};

SELECT 
  t1.column1,
  t2.column2,
  t3.column3
FROM {{table_1}} t1
JOIN {{table_2}} t2 ON t1.key = t2.key
JOIN {{table_3}} t3 ON t2.key = t3.key
WHERE {{filter_conditions}}
LIMIT {{limit}};
```

**Example - Dashboard Query:**
```sql
USE WAREHOUSE dashboard_iwh;

SELECT 
  c.customer_name,
  c.region,
  p.product_name,
  p.category,
  o.order_date,
  o.amount
FROM orders_interactive o
JOIN customers_interactive c ON o.customer_id = c.customer_id
JOIN products_interactive p ON o.product_id = p.product_id
WHERE o.order_date >= CURRENT_DATE() - 7
ORDER BY o.order_date DESC
LIMIT 100;
```

### Aggregation Query

```sql
USE WAREHOUSE {{warehouse_name}};

SELECT 
  c.region,
  p.category,
  COUNT(DISTINCT o.order_id) AS total_orders,
  SUM(o.amount) AS total_revenue,
  AVG(o.amount) AS avg_order_value
FROM orders_interactive o
JOIN customers_interactive c ON o.customer_id = c.customer_id
JOIN products_interactive p ON o.product_id = p.product_id
WHERE o.order_date >= CURRENT_DATE() - 30
GROUP BY c.region, p.category
ORDER BY total_revenue DESC;
```

### LEFT JOIN with NULL Handling

```sql
USE WAREHOUSE {{warehouse_name}};

SELECT 
  c.customer_tier,
  c.region,
  COUNT(o.order_id) AS order_count,
  SUM(o.total_amount) AS total_revenue
FROM customers_interactive c
LEFT JOIN orders_interactive o ON c.customer_id = o.customer_id
GROUP BY c.customer_tier, c.region
ORDER BY total_revenue DESC NULLS LAST;
```

---

## Performance Optimization

### DO: Write Efficient Queries

```sql
-- ✅ GOOD: Selective WHERE on clustered columns
SELECT * 
FROM orders_interactive
WHERE customer_id = 12345  -- Uses clustering
  AND order_date >= '2024-01-01'
LIMIT 100;

-- ✅ GOOD: Aggregation with few groups
SELECT region, COUNT(*) AS order_count, SUM(amount) AS total
FROM orders_interactive
WHERE order_date >= '2024-01-01'
GROUP BY region;
```

### DON'T: Expensive Operations

```sql
-- ❌ BAD: Cartesian product
SELECT * FROM orders o1 CROSS JOIN orders o2;

-- ❌ BAD: Full table scan without WHERE
SELECT * FROM large_table;

-- ❌ BAD: Deep subqueries
SELECT * FROM orders
WHERE customer_id IN (
  SELECT customer_id FROM customers 
  WHERE region IN (SELECT region FROM regions WHERE ...)
);
```

### Optimization Checklist

- [ ] Use WHERE clause on clustered columns
- [ ] Add LIMIT for large result sets
- [ ] Filter before JOIN (reduces data volume)
- [ ] Avoid window functions (performance varies)
- [ ] Keep GROUP BY dimensions minimal

---

## Troubleshooting Query Issues

### Query Timeout (> 5 seconds)

**Solutions:**
1. Add more selective WHERE clauses
2. Add LIMIT clause
3. Simplify JOINs
4. Scale up warehouse
5. Check clustering matches query pattern

**If timeout persists → Load** [troubleshoot/SKILL.md](../troubleshoot/SKILL.md)

### "Table Not Found" in JOIN

**Cause:** Table not associated with the warehouse

**Fix (bounded retry):**
```sql
ALTER WAREHOUSE {{warehouse_name}}
ADD TABLES ({{database}}.{{schema}}.{{table_name}});
```

Then rerun the query once. If it still fails, report the blocker succinctly instead of looping through repeated warehouse diagnostics.

### Cannot Query Standard Table

**Error:** `Cannot query standard Snowflake table from interactive warehouse`

**Fix:** Switch to standard warehouse for standard tables:
```sql
USE WAREHOUSE standard_wh;
SELECT * FROM standard_table;
```

Or convert standard table to interactive if needed.

---

## Validated JOIN Patterns

These patterns have been tested on XSMALL warehouse with ~2,000 rows per table:

| Pattern | Performance | Notes |
|---------|-------------|-------|
| Two-table JOIN with WHERE | < 1 second | Most common pattern |
| Aggregation with JOIN | < 2 seconds | Use GROUP BY sparingly |
| LEFT JOIN with NULL handling | < 2 seconds | Include NULLS LAST |
| Multi-dimension aggregation | < 3 seconds | Limit GROUP BY columns |

All patterns complete within 5-second timeout.

---

## Benchmarking Interactive Queries

When measuring query performance for interactive tables, follow these best practices to get accurate, reproducible results.

### ⚠️ CRITICAL: Set Up Interactive Warehouse First

**Before ANY benchmarking**, you MUST:

1. **Create or identify an interactive warehouse**
2. **Add the interactive table to the warehouse**
3. **Wait for cache warming (5-10 minutes)**

```sql
-- Step 1: Create interactive warehouse (if needed)
CREATE WAREHOUSE IF NOT EXISTS {{benchmark_iwh}}
  WAREHOUSE_TYPE = 'INTERACTIVE'
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_RESUME = TRUE;

-- Step 2: Add the interactive table
ALTER WAREHOUSE {{benchmark_iwh}}
ADD TABLES ({{database}}.{{schema}}.{{interactive_table}});

-- Step 3: Resume warehouse
ALTER WAREHOUSE {{benchmark_iwh}} RESUME;

-- Step 4: WAIT 5-10 minutes for cache warming before benchmarking!
```

**Common Mistake**: Trying to query an interactive table with a standard warehouse will either fail or return incorrect performance metrics.

### Comparing Interactive vs Standard Tables

When benchmarking interactive tables against standard tables:

1. **⚠️ CRITICAL: Use the SAME warehouse size for fair comparison**:
   - If interactive warehouse is MEDIUM → use MEDIUM standard warehouse
   - If interactive warehouse is XSMALL → use XSMALL standard warehouse
   - Different sizes = invalid comparison (larger warehouse is always faster)

   ```sql
   -- ✅ FAIR: Same size warehouses
   -- Interactive: MEDIUM
   CREATE WAREHOUSE benchmark_iwh WAREHOUSE_TYPE='INTERACTIVE' WAREHOUSE_SIZE='MEDIUM';
   -- Standard: MEDIUM  
   CREATE WAREHOUSE benchmark_std_wh WAREHOUSE_SIZE='MEDIUM' AUTO_SUSPEND=60;
   
   -- ❌ UNFAIR: Different sizes
   -- Interactive: MEDIUM vs Standard: XSMALL = invalid comparison!
   ```

2. **Use the correct warehouse TYPE for each table**:
   - Interactive tables → Interactive warehouse
   - Standard tables → Standard warehouse

3. **Complete all runs for one table type before switching**:

```sql
-- ✅ CORRECT: Complete all interactive benchmarks first
USE WAREHOUSE {{interactive_warehouse}};
ALTER SESSION SET USE_CACHED_RESULT = FALSE;
-- Run 10 iterations on interactive table

-- Then switch to standard warehouse (SAME SIZE!)
USE WAREHOUSE {{standard_warehouse}};
ALTER SESSION SET USE_CACHED_RESULT = FALSE;
-- Run 10 iterations on standard table

-- ❌ WRONG: Alternating warehouses
-- This creates inconsistent cache states and invalid comparisons
```

4. **Use identical queries** (same columns, filters, aggregations)

### Run Multiple Iterations with Client-Side Measurement

**⚠️ CRITICAL: Always measure latency on the client side**, not from QUERY_HISTORY.

**Why client-side measurement?**
- ACCOUNT_USAGE.QUERY_HISTORY has 15-45 minute delay
- INFORMATION_SCHEMA can have data quality issues
- Client-side captures true end-to-end latency users experience

**Use Python for accurate benchmarking:**

```python
#!/usr/bin/env python3
"""
Interactive Table Benchmark Script
Measures client-side query latency for interactive vs standard tables.

Requirements:
  pip install snowflake-connector-python

Usage:
  python benchmark_interactive.py
"""

import time
import statistics
import snowflake.connector

# Connection parameters - update these
CONNECTION_PARAMS = {
    "account": "YOUR_ACCOUNT",
    "user": "YOUR_USER",
    "authenticator": "externalbrowser",  # or use password
    # "password": "YOUR_PASSWORD",
    "warehouse": "YOUR_WAREHOUSE",
    "database": "YOUR_DATABASE",
    "schema": "YOUR_SCHEMA",
}

# Benchmark configuration
NUM_ITERATIONS = 10
WARMUP_RUNS = 2  # Discard first N runs

# Define your benchmark queries
QUERIES = {
    "Q1: Filter by clustered col": """
        SELECT COUNT(*) FROM {table}
        WHERE {filter_col} = '{filter_value}'
    """,
    "Q2: Date range filter": """
        SELECT COUNT(*) FROM {table}
        WHERE {date_col} BETWEEN '{start_date}' AND '{end_date}'
    """,
    "Q3: Combined filter": """
        SELECT COUNT(*), COUNT(DISTINCT {distinct_col}) 
        FROM {table}
        WHERE {filter_col} = '{filter_value}'
          AND {date_col} BETWEEN '{start_date}' AND '{end_date}'
    """,
    "Q4: Aggregation": """
        SELECT {group_col}, COUNT(*) AS cnt
        FROM {table}
        WHERE {date_col} BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY {group_col}
        ORDER BY cnt DESC
        LIMIT 10
    """,
}

def measure_query(cursor, query: str, iterations: int = NUM_ITERATIONS) -> dict:
    """Run query multiple times and return latency statistics."""
    latencies = []
    
    for i in range(iterations):
        start = time.perf_counter()
        cursor.execute(query)
        _ = cursor.fetchall()  # Ensure full result is fetched
        end = time.perf_counter()
        
        latency_ms = (end - start) * 1000
        latencies.append(latency_ms)
        print(f"  Run {i+1}: {latency_ms:.1f} ms")
    
    # Discard warmup runs
    latencies = latencies[WARMUP_RUNS:]
    latencies_sorted = sorted(latencies)
    n = len(latencies_sorted)
    
    return {
        "min": min(latencies),
        "max": max(latencies),
        "avg": statistics.mean(latencies),
        "p50": latencies_sorted[int(n * 0.50)],
        "p90": latencies_sorted[int(n * 0.90)] if n >= 10 else latencies_sorted[-1],
        "p99": latencies_sorted[int(n * 0.99)] if n >= 100 else latencies_sorted[-1],
    }

def run_benchmark(interactive_table: str, standard_table: str, query_params: dict):
    """Run full benchmark comparing interactive vs standard table."""
    
    results = {}
    
    # Connect and disable result caching
    conn = snowflake.connector.connect(**CONNECTION_PARAMS)
    cursor = conn.cursor()
    cursor.execute("ALTER SESSION SET USE_CACHED_RESULT = FALSE")
    
    # ⚠️ CRITICAL: Verify warehouse sizes match for fair comparison
    cursor.execute(f"SHOW WAREHOUSES LIKE '{query_params['interactive_warehouse']}'")
    iwh_info = cursor.fetchone()
    cursor.execute(f"SHOW WAREHOUSES LIKE '{query_params['standard_warehouse']}'")
    swh_info = cursor.fetchone()
    
    # Size is typically column index 3
    iwh_size = iwh_info[3] if iwh_info else "UNKNOWN"
    swh_size = swh_info[3] if swh_info else "UNKNOWN"
    
    print(f"\nWarehouse sizes:")
    print(f"  Interactive: {query_params['interactive_warehouse']} = {iwh_size}")
    print(f"  Standard:    {query_params['standard_warehouse']} = {swh_size}")
    
    if iwh_size != swh_size:
        print(f"\n⚠️  WARNING: Warehouse sizes don't match!")
        print(f"    This is NOT a fair comparison. Results will be skewed.")
        print(f"    Create a standard warehouse with size={iwh_size} for valid comparison.")
        response = input("\nContinue anyway? (y/N): ")
        if response.lower() != 'y':
            print("Benchmark cancelled.")
            return {}
    
    try:
        for query_name, query_template in QUERIES.items():
            print(f"\n{'='*60}")
            print(f"Running: {query_name}")
            print('='*60)
            
            # Benchmark interactive table (use interactive warehouse)
            print(f"\n[INTERACTIVE TABLE] - {interactive_table}")
            cursor.execute(f"USE WAREHOUSE {query_params['interactive_warehouse']}")
            query = query_template.format(table=interactive_table, **query_params)
            interactive_stats = measure_query(cursor, query)
            
            # Benchmark standard table (use standard warehouse)
            print(f"\n[STANDARD TABLE] - {standard_table}")
            cursor.execute(f"USE WAREHOUSE {query_params['standard_warehouse']}")
            query = query_template.format(table=standard_table, **query_params)
            standard_stats = measure_query(cursor, query)
            
            # Calculate speedup
            speedup = standard_stats['p50'] / interactive_stats['p50']
            
            results[query_name] = {
                "interactive": interactive_stats,
                "standard": standard_stats,
                "speedup": speedup,
            }
            
            print(f"\n  Summary:")
            print(f"    Interactive p50: {interactive_stats['p50']:.1f} ms")
            print(f"    Standard p50:    {standard_stats['p50']:.1f} ms")
            print(f"    Speedup:         {speedup:.1f}x faster")
    
    finally:
        cursor.close()
        conn.close()
    
    return results

def print_results_table(results: dict):
    """Print results in a formatted table."""
    print("\n" + "="*80)
    print("BENCHMARK RESULTS SUMMARY")
    print("="*80)
    print(f"{'Query':<30} {'Interactive p50':<18} {'Standard p50':<18} {'Speedup':<12}")
    print("-"*80)
    
    for query_name, data in results.items():
        int_p50 = f"{data['interactive']['p50']:.1f} ms"
        std_p50 = f"{data['standard']['p50']:.1f} ms"
        speedup = f"{data['speedup']:.1f}x"
        print(f"{query_name:<30} {int_p50:<18} {std_p50:<18} {speedup:<12}")
    
    print("="*80)

if __name__ == "__main__":
    # Configure your benchmark parameters
    query_params = {
        "interactive_warehouse": "MY_INTERACTIVE_WH",
        "standard_warehouse": "MY_STANDARD_WH",
        "filter_col": "category",
        "filter_value": "electronics",
        "date_col": "created_at",
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
        "distinct_col": "user_id",
        "group_col": "category",
    }
    
    results = run_benchmark(
        interactive_table="mydb.myschema.orders_interactive",
        standard_table="mydb.myschema.orders",
        query_params=query_params
    )
    
    print_results_table(results)
```

**Quick benchmark without script** (less accurate but faster):

```python
# Quick inline benchmark in Python REPL or notebook
import time
import snowflake.connector

conn = snowflake.connector.connect(
    account="YOUR_ACCOUNT",
    user="YOUR_USER", 
    authenticator="externalbrowser"
)
cur = conn.cursor()
cur.execute("ALTER SESSION SET USE_CACHED_RESULT = FALSE")

# Switch to interactive warehouse
cur.execute("USE WAREHOUSE MY_INTERACTIVE_WH")

# Measure query
query = "SELECT COUNT(*) FROM my_interactive_table WHERE col = 'value'"
latencies = []
for i in range(10):
    start = time.perf_counter()
    cur.execute(query)
    cur.fetchall()
    latencies.append((time.perf_counter() - start) * 1000)
    print(f"Run {i+1}: {latencies[-1]:.1f} ms")

print(f"\np50: {sorted(latencies)[5]:.1f} ms")
print(f"avg: {sum(latencies)/len(latencies):.1f} ms")
```

### Measure p50 and p90 Latency

**Always report percentiles**, not just averages:

| Metric | What it tells you |
|--------|-------------------|
| p50 (median) | Typical user experience |
| p90 | Worst case for most users |
| p99 | Tail latency (important for SLAs) |
| avg | Can be skewed by outliers - use with caution |

**Optional: SQL-based historical analysis** (use only for post-hoc analysis, not real-time benchmarking):

```sql
-- ⚠️ WARNING: ACCOUNT_USAGE has 15-45 min delay
-- Only use for historical analysis, not live benchmarking
SELECT 
  query_id,
  total_elapsed_time AS latency_ms,
  start_time
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE warehouse_name = '{{warehouse}}'
  AND query_text LIKE '%{{query_tag}}%'
  AND start_time >= DATEADD(hour, -24, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

### Cache Warming

**Wait for cache warm-up** after warehouse resume or table addition:

```sql
-- Resume warehouse
ALTER WAREHOUSE iwh_name RESUME;

-- Add tables
ALTER WAREHOUSE iwh_name ADD TABLES (my_table);

-- ⚠️ WAIT 5-10 minutes before benchmarking
-- Snowflake warms cache automatically
-- Running queries immediately will show cold-cache performance
```

**Cache warm-up time depends on:**
- Warehouse size (larger = faster warm-up)
- Table size (larger = longer warm-up)
- Working data set size

**Don't warm cache manually** by running sample queries - let Snowflake's auto-warming complete.

### Don't Interleave Table Types

**Run all benchmarks on interactive tables first**, then standard tables (or vice versa):

```sql
-- ✅ GOOD: Complete interactive benchmarks first
USE WAREHOUSE interactive_wh;
-- Run all interactive table benchmarks (10 iterations each)

-- Then switch to standard
USE WAREHOUSE standard_wh;
-- Run all standard table benchmarks (10 iterations each)

-- ❌ BAD: Alternating between types
USE WAREHOUSE interactive_wh;
SELECT ... FROM interactive_table;  -- Run 1
USE WAREHOUSE standard_wh;
SELECT ... FROM standard_table;     -- Run 1
USE WAREHOUSE interactive_wh;
SELECT ... FROM interactive_table;  -- Run 2
-- Creates inconsistent cache states
```

### Match Clustering to Query Predicates

**Ensure clustering columns match WHERE clauses** in benchmarks:

```sql
-- If table is clustered by customer_id and order_date
SHOW TABLES LIKE 'orders_interactive';
-- Check cluster_by column

-- ✅ Benchmark query should use these columns
SELECT * FROM orders_interactive
WHERE customer_id = 12345           -- Uses clustering
  AND order_date >= '2024-01-01'    -- Uses clustering
LIMIT 100;

-- ❌ Don't benchmark on non-clustered columns
SELECT * FROM orders_interactive
WHERE product_id = 999              -- Not in clustering key
LIMIT 100;
```

### Optimize Concurrency Settings

For short, simple queries with high concurrency needs:

```sql
-- Increase max concurrency level
ALTER WAREHOUSE iwh_name SET MAX_CONCURRENCY_LEVEL = 16;

-- Benchmark with concurrent queries
-- Run multiple queries simultaneously to test concurrency
```

### Benchmarking Checklist

Before running benchmarks:

- [ ] **Use Python client for measurement** (NOT QUERY_HISTORY - it has delays!)
- [ ] **Interactive warehouse created and table added** (CRITICAL!)
- [ ] **Warehouse sizes MUST match** (MEDIUM interactive → MEDIUM standard)
- [ ] **Waited 5-10 minutes for cache warming**
- [ ] Turn off `USE_CACHED_RESULT` in session
- [ ] Plan to run each query 10+ times (discard first 2 warmup runs)
- [ ] Clustering columns match query WHERE clauses
- [ ] Will measure p50, p90, p99 latency (not just average)
- [ ] Won't interleave interactive and standard table queries
- [ ] Using interactive warehouse for interactive tables, standard for standard tables

**Quick setup:**
```bash
pip install snowflake-connector-python
```

---

## Stopping Points Summary

This skill provides **query guidance only** (read-only). No approval needed for SELECT queries.

- **SELECT queries**: Execute freely - no approval needed
- **If mutations are needed**: → Load appropriate sub-skill (update-delete, create)

---

## Output

- Query executed successfully
- Results returned within timeout
- Performance recommendations provided if needed
