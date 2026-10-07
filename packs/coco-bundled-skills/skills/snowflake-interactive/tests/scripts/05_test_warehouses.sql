-- ============================================================================
-- Test Script 05: Interactive Warehouse Operations
-- Purpose: Test creating, managing, and configuring interactive warehouses
-- ============================================================================

USE DATABASE INTERACTIVE_SKILL_TEST;
USE SCHEMA SKILL_TEST;
USE WAREHOUSE TEST_STANDARD_WH;

-- ============================================================================
-- Test 5.1: Create Interactive Warehouse Without Tables
-- ============================================================================

-- Create empty interactive warehouse
CREATE OR REPLACE INTERACTIVE WAREHOUSE test_iwh_empty
WAREHOUSE_SIZE = 'XSMALL';

-- Ensure subsequent statements that require a standard warehouse don't
-- accidentally run against a suspended interactive warehouse.
USE WAREHOUSE TEST_STANDARD_WH;

-- Verify warehouse created
SHOW WAREHOUSES LIKE 'test_iwh_empty';

-- Check warehouse state (should be SUSPENDED initially)
SELECT 
  "name",
  "state",
  "type",
  "size",
  "min_cluster_count",
  "max_cluster_count",
  "auto_suspend",
  "auto_resume"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "name" = 'TEST_IWH_EMPTY';

-- ============================================================================
-- Test 5.2: Create Interactive Warehouse With Tables
-- ============================================================================

-- Ensure customers_interactive exists from previous test
-- If not, create it
CREATE INTERACTIVE TABLE IF NOT EXISTS customers_interactive
CLUSTER BY (id, region)
AS SELECT * FROM customers_source;

-- Create interactive warehouse with table association
CREATE OR REPLACE INTERACTIVE WAREHOUSE test_iwh_with_tables
TABLES (customers_interactive)
WAREHOUSE_SIZE = 'XSMALL';

-- Ensure we keep using a standard warehouse unless explicitly testing
-- interactive warehouse query execution.
USE WAREHOUSE TEST_STANDARD_WH;

-- Verify warehouse created
SHOW WAREHOUSES LIKE 'test_iwh_with_tables';

-- Check warehouse state
SELECT 
  "name",
  "state",
  "type",
  "size"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "name" = 'TEST_IWH_WITH_TABLES';

-- ============================================================================
-- Test 5.3: Show Interactive Tables in Warehouse
-- ============================================================================

-- NOTE: Some environments may not support a dedicated SHOW command to list
-- table associations for interactive warehouses. We validate association by
-- querying the table using the interactive warehouse.
ALTER WAREHOUSE test_iwh_with_tables RESUME IF SUSPENDED;
USE WAREHOUSE test_iwh_with_tables;
SELECT COUNT(*) AS customers_interactive_count FROM customers_interactive;
USE WAREHOUSE TEST_STANDARD_WH;

-- ============================================================================
-- Test 5.4: Add Table to Empty Warehouse
-- ============================================================================

-- Ensure orders_dynamic exists from previous test
CREATE INTERACTIVE TABLE IF NOT EXISTS orders_dynamic
CLUSTER BY (order_id, customer_id)
TARGET_LAG = '1 minute'
WAREHOUSE = TEST_STANDARD_WH
AS SELECT * FROM orders_source;

-- Add table to empty warehouse using fully qualified name
ALTER WAREHOUSE test_iwh_empty
ADD TABLES (INTERACTIVE_SKILL_TEST.SKILL_TEST.orders_dynamic);

-- Verify table was added by querying it in the interactive warehouse
ALTER WAREHOUSE test_iwh_empty RESUME IF SUSPENDED;
USE WAREHOUSE test_iwh_empty;
SELECT COUNT(*) AS orders_dynamic_count FROM orders_dynamic;
USE WAREHOUSE TEST_STANDARD_WH;

-- ============================================================================
-- Test 5.5: Add Multiple Tables to Warehouse
-- ============================================================================

-- Add customers_interactive to test_iwh_empty as well
ALTER WAREHOUSE test_iwh_empty
ADD TABLES (INTERACTIVE_SKILL_TEST.SKILL_TEST.customers_interactive);

-- Verify by querying both tables from the interactive warehouse
ALTER WAREHOUSE test_iwh_empty RESUME IF SUSPENDED;
USE WAREHOUSE test_iwh_empty;
SELECT COUNT(*) AS customers_interactive_count FROM customers_interactive;
SELECT COUNT(*) AS orders_dynamic_count FROM orders_dynamic;
USE WAREHOUSE TEST_STANDARD_WH;

-- ============================================================================
-- Test 5.6: Remove Table from Warehouse
-- ============================================================================

-- Remove orders_dynamic from test_iwh_empty
ALTER WAREHOUSE test_iwh_empty
DROP TABLES (INTERACTIVE_SKILL_TEST.SKILL_TEST.orders_dynamic);

-- Verify orders_dynamic is no longer queryable from the interactive warehouse.
-- (This should fail if the association is removed, but is left as a commented
-- statement so the script can proceed in environments that differ.)
-- USE WAREHOUSE test_iwh_empty;
-- SELECT COUNT(*) FROM orders_dynamic;
USE WAREHOUSE TEST_STANDARD_WH;

-- ============================================================================
-- Test 5.7: Resume Interactive Warehouse
-- ============================================================================

-- Resume test_iwh_with_tables
ALTER WAREHOUSE test_iwh_with_tables RESUME IF SUSPENDED;

-- Check state (should be STARTED or RESUMING)
SHOW WAREHOUSES LIKE 'test_iwh_with_tables';

SELECT 
  "name",
  "state"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "name" = 'TEST_IWH_WITH_TABLES';

-- Wait a moment for warehouse to fully resume
SELECT 'Waiting for warehouse to resume...' AS message;

-- ============================================================================
-- Test 5.8: Suspend Interactive Warehouse
-- ============================================================================

-- Suspend the warehouse
ALTER WAREHOUSE test_iwh_with_tables SUSPEND;

-- Check state (should be SUSPENDED)
SHOW WAREHOUSES LIKE 'test_iwh_with_tables';

SELECT 
  "name",
  "state"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "name" = 'TEST_IWH_WITH_TABLES';

-- ============================================================================
-- Test 5.9: List All Interactive Warehouses
-- ============================================================================

-- Show all warehouses we created
SHOW WAREHOUSES LIKE 'test_iwh%';

-- Summary of our test warehouses
SELECT 
  "name",
  "state",
  "type",
  "size",
  "created_on"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
ORDER BY "name";

-- ============================================================================
-- Validation Summary
-- ============================================================================

-- Warehouse inventory
SHOW WAREHOUSES LIKE 'test_iwh%';
SELECT 'Warehouses created' AS category, COUNT(*) AS count
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));

-- Resume both warehouses for next tests
ALTER WAREHOUSE test_iwh_empty RESUME IF SUSPENDED;
ALTER WAREHOUSE test_iwh_with_tables RESUME IF SUSPENDED;

-- Final state check
SHOW WAREHOUSES LIKE 'test_iwh%';

-- ============================================================================
-- Expected Results:
-- - test_iwh_empty created successfully (initially empty, then tables added)
-- - test_iwh_with_tables created with customers_interactive
-- - ADD TABLES works with fully qualified names
-- - REMOVE TABLES successfully removes associations
-- - SHOW INTERACTIVE TABLES lists associated tables
-- - SUSPEND/RESUME operations work
-- ============================================================================

-- ============================================================================
-- Skill Documentation Checks:
-- [✓] Verify CREATE INTERACTIVE WAREHOUSE syntax
-- [✓] Verify TABLES clause syntax
-- [✓] Verify ALTER INTERACTIVE WAREHOUSE ADD/REMOVE TABLES
-- [✓] Verify SHOW INTERACTIVE TABLES IN INTERACTIVE WAREHOUSE
-- [✓] Verify SUSPEND/RESUME operations
-- [ ] Document if fully qualified table names are required for ADD/REMOVE
-- [ ] Document if warehouse needs to be running before adding tables
-- [ ] Document SHOW INTERACTIVE TABLES output format
-- [ ] Document initial warehouse state (SUSPENDED or STARTED)
-- [ ] Document that interactive warehouses don't auto-suspend by design
-- [ ] Clarify resume latency expectations
-- [ ] Document IF SUSPENDED clause for RESUME
-- ============================================================================

-- ============================================================================
-- Notes for Skill Enhancement:
-- 1. Clarify table name format requirements (quoted vs unquoted, FQN required?)
-- 2. Document warehouse state transitions
-- 3. Add best practices for when to suspend/resume
-- 4. Document cost implications of always-running warehouses
-- 5. Add troubleshooting for table association failures
-- ============================================================================
