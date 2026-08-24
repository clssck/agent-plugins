-- ============================================================================
-- Test Script 10: Cleanup (Idempotent / Best-Effort)
-- Purpose: Remove all test objects without assuming database/schema/warehouse exist
-- ============================================================================

-- NOTE:
-- - This cleanup is intentionally written to be safe to run BEFORE setup.
-- - Fully qualified names are used to avoid dependency on USE DATABASE/SCHEMA.

-- ============================================================================
-- Drop test procedure(s) (if created)
-- ============================================================================

DROP PROCEDURE IF EXISTS INTERACTIVE_SKILL_TEST.SKILL_TEST.test_proc();

-- ============================================================================
-- Drop tables (interactive + standard) (if they exist)
-- ============================================================================

-- Static interactive tables
DROP TABLE IF EXISTS INTERACTIVE_SKILL_TEST.SKILL_TEST.customers_interactive;

-- Dynamic interactive tables
DROP TABLE IF EXISTS INTERACTIVE_SKILL_TEST.SKILL_TEST.orders_dynamic;
DROP TABLE IF EXISTS INTERACTIVE_SKILL_TEST.SKILL_TEST.orders_interactive_sync;
DROP TABLE IF EXISTS INTERACTIVE_SKILL_TEST.SKILL_TEST.daily_sales_summary;
DROP TABLE IF EXISTS INTERACTIVE_SKILL_TEST.SKILL_TEST.customer_order_summary;

-- Streaming interactive tables
DROP TABLE IF EXISTS INTERACTIVE_SKILL_TEST.SKILL_TEST.events_streaming;
DROP TABLE IF EXISTS INTERACTIVE_SKILL_TEST.SKILL_TEST.events_streaming_complex;
DROP TABLE IF EXISTS INTERACTIVE_SKILL_TEST.SKILL_TEST.kafka_demo;

-- Advanced scenario tables
DROP TABLE IF EXISTS INTERACTIVE_SKILL_TEST.SKILL_TEST.products_interactive;
DROP TABLE IF EXISTS INTERACTIVE_SKILL_TEST.SKILL_TEST.transactions_interactive;
DROP TABLE IF EXISTS INTERACTIVE_SKILL_TEST.SKILL_TEST.events_by_day;
DROP TABLE IF EXISTS INTERACTIVE_SKILL_TEST.SKILL_TEST.events_by_month_type;

-- Standard/source tables
DROP TABLE IF EXISTS INTERACTIVE_SKILL_TEST.SKILL_TEST.customers_source;
DROP TABLE IF EXISTS INTERACTIVE_SKILL_TEST.SKILL_TEST.orders_source;
DROP TABLE IF EXISTS INTERACTIVE_SKILL_TEST.SKILL_TEST.orders_standard;
DROP TABLE IF EXISTS INTERACTIVE_SKILL_TEST.SKILL_TEST.sales_raw;

-- ============================================================================
-- Drop interactive warehouses (if they exist)
-- ============================================================================

DROP WAREHOUSE IF EXISTS test_iwh_empty;
DROP WAREHOUSE IF EXISTS test_iwh_with_tables;
DROP WAREHOUSE IF EXISTS test_iwh_multi;
DROP WAREHOUSE IF EXISTS test_iwh_shared;
DROP WAREHOUSE IF EXISTS test_iwh_medium;

-- ============================================================================
-- Drop standard warehouse (if it exists)
-- ============================================================================

DROP WAREHOUSE IF EXISTS TEST_STANDARD_WH;

-- ============================================================================
-- Final Status
-- ============================================================================

SELECT 'Cleanup completed (best-effort)' AS status;

-- ============================================================================
-- Summary of Cleaned Up Objects:
-- 
-- Interactive Tables (11):
-- - customers_interactive
-- - orders_dynamic
-- - orders_interactive_sync
-- - events_streaming
-- - events_streaming_complex
-- - kafka_demo
-- - products_interactive
-- - transactions_interactive
-- - events_by_day
-- - events_by_month_type
-- - daily_sales_summary
-- - customer_order_summary
--
-- Standard Tables (4):
-- - customers_source
-- - orders_source
-- - orders_standard
-- - sales_raw
--
-- Interactive Warehouses (5):
-- - test_iwh_empty
-- - test_iwh_with_tables
-- - test_iwh_multi
-- - test_iwh_shared
-- - test_iwh_medium
--
-- Standard Warehouse (1):
-- - TEST_STANDARD_WH
--
-- Stored Procedures (1):
-- - test_proc
--
-- Pipes (auto-created, removed with tables):
-- - events_streaming
-- - events_streaming_complex
-- - kafka_demo
-- ============================================================================
