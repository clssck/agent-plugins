---
name: event-table-get-setup
description: "Get/show current Snowflake event table configuration and telemetry levels. Read-only inspection of observability setup. Use when: viewing event table setup, getting current event table, checking telemetry levels, showing log/trace/metric levels. Triggers: get event table, show event table, current event table, which event table, show telemetry levels, get telemetry, check telemetry, telemetry levels, show log level, show trace level, show metric level."
tools: ["snowflake_sql_execute"]
---

# Event Table Get Setup (Read-Only)

This skill displays the current event table configuration and telemetry levels. It does NOT modify any settings.

**⚠️ IMPORTANT: You MUST use the EXACT table formats specified below. Do not modify column names, column order, or add extra columns.**

## Workflow

### Step 1: Get Event Table Usage

Show which event tables are configured at account and database levels.

1. Get the database(s) from the user prompt, to check for the active event table
2. If no database is asked for, use the current database in the session
3. If no database exists in the session, pick 10 databases that the user has access to using `SHOW DATABASES LIMIT 10`
4. Use `SHOW PARAMETERS LIKE 'EVENT_TABLE' IN DATABASE {db}` to get the active event table for every database selected.
5. Use the level field from the output above to determine the overriding scope of the event table for each database
6. Also select the account level table using `SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT`
7. **MANDATORY**: Create a table with title "Event Table Usage" using the EXACT format below:
   - Column 1: "Objects" - the object types using this event table
   - Column 2: "Scope" - either "Account" or the database name(s)
   - Column 3: "Event Table" - the fully qualified event table name
   - Column 4: "Level" - the override level (ACCOUNT or DATABASE)

**Rules for populating the table:**
a. Object types UDF's, Stored Procedures, Tasks, Dynamic Tables, Pipes are schema level objects that will use the database level override. So add a row "UDF's, Stored Procedures, Tasks, Dynamic Tables, Pipes" for every database level override. For these objects in databases that do not have a database level override, add a single row and list the databases they are under in the "Scope" column and the account level event table.
b. Add a row each for "Native Apps", "SPCS" which use the account level event table
c. Find the event table for "Data Quality" and add as rows as well. Their event tables are possibly in snowflake.local schema.
d. Scope column is either "Account" or the database name(s). Only include the database name or account if its event table has been explicitly checked
e. Event Table column is the associated event table.
f. Level is the override level of the event table

**MANDATORY Output Table Format (use exactly these columns):**
| Objects | Scope | Event Table | Level |
|---------|-------|-------------|-------|
| UDFs, Stored Procedures, Tasks, Dynamic Tables, Pipes | DB_1 | db_1.schema_1.events | DATABASE |
| UDFs, Stored Procedures, Tasks, Dynamic Tables, Pipes | DB_2, DB_3 | snowflake.telemetry.events | ACCOUNT |
| Native Apps | Account | snowflake.telemetry.events | ACCOUNT |
| SPCS | Account | snowflake.telemetry.events | ACCOUNT |
| Data Quality | Account | SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS_RAW | ACCOUNT |

### Step 2: Get Telemetry Levels

Show LOG_LEVEL, LOG_EVENT_LEVEL, TRACE_LEVEL, METRIC_LEVEL settings.

**Supported object types:** account, database, schema, task, function, stored_procedure, dynamic table, pipe

**⚠️ MANDATORY: Determine which objects to query telemetry levels for:**

1. Check the user prompt for specific objects (e.g., "check telemetry for schema X", "show log level for my_task").
2. **⚠️ Cap at 10 objects.** If the user requests a class of objects (e.g., "all tasks in schema X"), enumerate them using the appropriate SHOW command (e.g., `SHOW TASKS IN SCHEMA X`) and pick **at most 10**. Do NOT query more than 10 individual objects — truncate and inform the user if more exist.
3. **⚠️ MANDATORY: Walk the full object hierarchy.** If multiple objects are requested, you **MUST** also query their **common ancestors** up to the account level. Telemetry levels are inherited, so every scope in the chain matters.
   - Example: User requests tasks in `DB1.SCHEMA_A` and `DB2.SCHEMA_B` → you must query ALL of:
     - Each task (the requested objects)
     - `SCHEMA_A` and `SCHEMA_B` (parent schemas)
     - `DB1` and `DB2` (parent databases)
     - `ACCOUNT` (root ancestor)
   - **Do NOT stop at the requested object level.** Always walk up to `ACCOUNT`.
4. **If the user does NOT specify objects**, you **MUST** query ALL THREE of these scopes — do NOT skip any:
   - **Account**: `SHOW PARAMETERS LIKE '%_LEVEL' IN ACCOUNT`
   - **Current database**: `SHOW PARAMETERS LIKE '%_LEVEL' IN DATABASE <current_database>`
   - **Current schema**: `SHOW PARAMETERS LIKE '%_LEVEL' IN SCHEMA <current_database>.<current_schema>`
5. For each object, get all telemetry levels using `SHOW PARAMETERS LIKE '%_LEVEL' IN {obj.type} {obj.name}`
6. **MANDATORY**: Create a table using the EXACT format below. Only include rows for LOG_LEVEL, LOG_EVENT_LEVEL, TRACE_LEVEL, and METRIC_LEVEL. If there are multiple objects, stick to the same table format

**MANDATORY Output Table Format (use exactly these columns):**
| Parameter | Value | Level | Object |
|-----------|-------|-------|--------|
| LOG_LEVEL | DEBUG | ACCOUNT | - |
| LOG_EVENT_LEVEL | DEBUG | DATABASE | DB_1 |
| TRACE_LEVEL | ALWAYS | DATABASE | DB_1 |
| METRIC_LEVEL | ALL | DATABASE | DB_1 |

### Step 3: Summary

After displaying both tables, provide a brief summary:

1. **Event table status** - Is an event table configured?
2. **Telemetry readiness** - Are logs being captured to event table?
3. **Common issues** - Flag if LOG_LEVEL is set but LOG_EVENT_LEVEL is OFF

**Critical Note:** For logs to appear in an event table, BOTH `LOG_LEVEL` AND `LOG_EVENT_LEVEL` must be set. Setting only `LOG_LEVEL` generates logs but they won't appear in the event table.

## Reference: Valid Values

| Parameter | Valid Values | Description |
|-----------|--------------|-------------|
| LOG_LEVEL | OFF, TRACE, DEBUG, INFO, WARN, ERROR, FATAL | Controls which log messages are generated |
| LOG_EVENT_LEVEL | OFF, TRACE, DEBUG, INFO, WARN, ERROR, FATAL | Controls which logs are sent to event table |
| TRACE_LEVEL | OFF, ALWAYS, ON_EVENT | Controls trace/span event collection |
| METRIC_LEVEL | NONE, ERRORS, ALL | Controls metric collection |

## Output

Two tables showing:
1. Event table configuration (account + database overrides)
2. Telemetry level settings with effective values

Plus a summary with any warnings about misconfiguration.
