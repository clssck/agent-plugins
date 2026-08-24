---
parent_skill: data-quality
---

# Workflow: Circuit Breaker

Set up an automated circuit breaker that halts downstream data pipelines when upstream DMF quality violations are detected. Prevents bad data from propagating through the pipeline until the quality issue is resolved.

**Closes gaps:** G4 (Circuit Breakers), TA-07 (Circuit Breaker Integration), CC-02 (Circuit Breaker Framework).

## Trigger Phrases
- "Set up a circuit breaker"
- "Pause downstream pipeline when quality fails"
- "Halt bad data propagation"
- "Stop the pipeline if DMF violations are detected"
- "Create a quality gate"
- "Protect downstream tables from bad upstream data"
- "Suspend my task if quality drops"
- "Auto-pause my dynamic table on violations"

## When to Load
- User wants to automatically halt a downstream pipeline when an upstream DMF fires a violation
- User completed a DQ incident investigation and wants to prevent recurrence

---

## Execution Steps

### Step 1: Identify the Circuit

Extract from user message:
- **Upstream (protected)**: the table with DMFs and expectations attached that triggers the break — `DATABASE.SCHEMA.UPSTREAM_TABLE`
- **Downstream (halted)**: the TASK or DYNAMIC TABLE to pause on violation
- **Which expectations to watch** (optional): default is any expectation violated on the upstream table; user may narrow by metric name in the template if desired

If upstream or downstream is not provided, ask:
> "To set up the circuit breaker, I need:
> 1. The **upstream table** with DMFs attached (the quality gate)
> 2. The **downstream TASK or DYNAMIC TABLE** to pause when quality fails
>
> Please provide both."

---

### Step 2: Verify Setup Prerequisites

Run checks:

```sql
-- Verify upstream table has DMFs attached
SELECT REF_ENTITY_NAME, METRIC_NAME, SCHEDULE, SCHEDULE_STATUS
FROM TABLE(INFORMATION_SCHEMA.DATA_METRIC_FUNCTION_REFERENCES(
    REF_ENTITY_NAME => '<database>.<schema>.<upstream_table>',
    REF_ENTITY_DOMAIN => 'TABLE'
));
```

```sql
-- Verify downstream task/DT exists
SHOW TASKS LIKE '<task_name>' IN SCHEMA <database>.<schema>;
-- OR for dynamic tables:
SHOW DYNAMIC TABLES LIKE '<dt_name>' IN SCHEMA <database>.<schema>;
```

If upstream table has no DMFs or no expectations:
> "The upstream table `<upstream_table>` has no DMFs attached, or no expectations set on them. A circuit breaker triggers when an expectation is violated (expectation_violated = TRUE). Would you like me to recommend DMFs and expectations first?"
> If yes → Load `workflows/monitor-recommendations.md` or `workflows/expectations-management.md`

---

### Step 3: Present Circuit Breaker Plan

**⚠️ MANDATORY STOPPING POINT**: Present the full plan and await explicit approval.
Read `templates/circuit-breaker-setup.sql` and show the user what will be created:

```
## Circuit Breaker Plan

### Trigger Condition
- Upstream table: <DATABASE.SCHEMA.UPSTREAM_TABLE>
- Trigger: any expectation violated on the upstream table (from DATA_QUALITY_MONITORING_EXPECTATION_STATUS; expectation_violated = TRUE)

### Action on Trigger
- Suspend TASK: <DATABASE.SCHEMA.TASK_NAME>
  (or: Pause DYNAMIC TABLE: <DATABASE.SCHEMA.DT_NAME>)

### How It Works
1. A Snowflake ALERT (<alert_name>) runs every <frequency> minutes
2. It checks expectation status for the upstream table (expectations set on DMF associations)
3. If any expectation is violated → it suspends the downstream task
4. To resume: fix the upstream data quality issue, then run:
   ALTER TASK <DATABASE.SCHEMA.TASK_NAME> RESUME;

### Objects to Create
- ALERT: <database>.<schema>.<alert_name>

Do you approve? (Yes / No / Modify)
```

**NEVER create the ALERT or modify the task without explicit user confirmation** (unless pre-approval was given in the request).

---

### Step 4: Execute (On Approval)

**Use the template for the ALERT condition:** The template’s IF clause queries **SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_EXPECTATION_STATUS** (view or table function) and checks `expectation_violated = TRUE`. Do not replace this with a condition on raw metric VALUE (e.g. VALUE > threshold); the circuit breaker must trigger on expectation status.

Read and execute `templates/circuit-breaker-setup.sql` with all placeholders replaced:
- `<database>`, `<schema>`
- `<upstream_table>`, `<downstream_object>`, `<object_type>`
- `<alert_name>`, `<warehouse>`, `<frequency_minutes>`

After execution, confirm:

```
Circuit Breaker Activated: <alert_name>

Monitoring: <DATABASE.SCHEMA.UPSTREAM_TABLE>
Trigger: any expectation violated (expectation_violated = TRUE)
Action: SUSPEND TASK <task_or_dt_name>

The circuit breaker will check every <frequency> minutes.
Run SHOW ALERTS LIKE '<alert_name>' to verify it is active.

### To Resume After a Quality Fix
1. Fix the upstream data issue
2. Verify the DMF passes: run health check on <upstream_table>
3. Resume the protected pipeline:
   ALTER TASK <DATABASE.SCHEMA.TASK_NAME> RESUME;
   -- or for dynamic tables:
   ALTER DYNAMIC TABLE <DATABASE.SCHEMA.DT_NAME> RESUME;
4. Optionally suspend and re-resume the ALERT to reset its state
```

---

### Step 5: List Active Circuit Breakers (Read-Only Sub-Flow)

If the user asks to **check existing circuit breakers** (e.g., "show me my circuit breakers"):

```sql
-- Find DQ circuit breaker ALERTs (by naming convention)
SHOW ALERTS IN SCHEMA <database>.<schema>;
```

Then for each matching alert, show:
- Alert name, schedule, state (STARTED/SUSPENDED)
- Condition SQL (what it monitors)
- Action SQL (what it suspends)

---

## Output Format
- Circuit breaker configuration summary (trigger, threshold, action)
- ALERT DDL (shown before execution)
- Post-activation confirmation
- Resume workflow instructions

## Stopping Points
- ✋ **Step 1**: Upstream/downstream not identified — ask before proceeding
- ✋ **Step 3**: Before creating ALERT or modifying task — show full plan and await explicit approval

## Error Handling
| Issue | Resolution |
|-------|-----------|
| Upstream table has no DMFs | Offer to run monitor-recommendations workflow first |
| Downstream task not found | Verify task name and schema; offer to SHOW TASKS to help user find the right one |
| Insufficient permissions for ALERT creation | Report required privilege: `CREATE ALERT` on schema |
| Warehouse not set | Alerts require a warehouse; ask user for the warehouse name |
| User asks to remove a circuit breaker | Run: `DROP ALERT <database>.<schema>.<alert_name>` (after confirmation) |

## Notes
- This workflow creates a Snowflake ALERT object — a **Write** operation requiring explicit approval
- The ALERT runs on the specified schedule, not in real-time (expectation status has inherent scheduling latency)
- For real-time protection, set the alert schedule to match the DMF schedule (e.g., both `TRIGGER_ON_CHANGES`)
- The suspend action is conservative by design — always requires manual resume to restart the pipeline
- **Async limitation:** This circuit breaker is asynchronous: the ALERT runs on a schedule, so the downstream TASK or DYNAMIC TABLE may run one more time before the suspend takes effect. For synchronous blocking of dynamic table refreshes, Snowflake does not currently offer a native "block refresh until expectations pass" option; alternatives include running quality checks inside the pipeline (e.g. in a task step before refresh) or using manual gates.
