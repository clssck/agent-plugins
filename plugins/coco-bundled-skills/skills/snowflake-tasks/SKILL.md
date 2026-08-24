---
name: snowflake-tasks
description: "**[REQUIRED]** Use for **ALL** Snowflake Task operations: creating, scheduling, managing, monitoring, and troubleshooting tasks and task graphs. This is the required entry point for any task-related work. Triggers: task, tasks, scheduled task, cron task, task graph, DAG, task chain, task pipeline, triggered task, stream trigger, WHEN condition, SYSTEM$STREAM_HAS_DATA, suspend task, resume task, alter task, drop task, task history, task failure, auto-suspended, SUSPEND_TASK_AFTER_NUM_FAILURES, serverless task, finalizer task, task permissions, EXECUTE TASK, task schedule, task monitoring, parameterized task, CONFIG, SYSTEM$GET_TASK_GRAPH_CONFIG, runtime parameters, configurable pipeline, return value, pass data between tasks, SYSTEM$SET_RETURN_VALUE, SYSTEM$GET_PREDECESSOR_RETURN_VALUE, inter-task communication."
---

# Snowflake Tasks

## Mandatory Rules

**Before writing AI function SQL, read `../sql-author/SKILL.md`.**

Expert guidance for Snowflake Tasks: creating scheduled and triggered tasks, building task graphs (DAGs), managing task lifecycle, monitoring execution history, and troubleshooting failures.

## When to Use

Use this skill when users ask about:
- Creating tasks with CRON or interval schedules
- Creating stream-triggered tasks with WHEN conditions
- Building task graphs (parent/child task chains, fan-out/fan-in DAGs)
- Suspending, resuming, or modifying tasks
- Monitoring task run history and investigating failures
- Troubleshooting auto-suspended tasks or permission issues
- Configuring serverless tasks or finalizer tasks
- Managing task execution privileges and roles

## Scheduling

Snowflake supports two schedule syntaxes. Use the right one for the situation:

- **Interval schedule** (`SCHEDULE = '43 MINUTE'`): For recurring intervals like "every N minutes" or "every N hours". This is the correct and simplest way to express a fixed-frequency schedule.
- **CRON schedule** (`SCHEDULE = 'USING CRON 0 2 * * MON America/Los_Angeles'`): For calendar-based schedules like "at 2 AM every Monday" or "at the top of every hour".
- **No schedule**: For stream-based tasks ("triggered tasks") which are purely event-driven, and child or finalizer tasks in a task DAG which run after their parent task(s) have finished.

When the user says "every N minutes" or "every N hours", always use an interval schedule — never CRON. Only use CRON when the user explicitly asks for CRON, or when their schedule requires a specific time of day, day of week, or timezone.
- "Every hour" -> `SCHEDULE = '60 MINUTE'` (interval)
- "Every 30 minutes" -> `SCHEDULE = '30 MINUTE'` (interval)
- "Every night at midnight" -> `SCHEDULE = 'USING CRON 0 0 * * * UTC'` (CRON — specific time required)

**Important:** CRON expressions cannot accurately represent arbitrary intervals. For example, `*/43 * * * *` does NOT mean "every 43 minutes" — it fires at minutes 0 and 43 of every hour. Always use interval syntax for interval-based schedules.

**Stream-triggered tasks:** For tasks that process stream data, use a `WHEN` condition with `SYSTEM$STREAM_HAS_DATA` and no schedule unless the user explicitly requests one. Do not add a `SCHEDULE` clause to a stream-triggered task unless the user specifically asks for one — a task with only a `WHEN` condition is a valid, purely event-driven task. If the user does request one, follow the same scheduling guidance above for CRON vs. Interval schedules.

If the task body SQL uses any AI or Cortex function, read `../sql-author/SKILL.md` first.

## Modifying Tasks

Before running `ALTER TASK` on any task, the **root task of its graph must be suspended**. This applies to all tasks — standalone tasks (which are their own root), child tasks, and finalizer tasks.

**If you already know the root task AND you know it is resumed** (e.g., from `SHOW TASKS` output or because you created the graph), suspend it first:

```sql
ALTER TASK root_task SUSPEND;
ALTER TASK child_task ... ;
ALTER TASK root_task RESUME;
```

**If you don't know the root task OR you don't know if it is resumed**, the fastest approach is to attempt the `ALTER TASK` directly. Snowflake will return an error identifying the root task that needs to be suspended. Read the error message, suspend the named root task, then retry the alter.

After modifying, resume the root task if it was resumed before modification to restart the graph. If it was already suspended, leave it suspended unless the user requests you to start it.

### ALTER TASK syntax

Most task properties are changed with `SET` / `UNSET`:

```sql
ALTER TASK my_task SET WAREHOUSE = 'NEW_WH';
ALTER TASK my_task SET SCHEDULE = '30 MINUTE';
ALTER TASK my_task UNSET SCHEDULE;
ALTER TASK my_task SET FINALIZE = my_db.my_schema.root_task;
ALTER TASK my_task UNSET FINALIZE;
```

Exceptions that use special syntax:

- **Task body (SQL definition):** `ALTER TASK my_task MODIFY AS <new_sql>`.
- **WHEN condition:** `ALTER TASK my_task MODIFY WHEN <new_condition>` or `ALTER TASK my_task REMOVE WHEN`.
- **Predecessors (parent-child relationships):** `ALTER TASK child_task ADD AFTER parent1, parent2` or `ALTER TASK child_task REMOVE AFTER parent1`. The alter is run on the child task. Note: the finalizer relationship uses `SET FINALIZE` / `UNSET FINALIZE`, not `ADD AFTER`.

**Prefer `ALTER TASK` over `CREATE OR REPLACE` or `DROP` + `CREATE`.** Replacing or dropping and recreating a task resets it to SUSPENDED, loses its relationships (`AFTER`, `FINALIZE`), other properties and parameters, and history.

## Task Privileges

Granting task-related privileges requires different roles depending on the scope:

- **Account-level grants** (`EXECUTE TASK`, `EXECUTE MANAGED TASK`) require the `ACCOUNTADMIN` role. If you get "Insufficient privileges" when granting these, switch to ACCOUNTADMIN first: `USE ROLE ACCOUNTADMIN; GRANT EXECUTE TASK ON ACCOUNT TO ROLE my_role;`. Remember to switch back afterward.
- **Schema-level grants** (`CREATE TASK`) can typically be granted by the schema owner or a role with `MANAGE GRANTS`.
- **Task-level grants** (`OPERATE`, `MONITOR`) can be granted by the task owner.

For a role to create and run tasks (including serverless), it needs at minimum:
1. `USAGE` on the database and schema
2. `CREATE TASK` on the schema
3. `EXECUTE TASK ON ACCOUNT` (for all tasks)
4. `EXECUTE MANAGED TASK ON ACCOUNT` (for serverless tasks only)
5. `USAGE` on a warehouse (for warehouse-based tasks only)

**Tasks run as their owner role**, not the calling user's role. If a task's SQL works when you run it interactively but the task itself fails, the owner role is likely missing a privilege (e.g. warehouse USAGE, INSERT on a target table). Check the owner with `SHOW TASKS`, then inspect that role's grants with `SHOW GRANTS TO ROLE <owner_role>` to find the gap.

## Task Timeouts

Two parameters control how long a task's SQL can run before being canceled:

- **`USER_TASK_TIMEOUT_MS`** — set on the task itself (in **milliseconds**). Use `ALTER TASK my_task SET USER_TASK_TIMEOUT_MS = 60000;` to allow up to 60 seconds. Check with `SHOW PARAMETERS LIKE 'USER_TASK_TIMEOUT_MS' IN TASK db.schema.my_task;`.
- **`STATEMENT_TIMEOUT_IN_SECONDS`** — session-level or warehouse-level parameter (in **seconds**). Can also be set on the task like any session-level parameter. Check with `SHOW PARAMETERS LIKE 'STATEMENT_TIMEOUT_IN_SECONDS' IN TASK db.schema.my_task;` (or on the task's warehouse for warehouse-level settings).

When both are set, the effective timeout is the **lowest non-zero value** of the two (after unit conversion). For example, `USER_TASK_TIMEOUT_MS = 30000` (30s) with `STATEMENT_TIMEOUT_IN_SECONDS = 60` (60s) results in a 30-second timeout.

When diagnosing task timeout failures, always check **both** parameters on the task to determine which one is limiting execution.

## Serverless Tasks

To create a serverless task, omit the `WAREHOUSE` parameter from `CREATE TASK`. Snowflake automatically provisions and scales compute resources.

To control the compute size range, set these parameters directly on the task:

```sql
CREATE TASK my_task
  SCHEDULE = '5 MINUTE'
  SERVERLESS_TASK_MIN_STATEMENT_SIZE = 'XSMALL'
  SERVERLESS_TASK_MAX_STATEMENT_SIZE = 'MEDIUM'
AS ...
```

- `SERVERLESS_TASK_MIN_STATEMENT_SIZE` — floor for compute size (default: `'XSMALL'`)
- `SERVERLESS_TASK_MAX_STATEMENT_SIZE` — ceiling for compute size (default: `'XXLARGE'`)
- Valid sizes: `XSMALL`, `SMALL`, `MEDIUM`, `LARGE`, `XLARGE`, `XXLARGE`

When a user asks to cap or limit the serverless compute size, set `SERVERLESS_TASK_MAX_STATEMENT_SIZE`. When they ask for a minimum performance guarantee, set `SERVERLESS_TASK_MIN_STATEMENT_SIZE`.

## Parameterized Task Graphs (CONFIG)

When the user wants a task graph that accepts runtime parameters (e.g., processing a specific region, date range, or mode), use Snowflake's built-in CONFIG mechanism — do **not** use SQL variables, bind parameters, or session variables.

**Creating a parameterized root task:** Use `SYSTEM$GET_TASK_GRAPH_CONFIG('<key>')` in the task body to read a config value. Use a Snowflake Scripting block to bind it to a variable:

```sql
CREATE OR REPLACE TASK process_sales
    WAREHOUSE = 'my_wh'
AS
BEGIN
    LET region STRING := SYSTEM$GET_TASK_GRAPH_CONFIG('region')::STRING;
    INSERT INTO regional_sales
    SELECT * FROM sales_data WHERE region = :region;
END;
```

Child tasks in the same graph can also call `SYSTEM$GET_TASK_GRAPH_CONFIG` to read the same config values.

**Executing with parameters:** Use `EXECUTE TASK ... USING CONFIG` with a JSON payload in dollar-quoted string:

```sql
EXECUTE TASK process_sales USING CONFIG = $${"region": "WEST"}$$;
```

**Important syntax notes:**
- `USING CONFIG = $${ ... }$$` is the only valid syntax. Do **not** use `USING (key => value)`, `PARAMETERS (...)`, or `TASK_GRAPH_CONFIG = ...` — these will all produce SQL compilation errors.
- The root task does not need a `SCHEDULE` to be executed with `EXECUTE TASK ... USING CONFIG`. You can leave it suspended and execute it on demand.
- Child tasks must be resumed (`ALTER TASK child RESUME`) before executing the root, or they will not run when the root completes.

## Passing Data Between Tasks (Return Values)

To pass data from a parent task to a child task, use `SYSTEM$SET_RETURN_VALUE` in the parent and `SYSTEM$GET_PREDECESSOR_RETURN_VALUE` in the child. Write the logic directly in the task body using a Snowflake Scripting block — do not delegate to a stored procedure, as the return value mechanism must be in the task body itself. The return value is always a string - you must pass a VARCHAR to system$set_return_value and system$get_predecessor_return_value will return a varchar.

Return values set via `SYSTEM$SET_RETURN_VALUE` are also visible in `TASK_HISTORY` (the `RETURN_VALUE` column), making them useful for logging and debugging what happened in each task run.

**Parent task — set the return value:**

```sql
CREATE OR REPLACE TASK count_orders
    WAREHOUSE = my_wh
    SCHEDULE = '240 MINUTE'
AS
BEGIN
    LET row_count NUMBER := (SELECT COUNT(*) FROM daily_orders);
    CALL SYSTEM$SET_RETURN_VALUE(:row_count::VARCHAR);
END;
```

A bare `SELECT` or `RETURN` at the end of a `BEGIN...END` block does **not** pass the result to child tasks. You must explicitly call `SYSTEM$SET_RETURN_VALUE`.

**Child task — read the predecessor's return value in the task body:**

```sql
CREATE OR REPLACE TASK log_order_count
    WAREHOUSE = my_wh
    AFTER count_orders
AS
BEGIN
    LET cnt VARCHAR := SYSTEM$GET_PREDECESSOR_RETURN_VALUE('COUNT_ORDERS');
    INSERT INTO pipeline_log (order_count, logged_at) VALUES (:cnt::NUMBER, CURRENT_TIMESTAMP());
END;
```

Child tasks can also use the predecessor's return value in a `WHEN` condition to conditionally execute. The syntax is restricted to simple comparisons:

```sql
CREATE OR REPLACE TASK log_order_count
    WAREHOUSE = my_wh
    AFTER count_orders
    WHEN SYSTEM$GET_PREDECESSOR_RETURN_VALUE('COUNT_ORDERS')::NUMBER > 0
AS
BEGIN
    LET cnt VARCHAR := SYSTEM$GET_PREDECESSOR_RETURN_VALUE('COUNT_ORDERS');
    INSERT INTO pipeline_log (order_count, logged_at) VALUES (:cnt::NUMBER, CURRENT_TIMESTAMP());
END;
```

**Critical:** The argument to `SYSTEM$GET_PREDECESSOR_RETURN_VALUE` must be the **task name only** (e.g., `'COUNT_ORDERS'`). Do **not** use a fully-qualified name like `'db.schema.COUNT_ORDERS'` — Snowflake will return an error. The name is case-sensitive and must match the task name exactly as created.

## Querying Task Run History

To inspect task execution history, use the `SNOWFLAKE.INFORMATION_SCHEMA.TASK_HISTORY` table function. `SNOWFLAKE.INFORMATION_SCHEMA.TASK_HISTORY` is the only source that records every execution attempt, including failures and their error messages. Its results are filtered based on the role querying it; runs are displayed for any tasks that the role has MONITOR, OPERATE or OWNERSHIP privileges on. `SNOWFLAKE.INFORMATION_SCHEMA.TASK_HISTORY` has the last 7 days history data only, nothing older than that.

```sql
SELECT name, state, scheduled_time, error_code, error_message
  FROM TABLE(SNOWFLAKE.INFORMATION_SCHEMA.TASK_HISTORY(
    TASK_NAME => 'my_task',
    SCHEDULED_TIME_RANGE_START => DATEADD('hour', -24, CURRENT_TIMESTAMP())
  ))
  ORDER BY scheduled_time DESC;
```

`SNOWFLAKE.INFORMATION_SCHEMA.TASK_HISTORY` returns runs from the **entire account** by default. Task names are only unique within a schema — the same name can exist in multiple schemas or databases. If the user is asking about a task in a specific database and schema, add a `WHERE` clause to avoid mixing in runs from identically-named tasks elsewhere:

```sql
SELECT name, state, scheduled_time, error_code, error_message
  FROM TABLE(SNOWFLAKE.INFORMATION_SCHEMA.TASK_HISTORY(
    TASK_NAME => 'my_task',
    SCHEDULED_TIME_RANGE_START => DATEADD('hour', -24, CURRENT_TIMESTAMP()),
    RESULT_LIMIT => 10000
  ))
  WHERE database_name = 'MY_DB' AND schema_name = 'MY_SCHEMA'
  ORDER BY scheduled_time DESC;
```

Key parameters (all optional):
- `TASK_NAME` — filter to a specific task (case-insensitive, unqualified name)
- `SCHEDULED_TIME_RANGE_START / _END` — time window (last 7 days only)
- `RESULT_LIMIT` — max rows (default 100, max 10000)
- `ERROR_ONLY => TRUE` — return only failed/cancelled runs
- `ROOT_TASK_ID` — show history for an entire task graph

Key output columns: `STATE` (SUCCEEDED / FAILED / CANCELLED / SKIPPED), `ERROR_CODE`, `ERROR_MESSAGE`, `SCHEDULED_TIME`, `COMPLETED_TIME`, `QUERY_ID`, `DATABASE_NAME`, `SCHEMA_NAME`.

**Push every filter you can into table-function arguments.** On a busy account `TASK_HISTORY` returns runs from every task, and `RESULT_LIMIT` is applied **before** any `WHERE` clause — so the function can hand you 100 rows of unrelated tasks and your `WHERE` keeps none of them. Use whichever arguments fit:

- Time range? Set `SCHEDULED_TIME_RANGE_START` / `SCHEDULED_TIME_RANGE_END` to bound the window. `SCHEDULED_TIME_RANGE_END => CURRENT_TIMESTAMP()` excludes future runs; `SCHEDULED_TIME_RANGE_START => CURRENT_TIMESTAMP()` excludes past runs.
- Investigating one task graph? Use `ROOT_TASK_ID` — get the id from the `id` column of `SHOW TASKS` on the root task.
- Only want failures? Set `ERROR_ONLY => TRUE`.
- Specific task? Use `TASK_NAME`.

Some filters have no argument equivalent — `DATABASE_NAME` and `SCHEMA_NAME` only work in `WHERE`. When `WHERE` is unavoidable, still pass every applicable argument **and** set `RESULT_LIMIT => 10000` (the maximum) so the pre-filter cap doesn't drop the rows you care about.

`SNOWFLAKE.INFORMATION_SCHEMA.TASK_HISTORY` has zero lag — it includes currently running runs and runs scheduled into the future. If you expect a task to be running and the function returns 0 rows, the run was never scheduled or your arguments are filtering it out. To exclude future scheduled runs, set `SCHEDULED_TIME_RANGE_END => CURRENT_TIMESTAMP()`.

For history older than 7 days, use `SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY` (view, not table function) instead. Key differences from `INFORMATION_SCHEMA`:
- Only contains completed task runs — future scheduled and currently running tasks are not included.
- 365 days of retention, compared to 7 days for `INFORMATION_SCHEMA`.
- May have up to 45 minutes of lag between when a task run finishes and when it is included in the view.
- Requires additional privileges to query and may not be accessible to some users. The ACCOUNTADMIN role can access it, roles granted IMPORTED PRIVILEGES on the SNOWFLAKE database can access it, and roles granted the USAGE_VIEWER SNOWFLAKE database role can access it. Results are not filtered by the role querying it — once you have access, you see every task's runs across the entire account.

## Monitor

After troubleshooting task health, always run this two-step monitor flow before closing.

Step 1 - Decide whether the failure context is simple or complex using the `ERROR_INTEGRATION` criteria below:
- If all criteria are met, treat the case as simple.
- If any criterion is not met, treat the case as complex.

Step 2 - Make a session-scoped, one-time monitoring recommendation based on Step 1:
- Session flag: `has_suggested_monitoring_recommendation = false` by default.
- If `has_suggested_monitoring_recommendation = false` and Step 1 is simple, recommend native `ERROR_INTEGRATION` and briefly explain why.
- If `has_suggested_monitoring_recommendation = false` and Step 1 is complex, recommend Alert-based monitoring and follow [Alert Monitoring Recommendation Policy](#alert-monitoring-recommendation-policy-session-scoped-consent-gated).
- Immediately after making either recommendation, set `has_suggested_monitoring_recommendation = true`.
- If `has_suggested_monitoring_recommendation = true`, do not repeat the same monitoring recommendation in the same session unless the customer explicitly asks to revisit monitoring options.

Use `ERROR_INTEGRATION` when:
- The user asks for simple "notify me when this task fails" behavior.
- The monitoring target is a single task or task graph, and root-task-level failure notifications are sufficient.
- The user already has (or wants to use) a Snowflake notification integration and wants Snowflake-native task failure events.
- The requirement is limited to task run failure notifications, without custom aggregation, deduplication, or multi-signal monitoring logic.

When Step 1 classifies the case as complex, follow the session-scoped, consent-gated Alert recommendation policy in [Alert Monitoring Recommendation Policy](#alert-monitoring-recommendation-policy-session-scoped-consent-gated).

## Alert Monitoring Recommendation Policy (Session-Scoped, Consent-Gated)

Use this policy whenever you are about to suggest Alert-based monitoring for Tasks, or when a customer directly asks you to set up Alert-based monitoring.

Session flag:
- `has_suggested_alert = false` by default at the start of each session.

Rules:
1. **Suggest once per session only.**
   - Before suggesting Alert-based monitoring, check `has_suggested_alert`.
   - If `has_suggested_alert = false`, you may suggest creating an Alert to monitor task health/failures.
   - Immediately after making that suggestion, set `has_suggested_alert = true`.
   - If `has_suggested_alert = true`, do not repeat the same Alert suggestion again in this session.

2. **Route only after explicit customer consent.**
   - A suggestion alone must not trigger delegation.
   - Ask for explicit confirmation (for example: "Would you like me to set up Alert-based monitoring for this task?").
   - Only when the customer clearly agrees, load and delegate to [`alert`](../alert/SKILL.md).
   - If the customer declines or does not answer, continue task-focused troubleshooting/operations without delegating to the Alert skill.

3. **Handle direct customer requests as explicit consent.**
   - If the customer directly asks to set up Alert-based monitoring (without a prior agent suggestion), treat that request as explicit consent.
   - In that case, load and delegate to [`alert`](../alert/SKILL.md) without asking a second consent question.
   - Immediately after taking this direct-request path, set `has_suggested_alert = true`.

## Starting / Resuming a Task Graph

When starting (resuming) a task graph, **resume child and finalizer tasks before the root task**. The root task must be resumed last — otherwise it can trigger a run before children are ready, leaving them in a suspended state. Newly created tasks are created in a suspended state by default. Either resume each task individually via "alter task <name> resume", or use "SELECT SYSTEM$TASK_DEPENDENTS_ENABLE('mydb.myschema.my_root_task');" to resume all the tasks in the graph with a single command, including the root. For production task graphs, follow [Alert Monitoring Recommendation Policy](#alert-monitoring-recommendation-policy-session-scoped-consent-gated) before any Alert suggestion or delegation.
