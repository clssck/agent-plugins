# Query Hash Concepts

Understanding `query_parameterized_hash` for query pattern analysis and comparison.

## What is a Query Parameterized Hash?

A unique identifier for a query pattern that abstracts away literal values. Two queries with the same structure but different literal values share the same hash.

```sql
-- These two queries have the SAME parameterized hash:
SELECT * FROM users WHERE user_id = 123;
SELECT * FROM users WHERE user_id = 456;
```

## Where It Appears

Available in these views/functions:
- `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`
- `SNOWFLAKE.ACCOUNT_USAGE.AGGREGATE_QUERY_HISTORY`
- `SNOWFLAKE.ACCOUNT_USAGE.TABLE_QUERY_PRUNING_HISTORY`
- `SNOWFLAKE.ACCOUNT_USAGE.COLUMN_QUERY_PRUNING_HISTORY`

## Using for Comparison

For an apples-to-apples comparison of two query executions:
1. Both must have the **same `query_parameterized_hash`** (same query structure)
2. Both should have the **same `query_parameterized_hash_version`** (same hash algorithm)

### Hash Mismatch Causes

| Scenario | Meaning | Action |
|---|---|---|
| Different hash | Different SQL structure (tables, joins, columns, WHERE clauses) | Not comparable — use `find-matching-queries` to find valid comparisons |
| Different hash version | Snowflake internal hash algorithm changed between releases | Check actual `query_text` — if SQL is identical, comparison is still valid despite version mismatch |

## Finding Other Executions of a Pattern

```sql
SELECT
    query_id,
    start_time,
    total_elapsed_time,
    execution_status,
    warehouse_name,
    warehouse_size
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_parameterized_hash = '<HASH>'
  AND query_parameterized_hash_version = <VERSION>
  AND start_time >= DATEADD('day', -7, CURRENT_DATE())
ORDER BY start_time DESC
LIMIT 20;
```

## Reference

- [Query Hash Documentation](https://docs.snowflake.com/en/user-guide/query-hash)
- [QUERY_HISTORY](https://docs.snowflake.com/en/sql-reference/account-usage/query_history)
