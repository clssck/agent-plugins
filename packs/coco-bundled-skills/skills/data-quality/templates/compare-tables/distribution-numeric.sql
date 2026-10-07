-- Distribution Comparison - Numeric
-- Compare numeric distributions using percentiles
-- Replace <source_table>, <target_table>, <numeric_column>

SELECT 
    'SOURCE' AS version,
    MIN(<numeric_column>) AS min_val,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY <numeric_column>) AS p25,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY <numeric_column>) AS median,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY <numeric_column>) AS p75,
    MAX(<numeric_column>) AS max_val,
    ROUND(AVG(<numeric_column>), 2) AS mean_val,
    ROUND(STDDEV(<numeric_column>), 2) AS stddev_val,
    COUNT(*) AS row_count,
    COUNT(<numeric_column>) AS non_null_count,
    COUNT(*) - COUNT(<numeric_column>) AS null_count
FROM <source_table>
UNION ALL
SELECT 
    'TARGET' AS version,
    MIN(<numeric_column>) AS min_val,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY <numeric_column>) AS p25,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY <numeric_column>) AS median,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY <numeric_column>) AS p75,
    MAX(<numeric_column>) AS max_val,
    ROUND(AVG(<numeric_column>), 2) AS mean_val,
    ROUND(STDDEV(<numeric_column>), 2) AS stddev_val,
    COUNT(*) AS row_count,
    COUNT(<numeric_column>) AS non_null_count,
    COUNT(*) - COUNT(<numeric_column>) AS null_count
FROM <target_table>;

-- Interpretation:
-- Compare p25, median, p75 to detect distribution shifts
-- Large stddev differences may indicate outliers
-- Increased null_count may indicate data quality issues
