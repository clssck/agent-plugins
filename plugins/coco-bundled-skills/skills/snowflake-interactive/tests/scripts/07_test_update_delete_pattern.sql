-- ============================================================================
-- Test Script 07: UPDATE/DELETE Pattern (Standard + Dynamic Table)
-- Purpose: Test the recommended pattern for handling DML operations
-- ============================================================================

USE DATABASE INTERACTIVE_SKILL_TEST;
USE SCHEMA SKILL_TEST;
USE WAREHOUSE TEST_STANDARD_WH;

-- ============================================================================
-- Test 7.1: Create Standard Table for DML Operations
-- ============================================================================

-- Create a standard table that will accept UPDATE/DELETE
CREATE OR REPLACE TABLE orders_standard (
  order_id INT,
  customer_id INT,
  order_date DATE,
  amount DECIMAL(10,2),
  status VARCHAR(20),
  last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

-- Insert initial data (100 rows)
INSERT INTO orders_standard (order_id, customer_id, order_date, amount, status)
SELECT 
  SEQ4() AS order_id,
  MOD(SEQ4(), 50) AS customer_id,
  DATEADD(day, -MOD(SEQ4(), 90), CURRENT_DATE()) AS order_date,
  ROUND(UNIFORM(10.00, 500.00, RANDOM()), 2) AS amount,
  CASE MOD(SEQ4(), 5)
    WHEN 0 THEN 'PENDING'
    WHEN 1 THEN 'PROCESSING'
    WHEN 2 THEN 'SHIPPED'
    WHEN 3 THEN 'DELIVERED'
    WHEN 4 THEN 'CANCELLED'
  END AS status
FROM TABLE(GENERATOR(ROWCOUNT => 100));

-- Verify data inserted
SELECT COUNT(*) AS initial_count FROM orders_standard;

-- Check status distribution
SELECT status, COUNT(*) AS count 
FROM orders_standard 
GROUP BY status 
ORDER BY status;

-- ============================================================================
-- Test 7.2: Create Dynamic Interactive Table Syncing from Standard Table
-- ============================================================================

-- Create dynamic interactive table with 1-minute lag
CREATE OR REPLACE INTERACTIVE TABLE orders_interactive_sync
CLUSTER BY (order_id, status)
TARGET_LAG = '1 minute'
WAREHOUSE = TEST_STANDARD_WH
AS SELECT * FROM orders_standard;

-- Verify initial sync
SELECT COUNT(*) AS initial_sync_count FROM orders_interactive_sync;

-- Verify data matches
SELECT 
  'Standard Table' AS source,
  COUNT(*) AS row_count,
  COUNT(DISTINCT status) AS distinct_statuses
FROM orders_standard
UNION ALL
SELECT 
  'Interactive Sync' AS source,
  COUNT(*) AS row_count,
  COUNT(DISTINCT status) AS distinct_statuses
FROM orders_interactive_sync;

-- ============================================================================
-- Test 7.3: Test INSERT Propagation
-- ============================================================================

-- Record timestamp before INSERT
SELECT CURRENT_TIMESTAMP() AS before_insert;

-- Record counts before
SELECT 'Before INSERT' AS timing, COUNT(*) AS std_count FROM orders_standard
UNION ALL
SELECT 'Before INSERT' AS timing, COUNT(*) AS sync_count FROM orders_interactive_sync;

-- Insert 20 new rows into standard table
INSERT INTO orders_standard (order_id, customer_id, order_date, amount, status)
SELECT 
  100 + SEQ4() AS order_id,
  MOD(SEQ4(), 50) AS customer_id,
  CURRENT_DATE() AS order_date,
  ROUND(UNIFORM(50.00, 300.00, RANDOM()), 2) AS amount,
  'PENDING' AS status
FROM TABLE(GENERATOR(ROWCOUNT => 20));

-- Verify inserted in standard table
SELECT COUNT(*) AS after_insert_std FROM orders_standard;

-- Wait for refresh (70 seconds for 1-minute lag + buffer)
CALL SYSTEM$WAIT(70);

-- Check if new data propagated to interactive table
SELECT COUNT(*) AS after_insert_sync FROM orders_interactive_sync;

-- Verify new rows are present
SELECT COUNT(*) AS new_rows 
FROM orders_interactive_sync 
WHERE order_id >= 100;

-- ============================================================================
-- Test 7.4: Test UPDATE Propagation
-- ============================================================================

-- Record timestamp before UPDATE
SELECT CURRENT_TIMESTAMP() AS before_update;

-- Count PENDING orders before update
SELECT 'Before UPDATE' AS timing, 
       COUNT(*) AS pending_count_std 
FROM orders_standard 
WHERE status = 'PENDING';

SELECT 'Before UPDATE' AS timing,
       COUNT(*) AS pending_count_sync
FROM orders_interactive_sync 
WHERE status = 'PENDING';

-- Update 10 PENDING orders to PROCESSING in standard table
UPDATE orders_standard 
SET status = 'PROCESSING',
    last_updated = CURRENT_TIMESTAMP()
WHERE status = 'PENDING' 
  AND order_id < 50;

-- Verify updates in standard table
SELECT 'After UPDATE' AS timing,
       status,
       COUNT(*) AS count 
FROM orders_standard 
GROUP BY status 
ORDER BY status;

-- Wait for refresh (70 seconds)
CALL SYSTEM$WAIT(70);

-- Check if updates propagated to interactive table
SELECT 'After UPDATE (sync)' AS timing,
       status,
       COUNT(*) AS count 
FROM orders_interactive_sync 
GROUP BY status 
ORDER BY status;

-- Verify specific updated orders
SELECT order_id, status, last_updated
FROM orders_interactive_sync
WHERE order_id < 50 AND status = 'PROCESSING'
ORDER BY order_id
LIMIT 10;

-- ============================================================================
-- Test 7.5: Test DELETE Propagation
-- ============================================================================

-- Record timestamp before DELETE
SELECT CURRENT_TIMESTAMP() AS before_delete;

-- Count before delete
SELECT 'Before DELETE' AS timing, COUNT(*) AS std_count FROM orders_standard
UNION ALL
SELECT 'Before DELETE' AS timing, COUNT(*) AS sync_count FROM orders_interactive_sync;

-- Count CANCELLED orders
SELECT COUNT(*) AS cancelled_before_delete FROM orders_standard WHERE status = 'CANCELLED';

-- Delete CANCELLED orders from standard table
DELETE FROM orders_standard WHERE status = 'CANCELLED';

-- Verify deletion in standard table
SELECT COUNT(*) AS after_delete_std FROM orders_standard;
SELECT COUNT(*) AS cancelled_after_delete_std FROM orders_standard WHERE status = 'CANCELLED';

-- Wait for refresh (70 seconds)
CALL SYSTEM$WAIT(70);

-- Check if deletes propagated to interactive table
SELECT COUNT(*) AS after_delete_sync FROM orders_interactive_sync;
SELECT COUNT(*) AS cancelled_after_delete_sync FROM orders_interactive_sync WHERE status = 'CANCELLED';

-- ============================================================================
-- Test 7.6: Mixed DML Operations
-- ============================================================================

-- Record timestamp
SELECT CURRENT_TIMESTAMP() AS before_mixed_dml;

-- Perform multiple operations
-- Insert new orders
INSERT INTO orders_standard (order_id, customer_id, order_date, amount, status)
VALUES (200, 25, CURRENT_DATE(), 150.00, 'PENDING');

-- Update some orders
UPDATE orders_standard 
SET status = 'SHIPPED' 
WHERE status = 'PROCESSING' 
  AND order_id BETWEEN 50 AND 60;

-- Delete specific orders
DELETE FROM orders_standard WHERE amount < 15.00;

-- Verify changes in standard table
SELECT 
  status,
  COUNT(*) AS count,
  SUM(amount) AS total_amount
FROM orders_standard
GROUP BY status
ORDER BY status;

-- Wait for refresh (70 seconds)
CALL SYSTEM$WAIT(70);

-- Check propagation to interactive table
SELECT 
  status,
  COUNT(*) AS count,
  SUM(amount) AS total_amount
FROM orders_interactive_sync
GROUP BY status
ORDER BY status;

-- ============================================================================
-- Validation Summary
-- ============================================================================

-- Final counts
SELECT 
  'Final State' AS label,
  'Standard Table' AS source,
  COUNT(*) AS row_count
FROM orders_standard
UNION ALL
SELECT 
  'Final State' AS label,
  'Interactive Sync' AS source,
  COUNT(*) AS row_count
FROM orders_interactive_sync;

-- Verify data consistency
SELECT 
  s.status,
  COUNT(s.order_id) AS std_count,
  COUNT(i.order_id) AS sync_count,
  ABS(COUNT(s.order_id) - COUNT(i.order_id)) AS difference
FROM orders_standard s
FULL OUTER JOIN orders_interactive_sync i ON s.order_id = i.order_id
GROUP BY s.status
ORDER BY s.status;

-- ============================================================================
-- Expected Results:
-- - Standard table created and accepts INSERT/UPDATE/DELETE
-- - Dynamic interactive table syncs from standard table with 1-minute lag
-- - INSERT operations propagate within ~70 seconds
-- - UPDATE operations propagate within ~70 seconds  
-- - DELETE operations propagate within ~70 seconds
-- - Mixed DML operations all propagate correctly
-- - Final state: both tables have consistent data (within lag tolerance)
-- ============================================================================

-- ============================================================================
-- Skill Documentation Checks:
-- [✓] Verify standard + dynamic table pattern is documented
-- [✓] Verify complete example with all DML operations
-- [ ] Document timing expectations clearly
-- [ ] Add monitoring section for checking sync status
-- [ ] Document how to validate sync completed
-- [ ] Add troubleshooting for sync delays
-- [ ] Clarify if DML triggers immediate refresh or waits for TARGET_LAG
-- [ ] Document last_updated pattern for tracking changes
-- ============================================================================

-- ============================================================================
-- Notes for Skill Enhancement:
-- 1. Add monitoring queries to check refresh history
-- 2. Document refresh trigger behavior (immediate vs scheduled)
-- 3. Add best practices for TARGET_LAG selection based on DML frequency
-- 4. Document data consistency guarantees
-- 5. Add troubleshooting section for sync issues
-- 6. Provide validation query templates
-- ============================================================================
