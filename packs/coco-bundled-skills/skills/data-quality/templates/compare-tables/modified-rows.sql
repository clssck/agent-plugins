-- Modified Rows
-- Find rows that exist in both tables but have different values
-- Replace <source_table>, <target_table>, <key_column>

WITH source_data AS (
    SELECT *, HASH(*) AS row_hash
    FROM <source_table>
),
target_data AS (
    SELECT *, HASH(*) AS row_hash
    FROM <target_table>
)
SELECT 
    s.<key_column>,
    s.row_hash AS source_hash,
    t.row_hash AS target_hash
FROM source_data s
JOIN target_data t ON s.<key_column> = t.<key_column>
WHERE s.row_hash != t.row_hash
ORDER BY s.<key_column>
LIMIT 100;

-- To see specific column changes, use column-level comparison:
-- SELECT 
--     s.<key_column>,
--     '<column_name>' AS changed_column,
--     s.<column_name> AS source_value,
--     t.<column_name> AS target_value
-- FROM source_data s
-- JOIN target_data t ON s.<key_column> = t.<key_column>
-- WHERE s.row_hash != t.row_hash
--   AND (s.<column_name> != t.<column_name> 
--        OR (s.<column_name> IS NULL AND t.<column_name> IS NOT NULL)
--        OR (s.<column_name> IS NOT NULL AND t.<column_name> IS NULL))
