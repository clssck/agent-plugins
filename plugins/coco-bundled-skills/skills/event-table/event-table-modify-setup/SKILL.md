---
name: event-table-modify-setup
description: "Set up or verify Snowflake event table configuration and telemetry levels (LOG_LEVEL, LOG_EVENT_LEVEL, TRACE_LEVEL, METRIC_LEVEL). Use when: viewing event table setup, getting event table configuration, checking telemetry setup, getting telemetry levels, setting log/trace/metric/event levels, configuring observability. Triggers: event table, event table setup, event table configuration, get event table, show event table, current event table, which event table, telemetry, telemetry setup, telemetry configuration, telemetry levels, get telemetry, show telemetry, check telemetry, log level, log event level, trace level, metric level, logging setup, tracing setup, observability setup."
tools: ["snowflake_sql_execute", "ask_user_question"]
---

# Event Table Setup Skill

This skill edits/modifies the event table setup. The operations that can be done with the event table are as under
1. Create an event table
2. Alter an event table
3. Associate an event table
4. Modify telemetry levels

## Workflow
1. Categorize the intent from the user prompt using the supported operations.
2. Always print the current setup using the event-table-get-setup skill before proceeding.
3. ** Important ** For every operation pick sensible defaults and present the final sql and get confirmation.
4. Execute the operation.
5. Verify the result by running the event-table-get-setup skill again.
6. Ask the user if they want to do follow up event table supported operations.

### Create an event table
1. The documentation is here https://docs.snowflake.com/en/sql-reference/sql/create-event-table
2. Pick a sensible default name for the table
3. Use the current schema if no schema is provided. If no current schema exists, ask the user to provide one.
4. Always use the sql `create event table if not exists <table_name> change_tracking = true;`

### Alter an event table
1. The documentation is here https://docs.snowflake.com/en/sql-reference/sql/alter-table-event-table

### Associate an event table
1. Event tables can be associated at the account or database level.
2. The documentation is here https://docs.snowflake.com/en/developer-guide/logging-tracing/event-table-setting-up
3. Determine the database or account that an event table needs to be associated to from the user prompt. The user prompt may not directly specify the database or account.
4. Always try to associate at the narrower scope when possible. eg. If the association can be done at a database level, do not associate at the account level
5. If more than 3 narrower scope event table associations are required for the requested objects, try moving up the scope hierarchy to reduce the number of associations required. Pick the narrowest scope which results in <= 3 associations. eg. if the user prompt resolves to objects in 3 different databases, set the event table at the database scope. However if the user prompt resolves to objects in 4 different databases, then set the association at the account level.
6. UDFs, Stored Procedures, Tasks, Dynamic Tables, Pipes are schema level objects that use the database level override for the event table if available
7. SPCS and Native apps use the account level table
8. **Important** Let the user know that modifying the association will affect all objects at that level (database/account) that send to the event table

### Modify telemetry levels
1. The documentation is here https://docs.snowflake.com/en/developer-guide/logging-tracing/telemetry-levels
2. The supported objects to set telemetry levels are 'account', 'database', 'schema', 'task', 'function', 'stored_procedure', 'dynamic table', 'pipe'
3. Find the objects whose telemetry level needs to changed from the user prompt. Determine the least level in the database->schema-object lineage where the change can be affected

** Examples **
`ALTER DATABASE <name> SET <desired_level> = <desired_value>'`
`ALTER TASK <name> SET LOG_LEVEL = DEBUG`
`ALTER TASK <name> SET LOG_EVENT_LEVEL = DEBUG`  -- Required for logs to appear in event table'
`ALTER PROCEDURE <name> SET LOG_LEVEL = DEBUG`
`ALTER PROCEDURE <name> SET LOG_EVENT_LEVEL = DEBUG`  -- Required for logs to appear in event table'

## Troubleshooting
1. If the current role does not have permissions for the operation, try finding a role that has the required permissions. Get confirmation from the user before proceeding using the found role. If no such role exists, let the user know of the permissions required for the operation
2. Setting/associating an event table at the database level is an enterprise edition feature. If a user not able to associate an event table at the databse level, it is possible that the account is not on enterprise edition or higher.
