-- Exact Match Check
-- Quick check if two tables are exactly identical
-- Replace <source_table>, <target_table>

SELECT 
    CASE 
        WHEN source_hash = target_hash AND source_count = target_count THEN 'IDENTICAL'
        WHEN source_count != target_count THEN 'DIFFERENT_ROW_COUNT'
        ELSE 'DIFFERENT_CONTENT'
    END AS comparison_result,
    source_count,
    target_count,
    source_count - target_count AS row_difference
FROM (
    SELECT 
        (SELECT COUNT(*) FROM <source_table>) AS source_count,
        (SELECT COUNT(*) FROM <target_table>) AS target_count,
        (SELECT SUM(HASH(*)) FROM <source_table>) AS source_hash,
        (SELECT SUM(HASH(*)) FROM <target_table>) AS target_hash
);

-- Interpretation:
-- IDENTICAL: Tables have same row count and content hash
-- DIFFERENT_ROW_COUNT: Tables have different number of rows
-- DIFFERENT_CONTENT: Same row count but different content
