---
name: alert-create-alter
description: "Create and alter Snowflake alerts with condition queries. Use when: user wants to create a new alert, modify an existing alert, set up monitoring for a product. Triggers: create alert, new alert, add alert, alter alert, modify alert, change alert, alert condition, monitor with alert."
---

# Alert Create & Alter

Creates and modifies Snowflake alerts with appropriate condition queries based on user requirements.

## Defaults

| Setting | Default Value |
|---------|---------------|
| **Compute** | Serverless (no warehouse) — only if `EXECUTE MANAGED ALERT` privilege is granted; otherwise use a warehouse |
| **Schedule** | 5 minutes |
| **Alert name** | Auto-generated: `alert_<product>_<event_type>` (e.g., `alert_dynamic_table_failures`) |
| **Event table** | Account default (discovered via `event-table-get-setup` skill) |
| **Notification** | Email to current user (uses notification skill) |
| **Runtime config** | Not set (add `CONFIG` only when user wants parameterized logic) |

## Dependencies

This skill depends on other skills for specific functionality:

### Dependency Loading Contract
**⛔ MANDATORY — Before writing SQL for a given workflow step/path, load and confirm only the dependencies required for that step/path. Do NOT preload all dependencies up front.**

- Resolve dependency paths relative to this skill file (not from guessed working directories).
- Use the path returned by the skill loader/runtime as the source of truth.
- If loading fails (`File not found` or equivalent), stop SQL generation and resolve the dependency location via the runtime's skill/reference discovery mechanism.
- Continue only after the dependency required for the current step/path is successfully loaded.
- Route first, then load dependencies lazily. Template and custom paths require different dependency sets.
- Do NOT improvise SQL patterns that are explicitly defined by required dependency skills/references.

### Event Table Setup Skill
**⛔ MANDATORY — Load `../../event-table/event-table-get-setup/SKILL.md` BEFORE building any condition query.** The event table is the data source for the alert's condition query. Without the correct event table, the alert will either misfire or never fire (CONDITION_FALSE with no error).

- Event table names are NOT standardized — they vary by account and database.
- Do NOT assume, guess, or hardcode the event table name .
- The ONLY way to get the correct event table is by loading this skill, which runs the discovery queries.

This skill discovers:
- The account's default event table
- Any database-level event table overrides (if user specified a database scope)

**Use the discovered event table automatically** when generating the alert. If the user's alert targets a specific database that has an override, use that database's event table; otherwise use the account default.

The user can customize the event table later in Step 4 (Confirm Defaults or Customize) along with other settings like schedule and notification.

This skill provides:
- Account default event table discovery
- Database-level event table overrides
- Event table validation

### Notification Integration Skill
**ALWAYS** load `../../notification/notification-integration/SKILL.md` when:
- User needs to create a new notification integration (email or webhook)
- User wants to send alerts to Slack, Teams, or PagerDuty
- No suitable notification integration exists

### Telemetry Format Skill
**ALWAYS** load `../../event-table/event-table-telemetry-format/SKILL.md` when building condition queries for event table telemetry.

This router skill will provide the correct telemetry format for any product (Dynamic Tables, Tasks, OpenFlow, Snowpark, etc.), including:
- Field names and paths (e.g., `resource_attributes:"snow.executable.type"`)
- State values
- Filter conditions specific to each product

### Notification Content Skill
**ALWAYS** load `../../notification/notification-content/SKILL.md` in Step 6 to generate formatted notification content.

This skill provides:
- Pre-formatted content for Email (HTML with Snowflake branding), Slack (Block Kit), Teams (Adaptive Card), PagerDuty
- Tone detection from header/footer for emoji and severity mapping
- Query result formatting as tables

Invoke with:
- `query_id`: `SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID()`
- `integration_type`: `email`, `slack`, `teams`, `pagerduty`, or `default`
- `header`: Alert title
- `footer`: Closing message
- `email_subject`: (email only) Subject line

### Notification Dispatch Path Reference
**ALWAYS** load `../references/notification-dispatch-paths.md` before notification dispatch guidance.

This reference defines:
- Path A: template-managed dispatch via `SYSTEM$SEND_NOTIFICATION_FROM_ALERT`
- Path B: manual/custom dispatch via `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION`

### Alert Mute Reference
If the user asks for rate-limited notifications (for example, "send at most once per hour"), **MUST load** `../../notification/references/alert-muting.md` before generating alert SQL and apply action-level mute (throttle) logic from that reference.


## Workflow

### Step 1: Analyze User Request and Determine Path

First, analyze the user's initial question to determine if templated alerts are applicable.

**Templated alerts ARE applicable when:**
- User asks for "recommended alerts" or "best practice alerts" for "standard alerts" or "templated alerts" for a supported product
- User explicitly asks about alert templates

**Supported products for templated alerts:**
- OpenFlow
- Data Quality
- Tasks

**Templated alerts are NOT applicable when:**
- User wants to monitor products not in the supported list (e.g., Dynamic Tables, Warehouses, Stored Procedures)
- User specifies a custom condition or business logic (e.g., "alert when row count drops below 1000")
- User wants to monitor custom tables or data quality metrics
- User provides a specific query or condition
- User wants to monitor something not covered by templates (e.g., query performance, storage costs, specific column values)

**If templates are applicable**, ask:
```
Would you like to use Snowflake's recommended alert templates for [product]?
Templates provide best-practice conditions for common monitoring scenarios.

1. Yes - show me available templates
2. No - I want to create a custom alert condition
```

**If user chooses templates → proceed to Step 2A**
**If user chooses custom OR templates not applicable → proceed to Step 2B**

### Step 2A: Generate Alerts from Templates

**→ Load `../references/alert-templates.md`** for template discovery — the available templates catalog and the `LIST` / `GET` / `RENDER` function reference.

The templated create path issues a **single** native DDL statement —
`CREATE … FROM TEMPLATE <template_id> … TEMPLATE_PARAMS = '{…}'` — rendered in-process.
Do NOT call `SYSTEM$RENDER_ALERT_TEMPLATE` on this path
(it is only for the optional preview and the fallback in Step 9).

**→** If the template the user named is not in the list — or if `CREATE … FROM TEMPLATE` later fails because the template is unknown — follow the **⛔ Unknown / unavailable template** guard in `../references/alert-templates.md`.

1. **List available templates:**
   ```sql
   SELECT SYSTEM$LIST_ALERT_TEMPLATES();
   ```

2. **Present matching templates** for the user's product (e.g., "DATA_QUALITY", "TASKS", "OPENFLOW"). If the user named a template that is not listed, follow the **⛔ Unknown / unavailable template** guard in `../references/alert-templates.md`.

3. **Get template details** for the user's selected template:
   ```sql
   SELECT SYSTEM$GET_ALERT_TEMPLATE('<template_id>');
   ```
   This returns the template definition including `template_variables` with their names, descriptions, data types, and default values.

4. **Collect the template-variable values** from the user, falling back to each variable's `default_value` when the user does not specify one. These are the values that ride the `TEMPLATE_PARAMS` JSON.

5. **→ Load `../references/alert-templates-native-create.md`** for statement construction, pre-existence check, and escaping rules. The reference covers the DDL-clause vs `TEMPLATE_PARAMS` split, serverless and schedule rules, both JSON shapes, and a worked example.

Template-rendered alerts use Path A template-managed notification dispatch. Do not replace with manual send-call construction unless the user explicitly requests a custom action block.

**→ Proceed to Step 8 (Verify Privileges), then Step 9. Steps 3–7 are not needed for template-generated alerts.**

### Step 2B: Identify What User Wants to Monitor

Determine from the user's question:
- **Product/Object type**: e.g., Dynamic Table, Task, Stored Procedure, Query, Warehouse
- **Event type**: e.g., failures, errors, warnings, specific states
- **Scope**: e.g., specific object, database, schema, or account-wide

### Step 3: Build Custom Condition Query

**Important:** The condition query must return actual data rows (not just `TRUE/FALSE` or `COUNT(*)`). This data is used in the notification via `SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID()` to provide actionable context.

**CRITICAL: Condition Query Defines Action Block Columns**

The action block retrieves data using `RESULT_SCAN(SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID())`, which returns **exactly** the columns selected in the condition query. The action block can ONLY reference columns that exist in the condition query's SELECT list.

**Design the condition query with notification in mind:**
1. Select ALL columns you want to display in the notification
2. Use meaningful column aliases (these become the column names in the action block)
3. Format values in the condition query if needed (e.g., `TO_VARCHAR(timestamp, 'YYYY-MM-DD HH24:MI:SS') AS event_time`)
4. **ALWAYS include a timestamp field** in the condition query output:
   - If the source has a `timestamp` column, include it: `timestamp AS event_time` or `TO_VARCHAR(timestamp, 'YYYY-MM-DD HH24:MI:SS') AS event_time`
   - If no timestamp column exists, add the current timestamp: `CURRENT_TIMESTAMP() AS event_time`

**Good condition query** (returns useful data for notification):
```sql
SELECT 
    resource_attributes:"snow.database.name"::VARCHAR AS database_name, 
    resource_attributes:"snow.schema.name"::VARCHAR AS schema_name, 
    resource_attributes:"snow.executable.name"::VARCHAR AS object_name, 
    value:message::STRING AS error_message,
    TO_VARCHAR(timestamp, 'YYYY-MM-DD HH24:MI:SS') AS event_time
FROM <event_table>
WHERE ...
```

**Bad condition query** (returns no actionable data):
```sql
SELECT 1 FROM <event_table> WHERE ... LIMIT 1
SELECT COUNT(*) > 0 FROM ...
```

**Option A: Product with telemetry in event table**

If the user wants to monitor a product with telemetry in the event table, **ALWAYS load `../../event-table/event-table-telemetry-format/SKILL.md`** to get the correct schema.

**Workflow:**
1. **⛔ MANDATORY — Load `../../event-table/event-table-get-setup/SKILL.md`** to discover the correct event table.
2. **Load** `../../event-table/event-table-telemetry-format/SKILL.md` for the correct telemetry format for the product.
   **If the file is not found**, load the appropriate reference directly from `../../event-table/references/`:

   | Product | Fallback Reference |
   |---------|-------------------|
   | Dynamic Tables | **Load** `../../event-table/references/dynamic-table.md` |
   | Tasks | **Load** `../../event-table/references/task.md` |
   | OpenFlow | **Load** `../../event-table/references/openflow.md` |
   | Snowpark (UDFs, Procedures) | **Load** `../../event-table/references/snowpark.md` |

3. **Use the format from the skill or reference** to build the condition query targeting the discovered event table from step 1
4. **Add the time window filter** (see below)
5. Iterate with the user to refine the query

**DO NOT hardcode telemetry formats or event table names** - always discover the event table first, and use the telemetry format skill or the fallback references above for the correct schema, field names, and state values

**Important:** Always include the time window filter in scheduled alert condition queries. **Load** `../references/time-window.md` for the filter pattern and rationale.

**Note:** This time window filter is NOT used for "Alert on New Data" — those alerts trigger on new rows without time-based filtering.

**Option B: Custom condition query**

If the user wants to monitor something not covered by event-table/event-table-telemetry-format (e.g., data quality, business metrics, custom tables):

Ask the user:
```
Please provide a SELECT query that returns rows when the alert condition is met.
The alert will trigger when this query returns one or more rows.

Important: Return actual data columns (not just SELECT 1 or COUNT(*)) so the notification 
includes actionable details about what triggered the alert.

Note: Do not include time filters - I will automatically add the proper time window:
  timestamp >= TIMESTAMPADD('second', -60, CONVERT_TIMEZONE('UTC', SNOWFLAKE.ALERT.LAST_SUCCESSFUL_SCHEDULED_TIME())::TIMESTAMP_NTZ)
  AND timestamp < TIMESTAMPADD('second', -60, CONVERT_TIMEZONE('UTC', SNOWFLAKE.ALERT.SCHEDULED_TIME())::TIMESTAMP_NTZ)

Example (returns useful data for notification):
SELECT id, status, error_message, created_at FROM my_table WHERE status = 'ERROR'
```

Validate the user's query:
- Must be a SELECT statement
- Must return actual data columns (not just `SELECT 1` or `COUNT(*)`)
- Identify the timestamp column to use for the time window filter
- Should return rows only when alerting is needed

**After receiving the query, confirm:**
```
I'll use this as the alert condition:
<user_query>

The alert will trigger when this query returns results. Does this look correct?
```

### Step 4: Confirm Defaults or Customize

**Check if Alert on New Data is better:**

If the condition query does NOT target the event table, suggest:
```
If your alert monitors a table that may have infrequent inserts. 
Consider using "Alert on New Data" instead of a scheduled alert:
- Triggers immediately when new matching rows are inserted
- More cost-effective for tables with sporadic updates
- Requires change tracking on the table: ALTER TABLE <table> SET CHANGE_TRACKING = TRUE

Would you like to use Alert on New Data instead? (recommended for infrequent inserts)
```

**If user chooses Alert on New Data:**
- Remove SCHEDULE parameter
- Remove timestamp filter from condition
- Note: Requires MODIFY privilege on the target table to enable change tracking

**Present the defaults (from the Defaults table above) to the user** and ask if they want to customize any setting. Only ask for customization if user wants to change defaults.

### Step 4.5: Optional Runtime Config (`CONFIG`)

**Source of truth (syntax and behavior):**
- [Passing configuration to an alert](https://docs.snowflake.com/en/user-guide/alerts#label-alerts-config)
- **Load** `../references/runtime-config.md` for canonical CREATE/ALTER syntax examples.

**When to use runtime config:**
- Use runtime config when the alert needs operator-tunable behavior (for example thresholds, enable flags, routing) without editing alert SQL.

**When NOT to use runtime config:**
- Do not use when users want hardcoded behavior and no runtime tuning.

**Defaulting behavior (minimize setup load):**
- If users do not provide runtime-config values, choose sensible defaults based on the alert intent.
- Show the proposed default `CONFIG` JSON to the user before execution.
- Let the user override any default; if no changes are requested, proceed with defaults.

For runtime-config syntax examples, **load** `../references/runtime-config.md`.

### Step 5: Set Up Notification Integration

**Before generating the alert, ensure a notification integration exists.**

1. **Check for existing integrations:**
   ```sql
   SHOW NOTIFICATION INTEGRATIONS;
   ```

2. **→ If no suitable integration exists, load `../../notification/notification-integration/SKILL.md` and follow its workflow to create the integration.**
3. If a suitable webhook integration exists, check with the user if they want to send the notification there instead.

### Step 6: Generate Notification Content and Dispatch Strategy

**MANDATORY — Do NOT skip this step.**

Then load references in this order:

1. **Load `../references/notification-dispatch-paths.md`** to confirm Path A vs Path B.
2. **Load `../../notification/notification-content/SKILL.md`** to generate notification content.

If Path B applies, also **load `../../notification/notification-send/SKILL.md`** for exact send-call syntax. If Path A applies, do not force manual `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION` construction.

Invoke with:

| Parameter | Value |
|-----------|-------|
| `query_id` | `SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID()` |
| `integration_type` | `email`, `slack`, `teams`, `pagerduty`, or `default` |
| `header` | Alert title (e.g., "Dynamic Table Failures Detected") |
| `footer` | Closing message (e.g., "Powered by Snowflake Alerts") |
| `email_subject` | (email only) Email subject line |
| `webhook_body_template` | (webhook only) `WEBHOOK_BODY_TEMPLATE` from `DESCRIBE NOTIFICATION INTEGRATION` output in Step 5 |
| `column_metadata` | List of column names/aliases from the condition query (from Step 3). E.g., `['EVENT_TIME', 'DT_NAME', 'DATABASE_NAME', 'STATE']`. **Strongly recommended** — avoids error-prone `DESCRIBE RESULT` at runtime. |

For Path B only, `notification-send` remains the single source of truth for argument order, allowed properties, and integration JSON. Do not guess send-call syntax.

**⛔ CRITICAL — Newline handling in alert action blocks (webhook integrations only: Slack, Teams, PagerDuty):**

This does NOT apply to email integrations. Only apply when the integration type is a webhook (Slack, Teams, PagerDuty).

Use `\\\\n` (four backslashes + n) for newlines in string literals inside alert action blocks. The alert action block is stored as a string, so normal `\n` or `\\n` will be consumed during storage and break webhook delivery.

```sql
-- ✅ CORRECT inside alert action block (webhook only)
LET message VARCHAR := 'Line 1\\\\nLine 2\\\\nLine 3';
LISTAGG(col, '\\\\n')

-- ❌ WRONG — newlines consumed during alert storage
LET message VARCHAR := 'Line 1\nLine 2';
LET message VARCHAR := 'Line 1\\nLine 2';
```

**IMPORTANT: Action block column alignment**

The `notification-content` skill (Step 6) should have already produced the action block. Before embedding it in the CREATE ALERT statement, verify that the action block accesses condition query columns correctly using one of these two valid approaches:

**a. Static column references** — the action block references the exact column names or aliases from the condition query. If the condition query defines an alias, the alias must be used (the original column path is not available via `RESULT_SCAN`).

**b. Dynamic column discovery** — the action block runs `DESCRIBE RESULT SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID()` as a **standalone statement** first, then reads column names from `TABLE(RESULT_SCAN(LAST_QUERY_ID()))`, then uses those names to access data from `TABLE(RESULT_SCAN(SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID()))`. `DESCRIBE RESULT` must NEVER be embedded in a SELECT, cursor, or any other statement — it is a standalone command.

In either case, the action block **cannot** reference columns that don't exist in the condition query output.

The output of this step is the alert's `ACTION` block for Step 7.


### Step 7: Generate CREATE ALERT Statement

**Choose template based on alert type:**

| Alert Type | Reference |
|------------|-----------|
| Scheduled alert (default) | **Load** `../references/scheduled-alert-template.md` |
| Alert on new data | **Load** `../references/alert-on-new-data-template.md` |

**Pass to template:**
- The condition query (from Step 3)
- The formatted content (from Step 6)
- The integration config (from Step 5)
- Runtime config JSON (optional, from Step 4.5)

**Supporting references (load as needed):**

| Topic | Reference |
|-------|-----------|
| Time window filter | **Load** `../references/time-window.md` |
| Action-level muting / throttle | **Load** `../../notification/references/alert-muting.md` when requested |

**Alert naming convention:**
- `alert_dynamic_table_failures` - for DT failure monitoring
- `alert_task_errors` - for task error monitoring
- `alert_<product>_<event_type>` - general pattern

### Step 8: Verify Privileges

**⚠️ STOP — Before creating the alert, verify the current role has the required privileges.**

Check the current role's grants against the **Required Privileges** table in the **Access Control** section below:

```sql
SHOW GRANTS TO ROLE <current_role>;
```

If the condition query references an event table, also run a test SELECT to verify the role can actually read it:

```sql
SELECT 1 FROM <event_table> LIMIT 0;
```

If this returns an error (e.g., "Insufficient privileges" or "does not exist or not authorized"), the current role lacks `SELECT` on the event table. **Do NOT proceed with alert creation** — the alert would silently fail at runtime.

**If any required privilege is missing:**
- Warn the user with the specific missing privilege(s)
- Suggest the `GRANT` statement(s) needed (these require a role with sufficient authority, e.g., `ACCOUNTADMIN`)
- **Do NOT proceed** until the user confirms the grants have been applied or chooses to proceed anyway

### Step 9: Present Complete Alert and Execute

**For template-generated alerts (Step 2A):**

1. Present the `CREATE … FROM TEMPLATE` statement to the user for approval.
2. After approval, **→ follow `../references/alert-templates-native-create.md`** for execution details (single DDL, no render round-trip).

**Error handling — three-way discrimination:**

- **`unexpected 'FROM'`** in a SQL compilation syntax error: the native clause is not available on this account — **→ load `../references/alert-templates-render-fallback.md`** and follow the render + execute flow.
- **A different syntax error** (unexpected token other than `FROM`): your generated SQL is malformed — fix it and retry the native statement; do **not** fall back.
- **`INVALID_PARAMETER_VALUE`** (unknown template, bad parameter name, missing required variable): surface the error to the user; do **not** fall back to render. For unknown template specifically, apply the **⛔** guard in `../references/alert-templates.md` — do not substitute a different template.

**For custom alerts (Step 2B):** Present the complete CREATE ALERT statement to the user. After approval, execute it.

### Step 10: Test the Alert (optional)

After executing the CREATE ALERT, ask the user:

```
The alert has been created. Would you like to test it now?

Testing will:
1. Execute the alert immediately (bypasses the schedule)
2. Check ALERT_HISTORY for the execution result
3. Check NOTIFICATION_HISTORY for delivery status

Would you like to test? (yes/no)
```

**If the user wants to test:**

Verify the current role has `EXECUTE ALERT` on the account (see **Required Privileges** in the **Access Control** section). If missing, warn the user and skip testing — proceed to Step 11 (Resume).

Execute the alert:

```sql
EXECUTE ALERT <alert_name>;
```

Then poll `ALERT_HISTORY` for the execution result (wait a few seconds for the row to appear):

```sql
SELECT STATE, SQL_ERROR_CODE, SQL_ERROR_MESSAGE
FROM TABLE(INFORMATION_SCHEMA.ALERT_HISTORY(
  ALERT_NAME => '<alert_name>',
  SCHEDULED_TIME_RANGE_START => DATEADD('minute', -5, CURRENT_TIMESTAMP())
))
ORDER BY SCHEDULED_TIME DESC
LIMIT 1;
```

**Interpret the result:**

| STATE | Meaning | Next Step |
|-------|---------|-----------|
| `TRIGGERED` | Condition matched, action executed | Check notification delivery (see Troubleshooting § 2) |
| `CONDITION_FALSE` | Condition query returned no rows | Expected if no matching events exist yet — not an error |
| `CONDITION_FAILED` | Condition query has a SQL error | Check `SQL_ERROR_MESSAGE`, fix the condition query |
| `ACTION_FAILED` | Action block has a SQL error | Check `SQL_ERROR_MESSAGE`, fix the action block |

On any error (`CONDITION_FAILED`, `ACTION_FAILED`, or `FAILED`), follow the **Troubleshooting** section below to diagnose and fix.

### Step 11: Resume the Alert

**After testing (or if user skipped testing), remind user to resume:**
```sql
ALTER ALERT <alert_name> RESUME;
```

## ALTER ALERT Operations

**CRITICAL: An alert MUST be suspended before it can be altered.** Any `ALTER ALERT ... SET`, `MODIFY CONDITION`, or `MODIFY ACTION` command will fail if the alert is currently running. Always suspend first, make changes, then resume.

**IMPORTANT SYNTAX NOTE:** The `MODIFY CONDITION` and `MODIFY ACTION` clauses do NOT use `=`. This is different from `SET` clauses.

```sql
-- CORRECT syntax (no = after MODIFY):
ALTER ALERT <name> MODIFY CONDITION EXISTS (<query>);
ALTER ALERT <name> MODIFY ACTION <action>;

-- WRONG syntax (will cause syntax error):
ALTER ALERT <name> MODIFY CONDITION = EXISTS (<query>);  -- ERROR!
ALTER ALERT <name> MODIFY ACTION = <action>;             -- ERROR!

-- SET clauses DO use = (for comparison):
ALTER ALERT <name> SET SCHEDULE = '10 MINUTE';
ALTER ALERT <name> SET WAREHOUSE = MY_WH;
```

### Step 1: Identify and Describe Existing Alerts

When the user wants to modify an alert, first find and describe matching alerts.

**Find alerts matching user's description:**
```sql
SHOW ALERTS LIKE '%<search_term>%';
```

**Or list all alerts in a database/schema:**
```sql
SHOW ALERTS IN SCHEMA <database>.<schema>;
```

**Describe the matching alert(s) to the user:**
```sql
DESCRIBE ALERT <alert_name>;
```

Present the alert details:
```
Found alert: <alert_name>
- State: <STARTED/SUSPENDED>
- Schedule: <schedule>
- Warehouse: <warehouse or SERVERLESS>
- Config: <JSON config or NULL>
- Condition: <condition_query>
- Action: <action>
- Owner: <owner>
- Last triggered: <timestamp or N/A>
```

If multiple alerts match, list them and ask the user to select which one to modify.

### Step 2: Suspend the Alert (if running)

**The alert must be suspended before any modification.** If the alert state from Step 1 is `STARTED`, suspend it first:

```sql
ALTER ALERT <alert_name> SUSPEND;
```

If the alert is already `SUSPENDED`, skip this step.

### Step 3: Apply Modifications

Once the alert is suspended, proceed with the appropriate operation:

#### Modify Schedule (for scheduled alerts)
```sql
ALTER ALERT <alert_name> SET SCHEDULE = '<new_interval>';
```

#### Modify Warehouse
```sql
ALTER ALERT <alert_name> SET WAREHOUSE = <new_warehouse>;
```

#### Modify Condition
```sql
ALTER ALERT <alert_name> MODIFY CONDITION EXISTS (<new_condition_query>);
```

#### Modify Action
```sql
ALTER ALERT <alert_name> MODIFY ACTION <new_action>;
```

#### Modify Runtime Config
For ALTER `SET CONFIG` syntax, **load** `../references/runtime-config.md`.

#### Remove Runtime Config
```sql
ALTER ALERT <alert_name> UNSET CONFIG;
```

### Step 4: Resume the Alert (if it was running)

If the alert was `STARTED` before the modification (i.e., it was suspended in Step 2), resume it:

```sql
ALTER ALERT <alert_name> RESUME;
```

If the alert was already `SUSPENDED` before the modification, leave it suspended unless the user explicitly asks to resume.

## Access Control

The current role must have these privileges for alert operations. Missing privileges will cause silent failures or runtime errors — verify before creating.

### Required Privileges

| Privilege | Scope | Required For |
|-----------|-------|--------------|
| `CREATE ALERT` | Schema where alert is created | Creating new alerts |
| `EXECUTE ALERT` | Account | **Required for all alert execution** — alerts will not run (scheduled or manual) without this privilege |
| `EXECUTE MANAGED ALERT` | Account | Serverless alerts (no warehouse). **If missing, do NOT default to serverless — use a warehouse instead** |
| `OWNERSHIP` | Alert | Full control: alter, drop, and implicitly grants all other alert-level privileges. The creating role is the owner by default |
| `OPERATE` | Alert | Suspend (`ALTER ALERT … SUSPEND`) and resume (`ALTER ALERT … RESUME`) alerts not owned by the current role |
| `USAGE` | Database and schema where alert is created/edited | All alert operations |
| `USAGE` | Warehouse (if non-serverless) | Alert execution with a warehouse |
| `SELECT` | Event table | Condition queries that read from the event table |
| `USAGE` | Database and schema of the event table | Condition queries that read from the event table |

### Verification

```sql
SHOW GRANTS TO ROLE <current_role>;
```

Check the output against the table above. Key items:
- **`EXECUTE ALERT`** on account — without this, nothing runs (scheduled or manual)
- **`CREATE ALERT`** on the target schema
- **`EXECUTE MANAGED ALERT`** on account — if missing, automatically switch to a warehouse; do not offer serverless as an option
- **`OPERATE`** on the alert — needed for suspend/resume if the current role does not own the alert

## Output

- Complete CREATE ALERT statement ready to execute
- ALTER ALERT statements for modifications
- Optional test execution with troubleshooting
- Reminder to resume the alert after creation/testing

## Troubleshooting

After executing or resuming an alert, use these functions to diagnose issues:

### 1. Check Alert Execution History

Use [ALERT_HISTORY](https://docs.snowflake.com/en/sql-reference/functions/alert_history) to check if the alert ran and whether the condition or action failed:

```sql
SELECT *
FROM TABLE(INFORMATION_SCHEMA.ALERT_HISTORY(
  ALERT_NAME => '<alert_name>',
  SCHEDULED_TIME_RANGE_START => DATEADD('hour', -1, CURRENT_TIMESTAMP())
))
ORDER BY SCHEDULED_TIME DESC;
```

Key columns: `STATE` (`TRIGGERED`, `CONDITION_FALSE`, `CONDITION_FAILED`, `ACTION_FAILED`, `FAILED`), `SQL_ERROR_CODE`, `SQL_ERROR_MESSAGE`.

### 2. Check Notification Delivery

If the alert executed successfully (`TRIGGERED`) but the notification did not arrive, use [NOTIFICATION_HISTORY](https://docs.snowflake.com/en/sql-reference/functions/notification_history) to check delivery status:

```sql
SELECT *
FROM TABLE(INFORMATION_SCHEMA.NOTIFICATION_HISTORY(
  INTEGRATION_NAME => '<integration_name>',
  START_TIME => DATEADD('hour', -1, CURRENT_TIMESTAMP())
))
ORDER BY CREATED DESC;
```

Key columns: `STATUS` (`QUEUED`, `SUCCESS`, `RETRIABLE_FAILURE`, `FAILURE`), `ERROR_MESSAGE`.

If the status is `FAILURE` or `RETRIABLE_FAILURE`, first determine dispatch path with `../references/notification-dispatch-paths.md`:

- **Path A (template-managed):** validate alert config notification keys and use `NOTIFICATION_HISTORY` as runtime evidence for integration/mode resolution.
- **Path B (manual/custom):** re-load `../../notification/notification-send/SKILL.md` to verify exact `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION` syntax and allowed properties, then re-load `../../notification/notification-content/SKILL.md` to verify wrapper type.
