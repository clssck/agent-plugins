-- ============================================================================
-- Test Script 04: Streaming Interactive Tables
-- Purpose: Test Snowpipe Streaming integration
-- ============================================================================

USE DATABASE INTERACTIVE_SKILL_TEST;
USE SCHEMA SKILL_TEST;
USE WAREHOUSE TEST_STANDARD_WH;

-- ============================================================================
-- Test 4.1: Create Simple Streaming Interactive Table
-- ============================================================================

-- Create streaming table with basic column definitions
CREATE INTERACTIVE TABLE events_streaming (
  event_id INT,
  event_name VARCHAR(100),
  event_ts TIMESTAMP
) CLUSTER BY (event_id);

-- Verify table created
SHOW TABLES LIKE 'events_streaming';

-- Check table structure
DESC TABLE events_streaming;

-- Verify table is empty (no data inserted via SQL)
SELECT COUNT(*) AS row_count FROM events_streaming;

-- ============================================================================
-- Test 4.2: Verify Auto-Pipe Creation
-- ============================================================================

-- Check if pipe was automatically created with same name as table
SHOW PIPES LIKE 'events_streaming';

-- NOTE:
-- Per docs, interactive tables with streaming enabled are represented as a pipe
-- and you can inspect it with `DESCRIBE PIPE <interactive_table_name>`.
-- In this environment, the pipe may not exist until a streaming client connects
-- (Kafka connector / Snowpipe Streaming SDK). If SHOW PIPES returns no rows,
-- treat that as expected until ingestion begins.
-- DESC PIPE events_streaming;

-- ============================================================================
-- Test 4.3: Streaming with Field Mapping (Kafka-style)
-- ============================================================================

-- Create streaming table with RECORD_CONTENT/RECORD_METADATA mapping
CREATE OR REPLACE INTERACTIVE TABLE kafka_demo (
  timestamp TIMESTAMP_NTZ(6),
  country_code VARCHAR(16777216),
  url VARCHAR(16777216),
  topicname VARCHAR(16777216),
  streamingeventtime TIMESTAMP_NTZ(6)
) CLUSTER BY (TRUNC(timestamp, 'day'))
AS (
  SELECT 
    $1:RECORD_CONTENT.timestamp,
    $1:RECORD_CONTENT.country_code,
    $1:RECORD_CONTENT.url,
    $1:RECORD_METADATA.topic,
    SYSDATE() as streamingeventtime
  FROM TABLE(DATA_SOURCE(TYPE => 'STREAMING'))
);

-- Verify table created
SHOW TABLES LIKE 'kafka_demo';

-- Describe the table
DESC TABLE kafka_demo;

-- Check pipe properties
-- Same note as above: the pipe may not exist until a streaming client connects.
-- DESC PIPE kafka_demo;
-- If/when DESCRIBE PIPE succeeds, you can inspect key attributes like kind/name/definition.
-- DESCRIBE PIPE kafka_demo ->> SELECT "kind", "name", IS_SNOWFLAKE_MANAGED, "definition" FROM $1;

-- ============================================================================
-- Test 4.4: Verify Cannot INSERT INTO Streaming Table via SQL
-- ============================================================================

-- This should fail - streaming tables don't accept direct SQL INSERTs
-- INSERT INTO events_streaming VALUES (1, 'test_event', CURRENT_TIMESTAMP());

-- ============================================================================
-- Test 4.5: Grant Privileges for Streaming (Setup Example)
-- ============================================================================

-- Example of setting up privileges for streaming
-- Note: This is for documentation purposes, may need role with privilege to execute

-- CREATE ROLE IF NOT EXISTS streaming_role;
-- CREATE USER IF NOT EXISTS streaming_user;
-- GRANT ROLE streaming_role TO USER streaming_user;
-- GRANT USAGE ON SCHEMA SKILL_TEST TO ROLE streaming_role;
-- GRANT ALL ON TABLE events_streaming TO ROLE streaming_role;
-- GRANT ALL ON PIPE events_streaming TO ROLE streaming_role;

-- ============================================================================
-- Test 4.6: Create Another Streaming Table with Different Clustering
-- ============================================================================

-- Streaming table with expression-based clustering
CREATE OR REPLACE INTERACTIVE TABLE events_streaming_complex (
  event_id INT,
  event_name VARCHAR(100),
  event_ts TIMESTAMP,
  event_date DATE
) CLUSTER BY (event_date);

-- Verify creation
SHOW TABLES LIKE 'events_streaming_complex';

-- Verify pipe
SHOW PIPES LIKE 'events_streaming_complex';

-- ============================================================================
-- Validation Summary
-- ============================================================================

-- List all streaming tables created
SHOW TABLES LIKE '%streaming%';

-- List all pipes created
SHOW PIPES IN SCHEMA SKILL_TEST;

-- Verify table properties
SELECT 
  TABLE_NAME,
  TABLE_TYPE,
  CREATED
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'SKILL_TEST'
  AND TABLE_NAME LIKE '%streaming%'
ORDER BY TABLE_NAME;

-- ============================================================================
-- Expected Results:
-- - events_streaming created successfully
-- - Pipe events_streaming auto-created
-- - kafka_demo created with field mapping
-- - Pipe kafka_demo shows STREAMING kind and DATA_SOURCE in definition
-- - events_streaming_complex created with date-based clustering
-- - All tables are empty (streaming ingestion happens externally)
-- ============================================================================

-- ============================================================================
-- Skill Documentation Checks:
-- [✓] Verify simple streaming table syntax
-- [✓] Verify complex streaming table with field mapping syntax
-- [✓] Verify CLUSTER BY with expressions (TRUNC)
-- [ ] Document that pipe is auto-created with same name as table
-- [ ] Document that DESCRIBE PIPE shows pipe properties
-- [ ] Document that streaming tables cannot accept SQL INSERT
-- [ ] Document RECORD_CONTENT and RECORD_METADATA keywords
-- [ ] Document DATA_SOURCE(TYPE => 'STREAMING') function
-- [ ] Add Kafka connector configuration example
-- [ ] Document required privileges clearly
-- [ ] Add monitoring section for streaming ingestion
-- [ ] Document IS_SNOWFLAKE_MANAGED column in DESCRIBE PIPE output
-- ============================================================================

-- ============================================================================
-- Notes for Skill Enhancement:
-- 1. Add complete Kafka connector setup guide in resources/
-- 2. Explain difference between simple form and AS form
-- 3. Document streaming vs batch ingestion use cases
-- 4. Add troubleshooting for streaming connection issues
-- 5. Document monitoring views (SNOWPIPE_STREAMING_FILE_MIGRATION_HISTORY)
-- ============================================================================
