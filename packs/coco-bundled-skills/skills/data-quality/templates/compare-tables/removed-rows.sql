-- Removed Rows
-- Find rows that exist in source but not in target (deleted rows)
-- Replace <source_table>, <target_table>, <key_column>

SELECT s.*
FROM <source_table> s
LEFT JOIN <target_table> t ON s.<key_column> = t.<key_column>
WHERE t.<key_column> IS NULL
ORDER BY s.<key_column>
LIMIT 100;

-- For compound keys, join on multiple columns:
-- LEFT JOIN <target_table> t 
--   ON s.<key_col1> = t.<key_col1> 
--   AND s.<key_col2> = t.<key_col2>
