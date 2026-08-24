---
name: dbt-schedule
description: "**[REQUIRED]** Schedule dbt project execution via Snowflake Tasks. Invoke FIRST for: CREATE TASK for dbt, schedule dbt runs, cron for dbt, run dbt every X hours/minutes, dbt automation, task chain, dependent tasks, run after task X. Critical: Uses special SQL syntax (EXECUTE DBT PROJECT) not standard dbt CLI."
parent_skill: dbt-projects-on-snowflake
---

# Schedule dbt Project Execution

**WHY THIS SUB-SKILL:** Scheduling dbt on Snowflake requires specific SQL syntax (`EXECUTE DBT PROJECT`) and task management patterns (suspend/resume order) that differ from standard Snowflake tasks.

## When to Load

Parent skill routes here when user mentions: "schedule", "task", "cron", "automate", "trigger", "recurring", "every X hours/minutes/days", "run daily", "run hourly", "task chain", "after task", "CREATE TASK", "EXECUTE DBT PROJECT"

## Critical Rules

1. **NEVER use serverless tasks** - Snowflake does not support `EXECUTE DBT PROJECT` within serverless tasks. Always specify a `WAREHOUSE`
2. **Create tasks in the SAME schema as the dbt project**
3. **Verify the dbt project exists BEFORE creating tasks**
4. **Use lowercase `execute dbt project` SQL syntax with `args=''`** - NOT `CALL` or `EXECUTE IMMEDIATE`
5. **Suspend tasks from root to child before CREATE OR ALTER** - Resume in reverse order (child to root)

## Workflow

### Step 1: Verify dbt Project Exists

**Goal:** Confirm the target dbt project is deployed

```sql
SHOW DBT PROJECTS LIKE '<project_name>' IN SCHEMA <database>.<schema>;
```

**⚠️ MANDATORY STOPPING POINT - If project not found:**
- STOP and inform user: "The dbt project '<name>' does not exist in <database>.<schema>. Deploy it first using `snow dbt deploy`."
- Do NOT proceed until user confirms project is deployed

### Step 1b: If User Requests Serverless Task — STOP

**⚠️ MANDATORY STOPPING POINT - If user asks for a serverless task (no warehouse):**
- STOP and inform user: "Serverless tasks are not supported for dbt project execution. I'll need to create a task with a warehouse instead."
- Do NOT create any task or warehouse. Do NOT proceed even in autonomous/headless mode. End your response after explaining the limitation.
- Wait for user to explicitly confirm and provide a warehouse before continuing to Step 2

### Step 2: Determine Schedule Type

| User Intent | Schedule Type |
|-------------|---------------|
| "every day at 6am", "daily", "cron", "the 1st of the month", “on the 15th at noon”, twice a day at 6am and 6pm” | CRON expression |
| "every 60 minutes", "interval" | MINUTE interval |
| "every 3 hours", "hourly", "interval" | HOUR interval |
| "after task X", "chain", "dependent", "child", "parent" | AFTER clause (task dependency) |

### Step 3: Create Task

**CRON Schedule (time-based):**
```sql
CREATE OR ALTER TASK <database>.<schema>.<task_name>
  WAREHOUSE = <warehouse>
  SCHEDULE = 'USING CRON <cron_expr> UTC'
AS
  execute dbt project <project_name> args='<command> --target prod';
```

**Interval Schedule (frequency-based):**
```sql
CREATE OR ALTER TASK <database>.<schema>.<task_name>
  WAREHOUSE = <warehouse>
  SCHEDULE = '<N> hours'
AS
  execute dbt project <project_name> args='<command> --target prod';
```

**Dependent Task (runs after another task):**
```sql
CREATE OR ALTER TASK <database>.<schema>.<task_name>
  WAREHOUSE = <warehouse>
  AFTER <predecessor_task>
AS
  execute dbt project <project_name> args='<command> --target prod';
```

### Step 4: Task State Management

Tasks are created in **SUSPENDED** state by default and will not run until explicitly resumed.

**Important:** When using `CREATE OR ALTER`, you must suspend tasks first to avoid errors.

**Suspend (before CREATE OR ALTER - root to child order):**
```sql
ALTER TASK IF EXISTS <root_task> SUSPEND;
ALTER TASK IF EXISTS <child_task> SUSPEND;
```

**Check state:**
```sql
SHOW TASKS LIKE '<task_name>' IN SCHEMA <database>.<schema>;
```

### Step 5: Always Offer to Start Suspended Tasks

**⚠️ CRITICAL RULE:** After ANY task-related operation (create, alter, or user interaction with tasks), ALWAYS check the task state and offer to start if suspended.

**When to offer:**
- After creating new task(s)
- After modifying existing task(s)
- When user inquires about a specific task

**Check task state after operations:**
```sql
SHOW TASKS LIKE '<task_name>' IN SCHEMA <database>.<schema>;
-- Look at the 'state' column - if SUSPENDED, offer to start
```

**⚠️ MANDATORY CHECKPOINT - If task(s) are SUSPENDED, always inform user and offer to start (unless user explicitly requested suspended state):**
```
The task(s) are currently in SUSPENDED state and will NOT run until started:
- [task_name]: SUSPENDED (schedule: [schedule])

Would you like me to start the task(s) now? (Yes/No)
```

**Resume (enable scheduling - child to root order):**
```sql
ALTER TASK IF EXISTS <child_task> RESUME;
ALTER TASK IF EXISTS <root_task> RESUME;
```

**After resuming, confirm:**
```sql
SHOW TASKS LIKE '<task_name>' IN SCHEMA <database>.<schema>;
-- Verify state is now STARTED
```

## Common CRON Expressions

| Schedule | CRON Expression |
|----------|-----------------|
| Daily at 6:00 AM UTC | `0 6 * * *` |
| Daily at midnight UTC | `0 0 * * *` |
| Every Monday at 9 AM | `0 9 * * 1` |
| First day of month | `0 0 1 * *` |
| Every 6 hours | `0 */6 * * *` |

## Task Chain Example

For sequential dbt operations (subset → full run → test):

```sql
-- STEP 1: Suspend all tasks from root to child (ensures CREATE OR ALTER works)
ALTER TASK IF EXISTS run_tasty_bytes_subset SUSPEND;
ALTER TASK IF EXISTS run_tasty_bytes_full SUSPEND;
ALTER TASK IF EXISTS test_tasty_bytes SUSPEND;

-- STEP 2: Create/alter tasks
-- Root task (has schedule) - runs a subset of models early for business needs
CREATE OR ALTER TASK run_tasty_bytes_subset
  WAREHOUSE = my_wh
  SCHEDULE = '12 hours'
AS
  execute dbt project my_dbt_project args='run --select raw_customers stg_customers customers --target prod';

-- Dependent task 1 - full project run
CREATE OR ALTER TASK run_tasty_bytes_full
  WAREHOUSE = my_wh
  AFTER run_tasty_bytes_subset
AS
  execute dbt project my_dbt_project args='run --target prod';

-- Dependent task 2 - data quality tests
CREATE OR ALTER TASK test_tasty_bytes
  WAREHOUSE = my_wh
  AFTER run_tasty_bytes_full
AS
  execute dbt project my_dbt_project args='test --target prod';

-- STEP 3: Resume tasks in REVERSE order (child to root)
ALTER TASK IF EXISTS test_tasty_bytes RESUME;
ALTER TASK IF EXISTS run_tasty_bytes_full RESUME;
ALTER TASK IF EXISTS run_tasty_bytes_subset RESUME;
```

## Best Practices

1. **Same schema as project** - Create tasks in the same schema where the dbt project is deployed
2. **Always specify warehouse** - Serverless tasks (omitting warehouse) cannot run `EXECUTE DBT PROJECT`
3. **Meaningful task names** - Use descriptive names like `dbt_daily_run`, `dbt_hourly_refresh`
5. **Chain for dependencies** - Use AFTER clause for sequential operations

## Stopping Points

- ✋ Step 1: If dbt project does not exist - STOP and inform user
- ✋ Step 1b: If user requests serverless task - STOP, explain unsupported, wait for confirmation to use warehouse
- ✋ Step 5: If task(s) are SUSPENDED - ALWAYS offer to start (unless user explicitly requested suspended state)
- ✋ Any destructive operation - confirm before executing

## Output

- Snowflake TASK object created in the target schema
- Task configured with specified schedule or dependency
- Task in SUSPENDED or STARTED state as requested
