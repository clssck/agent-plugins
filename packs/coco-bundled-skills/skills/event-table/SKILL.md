---
name: event-table
description: "Manage Snowflake event tables and telemetry configuration. Use when: viewing/configuring event tables, checking telemetry setup, getting/setting telemetry levels, querying event table data, understanding telemetry formats. Triggers: event table, get event table, show event table, current event table, event table setup, event table configuration, telemetry, telemetry setup, telemetry configuration, telemetry levels, get telemetry, show telemetry, check telemetry, log level, trace level, metric level, logging setup, tracing setup, observability setup, event table format, telemetry format, log format, trace format, metric format."
tools: ["snowflake_sql_execute", "ask_user_question"]
---

# Event Table Router Skill

This skill routes to specialized skills for event table and telemetry tasks.

## Workflow

### Step 1: Detect User Intent

Analyze the user's request and route to the appropriate sub-skill:

| User Intent | Triggers | Action |
|-------------|----------|--------|
| Get/show event table & telemetry config (read-only) | "get event table", "show event table", "current event table", "which event table", "show telemetry levels", "get telemetry", "check telemetry", "telemetry levels", "show log level", "show trace level", "show metric level" | **Load** `event-table-get-setup/SKILL.md` |
| Set up/modify event table & telemetry | "event table setup", "event table configuration", "set log level", "set trace level", "set metric level", "configure telemetry", "create event table", "associate event table", "logging setup", "tracing setup", "observability setup" | **Load** `event-table-modify-setup/SKILL.md` |
| Telemetry format, schema, or product events | "event table format", "telemetry format", "log format", "trace format", "metric format", "telemetry schema", "parse telemetry", "query event table", "event table schema", "telemetry structure", "dynamic table events", "DT events", "DT refresh", "DT telemetry", "DT logs", "DT refresh failures", "task events", "task logs", "task telemetry", "task failures", "task success", "snowpark events", "procedure logs", "UDF logs", "procedure errors", "python procedure", "javascript procedure", "openflow events", "openflow telemetry", "connector events", "replication events" | **Load** `event-table-telemetry-format/SKILL.md` |

### Step 2: Route to Specialized Skill

**Mandatory:** You must load one or more of the below specialized skills, because this router skill does not have enough knowledge.

**If request mentions getting/viewing event tables or telemetry config (read-only):**
- **-> Load**: [event-table-get-setup/SKILL.md](event-table-get-setup/SKILL.md)
- Follow the event table get setup workflow
- The skill will display current configuration without making changes

**If request mentions setting up or modifying event tables or telemetry:**
- **-> Load**: [event-table-modify-setup/SKILL.md](event-table-modify-setup/SKILL.md)
- Follow the event table modify setup workflow
- The skill will guide you through creating, altering, or associating event tables and setting telemetry levels

**If request mentions telemetry format, schema, querying event table data, or product-specific events (dynamic tables, tasks, Snowpark, OpenFlow):**
- **-> Load**: [event-table-telemetry-format/SKILL.md](event-table-telemetry-format/SKILL.md)
- Follow the telemetry format workflow
- The skill identifies the product, finds the correct format, discovers the event table, and generates SQL queries

**If request is to test the skill:**
- Print "hello world"
- Exit

---

## Related Skills (Can Be Loaded Directly)

- [event-table-get-setup/SKILL.md](event-table-get-setup/SKILL.md) - Get/show current event table and telemetry level configuration (read-only)
- [event-table-modify-setup/SKILL.md](event-table-modify-setup/SKILL.md) - Modify event table configuration and telemetry levels
- [event-table-telemetry-format/SKILL.md](event-table-telemetry-format/SKILL.md) - Parse telemetry formats and generate SQL queries for event tables (includes references for dynamic tables, tasks, Snowpark, OpenFlow)

## Stopping Points

- After routing: Sub-skill handles its own stopping points
