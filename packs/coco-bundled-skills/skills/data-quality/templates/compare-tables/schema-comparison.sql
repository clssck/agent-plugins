-- Schema Comparison
-- Compare table schemas between source and target tables
-- Replace <source_database>, <source_schema>, <source_table> and target equivalents

WITH source_cols AS (
    SELECT 
        COLUMN_NAME,
        DATA_TYPE,
        IS_NULLABLE,
        CHARACTER_MAXIMUM_LENGTH,
        NUMERIC_PRECISION,
        NUMERIC_SCALE,
        ORDINAL_POSITION
    FROM <source_database>.INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = '<source_schema>'
      AND TABLE_NAME = '<source_table>'
),
target_cols AS (
    SELECT 
        COLUMN_NAME,
        DATA_TYPE,
        IS_NULLABLE,
        CHARACTER_MAXIMUM_LENGTH,
        NUMERIC_PRECISION,
        NUMERIC_SCALE,
        ORDINAL_POSITION
    FROM <target_database>.INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = '<target_schema>'
      AND TABLE_NAME = '<target_table>'
)
SELECT 
    COALESCE(s.COLUMN_NAME, t.COLUMN_NAME) AS column_name,
    s.DATA_TYPE AS source_type,
    t.DATA_TYPE AS target_type,
    s.IS_NULLABLE AS source_nullable,
    t.IS_NULLABLE AS target_nullable,
    CASE 
        WHEN s.COLUMN_NAME IS NULL THEN 'ADDED'
        WHEN t.COLUMN_NAME IS NULL THEN 'REMOVED'
        WHEN s.DATA_TYPE != t.DATA_TYPE THEN 'TYPE_CHANGED'
        WHEN s.IS_NULLABLE != t.IS_NULLABLE THEN 'NULLABILITY_CHANGED'
        ELSE 'UNCHANGED'
    END AS change_status
FROM source_cols s
FULL OUTER JOIN target_cols t ON s.COLUMN_NAME = t.COLUMN_NAME
ORDER BY 
    CASE WHEN change_status != 'UNCHANGED' THEN 0 ELSE 1 END,
    COALESCE(s.ORDINAL_POSITION, t.ORDINAL_POSITION);

-- Interpretation:
-- ADDED: Column exists in target but not source (new column)
-- REMOVED: Column exists in source but not target (dropped column)
-- TYPE_CHANGED: Column data type differs
-- NULLABILITY_CHANGED: Column nullability constraint differs
-- UNCHANGED: Column is identical in both tables
