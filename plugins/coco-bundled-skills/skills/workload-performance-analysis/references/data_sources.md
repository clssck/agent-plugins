# Data Sources

When to use each Snowflake data source for query and performance analysis.

## QUERY_HISTORY

**View:** `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`

- **Use for:** Individual query execution details, specific query ID lookups, single execution analysis. Does not include Hybrid and Interactive table queries — use AGGREGATE_QUERY_HISTORY instead.
- **Latency:** Up to 45 minutes
- **Retention:** 365 days
- **Key columns:** `query_id`, `query_parameterized_hash`, `total_elapsed_time`, `compilation_time`, `execution_time`, `bytes_scanned`, `percentage_scanned_from_cache`, `partitions_scanned`, `partitions_total`, `bytes_spilled_to_local_storage`, `bytes_spilled_to_remote_storage`, `queued_overload_time`, `queued_provisioning_time`, `queued_repair_time`

## INFORMATION_SCHEMA.QUERY_HISTORY()

**Function:** `TABLE(INFORMATION_SCHEMA.QUERY_HISTORY())`

- **Use for:** Real-time query data (< 45 min old), fallback when ACCOUNT_USAGE hasn't caught up
- **Latency:** Real-time
- **Retention:** 7 days, current user only
- **Columns NOT available** (only in ACCOUNT_USAGE): `percentage_scanned_from_cache`, `partitions_scanned`, `partitions_total`, `bytes_spilled_to_local_storage`, `bytes_spilled_to_remote_storage`
- **Column name difference:** `list_external_files_time` (ACCOUNT_USAGE) → `list_external_file_time` (INFORMATION_SCHEMA, singular)

## INFORMATION_SCHEMA.QUERY_HISTORY_BY_SESSION()

**Function:** `TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_SESSION())`

- **Use for:** Looking up queries run in the current session — useful for post-execution comparison when the optimized query is too recent for ACCOUNT_USAGE
- **Latency:** Real-time
- **Retention:** Current session only
- **Key columns available:** `query_id`, `query_text`, `total_elapsed_time`, `compilation_time`, `execution_time`, `rows_produced`, `bytes_scanned`, `bytes_written_to_result`
- **Columns NOT available** (unlike ACCOUNT_USAGE.QUERY_HISTORY): `percentage_scanned_from_cache`, `partitions_scanned`, `partitions_total`, `bytes_spilled_to_local_storage`, `bytes_spilled_to_remote_storage`, `queued_overload_time`
- **Tip:** Use `SELECT *` first to discover available columns if unsure, rather than assuming column names from ACCOUNT_USAGE

## AGGREGATE_QUERY_HISTORY

**View:** `SNOWFLAKE.ACCOUNT_USAGE.AGGREGATE_QUERY_HISTORY`

- **Use for:** Historical trend analysis, high-frequency recurrent query patterns, percentile statistics (p90, p99, p99.9)
- **Latency:** Up to 180 minutes (3 hours)
- **Structure:** Groups by `query_parameterized_hash` in 1-minute intervals. Each row = aggregated stats for multiple executions
- **Key fields:** `calls` (count), statistical objects with `sum/avg/stddev/min/median/p90/p99/max`, `errors` array
- **Benefits over QUERY_HISTORY:** Pre-aggregated = faster execution; built-in percentile stats; better for high-throughput workloads; includes Hybrid and Interactive table queries (which QUERY_HISTORY excludes)
- **Trade-off:** Higher latency, no individual query IDs

## GET_QUERY_OPERATOR_STATS

**Function:** `TABLE(GET_QUERY_OPERATOR_STATS('<QUERY_ID>'))`

- **Use for:** Operator-level deep dive — identifying specific bottleneck operators (joins, scans, filters, aggregations)
- **Retention:** 14 days only
- **Privileges:** Requires OPERATE or MONITOR on warehouse
- **Key fields per operator:** `operator_type`, `operator_statistics` (bytes_scanned, cache_hit_pct, input_rows, output_rows, spill metrics, pruning metrics), `execution_time_breakdown`, `operator_attributes` (table_name, filter_condition)
- **Common operator types:** TableScan, Join, CartesianJoin, Filter, Aggregate, Sort, WindowFunction

## Decision Table

| Use Case | Data Source | Reason |
|---|---|---|
| Look up specific query by ID | QUERY_HISTORY | Need individual execution details |
| Real-time query (< 45 min old) | INFORMATION_SCHEMA | Lower latency |
| Recurrent query trend analysis | AGGREGATE_QUERY_HISTORY | Pre-aggregated percentile stats |
| High-frequency query monitoring | AGGREGATE_QUERY_HISTORY | Optimized for high-throughput |
| Operator-level bottleneck analysis | GET_QUERY_OPERATOR_STATS | Operator breakdown |
| Which table scans hit local disk cache / spilled | GET_QUERY_OPERATOR_STATS | Per-operator I/O metrics |

## Reference

- [QUERY_HISTORY](https://docs.snowflake.com/en/sql-reference/account-usage/query_history)
- [AGGREGATE_QUERY_HISTORY](https://docs.snowflake.com/en/sql-reference/account-usage/aggregate_query_history)
- [GET_QUERY_OPERATOR_STATS](https://docs.snowflake.com/en/sql-reference/functions/get_query_operator_stats)
- [Common Query Problems (Query Profile)](https://docs.snowflake.com/en/user-guide/ui-snowsight-query-profile#common-query-problems-identified-by-query-profile)
