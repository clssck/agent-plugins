-- ============================================================================
-- Test Script 08: Error Cases & Limitations
-- Purpose: Verify limitations and document error messages
-- ============================================================================

USE DATABASE INTERACTIVE_SKILL_TEST;
USE SCHEMA SKILL_TEST;

-- ============================================================================
-- Test 8.1: Attempt UPDATE on Interactive Table (Should Fail)
-- ============================================================================

USE WAREHOUSE TEST_STANDARD_WH;

SELECT 'Test 8.1: Attempting UPDATE on interactive table...' AS test;

-- This should fail with specific error message
-- UPDATE customers_interactive SET name = 'Updated Name' WHERE id = 1;

-- Expected error: SQL compilation error - UPDATE not supported on interactive tables

-- ============================================================================
-- Test 8.2: Attempt DELETE on Interactive Table (Should Fail)
-- ============================================================================

SELECT 'Test 8.2: Attempting DELETE on interactive table...' AS test;

-- This should fail
-- DELETE FROM customers_interactive WHERE id = 1;

-- Expected error: SQL compilation error - DELETE not supported on interactive tables

-- ============================================================================
-- Test 8.3: Attempt ALTER TABLE ADD COLUMN (Should Fail)
-- ============================================================================

SELECT 'Test 8.3: Attempting ALTER TABLE ADD COLUMN...' AS test;

-- This should fail
-- ALTER TABLE customers_interactive ADD COLUMN new_column VARCHAR(50);

-- Expected error: Cannot alter interactive table structure

-- ============================================================================
-- Test 8.4: Attempt to Create Stream on Interactive Table (Should Fail)
-- ============================================================================

SELECT 'Test 8.4: Attempting CREATE STREAM on interactive table...' AS test;

-- This should fail
-- CREATE STREAM customers_stream ON TABLE customers_interactive;

-- Expected error: Streams not supported on interactive tables

-- ============================================================================
-- Test 8.5: Query Standard Table from Interactive Warehouse (Should Fail)
-- ============================================================================

USE WAREHOUSE test_iwh_with_tables;
ALTER WAREHOUSE test_iwh_with_tables RESUME IF SUSPENDED;

SELECT 'Test 8.5: Attempting to query standard table from interactive warehouse...' AS test;

-- This should fail
-- SELECT * FROM customers_source LIMIT 10;

-- Expected error: Cannot query standard table from interactive warehouse

-- ============================================================================
-- Test 8.6: Test 5-Second Query Timeout
-- ============================================================================

SELECT 'Test 8.6: Testing 5-second query timeout...' AS test;

-- Attempt an expensive query that might timeout
-- Note: Adjust complexity based on data size

-- Cartesian product (likely to timeout on larger datasets)
-- SELECT COUNT(*) 
-- FROM customers_interactive c1 
-- CROSS JOIN customers_interactive c2 
-- WHERE c1.id != c2.id;

-- Expected: Query timeout after 5 seconds

-- ============================================================================
-- Test 8.7: Attempt to Use ->> Pipe Operator (Should Fail)
-- ============================================================================

SELECT 'Test 8.7: Attempting to use ->> pipe operator...' AS test;

-- This should fail - pipe operator not supported
-- SELECT * FROM customers_interactive ->> SELECT * FROM orders_dynamic;

-- Expected error: Pipe operator not supported in interactive warehouses

-- ============================================================================
-- Test 8.8: Attempt to Call Stored Procedure (Should Fail)
-- ============================================================================

SELECT 'Test 8.8: Attempting CALL stored procedure...' AS test;

-- Create a simple procedure first (using standard warehouse)
USE WAREHOUSE TEST_STANDARD_WH;

CREATE OR REPLACE PROCEDURE test_proc()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
BEGIN
  RETURN 'Test';
END;
$$
;

-- Try to call from interactive warehouse (should fail)
USE WAREHOUSE test_iwh_with_tables;

-- This should fail
-- CALL test_proc();

-- Expected error: CALL commands not supported in interactive warehouses

-- ============================================================================
-- Test 8.9: Attempt to Create Materialized View from Interactive Table
-- ============================================================================

USE WAREHOUSE TEST_STANDARD_WH;

SELECT 'Test 8.9: Attempting to create materialized view from interactive table...' AS test;

-- This should fail
-- CREATE MATERIALIZED VIEW customers_mv AS 
-- SELECT region, COUNT(*) AS count FROM customers_interactive GROUP BY region;

-- Expected error: Interactive tables cannot be source for materialized views

-- ============================================================================
-- Test 8.10: Attempt to Create Dynamic Table with Interactive Base
-- ============================================================================

SELECT 'Test 8.10: Attempting to create dynamic table with interactive base...' AS test;

-- This should fail
-- CREATE DYNAMIC TABLE customers_dt
-- TARGET_LAG = '1 minute'
-- WAREHOUSE = TEST_STANDARD_WH
-- AS SELECT * FROM customers_interactive;

-- Expected error: Cannot use interactive table as base for dynamic table

-- ============================================================================
-- Test 8.11: Attempt to Apply Data Masking Policy (Should Fail)
-- ============================================================================

SELECT 'Test 8.11: Attempting to apply masking policy...' AS test;

-- NOTE:
-- Masking policies are an account/edition-governed feature. In some accounts,
-- CREATE MASKING POLICY itself is unsupported, which would stop this suite.
-- Keep this test optional; uncomment when your account supports masking policies.

-- Create a simple masking policy first
-- CREATE OR REPLACE MASKING POLICY mask_name AS (val STRING) RETURNS STRING ->
--   CASE WHEN CURRENT_ROLE() = 'SYSADMIN' THEN val ELSE '***' END;

-- Try to apply to interactive table (should fail)
-- ALTER TABLE customers_interactive MODIFY COLUMN name SET MASKING POLICY mask_name;

-- Expected error: Masking policies not supported on interactive tables

-- Clean up
-- DROP MASKING POLICY IF EXISTS mask_name;

-- ============================================================================
-- Test 8.12: Attempt Direct INSERT to Streaming Interactive Table
-- ============================================================================

SELECT 'Test 8.12: Attempting direct INSERT to streaming table...' AS test;

-- This should fail
-- INSERT INTO events_streaming VALUES (1, 'test', CURRENT_TIMESTAMP());

-- Expected error: Cannot INSERT directly to streaming interactive table

-- ============================================================================
-- Test 8.13: Attempt to Create Interactive Table Without CLUSTER BY
-- ============================================================================

SELECT 'Test 8.13: Attempting to create interactive table without CLUSTER BY...' AS test;

-- This should fail
-- CREATE INTERACTIVE TABLE test_no_cluster
-- AS SELECT * FROM customers_source;

-- Expected error: CLUSTER BY clause required for interactive tables

-- ============================================================================
-- Test 8.14: Attempt to Set TARGET_LAG Below Minimum
-- ============================================================================

SELECT 'Test 8.14: Attempting TARGET_LAG below minimum (< 1 minute)...' AS test;

-- This should fail
-- CREATE INTERACTIVE TABLE test_low_lag
-- CLUSTER BY (id)
-- TARGET_LAG = '30 seconds'
-- WAREHOUSE = TEST_STANDARD_WH
-- AS SELECT * FROM customers_source;

-- Expected error: TARGET_LAG minimum is 60 seconds or 1 minute

-- ============================================================================
-- Test 8.15: Attempt to Use RESAMPLE Clause
-- ============================================================================

USE WAREHOUSE test_iwh_with_tables;

SELECT 'Test 8.15: Attempting RESAMPLE clause...' AS test;

-- This should fail
-- SELECT * FROM customers_interactive SAMPLE (10 ROWS);

-- Expected error or unsupported: RESAMPLE not supported

-- ============================================================================
-- Validation Summary
-- ============================================================================

-- Document all tested limitations
SELECT 'Limitation Tests Completed' AS status;

SELECT 'Review error messages and update skill documentation accordingly' AS action_item;

-- ============================================================================
-- Expected Results (All Should Fail with Specific Errors):
-- 1. UPDATE on interactive table: NOT SUPPORTED
-- 2. DELETE on interactive table: NOT SUPPORTED
-- 3. ALTER TABLE ADD COLUMN: NOT SUPPORTED
-- 4. CREATE STREAM: NOT SUPPORTED
-- 5. Query standard table from interactive warehouse: NOT SUPPORTED
-- 6. Complex queries: MAY TIMEOUT (5 seconds)
-- 7. ->> pipe operator: NOT SUPPORTED
-- 8. CALL procedure: NOT SUPPORTED
-- 9. Materialized view source: NOT SUPPORTED
-- 10. Dynamic table base: NOT SUPPORTED
-- 11. Masking policy: NOT SUPPORTED
-- 12. INSERT to streaming table: NOT SUPPORTED
-- 13. Missing CLUSTER BY: REQUIRED
-- 14. TARGET_LAG < 1 minute: BELOW MINIMUM
-- 15. RESAMPLE: NOT SUPPORTED
-- ============================================================================

-- ============================================================================
-- Skill Documentation Checks:
-- [ ] Document exact error messages for each limitation
-- [ ] Add "Common Errors" section to skill
-- [ ] Document workarounds where available
-- [ ] Add troubleshooting guide
-- [ ] Document all SQL features not supported
-- [ ] Add validation requirements (CLUSTER BY, TARGET_LAG minimums)
-- ============================================================================

-- ============================================================================
-- Notes for Skill Enhancement:
-- 1. Create comprehensive error messages reference
-- 2. Add "What Works / What Doesn't Work" comparison table
-- 3. Document workarounds for each limitation
-- 4. Add decision tree: when to use interactive vs standard vs dynamic tables
-- 5. Create troubleshooting flowchart
-- 6. Document performance expectations and timeout behavior
-- ============================================================================
