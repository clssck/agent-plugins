# Table Summary

**This is a Phase 1 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Present a high-level performance overview for a specific table, including table type detection and pruning efficiency.

## Workflow

### Step 1: Find the Table and Check Type

**[IMPORTANT] Check table type FIRST before any analysis.**

**Primary: Use `SHOW TABLES`** (no latency, no warehouse needed, returns `is_hybrid`, `cluster_by`, `search_optimization`):

If the fully qualified name (database.schema.table) is provided:
```sql
SHOW TABLES LIKE '<TABLE_NAME>' IN SCHEMA <DATABASE>.<SCHEMA> LIMIT 20;
```

If only the table name is provided:
```sql
SHOW TABLES LIKE '%<TABLE_NAME>%' IN ACCOUNT LIMIT 20;
```

Check the `is_hybrid` column (Y/N) in the result.

**Fallback: If `SHOW TABLES` fails** (permissions, too many results, etc.), fall back to `ACCOUNT_USAGE.TABLES` (up to 90 min latency):
```sql
SELECT table_catalog, table_schema, table_name, table_type, is_hybrid, clustering_key
FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
WHERE table_name = UPPER('<TABLE_NAME>')
  AND deleted IS NULL
ORDER BY last_altered DESC
LIMIT 20;
```

Check the `IS_HYBRID` column (YES/NO) in the result.

### Step 2: Handle Hybrid Tables

**If is_hybrid = 'Y', STOP and respond:**
```
The table <DATABASE>.<SCHEMA>.<TABLE> is a Hybrid Table.

[IMPORTANT] The following features are NOT supported for hybrid tables:
- Search Optimization Service
- Clustering keys (data is ordered by primary key only)
- Query Acceleration Service (QAS)

Hybrid tables do not appear in pruning history views. For performance optimization, consider:
- Reviewing primary key design for your access patterns
- Adding secondary indexes for frequent query patterns
- Using appropriate warehouse sizing

For more information: https://docs.snowflake.com/en/user-guide/tables-hybrid-limitations
```

**DO NOT query pruning history for hybrid tables — it will return no results.**

### Step 3: Present Table Summary (non-hybrid only)

From the SHOW TABLES result (Step 1), extract: `cluster_by`, `search_optimization`, `rows`, `bytes`.

Then **[MANDATORY]** fetch and execute the exact SQL from the following verified queries in the semantic model, scoped to this table by adding `AND table_name ILIKE '<name>'` (and `AND database_name = '<DB>' AND schema_name = '<SCHEMA>'` if known). Do NOT rewrite or regenerate these queries.

1. **Pruning efficiency** — verified query: `Pruning opportunity, sorted by the potential to avoid partitions`
2. **Column usage** — verified query: `Identification of columns that have opportunities to improve pruning rate`
3. **Search optimization candidates** — verified query: `Identification of columns that could benefit from search to reduce scan volume`

Present:
```
## Table Performance: <DATABASE>.<SCHEMA>.<TABLE> — Last 7 Days

| Property | Value |
|---|---|
| Clustering Key | <cluster_by or "None"> |
| Search Optimization | <ON/OFF> |
| Rows | <row_count> |
| Query Count | <from pruning query> |
| Avg Pruning Rate | <partition_unused_percentage>% |
| Avg Excess Rows Scanned per Query | <avg_excess_rows_scanned> |
| Top Filtered Columns | <top 3 from column usage> |
| SOS Candidates | <count from search optimization query> |
```

**[STOP]** Present the summary table. Ask: "Want me to analyze clustering health and pruning patterns, or provide recommendations?"
