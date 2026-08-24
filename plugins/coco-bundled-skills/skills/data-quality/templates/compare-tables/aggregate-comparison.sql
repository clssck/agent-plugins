-- Aggregate Comparison
-- Compare aggregate metrics between source and target tables
-- Replace <source_table>, <target_table>, <key_column>, and optionally add numeric columns

WITH source_agg AS (
    SELECT 
        'SOURCE' AS version,
        COUNT(*) AS row_count,
        COUNT(DISTINCT <key_column>) AS unique_keys
        -- Add numeric aggregates as needed:
        -- , SUM(<numeric_col>) AS sum_<col>
        -- , AVG(<numeric_col>) AS avg_<col>
        -- , MIN(<numeric_col>) AS min_<col>
        -- , MAX(<numeric_col>) AS max_<col>
    FROM <source_table>
),
target_agg AS (
    SELECT 
        'TARGET' AS version,
        COUNT(*) AS row_count,
        COUNT(DISTINCT <key_column>) AS unique_keys
        -- Add same numeric aggregates
    FROM <target_table>
)
SELECT 
    s.row_count AS source_rows,
    t.row_count AS target_rows,
    t.row_count - s.row_count AS row_diff,
    ROUND((t.row_count - s.row_count) * 100.0 / NULLIF(s.row_count, 0), 2) AS row_diff_pct,
    s.unique_keys AS source_unique_keys,
    t.unique_keys AS target_unique_keys,
    t.unique_keys - s.unique_keys AS key_diff
FROM source_agg s, target_agg t;

-- Interpretation:
-- row_diff > 0: Target has more rows (additions)
-- row_diff < 0: Target has fewer rows (removals)
-- key_diff != row_diff: Some keys have duplicates
