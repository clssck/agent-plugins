-- ============================================================================
-- Test Script 09: Advanced Scenarios
-- Purpose: Test complex configurations and edge cases
-- ============================================================================

USE DATABASE INTERACTIVE_SKILL_TEST;
USE SCHEMA SKILL_TEST;

-- ============================================================================
-- Test 9.1: Multiple Interactive Tables in One Warehouse
-- ============================================================================

USE WAREHOUSE TEST_STANDARD_WH;

-- Create additional interactive tables
CREATE OR REPLACE INTERACTIVE TABLE products_interactive
CLUSTER BY (product_id)
AS SELECT 
  SEQ4() AS product_id,
  'Product_' || SEQ4() AS product_name,
  ROUND(UNIFORM(5.00, 500.00, RANDOM()), 2) AS price,
  CASE MOD(SEQ4(), 4)
    WHEN 0 THEN 'Electronics'
    WHEN 1 THEN 'Clothing'
    WHEN 2 THEN 'Food'
    WHEN 3 THEN 'Books'
  END AS category
FROM TABLE(GENERATOR(ROWCOUNT => 200));

CREATE OR REPLACE INTERACTIVE TABLE transactions_interactive
CLUSTER BY (transaction_id, transaction_date)
AS SELECT 
  SEQ4() AS transaction_id,
  MOD(SEQ4(), 100) AS customer_id,
  MOD(SEQ4(), 200) AS product_id,
  DATEADD(day, -MOD(SEQ4(), 60), CURRENT_DATE()) AS transaction_date,
  ROUND(UNIFORM(10.00, 1000.00, RANDOM()), 2) AS amount
FROM TABLE(GENERATOR(ROWCOUNT => 1000));

-- Add all three tables to one warehouse
CREATE OR REPLACE INTERACTIVE WAREHOUSE test_iwh_multi
TABLES (customers_interactive, products_interactive, transactions_interactive)
WAREHOUSE_SIZE = 'XSMALL';

-- Verify all tables added:
-- Some environments do not support a dedicated SHOW command for listing
-- table associations for interactive warehouses. We validate the association
-- by successfully querying each interactive table using the warehouse below.

-- Resume warehouse
ALTER WAREHOUSE test_iwh_multi RESUME IF SUSPENDED;

-- Query each table
USE WAREHOUSE test_iwh_multi;

SELECT COUNT(*) AS customers FROM customers_interactive;
SELECT COUNT(*) AS products FROM products_interactive;
SELECT COUNT(*) AS transactions FROM transactions_interactive;

-- Query multiple tables in one query (JOIN)
SELECT 
  c.region,
  p.category,
  COUNT(*) AS transaction_count,
  SUM(t.amount) AS total_amount
FROM transactions_interactive t
JOIN customers_interactive c ON t.customer_id = c.id
JOIN products_interactive p ON t.product_id = p.product_id
GROUP BY c.region, p.category
ORDER BY total_amount DESC
LIMIT 20;

-- ============================================================================
-- Test 9.2: Complex Clustering Expressions
-- ============================================================================

USE WAREHOUSE TEST_STANDARD_WH;

-- Create table with date truncation clustering
CREATE OR REPLACE INTERACTIVE TABLE events_by_day
CLUSTER BY (TRUNC(event_timestamp, 'day'))
AS SELECT 
  SEQ4() AS event_id,
  DATEADD(hour, -MOD(SEQ4(), 720), CURRENT_TIMESTAMP()) AS event_timestamp,
  'Event_' || MOD(SEQ4(), 50) AS event_type,
  ROUND(UNIFORM(1.00, 100.00, RANDOM()), 2) AS event_value
FROM TABLE(GENERATOR(ROWCOUNT => 5000));

-- Verify clustering works
SELECT COUNT(*) FROM events_by_day;

-- Create table with multiple expression clustering
CREATE OR REPLACE INTERACTIVE TABLE events_by_month_type
CLUSTER BY (DATE_TRUNC('month', event_timestamp), event_type)
AS SELECT 
  SEQ4() AS event_id,
  DATEADD(hour, -MOD(SEQ4(), 2160), CURRENT_TIMESTAMP()) AS event_timestamp,
  CASE MOD(SEQ4(), 5)
    WHEN 0 THEN 'Click'
    WHEN 1 THEN 'View'
    WHEN 2 THEN 'Purchase'
    WHEN 3 THEN 'Search'
    WHEN 4 THEN 'Logout'
  END AS event_type
FROM TABLE(GENERATOR(ROWCOUNT => 3000));

-- Add to warehouse and query
ALTER WAREHOUSE test_iwh_multi
ADD TABLES (INTERACTIVE_SKILL_TEST.SKILL_TEST.events_by_day, INTERACTIVE_SKILL_TEST.SKILL_TEST.events_by_month_type);

USE WAREHOUSE test_iwh_multi;

-- Query with matching clustering
SELECT 
  TRUNC(event_timestamp, 'day') AS event_day,
  COUNT(*) AS event_count
FROM events_by_day
WHERE TRUNC(event_timestamp, 'day') >= DATEADD(day, -7, CURRENT_DATE())
GROUP BY TRUNC(event_timestamp, 'day')
ORDER BY event_day;

-- ============================================================================
-- Test 9.3: Dynamic Table with Aggregation
-- ============================================================================

USE WAREHOUSE TEST_STANDARD_WH;

-- Create source table
CREATE OR REPLACE TABLE sales_raw (
  sale_id INT,
  product_id INT,
  sale_date DATE,
  quantity INT,
  unit_price DECIMAL(10,2)
);

INSERT INTO sales_raw
SELECT 
  SEQ4() AS sale_id,
  MOD(SEQ4(), 50) AS product_id,
  DATEADD(day, -MOD(SEQ4(), 90), CURRENT_DATE()) AS sale_date,
  UNIFORM(1, 10, RANDOM()) AS quantity,
  ROUND(UNIFORM(5.00, 100.00, RANDOM()), 2) AS unit_price
FROM TABLE(GENERATOR(ROWCOUNT => 500));

-- Create dynamic interactive table with aggregation
CREATE OR REPLACE INTERACTIVE TABLE daily_sales_summary
CLUSTER BY (sale_date)
TARGET_LAG = '1 minute'
WAREHOUSE = TEST_STANDARD_WH
AS SELECT 
  sale_date,
  COUNT(*) AS num_sales,
  SUM(quantity) AS total_quantity,
  SUM(quantity * unit_price) AS total_revenue,
  AVG(unit_price) AS avg_price
FROM sales_raw
GROUP BY sale_date;

-- Verify aggregation
SELECT COUNT(*) AS distinct_days FROM daily_sales_summary;
SELECT * FROM daily_sales_summary ORDER BY sale_date DESC LIMIT 10;

-- ============================================================================
-- Test 9.4: Suspend and Resume with Latency Test
-- ============================================================================

USE WAREHOUSE test_iwh_multi;

-- Ensure warehouse is running
ALTER WAREHOUSE test_iwh_multi RESUME IF SUSPENDED;

-- Run a query and time it
SELECT CURRENT_TIMESTAMP() AS query_start;
SELECT COUNT(*) FROM customers_interactive;
SELECT CURRENT_TIMESTAMP() AS query_end;

-- Suspend warehouse
ALTER WAREHOUSE test_iwh_multi SUSPEND;

-- Check state
SHOW WAREHOUSES LIKE 'test_iwh_multi';

-- Resume warehouse
SELECT CURRENT_TIMESTAMP() AS resume_start;
ALTER WAREHOUSE test_iwh_multi RESUME IF SUSPENDED;

-- Immediately try to query (may have latency)
SELECT CURRENT_TIMESTAMP() AS first_query_start;
SELECT COUNT(*) FROM customers_interactive;
SELECT CURRENT_TIMESTAMP() AS first_query_end;

-- Query again (should be faster)
SELECT CURRENT_TIMESTAMP() AS second_query_start;
SELECT COUNT(*) FROM customers_interactive;
SELECT CURRENT_TIMESTAMP() AS second_query_end;

-- ============================================================================
-- Test 9.5: Large Result Set Handling
-- ============================================================================

-- Query with large result set
SELECT * 
FROM transactions_interactive 
ORDER BY transaction_id 
LIMIT 1000;

-- Aggregation on large dataset
SELECT 
  transaction_date,
  COUNT(*) AS tx_count,
  SUM(amount) AS daily_total,
  AVG(amount) AS avg_amount,
  MIN(amount) AS min_amount,
  MAX(amount) AS max_amount
FROM transactions_interactive
GROUP BY transaction_date
ORDER BY transaction_date DESC;

-- ============================================================================
-- Test 9.6: Multiple Warehouses Sharing Same Table
-- ============================================================================

USE WAREHOUSE TEST_STANDARD_WH;

-- Create another interactive warehouse
CREATE OR REPLACE INTERACTIVE WAREHOUSE test_iwh_shared
TABLES (customers_interactive)
WAREHOUSE_SIZE = 'XSMALL';

ALTER WAREHOUSE test_iwh_shared RESUME;

-- Query from first warehouse
USE WAREHOUSE test_iwh_multi;
SELECT 'Warehouse: test_iwh_multi' AS wh, COUNT(*) AS count FROM customers_interactive;

-- Query from second warehouse
USE WAREHOUSE test_iwh_shared;
SELECT 'Warehouse: test_iwh_shared' AS wh, COUNT(*) AS count FROM customers_interactive;

-- Both should work independently

-- ============================================================================
-- Test 9.7: Create Interactive Table from Complex Query
-- ============================================================================

USE WAREHOUSE TEST_STANDARD_WH;

-- Create interactive table from multi-table join
CREATE OR REPLACE INTERACTIVE TABLE customer_order_summary
CLUSTER BY (customer_id)
TARGET_LAG = '1 minute'
WAREHOUSE = TEST_STANDARD_WH
AS SELECT 
  c.id AS customer_id,
  c.name AS customer_name,
  c.region,
  COUNT(o.order_id) AS total_orders,
  SUM(o.amount) AS lifetime_value,
  AVG(o.amount) AS avg_order_value,
  MAX(o.order_date) AS last_order_date,
  MIN(o.order_date) AS first_order_date
FROM customers_source c
LEFT JOIN orders_source o ON c.id = o.customer_id
GROUP BY c.id, c.name, c.region;

-- Verify complex query result
SELECT * FROM customer_order_summary ORDER BY lifetime_value DESC NULLS LAST LIMIT 20;

-- ============================================================================
-- Test 9.8: Warehouse Sizing Impact
-- ============================================================================

-- Create larger warehouse
CREATE OR REPLACE INTERACTIVE WAREHOUSE test_iwh_medium
TABLES (transactions_interactive)
WAREHOUSE_SIZE = 'MEDIUM';

ALTER WAREHOUSE test_iwh_medium RESUME;

USE WAREHOUSE test_iwh_medium;

-- Run same query on larger warehouse
SELECT CURRENT_TIMESTAMP() AS query_start;

SELECT 
  customer_id,
  COUNT(*) AS tx_count,
  SUM(amount) AS total_spent
FROM transactions_interactive
GROUP BY customer_id
HAVING SUM(amount) > 1000
ORDER BY total_spent DESC;

SELECT CURRENT_TIMESTAMP() AS query_end;

-- Compare with XSMALL warehouse
USE WAREHOUSE test_iwh_multi;

SELECT CURRENT_TIMESTAMP() AS query_start;

SELECT 
  customer_id,
  COUNT(*) AS tx_count,
  SUM(amount) AS total_spent
FROM transactions_interactive
GROUP BY customer_id
HAVING SUM(amount) > 1000
ORDER BY total_spent DESC;

SELECT CURRENT_TIMESTAMP() AS query_end;

-- ============================================================================
-- Validation Summary
-- ============================================================================

-- List all warehouses created
SHOW WAREHOUSES LIKE 'test_iwh%';

-- List all interactive tables
SHOW TABLES LIKE '%interactive%';

-- Summary of advanced scenarios tested
SELECT 'Advanced scenarios completed successfully' AS status;

-- ============================================================================
-- Expected Results:
-- - Multiple tables can coexist in one interactive warehouse
-- - Complex joins across interactive tables work
-- - Complex clustering expressions (TRUNC, DATE_TRUNC) work
-- - Dynamic tables with aggregations work
-- - Suspend/resume shows latency on first query after resume
-- - Large result sets are handled correctly
-- - Same table can be used by multiple warehouses
-- - Interactive tables can be created from complex queries
-- - Warehouse sizing affects query performance
-- ============================================================================

-- ============================================================================
-- Skill Documentation Checks:
-- [✓] Multiple tables per warehouse
-- [✓] Complex clustering expressions
-- [✓] Dynamic tables with aggregation
-- [✓] Suspend/resume behavior
-- [ ] Document resume latency expectations
-- [ ] Document warehouse sizing guidance
-- [ ] Document complex query patterns
-- [ ] Add performance tuning section
-- [ ] Document multi-warehouse scenarios
-- [ ] Add capacity planning guidance
-- ============================================================================

-- ============================================================================
-- Notes for Skill Enhancement:
-- 1. Add performance comparison examples (XSMALL vs MEDIUM)
-- 2. Document clustering strategy selection guide
-- 3. Add capacity planning calculator/guidance
-- 4. Document when to use multiple warehouses
-- 5. Add monitoring queries for performance tracking
-- 6. Document cost implications of different configurations
-- ============================================================================
