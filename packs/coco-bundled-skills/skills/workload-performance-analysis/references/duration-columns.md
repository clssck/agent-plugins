# Duration Column Reference

Reference for `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` duration columns used by the stored-procedure analysis sub-skills (and applicable to general query analysis).

---

## Read This When

- Interpreting duration breakdown results
- User asks what a specific duration column means
- Explaining where time is spent in a query or procedure execution
- Building insights or recommendations based on duration patterns

## Do NOT Read This When

- Initial parameter gathering (Phase 1 Step 1 in any sub-skill)
- Just running the parent / call-tree query in `stored-procedure/summary`

---

## Duration Columns (all values in milliseconds)

### Primary Duration Categories

| Column | Description | What High Values Indicate |
|---|---|---|
| `total_elapsed_time` | Total wall-clock time | Overall execution time |
| `execution_time` | Compute execution time | Compute-intensive query |
| `compilation_time` | Time spent compiling the query | Complex query or cold cache |

### Queue-Related Durations

| Column | Description | What High Values Indicate |
|---|---|---|
| `queued_overload_time` | Time queued due to warehouse overload | Warehouse undersized or contention |
| `queued_provisioning_time` | Time queued waiting for warehouse to provision, resume, or resize | Warehouse was suspended or scaling |
| `queued_repair_time` | Time queued for warehouse repair | Warehouse repair in progress |

### Lock and Wait Durations

| Column | Description | What High Values Indicate |
|---|---|---|
| `transaction_blocked_time` | Time blocked by concurrent DML | Lock contention with concurrent writes |
| `list_external_files_time` | Time listing external files | External storage latency |

---

## Duration Percentage Thresholds

Use these thresholds to classify a query or procedure profile:

| Metric | Threshold | Classification |
|---|---|---|
| `execution_time / total_elapsed_time` | > 90% | Compute-intensive |
| `compilation_time / total_elapsed_time` | > 30% | Compilation-heavy |
| `queued_overload_time / total_elapsed_time` | > 10% | Queue delays present |
| `queued_provisioning_time / total_elapsed_time` | > 10% | Warehouse provisioning delays |
| `transaction_blocked_time / total_elapsed_time` | > 5% | Lock contention |
| `other_time / total_elapsed_time` | > 30% | Significant unattributed overhead |

---

## "Other" Time (Computed)

The 7 exposed duration columns do not cover all of a query's wall-clock time. Compute the residual "other" bucket as:

```
other_time = total_elapsed_time
           - compilation_time
           - execution_time
           - queued_overload_time
           - queued_provisioning_time
           - queued_repair_time
           - transaction_blocked_time
           - list_external_files_time
```

This bucket captures GS execution, scheduling overhead, gateway waits, and other internal processing that ACCOUNT_USAGE does not break out individually. A high `other_time` ratio (> 30%) usually indicates many small sub-operations (e.g. heavy DDL or metadata churn inside a procedure body).
