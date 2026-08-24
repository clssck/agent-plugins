# Operations Reference

Scheduling, monitoring, error handling, and permissions for Snowflake Task Graph DAGs.

---

## Scheduling

### Schedule Types

| Type | Example | Use Case |
|------|---------|----------|
| `timedelta` | `schedule=timedelta(hours=6)` | Simple intervals |
| `Cron` | `schedule=Cron("0 9 * * *", "America/Los_Angeles")` | Production, timezone-aware |
| `None` | `schedule=None` | Manual-only, event-driven |

### Pause, Resume, Manual Execution

```sql
-- Suspend/resume (alter ROOT task only)
ALTER TASK <DATABASE>.<SCHEMA>.<ROOT_TASK_NAME> SUSPEND;
ALTER TASK <DATABASE>.<SCHEMA>.<ROOT_TASK_NAME> RESUME;

-- Manual trigger
EXECUTE TASK <DATABASE>.<SCHEMA>.<ROOT_TASK_NAME>;
```

```python
dag_op.run(dag)                # Trigger immediate run
dag_op.run(dag, retry_last=True)  # Retry last failed
```

---

## Monitoring

### Snowsight UI

**Monitoring > Task History** → Filter by DAG name.

### TASK_HISTORY() Queries

```sql
-- Last 24 hours of failures
SELECT *
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
    SCHEDULED_TIME_RANGE_START => DATEADD('day', -1, CURRENT_TIMESTAMP()),
    ROOT_TASK_ID => '<ROOT_TASK_ID>',
    ERROR_ONLY => TRUE
))
ORDER BY SCHEDULED_TIME DESC;

-- All runs for a DAG (last 7 days)
SELECT NAME, STATE, SCHEDULED_TIME, COMPLETED_TIME, ERROR_MESSAGE
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
    SCHEDULED_TIME_RANGE_START => DATEADD('day', -7, CURRENT_TIMESTAMP()),
    ROOT_TASK_ID => '<ROOT_TASK_ID>'
))
ORDER BY SCHEDULED_TIME DESC;
```

### Task States

| State | Description |
|-------|-------------|
| `SCHEDULED` | Queued |
| `EXECUTING` | Running |
| `SUCCEEDED` | Completed |
| `FAILED` | Error occurred |
| `SKIPPED` | Branch not taken or predecessor failed |

### Python Monitoring

```python
failed_runs = dag_op.get_complete_dag_runs(dag, error_only=True)
all_runs = dag_op.get_complete_dag_runs(dag, error_only=False)
current_runs = dag_op.get_current_dag_runs(dag)
```

> For ML Job monitoring (logs, GPU utilization), see **`../ml-jobs/SKILL.md`** → `get_job()`, `get_logs()`.

---

## Error Handling & Retry

### Task Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `task_auto_retry_attempts` | `0` | Auto retries on failure |
| `suspend_task_after_num_failures` | `10` | Auto-suspend after N failures |
| `user_task_timeout_ms` | `3600000` | Max execution time (1 hour) |

```python
# Set on DAG (applies to all tasks)
dag = DAG(
    name="MY_PIPELINE",
    task_auto_retry_attempts=2,
    suspend_task_after_num_failures=5,
    user_task_timeout_ms=7200000,  # 2 hours
    ...
)

# Or set on individual task
train_task = DAGTask("TRAIN", train_model, warehouse=WH, user_task_timeout_ms=7200000)
```

### Finalizer Tasks

Always run regardless of success/failure:

```python
cleanup_task = DAGTask("CLEANUP", cleanup, warehouse=WAREHOUSE, is_finalizer=True)
```

---

## Permissions

### Task-Specific Privileges (Commonly Missing)

```sql
GRANT CREATE TASK ON SCHEMA <database>.<schema> TO ROLE <role>;
GRANT EXECUTE TASK ON ACCOUNT TO ROLE <role>;
GRANT EXECUTE MANAGED TASK ON ACCOUNT TO ROLE <role>;  -- for serverless schedules
```

### Task Ownership Rule

All tasks in a DAG must have the **same owner role**.

```sql
SHOW TASKS LIKE '%MY_DAG%' IN SCHEMA <DATABASE>.<SCHEMA>;
-- Check "owner" column — all must match
```
