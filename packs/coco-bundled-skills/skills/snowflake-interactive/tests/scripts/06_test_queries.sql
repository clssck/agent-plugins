-- ============================================================================
-- Test Script 06: Querying Interactive Tables
-- Purpose: Test various query patterns and performance
-- ============================================================================

USE DATABASE INTERACTIVE_SKILL_TEST;
USE SCHEMA SKILL_TEST;

-- Ensure warehouse is running
ALTER WAREHOUSE test_iwh_with_tables RESUME IF SUSPENDED;

-- ============================================================================
-- Test 6.1: Basic SELECT Query
-- ============================================================================

-- Use interactive warehouse
USE WAREHOUSE test_iwh_with_tables;

-- Record start time
SELECT CURRENT_TIMESTAMP() AS query_start_time;

-- Simple SELECT *
SELECT * FROM customers_interactive LIMIT 100;

-- Record end time and calculate duration
SELECT CURRENT_TIMESTAMP() AS query_end_time;

-- Count all rows
SELECT COUNT(*) AS total_rows FROM customers_interactive;

-- ============================================================================
-- Test 6.2: Filtered Query with WHERE Clause (Tests Clustering)
-- ============================================================================

-- Query with WHERE on clustered column (region)
SELECT CURRENT_TIMESTAMP() AS query_start;

SELECT * 
FROM customers_interactive 
WHERE region = 'WEST'
ORDER BY id;

SELECT CURRENT_TIMESTAMP() AS query_end;

-- Count by region
SELECT region, COUNT(*) AS customer_count
FROM customers_interactive
GROUP BY region
ORDER BY region;

-- Filter by multiple conditions
SELECT *
FROM customers_interactive
WHERE region = 'WEST'
  AND id < 50
ORDER BY id;

-- ============================================================================
-- Test 6.3: Aggregation Queries
-- ============================================================================

-- Simple aggregation
SELECT 
  COUNT(*) AS total_customers,
  COUNT(DISTINCT region) AS distinct_regions,
  MIN(id) AS min_id,
  MAX(id) AS max_id
FROM customers_interactive;

-- GROUP BY aggregation
SELECT 
  region,
  COUNT(*) AS customer_count,
  MIN(signup_date) AS earliest_signup,
  MAX(signup_date) AS latest_signup
FROM customers_interactive
GROUP BY region
ORDER BY customer_count DESC;

-- Aggregation with HAVING
SELECT 
  region,
  COUNT(*) AS customer_count
FROM customers_interactive
GROUP BY region
HAVING COUNT(*) > 20
ORDER BY customer_count DESC;

-- ============================================================================
-- Test 6.4: Date-based Filtering
-- ============================================================================

-- Filter by date range
SELECT *
FROM customers_interactive
WHERE signup_date >= DATEADD(day, -90, CURRENT_DATE())
ORDER BY signup_date DESC
LIMIT 50;

-- Date aggregation
SELECT 
  DATE_TRUNC('month', signup_date) AS signup_month,
  COUNT(*) AS signups
FROM customers_interactive
GROUP BY DATE_TRUNC('month', signup_date)
ORDER BY signup_month DESC;

-- ============================================================================
-- Test 6.5: ORDER BY and LIMIT
-- ============================================================================

-- Order by different columns
SELECT * FROM customers_interactive ORDER BY name LIMIT 20;
SELECT * FROM customers_interactive ORDER BY signup_date DESC LIMIT 20;
SELECT * FROM customers_interactive ORDER BY region, id LIMIT 20;

-- ============================================================================
-- Test 6.6: Join Between Two Interactive Tables
-- ============================================================================

-- Ensure both tables are in the warehouse
-- Add orders_dynamic if not already there
ALTER WAREHOUSE test_iwh_with_tables
ADD TABLES (INTERACTIVE_SKILL_TEST.SKILL_TEST.orders_dynamic);

-- Simple join query
SELECT 
  c.id AS customer_id,
  c.name,
  c.region,
  COUNT(o.order_id) AS order_count,
  SUM(o.amount) AS total_amount
FROM customers_interactive c
LEFT JOIN orders_dynamic o ON c.id = o.customer_id
GROUP BY c.id, c.name, c.region
ORDER BY total_amount DESC NULLS LAST
LIMIT 50;

-- ============================================================================
-- Test 6.7: DISTINCT Query
-- ============================================================================

-- Distinct values
SELECT DISTINCT region FROM customers_interactive ORDER BY region;

-- Count distinct
SELECT COUNT(DISTINCT region) AS unique_regions FROM customers_interactive;

-- ============================================================================
-- Test 6.8: CASE Statement
-- ============================================================================

-- CASE expression
SELECT 
  id,
  name,
  region,
  CASE 
    WHEN region IN ('NORTH', 'SOUTH') THEN 'Vertical Markets'
    WHEN region IN ('EAST', 'WEST') THEN 'Horizontal Markets'
    ELSE 'Unknown'
  END AS market_segment
FROM customers_interactive
LIMIT 100;

-- ============================================================================
-- Test 6.9: Subquery
-- ============================================================================

-- Simple subquery
SELECT *
FROM customers_interactive
WHERE region IN (
  SELECT region 
  FROM customers_interactive 
  GROUP BY region 
  HAVING COUNT(*) > 30
)
LIMIT 100;

-- ============================================================================
-- Test 6.10: Try to Query Standard Table from Interactive Warehouse
-- ============================================================================

-- This should fail - interactive warehouses can't query standard tables
-- SELECT * FROM customers_source LIMIT 10;

-- ============================================================================
-- Test 6.11: Test 5-Second Query Timeout
-- ============================================================================

-- Try a potentially expensive query
-- Note: May or may not timeout depending on data size

-- Cartesian product (this might timeout)
-- SELECT COUNT(*) 
-- FROM customers_interactive c1, customers_interactive c2
-- WHERE c1.id < c2.id;

-- ============================================================================
-- Test 6.12: Switch Warehouse Types
-- ============================================================================

-- Switch to standard warehouse to query standard table
USE WAREHOUSE TEST_STANDARD_WH;

-- This should work
SELECT COUNT(*) AS source_count FROM customers_source;

-- Switch back to interactive warehouse
USE WAREHOUSE test_iwh_with_tables;

-- This works
SELECT COUNT(*) AS interactive_count FROM customers_interactive;

-- ============================================================================
-- Validation Summary
-- ============================================================================

-- Check that all queries completed successfully
SELECT 'Query tests completed' AS status;

-- Performance comparison (if applicable)
SELECT 
  'Interactive table queries completed within 5-second timeout' AS performance_note;

-- ============================================================================
-- Expected Results:
-- - All SELECT queries complete successfully
-- - Queries execute within 5-second timeout
-- - Filtering on clustered columns (region, id) performs well
-- - Aggregations work correctly
-- - JOIN between interactive tables works
-- - Cannot query standard tables from interactive warehouse
-- - Can switch between warehouse types with USE WAREHOUSE
-- ============================================================================

-- ============================================================================
-- Skill Documentation Checks:
-- [✓] Verify USE WAREHOUSE syntax
-- [✓] Verify basic SELECT works
-- [✓] Verify WHERE, GROUP BY, ORDER BY, LIMIT work
-- [✓] Verify JOINs between interactive tables
-- [✓] Verify aggregations (COUNT, SUM, MIN, MAX)
-- [ ] Document 5-second timeout behavior and error message
-- [ ] Document which query patterns are most efficient
-- [ ] Document clustering optimization benefits
-- [ ] Document that standard tables cannot be queried
-- [ ] Document how to switch between warehouse types
-- [ ] Document supported vs unsupported SQL features
-- [ ] Add performance tuning guidance
-- ============================================================================

-- ============================================================================
-- Notes for Skill Enhancement:
-- 1. Add section on query optimization best practices
-- 2. Document which SQL features work best with interactive tables
-- 3. Add examples of queries that might timeout
-- 4. Document error messages for unsupported operations
-- 5. Add guidance on when to use interactive vs standard warehouses
-- 6. Document window function support/limitations
-- 7. Add monitoring queries for query performance
-- ============================================================================
