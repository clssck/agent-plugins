---
name: enable-native-app-logging
parent_skill: native-app-consumer
---

# Enable Logging & Troubleshoot a Native App (Consumer)

## When to Load

From the root `native-app-consumer` skill when the user wants to enable logging, set up event sharing, or troubleshoot an installed native app by querying its logs, traces, and errors.

## Prerequisites

- An installed native app in the consumer account
- ACCOUNTADMIN role (or a role with MANAGE EVENT SHARING privilege)

---

## Workflow

### Step 0: Identify the Application

If the app name is already known from a parent skill, skip to Step 1.

Otherwise, **Ask** the user:
```
What is the name of the installed application you want to enable logging for?
```

**⚠️ MANDATORY STOPPING POINT**: Do NOT proceed until user responds.

Verify the app exists:
```sql
SHOW APPLICATIONS LIKE '<app_name>';
```

If no results, inform the user the application was not found.

---

### Step 1: Set Up an Event Table

**Goal:** Ensure the account has an active event table — without one, all log messages and trace events from the app are discarded.

```sql
SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT;
```

If the `value` is empty, help the user set up an active event table before proceeding.

---

### Step 2: Review Telemetry Event Definitions

**Goal:** Show the consumer what telemetry the app is configured to share and which definitions are required vs optional.

```sql
SHOW TELEMETRY EVENT DEFINITIONS IN APPLICATION <app_name>;
```

Present results grouped by sharing type:

- **Required (MANDATORY)**: Enabled automatically at install. Cannot be disabled.
- **Optional**: Can be enabled/disabled by you. Enabling shares additional telemetry with the provider.

**⚠️ MANDATORY STOPPING POINT**: Ask the user:
> "Here are the telemetry event definitions for this app:
> [table of name, type, sharing, status]
>
> Which optional event definitions would you like to enable? You can say 'all' to enable everything, list specific ones, or 'skip' to only keep the required ones."

---

### Step 3: Enable Event Sharing

**Goal:** Enable the event definitions the user approved.

**If the app has required (MANDATORY) event definitions and `authorize_telemetry_event_sharing` is not yet true:**
```sql
ALTER APPLICATION <app_name> SET AUTHORIZE_TELEMETRY_EVENT_SHARING = true;
```

**If the user wants to enable specific optional event definitions:**
```sql
ALTER APPLICATION <app_name> SET SHARED TELEMETRY EVENTS ('<EVENT_NAME_1>', '<EVENT_NAME_2>');
```

For example, to enable traces and debug logs:
```sql
ALTER APPLICATION <app_name> SET SHARED TELEMETRY EVENTS ('SNOWFLAKE$TRACES', 'SNOWFLAKE$DEBUG_LOGS');
```

**If the user wants all optional definitions enabled:**
Include all optional event names in the command.

---

### Step 4: Verify Configuration

**Goal:** Confirm that event sharing is properly enabled.

```sql
DESC APPLICATION <app_name>;
```

Check the output for:
- `authorize_telemetry_event_sharing` — should be `true` if required events exist
- `share_events_with_provider` — `TRUE` when all event definitions are enabled

Present the verification result to the user.

---

### Step 5: Query App Logs and Traces

**Goal:** Help the consumer troubleshoot by querying the event table for this app's telemetry.

Use the active event table identified in Step 1. Replace `<event_table>` with its fully qualified name and `<app_name>` with the application name (UPPERCASE).

> **Note:** SPCS containers emit `snow.database.name` instead of `snow.application.name`. The queries below use an OR condition to capture telemetry from both standard app code and SPCS services.

**Recent log messages:**
```sql
SELECT
  TIMESTAMP,
  RESOURCE_ATTRIBUTES['snow.executable.name'] AS executable,
  RECORD['severity_text'] AS severity,
  VALUE AS message
FROM <event_table>
WHERE (RESOURCE_ATTRIBUTES['snow.application.name'] = '<app_name>'
       OR RESOURCE_ATTRIBUTES['snow.database.name'] = '<app_name>')
  AND RECORD_TYPE = 'LOG'
  AND TIMESTAMP > DATEADD(hour, -24, CURRENT_TIMESTAMP())
ORDER BY TIMESTAMP DESC
LIMIT 50;
```

**Recent errors and warnings:**
```sql
SELECT
  TIMESTAMP,
  RESOURCE_ATTRIBUTES['snow.executable.name'] AS executable,
  RECORD['severity_text'] AS severity,
  VALUE AS message
FROM <event_table>
WHERE (RESOURCE_ATTRIBUTES['snow.application.name'] = '<app_name>'
       OR RESOURCE_ATTRIBUTES['snow.database.name'] = '<app_name>')
  AND RECORD_TYPE = 'LOG'
  AND RECORD['severity_text'] IN ('ERROR', 'WARN', 'FATAL')
  AND TIMESTAMP > DATEADD(hour, -24, CURRENT_TIMESTAMP())
ORDER BY TIMESTAMP DESC
LIMIT 50;
```

**Recent trace events (spans):**
```sql
SELECT
  TIMESTAMP,
  RESOURCE_ATTRIBUTES['snow.executable.name'] AS executable,
  RECORD['name'] AS span_name,
  RECORD_ATTRIBUTES AS attributes
FROM <event_table>
WHERE (RESOURCE_ATTRIBUTES['snow.application.name'] = '<app_name>'
       OR RESOURCE_ATTRIBUTES['snow.database.name'] = '<app_name>')
  AND RECORD_TYPE IN ('SPAN', 'SPAN_EVENT')
  AND TIMESTAMP > DATEADD(hour, -24, CURRENT_TIMESTAMP())
ORDER BY TIMESTAMP DESC
LIMIT 50;
```

**Application lifecycle events:**
```sql
SELECT TIMESTAMP, RECORD, VALUE
FROM <event_table>
WHERE (RESOURCE_ATTRIBUTES['snow.application.name'] = '<app_name>'
       OR RESOURCE_ATTRIBUTES['snow.database.name'] = '<app_name>')
  AND RECORD_TYPE = 'EVENT'
  AND TIMESTAMP > DATEADD(hour, -24, CURRENT_TIMESTAMP())
ORDER BY TIMESTAMP DESC
LIMIT 50;
```

Present results to the user. If no rows are returned:
> "No events found in the last 24 hours. The app may not have emitted telemetry yet, or the event table was set up after events occurred. Try invoking an app function and checking again."

---

## Stopping Points

- ✋ After Step 0: User provides application name (if not already known)
- ✋ After Step 2: User selects which optional event definitions to enable

**Resume rule:** Upon user approval, proceed directly to next step without re-asking.

## Output

- Active event table confirmed
- Telemetry event definitions reviewed and enabled per user decisions
- Event sharing verified via DESC APPLICATION
- App logs/traces/errors queried and presented to the user
