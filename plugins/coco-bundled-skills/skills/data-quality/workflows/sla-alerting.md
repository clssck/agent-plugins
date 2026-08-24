---
parent_skill: data-quality
---

# Workflow 5: SLA Monitoring & Alerting

## Trigger Phrases
- "Alert me on quality drops"
- "Enforce DQ SLAs"
- "Set up quality alerts"
- "Notify me when quality fails"
- "Create DQ alert"

## When to Load
Data-quality Step 2: alerting/SLA intent.

## Template to Use
**Primary:** `schema-sla-alert.sql`
- Creates Snowflake alert based on health threshold
- Triggers when health drops below specified percentage
- Can send notifications via email/webhook

## Execution Steps

### Step 1: Extract Database and Schema
- From user query: "DEMO_DQ_DB.SALES" → database='DEMO_DQ_DB', schema='SALES'
- If not already provided, ask which DATABASE.SCHEMA to monitor

### Step 2: Gather Alert Configuration
Ask the user for:
- Alert threshold: "What health percentage should trigger alerts? (default: 90%)"
- Notification method: "How should I notify you? (email/webhook)"
- Alert frequency: "How often to check? (default: every 60 minutes)"

### Step 3: Present Configuration for Approval

**⚠️ MANDATORY CHECKPOINT**: This workflow creates Snowflake objects (ALERT, TABLE). Present the full plan and wait for explicit approval before executing.

Present to user:
```
I will create the following Snowflake objects:

1. TABLE: <log_database>.<log_schema>.DQ_ALERT_LOG (if not exists)
2. ALERT: <alert_name>
   - Schema monitored: DATABASE.SCHEMA
   - Threshold: < X% health
   - Frequency: Every Y minutes
   - Warehouse: <warehouse>

Do you approve? (Yes / No / Modify)
```

**NEVER proceed without explicit user confirmation (e.g., "yes", "approved", "looks good").**

### Step 4: Execute Template
- Read: `templates/schema-sla-alert.sql`
- Replace all placeholders: `<database>`, `<schema>`, `<threshold>`, `<alert_name>`, `<warehouse>`, `<log_database>`, `<log_schema>`
- Execute each SQL statement in order (log table first, then alert, then resume)

### Step 5: Present Results
```
Alert Created: <alert_name>

Configuration:
- Schema: DATABASE.SCHEMA
- Threshold: < X% health
- Frequency: Every Y minutes

Status: Active

The alert will trigger when schema health drops below the threshold.
```

### Step 6: Next Steps
- "Monitor alerts in Snowflake UI under 'Monitoring > Alerts'."
- "Run `SHOW ALERTS LIKE '<alert_name>'` to verify."
- "To disable: `ALTER ALERT <alert_name> SUSPEND;`"

## Output Format
- Alert name
- Configuration details (threshold, frequency, notification)
- Activation status
- Instructions for monitoring

## Configuration Options
- **Threshold:** Health percentage that triggers alert (default: 90%)
- **Frequency:** How often to check (options: 15min, 1hr, 4hr, daily)
- **Notification:** Email, webhook, or Snowflake UI only
- **Alert Name:** Auto-generated: `{SCHEMA}_HEALTH_ALERT`

## What the Alert Does
1. Runs health check query every X minutes/hours
2. Compares result to threshold
3. If health < threshold → Triggers alert
4. Sends notification with:
   - Current health score
   - Failing metrics count
   - Top 3 failing tables/columns
   - Link to detailed report

## Error Handling
- If alert already exists → "Alert already exists. Update it?"
- If insufficient permissions → "Need MANAGE ALERT privilege."
- If notification method invalid → "Use valid email or webhook URL."

## Notes
- This is a **WRITE operation** — creates Snowflake ALERT and TABLE objects
- Requires MANAGE ALERT and CREATE TABLE privileges
- Alert persists until user drops it
- Can create multiple alerts with different thresholds
- Use for production monitoring, not ad-hoc checks

## Halting States
- **Success**: Alert created and resumed — present summary
- **User declined**: User chose "No" at approval checkpoint — do not create any objects
- **Permission error**: Inform user which privilege is missing
