# Materialized Views, Temporary Tables/Views, and Pipe Syntax

## 1. Materialized Views (MVs)

### Overview

MVs are Unity Catalog-managed tables storing precomputed query results as Delta tables. Unlike standard views, MVs cache results and update automatically.

- **Pre-computed storage**: Reduces query latency
- **Automatic updates**: Via schedule, trigger, or manual refresh
- **Serverless pipelines**: Each MV auto-creates a serverless pipeline
- **Incremental refresh**: Computes only changed data when possible

### Requirements

- Unity Catalog-enabled **Serverless** SQL warehouse
- Permissions: `SELECT` on base tables, `USE CATALOG`, `USE SCHEMA`, `CREATE TABLE`, `CREATE MATERIALIZED VIEW`
- Refresh: Ownership or `REFRESH` privilege
- Query: `SELECT` on the MV

### CREATE MATERIALIZED VIEW

```sql
{ CREATE OR REPLACE MATERIALIZED VIEW | CREATE MATERIALIZED VIEW [ IF NOT EXISTS ] }
  <view_name>
  [ column_list ]
  [ view_clauses ]
  AS <query>
```

**View clauses (optional):**
- `PARTITIONED BY (<col1>, <col2>)`
- `CLUSTER BY (<col1>, <col2>)` or `CLUSTER BY AUTO` (cannot combine with PARTITIONED BY)
- `COMMENT '<description>'`
- `TBLPROPERTIES ('<key>' = '<value>')`
- `WITH ROW FILTER <func> ON (<col1>, <col2>)` — row-level security
- `MASK <func>` on columns — column-level masking
- `SCHEDULE` clause — automatic refresh
- `TRIGGER ON UPDATE` clause — event-driven refresh

### Basic Examples

```sql
-- Simple MV with aggregation
CREATE MATERIALIZED VIEW catalog.schema.daily_sales
  COMMENT 'Daily sales aggregations'
AS SELECT
    date, region,
    SUM(sales) AS total_sales,
    COUNT(*) AS num_transactions
FROM catalog.schema.raw_sales
GROUP BY date, region;

-- MV with constraints and auto-clustering
CREATE MATERIALIZED VIEW catalog.schema.customer_orders (
  customer_id INT NOT NULL,
  full_name STRING,
  order_count BIGINT,
  CONSTRAINT customer_pk PRIMARY KEY (customer_id)
)
CLUSTER BY AUTO
AS SELECT
    c.customer_id, c.full_name,
    COUNT(o.order_id) AS order_count
FROM catalog.schema.customers c
JOIN catalog.schema.orders o ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.full_name;
```

### Refresh Strategies

#### 1. Manual Refresh

```sql
-- Synchronous (blocks until complete)
REFRESH MATERIALIZED VIEW catalog.schema.daily_sales;

-- Asynchronous (returns immediately)
REFRESH MATERIALIZED VIEW catalog.schema.daily_sales ASYNC;
```

#### 2. Scheduled Refresh

```sql
-- Interval-based (1-72 hours, 1-31 days, 1-8 weeks)
CREATE OR REPLACE MATERIALIZED VIEW catalog.schema.hourly_metrics
  SCHEDULE EVERY 1 HOUR
AS SELECT date_trunc('hour', event_time) AS hour, COUNT(*) AS events
FROM catalog.schema.raw_events
GROUP BY 1;

-- Cron-based
CREATE OR REPLACE MATERIALIZED VIEW catalog.schema.nightly_report
  SCHEDULE CRON '0 0 2 * * ?' AT TIME ZONE 'America/New_York'
AS SELECT * FROM catalog.schema.daily_aggregates;
```

A Databricks Job is automatically created for scheduled refreshes.

#### 3. Event-Driven (TRIGGER ON UPDATE)

```sql
-- Auto-refresh when upstream data changes
CREATE OR REPLACE MATERIALIZED VIEW catalog.schema.customer_orders
  TRIGGER ON UPDATE
AS SELECT c.customer_id, c.name, COUNT(o.order_id) AS order_count
FROM catalog.schema.customers c
JOIN catalog.schema.orders o ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.name;

-- With throttle to avoid excessive refreshes
CREATE OR REPLACE MATERIALIZED VIEW catalog.schema.customer_orders
  TRIGGER ON UPDATE AT MOST EVERY INTERVAL 5 MINUTES
AS SELECT ...;
```

**Trigger limits:**
- Max **10 upstream source tables**, **30 upstream views**
- Min **1-minute** interval (default)
- Max **1,000** trigger-based MVs per workspace
- Supports Delta tables, managed views, streaming tables
- Does **not** support Delta Sharing shared tables

#### 4. Job-Based Orchestration

```sql
-- In a Databricks Job SQL task
REFRESH MATERIALIZED VIEW catalog.schema.daily_sales_summary;
```

### Managing Schedules After Creation

```sql
ALTER MATERIALIZED VIEW catalog.schema.my_mv ADD SCHEDULE EVERY 4 HOURS;
ALTER MATERIALIZED VIEW catalog.schema.my_mv ADD TRIGGER ON UPDATE;
ALTER MATERIALIZED VIEW catalog.schema.my_mv ALTER SCHEDULE EVERY 2 HOURS;
ALTER MATERIALIZED VIEW catalog.schema.my_mv DROP SCHEDULE;
```

### Incremental vs Full Refresh

| Aspect | Incremental | Full |
|--------|-------------|------|
| What it does | Merges only new/modified records | Re-executes entire defining query |
| When used | Delta sources with row tracking + CDF | When incremental not possible |
| Cost | Lower (processes deltas only) | Higher (recomputes everything) |

Enable row tracking for incremental refresh:

```sql
ALTER TABLE catalog.schema.source_table
SET TBLPROPERTIES (delta.enableRowTracking = true);
```

Use `EXPLAIN CREATE MATERIALIZED VIEW` to verify the chosen refresh type.

### Timeout Configuration

```sql
SET STATEMENT_TIMEOUT = '6h';
CREATE OR REPLACE MATERIALIZED VIEW catalog.schema.my_mv
  SCHEDULE EVERY 12 HOURS
AS SELECT * FROM catalog.schema.large_source_table;
```

Default timeout: **2 days**.

### Monitoring

- **Catalog Explorer**: Refresh status, schema, permissions, lineage
- **DESCRIBE EXTENDED**: Schedule and configuration details
- **DESCRIBE EXTENDED AS JSON**: Refresh time, type, status, schedule
- **Jobs & Pipelines UI**: Auto-created pipeline status
- **Pipelines API**: `GET /api/2.0/pipelines/<pipeline_id>`

### DBSQL MVs vs Pipeline (DLT) MVs

| Aspect | DBSQL MVs | Pipeline (DLT) MVs |
|--------|-----------|---------------------|
| Creation | `CREATE MATERIALIZED VIEW` in SQL warehouse | Defined in pipeline source code |
| Pipeline | Auto-created serverless | User-defined, full lifecycle control |
| Refresh trigger | Schedule, trigger-on-update, manual, job | Pipeline update (manual/scheduled) |
| Private MVs | Not supported | `PRIVATE` keyword supported |
| Data quality | Not supported | Expectations supported |
| Best for | Standalone MVs, BI acceleration | Complex multi-table pipelines |

### Key Limitations

- No identity columns or surrogate keys
- No CDF reads, time travel, `OPTIMIZE`, or `VACUUM` (managed automatically)
- `SUM()` on nullable column returns **0** instead of `NULL` when all non-null values removed
- Cannot rename or change owner (must drop and recreate)
- Non-column expressions require explicit aliases

### Best Practices

1. **Choose the right refresh**: `TRIGGER ON UPDATE` for near-real-time; `SCHEDULE` for predictable cadences; manual/job for complex orchestration
2. **Enable row tracking** on Delta sources for incremental refresh
3. **Use async refreshes** when downstream queries can tolerate slight staleness
4. **Set explicit timeouts** for long-running refreshes
5. **Use Liquid Clustering** (`CLUSTER BY AUTO` or explicit columns) instead of `PARTITIONED BY` for new MVs

---

## 2. Temporary Tables and Views

### Session-Scoped Temporary Views

```sql
-- Visible only within the current session
CREATE TEMPORARY VIEW temp_active_customers AS
SELECT * FROM catalog.schema.customers WHERE status = 'active';

-- Use in subsequent queries
SELECT * FROM temp_active_customers WHERE region = 'US';
```

- Dropped automatically when session ends
- Not registered in Unity Catalog
- Visible only to the creating session

### Session-Scoped Temporary Tables

```sql
CREATE TEMPORARY TABLE temp_staging (
  id INT,
  name STRING,
  processed BOOLEAN DEFAULT false
);

INSERT INTO temp_staging
SELECT id, name, false FROM catalog.schema.raw_data WHERE batch_id = 42;
```

### Global Temporary Views

```sql
-- Visible across sessions within the same cluster/warehouse
CREATE GLOBAL TEMPORARY VIEW global_temp.shared_metrics AS
SELECT region, SUM(revenue) AS total FROM catalog.schema.sales GROUP BY region;

-- Access via global_temp schema
SELECT * FROM global_temp.shared_metrics;
```

### When to Use Each

| Type | Scope | Persisted | UC Registered | Use Case |
|------|-------|-----------|---------------|----------|
| Temporary View | Session | No | No | Ad-hoc analysis, intermediate CTEs |
| Temporary Table | Session | No | No | Staging data, iterative processing |
| Global Temp View | Cluster | No | No | Shared intermediate results |
| Materialized View | Permanent | Yes | Yes | BI dashboards, repeated aggregations |

---

## 3. Pipe Syntax (`|>` Operator)

### Overview

Pipe syntax (DBR 16.1+) provides a left-to-right, top-to-bottom query flow. Each pipe stage takes the previous result as input.

### Basic Syntax

```sql
FROM <table_or_query>
  |> <operation>
  |> <operation>
  |> ...;
```

### Supported Operations

| Operation | Pipe Syntax | Traditional Equivalent |
|-----------|-------------|----------------------|
| Filter | `\|> WHERE condition` | `WHERE condition` |
| Project | `\|> SELECT col1, col2` | `SELECT col1, col2` |
| Aggregate | `\|> AGGREGATE agg_expr GROUP BY col` | `GROUP BY col` with aggregation |
| Sort | `\|> ORDER BY col` | `ORDER BY col` |
| Limit | `\|> LIMIT n` | `LIMIT n` |
| Extend | `\|> EXTEND expr AS alias` | Add computed column |
| Drop | `\|> DROP col1, col2` | Remove columns |
| Rename | `\|> RENAME old_name AS new_name` | Rename columns |
| Set ops | `\|> UNION ALL` / `INTERSECT` / `EXCEPT` | Set operations |
| Join | `\|> JOIN table ON condition` | `JOIN` |
| Distinct | `\|> SELECT DISTINCT col` | `SELECT DISTINCT` |
| Window | `\|> EXTEND window_func OVER (...) AS alias` | Window function |
| Tablesample | `\|> TABLESAMPLE (n PERCENT)` | `TABLESAMPLE` |
| Pivot/Unpivot | `\|> PIVOT (...)` | `PIVOT` |

### Examples

#### Basic Filtering and Aggregation

```sql
FROM catalog.schema.fact_orders
  |> WHERE order_date >= current_date() - INTERVAL 30 DAYS
  |> AGGREGATE SUM(amount) AS total, COUNT(*) AS cnt GROUP BY region
  |> WHERE total > 10000
  |> ORDER BY total DESC
  |> LIMIT 20;
```

#### Multi-Step Transformation

```sql
FROM catalog.schema.raw_events
  |> WHERE event_type = 'purchase'
  |> EXTEND date_trunc('day', event_time) AS event_day
  |> AGGREGATE
      COUNT(*) AS purchase_count,
      SUM(amount) AS daily_revenue
    GROUP BY event_day
  |> EXTEND daily_revenue / purchase_count AS avg_order_value
  |> ORDER BY event_day DESC;
```

#### Joins in Pipe Syntax

```sql
FROM catalog.schema.orders
  |> JOIN catalog.schema.customers ON orders.customer_id = customers.id
  |> WHERE customers.region = 'EMEA'
  |> AGGREGATE SUM(orders.amount) AS total_spend GROUP BY customers.name
  |> ORDER BY total_spend DESC
  |> LIMIT 10;
```

#### Window Functions

```sql
FROM catalog.schema.monthly_sales
  |> EXTEND
      ROW_NUMBER() OVER (PARTITION BY region ORDER BY revenue DESC) AS rank
  |> WHERE rank <= 3;
```

#### Subqueries and CTEs with Pipes

```sql
WITH active_customers AS (
  FROM catalog.schema.customers
    |> WHERE status = 'active'
    |> WHERE last_order_date >= current_date() - INTERVAL 90 DAYS
)
FROM active_customers
  |> JOIN catalog.schema.orders ON active_customers.id = orders.customer_id
  |> AGGREGATE COUNT(*) AS order_count GROUP BY active_customers.id, active_customers.name
  |> ORDER BY order_count DESC;
```

### Pipe Syntax vs Traditional SQL

**Traditional:**
```sql
SELECT region, SUM(amount) AS total
FROM catalog.schema.orders
WHERE order_date >= '2024-01-01'
GROUP BY region
HAVING SUM(amount) > 10000
ORDER BY total DESC
LIMIT 10;
```

**Pipe syntax:**
```sql
FROM catalog.schema.orders
  |> WHERE order_date >= '2024-01-01'
  |> AGGREGATE SUM(amount) AS total GROUP BY region
  |> WHERE total > 10000
  |> ORDER BY total DESC
  |> LIMIT 10;
```

Key differences:
- Starts with `FROM` instead of `SELECT`
- `HAVING` replaced by `|> WHERE` after `|> AGGREGATE`
- `AGGREGATE` replaces `SELECT ... GROUP BY`
- `EXTEND` adds columns without replacing existing ones
- Reads top-to-bottom in execution order

### Pipe Syntax Rules

1. Query **must** start with `FROM` or a CTE (`WITH`)
2. Each `|>` stage takes previous result as input
3. `AGGREGATE` replaces both `SELECT` aggregates and `GROUP BY`
4. `EXTEND` adds columns; `SELECT` replaces all columns
5. `WHERE` after `AGGREGATE` acts like `HAVING`
6. Column references are unambiguous — no need for table qualifiers in later stages
7. Requires **DBR 16.1+**

### Best Practices

1. **Use for complex multi-step queries** — pipe syntax shines when there are many sequential transformations
2. **Keep each stage focused** — one logical operation per `|>` stage
3. **Filter early** — push `WHERE` stages as early as possible
4. **Use `EXTEND` for computed columns** — cleaner than rewriting the entire SELECT list
5. **Combine with CTEs** — use `WITH` for named intermediate datasets, then pipe for transformations
