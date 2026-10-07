-- Distribution Comparison - Categorical
-- Compare value distributions for categorical columns
-- Replace <source_table>, <target_table>, <column_name>

WITH source_dist AS (
    SELECT 
        <column_name> AS value,
        COUNT(*) AS source_count,
        ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS source_pct
    FROM <source_table>
    GROUP BY <column_name>
),
target_dist AS (
    SELECT 
        <column_name> AS value,
        COUNT(*) AS target_count,
        ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS target_pct
    FROM <target_table>
    GROUP BY <column_name>
)
SELECT 
    COALESCE(s.value, t.value) AS value,
    COALESCE(s.source_count, 0) AS source_count,
    COALESCE(t.target_count, 0) AS target_count,
    COALESCE(s.source_pct, 0) AS source_pct,
    COALESCE(t.target_pct, 0) AS target_pct,
    ROUND(COALESCE(t.target_pct, 0) - COALESCE(s.source_pct, 0), 2) AS pct_shift
FROM source_dist s
FULL OUTER JOIN target_dist t ON s.value = t.value
ORDER BY ABS(COALESCE(t.target_pct, 0) - COALESCE(s.source_pct, 0)) DESC;

-- Interpretation:
-- pct_shift > 0: Value is more common in target
-- pct_shift < 0: Value is less common in target
-- Large shifts may indicate data quality issues
