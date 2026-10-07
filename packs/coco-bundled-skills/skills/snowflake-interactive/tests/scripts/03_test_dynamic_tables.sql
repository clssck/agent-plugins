-- ============================================================================
-- Test Script 03: Dynamic Interactive Tables with TARGET_LAG
-- Purpose: Test auto-refresh functionality with TARGET_LAG
-- ============================================================================

USE DATABASE INTERACTIVE_SKILL_TEST;
USE SCHEMA SKILL_TEST;
USE WAREHOUSE TEST_STANDARD_WH;

-- ============================================================================
-- Test 3.1: Create Dynamic Interactive Table
-- ============================================================================

-- Create dynamic interactive table with 1-minute lag
CREATE INTERACTIVE TABLE orders_dynamic
CLUSTER BY (order_id, customer_id)
TARGET_LAG = '1 minute'
WAREHOUSE = TEST_STANDARD_WH
AS SELECT * FROM orders_source;

-- Verify table created
SHOW TABLES LIKE 'orders_dynamic';

-- Verify initial data loaded
SELECT 'orders_source' AS table_name, COUNT(*) AS row_count FROM orders_source
UNION ALL
SELECT 'orders_dynamic' AS table_name, COUNT(*) AS row_count FROM orders_dynamic;

-- Check table properties
DESC TABLE orders_dynamic;

-- Sample data preview
SELECT * FROM orders_dynamic ORDER BY order_id DESC LIMIT 10;

-- ============================================================================
-- Test 3.2: Verify Auto-Refresh Behavior - INSERT
-- ============================================================================

-- Record timestamp before change
SELECT CURRENT_TIMESTAMP() AS before_insert_timestamp;

-- Record current row count
SELECT COUNT(*) AS before_insert FROM orders_dynamic;

-- Insert 50 new rows into source
INSERT INTO orders_source
SELECT 
  500 + SEQ4() AS order_id,
  MOD(SEQ4(), 100) AS customer_id,
  DATEADD(day, -MOD(SEQ4(), 30), CURRENT_DATE()) AS order_date,
  ROUND(UNIFORM(10.00, 1000.00, RANDOM()), 2) AS amount,
  'PENDING' AS status
FROM TABLE(GENERATOR(ROWCOUNT => 50));

-- Verify source has new rows
SELECT COUNT(*) AS source_count_after_insert FROM orders_source;

-- Wait for refresh (70 seconds to account for 1-minute lag + buffer)
CALL SYSTEM$WAIT(70);

-- Check if new data appeared in dynamic table
SELECT COUNT(*) AS after_insert FROM orders_dynamic;

-- Verify new rows are present
SELECT COUNT(*) AS new_orders 
FROM orders_dynamic 
WHERE order_id >= 500;

-- ============================================================================
-- Test 3.3: Verify Auto-Refresh Behavior - UPDATE
-- ============================================================================

-- Record timestamp before update
SELECT CURRENT_TIMESTAMP() AS before_update_timestamp;

-- Count current SHIPPED orders
SELECT COUNT(*) AS shipped_before FROM orders_dynamic WHERE status = 'SHIPPED';

-- Update 20 rows in source from PENDING to SHIPPED
-- NOTE: Snowflake UPDATE does not support a LIMIT clause.
UPDATE orders_source
SET status = 'SHIPPED'
WHERE order_id IN (
  SELECT order_id
  FROM orders_source
  WHERE status = 'PENDING'
  ORDER BY order_id
  LIMIT 20
);

-- Verify source has updated rows
SELECT COUNT(*) AS shipped_in_source FROM orders_source WHERE status = 'SHIPPED';

-- Wait for refresh (70 seconds)
CALL SYSTEM$WAIT(70);

-- Check if updates appeared in dynamic table
SELECT COUNT(*) AS shipped_after FROM orders_dynamic WHERE status = 'SHIPPED';

-- ============================================================================
-- Test 3.4: Verify Auto-Refresh Behavior - DELETE
-- ============================================================================

-- Record timestamp before delete
SELECT CURRENT_TIMESTAMP() AS before_delete_timestamp;

-- Count current rows
SELECT COUNT(*) AS before_delete FROM orders_dynamic;

-- Delete CANCELLED orders from source
DELETE FROM orders_source WHERE status = 'CANCELLED';

-- Verify source has fewer rows
SELECT COUNT(*) AS source_after_delete FROM orders_source;

-- Wait for refresh (70 seconds)
CALL SYSTEM$WAIT(70);

-- Check if deletes propagated to dynamic table
SELECT COUNT(*) AS after_delete FROM orders_dynamic;

-- Verify CANCELLED orders are gone
SELECT COUNT(*) AS cancelled_count FROM orders_dynamic WHERE status = 'CANCELLED';

-- ============================================================================
-- Test 3.5: Check Refresh History (if available)
-- ============================================================================

-- Try to query refresh history
-- Note: This may not be available in all versions
-- SELECT * FROM TABLE(INFORMATION_SCHEMA.INTERACTIVE_TABLE_REFRESH_HISTORY(TABLE_NAME => 'orders_dynamic'));

-- ============================================================================
-- Validation Summary
-- ============================================================================

SELECT 
  'orders_source' AS table_name,
  COUNT(*) AS row_count,
  COUNT(DISTINCT status) AS distinct_statuses
FROM orders_source
UNION ALL
SELECT 
  'orders_dynamic' AS table_name,
  COUNT(*) AS row_count,
  COUNT(DISTINCT status) AS distinct_statuses
FROM orders_dynamic;

-- Status breakdown
SELECT status, COUNT(*) AS count FROM orders_source GROUP BY status ORDER BY status;
SELECT status, COUNT(*) AS count FROM orders_dynamic GROUP BY status ORDER BY status;

-- ============================================================================
-- Expected Results:
-- - orders_dynamic created successfully with TARGET_LAG='1 minute'
-- - Initial data matches source (500 rows)
-- - After INSERT: dynamic table gets 50 new rows (within 70 seconds)
-- - After UPDATE: status changes propagate (within 70 seconds)
-- - After DELETE: cancelled orders removed (within 70 seconds)
-- ============================================================================

-- ============================================================================
-- Skill Documentation Checks:
-- [✓] Verify TARGET_LAG syntax
-- [✓] Verify minimum TARGET_LAG value (1 minute)
-- [✓] Verify WAREHOUSE clause requirement
-- [ ] Document how to monitor refresh status
-- [ ] Document initial vs subsequent refresh behavior
-- [ ] Clarify if DML on source triggers immediate refresh or waits for lag
-- [ ] Document refresh history querying methods
-- ============================================================================
