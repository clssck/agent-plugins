# Budget Actions Reference

Budgets support two types of automated actions:
1. **Custom Actions** - Triggered when spending hits a threshold
2. **Cycle-Start Actions** - Triggered at the start of each monthly cycle

> **⚠️ ADD_CUSTOM_ACTION Parameter Order**  
> The parameter order is: `(procedure_reference, arguments_array, trigger_type, threshold)`  
> - Procedure name in SYSTEM$REFERENCE **must include parentheses**: `'mydb.schema.proc()'`  
> - Arguments array is required (use `ARRAY_CONSTRUCT()` if no args)

---

## Custom Actions

Execute a stored procedure when spending **actually reaches** or is **projected to reach** a percentage of the limit. The trigger type (`ACTUAL` vs `PROJECTED`) is specified per action.

### Add Custom Action

```sql
-- Create the action procedure
CREATE OR REPLACE PROCEDURE mydb.myschema.budget_alert_action()
RETURNS STRING
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
BEGIN
    -- Custom logic: resize warehouse down to reduce spend, send alert, log event, etc.
    ALTER WAREHOUSE expensive_wh SET WAREHOUSE_SIZE = XSMALL;
    RETURN 'Warehouse resized to XSMALL due to budget threshold';
END;
$$;

-- Grant USAGE to Snowflake application (DATABASE, SCHEMA, and PROCEDURE required)
GRANT USAGE ON DATABASE mydb TO APPLICATION SNOWFLAKE;
GRANT USAGE ON SCHEMA mydb.myschema TO APPLICATION SNOWFLAKE;
GRANT USAGE ON PROCEDURE mydb.myschema.budget_alert_action() TO APPLICATION SNOWFLAKE;

-- Add to budget
CALL my_budget!ADD_CUSTOM_ACTION(
    SYSTEM$REFERENCE('PROCEDURE', 'mydb.myschema.budget_alert_action()', 'SESSION', 'USAGE'),
    ARRAY_CONSTRUCT(),     -- arguments to pass to procedure (empty if none)
    'PROJECTED',           -- trigger type: PROJECTED or ACTUAL
    80                     -- threshold: fires at 80% of spending limit
);
```

### Trigger Types

| Type | When Fired |
|------|------------|
| `PROJECTED` | When forecasted end-of-month spending exceeds threshold |
| `ACTUAL` | When actual current spending exceeds threshold |

### Multiple Actions

You can add multiple custom actions at different thresholds:

```sql
-- Warning at 70%
CALL my_budget!ADD_CUSTOM_ACTION(
    SYSTEM$REFERENCE('PROCEDURE', 'mydb.myschema.send_warning()', 'SESSION', 'USAGE'),
    ARRAY_CONSTRUCT(),
    'PROJECTED',
    70
);

-- Suspend at 90%
CALL my_budget!ADD_CUSTOM_ACTION(
    SYSTEM$REFERENCE('PROCEDURE', 'mydb.myschema.suspend_resources()', 'SESSION', 'USAGE'),
    ARRAY_CONSTRUCT(),
    'ACTUAL',
    90
);
```

### Remove Custom Actions

Three overloads are available — from broadest to most targeted:

```sql
-- Remove ALL custom actions from budget
CALL my_budget!REMOVE_CUSTOM_ACTIONS();

-- Remove all custom actions at a specific threshold
CALL my_budget!REMOVE_CUSTOM_ACTIONS(75);

-- Remove a specific procedure at a specific threshold
-- Use the PROCEDURE_FQN value from GET_CUSTOM_ACTIONS() output
CALL my_budget!REMOVE_CUSTOM_ACTIONS(75, 'code_db.sch1.my_sp');
```

> **Tip**: Run `GET_CUSTOM_ACTIONS()` first to see current actions and get the exact `PROCEDURE_FQN` to use in the targeted form.

### Requirements

1. **Spending limit required**: Custom actions only fire if `SET_SPENDING_LIMIT` is configured
2. **Owner's rights**: Procedure must use `EXECUTE AS OWNER`
3. **Grant USAGE to APPLICATION SNOWFLAKE**: Must grant on all three:
   - `GRANT USAGE ON DATABASE <db> TO APPLICATION SNOWFLAKE`
   - `GRANT USAGE ON SCHEMA <db.schema> TO APPLICATION SNOWFLAKE`
   - `GRANT USAGE ON PROCEDURE <db.schema.proc()> TO APPLICATION SNOWFLAKE`

---

## Cycle-Start Actions

Execute a stored procedure at the start of each monthly billing cycle (when spending resets to zero).

### Set Cycle-Start Action

```sql
-- Create procedure
CREATE OR REPLACE PROCEDURE mydb.myschema.monthly_budget_reset()
RETURNS STRING
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
BEGIN
    -- Reset warehouse sizes, clear alerts, archive logs, etc.
    ALTER WAREHOUSE analytics_wh SET WAREHOUSE_SIZE = 'XSMALL';
    RETURN 'Monthly reset complete';
END;
$$;

-- Grant to Snowflake (DATABASE, SCHEMA, and PROCEDURE required)
GRANT USAGE ON DATABASE mydb TO APPLICATION SNOWFLAKE;
GRANT USAGE ON SCHEMA mydb.myschema TO APPLICATION SNOWFLAKE;
GRANT USAGE ON PROCEDURE mydb.myschema.monthly_budget_reset() TO APPLICATION SNOWFLAKE;

-- Set as cycle-start action (only ONE per budget)
CALL my_budget!SET_CYCLE_START_ACTION(
    SYSTEM$REFERENCE('PROCEDURE', 'mydb.myschema.monthly_budget_reset()'),
    ARRAY_CONSTRUCT()    -- arguments to pass to procedure (empty if none)
);
```

### Get Cycle-Start Action

```sql
CALL my_budget!GET_CYCLE_START_ACTION();
```

### Remove Cycle-Start Action

```sql
CALL my_budget!REMOVE_CYCLE_START_ACTION();
```

### Cycle-Start Constraints

- **Exactly one** cycle-start action per budget
- Executes just after **12:00 AM UTC on the 1st** of each month
- **30 minute timeout**: Procedure must complete within 30 minutes
- **Re-grant on change**: If you ALTER the procedure, re-grant USAGE to Snowflake

---

## Stored Procedure Requirements

| Requirement | Custom Action | Cycle-Start Action |
|-------------|---------------|-------------------|
| EXECUTE AS OWNER | Required | Required |
| GRANT USAGE to APPLICATION SNOWFLAKE | Required | Required |
| Max runtime | 30 minutes | 30 minutes |
| Multiple per budget | Yes | No (at most one) |

### Supported Languages

- SQL
- JavaScript
- Python
- Java
- Scala

### Example: Multi-Language Procedure

```sql
-- Python procedure example
CREATE OR REPLACE PROCEDURE mydb.myschema.budget_alert_python()
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.10'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'run'
EXECUTE AS OWNER
AS
$$
def run(session):
    # Custom Python logic
    session.sql("ALTER WAREHOUSE my_wh SUSPEND").collect()
    return "Action complete"
$$;

GRANT USAGE ON PROCEDURE mydb.myschema.budget_alert_python() TO APPLICATION SNOWFLAKE;
```

---

## Debugging Actions

### Check Cycle-Start Task History

Cycle-start actions run as internal tasks named `_budget_cycle_start_task`:

```sql
SELECT *
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
    SCHEDULED_TIME_RANGE_START => DATEADD('day', -7, CURRENT_TIMESTAMP())
))
WHERE NAME LIKE '%_budget_cycle_start_task%'
ORDER BY SCHEDULED_TIME DESC;
```

### Common Debug Steps

1. **Verify procedure exists and compiles**:
   ```sql
   CALL mydb.myschema.my_action_procedure();
   ```

2. **Check USAGE grant**:
   ```sql
   SHOW GRANTS ON PROCEDURE mydb.myschema.my_action_procedure();
   ```

3. **Verify spending limit is set** (required for custom actions):
   ```sql
   CALL my_budget!GET_SPENDING_LIMIT();
   ```

4. **Confirm all action procedures are accessible** — validates that Snowflake can reach every stored procedure registered as a custom action:
   ```sql
   CALL my_budget!CONFIRM_CUSTOM_ACTIONS_ACCESS();
   ```
   Returns a result for each action indicating whether the procedure is accessible. Use this when actions aren't firing as expected and you want to rule out permission issues.

---

> **Common Errors**: See `references/budget/troubleshooting.md` for action-related error messages and solutions.
