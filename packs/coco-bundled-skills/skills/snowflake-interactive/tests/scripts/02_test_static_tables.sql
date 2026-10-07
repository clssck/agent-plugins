-- ============================================================================
-- Test Script 02: Static Interactive Tables
-- Purpose: Test CREATE INTERACTIVE TABLE via CTAS and INSERT OVERWRITE
-- ============================================================================

USE DATABASE INTERACTIVE_SKILL_TEST;
USE SCHEMA SKILL_TEST;
USE WAREHOUSE TEST_STANDARD_WH;

-- ============================================================================
-- Test 2.1: Create Static Interactive Table via CTAS
-- ============================================================================

-- Create interactive table from source
CREATE INTERACTIVE TABLE IF NOT EXISTS customers_interactive
CLUSTER BY (id, region)
AS SELECT * FROM customers_source;

-- Verify table created
SHOW TABLES LIKE 'customers_interactive';

-- Verify data population
SELECT 'customers_interactive' AS table_name, COUNT(*) AS row_count 
FROM customers_interactive;

-- Verify data matches source
SELECT 'Source rows' AS source, COUNT(*) AS count FROM customers_source
UNION ALL
SELECT 'Interactive rows' AS source, COUNT(*) AS count FROM customers_interactive;

-- Check clustering info
SHOW TABLES LIKE 'customers_interactive';

-- Sample data preview
SELECT * FROM customers_interactive ORDER BY id LIMIT 10;

-- ============================================================================
-- Test 2.2: INSERT OVERWRITE on Static Interactive Table
-- ============================================================================

-- Record initial row count
SELECT COUNT(*) AS before_overwrite FROM customers_interactive;

-- Modify source data (add 50 more rows)
INSERT INTO customers_source
SELECT 
  100 + SEQ4() AS id,
  'NewCustomer_' || SEQ4() AS name,
  CASE MOD(SEQ4(), 4)
    WHEN 0 THEN 'NORTH'
    WHEN 1 THEN 'SOUTH'
    WHEN 2 THEN 'EAST'
    WHEN 3 THEN 'WEST'
  END AS region,
  DATEADD(day, -MOD(SEQ4(), 30), CURRENT_DATE()) AS signup_date
FROM TABLE(GENERATOR(ROWCOUNT => 50));

-- Verify source now has 150 rows
SELECT COUNT(*) AS source_count FROM customers_source;

-- Perform INSERT OVERWRITE
INSERT OVERWRITE INTO customers_interactive
SELECT * FROM customers_source;

-- Verify data replaced (should now have 150 rows)
SELECT COUNT(*) AS after_overwrite FROM customers_interactive;

-- Verify new data is present
SELECT * FROM customers_interactive WHERE id >= 100 LIMIT 10;

-- ============================================================================
-- Validation Summary
-- ============================================================================

SELECT 
  'customers_source' AS table_name,
  COUNT(*) AS row_count,
  MIN(id) AS min_id,
  MAX(id) AS max_id
FROM customers_source
UNION ALL
SELECT 
  'customers_interactive' AS table_name,
  COUNT(*) AS row_count,
  MIN(id) AS min_id,
  MAX(id) AS max_id
FROM customers_interactive;

-- ============================================================================
-- Expected Results:
-- - customers_interactive created successfully
-- - Initial row count: 100
-- - After INSERT OVERWRITE: 150 rows
-- - Data matches source table
-- ============================================================================

-- ============================================================================
-- Skill Documentation Checks:
-- [✓] Verify CTAS syntax works as documented
-- [✓] Verify IF NOT EXISTS clause handling
-- [✓] Verify CLUSTER BY syntax with multiple columns
-- [✓] Verify INSERT OVERWRITE syntax
-- [ ] Check if privilege requirements need to be documented
-- [ ] Check if performance considerations for clustering need more detail
-- ============================================================================
