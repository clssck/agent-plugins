# Single Query Detection

**This is a Phase 2 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Classify the primary bottleneck for a single query based on its execution metrics, and offer operator-level drill-down.

## Prerequisites

- Query metrics already fetched by `query/summary/SKILL.md`
- Access to `GET_QUERY_OPERATOR_STATS` (for operator-level analysis, 14-day retention)

## Workflow

### Step 1: Classify Bottleneck

Based on the metrics from the summary phase, classify the primary bottleneck:

| Indicator | Bottleneck Type | Severity |
|---|---|---|
| `remote_spill_gb > 0` | **Spilling** | Critical if remote > 1GB |
| `local_spill_gb > 0` AND `remote_spill_gb = 0` | **Spilling** | Moderate |
| Pruning efficiency < 50% (partitions_scanned / partitions_total > 0.5) | **Poor Pruning** | High if large table |
| `cache_hit_pct < 10` AND `gb_scanned > 1` | **Cache Miss** | Moderate |
| `queued_overload_seconds > execution_seconds * 0.2` | **Queue Contention (Overload)** | High — warehouse compute fully utilized |
| `queued_provisioning_seconds > 5` | **Queue Contention (Provisioning)** | Low — warehouse resuming from suspended state |
| `queued_repair_seconds > 0` | **Queue Contention (Repair)** | Rare — warehouse repair in progress |
| `compilation_seconds > execution_seconds` | **Compilation Heavy** | Unusual |

**Queue metric definitions** (all in milliseconds in raw data, converted to seconds in summary):
- `queued_overload_time`: Time waiting because all warehouse compute resources were in use by other queries
- `queued_provisioning_time`: Time waiting for warehouse to resume from suspended state or provision new resources
- `queued_repair_time`: Time waiting for warehouse repair operations

Present the classification:
```
### Primary Bottleneck: <TYPE>
- <Evidence from metrics>
- <Impact description>
```

### Step 2: Operator-Level Drill-Down (optional)

Based on bottleneck type, offer operator-level analysis using `GET_QUERY_OPERATOR_STATS` (14-day retention).

**If multiple bottleneck types are detected (e.g., spilling AND poor pruning), the operator queries for each are independent — execute them in parallel.**

**For Local Disk Cache Miss bottleneck** — show which table scans had worst cache:
```sql
SELECT
    operator_id,
    operator_type,
    operator_statistics:io.bytes_scanned::NUMBER AS bytes_scanned,
    operator_statistics:io.percentage_scanned_from_cache::NUMBER AS cache_hit_pct,
    operator_attributes:table_name::STRING AS table_name
FROM TABLE(GET_QUERY_OPERATOR_STATS('<QUERY_ID>'))
WHERE operator_type = 'TableScan'
ORDER BY operator_statistics:io.bytes_scanned::NUMBER DESC;
```

**For Poor Pruning bottleneck** — show per-table-scan partition stats:
```sql
SELECT
    operator_id,
    operator_type,
    operator_statistics:pruning.partitions_scanned::NUMBER AS partitions_scanned,
    operator_statistics:pruning.partitions_total::NUMBER AS partitions_total,
    operator_attributes:table_name::STRING AS table_name,
    operator_attributes:filter_condition::STRING AS filter_condition
FROM TABLE(GET_QUERY_OPERATOR_STATS('<QUERY_ID>'))
WHERE operator_type = 'TableScan'
ORDER BY operator_id;
```

**For Spilling bottleneck** — show which operators spilled:
```sql
SELECT
    operator_id,
    operator_type,
    operator_statistics:io.bytes_spilled_to_local_storage::NUMBER AS bytes_spilled_local,
    operator_statistics:io.bytes_spilled_to_remote_storage::NUMBER AS bytes_spilled_remote,
    execution_time_breakdown:overall_percentage::NUMBER AS execution_time_pct
FROM TABLE(GET_QUERY_OPERATOR_STATS('<QUERY_ID>'))
WHERE operator_statistics:io.bytes_spilled_to_local_storage::NUMBER > 0
   OR operator_statistics:io.bytes_spilled_to_remote_storage::NUMBER > 0
ORDER BY execution_time_breakdown:overall_percentage::NUMBER DESC;
```

**Co-located SQL root cause check:** If spilling is detected, also check whether a Join operator on the same `operator_id` (or nearby in the plan) has `output_rows >> input_rows` (indicating an exploding join). If so, flag it: "Spilling may be caused by an exploding join at operator <ID> — the SQL-level root cause should be addressed first in the recommendation phase (see `references/query_insights.md` — Co-Located Spillage Detection)."

### Step 3: Offer Comparison Analysis

If the user wants to compare this execution with another, validate they share the same `query_parameterized_hash` (see `references/query_hash_concepts.md`):

- **Query comparison**: "Want to compare this with another execution of the same query?"
  - If user provides a second query ID, validate they share the same `query_parameterized_hash`
  - If hashes match, offer operator-level comparison:
    ```sql
    WITH q1 AS (
        SELECT operator_id, operator_type,
            operator_statistics:input_rows::NUMBER AS input_rows,
            operator_statistics:output_rows::NUMBER AS output_rows,
            operator_statistics:io.bytes_scanned::NUMBER AS bytes_scanned,
            operator_statistics:io.percentage_scanned_from_cache::NUMBER AS cache_hit_pct,
            execution_time_breakdown:overall_percentage::NUMBER AS exec_time_pct
        FROM TABLE(GET_QUERY_OPERATOR_STATS('<QUERY1_ID>'))
    ),
    q2 AS (
        SELECT operator_id, operator_type,
            operator_statistics:input_rows::NUMBER AS input_rows,
            operator_statistics:output_rows::NUMBER AS output_rows,
            operator_statistics:io.bytes_scanned::NUMBER AS bytes_scanned,
            operator_statistics:io.percentage_scanned_from_cache::NUMBER AS cache_hit_pct,
            execution_time_breakdown:overall_percentage::NUMBER AS exec_time_pct
        FROM TABLE(GET_QUERY_OPERATOR_STATS('<QUERY2_ID>'))
    )
    SELECT
        COALESCE(q1.operator_id, q2.operator_id) AS operator_id,
        COALESCE(q1.operator_type, q2.operator_type) AS operator_type,
        q1.exec_time_pct AS q1_exec_time_pct,
        q2.exec_time_pct AS q2_exec_time_pct,
        (q2.exec_time_pct - q1.exec_time_pct) AS exec_time_pct_delta,
        q1.bytes_scanned AS q1_bytes_scanned,
        q2.bytes_scanned AS q2_bytes_scanned,
        q1.cache_hit_pct AS q1_cache_pct,
        q2.cache_hit_pct AS q2_cache_pct
    FROM q1 FULL OUTER JOIN q2 ON q1.operator_id = q2.operator_id
    ORDER BY COALESCE(q1.operator_id, q2.operator_id);
    ```
  - If hashes don't match, explain why comparison isn't valid (reference `references/query_hash_concepts.md`)

**[STOP]** Wait for user to choose: "Want me to compare with another execution, analyze the full query pattern, or proceed to recommendations?"
