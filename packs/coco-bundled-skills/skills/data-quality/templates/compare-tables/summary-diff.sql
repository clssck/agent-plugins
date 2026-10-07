-- Summary Diff Statistics
-- Get summary of all differences between tables
-- Replace <source_table>, <target_table>, <key_column>

WITH source_keys AS (
    SELECT <key_column>, HASH(*) AS row_hash
    FROM <source_table>
),
target_keys AS (
    SELECT <key_column>, HASH(*) AS row_hash
    FROM <target_table>
),
diff_summary AS (
    SELECT 
        SUM(CASE WHEN s.<key_column> IS NULL THEN 1 ELSE 0 END) AS rows_added,
        SUM(CASE WHEN t.<key_column> IS NULL THEN 1 ELSE 0 END) AS rows_removed,
        SUM(CASE WHEN s.<key_column> IS NOT NULL AND t.<key_column> IS NOT NULL 
                 AND s.row_hash != t.row_hash THEN 1 ELSE 0 END) AS rows_modified,
        SUM(CASE WHEN s.<key_column> IS NOT NULL AND t.<key_column> IS NOT NULL 
                 AND s.row_hash = t.row_hash THEN 1 ELSE 0 END) AS rows_unchanged
    FROM source_keys s
    FULL OUTER JOIN target_keys t ON s.<key_column> = t.<key_column>
)
SELECT 
    rows_added,
    rows_removed,
    rows_modified,
    rows_unchanged,
    rows_added + rows_removed + rows_modified + rows_unchanged AS total_rows,
    CASE 
        WHEN rows_added + rows_removed + rows_modified = 0 THEN 'IDENTICAL'
        WHEN rows_modified > 0 THEN 'MODIFIED'
        WHEN rows_added > 0 AND rows_removed > 0 THEN 'CHANGED'
        WHEN rows_added > 0 THEN 'ADDITIONS_ONLY'
        WHEN rows_removed > 0 THEN 'REMOVALS_ONLY'
        ELSE 'UNKNOWN'
    END AS diff_status
FROM diff_summary;

-- Interpretation:
-- IDENTICAL: No differences found
-- MODIFIED: Some rows have changed values
-- CHANGED: Both additions and removals
-- ADDITIONS_ONLY: Only new rows added
-- REMOVALS_ONLY: Only rows removed
