---
parent_skill: data-quality
---

# Data Diff Concepts

## Overview

Data diff is the process of comparing two tables to identify row-level differences. This is essential for validating data pipeline changes, migrations, and ensuring data consistency across environments.

## Key Concepts

### 1. Source vs Target Tables

| Term | Definition | Example |
|------|------------|---------|
| **Source** | Baseline/before table (reference) | Production table, old version |
| **Target** | New/after table (being validated) | Staging table, new version |

**Convention:** Compare TARGET against SOURCE. Differences are reported as changes from source to target.

### 2. Primary Key

The primary key uniquely identifies rows for comparison:

```sql
-- Single key
-k user_id

-- Compound key (multiple columns)
-k order_id -k line_item_id
```

**Why it matters:**
- Without a key, rows can't be matched between tables
- Wrong key leads to incorrect diff results
- Compound keys handle multi-column uniqueness

### 3. Types of Differences

| Difference Type | Description | Meaning |
|-----------------|-------------|---------|
| **Added** | Row exists in target but not source | New data inserted |
| **Removed** | Row exists in source but not target | Data deleted |
| **Modified** | Row exists in both but values differ | Data updated |
| **Unchanged** | Row exists in both with same values | No change |

### 4. The data_diff Tool

The `data_diff` tool provides efficient row-level comparison between Snowflake tables.

**Connection String Format:**
```
snowflake://<connection_name>/DATABASE/SCHEMA
```

**CRITICAL:** Wrap the connection name in angle brackets `< >`. Use the connection name from `snowflake_connections_list`.

**Example:** If your connection is named "prod_snowflake":
```
snowflake://<prod_snowflake>/ANALYTICS_DB/PUBLIC
```

### 5. Tool Options Reference

| Option | Description | Example |
|--------|-------------|---------|
| `-k` | Primary key column (required) | `-k user_id` |
| `-c` | Columns to compare | `-c %` (all) or `-c name -c email` |
| `-s` | Summary statistics only | `-s` |
| `-w` | WHERE clause filter | `-w "created_at > '2024-01-01'"` |
| `-m` | Materialize results to table | `-m DIFF_RESULTS_%t` |
| `--case-sensitive` | Case-sensitive column names | `--case-sensitive` |

### 6. Common Usage Patterns

**Same-database comparison:**
```bash
"snowflake://<connection>/DATABASE/SCHEMA" table_v1 table_v2 -k id -c %
```

**Cross-database comparison:**
```bash
"snowflake://<connection>/PROD_DB/PUBLIC" users "snowflake://<connection>/STAGING_DB/PUBLIC" users -k user_id -c %
```

**Cross-account comparison:**
```bash
"snowflake://<prod_conn>/PROD_DB/PUBLIC" users "snowflake://<staging_conn>/STAGING_DB/PUBLIC" users -k user_id -c %
```

**Summary only (faster for large tables):**
```bash
"snowflake://<connection>/DB/SCHEMA" t1 t2 -k id -c % -s
```

**Filter to specific date range:**
```bash
"snowflake://<connection>/DB/SCHEMA" t1 t2 -k id -c % -w "order_date >= '2024-01-01'"
```

**Compare specific columns:**
```bash
"snowflake://<connection>/DB/SCHEMA" t1 t2 -k id -c name -c email -c status
```

**Save results for audit:**
```bash
"snowflake://<connection>/DB/SCHEMA" t1 t2 -k id -c % -m AUDIT_DIFF_%t
```
The `%t` placeholder creates a timestamp suffix.

### 7. Understanding Output

**Summary output (`-s` flag):**
```
Rows added: 150
Rows removed: 25
Rows with differences: 0
```

**Detailed output (without `-s`):**
Shows actual row values with `+` for added and `-` for removed:
```
- | 1001 | john@old.com | inactive
+ | 1001 | john@new.com | active
```

### 8. When to Use Each Comparison Type

| Scenario | Approach |
|----------|----------|
| Quick validation | `-s` flag for summary counts |
| Migration sign-off | Full diff without `-s` |
| Large tables (>1M rows) | Use `-w` filter + `-s` |
| Audit trail needed | Use `-m` to materialize |
| Column-specific validation | Use `-c col1 -c col2` |

### 9. Performance Considerations

**For large tables:**
1. Start with `-s` (summary) to get counts
2. Add `-w` filter to limit scope
3. Run full diff only on filtered subset

**Example workflow:**
```bash
# Step 1: Quick summary
"snowflake://<conn>/DB/SCHEMA" big_table_v1 big_table_v2 -k id -c % -s

# Step 2: If differences found, filter to recent data
"snowflake://<conn>/DB/SCHEMA" big_table_v1 big_table_v2 -k id -c % -w "updated_at > CURRENT_DATE - 7"
```

### 10. Comparison Strategies

#### Strategy 1: Full Table Comparison
Compare all rows across entire tables.
- **Use when:** Tables are small (<100K rows) or thorough validation required
- **Command:** `... -k key -c %`

#### Strategy 2: Incremental Comparison
Compare only recent/changed data.
- **Use when:** Tables are large, only recent changes matter
- **Command:** `... -k key -c % -w "modified_date > '2024-01-01'"`

#### Strategy 3: Column-Specific Comparison
Compare only specific columns of interest.
- **Use when:** Some columns are expected to differ (timestamps, audit fields)
- **Command:** `... -k key -c col1 -c col2 -c col3`

#### Strategy 4: Summary-First Approach
Get summary counts before detailed diff.
- **Use when:** Don't know the scale of differences
- **Command:** `... -k key -c % -s` then remove `-s` if needed

## SQL Alternatives

For cases where the data_diff tool isn't suitable, use SQL templates.

### Row Count Comparison
```sql
SELECT 'SOURCE' AS table_version, COUNT(*) AS row_count FROM source_table
UNION ALL
SELECT 'TARGET' AS table_version, COUNT(*) AS row_count FROM target_table;
```

### Hash-Based Quick Check
```sql
SELECT 
    CASE WHEN src_hash = tgt_hash THEN 'IDENTICAL' ELSE 'DIFFERENT' END AS result
FROM (
    SELECT 
        (SELECT SUM(HASH(*)) FROM source_table) AS src_hash,
        (SELECT SUM(HASH(*)) FROM target_table) AS tgt_hash
);
```

### Find Added Rows (SQL)
```sql
SELECT t.*
FROM target_table t
LEFT JOIN source_table s ON t.key_col = s.key_col
WHERE s.key_col IS NULL;
```

### Find Removed Rows (SQL)
```sql
SELECT s.*
FROM source_table s
LEFT JOIN target_table t ON s.key_col = t.key_col
WHERE t.key_col IS NULL;
```

## Privilege Requirements

| Operation | Required Privilege |
|-----------|-------------------|
| Compare tables | SELECT on both tables |
| Cross-database diff | SELECT on tables in both databases |
| Materialize results | CREATE TABLE on target schema |
| Use connection | Valid Snowflake connection configured |

## Best Practices

1. **Always specify a key**: Without `-k`, comparison fails
2. **Start with summary**: Use `-s` first to understand scale
3. **Filter large tables**: Use `-w` to limit comparison scope
4. **Use `-c %` for thoroughness**: Compare all columns unless specific columns needed
5. **Materialize for audit**: Use `-m` when results need to be retained
6. **Verify connection**: Ensure connection name matches your configuration

## Common Issues

| Issue | Solution |
|-------|----------|
| "Connection not found" | Check connection name with `cortex connections list` |
| Timeout on large table | Add `-w` filter or use `-s` for summary |
| "Column not found" | Verify key column exists in both tables |
| Permission denied | Ensure SELECT access on both tables |
| Wrong row counts | Verify primary key is truly unique |

## Next Steps

After understanding concepts:

1. **For quick comparison**: Use `workflows/summary-diff.md`
2. **For row-level details**: Use `workflows/row-level-diff.md`
3. **For schema validation**: Use `workflows/schema-comparison.md`
4. **For statistical analysis**: Use `workflows/distribution-analysis.md`
5. **For full migration sign-off**: Use `workflows/validation-report.md`
