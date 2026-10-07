-- ============================================================================
-- Test Script 01: Environment Setup
-- Purpose: Create database, schema, warehouse, and sample data
-- ============================================================================

-- Step 1: Create database and schema
CREATE DATABASE IF NOT EXISTS INTERACTIVE_SKILL_TEST;
USE DATABASE INTERACTIVE_SKILL_TEST;

CREATE SCHEMA IF NOT EXISTS SKILL_TEST;
USE SCHEMA SKILL_TEST;

-- Step 2: Create standard warehouse for dynamic table refreshes
CREATE WAREHOUSE IF NOT EXISTS TEST_STANDARD_WH
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = FALSE;

-- Step 3: Create sample source tables
CREATE OR REPLACE TABLE customers_source (
  id INT,
  name VARCHAR(100),
  region VARCHAR(50),
  signup_date DATE
);

CREATE OR REPLACE TABLE orders_source (
  order_id INT,
  customer_id INT,
  order_date DATE,
  amount DECIMAL(10,2),
  status VARCHAR(20)
);

-- Step 4: Insert sample data into customers_source (100 rows)
INSERT INTO customers_source
SELECT 
  SEQ4() AS id,
  'Customer_' || SEQ4() AS name,
  CASE MOD(SEQ4(), 4)
    WHEN 0 THEN 'NORTH'
    WHEN 1 THEN 'SOUTH'
    WHEN 2 THEN 'EAST'
    WHEN 3 THEN 'WEST'
  END AS region,
  DATEADD(day, -MOD(SEQ4(), 365), CURRENT_DATE()) AS signup_date
FROM TABLE(GENERATOR(ROWCOUNT => 100));

-- Step 5: Insert sample data into orders_source (500 rows)
INSERT INTO orders_source
SELECT 
  SEQ4() AS order_id,
  MOD(SEQ4(), 100) AS customer_id,
  DATEADD(day, -MOD(SEQ4(), 180), CURRENT_DATE()) AS order_date,
  ROUND(UNIFORM(10.00, 1000.00, RANDOM()), 2) AS amount,
  CASE MOD(SEQ4(), 5)
    WHEN 0 THEN 'PENDING'
    WHEN 1 THEN 'PROCESSING'
    WHEN 2 THEN 'SHIPPED'
    WHEN 3 THEN 'DELIVERED'
    WHEN 4 THEN 'CANCELLED'
  END AS status
FROM TABLE(GENERATOR(ROWCOUNT => 500));

-- ============================================================================
-- Validation Queries
-- ============================================================================

-- Verify database and schema
SHOW DATABASES LIKE 'INTERACTIVE_SKILL_TEST';
SHOW SCHEMAS IN DATABASE INTERACTIVE_SKILL_TEST;

-- Verify warehouse
SHOW WAREHOUSES LIKE 'TEST_STANDARD_WH';

-- Verify tables and row counts
SELECT 'customers_source' AS table_name, COUNT(*) AS row_count FROM customers_source
UNION ALL
SELECT 'orders_source' AS table_name, COUNT(*) AS row_count FROM orders_source;

-- Sample data preview
SELECT * FROM customers_source LIMIT 10;
SELECT * FROM orders_source LIMIT 10;

-- ============================================================================
-- Expected Results:
-- - Database INTERACTIVE_SKILL_TEST created
-- - Schema SKILL_TEST created
-- - Warehouse TEST_STANDARD_WH created and running
-- - customers_source: 100 rows
-- - orders_source: 500 rows
-- ============================================================================
