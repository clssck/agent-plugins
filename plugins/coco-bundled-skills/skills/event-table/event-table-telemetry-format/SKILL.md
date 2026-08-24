---
name: event-table-telemetry-format
description: "Parse and explain telemetry formats (logs, metrics, traces, events) from Snowflake products in event tables. Use when: user asks about event table schema, telemetry format, log/trace/metric structure, or needs SQL to query telemetry data. Triggers: event table format, telemetry format, log format, trace format, metric format, telemetry schema, parse telemetry, query event table."
---

# Event Table Telemetry Format

Parses telemetry format from Snowflake products and generates SQL queries for event tables.

## Event Table Schema

Telemetry events are stored in `SNOWFLAKE.TELEMETRY.EVENTS` (or a custom event table) with the following structure:

| Column | Path | Description |
|--------|------|-------------|
| `timestamp` | - | When the event occurred |
| `resource_attributes` | `:"snow.executable.type"` | Object type (e.g., `'DYNAMIC_TABLE'`, `'TASK'`, `'STORED_PROCEDURE'`) |
| `resource_attributes` | `:"snow.executable.name"` | Object name |
| `resource_attributes` | `:"snow.database.name"` | Database name |
| `resource_attributes` | `:"snow.schema.name"` | Schema name |
| `resource_attributes` | `:"snow.query.id"` | Associated query ID |
| `record` | `:"severity_text"` | `ERROR`, `WARN`, or `INFO` |
| `record` | `:"name"` | Event name (e.g., `'refresh.status'`) |
| `record_type` | - | `'LOG'`, `'SPAN'`, `'SPAN_EVENT'`, `'EVENT'`, or `'METRIC'` |
| `value` | `:state` | State value (varies by event type) |
| `value` | `:message` | Message content |

**Important:** The `snow.*` resource attributes above apply to most Snowflake products (Tasks, Dynamic Tables, Stored Procedures, etc.). **OpenFlow does NOT use `snow.*` keys.** OpenFlow telemetry uses Kubernetes-level attributes (`k8s.namespace.name`, `k8s.pod.name`, `openflow.dataplane.id`) instead. See the OpenFlow reference for its specific schema.

## Workflow

**IMPORTANT** Follow the workflow steps as directed.

### Step 1: Identify Product(s) from User Prompt

Parse the user's request and extract the Snowflake product(s) for which they want telemetry format.

**Common product keywords:**

| User Mentions | Product |
|---------------|---------|
| dynamic table, DT, DT refresh, DT failures | Dynamic Tables |
| task, task run, task execution, task failures | Tasks |
| openflow, connector, data plane, replication | OpenFlow |
| snowpark, stored procedure, UDF, procedure logs, Python/JavaScript procedure | Snowpark |
| warehouse, query, query performance | Warehouse |
| data quality, data metric functions | Data Quality |

If the user's prompt is ambiguous or mentions multiple products, ask for clarification before proceeding. For each identified product, run Steps 2–4 in order until a format is found.

### Step 2: Load the External Product Skill

Check if a **top-level product skill** provides the telemetry format. These are authoritative because they are maintained by the product team.

**Known external skills with telemetry format:**

| Product | Skill Command | What It Provides |
|---------|--------------|------------------|
| Dynamic Tables | `dt-alerting` | Event Table Schema Reference for DT refresh events, states, alerting queries |

**Action:** Use the `skill` tool to load the external skill by name. Do NOT use `read` — you must use the `skill` tool.

Example for Dynamic Tables:
```
skill(command="dt-alerting")
```

**If the skill loads successfully:** Use its telemetry format definitions. Proceed to Step 5 (Generate SQL Query).

**If the skill is not found or fails to load:** Proceed to Step 3.

**If the product is NOT listed in the table above:** There is no external skill — proceed directly to Step 3 (do NOT skip to Step 4).

### Step 3: Query SYSTEM$LIST_ALERT_TEMPLATES() — MANDATORY

**IMPORTANT: You MUST always execute this step before Step 4. Do NOT read any `references/*.md` files before completing this step.**

```sql
SELECT SYSTEM$LIST_ALERT_TEMPLATES();
```

Parse the JSON result to find a matching template for the identified product. Then fetch the full template:

```sql
SELECT SYSTEM$GET_ALERT_TEMPLATE('<template_id>');
```

Parse and explain the format to the user, then proceed to Step 5.

**Only if `SYSTEM$LIST_ALERT_TEMPLATES()` returns an error or no matching template exists:** Proceed to Step 4.

### Step 4: Load Internal Telemetry Format References — LAST RESORT

**Only use this step if Step 3 failed or returned no matching template.** These are static fallback references:

| Product | Reference |
|---------|-----------|
| Dynamic Tables | **Load** `../references/dynamic-table.md` |
| Tasks | **Load** `../references/task.md` |
| OpenFlow | **Load** `../references/openflow.md` |
| Snowpark (UDFs, Procedures) | **Load** `../references/snowpark.md` |

**If a matching reference exists:** Load it and use its schema, query templates, and filters. Proceed to Step 5.

**If no match found:** Inform the user (see below).

### Step 5: Discover Event Table and Generate SQL Query

**If format was found (from Steps 2, 3, or 4):**

**First, discover the active event table** by loading `../event-table-get-setup/SKILL.md` and using its Step 1 workflow to find the event table for the objects the user is asking about. This determines whether the objects use a database-level override or the account-level default event table.

**Then build the SQL query** using:
- The **telemetry format** discovered in Steps 2–4 (column paths, filter conditions, state values)
- The **event table** discovered from `event-table-get-setup` (e.g., `MY_DB.MY_SCHEMA.MY_EVENTS` or `SNOWFLAKE.TELEMETRY.EVENTS`)

**After presenting the query, ask:**
```
Would you like me to:
- Use a different event table? (e.g., MY_DB.MY_SCHEMA.MY_EVENT_TABLE)
- Filter by a specific object?
- Adjust the time range?
```

If user provides values, update the query and re-present it.

**If no format was found in any previous step:**

Inform the user:
```
No documented telemetry format exists for [product] in the available skills or alert templates.

You can check the Snowflake documentation for telemetry support:
- https://docs.snowflake.com/en/developer-guide/logging-tracing/logging-tracing-overview
- https://docs.snowflake.com/en/sql-reference/account-usage/event-table-columns
```

## Tools

### SYSTEM$LIST_ALERT_TEMPLATES()

Lists all available telemetry templates.

**Usage:**
```sql
SELECT SYSTEM$LIST_ALERT_TEMPLATES();
```

**Returns:** JSON array of template metadata (IDs, names, types)

### SYSTEM$GET_ALERT_TEMPLATE(template_id)

Gets detailed format specification for a template.

**Usage:**
```sql
SELECT SYSTEM$GET_ALERT_TEMPLATE('<template_id>');
```

**Returns:** JSON with field definitions, types, and descriptions

## Output

- **Format explanation**: Human-readable description of telemetry fields
- **SQL queries**: Ready-to-run queries against the event table
