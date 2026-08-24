-- Root Cause Analysis Fallback: Extract upstream lineage from DDL
-- When GET_LINEAGE and OBJECT_DEPENDENCIES return empty (e.g. latency or new object)
-- Replace <database>, <schema>, <table> with actual values BEFORE executing

-- This template provides the approach for DDL-based lineage extraction:
-- 1. Get the DDL of the target object
-- 2. Parse for table/view references
-- 3. Recursively get DDL of those objects
-- 4. Build upstream lineage tree

-- Step 1: Get DDL of target view (works immediately, no latency)
SELECT 
    '<database>.<schema>.<table>' AS target_object,
    GET_DDL('VIEW', '<database>.<schema>.<table>') AS ddl_text,
    'Parse DDL for FROM/JOIN clauses to identify upstream objects' AS next_step;

-- Example parsing approach (to be done by agent):
-- DDL: SELECT * FROM SCHEMA.TABLE_A JOIN SCHEMA.TABLE_B ON ...
-- Extract: SCHEMA.TABLE_A, SCHEMA.TABLE_B as Level 1 upstream
-- Then get DDL for each of those and repeat

-- For tables (not views), check for CLONE or CTAS patterns:
-- CREATE TABLE ... CLONE SOURCE_TABLE
-- CREATE TABLE ... AS SELECT * FROM SOURCE

-- Agent should:
-- 1. Execute: SELECT GET_DDL('VIEW', '<database>.<schema>.<table>')
-- 2. Parse result for: FROM <schema>.<table>, JOIN <schema>.<table>
-- 3. For each found reference, recursively get its DDL
-- 4. Build lineage tree up to 3 levels
-- 5. Present results with schema change times from ACCOUNT_USAGE.TABLES
