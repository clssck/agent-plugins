-- Row Count Comparison
-- Compare row counts between source and target tables
-- Replace <source_table> and <target_table> with fully qualified names

SELECT 
    'SOURCE' AS table_version,
    '<source_table>' AS table_name,
    COUNT(*) AS row_count
FROM <source_table>
UNION ALL
SELECT 
    'TARGET' AS table_version,
    '<target_table>' AS table_name,
    COUNT(*) AS row_count
FROM <target_table>;

-- Add optional filter: WHERE <filter_condition>
