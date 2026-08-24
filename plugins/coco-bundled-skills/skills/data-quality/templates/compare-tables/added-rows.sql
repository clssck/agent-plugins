-- Added Rows
-- Find rows that exist in target but not in source (new rows)
-- Replace <source_table>, <target_table>, <key_column>

SELECT t.*
FROM <target_table> t
LEFT JOIN <source_table> s ON t.<key_column> = s.<key_column>
WHERE s.<key_column> IS NULL
ORDER BY t.<key_column>
LIMIT 100;

-- For compound keys, join on multiple columns:
-- LEFT JOIN <source_table> s 
--   ON t.<key_col1> = s.<key_col1> 
--   AND t.<key_col2> = s.<key_col2>
